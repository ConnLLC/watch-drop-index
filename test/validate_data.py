#!/usr/bin/env python3
"""
The last gate before data.json can reach the site.

This runs in CI after a refresh and before the commit, and it exists because
Pages deploys from `main`: the commit IS the deploy, so there is no staging step
where a malformed file could be caught. If this exits non-zero, nothing is
committed and the live site keeps yesterday's data — which is always better than
publishing a register whose own figures disagree with each other.

Extracted from the inline step in refresh.yml when the schedule was split
(2026-08-05). Both the daily sweep and the weekly refresh call it. Kept as one
file rather than two copies on purpose: two validators drift, and the one that
drifts is the one that stops catching things.

Run:  python3 test/validate_data.py [path/to/data.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# RANK order, which is not the same as the sort order the page uses — the two
# lists differ in their first three entries, so copying the wrong one produces a
# validator that condemns every healthy entry. Index is the rank.
TIERS = ["Buy online now", "Drop upcoming", "Retailer enquiry", "Waitlist or ballot",
         "AD or boutique", "In person only", "Gone"]

# Every field here is one a reader sees or the register's honesty depends on.
# `source` is in the list because an entry with no provenance cannot carry an
# honest confidence rating; `buy` because a register about where to get one is
# not much use without it.
REQUIRED = ("id", "brand", "model", "buy", "source", "conf", "addedOn")


def validate(payload: dict) -> list[str]:
    errs: list[str] = []
    meta = payload.get("meta", {})
    watches = payload.get("watches", [])

    # The counts the masthead quotes. They are recomputed by the refresh, so a
    # mismatch means a stage wrote entries without updating the totals — the
    # page would then advertise a number that is not the number of rows in it.
    if meta.get("count") != len(watches):
        errs.append(f"meta.count {meta.get('count')} != {len(watches)} entries")
    if meta.get("brands") != len({x["brand"] for x in watches}):
        errs.append("meta.brands is stale")
    if meta.get("imagesResolved") != sum(1 for x in watches if x.get("image")):
        errs.append("meta.imagesResolved is stale")

    ids = [x["id"] for x in watches]
    if len(ids) != len(set(ids)):
        errs.append("duplicate ids")

    for x in watches:
        # rank and tier are two spellings of one fact. When they disagree the
        # row renders one thing and filters as another.
        if not isinstance(x.get("rank"), int) or not 0 <= x["rank"] < len(TIERS):
            errs.append(f"{x.get('id')}: rank {x.get('rank')!r} is not a tier index")
        elif TIERS[x["rank"]] != x["tier"]:
            errs.append(f"{x['id']}: rank {x['rank']} does not match tier {x['tier']!r}")
        # "Sold out" with no date is a claim with no evidence behind it.
        if x.get("status") == "Sold out" and not x.get("soldOutOn"):
            errs.append(f"{x['id']}: Sold out with no soldOutOn")
        for f in REQUIRED:
            if not x.get(f):
                errs.append(f"{x['id']}: missing {f}")
        # The search residue is a dated claim, and the date is the whole point:
        # it is what makes "no product page exists" expire instead of freezing
        # an entry out of ever being upgraded. A residue with no date, or with a
        # result nothing recognises, is a flag that never lifts.
        residue = x.get("buySearch")
        if residue is not None:
            if not isinstance(residue, dict):
                errs.append(f"{x['id']}: buySearch is not an object")
            elif residue.get("result") not in ("product", "none", "unverified"):
                errs.append(f"{x['id']}: buySearch.result {residue.get('result')!r} "
                            "is not a recognised outcome")
            elif not residue.get("date"):
                errs.append(f"{x['id']}: buySearch has no date, so it would never expire")

    # A takedown that has been recorded but not honoured is worse than one that
    # was never recorded, because the list makes it look handled.
    rules = payload.get("suppressed") or []
    if rules:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        try:
            from refresh import is_suppressed  # noqa: PLC0415
        except Exception as e:  # noqa: BLE001
            errs.append(f"could not load the suppression check: {e}")
        else:
            for x in watches:
                if x.get("image") and is_suppressed(x["image"], rules):
                    errs.append(f"{x['id']}: publishes a photograph that is suppressed")

    return errs


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data.json")
    payload = json.loads(path.read_text())
    errs = validate(payload)
    if errs:
        print(f"{path} failed validation:")
        for e in errs[:40]:
            print("  -", e)
        if len(errs) > 40:
            print(f"  … and {len(errs) - 40} more")
        return 1
    m = payload["meta"]
    print(f"{path} valid — {len(payload['watches'])} entries, {m['brands']} brands, "
          f"revision {m['revision']}, {m['imagesResolved']} photographs"
          + (f", {len(payload['suppressed'])} suppression rule(s)"
             if payload.get("suppressed") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
