#!/usr/bin/env python3
"""
Tests for the weekly refresh.

The point of these is not coverage — it is the one rule the site's credibility
rests on: an entry moves only on positive, quotable evidence, and never on
silence. Every "unreadable page leaves it untouched" case below is a case that
would otherwise quietly turn this register into a guess.

Run:  python3 test/refresh_test.py
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import refresh as R  # noqa: E402

PASS = FAIL = 0


def check(label: str, got, want) -> None:
    global PASS, FAIL
    ok = got == want
    if ok:
        PASS += 1
        print(f"  ok    {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}: got {got!r}, expected {want!r}")


def section(t: str) -> None:
    print(f"\n=== {t} ===")


REAL = json.loads((ROOT / "data.json").read_text())


def entry(**over) -> dict:
    e = {
        "id": "aaaaaaaaaa", "brand": "Testbrand", "model": "Fixture One", "ref": "T-1",
        "cat": "Independents", "desc": "d", "specs": "s", "edition": "100 pieces",
        "price": "$1,000", "priceNum": 1000, "date": "March 2026", "status": "Available",
        "tier": "Buy online now", "rank": 0, "buy": "https://example.com/p",
        "buyLabel": "Add to cart", "source": "https://monochrome-watches.com/a",
        "image": None, "imageCredit": None, "conf": "high", "verified": None,
        "soldOutOn": None, "addedOn": "2026-01-01", "tags": ["Buy online"],
    }
    e.update(over)
    return e


class StubModel:
    """Returns a canned verdict per entry id.

    Mirrors the real Model's interface, budget surface included — a double that
    silently lacks a method the production code calls turns an interface change
    into a confusing AttributeError instead of a failed assertion.
    """

    def __init__(self, verdicts: dict | None = None, default=None, budget_cad: float = 0.0,
                 exhausted: bool = False):
        self.verdicts, self.default, self.calls = verdicts or {}, default, 0
        self.enabled = True
        self.budget_cad = budget_cad
        self.usd = 0.0
        self.searches = 0
        self.skipped = 0
        self.stopped_at = None
        self._exhausted = exhausted

    @property
    def cad(self) -> float:
        return self.usd * R.USD_TO_CAD

    def exhausted(self) -> bool:
        return self._exhausted

    def structured(self, prompt, schema, max_tokens=8000, stage="judgement"):
        if self.exhausted():
            self.skipped += 1
            self.stopped_at = self.stopped_at or stage
            return None
        self.calls += 1
        for wid, v in self.verdicts.items():
            if wid in prompt or (self._brand(wid) and self._brand(wid) in prompt):
                return v
        return self.default

    def _brand(self, wid):
        return None

    def search(self, *a, **k):
        return None


def verdict(obtainable, signal, quote="Sold out", confidence="high") -> dict:
    return {"obtainable": obtainable, "signal": signal, "quote": quote, "confidence": confidence}


def run_stage2(entries, model, fetch_result=("<html><body>" + "x" * 600 + "</body></html>", "ok")):
    orig = R.fetch
    R.fetch = lambda url: fetch_result
    try:
        return R.stage_availability(entries, model, None)
    finally:
        R.fetch = orig


# --------------------------------------------------------------------------

section("Tier derivation matches the live register")
mismatch = [w for w in REAL["watches"]
            if R.rank_for(w["status"], w.get("buyLabel", ""), w.get("tags", [])) != w["rank"]]
check("all 252 ranks reproduced", len(mismatch), 0)
check("all 252 ids reproduced", sum(1 for w in REAL["watches"]
                                    if R.make_id(w["brand"], w["model"]) == w["id"]), 252)
check("'Allocation' is never purchasable-online", R.rank_for("Allocation", "Add to cart", ["Buy online"]), 4)
check("'Available' + info-only label -> Retailer enquiry", R.rank_for("Available", "Read the review", []), 2)
check("'Available' + 'Buy online' tag -> Buy online now", R.rank_for("Available", "Read the review", ["Buy online"]), 0)

section("An unreadable page changes NOTHING")
for note in ["HTTP 403", "HTTP 500", "fetch failed: Timeout", "no url", "not html (application/pdf)"]:
    e = [entry()]
    snap = copy.deepcopy(e)
    run_stage2(e, StubModel(default=verdict("no", "sold_out")), fetch_result=(None, note))
    check(f"{note}: entry untouched", e, snap)

e = [entry()]
snap = copy.deepcopy(e)
run_stage2(e, StubModel(default=verdict("no", "sold_out")), fetch_result=("<html>tiny</html>", "ok"))
check("page below the readable-text floor: entry untouched", e, snap)

e = [entry()]
snap = copy.deepcopy(e)
run_stage2(e, StubModel(default=None))  # model failed / refused
check("model returned no verdict: entry untouched", e, snap)

section("Gone requires positive, high-confidence, quoted evidence")
e = [entry()]
run_stage2(e, StubModel(default=verdict("no", "sold_out", "This item is sold out.", "high")))
check("flips to Sold out", e[0]["status"], "Sold out")
check("rank becomes 6", e[0]["rank"], 6)
check("tier becomes Gone", e[0]["tier"], "Gone")
check("soldOutOn stamped", e[0]["soldOutOn"], R.today())
check("verified quotes the page", e[0]["verified"]["note"], 'Purchase page reads: "This item is sold out."')

for bad, why in [
    (verdict("no", "sold_out", "Sold out", "medium"), "medium confidence"),
    (verdict("no", "sold_out", "Sold out", "low"), "low confidence"),
    (verdict("no", "sold_out", "", "high"), "no quote"),
    (verdict("unclear", "not_a_product_page", "x", "high"), "not a product page"),
    (verdict("unclear", "contact_retailer", "Contact us", "high"), "contact_retailer"),
    (verdict("unclear", "unreadable", "", "high"), "unreadable"),
]:
    e = [entry()]
    snap = copy.deepcopy(e)
    run_stage2(e, StubModel(default=bad))
    check(f"never Gone on {why}", e, snap)

section("Out of stock is not the same as sold out")
# The first real run flipped a Sinn LE whose retailer page said "Temporarily Sold
# Out" into 'Waitlist or ballot', while a Nodus entry with near-identical wording
# went to 'Gone'. Same evidence, two different answers — and 'Waitlist or ballot'
# means the brand runs a ballot, which a retailer stock message never implies.
# Only a finished run moves a tier now; everything else is recorded and left alone.
for sig, label in [("temporarily_unavailable", "temporarily out of stock"),
                   ("waitlist_only", "a notify-me list")]:
    e = [entry()]
    run_stage2(e, StubModel(default=verdict("no", sig, "Temporarily Sold Out", "high")))
    check(f"{label}: tier unchanged", e[0]["tier"], "Buy online now")
    check(f"{label}: status unchanged", e[0]["status"], "Available")
    check(f"{label}: not stamped sold out", e[0]["soldOutOn"], None)
    check(f"{label}: but the page is quoted for the reader",
          e[0]["verified"]["note"], 'Purchase page reads: "Temporarily Sold Out"')

e = [entry()]
snap = copy.deepcopy(e)
run_stage2(e, StubModel(default=verdict("no", "temporarily_unavailable", "", "high")))
check("no quote means not even a note", e, snap)

section("Entries can move up as well as down")
e = [entry(status="Upcoming", rank=1, tier="Drop upcoming", buyLabel="Announced", tags=[])]
run_stage2(e, StubModel(default=verdict("yes", "preorder_open", "Pre-order now", "high")))
check("Upcoming -> Buy online now", e[0]["tier"], "Buy online now")
check("status becomes Pre-order", e[0]["status"], "Pre-order")
check("'Buy online' tag added", "Buy online" in e[0]["tags"], True)

e = [entry(status="Available", rank=2, tier="Retailer enquiry", buyLabel="Find a retailer", tags=[])]
run_stage2(e, StubModel(default=verdict("yes", "add_to_cart", "Add to cart", "high")))
check("Retailer enquiry -> Buy online now", e[0]["tier"], "Buy online now")

section("A confirmed entry gets a fresh stock check, not a tier change")
e = [entry()]
run_stage2(e, StubModel(default=verdict("yes", "add_to_cart", "In stock", "high")))
check("tier unchanged", e[0]["tier"], "Buy online now")
check("verified date refreshed", e[0]["verified"]["date"], R.today())

section("Demand is never conflated with distribution")
e = [entry()]
snap = copy.deepcopy(e)
run_stage2(e, StubModel(default=verdict("unclear", "contact_retailer", "Contact a boutique", "high")))
check("a rank-0 entry is never demoted to Retailer enquiry", e, snap)

section("Photograph probe caching")
check("404 source is permanent", R.probe_result_for("HTTP 404"), "dead")
check("410 source is permanent", R.probe_result_for("HTTP 410"), "dead")
check("403 bot wall is retried", R.probe_result_for("HTTP 403"), "blocked")
check("timeout is retried", R.probe_result_for("fetch failed: Timeout"), "blocked")
ws = [entry(id="p1", image=None, imageProbe={"date": R.today(), "result": "none"}),
      entry(id="p2", image=None, imageProbe={"date": R.today(), "result": "dead"}),
      entry(id="p3", image=None, imageProbe={"date": "2026-01-01", "result": "blocked"}),
      entry(id="p4", image="https://x/y.jpg"),
      entry(id="p5", image=None)]
check("only retryable candidates are probed",
      sorted(w["id"] for w in R.photo_candidates(ws)), ["p3", "p5"])

section("og:image extraction")
check("plain og:image", R.og_image('<meta property="og:image" content="https://a/b.jpg">', "https://s/"),
      "https://a/b.jpg")
check("http upgraded to https (mixed content would be blocked)",
      R.og_image('<meta property="og:image" content="http://a/b.jpg">', "https://s/"), "https://a/b.jpg")
check("protocol-relative", R.og_image('<meta property="og:image" content="//a/b.jpg">', "https://s/"),
      "https://a/b.jpg")
check("root-relative resolved against the source", R.og_image('<meta property="og:image" content="/b.jpg">',
      "https://s.com/post/1"), "https://s.com/b.jpg")
check("twitter:image fallback", R.og_image('<meta name="twitter:image" content="https://a/t.jpg">', "https://s/"),
      "https://a/t.jpg")
check("no image tag", R.og_image("<html><body>hi</body></html>", "https://s/"), None)

section("Page text and structured-data extraction")
check("script and style stripped",
      "alert" in R.page_text("<html><script>alert('x')</script><p>Sold out</p></html>"), False)
check("visible text survives", "Sold out" in R.page_text("<script>x</script><p>Sold out</p>"), True)
check("entities unescaped", "Grönefeld" in R.page_text("<p>Gr&ouml;nefeld</p>"), True)
check("schema.org availability read",
      R.jsonld_availability('{"availability": "https://schema.org/OutOfStock"}'), ["OutOfStock"])
check("no structured data", R.jsonld_availability("<html></html>"), [])


# ---------------------------------------------------- guardrails, end-to-end

def run_main(watches, model_factory, argv) -> tuple[int, dict]:
    """Runs main() against a temp data.json and returns (exit code, resulting data)."""
    tmp = Path(tempfile.mkdtemp())
    data = {"meta": {"updated": "2026-08-03", "count": len(watches), "brands": 1,
                     "revision": 1, "imagesResolved": 0, "domain": "watchdropindex.com",
                     "title": "t", "tagline": "t"},
            "watches": watches, "calendar": {}}
    (tmp / "data.json").write_text(json.dumps(data))
    old_data, old_report, old_root, old_argv, old_model = R.DATA, R.REPORT, R.ROOT, sys.argv, R.Model
    R.DATA, R.REPORT, R.ROOT = tmp / "data.json", tmp / "report.md", tmp
    R.Model = model_factory
    sys.argv = ["refresh.py"] + argv
    orig_fetch = R.fetch
    try:
        code = R.main()
        return code, json.loads((tmp / "data.json").read_text())
    finally:
        R.DATA, R.REPORT, R.ROOT, sys.argv, R.Model, R.fetch = (
            old_data, old_report, old_root, old_argv, old_model, orig_fetch)


section("Guardrail: blast radius")
many = [entry(id=f"{i:010d}", model=f"M{i}") for i in range(40)]
R.fetch = lambda url: ("<html>" + "x" * 600 + "</html>", "ok")
code, after = run_main(many, lambda enabled=True, budget_cad=0.0: StubModel(default=verdict("no", "sold_out", "Sold out", "high")),
                       ["--stages", "2"])
check("exits 20 when >15% would flip to Gone", code, 20)
check("data.json is NOT written", after["meta"]["revision"], 1)
check("no entry was persisted as Gone", [w for w in after["watches"] if w["status"] == "Sold out"], [])

section("Guardrail: silence is a failure")
R.fetch = lambda url: (None, "HTTP 403")
code, after = run_main([entry(id=f"{i:010d}", model=f"M{i}") for i in range(20)],
                       lambda enabled=True, budget_cad=0.0: StubModel(default=verdict("no", "sold_out")), ["--stages", "2"])
check("exits 21 when no page was readable", code, 21)
check("data.json is NOT written", after["meta"]["revision"], 1)

section("Guardrail: entries are never deleted, ids never rewritten")
R.fetch = lambda url: ("<html>" + "x" * 600 + "</html>", "ok")
watches = [entry(id=f"{i:010d}", model=f"M{i}") for i in range(20)]
ids_before = [w["id"] for w in watches]
code, after = run_main(watches, lambda enabled=True, budget_cad=0.0: StubModel(default=verdict("yes", "add_to_cart", "In stock")),
                       ["--stages", "2"])
check("exit 0", code, 0)
check("no entries lost", len(after["watches"]), 20)
check("every id preserved", [w["id"] for w in after["watches"]], ids_before)
check("meta.updated bumped", after["meta"]["updated"], R.today())
check("meta.revision bumped", after["meta"]["revision"], 2)
check("meta.count recomputed", after["meta"]["count"], 20)

section("Guardrail: a Gone flip within the cap does commit")
watches = [entry(id=f"{i:010d}", model=f"M{i}") for i in range(40)]
gone_one = {"0000000000": verdict("no", "sold_out", "Sold out", "high")}


class OneGone(StubModel):
    def structured(self, prompt, schema, max_tokens=8000, stage="judgement"):
        self.calls += 1
        return (verdict("no", "sold_out", "Sold out", "high") if "M0 " in prompt or "M0\n" in prompt
                else verdict("yes", "add_to_cart", "In stock", "high"))


code, after = run_main(watches, lambda enabled=True, budget_cad=0.0: OneGone(), ["--stages", "2"])
check("exit 0", code, 0)
check("exactly one entry went Gone", sum(1 for w in after["watches"] if w["status"] == "Sold out"), 1)
check("the rest kept their tier", sum(1 for w in after["watches"] if w["tier"] == "Buy online now"), 39)

section("--dry-run writes nothing")
watches = [entry(id=f"{i:010d}", model=f"M{i}") for i in range(20)]
code, after = run_main(watches, lambda enabled=True, budget_cad=0.0: StubModel(default=verdict("yes", "add_to_cart", "In stock")),
                       ["--stages", "2", "--dry-run"])
check("exit 0", code, 0)
check("data.json untouched on disk", after["meta"]["revision"], 1)

section("Ledger display names — the job never guesses one")
# A wrong maker is a factual error about who built a watch, and an invented model
# word is worse than a long name. Both must leave the field unset and escalate.


class NoAnswer:
    def structured(self, *a, **k):
        return None


class Inventive:
    """Answers, but with a word that is not in the full model name."""

    def structured(self, *a, **k):
        return {"names": [
            {"id": "collab", "maker": "BOLDR", "maker_certain": True, "short_model": ""},
            {"id": "long", "maker": "", "maker_certain": False,
             "short_model": "Deepsea Challenger Special"},
        ]}


class Careful:
    def structured(self, *a, **k):
        return {"names": [
            {"id": "collab", "maker": "BOLDR", "maker_certain": True, "short_model": ""},
            {"id": "maker-first", "maker": "Baltic", "maker_certain": True, "short_model": ""},
            {"id": "long", "maker": "", "maker_certain": False,
             "short_model": "Deepsea Challenge Titanium"},
        ]}


def naming_fixtures():
    return [
        {"id": "collab", "brand": "Worn & Wound × BOLDR", "model": "Field Watch"},
        {"id": "maker-first", "brand": "Baltic × SpaceOne", "model": "Seconde Majeure"},
        {"id": "long", "brand": "Rolex",
         "model": "Oyster Perpetual Deepsea Challenge Titanium RLX 50th"},
    ]


check("only collabs and long names are looked at",
      [e["id"] for e in naming_fixtures() if R.needs_display_names(e)],
      ["collab", "maker-first", "long"])
check("a short, single-brand entry needs nothing",
      R.needs_display_names({"brand": "Rolex", "model": "Submariner"}), False)

entries = naming_fixtures()
queries = R.assign_display_names(entries, NoAnswer())
check("no model answer means no name is written",
      [k for e in entries for k in e if k.startswith("display")], [])
check("...and every name is escalated instead", len(queries), 3)

entries = naming_fixtures()
queries = R.assign_display_names(entries, Inventive())
check("an invented word is refused",
      [k for e in entries for k in e if k == "displayModel"], [])
check("...and that name goes to design",
      any("introduces" in q for q in queries), True)
check("an uncertain maker is escalated, not guessed",
      any("which party makes the watch" in q for q in queries), True)

entries = naming_fixtures()
queries = R.assign_display_names(entries, Careful())
by_id = {e["id"]: e for e in entries}
check("a maker named second is written down", by_id["collab"].get("displayBrand"), "BOLDR")
check("a maker named first needs no field at all",
      "displayBrand" in by_id["maker-first"], False)
check("a clean short title is written down",
      by_id["long"].get("displayModel"), "Deepsea Challenge Titanium")
check("...and it fits the column", len(by_id["long"]["displayModel"]) <= R.DISPLAY_LIMIT, True)
check("nothing is left for design", queries, [])

section("Corrections from the editor's journal are applied verbatim")
w = [{"id": "a", "brand": "B", "model": "M", "desc": "old"}]
patch = Path(tempfile.mkdtemp()) / "corrections.json"
patch.write_text(json.dumps({
    "a": {"displayModel": "Short title", "desc": "new", "displayBrand": "   "},
    "ghost": {"desc": "no such entry"},
}))
applied, unknown = R.apply_corrections(w, patch)
check("applied to the entry that exists", applied, 1)
check("an unknown id is reported, not invented", unknown, ["ghost"])
check("the description is replaced", w[0]["desc"], "new")
check("the display name is set", w[0]["displayModel"], "Short title")
check("a blank field is ignored rather than written", "displayBrand" in w[0], False)

section("Scope — a production cap is not a limited edition")
check("capped by an order window is out", R.in_scope({"edition": "Capped by the order window"}), False)
check("an annual cap is out", R.in_scope({"edition": "Up to 250 annually"}), False)
check("not formally limited is out", R.in_scope({"edition": "Not formally limited — stone-constrained"}), False)
check("a real edition size is in", R.in_scope({"edition": "100 pieces"}), True)
check("an unconfirmed size stays in", R.in_scope({"edition": "Unconfirmed"}), True)
# The rule lives in three places and they must agree, or the site renders a
# different register from the one the job reports on.
build_src = (ROOT / "build.py").read_text()
page_src = (ROOT / "index.html").read_text()
for pattern in ("not formally limited", "^capped", "annually"):
    check(f"build.py carries the {pattern!r} rule", pattern in build_src, True)
    check(f"the page carries the {pattern!r} rule", pattern in page_src, True)

section("The spend guard measures real usage")
# Money is the one thing here nobody can eyeball afterwards, so the arithmetic
# is pinned to the published rates rather than trusted.


class Usage:
    def __init__(self, **kw):
        self.input_tokens = kw.get("input_tokens", 0)
        self.output_tokens = kw.get("output_tokens", 0)
        self.cache_creation_input_tokens = kw.get("cache_creation_input_tokens", 0)
        self.cache_read_input_tokens = kw.get("cache_read_input_tokens", 0)
        self.server_tool_use = kw.get("server_tool_use")


class Searches:
    def __init__(self, n):
        self.web_search_requests = n


def meter(budget=5.0):
    m = R.Model.__new__(R.Model)          # no API client, no key needed
    m.enabled, m.calls, m.usd, m.searches = True, 0, 0.0, 0
    m.budget_cad, m.skipped, m.stopped_at, m._worst_call_cad = budget, 0, None, 0.0
    return m


m = meter()
m._charge(Usage(input_tokens=1_000_000, output_tokens=1_000_000))
check("a million in and a million out costs $30 on Opus 5", round(m.usd, 6), 30.0)
check("...converted at the fixed rate", round(m.cad, 4), round(30.0 * R.USD_TO_CAD, 4))

m = meter()
m._charge(Usage(input_tokens=0, server_tool_use=Searches(5)))
check("web search bills $10 per 1,000", round(m.usd, 6), 0.05)
check("...and the searches are counted for the report", m.searches, 5)

m = meter()
m._charge(Usage(cache_read_input_tokens=1_000_000, cache_creation_input_tokens=1_000_000))
check("cache reads and writes are priced, not ignored", round(m.usd, 4), 6.75)

m = meter()
m._charge(Usage())  # a usage object with nothing on it must not raise
check("an empty usage block costs nothing and does not raise", m.usd, 0.0)

section("The ceiling is respected, not merely noticed")
m = meter(budget=1.00)
check("a fresh meter is not exhausted", m.exhausted(), False)
# One call of this size costs about 0.175 CAD, so a 1.00 CAD ceiling should buy
# several and then refuse — the invariant being that it refuses BEFORE going
# over, not after. Spending the ceiling and then apologising is not a ceiling.
spent_calls = 0
while not m.exhausted() and spent_calls < 50:
    m._charge(Usage(input_tokens=20_000, output_tokens=1_000))
    spent_calls += 1
check("several calls fit inside a 1.00 CAD ceiling", spent_calls > 1, True)
check("it stops before the ceiling is crossed, not after", m.cad <= m.budget_cad, True)
check("the reserve is a real call's cost, self-calibrated", round(m._worst_call_cad, 4),
      round(0.175, 4))
check("_afford records what it refused", (m._afford("availability"), m.skipped, m.stopped_at),
      (False, 1, "availability"))
check("a zero budget means no ceiling at all", meter(budget=0).exhausted(), False)

section("A budget stop is safe to commit, and is not a failure")
# The refused call returns None — the same thing an unreadable page returns — so
# every decision rule already leaves the entry alone. That is what makes stopping
# mid-run safe rather than something to roll back.
e = [entry()]
snap = copy.deepcopy(e)
broke = StubModel(default=verdict("no", "sold_out", "Sold out", "high"), exhausted=True)
summary = run_stage2(e, broke)
check("nothing moves once the ceiling is hit", e, snap)
check("...and the run records why", summary["budget_skipped"], 1)
check("...without pretending it read the page", summary["read"], 0)

watches = [entry(id=f"{i:010d}", model=f"M{i}") for i in range(20)]
code, after = run_main(
    watches,
    lambda enabled=True, budget_cad=0.0: StubModel(
        default=verdict("yes", "add_to_cart", "In stock"), exhausted=True),
    ["--stages", "2"])
check("a fully-skipped run is green, not red", code, 0)
check("...and every entry is intact", sum(1 for w in after["watches"] if w["tier"] == "Buy online now"), 20)

section("Photographs are free and uncapped, but polite")
check("the stage takes no model at all", "model" in R.stage_photos.__code__.co_varnames, False)

pending = [entry(id=f"{i:010d}", model=f"M{i}", image=None,
                 source=f"https://{'alpha' if i % 2 else 'beta'}.example/{i}") for i in range(6)]
hits: list[tuple[str, float]] = []
lock_for_test = __import__("threading").Lock()


def timed_fetch(url):
    with lock_for_test:
        hits.append((R.domain_of(url), R.time.monotonic()))
    return ("<html><head></head><body>" + "x" * 400 + "</body></html>", "ok")


orig_fetch, orig_delay = R.fetch, R.PHOTO_HOST_DELAY
R.fetch, R.PHOTO_HOST_DELAY = timed_fetch, 0.25
try:
    R.stage_photos(pending)
finally:
    R.fetch, R.PHOTO_HOST_DELAY = orig_fetch, orig_delay

check("every pending entry is attempted, not a batch of them", len(hits), 6)
gaps_ok = True
for host in {h for h, _ in hits}:
    times = sorted(t for h, t in hits if h == host)
    for a, b in zip(times, times[1:]):
        if b - a < 0.2:          # 0.25s spacing, small tolerance for scheduling
            gaps_ok = False
check("two requests to one outlet are spaced apart", gaps_ok, True)
check("but different outlets still run in parallel",
      max(t for _, t in hits) - min(t for _, t in hits) < 6 * 0.25, True)

section("The calendar expires on dates, deterministically and for free")
# A "Dated opportunities" list advertising a drop that already happened is the
# small visible rot that tells a reader nobody is home — and it needs no
# research to catch, only arithmetic. So this is plain code, not a model call.
for text, want in [
    ("6 Aug 2026", "2026-08-06"),
    ("13–16 Aug 2026", "2026-08-16"),       # a range expires on its END
    ("2–6 Sept 2026", "2026-09-06"),        # 4-letter month abbreviation
    ("Now → Sept 2026", "2026-09-30"),      # open-ended window: end of month
    ("Now → early Oct 2026", "2026-10-10"),
    ("Mid-Aug 2026", "2026-08-20"),
    ("Nov 2026", "2026-11-30"),
    ("Q4 2026", "2026-12-31"),
    ("31 Feb 2026", "2026-02-28"),          # an impossible day must not raise
    ("Live now", None),                     # no date at all — a different case
    ("", None),
]:
    got = R.calendar_end(text)
    check(f"{text!r} ends {want}", got.isoformat() if got else None, want)

check("the whole stage takes no model", "model" in R.stage_calendar.__code__.co_varnames, False)


def run_calendar(cal, watches, when):
    orig = R.today
    R.today = lambda: when
    try:
        return R.stage_calendar(cal, watches)
    finally:
        R.today = orig


cal = {"drops": [{"date": "6 Aug 2026", "what": "Ming batch", "url": "https://m.example/x"},
                 {"date": "Nov 2026", "what": "Baltic deliveries", "url": "https://b.example/x"}],
       "events": [{"date": "13–16 Aug 2026", "what": "Watch Week Aspen"}],
       "expected": [{"what": "GWD novelties"}],
       "notHappening": [{"what": "Only Watch 2026", "checkedOn": R.today()}]}
summary = run_calendar(cal, [], "2026-08-17")

check("a passed drop leaves the live list", [d["what"] for d in cal["drops"]], ["Baltic deliveries"])
check("a finished event leaves too", cal["events"], [])
check("...but nothing is deleted", sorted(i["what"] for i in cal["passed"]),
      ["Ming batch", "Watch Week Aspen"])
check("...with the reason recorded",
      [i["passedBecause"] for i in cal["passed"] if i["what"] == "Ming batch"], ["ended 2026-08-06"])
check("a future date is left alone", len(summary["expired"]), 2)
check("an unstamped editorial claim is flagged",
      [i["what"] for _, i, _ in summary["stale"]], ["GWD novelties"])
check("...and a freshly-stamped one is not", len(summary["stale"]), 1)

# The day before, none of it should move — an opportunity must not vanish while
# it is still live.
cal2 = {"drops": [{"date": "6 Aug 2026", "what": "Ming batch"}], "events": [],
        "expected": [], "notHappening": []}
run_calendar(cal2, [], "2026-08-06")
check("a drop is still live on its own day", [d["what"] for d in cal2["drops"]], ["Ming batch"])

# "Live now" has no date to expire on, so the register retires it: the linked
# watch going Gone is the evidence.
live = {"date": "Live now", "what": "Doxa for Hodinkee", "url": "https://le.example/doxa"}
cal3 = {"drops": [live], "events": [], "expected": [], "notHappening": []}
run_calendar(cal3, [entry(buy="https://le.example/doxa", rank=0)], "2026-08-17")
check("an undated drop survives while its watch is buyable", cal3["drops"], [live])
cal4 = {"drops": [dict(live)], "events": [], "expected": [], "notHappening": []}
s4 = run_calendar(cal4, [entry(buy="https://le.example/doxa", rank=6, tier="Gone")], "2026-08-17")
check("...and retires when that watch goes Gone", cal4["drops"], [])
check("...naming the watch as the reason",
      "is now Gone" in cal4["passed"][0]["passedBecause"], True)
check("an undated drop with no link is reported, not silently kept forever",
      len(run_calendar({"drops": [{"date": "Live now", "what": "orphan"}], "events": [],
                        "expected": [], "notHappening": []}, [], "2026-08-17")["undated"]), 1)

section("Rotted image URLs — only positive evidence clears a photograph")
# The photograph stage only looks at entries with NO image, so a URL that dies
# after we resolved it is invisible to it forever and the row renders a broken
# picture. A 25-entry sample of live data on 2026-08-04 found one already dead,
# which puts the real number near 9 of 224. The danger in fixing it is the
# opposite error: a hotlink-blocking CDN answering 403 must never be allowed to
# delete a perfectly good photograph.


class Resp:
    def __init__(self, status, ctype="image/jpeg"):
        self.status_code = status
        self.headers = {"content-type": ctype} if ctype else {}

    def close(self):
        pass


def with_http(head=None, get=None, err=None):
    """Swap requests.head/get for canned answers."""
    import requests as rq

    def fake(*a, **k):
        if err:
            raise rq.RequestException(err)
        return head if fake.first else get
    return fake


def run_check(url, head=None, get=None, raises=False):
    import requests as rq
    oh, og = rq.head, rq.get
    calls = {"head": 0, "get": 0}

    def h(*a, **k):
        calls["head"] += 1
        if raises:
            raise rq.Timeout("slow")
        return head

    def g(*a, **k):
        calls["get"] += 1
        if raises:
            raise rq.Timeout("slow")
        return get if get is not None else head
    rq.head, rq.get = h, g
    try:
        return R.check_image(url), calls
    finally:
        rq.head, rq.get = oh, og


U = "https://img.example/a.jpg"
check("a served image is fine", run_check(U, head=Resp(200, "image/jpeg"))[0], ("ok", "image/jpeg"))
check("a 404 is rot", run_check(U, head=Resp(404, "text/html"))[0][0], "rotted")
check("a 410 is rot", run_check(U, head=Resp(410, "text/html"))[0][0], "rotted")
check("a 200 serving HTML is a soft 404, also rot",
      run_check(U, head=Resp(200, "text/html"))[0][0], "rotted")
check("a 403 is silence, NOT rot",
      run_check(U, head=Resp(403, None), get=Resp(403, None))[0][0], "unclear")
check("a 500 is silence", run_check(U, head=Resp(500, "text/html"))[0][0], "unclear")
check("a timeout is silence", run_check(U, raises=True)[0][0], "unclear")
check("a rejected HEAD falls back to a ranged GET, not a full download",
      run_check(U, head=Resp(405, None), get=Resp(200, "image/png"))[0], ("ok", "image/png"))

# The whole point: what the stage does to the entry.
def rot_stage(watches, results, batch=0):
    orig = R.check_image
    R.check_image = lambda url: results[url]
    try:
        return R.stage_image_rot(watches, batch)
    finally:
        R.check_image = orig


good = entry(id="0000000001", image="https://img.example/good.jpg", imageCredit="Monochrome")
dead = entry(id="0000000002", image="https://img.example/dead.jpg", imageCredit="SJX")
blocked = entry(id="0000000003", image="https://img.example/403.jpg", imageCredit="Fratello")
ws = [good, dead, blocked]
s = rot_stage(ws, {good["image"]: ("ok", "image/jpeg"),
                   dead["image"]: ("rotted", "HTTP 404"),
                   blocked["image"]: ("unclear", "HTTP 403")})
check("a good photograph is kept", good["image"], "https://img.example/good.jpg")
check("...and stamped so the rotation moves on", good["imageCheck"]["result"], "ok")
check("a rotted one is cleared", dead["image"], None)
check("...and its credit goes with it", dead["imageCredit"], None)
check("...and the dead URL is remembered", dead["deadImages"], ["https://img.example/dead.jpg"])
check("a 403 keeps its photograph", blocked["image"], "https://img.example/403.jpg")
check("...and is reported as no answer, not as rot", len(s["unclear"]), 1)
check("the stage costs nothing", "model" in R.stage_image_rot.__code__.co_varnames, False)

# THE LOOP THIS HAS TO AVOID: clearing a dead image sends the entry back to the
# photograph stage, which re-reads the same article, finds the same dead
# og:image, and writes it straight back — for ever, every week.
orig_fetch = R.fetch
R.fetch = lambda url: ('<html><head><meta property="og:image" '
                       'content="https://img.example/dead.jpg"></head><body>'
                       + "x" * 400 + "</body></html>", "ok")
try:
    ps = R.stage_photos([dead])
finally:
    R.fetch = orig_fetch
check("the photograph stage will not re-adopt a URL proven dead", dead["image"], None)
check("...and says so rather than blaming the source",
      len(ps["stale_source"]), 1)
check("...but leaves the door open for the outlet to fix it",
      dead["imageProbe"]["result"], "blocked")

# A DIFFERENT image on the same article is still welcome.
fixed = entry(id="0000000004", image=None,
              deadImages=["https://img.example/dead.jpg"])
R.fetch = lambda url: ('<html><head><meta property="og:image" '
                       'content="https://img.example/fresh.jpg"></head><body>'
                       + "x" * 400 + "</body></html>", "ok")
try:
    R.stage_photos([fixed])
finally:
    R.fetch = orig_fetch
check("a repaired article still resolves normally", fixed["image"], "https://img.example/fresh.jpg")

section("The rot check rotates instead of re-checking everything weekly")
pool = [entry(id=f"{i:010d}", image=f"https://img.example/{i}.jpg") for i in range(10)]
pool[0]["imageCheck"] = {"date": "2026-01-01", "result": "ok"}       # oldest
pool[1]["imageCheck"] = {"date": R.today(), "result": "ok"}          # checked today
picked = [w["id"] for w in R.image_check_candidates(pool, 3)]
check("never-checked entries come first", len(picked), 3)
check("...and the freshly-checked one is not among them", pool[1]["id"] in picked, False)
check("the oldest check outranks a recent one",
      R.image_check_candidates([pool[0], pool[1]], 1)[0]["id"], pool[0]["id"])
check("batch 0 means everything", len(R.image_check_candidates(pool, 0)), 10)
check("entries with no photograph are not candidates",
      len(R.image_check_candidates([entry(image=None)], 0)), 0)

section("Corrupt data.json aborts without touching anything")
tmp = Path(tempfile.mkdtemp())
(tmp / "data.json").write_text("{ this is not json")
old = R.DATA
R.DATA = tmp / "data.json"
sys.argv = ["refresh.py"]
try:
    check("exits 1 on unparseable data", R.main(), 1)
finally:
    R.DATA = old

print(f"\n{'ALL PASS' if not FAIL else 'FAILURES'} — {PASS} passed, {FAIL} failed\n")
sys.exit(1 if FAIL else 0)
