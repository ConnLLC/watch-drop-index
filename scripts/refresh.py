#!/usr/bin/env python3
"""
Weekly refresh for the Watch Drop Index.

The masthead claims the site is refreshed weekly. That claim is the product, and
this is the machinery behind it. Five stages:

  1  LOAD       read and validate data.json; abort loudly without touching anything
  2  AVAILABLE  re-check every entry that claims to be obtainable (rank <= 2)
  3  PHOTOS     backfill og:image for entries that still have none
  4  NEW         search the week's watch press for limited editions
  5  COMMIT      update meta, write data.json, emit a report

The governing rule throughout: an unreadable page changes nothing. A 403, a
timeout, a bot wall and a JavaScript-only page are all silence, not evidence.
Only positive, quotable evidence moves an entry, and only ever in the direction
that evidence supports. False confidence is worse than missing coverage — the
whole site rests on the distinction between "we checked" and "we inferred".

Usage:
    python3 scripts/refresh.py                      # full run
    python3 scripts/refresh.py --dry-run            # change nothing on disk
    python3 scripts/refresh.py --stages 2,3         # availability + photos only
    python3 scripts/refresh.py --no-api             # fetch layer only, no model calls

Exit codes:
    0   completed; data.json updated (or --dry-run)
    10  no changes to commit (clean run, nothing moved)
    20  blast radius exceeded — refused to commit, open an issue instead
    21  silence failure — the fetch layer looks broken
    1   hard error
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data.json"
REPORT = ROOT / "refresh-report.md"

MODEL = os.environ.get("WDI_MODEL", "claude-opus-5")
EFFORT = os.environ.get("WDI_EFFORT", "low")

# Guardrails.
GONE_BLAST_RADIUS = 0.15   # refuse to commit if this share of entries flips to Gone
PHOTO_BATCH = 36           # coverage converges in a couple of months at this rate
PHOTO_RETRY_DAYS = 28      # how long before re-probing a source that errored
MAX_NEW_ENTRIES = 25       # a week that yields more than this is a bug, not a boom

# SCOPE (Lowell, 2026-08-04): a production cap is not a limited edition. Entries
# matching these do not render — the same three patterns are in build.py and in
# the page's script, and the three copies must not drift.
NOT_LE = [re.compile(r"not formally limited", re.I),
          re.compile(r"^capped", re.I),
          re.compile(r"annually", re.I)]
MIN_PAGE_TEXT = 200        # below this the page is JS-only or a bot wall: unreadable
FETCH_TIMEOUT = 25
MAX_PAGE_CHARS = 9000      # what we hand the model, from the end-of-header onward

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

TIERS = ["Buy online now", "Drop upcoming", "Retailer enquiry", "Waitlist or ballot",
         "AD or boutique", "In person only", "Gone"]

# Matched against buyLabel to decide whether a "buy" link is a real purchase page
# or an information page. Carried over verbatim from the v1 template so the
# refresh classifies entries exactly the way the site already does.
PURCHASE_LABEL = re.compile(
    r"in stock|add to cart|buy now|product page|orders open|pre-?order|now shipping|"
    r"direct sale|webshop|check stock|available to order|online drop|verified",
    re.I,
)

# Photographs are editorial: the outlet that covered the release gets the credit
# under the image. Covers every domain currently cited in the register plus the
# press list. An unmapped domain falls back to the bare hostname — ugly, but
# factual, which is the right way round for this site.
OUTLETS = {
    # watch press
    "monochrome-watches.com": "Monochrome",
    "watchesbysjx.com": "SJX",
    "timeandtidewatches.com": "Time+Tide",
    "shop.timeandtidewatches.com": "Time+Tide",
    "ablogtowatch.com": "aBlogtoWatch",
    "wornandwound.com": "Worn & Wound",
    "windupwatchshop.com": "Worn & Wound",
    "fratellowatches.com": "Fratello",
    "hodinkee.com": "Hodinkee",
    "revolutionwatch.com": "Revolution",
    "plus9time.com": "Plus9Time",
    "g-central.com": "G-Central",
    "watchilove.com": "WatchILove",
    "thehourmarkers.com": "The Hour Markers",
    "professionalwatches.com": "Professional Watches",
    "watchpro.com": "WatchPro",
    "quillandpad.com": "Quill & Pad",
    "deployant.com": "Deployant",
    "watchtime.com": "WatchTime",
    "oracleoftime.com": "Oracle of Time",
    "gearpatrol.com": "Gear Patrol",
    "hypebeast.com": "Hypebeast",
    "hiconsumption.com": "HiConsumption",
    "luxe.outlookindia.com": "Outlook Luxe",
    "twobrokewatchsnobs.com": "Two Broke Watch Snobs",
    "masterhorologer.com": "Master Horologer",
    "somethingaboutrocks.com": "Something About Rocks",
    "notebookcheck.net": "Notebookcheck",
    "nxtmag.tech": "NXT Mag",
    "sfwatchlover.substack.com": "SF Watch Lover",
    # retailers
    "luxurybazaar.com": "Luxury Bazaar",
    "watchbuys.com": "WatchBuys",
    "watchesofswitzerland.com": "Watches of Switzerland",
    "longislandwatch.com": "Long Island Watch",
    # brands
    "christopherward.com": "Christopher Ward",
    "grand-seiko.com": "Grand Seiko",
    "seikowatches.com": "Seiko",
    "citizenwatch-global.com": "Citizen",
    "orient-watch.com": "Orient",
    "omegawatches.com": "Omega",
    "breitling.com": "Breitling",
    "junghans.de": "Junghans",
    "yema.com": "Yema",
    "gronefeld.com": "Grönefeld",
    "unimaticwatches.com": "Unimatic",
    "kuronotokyo.com": "Kurono Tokyo",
    "mrstateless.com": "Mr Stateless",
}

# Stage 4 searches only these. Restricting the domain list is what keeps the
# scope rules enforceable — an aggregator or a marketplace listing is exactly
# the kind of source that turns a limited-edition register into a restock feed.
PRESS_DOMAINS = [
    "monochrome-watches.com", "watchesbysjx.com", "wornandwound.com",
    "fratellowatches.com", "timeandtidewatches.com", "ablogtowatch.com",
    "revolutionwatch.com", "plus9time.com", "g-central.com",
    "quillandpad.com", "deployant.com", "watchpro.com", "oracleoftime.com",
]
# hodinkee.com is deliberately absent: it blocks the model's crawler, and naming it
# rejects the ENTIRE search with a 400 rather than just skipping that one site.


# ---------------------------------------------------------------- utilities


def today() -> str:
    return dt.date.today().isoformat()


def log(msg: str) -> None:
    print(msg, flush=True)


def make_id(brand: str, model: str) -> str:
    """The id scheme the register already uses. Immutable once assigned —
    rewriting one orphans that watch's verification history."""
    return hashlib.md5(f"{brand}|{model}".lower().encode()).hexdigest()[:10]


def domain_of(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url or "")
    return re.sub(r"^www\.", "", m.group(1)).lower() if m else ""


def outlet_for(url: str) -> str:
    d = domain_of(url)
    return OUTLETS.get(d, d)


def rank_for(status: str, buy_label: str, tags: list[str]) -> int:
    """Tier derivation. Describes how the brand distributes the watch — never
    a guess about whether stock remains."""
    if status == "Sold out":
        return 6
    if status == "Event only":
        return 5
    if status == "Allocation":
        return 4
    if status == "Waitlist":
        return 3
    if status == "Upcoming":
        return 1
    if status in ("Available", "Pre-order"):
        purchasable = bool(PURCHASE_LABEL.search(buy_label or "")) or "Buy online" in (tags or [])
        return 0 if purchasable else 2
    raise ValueError(f"unknown status: {status!r}")


def apply_tier(entry: dict) -> None:
    entry["rank"] = rank_for(entry["status"], entry.get("buyLabel", ""), entry.get("tags", []))
    entry["tier"] = TIERS[entry["rank"]]


def in_scope(entry: dict) -> bool:
    edition = str(entry.get("edition", "")).strip()
    return not any(rx.search(edition) for rx in NOT_LE)


def days_since(iso: str | None) -> float:
    if not iso:
        return 1e9
    try:
        return (dt.date.today() - dt.date.fromisoformat(iso[:10])).days
    except ValueError:
        return 1e9


# ------------------------------------------------------------ html handling


_SCRIPTISH = re.compile(r"<(script|style|noscript|svg|head)\b.*?</\1>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")
_BLANK = re.compile(r"\n{3,}")


def page_text(raw: str) -> str:
    """Crude but adequate: retailers put 'Sold out' and 'Add to cart' in plain
    text. We are not rendering the page, only reading what it says."""
    s = _SCRIPTISH.sub(" ", raw)
    s = re.sub(r"<(br|/p|/div|/li|/h[1-6]|/tr)\s*/?>", "\n", s, flags=re.I)
    s = _TAG.sub(" ", s)
    s = html.unescape(s)
    s = _WS.sub(" ", s)
    s = "\n".join(line.strip() for line in s.split("\n"))
    return _BLANK.sub("\n\n", s).strip()


def jsonld_availability(raw: str) -> list[str]:
    """schema.org Offer availability is the single most reliable machine signal
    on a Shopify/WooCommerce product page. Surfaced to the model as evidence,
    never acted on alone."""
    out: list[str] = []
    for m in re.finditer(r'"availability"\s*:\s*"([^"]+)"', raw):
        out.append(m.group(1).rsplit("/", 1)[-1])
    return sorted(set(out))


_META = re.compile(
    r"""<meta[^>]+?(?:property|name)\s*=\s*["'](og:image(?::secure_url)?|twitter:image(?::src)?)["'][^>]*>""",
    re.I,
)
_CONTENT = re.compile(r"""content\s*=\s*["']([^"']+)["']""", re.I)


def og_image(raw: str, base_url: str) -> str | None:
    for tag in _META.finditer(raw):
        c = _CONTENT.search(tag.group(0))
        if not c:
            continue
        url = html.unescape(c.group(1)).strip()
        if not url:
            continue
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            m = re.match(r"(https?://[^/]+)", base_url)
            if not m:
                continue
            url = m.group(1) + url
        # The site is served over HTTPS, so an http:// image is mixed content and
        # the browser blocks it outright — the caption degrades and the reader
        # never sees why. Several sources (Squarespace-hosted ones especially)
        # publish og:image over http; upgrade rather than lose the photograph.
        if url.startswith("http://"):
            url = "https://" + url[len("http://"):]
        if url.startswith("https://"):
            return url
    return None


def fetch(url: str) -> tuple[str | None, str]:
    """Returns (raw_html, note). raw_html is None whenever the page could not be
    read for any reason — the caller must treat that as 'no information'."""
    if not url or not url.startswith("http"):
        return None, "no url"
    try:
        r = requests.get(
            url,
            timeout=FETCH_TIMEOUT,
            allow_redirects=True,
            headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
    except requests.RequestException as e:
        return None, f"fetch failed: {type(e).__name__}"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    if r.status_code == 200 and not r.content:
        return None, "empty response"
    ctype = r.headers.get("content-type", "")
    if "html" not in ctype and "xml" not in ctype:
        return None, f"not html ({ctype.split(';')[0] or 'unknown'})"
    if not r.encoding or r.encoding.lower() == "iso-8859-1":
        r.encoding = r.apparent_encoding or "utf-8"
    return r.text, "ok"


# ----------------------------------------------------------------- the model


class Model:
    """Thin wrapper so --no-api can stub every call out and the fetch layer
    stays testable without a key."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.calls = 0
        self._client = None
        if enabled:
            import anthropic  # imported lazily so --no-api needs no dependency
            self._client = anthropic.Anthropic()

    def structured(self, prompt: str, schema: dict, max_tokens: int = 8000) -> dict | None:
        if not self.enabled:
            return None
        self.calls += 1
        for attempt in range(3):
            try:
                r = self._client.messages.create(
                    model=MODEL,
                    max_tokens=max_tokens,
                    output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": schema}},
                    messages=[{"role": "user", "content": prompt}],
                )
                if r.stop_reason == "refusal":
                    return None
                text = next((b.text for b in r.content if b.type == "text"), None)
                return json.loads(text) if text else None
            except Exception as e:  # noqa: BLE001 - a failed judgement must never move an entry
                if attempt == 2:
                    log(f"    ! model call failed: {type(e).__name__}: {e}")
                    return None
                time.sleep(2 ** attempt * 2)
        return None

    def search(self, prompt: str, domains: list[str], max_tokens: int = 16000) -> str | None:
        if not self.enabled:
            return None
        self.calls += 1
        try:
            with self._client.messages.stream(
                model=MODEL,
                max_tokens=max_tokens,
                output_config={"effort": "high"},
                tools=[{
                    "type": "web_search_20260209",
                    "name": "web_search",
                    "max_uses": 18,
                    "allowed_domains": domains,
                }],
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                msg = stream.get_final_message()
            if msg.stop_reason == "refusal":
                return None
            return "\n".join(b.text for b in msg.content if b.type == "text").strip() or None
        except Exception as e:  # noqa: BLE001
            log(f"    ! search failed: {type(e).__name__}: {e}")
            return None


# ------------------------------------------------------- stage 2: available


VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "obtainable": {
            "type": "string",
            "enum": ["yes", "no", "unclear"],
            "description": "Can a member of the public still acquire this watch through this page?",
        },
        "signal": {
            "type": "string",
            "enum": ["add_to_cart", "preorder_open", "sold_out", "temporarily_unavailable",
                     "waitlist_only", "contact_retailer", "not_a_product_page", "unreadable"],
        },
        "quote": {
            "type": "string",
            "description": "A short verbatim phrase from the page supporting the verdict. Empty if none.",
        },
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["obtainable", "signal", "quote", "confidence"],
    "additionalProperties": False,
}

VERDICT_PROMPT = """You are checking whether a specific limited-edition watch can still be bought.

WATCH: {brand} {model}
CURRENTLY RECORDED AS: {tier} (status: {status})
THE LINK WE HOLD IS LABELLED: "{label}"
PAGE URL: {url}
{ld}
Below is the readable text of that page.

Judge only what this page shows. The distinctions that matter:

- An active add-to-cart / buy button, or a live price with stock => obtainable: yes,
  signal add_to_cart (or preorder_open if it is an order window rather than stock)

- signal sold_out — the run is finished and will not return. Use this when the page
  says the edition is sold out, fully allocated, no longer available, or that all
  pieces are accounted for. A plain "Out of stock" on a limited edition's only listed
  purchase channel also counts: a capped run does not get restocked.

- signal temporarily_unavailable — the page says you cannot buy it RIGHT NOW but
  frames that as temporary: "temporarily sold out", "back in stock soon",
  "currently unavailable", "out of stock at this retailer" alongside other channels.
  The difference from sold_out is what the page says about permanence, not how you
  feel about the odds.

- signal waitlist_only — the brand's stated way in is a ballot, lottery or
  application. A "notify me when available" mailing list is NOT this; that is
  temporarily_unavailable.

- "Contact us", "enquire", "find a boutique" => obtainable: unclear, signal
  contact_retailer. That is a distribution model, NOT evidence the watch is gone.

- A category page, a 404, a homepage, a cookie wall, or a page that does not
  identify this watch => obtainable: unclear, signal not_a_product_page
- Text that looks like a bot challenge or is too sparse to read => unclear, unreadable

Be conservative. "unclear" is the correct and expected answer whenever the page
does not plainly settle it. Do not infer scarcity from tone, marketing copy, or
the absence of a price. Only answer "no" when the page positively states the
watch cannot be bought, and give the exact wording in `quote`.

--- PAGE TEXT ---
{text}
--- END ---"""


def check_availability(entry: dict, model: Model) -> dict:
    """Returns a result record. Never mutates the entry."""
    res = {"id": entry["id"], "changed": False, "note": None, "verdict": None, "read": False}
    raw, note = fetch(entry.get("buy", ""))
    if raw is None:
        res["note"] = note
        return res
    text = page_text(raw)
    if len(text) < MIN_PAGE_TEXT:
        res["note"] = "page unreadable (no extractable text)"
        return res
    res["read"] = True

    avail = jsonld_availability(raw)
    ld = f"\nSTRUCTURED DATA ON THE PAGE DECLARES: {', '.join(avail)}\n" if avail else ""

    verdict = model.structured(
        VERDICT_PROMPT.format(
            brand=entry["brand"], model=entry["model"], tier=entry["tier"],
            status=entry["status"], label=entry.get("buyLabel", ""),
            url=entry.get("buy", ""), ld=ld, text=text[:MAX_PAGE_CHARS],
        ),
        VERDICT_SCHEMA,
    )
    if not verdict:
        res["note"] = "no verdict"
        return res
    res["verdict"] = verdict
    return res


def stage_availability(watches: list[dict], model: Model, limit: int | None) -> dict:
    targets = [w for w in watches if w["rank"] <= 2]
    if limit:
        targets = targets[:limit]
    log(f"\n[2] AVAILABILITY — {len(targets)} entries with rank <= 2")

    results: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(check_availability, w, model): w for w in targets}
        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            w = futures[fut]
            try:
                results.append(fut.result())
            except Exception as e:  # noqa: BLE001
                log(f"    ! {w['brand']} {w['model']}: {type(e).__name__}")
                results.append({"id": w["id"], "changed": False, "read": False,
                                "note": "worker error", "verdict": None})
            if i % 15 == 0:
                log(f"    ...{i}/{len(targets)}")

    by_id = {w["id"]: w for w in watches}
    summary = {"checked": len(targets), "read": 0, "gone": [], "promoted": [],
               "confirmed": [], "noted": [], "skipped": []}

    for r in results:
        w = by_id[r["id"]]
        if r["read"]:
            summary["read"] += 1
        v = r["verdict"]
        if not v:
            summary["skipped"].append((w, r.get("note") or "unreadable"))
            continue

        quote = (v.get("quote") or "").strip()[:200]
        signal, conf = v["signal"], v["confidence"]

        # --- Gone. The only downgrade this job is permitted to make, and only on
        # positive, high-confidence, quotable evidence that the run is finished.
        #
        # `sold_out` is the ONLY signal that moves a tier downward. A retailer
        # being temporarily out of stock is a fact about stock, not about how the
        # brand distributes the watch, and the tiers describe distribution. A
        # "notify me" list is likewise not a ballot. Both of those get a verified
        # note quoting the page and keep their tier — the reader sees "Buy online
        # now" next to "Stock checked today, page reads 'Temporarily Sold Out'"
        # and can judge for themselves, which is the honest presentation and the
        # one that keeps demand and distribution from blurring together.
        if v["obtainable"] == "no" and conf == "high" and signal == "sold_out" and quote:
            w["status"] = "Sold out"
            w["soldOutOn"] = today()
            apply_tier(w)
            w["verified"] = {"date": today(), "note": f'Purchase page reads: "{quote}"'}
            summary["gone"].append((w, quote))
            continue

        # --- Can't be bought right now, but the page says nothing permanent.
        # Record what it said; change nothing else.
        if signal in ("temporarily_unavailable", "waitlist_only") and quote:
            w["verified"] = {"date": today(), "note": f'Purchase page reads: "{quote}"'}
            summary["noted"].append((w, quote))
            continue

        # --- Upward moves. A pre-order opening or an AD putting stock online.
        if v["obtainable"] == "yes" and signal in ("add_to_cart", "preorder_open") and conf == "high":
            was = w["tier"]
            if w["rank"] in (1, 2):
                w["status"] = "Pre-order" if signal == "preorder_open" else "Available"
                tags = w.setdefault("tags", [])
                if "Buy online" not in tags:
                    tags.append("Buy online")
                apply_tier(w)
            w["verified"] = {"date": today(), "note": f'Purchase page reads: "{quote}"' if quote
                             else "Purchase page showed an active buy option."}
            if w["tier"] != was:
                summary["promoted"].append((w, was, quote))
            else:
                summary["confirmed"].append((w, quote))
            continue

        # --- Confirmed as-is. Refreshing `verified` is what makes the weekly
        # claim visible per entry rather than only in the masthead.
        if v["obtainable"] == "yes" and conf in ("high", "medium"):
            w["verified"] = {"date": today(), "note": f'Purchase page reads: "{quote}"' if quote
                             else "Purchase page still showed this watch for sale."}
            summary["confirmed"].append((w, quote))
            continue

        # Everything else — unclear, low confidence, contact_retailer,
        # not_a_product_page — leaves the entry completely untouched.
        summary["skipped"].append((w, f"{v['obtainable']}/{signal}/{conf}"))

    log(f"    read {summary['read']}/{summary['checked']} pages · "
        f"{len(summary['gone'])} gone · {len(summary['promoted'])} moved up · "
        f"{len(summary['confirmed'])} confirmed · {len(summary['noted'])} noted "
        f"· {len(summary['skipped'])} left alone")
    return summary


# ---------------------------------------------------------- stage 3: photos


def photo_candidates(watches: list[dict]) -> list[dict]:
    out = []
    for w in watches:
        if w.get("image"):
            continue
        probe = w.get("imageProbe")
        if probe:
            # "none"  — the source has no og:image at all
            # "dead"  — the source URL is 404/410; it is not coming back
            # Both are permanent. Anything else (403 bot wall, 5xx, timeout) is
            # transient and gets another look after PHOTO_RETRY_DAYS.
            if probe.get("result") in ("none", "dead"):
                continue
            if days_since(probe.get("date")) < PHOTO_RETRY_DAYS:
                continue
        out.append(w)
    return out


def probe_result_for(note: str) -> str:
    """Classify a failed photograph probe as permanent or worth retrying."""
    m = re.match(r"HTTP (\d+)", note or "")
    if m and int(m.group(1)) in (404, 410):
        return "dead"
    return "blocked"


def stage_photos(watches: list[dict], batch: int) -> dict:
    targets = photo_candidates(watches)[:batch]
    log(f"\n[3] PHOTOGRAPHS — probing {len(targets)} sources "
        f"({sum(1 for w in watches if w.get('image'))}/{len(watches)} resolved)")
    summary = {"resolved": [], "none": [], "blocked": [], "dead": []}

    def probe(w: dict) -> tuple[dict, str | None, str]:
        raw, note = fetch(w.get("source", ""))
        if raw is None:
            return w, None, note
        img = og_image(raw, w["source"])
        return w, img, "ok" if img else "no og:image"

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for w, img, note in pool.map(probe, targets):
            if img:
                w["image"] = img
                w["imageCredit"] = outlet_for(w["source"])
                w.pop("imageProbe", None)
                summary["resolved"].append(w)
            elif note == "no og:image":
                w["imageProbe"] = {"date": today(), "result": "none"}
                summary["none"].append(w)
            else:
                result = probe_result_for(note)
                w["imageProbe"] = {"date": today(), "result": result, "note": note}
                summary["dead" if result == "dead" else "blocked"].append(w)

    log(f"    resolved {len(summary['resolved'])} · no og:image {len(summary['none'])} · "
        f"dead source {len(summary['dead'])} · unreachable {len(summary['blocked'])}")
    return summary


# ------------------------------------------------------ stage 4: new releases


SEARCH_PROMPT = """Search the watch press for LIMITED-EDITION watches announced or released since {since}.

Search the sites available to you for new limited-edition announcements. Cover as
many brands as you can — Swiss, independent, Japanese, and microbrands.

SCOPE — this is a register of limited editions ONLY. Include:
  - numbered runs ("one of 250"), capped annual production, ballot pieces,
    single-retailer or single-boutique exclusives
Exclude, without exception:
  - regular production models, however new
  - RESTOCKS or re-releases of anything previously available
  - price changes, colour additions to an ongoing line, or reviews of old watches
  - unnumbered "special editions" UNLESS you label them clearly as such

For each qualifying watch, report:
  brand, model name, reference, one-line description, case/movement specs,
  edition size (or "Unconfirmed" if the brand did not state one), price as
  published including currency, announcement date, where to buy it, and the
  source article URL.

Do not guess any field. If a source does not state something, say "Unconfirmed".
It is far better to report six watches accurately than twenty with invented
details. Report what you found in plain prose, one watch per paragraph, with the
source URL on each."""

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "releases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "brand": {"type": "string"},
                    "model": {"type": "string"},
                    "ref": {"type": "string"},
                    "cat": {"type": "string", "enum": ["Swiss majors", "Independents",
                                                       "Japanese", "Accessible & micro"]},
                    "desc": {"type": "string"},
                    "specs": {"type": "string"},
                    "edition": {"type": "string"},
                    "price": {"type": "string"},
                    "priceNum": {"type": ["number", "null"]},
                    "date": {"type": "string"},
                    "status": {"type": "string", "enum": ["Available", "Pre-order", "Upcoming",
                                                          "Waitlist", "Allocation", "Event only",
                                                          "Sold out"]},
                    "buy": {"type": "string"},
                    "buyLabel": {"type": "string"},
                    "source": {"type": "string"},
                    "conf": {"type": "string", "enum": ["high", "medium", "low"]},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "is_limited_edition": {"type": "boolean"},
                },
                "required": ["brand", "model", "ref", "cat", "desc", "specs", "edition",
                             "price", "priceNum", "date", "status", "buy", "buyLabel",
                             "source", "conf", "tags", "is_limited_edition"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["releases"],
    "additionalProperties": False,
}

EXTRACT_PROMPT = """Convert the research notes below into structured records.

Rules, in order of importance:
1. NEVER invent a value. If the notes do not state a price, edition size or
   reference, write "Unconfirmed" (or null for priceNum). A wrong number is far
   worse than an absent one.
2. `is_limited_edition` is false for regular production, restocks, re-releases,
   and anything whose limited status the notes do not establish. Set it honestly;
   entries marked false are discarded.
3. `conf` is the credibility of the record: "high" only when a brand source or
   several outlets agree, "medium" for a single credible outlet, "low" for a
   single aggregator or an unresolved conflict between sources.
4. `priceNum` is a USD estimate used only for sorting. Convert if needed; null
   if no price was published.
5. `source` must be the article URL the notes cite. `buy` is where a reader goes
   to acquire it — the brand's product page if there is one, otherwise the
   brand's site. `buyLabel` should say what the visitor will actually find
   there, e.g. "Add to cart", "Pre-order", "Find a boutique".
6. `cat` classifies the maker, not the price.

Omit any watch the notes describe too vaguely to record properly.

--- RESEARCH NOTES ---
{notes}
--- END ---"""


""" ---------------------------------------------------- ledger display names

The ledger is a register, so it reads like one: the brand column names the
MANUFACTURER, and the model column carries a short editorial title. Design set
those by hand for the founding 252 and baked them into the page. Anything added
after that has to arrive with its own, in data.json — which is what this does.

Two rules, both from design (v1.2 and v1.3 §9), and both closed:

  displayBrand — only for a collab (× or /). The maker is named first by
  convention, and the page already assumes that, so this field is written ONLY
  when the maker is listed SECOND. If it cannot be told which party actually
  makes the watch, the field is left unset and the name goes to design. The page
  falls back safely either way.

  displayModel — only when the model runs past 38 characters. Keep the family and
  the edition identity (the quoted edition name especially); drop calibre
  numbers, spec words, mm sizes, reference numbers and parenthetical variant
  lists. Never invent a word that is not in the full name.

Guessing is the one thing that is not allowed: a wrong maker attribution is a
factual error about who built a watch, and an invented model word is worse than
a long one. Both failure modes leave the field unset and surface the name in the
report for design to rule on.
"""

DISPLAY_LIMIT = 38

NAMING_SCHEMA = {
    "type": "object",
    "properties": {
        "names": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "maker": {
                        "type": "string",
                        "description": "For a collab: the party that MANUFACTURES the watch, "
                                       "copied exactly as it appears in the brand string. "
                                       "Empty when the entry is not a collab or you cannot tell.",
                    },
                    "maker_certain": {"type": "boolean"},
                    "short_model": {
                        "type": "string",
                        "description": f"The model name at {DISPLAY_LIMIT} characters or fewer, "
                                       "using only words present in the full name. Empty if the "
                                       "rule cannot get there without losing the identity.",
                    },
                },
                "required": ["id", "maker", "maker_certain", "short_model"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["names"],
    "additionalProperties": False,
}

NAMING_PROMPT = """You are keeping a watch register's ledger column readable.

For each entry below, do two things.

1. MAKER. If the brand is a collaboration (it contains × or /), say which party
   actually MANUFACTURES the watch — the one whose factory builds it, not the
   retailer, magazine, artist or fashion house that commissioned it. Copy the
   name exactly as it appears inside the brand string. Set maker_certain false
   if you are not sure; a wrong attribution is a factual error about who built
   the watch. If the brand is not a collaboration, leave maker empty.

2. SHORT MODEL. If the model name is longer than {limit} characters, shorten it
   to {limit} or fewer:
     KEEP  the family name and the edition identity — a quoted edition name
           ("Tribute to Concorde") always survives, with its quotation marks.
     DROP  calibre numbers (B01, 9SA5), spec words (Chronograph, Automatic,
           Self-Winding, Date) unless the spec IS the identity, mm sizes,
           reference numbers, and parenthetical variant lists.
     NEVER introduce a word that does not appear in the full name.
   If you cannot get under {limit} without losing what identifies the watch,
   return an empty short_model. Leave it empty too when the name is already
   {limit} characters or fewer.

Entries:
{entries}
"""


def needs_display_names(entry: dict) -> bool:
    return bool(re.search(r"[×/]", entry["brand"])) or len(entry["model"]) > DISPLAY_LIMIT


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[A-Za-z0-9]+", s.lower())}


def assign_display_names(entries: list[dict], model: Model) -> list[str]:
    """Fills displayBrand/displayModel in place. Returns the names design has to
    rule on — anything the rules could not settle without guessing."""
    todo = [e for e in entries if needs_display_names(e)]
    if not todo:
        return []

    listing = "\n".join(
        f'- id {e["id"]}\n  brand: {e["brand"]}\n  model: {e["model"]}' for e in todo
    )
    parsed = model.structured(
        NAMING_PROMPT.format(limit=DISPLAY_LIMIT, entries=listing),
        NAMING_SCHEMA, max_tokens=4000,
    )
    by_id = {e["id"]: e for e in todo}
    answers = {a["id"]: a for a in (parsed or {}).get("names", [])}
    queries: list[str] = []

    for eid, e in by_id.items():
        a = answers.get(eid, {})

        if re.search(r"[×/]", e["brand"]):
            parties = [p.strip() for p in re.split(r"\s*[×/]\s*", e["brand"]) if p.strip()]
            maker = (a.get("maker") or "").strip()
            if not maker or not a.get("maker_certain") or maker not in parties:
                queries.append(f'collab brand "{e["brand"]}" — which party makes the watch?')
            elif maker != parties[0]:
                # First name = maker is what the page already assumes, so only the
                # second-named case needs a field written at all.
                e["displayBrand"] = maker

        if len(e["model"]) > DISPLAY_LIMIT:
            short = (a.get("short_model") or "").strip()
            invented = _words(short) - _words(e["model"])
            if not short or len(short) > DISPLAY_LIMIT or invented:
                why = ("no short title" if not short
                       else f"still {len(short)} characters" if len(short) > DISPLAY_LIMIT
                       else "introduces " + ", ".join(sorted(invented)))
                queries.append(f'model "{e["model"]}" ({len(e["model"])} chars) — {why}')
            else:
                e["displayModel"] = short

    return queries


def apply_corrections(watches: list[dict], path: Path) -> tuple[int, list[str]]:
    """Folds Lowell's admin export into data.json, verbatim. His edits are the
    top of the precedence order and this job never overwrites them afterwards —
    once a name is here by hand, the naming pass leaves it alone."""
    payload = json.loads(path.read_text())
    by_id = {w["id"]: w for w in watches}
    applied, unknown = 0, []
    for wid, fields in payload.items():
        target = by_id.get(wid)
        if not target:
            unknown.append(wid)
            continue
        for field in ("displayBrand", "displayModel", "desc"):
            if field in fields and str(fields[field]).strip():
                target[field] = fields[field]
        applied += 1
    return applied, unknown


def stage_new_releases(watches: list[dict], model: Model, since: str) -> dict:
    log(f"\n[4] NEW RELEASES — searching the press since {since}")
    summary = {"added": [], "rejected": [], "notes": None}

    notes = model.search(SEARCH_PROMPT.format(since=since), PRESS_DOMAINS)
    if not notes:
        log("    no research returned")
        return summary
    summary["notes"] = notes

    parsed = model.structured(EXTRACT_PROMPT.format(notes=notes[:60000]),
                              EXTRACT_SCHEMA, max_tokens=32000)
    if not parsed:
        log("    extraction returned nothing")
        return summary

    existing_ids = {w["id"] for w in watches}
    existing_key = {(w["brand"].strip().lower(), w["model"].strip().lower()) for w in watches}

    for c in parsed.get("releases", []):
        brand, mdl = c["brand"].strip(), c["model"].strip()
        why = None
        if not c.get("is_limited_edition"):
            why = "not a limited edition"
        elif not brand or not mdl:
            why = "missing brand or model"
        elif not str(c.get("source", "")).startswith("http"):
            why = "no source URL"
        elif not str(c.get("buy", "")).startswith("http"):
            why = "no buy URL"
        elif domain_of(c["source"]) not in PRESS_DOMAINS:
            why = f"source outside the press list ({domain_of(c['source'])})"
        elif make_id(brand, mdl) in existing_ids or (brand.lower(), mdl.lower()) in existing_key:
            why = "already in the register"
        elif len(summary["added"]) >= MAX_NEW_ENTRIES:
            why = "over the per-run cap"

        if why:
            summary["rejected"].append((f"{brand} {mdl}".strip() or "(unnamed)", why))
            continue

        entry = {
            "id": make_id(brand, mdl),
            "brand": brand, "model": mdl, "ref": c.get("ref") or "—",
            "cat": c["cat"], "desc": c["desc"], "specs": c["specs"],
            "edition": c["edition"], "price": c["price"],
            "priceNum": c.get("priceNum"), "date": c["date"],
            "status": c["status"], "buy": c["buy"], "buyLabel": c["buyLabel"],
            "source": c["source"], "image": None, "imageCredit": None,
            "conf": c["conf"], "verified": None, "soldOutOn": None,
            "addedOn": today(), "tags": c.get("tags") or [],
        }
        apply_tier(entry)
        existing_ids.add(entry["id"])
        existing_key.add((brand.lower(), mdl.lower()))
        watches.append(entry)
        summary["added"].append(entry)

    summary["design"] = assign_display_names(summary["added"], model)
    named = sum(1 for e in summary["added"] if e.get("displayBrand") or e.get("displayModel"))

    # An entry whose edition is a production cap is NOT a limited edition, so the
    # page will not render it. That is the rule working, not a bug — the data is
    # never "fixed" to force it on. It is reported because an addition nobody can
    # see would otherwise look like the job doing nothing.
    summary["out_of_scope"] = [e for e in summary["added"] if not in_scope(e)]

    log(f"    added {len(summary['added'])} · rejected {len(summary['rejected'])}"
        f" · ledger names written {named}")
    if summary["design"]:
        log(f"    {len(summary['design'])} name(s) need design's ruling — see the report")
    if summary["out_of_scope"]:
        log(f"    {len(summary['out_of_scope'])} added but out of scope (won't render)")
    return summary


# ------------------------------------------------------------------- report


def write_report(meta: dict, avail: dict, photos: dict, news: dict, verdict: str) -> str:
    L = [f"# Refresh {today()}", "", f"**Outcome:** {verdict}", ""]

    if avail:
        L += ["## Availability", "",
              f"- Checked **{avail['checked']}** entries at rank 0–2",
              f"- Read **{avail['read']}** pages successfully "
              f"({avail['read'] * 100 // max(avail['checked'], 1)}%)",
              f"- Flipped to Gone: **{len(avail['gone'])}**",
              f"- Moved up a tier: **{len(avail['promoted'])}**",
              f"- Confirmed still available: **{len(avail['confirmed'])}**",
              f"- Out of stock but not permanently — noted, tier unchanged: "
              f"**{len(avail.get('noted', []))}**",
              f"- Left untouched (unreadable or unclear): **{len(avail['skipped'])}**", ""]
        if avail["gone"]:
            L += ["### Flipped to Gone", ""]
            L += [f"- **{w['brand']} {w['model']}** — \"{q}\"" for w, q in avail["gone"]] + [""]
        if avail["promoted"]:
            L += ["### Moved up", ""]
            L += [f"- **{w['brand']} {w['model']}** — {was} → {w['tier']}"
                  for w, was, _ in avail["promoted"]] + [""]

    if photos:
        L += ["## Photographs", "",
              f"- Resolved: **{len(photos['resolved'])}**",
              f"- Source has no og:image (will not retry): **{len(photos['none'])}**",
              f"- Source URL dead / 404 (will not retry): **{len(photos.get('dead', []))}**",
              f"- Source unreachable (retry in {PHOTO_RETRY_DAYS}d): **{len(photos['blocked'])}**",
              f"- Coverage now: **{meta.get('imagesResolved', 0)}/{meta.get('count', 0)}**", ""]

    if news:
        L += ["## New releases", "", f"- Added: **{len(news['added'])}**", ""]
        if news["added"]:
            L += ["> Newly researched entries — worth a spot-check before they age into "
                  "the record.", ""]
            L += [f"- **{e['brand']} {e['model']}** — {e['edition']}, {e['price']} "
                  f"(confidence: {e['conf']}) · [source]({e['source']})" for e in news["added"]] + [""]
        if news["rejected"]:
            L += ["<details><summary>Rejected candidates "
                  f"({len(news['rejected'])})</summary>", ""]
            L += [f"- {n} — {why}" for n, why in news["rejected"]] + ["", "</details>", ""]
        if news.get("out_of_scope"):
            L += ["### Added but out of scope — these do not appear on the site", "",
                  "> A production cap is not a limited edition. They stay in the file and "
                  "start rendering by themselves if a later run confirms a real edition "
                  "size. Do not edit the data to force them on.", ""]
            L += [f"- **{e['brand']} {e['model']}** — {e['edition']}" for e in news["out_of_scope"]] + [""]
        if news.get("design"):
            # This is a question, not a note: the entries below are on the site
            # under their full names until design rules, which is the safe state
            # but not the finished one.
            L += ["### For design — ledger names this run would not guess", "",
                  "> Post these on the WATCHDROP RELAY thread. Until they are ruled on, "
                  "the entries show their full brand and model.", ""]
            L += [f"- {q}" for q in news["design"]] + [""]

    REPORT.write_text("\n".join(L))
    return "\n".join(L)


# --------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(description="Weekly refresh for the Watch Drop Index.")
    ap.add_argument("--stages", default="2,3,4", help="comma-separated stage numbers")
    ap.add_argument("--dry-run", action="store_true", help="change nothing on disk")
    ap.add_argument("--no-api", action="store_true", help="skip all model calls")
    ap.add_argument("--limit-checks", type=int, default=None)
    ap.add_argument("--photo-batch", type=int, default=PHOTO_BATCH)
    ap.add_argument("--corrections", type=Path, default=None,
                    help="apply Lowell's admin export (Copy corrections JSON) into data.json")
    args = ap.parse_args()
    stages = {int(s) for s in args.stages.split(",") if s.strip()}

    # --- Stage 1. If anything here is wrong we change nothing at all.
    log(f"[1] LOAD — {DATA}")
    try:
        payload = json.loads(DATA.read_text())
        meta, watches = payload["meta"], payload["watches"]
        assert isinstance(watches, list) and watches, "watches must be a non-empty list"
        for w in watches:
            for f in ("id", "brand", "model", "status", "tier", "rank", "buy", "source"):
                assert f in w, f"entry {w.get('id', '?')} missing {f}"
        ids = [w["id"] for w in watches]
        assert len(ids) == len(set(ids)), "duplicate ids in data.json"
    except Exception as e:  # noqa: BLE001
        log(f"FATAL: data.json did not parse or validate — {e}")
        log("Nothing was changed.")
        return 1

    before = json.dumps(payload, sort_keys=True)
    start_count = len(watches)
    log(f"    {start_count} entries · {len({w['brand'] for w in watches})} brands · "
        f"revision {meta.get('revision')} · updated {meta.get('updated')}")

    model = Model(enabled=not args.no_api)
    if args.no_api:
        log("    (--no-api: fetch layer only, no model calls)")

    # Lowell's hand corrections go in before anything else looks at a name, so a
    # run can never write a display name over an edit he made this morning.
    if args.corrections:
        applied, unknown = apply_corrections(watches, args.corrections)
        log(f"    corrections applied to {applied} entr{'y' if applied == 1 else 'ies'}"
            + (f" · {len(unknown)} unknown id(s): {', '.join(unknown[:5])}" if unknown else ""))

    avail = photos = news = {}
    if 2 in stages:
        avail = stage_availability(watches, model, args.limit_checks)
    if 3 in stages:
        photos = stage_photos(watches, args.photo_batch)
    if 4 in stages:
        news = stage_new_releases(watches, model, meta.get("updated", "2026-01-01"))

    # --- Stage 5. Guardrails first, then meta, then disk.
    gone_now = len(avail.get("gone", []))
    if gone_now > start_count * GONE_BLAST_RADIUS:
        log(f"\nREFUSING TO COMMIT: {gone_now} entries would flip to Gone "
            f"({gone_now / start_count:.0%} of the register, cap is {GONE_BLAST_RADIUS:.0%}).")
        log("That pattern means the fetch layer broke, not that the market cleared.")
        write_report(meta, avail, photos, news, f"BLOCKED — {gone_now} Gone flips exceeds the "
                                                f"{GONE_BLAST_RADIUS:.0%} blast-radius cap. Not committed.")
        return 20

    if 2 in stages and avail.get("checked") and avail.get("read", 0) == 0:
        log(f"\nFAILING: {avail['checked']} availability checks and not one page was readable.")
        log("Silence on this scale is a broken fetch layer, not a quiet week.")
        write_report(meta, avail, photos, news, "FAILED — zero pages readable across "
                                                f"{avail['checked']} checks. Not committed.")
        return 21

    meta["updated"] = today()
    meta["count"] = len(watches)
    meta["brands"] = len({w["brand"] for w in watches})
    meta["imagesResolved"] = sum(1 for w in watches if w.get("image"))
    meta["revision"] = int(meta.get("revision", 0)) + 1

    changed = json.dumps(payload, sort_keys=True) != before
    if not changed:
        log("\nNo changes to commit.")
        write_report(meta, avail, photos, news, "No changes.")
        return 10

    parts = []
    if news.get("added"):
        parts.append(f"{len(news['added'])} added")
    if avail.get("gone"):
        parts.append(f"{len(avail['gone'])} sold out")
    if avail.get("promoted"):
        parts.append(f"{len(avail['promoted'])} moved up")
    if photos.get("resolved"):
        parts.append(f"{len(photos['resolved'])} photos resolved")
    if avail.get("confirmed"):
        parts.append(f"{len(avail['confirmed'])} stock checks")
    subject = f"refresh {today()} — " + (", ".join(parts) if parts else "no material change")

    if args.dry_run:
        log(f"\n--dry-run: would write data.json and commit as:\n    {subject}")
    else:
        DATA.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        log(f"\nWrote data.json — revision {meta['revision']}, {meta['count']} entries")

    write_report(meta, avail, photos, news, subject)
    Path(ROOT / "refresh-subject.txt").write_text(subject + "\n")
    log(f"Commit subject: {subject}")
    log(f"Model calls: {model.calls}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
