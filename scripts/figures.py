#!/usr/bin/env python3
"""Publication figures, computed from data.json the way the PAGE computes them.

This exists because figures get quoted publicly, under Lowell's name, to people
who will check them. A number read off the raw file is not the number a reader
sees: the register applies a scope filter and a tier remap at display time, so
"252 entries" and "what the site shows" are different claims.

Every rule below is PORTED from build.py rather than re-invented — the scope
filter, the Retailer-enquiry remap, the edition-size reader and the date parser.
If build.py's rules change, these must change with them; test/figures_test.py
pins the ported ones against the same fixtures the template suite uses.

    python3 scripts/figures.py            # local data.json
    python3 scripts/figures.py --live     # what is actually being served
"""
import argparse
import json
import re
import statistics
import sys
import urllib.request
from collections import Counter

LIVE_URL = "https://www.watchdropindex.com/data.json"

# --- ported from build.py: the display layer -------------------------------
TIERS = ["Buy online now", "Buy at retailer", "Drop upcoming", "Waitlist or ballot",
         "AD or boutique", "In person only", "Gone"]
NOT_LE = [re.compile(r"not formally limited", re.I),
          re.compile(r"^capped", re.I),
          re.compile(r"annually", re.I)]

# --- ported from build.py: shortEd, the Edition column ---------------------
_ED_NA = re.compile(r"unconfirmed|not stated|not disclosed|not numbered|special edition|size not stated", re.I)


def edition_size(s):
    """The Edition column: an integer, or None where the size is undisclosed."""
    t = str(s or "").strip()
    if _ED_NA.search(t):
        return None
    if re.match(r"^unique piece", t, re.I):
        return 1
    tot = re.search(r"([\d,]+)\s*total", t, re.I)
    if tot:
        return int(tot.group(1).replace(",", ""))
    nums = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", t)]
    if not nums:
        return None
    if re.search(r"each", t, re.I):
        return None
    if re.search(r"[–—]|-\s*\d", re.sub(r"[\d,]+", "", t, count=1)):
        return nums[0]
    if len(nums) > 1 and "/" in t:
        return sum(nums)
    return nums[0]


# --- ported from build.py: datePick, the Released column -------------------
MONTH = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
         "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
_DATE_RE = re.compile(r"(?:(\d{1,2})\s+)?(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?(?:\s+(\d{4}))?", re.I)


def date_pick(ds):
    """(year, month, day) preferring the month anchored to 2026, or None."""
    ds = (ds or "").strip()
    if not ds:
        return None
    ms = [(int(d) if d else 0, mon, yr) for d, mon, yr in _DATE_RE.findall(ds)]
    if not ms:
        return None
    pick = next((m for m in ms if m[2] == "2026"), None) \
        or next((m for m in ms if not m[2]), None) or ms[0]
    day, mon, yr = pick
    year = int(yr) if yr else int((re.search(r"\b(20\d\d)\b", ds) or [None, "2026"])[1])
    return (year, MONTH[mon.lower()[:3]], day)


def check_date(v):
    """`verified` is {date, note}; older rows may carry a bare string."""
    return (v.get("date") if isinstance(v, dict) else str(v))[:10]


def in_scope(entry):
    edition = str(entry.get("edition", "")).strip()
    return not any(rx.search(edition) for rx in NOT_LE)


def rendered(items):
    """Exactly what the register shows: retracted out, scope filter, tier remap."""
    kept = [i for i in items if not i.get("retracted") and in_scope(i)]
    return [dict(i, tier="Buy at retailer", rank=3) if i["tier"] == "Retailer enquiry" else i
            for i in kept]


def money(n):
    return f"${n:,.0f}"


def report(payload, out=sys.stdout):
    meta = payload["meta"]
    items = payload["watches"]
    shown = rendered(items)
    p = lambda *a: print(*a, file=out)

    p(f"WATCH DROP INDEX — figures from data.json revision {meta.get('revision')}, "
      f"updated {meta.get('updated')}")
    p("=" * 74)

    # --- size of the register ---------------------------------------------
    brands_shown = sorted({w["brand"] for w in shown})
    p(f"\nRESEARCHED      {len(items)}")
    p(f"RENDERED        {len(shown)}   ({len(items) - len(shown)} held back by the scope filter"
      f" — production caps and annual editions, which are not limited editions)")
    p(f"BRANDS          {len(brands_shown)} across the rendered set"
      f"   (raw file: {len({w['brand'] for w in items})})")
    p(f"meta.count={meta.get('count')} meta.brands={meta.get('brands')}"
      f"   {'AGREES' if meta.get('count') == len(items) else 'DISAGREES with the file'}")

    # --- availability -------------------------------------------------------
    tiers = Counter(w["tier"] for w in shown)
    p("\nAVAILABILITY — all seven tiers, rendered set")
    for t in TIERS:
        p(f"  {t:22} {tiers.get(t, 0):>4}")
    unknown = {t: n for t, n in tiers.items() if t not in TIERS}
    if unknown:
        p(f"  !! tiers not in the display list: {unknown}")
    p(f"  {'TOTAL':22} {sum(tiers.values()):>4}")

    # --- verification -------------------------------------------------------
    ver = [w for w in shown if w.get("verified")]
    buychecked = [w for w in shown if w.get("buyCheck")]
    kinds = Counter(w.get("buyKind") or "unclassified" for w in shown)
    p("\nVERIFICATION")
    p(f"  stock-checked (a purchase page read on a date)   {len(ver)} of {len(shown)}")
    if ver:
        dates = sorted(check_date(w["verified"]) for w in ver)
        p(f"    checks run between {dates[0]} and {dates[-1]}")
    p(f"  buy link classified by evidence                  {len(buychecked)} of {len(shown)}")
    for k in ("product", "listing", "brand", "unclassified"):
        p(f"    {k:14} {kinds.get(k, 0):>4}")
    conf = Counter(w.get("conf") or "—" for w in shown)
    p(f"  confidence      " + "  ".join(f"{k} {v}" for k, v in conf.most_common()))

    # --- photographs --------------------------------------------------------
    withimg = [w for w in shown if w.get("image")]
    sized = [w for w in withimg if w.get("imageSize")]
    p("\nPHOTOGRAPHS")
    p(f"  resolved        {len(withimg)} of {len(shown)}   ({100 * len(withimg) / len(shown):.0f}%)")
    p(f"  with measured pixel dimensions   {len(sized)}")
    if sized:
        widths = sorted(w["imageSize"][0] for w in sized)
        p(f"  width: min {widths[0]} · median {int(statistics.median(widths))} · max {widths[-1]}"
          f" · {sum(1 for x in widths if x >= 900)} at 900px or wider")

    # --- price --------------------------------------------------------------
    priced = [w for w in shown if w.get("priceNum") is not None]
    nums = sorted(w["priceNum"] for w in priced)
    p("\nPRICE (USD, entries carrying a real figure)")
    p(f"  with a price    {len(priced)} of {len(shown)}   ({len(shown) - len(priced)} without)")
    p(f"  min             {money(nums[0])}   {next(w['brand'] + ' ' + w['model'] for w in priced if w['priceNum'] == nums[0])}")
    p(f"  median          {money(statistics.median(nums))}")
    p(f"  max             {money(nums[-1])}   {next(w['brand'] + ' ' + w['model'] for w in priced if w['priceNum'] == nums[-1])}")
    bands = [("<$1k", 0, 1000), ("$1k–5k", 1000, 5000), ("$5k–15k", 5000, 15000),
             ("$15k–50k", 15000, 50000), ("$50k–250k", 50000, 250000), ("$250k+", 250000, 10**12)]
    for label, lo, hi in bands:
        p(f"    {label:10} {sum(1 for n in nums if lo <= n < hi):>4}")

    # --- edition sizes ------------------------------------------------------
    sizes = [(edition_size(w["edition"]), w) for w in shown]
    disclosed = [(n, w) for n, w in sizes if n is not None]
    undisclosed = [w for n, w in sizes if n is None]
    ed = sorted(n for n, _ in disclosed)
    p("\nEDITION SIZE")
    p(f"  undisclosed     {len(undisclosed)} of {len(shown)}   (the Edition cell reads N/A)")
    p(f"  disclosed       {len(disclosed)}")
    p(f"  smallest        {ed[0]}   {min(disclosed, key=lambda x: x[0])[1]['brand']} "
      f"{min(disclosed, key=lambda x: x[0])[1]['model']}")
    p(f"  median          {int(statistics.median(ed))}")
    p(f"  largest         {ed[-1]:,}   {max(disclosed, key=lambda x: x[0])[1]['brand']} "
      f"{max(disclosed, key=lambda x: x[0])[1]['model']}")
    p(f"  unique pieces (edition of 1)     {sum(1 for n in ed if n == 1)}")
    p(f"  100 or fewer                     {sum(1 for n in ed if n <= 100)}")

    # --- dates --------------------------------------------------------------
    dated = [(date_pick(w["date"]), w) for w in shown]
    have = [(d, w) for d, w in dated if d]
    have.sort(key=lambda x: x[0])
    p("\nRELEASE DATES")
    p(f"  parsed          {len(have)} of {len(shown)}   ({len(shown) - len(have)} with no month, e.g. Q-only or TBC)")
    p(f"  oldest          {have[0][1]['date']}   {have[0][1]['brand']} {have[0][1]['model']}")
    p(f"  newest          {have[-1][1]['date']}   {have[-1][1]['brand']} {have[-1][1]['model']}")
    bymonth = Counter(d[1] for d, _ in have if d[0] == 2026)
    p("  by month, 2026  " + " ".join(f"{m:02d}:{bymonth.get(m, 0)}" for m in range(1, 13)))

    # --- the things worth saying out loud -----------------------------------
    p("\nNOTABLE")
    bybrand = Counter(w["brand"] for w in shown)
    p("  most-represented brands   " + ", ".join(f"{b} {n}" for b, n in bybrand.most_common(6)))
    p(f"  brands with a single entry  {sum(1 for _, n in bybrand.items() if n == 1)}")
    cats = Counter(w["cat"] for w in shown)
    p("  categories                " + " · ".join(f"{c} {n}" for c, n in cats.most_common()))
    srcs = Counter(w["source"] for w in shown)
    p(f"  distinct source URLs      {len(srcs)}  "
      f"(the most-cited covers {srcs.most_common(1)[0][1]} entries)")
    # An entry that arrived already sold out carries soldOutOn == addedOn: that is
    # the seed date, not an observation. Only a LATER date means we watched it go.
    flipped = [w for w in shown if w.get("soldOutOn") and w.get("addedOn")
               and str(w["soldOutOn"])[:10] > str(w["addedOn"])[:10]]
    seeded = sum(1 for w in shown if w["tier"] == "Gone") - len(flipped)
    p(f"  arrived already sold out             {seeded}")
    p(f"  watched sell out since indexing      {len(flipped)}"
      + (("   " + ", ".join(f"{w['brand']} {w['model']} ({w['soldOutOn']})" for w in flipped)) if flipped else ""))
    p(f"  buyable online AND stock-checked     "
      f"{sum(1 for w in shown if w['tier'] == 'Buy online now' and w.get('verified'))}")

    # --- do not quote -------------------------------------------------------
    p("\nWOULD NOT QUOTE PUBLICLY")
    unread = kinds.get("unclassified", 0)
    p(f"  · anything implying full coverage of 2026. Source roundups run Jan–Jun;")
    p(f"    Grand Seiko/Seiko H2 and F.P. Journe are known gaps.")
    p(f"  · availability as a live figure. {unread} of {len(shown)} buy pages cannot be read")
    p(f"    at all, so verification is structurally blind on that share of the register.")
    p(f"  · '{len(ver)} stock checks' without saying it is {100 * len(ver) / len(shown):.0f}% — quoted bare it")
    p(f"    reads as the whole register having been checked.")
    p(f"  · brand count: {len(brands_shown)} rendered vs {len({w['brand'] for w in items})} researched. Say which one.")

    return {"researched": len(items), "rendered": len(shown), "brands": len(brands_shown),
            "tiers": dict(tiers), "verified": len(ver), "images": len(withimg),
            "priced": len(priced), "undisclosed": len(undisclosed)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="fetch the served file instead of the local one")
    ap.add_argument("--path", default="data.json")
    a = ap.parse_args()
    if a.live:
        with urllib.request.urlopen(LIVE_URL, timeout=30) as r:
            payload = json.loads(r.read().decode("utf-8"))
    else:
        payload = json.load(open(a.path, encoding="utf-8"))
    report(payload)


if __name__ == "__main__":
    main()
