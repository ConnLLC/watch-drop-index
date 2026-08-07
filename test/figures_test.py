#!/usr/bin/env python3
"""
Tests for the publication figures.

The risk here is not arithmetic. It is DRIFT: figures.py re-implements four rules
that already exist in build.py — the scope filter, the Retailer-enquiry remap, the
edition-size reader and the date parser — because build.py cannot be imported
without running a build. If build.py's copy changes and this one does not, the
figures keep computing cleanly and start disagreeing with the page, and the first
person to notice is a journalist holding a number we gave them.

So the drift guards below read build.py AS TEXT and assert the rules still match.
They are deliberately brittle. A failure here means "go and port the change",
not "loosen the test".

Run:  python3 test/figures_test.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import figures as F  # noqa: E402

PASS = FAIL = 0
BUILD = (ROOT / "build.py").read_text(encoding="utf-8")


def check(label: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok    {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}: got {got!r}, expected {want!r}")


def section(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


# ---------------------------------------------------------------------------
section("Drift guards — the page's rules and ours must be the same rules")

check("scope filter matches the runtime copy in build.py",
      "var NOT_LE = [/not formally limited/i, /^capped/i, /annually/i];" in BUILD, True)
check("our scope patterns are those three, in that order",
      [r.pattern for r in F.NOT_LE],
      ["not formally limited", "^capped", "annually"])
check("the Edition N/A vocabulary matches shortEd",
      "/unconfirmed|not stated|not disclosed|not numbered|special edition|size not stated/i" in BUILD,
      True)
check("our N/A vocabulary is the same alternation",
      F._ED_NA.pattern,
      "unconfirmed|not stated|not disclosed|not numbered|special edition|size not stated")
check("the tier list matches the runtime copy, in sort order",
      'var TIERS = [' + ",".join(f'"{t}"' for t in F.TIERS) + '];' in BUILD, True)
check("the Retailer-enquiry remap still exists in build.py",
      'tier="Buy at retailer", rank=3) if i["tier"] == "Retailer enquiry"' in BUILD, True)

# ---------------------------------------------------------------------------
section("Edition size — a number or nothing, never prose")

check("plain count", F.edition_size("300 numbered sets"), 300)
check("thousands separator", F.edition_size("9,999 pieces"), 9999)
check("status words beat digits", F.edition_size("Unconfirmed, likely 100"), None)
check("not disclosed", F.edition_size("Limited, size not stated"), None)
check("unique piece", F.edition_size("Unique piece"), 1)
check("total wins over the parts", F.edition_size("50 steel / 25 gold, 75 total"), 75)
check("slash without a total sums", F.edition_size("50 steel / 25 gold"), 75)
check("'each' is not a register-wide size", F.edition_size("300 each"), None)
check("a range takes the first figure", F.edition_size("200–250 pieces"), 200)
check("empty", F.edition_size(""), None)
check("prose with no digits", F.edition_size("Special edition"), None)

# ---------------------------------------------------------------------------
section("Release date — 2026 anchors, announcement dates do not")

check("day, month, year", F.date_pick("19 Dec 2025 (deliveries into 2026)")[:2], (2025, 12))
check("month and year", F.date_pick("May 2026"), (2026, 5, 0))
check("the 2026 month wins over the announcement",
      F.date_pick("Announced Dec 2025 for the Feb 2026 lunar year"), (2026, 2, 0))
check("bare month assumes the register's year", F.date_pick("April")[:2], (2026, 4))
check("quarter-only has no month", F.date_pick("Q3"), None)
check("TBC has no month", F.date_pick("TBC"), None)

# ---------------------------------------------------------------------------
section("The rendered set is what a reader can count on the page")

payload = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
items = payload["watches"]
shown = F.rendered(items)

check("nothing is invented", len(shown) <= len(items), True)
check("the remap leaves no old tier name behind",
      [w for w in shown if w["tier"] == "Retailer enquiry"], [])
check("every rendered tier is a tier the page can display",
      sorted({w["tier"] for w in shown} - set(F.TIERS)), [])
check("retracted entries are excluded",
      [w for w in shown if w.get("retracted")], [])
check("out-of-scope entries are excluded, not deleted from the file",
      all(F.in_scope(w) for w in shown) and len(items) >= len(shown), True)
check("the scope filter is doing something (if this hits 0, the rule broke)",
      len(items) > len(shown), True)

# A figure quoted publicly must never exceed the rendered set.
report = F.report(payload, out=open("/dev/null", "w"))
for key in ("verified", "images", "priced", "undisclosed"):
    check(f"{key} cannot exceed the rendered total", report[key] <= report["rendered"], True)
check("tier counts sum to the rendered total — the failure that started this",
      sum(report["tiers"].values()), report["rendered"])
check("brands counted from the rendered set, not the file",
      report["brands"], len({w["brand"] for w in shown}))

print(f"\n{'ALL PASS' if not FAIL else 'FAILURES'} — {PASS} passed, {FAIL} failed\n")
sys.exit(1 if FAIL else 0)
