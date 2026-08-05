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

import collections
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
        # The per-stage spend surface. Mirrored here for the reason this class's
        # docstring already gives: a double that silently lacks something the
        # production code reads turns an interface change into a confusing
        # AttributeError instead of a failed assertion. It did exactly that.
        self.by_stage = collections.Counter()
        self.calls_by_stage = collections.Counter()
        self.searches_by_stage = collections.Counter()

        self.carried_cad = 0.0

    @property
    def cad(self) -> float:
        return self.usd * R.USD_TO_CAD

    @property
    def week_cad(self) -> float:
        return self.carried_cad + self.cad

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
            if R.rank_for(w["status"], w.get("buyLabel", ""), w.get("tags", []),
                          w.get("buyKind")) != w["rank"]]
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
code, after = run_main(many, lambda enabled=True, budget_cad=0.0, carried_cad=0.0: StubModel(default=verdict("no", "sold_out", "Sold out", "high")),
                       ["--stages", "2"])
check("exits 20 when >15% would flip to Gone", code, 20)
check("data.json is NOT written", after["meta"]["revision"], 1)
check("no entry was persisted as Gone", [w for w in after["watches"] if w["status"] == "Sold out"], [])

section("Guardrail: silence is a failure")
R.fetch = lambda url: (None, "HTTP 403")
code, after = run_main([entry(id=f"{i:010d}", model=f"M{i}") for i in range(20)],
                       lambda enabled=True, budget_cad=0.0, carried_cad=0.0: StubModel(default=verdict("no", "sold_out")), ["--stages", "2"])
check("exits 21 when no page was readable", code, 21)
check("data.json is NOT written", after["meta"]["revision"], 1)

section("Guardrail: entries are never deleted, ids never rewritten")
R.fetch = lambda url: ("<html>" + "x" * 600 + "</html>", "ok")
watches = [entry(id=f"{i:010d}", model=f"M{i}") for i in range(20)]
ids_before = [w["id"] for w in watches]
code, after = run_main(watches, lambda enabled=True, budget_cad=0.0, carried_cad=0.0: StubModel(default=verdict("yes", "add_to_cart", "In stock")),
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


code, after = run_main(watches, lambda enabled=True, budget_cad=0.0, carried_cad=0.0: OneGone(), ["--stages", "2"])
check("exit 0", code, 0)
check("exactly one entry went Gone", sum(1 for w in after["watches"] if w["status"] == "Sold out"), 1)
check("the rest kept their tier", sum(1 for w in after["watches"] if w["tier"] == "Buy online now"), 39)

section("--dry-run writes nothing")
watches = [entry(id=f"{i:010d}", model=f"M{i}") for i in range(20)]
code, after = run_main(watches, lambda enabled=True, budget_cad=0.0, carried_cad=0.0: StubModel(default=verdict("yes", "add_to_cart", "In stock")),
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

section("The ceiling is WEEKLY, not per-run")
# This was a live bug until 2026-08-05, and the sort that hides behind a correct
# word. Every run started its meter at zero, so a ceiling called "weekly" was
# really "per invocation, unbounded per week". One manual dispatch spent 4.33 CAD
# and Monday's scheduled run would have been free to spend 5.00 more, with
# nothing anywhere noticing. Everything below asserts the word is now true.
check("a fresh week starts at zero",
      R.spend_carried({"spend": {"weekStart": "1999-01-04", "cad": 4.33}})[0], 0.0)
check("...and spend inside the current week is carried",
      R.spend_carried({"spend": {"weekStart": R.week_anchor(), "cad": 4.33}})[0], 4.33)
check("no ledger at all is zero, not an error", R.spend_carried({})[0], 0.0)
check("the week is anchored to a Monday a human can check on a calendar",
      R.week_anchor("2026-08-05"), "2026-08-03")
check("...including when today IS Monday", R.week_anchor("2026-08-03"), "2026-08-03")
check("...and Sunday belongs to the week that started six days earlier",
      R.week_anchor("2026-08-09"), "2026-08-03")
# A corrupt ledger must never hand out a free budget.
check("an unreadable ledger reads as fully spent, not as empty",
      R.spend_carried({"spend": {"weekStart": R.week_anchor(), "cad": "??"}})[0], float("inf"))

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
    """A real Model with no API client.

    Built through __init__ with enabled=False — which is exactly the path that
    skips the anthropic import and the key — and then switched on. It used to be
    hand-assembled with __new__ and a list of fields, which meant every new
    attribute on Model broke this with an AttributeError from inside production
    code rather than a failed assertion. Adding per-stage cost tracking did
    precisely that. Constructing it properly cannot drift.
    """
    m = R.Model(enabled=False, budget_cad=budget)
    m.enabled = True
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

# --- and the ceiling has to span the WEEK, not one invocation ---------------
carried = meter(budget=5.0)
carried.carried_cad = 4.33
check("a run inherits what the week already spent", round(carried.week_cad, 2), 4.33)
check("...and only 0.67 of the ceiling remains", round(carried.remaining_cad(), 2), 0.67)
carried._worst_call_cad = 1.0
check("...so a call larger than the remainder is refused", carried.exhausted(), True)
check("a second dispatch in the same week cannot spend a second full ceiling",
      carried._afford("availability"), False)
check("but a genuinely fresh week can", meter(budget=5.0).exhausted(), False)

# Written on EVERY run, free ones included — that is what rolls the week over on
# a Monday rather than waiting for the next paid run to notice.
m2 = meter(budget=5.0)
m2.carried_cad = 1.0
m2.usd = 1.0 / R.USD_TO_CAD
meta_out = {}
R.record_spend(meta_out, m2)
check("the ledger records the WEEK's total, not the run's",
      round(meta_out["spend"]["cad"], 2), 2.0)
check("...stamped with the week it belongs to",
      meta_out["spend"]["weekStart"], R.week_anchor())

section("A raised ceiling is scoped to ONE week and lapses by itself")
# "Raise it to 10 for this week" has to mean this week, or it is just a permanent
# raise nobody remembers to undo — the same silent drift this codebase keeps
# catching. The override is stamped with its week and stops applying when that
# week rolls over, so nobody has to remember anything.
THIS = R.week_anchor()
check("an override for THIS week raises the ceiling",
      R.effective_budget({"ceilingOverride": {"weekStart": THIS, "cad": 10}}, 5.0), (10.0, True))
check("an override for a PAST week does not — it lapses on its own",
      R.effective_budget({"ceilingOverride": {"weekStart": "1999-01-04", "cad": 10}}, 5.0),
      (5.0, False))
check("no override means the standing ceiling", R.effective_budget({}, 5.0), (5.0, False))
# Fails safe in every direction: a broken override must never be why a run spends
# more than it was allowed to.
check("an unreadable override falls back to the standing ceiling, not the raised one",
      R.effective_budget({"ceilingOverride": {"weekStart": THIS, "cad": "lots"}}, 5.0), (5.0, False))
check("a zero or negative override cannot disable the ceiling",
      (R.effective_budget({"ceilingOverride": {"weekStart": THIS, "cad": 0}}, 5.0),
       R.effective_budget({"ceilingOverride": {"weekStart": THIS, "cad": -1}}, 5.0)),
      ((5.0, False), (5.0, False)))
# And it composes with the ledger: the week's spend still counts against it.
raised = meter(budget=10.0)
raised.carried_cad = 4.33
check("a raised ceiling still counts what the week already spent",
      round(raised.remaining_cad(), 2), 5.67)

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
    lambda enabled=True, budget_cad=0.0, carried_cad=0.0: StubModel(
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
# A pass leaves NO stamp on the entry, deliberately. At a full daily sweep a
# per-entry "checked and fine today" rewrites every line of data.json daily for
# no information, and it asserts something this checker cannot know: it can
# prove a URL is dead, never that one renders for a reader. The run records the
# sweep; the entry records only what is wrong with it.
check("...and carries no stamp saying it passed", "imageCheck" in good, False)
stale = entry(id="0000000004", image="https://img.example/good.jpg",
              imageCheck={"date": "2026-01-01", "result": "rotted", "note": "HTTP 404"})
rot_stage([stale], {stale["image"]: ("ok", "image/jpeg")})
check("...and a recovered image loses its old failure stamp", "imageCheck" in stale, False)
check("a rotted one is cleared", dead["image"], None)
check("...and its credit goes with it", dead["imageCredit"], None)
check("...and the dead URL is remembered", dead["deadImages"], ["https://img.example/dead.jpg"])
check("a 403 keeps its photograph", blocked["image"], "https://img.example/403.jpg")
check("...and is reported as no answer, not as rot", len(s["unclear"]), 1)
check("the stage costs nothing", "model" in R.stage_image_rot.__code__.co_varnames, False)

# NO SAMPLING. This stage used to check a rotating 40 of 224 on the reasoning
# that requests are worth saving — but a HEAD costs no model call, no tokens and
# no budget, so there was nothing to save, and a photograph could stay broken on
# the page for six weeks while the checker reported all clear. Pinned as a test
# because the instruction to throttle it has been issued twice and withdrawn
# twice: if a cap on a free stage reappears, it should fail here.
check("the default is every photograph, not a sample", R.IMAGE_CHECK_BATCH, 0)
check("...and the stage's own default agrees",
      R.stage_image_rot.__defaults__[0], 0)
# Asserted on the candidate list rather than by running the stage: 120 URLs on
# one host are serialised by HostLimiter at PHOTO_HOST_DELAY apiece, so actually
# sweeping them here would make the suite take minutes to prove arithmetic.
many = [entry(id=f"{i:010d}", image=f"https://img.example/{i}.jpg") for i in range(120)]
check("a 120-entry register queues all 120", len(R.image_check_candidates(many, 0)), 120)
check("...and a batch is still honoured for testing",
      len(R.image_check_candidates(many, 5)), 5)

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

section("Buy links are classified by evidence, never by URL shape")
# "Buy online now" is the strongest claim the register makes. A homepage behind
# it is an unearned claim — and worse, the weekly stock check reads that same
# URL, so a homepage reads as "fine" for ever and the verification cannot detect
# the thing it exists to detect.
BRE = {"brand": "Breitling", "model": 'Navitimer B01 Chronograph 43 "Tribute to Concorde"',
       "ref": "AB01452A1L1X1"}
check("a reference number identifies the watch",
      R.names_the_watch(BRE, "product code ab01452a1l1x1, in stock"), True)
check("...even punctuated differently",
      R.names_the_watch(BRE, "Ref. AB01452-A1L1X1 available"), True)
check("the model's distinctive words identify it",
      R.names_the_watch(BRE, "The new Navitimer Tribute to Concorde has landed"), True)
check("a homepage does not", R.names_the_watch(BRE, "Welcome to Breitling. Shop all watches."), False)
check("nor does a generic category page",
      R.names_the_watch(BRE, "Limited edition automatic chronograph watches in steel and gold"), False)

for markup, label, want in [
    ('<button name="add">Add to Cart</button>', "a cart button", True),
    ('<form action="/cart/add">', "a cart form", True),
    ('{"@type": "Offer", "price": 9500}', "a schema.org offer", True),
    ("<a href='/x'>Pre-order now</a>", "a pre-order link", True),
    ("<p>Read our full review of this watch.</p>", "a review with no purchase", False),
]:
    check(f"purchase affordance in {label}", bool(R._CART.search(markup)), want)


def classify(entry, html, note="ok"):
    orig = R.fetch
    R.fetch = lambda url: (html, note)
    try:
        return R.classify_buy(entry)
    finally:
        R.fetch = orig


body = "x" * 400
e = {**BRE, "buy": "https://example.com/p"}
check("names it and sells it -> product",
      classify(e, f"<html><body>Navitimer Tribute to Concorde {body}"
                  '<button name="add">Add to Cart</button></body></html>')[0], "product")
check("names it but sells nothing -> listing",
      classify(e, f"<html><body>Navitimer Tribute to Concorde. Find a retailer. {body}</body></html>")[0],
      "listing")
check("never names it -> brand",
      classify(e, f"<html><body>Welcome to Breitling, shop all watches {body}"
                  '<button name="add">Add to Cart</button></body></html>')[0], "brand")
check("no URL at all -> none", R.classify_buy({**BRE, "buy": ""})[0], "none")

# The rule that matters most: an unreachable page is NOT a classification.
check("a 403 classifies nothing", classify(e, None, "HTTP 403")[0], None)
check("a timeout classifies nothing", classify(e, None, "fetch failed: Timeout")[0], None)
check("a too-short page classifies nothing", classify(e, "<html>tiny</html>")[0], None)
check("...and the reason is carried through", classify(e, None, "HTTP 403")[1], "HTTP 403")

section("The tier has to be earned by the link")
w1 = entry(id="0000000001", rank=0, tier="Buy online now")   # will classify listing
w2 = entry(id="0000000002", rank=0, tier="Buy online now")   # will classify product
w3 = entry(id="0000000003", rank=4, tier="AD or boutique")   # not a rank-0 claim
pages = {
    w1["id"]: f"<html><body>Testbrand Fixture One. Find a retailer. {body}</body></html>",
    w2["id"]: f"<html><body>Testbrand Fixture One {body}<button name=\"add\">Add to Cart</button></body></html>",
    w3["id"]: f"<html><body>Welcome, shop all {body}</body></html>",
}
orig = R.fetch
R.fetch = lambda url: (pages[url.rsplit("/", 1)[-1]], "ok")
try:
    for x in (w1, w2, w3):
        x["buy"] = "https://example.com/" + x["id"]
    s = R.stage_buy_links([w1, w2, w3])
finally:
    R.fetch = orig

check("each entry carries its evidence class", [w1["buyKind"], w2["buyKind"], w3["buyKind"]],
      ["listing", "product", "brand"])
check("only unearned rank-0 claims are queued for demotion",
      [w["id"] for w, _ in s["demote"]], [w1["id"]])
check("a product page keeps its claim", w2["tier"], "Buy online now")
R.apply_buy_demotions(s)
check("the unearned claim is dropped", w1["tier"], "Retailer enquiry")
check("...and rank stays consistent with tier", R.TIERS[w1["rank"]], w1["tier"])
check("the earned one is untouched", (w2["tier"], w2["rank"]), ("Buy online now", 0))
check("a non-rank-0 entry is classified but never demoted", w3["tier"], "AD or boutique")

# The rule lives INSIDE the derivation, not on top of it. Two rules that
# disagree would mean the weaker one wins every Monday: an availability check
# re-derives the tier and silently restores the claim we just took away.
check("the derivation itself demotes on evidence",
      R.rank_for("Available", "Add to cart", ["Buy online"], "listing"), 2)
check("...and keeps the claim when it is earned",
      R.rank_for("Available", "Add to cart", ["Buy online"], "product"), 0)
check("...but treats unknown as silence, not as failure",
      R.rank_for("Available", "Add to cart", ["Buy online"], None), 0)
check("evidence can never PROMOTE an entry",
      R.rank_for("Available", "Read the review", [], "product"), 2)
check("...nor resurrect a sold-out one",
      R.rank_for("Sold out", "Add to cart", ["Buy online"], "product"), 6)
demoted = entry(id="0000000009", rank=0, tier="Buy online now", buyKind="brand")
R.apply_tier(demoted)
check("a re-derivation keeps the demotion instead of reverting it",
      (demoted["tier"], demoted["rank"]), ("Retailer enquiry", 2))

section("A human edit wins, permanently, until a human releases it")
# The failure mode: Lowell hand-corrects a price on Sunday and Monday's run puts
# it back. Same shape as the demotion bug — two rules disagree and the one on a
# timer wins every time, so the edit survives exactly until nobody is watching.
R.PROPOSALS.clear()
e = entry(id="0000000011", price="$9,999", priceNum=9999)
R.mark_manual(e, ["price", "priceNum"])
check("the fields are recorded as owned", e["manual"], ["price", "priceNum"])
check("...and stamped with when and by whom", (e["editedOn"], e["editedBy"]), (R.today(), "admin"))
check("a guarded write to an owned field is refused",
      R.guarded_set(e, "price", "$1,000", "found on the brand page"), False)
check("...and the value is untouched", e["price"], "$9,999")
check("...and the disagreement is PROPOSED, not swallowed", len(R.PROPOSALS), 1)
check("...naming the field and both values",
      (R.PROPOSALS[0]["field"], R.PROPOSALS[0]["from"], R.PROPOSALS[0]["to"]),
      ("price", "$9,999", "$1,000"))
check("an unowned field still writes normally",
      (R.guarded_set(e, "desc", "new copy"), e["desc"]), (True, "new copy"))
R.PROPOSALS.clear()
check("writing the SAME value to an owned field proposes nothing",
      (R.guarded_set(e, "price", "$9,999"), len(R.PROPOSALS)), (False, 0))
check("bookkeeping fields can never be owned by a human",
      (R.mark_manual(e, ["imageProbe", "deadImages"]), "imageProbe" in e["manual"]), (None, False))
R.release_manual(e, ["price"])
check("releasing one field leaves the others owned", e["manual"], ["priceNum"])
check("...and automation can write it again",
      (R.guarded_set(e, "price", "$1,000"), e["price"]), (True, "$1,000"))
R.release_manual(e)
check("releasing everything drops the key", "manual" in e, False)

# Tier and rank are two spellings of one fact and must be guarded together, or a
# row renders one thing and filters as another.
R.PROPOSALS.clear()
pinned = entry(id="0000000012", status="Available", tier="Gone", rank=6, tags=[],
               buyLabel="Add to cart", manual=["tier"])
R.apply_tier(pinned)
check("a pinned tier is not re-derived", (pinned["tier"], pinned["rank"]), ("Gone", 6))
check("...and the derivation is proposed instead", len(R.PROPOSALS), 1)
R.PROPOSALS.clear()
pinned_rank = entry(id="0000000013", status="Available", tier="Gone", rank=6, tags=[],
                    buyLabel="Add to cart", manual=["rank"])
R.apply_tier(pinned_rank)
check("owning rank alone also protects tier", pinned_rank["tier"], "Gone")

# The whole point, end to end: a simulated refresh must not move a manual entry.
R.PROPOSALS.clear()
owned = entry(id="0000000014", status="Available", manual=["status"])
run_stage2([owned], StubModel(default=verdict("no", "sold_out", "Sold out.", "high")))
check("a sell-out cannot flip a manually owned status", owned["status"], "Available")
check("...and the tier does not move either", owned["tier"], "Buy online now")
check("...but the page is still QUOTED, because evidence is not a claim",
      owned["verified"]["note"], 'Purchase page reads: "Sold out."')
free = entry(id="0000000015", status="Available")
run_stage2([free], StubModel(default=verdict("no", "sold_out", "Sold out.", "high")))
check("an unowned entry still flips exactly as before", free["status"], "Sold out")

section("A hand-picked photograph is flagged when it breaks, never replaced")
# A human chose that picture. The machine reports the problem; it does not
# overrule the choice by scraping an og:image over the top of it.
mine = entry(id="0000000016", image="https://img.example/chosen.jpg",
             imageCredit="Lowell", manual=["image"])
s = rot_stage([mine], {mine["image"]: ("rotted", "HTTP 404")})
check("a broken manual image is KEPT", mine["image"], "https://img.example/chosen.jpg")
check("...and its credit is kept too", mine["imageCredit"], "Lowell")
check("...and it is flagged for a person", len(s["flagged"]), 1)
check("...and marked as needing a human, not as ordinary rot",
      (mine["imageCheck"]["result"], mine["imageCheck"]["manual"]), ("rotted", True))
check("...and it is NOT queued for automatic re-resolution",
      len(R.photo_candidates([mine])), 0)
auto = entry(id="0000000017", image="https://img.example/auto.jpg", imageCredit="SJX")
rot_stage([auto], {auto["image"]: ("rotted", "HTTP 404")})
check("an automatic image still gets cleared exactly as before", auto["image"], None)

section("Retracted entries are hidden, never deleted")
# Never delete: a mistaken entry is part of the audit trail and a sold-out one is
# the historical record.
gone = entry(id="0000000018", retracted=True, rank=0)
check("a retracted entry reads as retracted", R.is_retracted(gone), True)
check("an ordinary entry does not", R.is_retracted(entry()), False)
check("it is not worth spending a stock check on",
      len([w for w in [gone, entry(id="0000000019", rank=0)]
           if w["rank"] <= 2 and not R.is_retracted(w)]), 1)
check("...nor a photograph probe", len(R.photo_candidates([gone])), 0)
section("Takedowns are permanent, not seven-day")
# The failure this guards against is specific and embarrassing: honour a rights
# holder's request by nulling `image`, then re-publish the same photograph on the
# next photograph pass because the source article still offers it. Complying for
# exactly one day is not complying.
PHOTO = "https://www.ablogtowatch.com/wp-content/uploads/2026/06/a-watch-scaled.jpeg"
pay = {"meta": {}, "watches": [
    entry(id="1111111111", image=PHOTO, imageCredit="aBlogtoWatch", imageSize=[1200, 800]),
    entry(id="2222222222", image=PHOTO, imageCredit="aBlogtoWatch"),
    entry(id="3333333333", image="https://hodinkee.com/other.jpg", imageCredit="Hodinkee"),
]}
cleared = R.suppress_image(pay, PHOTO, "rights holder request")
check("a takedown clears the picture from every entry using it", cleared, 2)
check("...and leaves other photographs alone", pay["watches"][2]["image"], "https://hodinkee.com/other.jpg")
check("the credit goes with the picture", pay["watches"][0]["imageCredit"], None)
check("the entry itself survives — the objection is to the photograph",
      pay["watches"][0]["id"], "1111111111")
check("provenance is untouched: the outlet still reported the watch",
      pay["watches"][0]["source"], "https://monochrome-watches.com/a")
check("the rule is recorded with a date", bool(pay["suppressed"][0]["on"]), True)
check("actioning the same URL twice does not duplicate the rule",
      (R.suppress_image(pay, PHOTO), len(pay["suppressed"])), (0, 1))

rules = R.suppressions(pay)
check("suppression ignores a tracking query string",
      R.is_suppressed(PHOTO + "?utm_source=x", rules), True)
check("...and a www prefix", R.is_suppressed(PHOTO.replace("www.", ""), rules), True)
check("a different photograph from the same outlet is NOT suppressed",
      R.is_suppressed("https://www.ablogtowatch.com/wp-content/uploads/2026/06/b.jpeg", rules), False)
check("an unrelated URL is not suppressed", R.is_suppressed("https://hodinkee.com/x.jpg", rules), False)
check("a null image is not suppressed", R.is_suppressed(None, rules), False)

# The whole point: the photograph stage must REFUSE to re-adopt it.
readopt = {"meta": {}, "watches": [entry(id="1111111111", image=None)]}
readopt["suppressed"] = pay["suppressed"]
check("the photograph stage will not re-resolve a suppressed image",
      R.is_suppressed(PHOTO, R.suppressions(readopt)), True)
check("a suppressed entry is not even a candidate after enforcement", (
    R.enforce_suppressions({"meta": {}, "suppressed": pay["suppressed"],
                            "watches": [entry(id="4444444444", image=PHOTO)]}),
), (1,))

# An outlet objecting wholesale rather than to a single image.
whole = {"meta": {}, "suppressed": [{"domain": "example-press.com", "on": "2026-08-05"}],
         "watches": [entry(id="5555555555", image="https://cdn.example-press.com/a.jpg"),
                     entry(id="6666666666", image="https://example-press.com/b.jpg"),
                     entry(id="7777777777", image="https://notexample-press.com/c.jpg")]}
check("a domain rule covers the outlet and its subdomains", R.enforce_suppressions(whole), 2)
check("...without catching a lookalike domain", whole["watches"][2]["image"],
      "https://notexample-press.com/c.jpg")

check("no suppression list is not an error", R.enforce_suppressions({"meta": {}, "watches": []}), 0)

section("Source and calendar links — the other half of the sweep")
# Stage 7 checks images and stage 8 checks buy URLs; between them that was ~480
# of the register's ~750 links while the report said "full sweep". This closes it.


class LinkResp:
    def __init__(self, status, ctype="text/html", url=None):
        self.status_code = status
        self.headers = {"content-type": ctype} if ctype else {}
        self.url = url

    def close(self):
        pass


def run_link(url, resp, was_deep=None):
    orig = R.requests.head, R.requests.get
    R.requests.head = lambda *a, **k: resp
    R.requests.get = lambda *a, **k: resp
    try:
        return R.check_link(url, was_deep)
    finally:
        R.requests.head, R.requests.get = orig


DEEP = "https://monochrome-watches.com/some-watch-review/"
check("a live page is ok", run_link(DEEP, LinkResp(200, url=DEEP))[0], "ok")
check("a 404 is dead", run_link(DEEP, LinkResp(404, url=DEEP))[0], "dead")
check("a 410 is dead", run_link(DEEP, LinkResp(410, url=DEEP))[0], "dead")
check("a 403 is silence, NOT dead", run_link(DEEP, LinkResp(403, url=DEEP))[0], "unclear")
check("a 429 is silence too", run_link(DEEP, LinkResp(429, url=DEEP))[0], "unclear")
check("a 500 is silence", run_link(DEEP, LinkResp(500, url=DEEP))[0], "unclear")
check("an empty url is dead", run_link("", LinkResp(200))[0], "dead")

# THE SOFT-404 — the trap a bare status check cannot see. When a publisher pulls
# an article they very often 301 to the homepage rather than 404, so the link
# returns a clean 200 and the thing it pointed at is gone.
soft = run_link(DEEP, LinkResp(200, url="https://monochrome-watches.com/"))
check("a deep URL redirected to the bare root is a soft-404", soft[0], "dead")
check("...and says so rather than reporting a 200", "soft-404" in soft[1], True)
check("a deep URL redirected to ANOTHER deep URL is fine — sites reorganise",
      run_link(DEEP, LinkResp(200, url="https://monochrome-watches.com/moved/"))[0], "ok")
check("a URL that was ALREADY a root is not a soft-404 against itself",
      run_link("https://monochrome-watches.com/",
               LinkResp(200, url="https://monochrome-watches.com/"))[0], "ok")
check("root detection ignores a trailing slash",
      (R._is_bare_root("https://x.com"), R._is_bare_root("https://x.com/"),
       R._is_bare_root("https://x.com/a")), (True, True, False))
check("...but a query string means it is not a bare root",
      R._is_bare_root("https://x.com/?s=watch"), False)


def run_stage9(watches, results, calendar=None):
    orig = R.check_link
    R.check_link = lambda url, was_deep=None: results.get(url, ("ok", "HTTP 200"))
    try:
        return R.stage_links(watches, calendar)
    finally:
        R.check_link = orig


live = entry(id="0000000021", source="https://monochrome-watches.com/a")
gone = entry(id="0000000022", source="https://sjx.com/dead", conf="high")
blocked = entry(id="0000000023", source="https://fratellowatches.com/x")
s9 = run_stage9([live, gone, blocked], {
    gone["source"]: ("dead", "HTTP 404"),
    blocked["source"]: ("unclear", "HTTP 403"),
})
check("a live source is counted, not stamped", (s9["ok"], "sourceCheck" in live), (1, False))
check("a dead source is flagged on the entry", gone["sourceCheck"]["result"], "dead")
check("...and the ENTRY is kept — a dead source does not untrue the watch",
      gone["source"], "https://sjx.com/dead")
check("...and its confidence is NOT auto-downgraded; that is a person's call",
      gone["conf"], "high")
check("...and it is grouped by outlet, which is the fixable-cause half",
      s9["by_outlet"].most_common(1)[0][1], 1)
check("a blocked source is 'no answer', not dead", len(s9["unclear"]), 1)
check("...and is not counted as dead", len(s9["dead"]), 1)
check("the stage costs nothing", "model" in R.stage_links.__code__.co_varnames, False)

# A recovered source loses its old failure stamp, same as photographs.
recovered = entry(id="0000000024", source="https://monochrome-watches.com/b",
                  sourceCheck={"date": "2026-01-01", "result": "dead", "note": "HTTP 404"})
run_stage9([recovered], {})
check("a source that comes back loses its failure stamp", "sourceCheck" in recovered, False)

cal = {"drops": [{"what": "A drop", "url": "https://example.com/dead-drop"}],
       "events": [{"what": "An event", "url": "https://example.com/live"}]}
s9c = run_stage9([], {"https://example.com/dead-drop": ("dead", "HTTP 404")}, cal)
check("a dead calendar link is flagged for a human", len(s9c["cal_dead"]), 1)
check("...and the curated item is NOT edited or removed", len(cal["drops"]), 1)

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
