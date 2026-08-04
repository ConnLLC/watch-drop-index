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
    """Returns a canned verdict per entry id."""

    def __init__(self, verdicts: dict | None = None, default=None):
        self.verdicts, self.default, self.calls = verdicts or {}, default, 0
        self.enabled = True

    def structured(self, prompt, schema, max_tokens=8000):
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
code, after = run_main(many, lambda enabled=True: StubModel(default=verdict("no", "sold_out", "Sold out", "high")),
                       ["--stages", "2"])
check("exits 20 when >15% would flip to Gone", code, 20)
check("data.json is NOT written", after["meta"]["revision"], 1)
check("no entry was persisted as Gone", [w for w in after["watches"] if w["status"] == "Sold out"], [])

section("Guardrail: silence is a failure")
R.fetch = lambda url: (None, "HTTP 403")
code, after = run_main([entry(id=f"{i:010d}", model=f"M{i}") for i in range(20)],
                       lambda enabled=True: StubModel(default=verdict("no", "sold_out")), ["--stages", "2"])
check("exits 21 when no page was readable", code, 21)
check("data.json is NOT written", after["meta"]["revision"], 1)

section("Guardrail: entries are never deleted, ids never rewritten")
R.fetch = lambda url: ("<html>" + "x" * 600 + "</html>", "ok")
watches = [entry(id=f"{i:010d}", model=f"M{i}") for i in range(20)]
ids_before = [w["id"] for w in watches]
code, after = run_main(watches, lambda enabled=True: StubModel(default=verdict("yes", "add_to_cart", "In stock")),
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
    def structured(self, prompt, schema, max_tokens=8000):
        self.calls += 1
        return (verdict("no", "sold_out", "Sold out", "high") if "M0 " in prompt or "M0\n" in prompt
                else verdict("yes", "add_to_cart", "In stock", "high"))


code, after = run_main(watches, lambda enabled=True: OneGone(), ["--stages", "2"])
check("exit 0", code, 0)
check("exactly one entry went Gone", sum(1 for w in after["watches"] if w["status"] == "Sold out"), 1)
check("the rest kept their tier", sum(1 for w in after["watches"] if w["tier"] == "Buy online now"), 39)

section("--dry-run writes nothing")
watches = [entry(id=f"{i:010d}", model=f"M{i}") for i in range(20)]
code, after = run_main(watches, lambda enabled=True: StubModel(default=verdict("yes", "add_to_cart", "In stock")),
                       ["--stages", "2", "--dry-run"])
check("exit 0", code, 0)
check("data.json untouched on disk", after["meta"]["revision"], 1)

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
