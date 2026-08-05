#!/usr/bin/env python3
"""
Weekly refresh for the Watch Drop Index.

The masthead claims the site is refreshed weekly. That claim is the product, and
this is the machinery behind it. Five stages:

  1  LOAD       read and validate data.json; abort loudly without touching anything
  2  AVAILABLE  re-check every entry that claims to be obtainable (rank <= 2)
  4  NEW        search the week's watch press for limited editions
  3  PHOTOS     backfill og:image for entries that still have none
  5  COMMIT     update meta, write data.json, emit a report

Stages run 2 → 4 → 3, which is the budget's priority order: the two stages that
cost money go first, most valuable first, so a tight ceiling truncates the least
valuable work. Photographs run last because they cost nothing at all — a fetch
and a parse, no model call — so a budget stop can never take them away.

The governing rule throughout: an unreadable page changes nothing. A 403, a
timeout, a bot wall and a JavaScript-only page are all silence, not evidence.
Only positive, quotable evidence moves an entry, and only ever in the direction
that evidence supports. False confidence is worse than missing coverage — the
whole site rests on the distinction between "we checked" and "we inferred".

A budget stop borrows that same rule: a call the ceiling refuses returns the
same "no answer" an unreadable page does, so every decision rule already leaves
the entry alone. That is what makes stopping half-way through safe to commit.

Usage:
    python3 scripts/refresh.py                      # full run
    python3 scripts/refresh.py --dry-run            # change nothing on disk
    python3 scripts/refresh.py --stages 2,3         # availability + photos only
    python3 scripts/refresh.py --no-api             # fetch layer only, no model calls
    python3 scripts/refresh.py --budget 2.50        # tighter ceiling for one run
    python3 scripts/refresh.py --stages 3 --budget 0  # photographs only; costs nothing

Exit codes:
    0   completed; data.json updated (or --dry-run)
    10  no changes to commit (clean run, nothing moved)
    20  blast radius exceeded — refused to commit, open an issue instead
    21  silence failure — the fetch layer looks broken
    1   hard error
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import datetime as dt
import hashlib
import html
import io
import json
import os
import re
import struct
import sys
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data.json"
REPORT = ROOT / "refresh-report.md"

MODEL = os.environ.get("WDI_MODEL", "claude-opus-5")
EFFORT = os.environ.get("WDI_EFFORT", "low")

# ------------------------------------------------------------- the spend guard
#
# A weekly ceiling in Canadian dollars, adjustable WITHOUT editing this file:
# set the repository variable WEEKLY_BUDGET_CAD (Settings → Secrets and
# variables → Actions → Variables). A variable, not a secret, so Lowell can read
# the current value as well as change it.
#
# The Anthropic console cap is monthly and in USD, which makes it a coarse
# backstop only. This guard is the real control and the only thing that
# understands "weekly" or "CAD".
#
# Hitting the ceiling is NOT a failure. The run stops asking the model, commits
# whatever it finished, and reports what it skipped — the job stays green,
# because a red badge every week for working as designed teaches everyone to
# ignore the badge.
WEEKLY_BUDGET_CAD = float(os.environ.get("WEEKLY_BUDGET_CAD") or 5)

# A fixed rate on purpose. At this precision a stale number is fine and an FX
# API is one more thing that can break a Monday morning; override with the
# USD_TO_CAD repository variable if it ever drifts enough to matter.
USD_TO_CAD = float(os.environ.get("USD_TO_CAD") or 1.40)

# USD per million tokens, from platform.claude.com/docs/en/about-claude/pricing
# (checked 2026-08-04). Cache writes are the 5-minute rate; nothing here sets
# cache_control, so those columns should stay at zero — they are counted anyway
# so that turning caching on later cannot silently under-report.
PRICES = {
    "claude-opus-5":   {"input": 5.0,  "cache_write": 6.25, "cache_read": 0.50, "output": 25.0},
    "claude-opus-4-8": {"input": 5.0,  "cache_write": 6.25, "cache_read": 0.50, "output": 25.0},
    "claude-sonnet-5": {"input": 2.0,  "cache_write": 2.50, "cache_read": 0.20, "output": 10.0},
    "claude-haiku-4-5": {"input": 1.0, "cache_write": 1.25, "cache_read": 0.10, "output": 5.0},
}
# Web search bills separately from tokens: $10 per 1,000 searches. Web fetch and
# (alongside either) code execution are free, so the photograph stage costs
# nothing at all — it never calls the model.
WEB_SEARCH_USD = 10.0 / 1000

# Guardrails.
GONE_BLAST_RADIUS = 0.15   # refuse to commit if this share of entries flips to Gone
PHOTO_RETRY_DAYS = 28      # how long before re-probing a source that errored
PHOTO_HOST_DELAY = 1.5     # seconds between two requests to the SAME outlet
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


def rank_for(status: str, buy_label: str, tags: list[str], buy_kind: str | None = None) -> int:
    """Tier derivation. Describes how the brand distributes the watch — never
    a guess about whether stock remains.

    `buy_kind` is the evidence from stage 8, and it can only ever DEMOTE. "Buy
    online now" is the strongest claim here, and it has to be earned: if we have
    looked at the page and a reader cannot buy the watch there, the honest
    answer is a retailer enquiry.

    This lives inside the derivation rather than as a separate pass on purpose.
    A demotion applied on top of this function would be silently reverted the
    next time an availability check re-derived the tier — two rules disagreeing,
    with the weaker one winning every Monday."""
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
        if not purchasable:
            return 2
        # Known-and-not-product demotes. UNKNOWN does not: an unreachable page
        # is silence, and silence has never been allowed to move an entry here.
        if buy_kind is not None and buy_kind != "product":
            return 2
        return 0
    raise ValueError(f"unknown status: {status!r}")


def apply_tier(entry: dict) -> None:
    """Re-derive tier and rank — unless a human has taken ownership of them.

    rank and tier are two spellings of one fact, so they are guarded together: a
    human who pins the tier and then gets the rank re-derived underneath them ends
    up with a row that renders one thing and filters as another, which is worse
    than either outcome on its own."""
    rank = rank_for(entry["status"], entry.get("buyLabel", ""),
                    entry.get("tags", []), entry.get("buyKind"))
    if is_manual(entry, "tier") or is_manual(entry, "rank"):
        if entry.get("rank") != rank:
            PROPOSALS.append({"id": entry.get("id"), "field": "tier",
                              "from": entry.get("tier"), "to": TIERS[rank],
                              "why": "derived from status, label and buy evidence"})
        return
    entry["rank"] = rank
    entry["tier"] = TIERS[rank]


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


class HostLimiter:
    """Politeness is per-OUTLET, not global: eight parallel requests spread
    over eight sites is fine, eight at one site is not. Requests to the same
    host are serialised and spaced; different hosts still run concurrently.
    Shared by every stage that fetches in bulk, so adding a stage cannot
    accidentally double the load one outlet sees."""

    def __init__(self, delay: float):
        self.delay = delay
        self._locks: dict[str, threading.Lock] = {}
        self._last: dict[str, float] = {}
        self._registry = threading.Lock()

    def run(self, url: str, work):
        host = domain_of(url) or "?"
        with self._registry:
            lock = self._locks.setdefault(host, threading.Lock())
        with lock:
            wait = self.delay - (time.monotonic() - self._last.get(host, 0.0))
            if wait > 0:
                time.sleep(wait)
            try:
                return work()
            finally:
                self._last[host] = time.monotonic()


def image_dimensions(url: str) -> tuple[int, int] | None:
    """Native pixel size, read from the file HEADER rather than by downloading
    the picture. Every format keeps it in the first few KB, so this is a bounded
    read of at most 128 KB against images that are frequently several MB.

    Stored so the lightbox can cap enlargement at native size: these are press
    og:image files, and blowing a 900px photograph up to fill a 4K display just
    makes it soft. Also lets the markup carry width/height, which stops the row
    jumping as each photograph loads."""
    try:
        r = requests.get(url, timeout=FETCH_TIMEOUT, stream=True, allow_redirects=True,
                         headers={"User-Agent": UA, "Accept": "image/*,*/*;q=0.8"})
        if r.status_code >= 400:
            r.close()
            return None
        buf = b""
        for chunk in r.iter_content(8192):
            buf += chunk
            if len(buf) >= 131072:
                break
        r.close()
    except requests.RequestException:
        return None
    return _parse_dimensions(buf)


def _parse_dimensions(buf: bytes) -> tuple[int, int] | None:
    if buf[:8] == b"\x89PNG\r\n\x1a\n" and len(buf) >= 24:
        return struct.unpack(">II", buf[16:24])
    if buf[:6] in (b"GIF87a", b"GIF89a") and len(buf) >= 10:
        return struct.unpack("<HH", buf[6:10])
    if buf[:4] == b"RIFF" and buf[8:12] == b"WEBP" and len(buf) >= 30:
        codec = buf[12:16]
        if codec == b"VP8 ":
            w, h = struct.unpack("<HH", buf[26:30])
            return w & 0x3FFF, h & 0x3FFF
        if codec == b"VP8L":
            bits = struct.unpack("<I", buf[21:25])[0]
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if codec == b"VP8X":
            w = buf[24] | buf[25] << 8 | buf[26] << 16
            h = buf[27] | buf[28] << 8 | buf[29] << 16
            return w + 1, h + 1
    if buf[:2] == b"\xff\xd8":                      # JPEG: walk to the SOF frame
        f = io.BytesIO(buf)
        f.read(2)
        while True:
            b = f.read(1)
            if not b:
                return None
            if b != b"\xff":
                continue
            while b == b"\xff":
                b = f.read(1)
            if not b:
                return None
            marker = b[0]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                continue
            raw = f.read(2)
            if len(raw) < 2:
                return None
            size = struct.unpack(">H", raw)[0]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                head = f.read(5)
                if len(head) < 5:
                    return None
                h, w = struct.unpack(">HH", head[1:5])
                return w, h
            f.seek(size - 2, 1)
    return None


def check_image(url: str) -> tuple[str, str]:
    """Is this image URL still serving an image? Returns one of:

      "ok"      — it serves an image; the entry is fine
      "rotted"  — POSITIVE evidence it does not: a 404/410, or a 200 that
                  hands back something that is not an image (a soft-404 HTML
                  error page renders as a broken picture just the same)
      "unclear" — a 403, a rate limit, a 5xx, a timeout. Silence, not evidence.

    The three-way split is the same rule the rest of this job runs on: only
    positive evidence moves an entry. A hotlink-blocking CDN answering 403 must
    never be allowed to delete a perfectly good photograph.
    """
    if not url or not url.startswith("http"):
        return "rotted", "no url"
    headers = {"User-Agent": UA, "Accept": "image/*,*/*;q=0.8"}
    try:
        r = requests.head(url, timeout=FETCH_TIMEOUT, allow_redirects=True, headers=headers)
        # Plenty of image hosts simply refuse HEAD. Fall back to a one-byte
        # ranged GET rather than pulling the whole file down.
        if r.status_code in (403, 405, 501) or not r.headers.get("content-type"):
            r = requests.get(url, timeout=FETCH_TIMEOUT, allow_redirects=True, stream=True,
                             headers={**headers, "Range": "bytes=0-0"})
            r.close()
    except requests.RequestException as e:
        return "unclear", f"fetch failed: {type(e).__name__}"

    ctype = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
    if r.status_code in (404, 410):
        return "rotted", f"HTTP {r.status_code}"
    if r.status_code >= 400:
        return "unclear", f"HTTP {r.status_code}"
    if ctype.startswith("image/"):
        return "ok", ctype
    if ctype:
        # 200, but it is not a picture — a soft 404. Positive evidence of rot.
        return "rotted", f"HTTP {r.status_code} serving {ctype}"
    return "unclear", f"HTTP {r.status_code} with no content-type"


def _is_bare_root(url: str) -> bool:
    """Does this URL point at a site's front door rather than a page on it?"""
    try:
        p = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    return p.path.strip("/") == "" and not p.query


def check_link(url: str, was_deep: bool | None = None) -> tuple[str, str]:
    """Is this page still there? The same three-way rule as check_image:

      "ok"      — it answers
      "dead"    — POSITIVE evidence it does not: 404/410, or a soft-404 where a
                  deep URL redirects to the site's bare root
      "unclear" — 403, 429, 5xx, a timeout. Silence, not evidence.

    THE SOFT-404 IS THE ONE THAT WOULD OTHERWISE BE MISSED, and it is the whole
    reason this cannot be a bare status check. When a publisher pulls an article
    or a retailer pulls a product, they very often 301 to the homepage or a
    category page rather than 404. A HEAD returns a clean 200, the link looks
    perfect, and the thing it pointed at is gone. So the destination is compared
    with the origin: a deep URL that lands on a bare root is dead, whatever the
    status code says.

    Deliberately NOT treated as dead: a deep URL landing on a different deep URL.
    Sites reorganise and redirect properly, and calling that rot would delete
    working links — the same asymmetry as 403 not meaning 404.
    """
    if not url or not url.startswith("http"):
        return "dead", "no url"
    deep = (not _is_bare_root(url)) if was_deep is None else was_deep
    headers = {"User-Agent": UA, "Accept": "text/html,*/*;q=0.8"}
    try:
        r = requests.head(url, timeout=FETCH_TIMEOUT, allow_redirects=True, headers=headers)
        # A great many sites refuse HEAD outright or answer it with nothing
        # useful. Fall back to a ranged GET rather than concluding from a refusal.
        if r.status_code in (403, 405, 501) or not r.headers.get("content-type"):
            r = requests.get(url, timeout=FETCH_TIMEOUT, allow_redirects=True, stream=True,
                             headers={**headers, "Range": "bytes=0-0"})
            r.close()
    except requests.RequestException as e:
        return "unclear", f"fetch failed: {type(e).__name__}"

    if r.status_code in (404, 410):
        return "dead", f"HTTP {r.status_code}"
    if r.status_code >= 400:
        return "unclear", f"HTTP {r.status_code}"
    final = str(r.url or url)
    # No origin/destination comparison needed: `deep` already means the origin
    # was not a bare root, so a bare-root destination is necessarily different.
    if deep and _is_bare_root(final):
        return "dead", f"soft-404: redirected to {final}"
    return "ok", f"HTTP {r.status_code}"


# ----------------------------------------------------------------- the model


class Model:
    """Thin wrapper so --no-api can stub every call out and the fetch layer
    stays testable without a key. It is also the meter and the gate: every
    call's real token usage is priced and charged against the weekly ceiling,
    and once the ceiling is reached the wrapper stops calling.

    A refused call returns None — exactly what an unreadable page returns — so
    every existing decision rule already treats it correctly: nothing moves
    without positive evidence. That is what makes a mid-run budget stop safe to
    commit rather than something to roll back."""

    def __init__(self, enabled: bool = True, budget_cad: float = WEEKLY_BUDGET_CAD,
                 carried_cad: float = 0.0):
        self.enabled = enabled
        # Already spent this week, before this run started. See week_cad().
        self.carried_cad = carried_cad
        self.calls = 0
        self.usd = 0.0
        self.searches = 0
        self.budget_cad = budget_cad
        self.skipped = 0            # calls the ceiling refused
        self.stopped_at = None      # which stage ran out
        self._worst_call_cad = 0.0  # self-calibrating reserve; see _afford()
        self.by_stage: collections.Counter = collections.Counter()
        self.calls_by_stage: collections.Counter = collections.Counter()
        self.searches_by_stage: collections.Counter = collections.Counter()
        self._client = None
        if enabled:
            import anthropic  # imported lazily so --no-api needs no dependency
            self._client = anthropic.Anthropic()

    # ---- money ------------------------------------------------------------
    @property
    def cad(self) -> float:
        """THIS RUN's spend."""
        return self.usd * USD_TO_CAD

    @property
    def week_cad(self) -> float:
        """Spend for the WEEK — what the ceiling is actually about.

        This distinction was a live bug until 2026-08-05. Every run started its
        meter at zero, so a ceiling named "weekly" was really "per invocation,
        unbounded per week": one manual dispatch spent 4.33 CAD and Monday's
        scheduled run would have been free to spend 5.00 more, with nothing
        anywhere noticing. The word promised a guarantee the code did not make.
        The carried figure is read from meta.spend and rolls over on Monday."""
        return self.carried_cad + self.cad

    def remaining_cad(self) -> float:
        return max(0.0, self.budget_cad - self.week_cad)

    def exhausted(self) -> bool:
        """Would the next call breach the ceiling? The reserve is the most
        expensive call seen so far, so the guard calibrates itself against this
        workload rather than an estimate someone guessed a year ago — and the
        ceiling is respected rather than merely noticed after the fact.
        Read-only: callers use it to stop fetching pages they cannot judge."""
        if self.budget_cad <= 0:
            return False                      # no ceiling configured
        return self.week_cad + max(self._worst_call_cad, 0.05) > self.budget_cad

    def _afford(self, stage: str) -> bool:
        if self.exhausted():
            self.skipped += 1
            if self.stopped_at is None:
                self.stopped_at = stage
                carried = (f" — {self.carried_cad:.2f} of it spent earlier this week"
                           if self.carried_cad else "")
                log(f"    ! weekly ceiling of {self.budget_cad:.2f} CAD reached "
                    f"({self.week_cad:.2f} CAD spent this week{carried}). Skipping the rest "
                    f"of the model work; everything finished so far still commits.")
            return False
        return True

    def _charge(self, usage, stage: str = "other") -> None:
        """Price one response. Unknown fields default to zero rather than
        raising — a usage field that moves must never take a run down, and the
        spend line in the report is where an under-count would show up."""
        p = PRICES.get(MODEL) or PRICES["claude-opus-5"]
        get = lambda name: getattr(usage, name, 0) or 0
        usd = (get("input_tokens") * p["input"]
               + get("cache_creation_input_tokens") * p["cache_write"]
               + get("cache_read_input_tokens") * p["cache_read"]
               + get("output_tokens") * p["output"]) / 1_000_000
        server = getattr(usage, "server_tool_use", None)
        searches = getattr(server, "web_search_requests", 0) or 0 if server else 0
        self.searches += searches
        usd += searches * WEB_SEARCH_USD
        self.usd += usd
        # Per-stage, because a single total cannot answer the question that
        # actually matters: what does ONE stock check cost, versus one press
        # search? Without that split, a cadence tiered by volatility can only
        # be guessed at. Counted here rather than estimated afterwards from
        # call counts, which silently assumes every call costs the same — and
        # a 16k-token search with 18 web results plainly does not.
        self.by_stage[stage] += usd
        self.calls_by_stage[stage] += 1
        self.searches_by_stage[stage] += searches
        self._worst_call_cad = max(self._worst_call_cad, usd * USD_TO_CAD)

    # ---- calls ------------------------------------------------------------
    def structured(self, prompt: str, schema: dict, max_tokens: int = 8000,
                   stage: str = "judgement") -> dict | None:
        if not self.enabled:
            return None
        if not self._afford(stage):
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
                self._charge(r.usage, stage)
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

    def search(self, prompt: str, domains: list[str], max_tokens: int = 16000,
               stage: str = "search") -> str | None:
        if not self.enabled:
            return None
        if not self._afford(stage):
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
            # Streaming still carries a full usage block on the final message —
            # including server_tool_use.web_search_requests, which is the only
            # place the per-search charge is visible.
            self._charge(msg.usage, stage)
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
    res = {"id": entry["id"], "changed": False, "note": None, "verdict": None,
           "read": False, "budget": False}
    # Check the ceiling BEFORE fetching: there is no point pulling someone
    # else's page for a judgement we cannot afford to make.
    if model.exhausted():
        res["budget"] = True
        res["note"] = "skipped — weekly budget reached"
        return res
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
        VERDICT_SCHEMA, stage="availability",
    )
    if not verdict:
        res["note"] = "no verdict"
        return res
    res["verdict"] = verdict
    return res


def stage_availability(watches: list[dict], model: Model, limit: int | None) -> dict:
    # Retracted entries are skipped here rather than filtered at the display
    # layer alone: this is the stage that spends money, and paying to re-check
    # the availability of a watch nobody can see is the one waste with a bill
    # attached.
    targets = [w for w in watches if w["rank"] <= 2 and not is_retracted(w)]
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
                                "note": "worker error", "verdict": None, "budget": False})
            if i % 15 == 0:
                log(f"    ...{i}/{len(targets)}")

    by_id = {w["id"]: w for w in watches}
    summary = {"checked": len(targets), "read": 0, "gone": [], "promoted": [],
               "confirmed": [], "noted": [], "skipped": [], "budget_skipped": 0}

    for r in results:
        w = by_id[r["id"]]
        if r.get("budget"):
            summary["budget_skipped"] += 1
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
            if not guarded_set(w, "status", "Sold out", f'page reads: "{quote}"'):
                # A human owns this entry's status. Record what the page said —
                # `verified` is evidence, not an editorial claim, so it is always
                # safe to write — and leave the status alone.
                w["verified"] = {"date": today(), "note": f'Purchase page reads: "{quote}"'}
                summary["skipped"].append((w, "status is a manual field"))
                continue
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
                new_status = "Pre-order" if signal == "preorder_open" else "Available"
                if guarded_set(w, "status", new_status, f'page reads: "{quote}"'):
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


# ------------------------------------------- manual fields: a human edit wins
"""
If Lowell hand-corrects a price on Sunday, Monday's run must not stomp it.

This is the same shape of bug as the demotion one already fixed here: two rules
disagree about a field, and the one that runs on a timer wins every time — so the
human's edit survives right up until the moment nobody is watching. The rule:

    Automation may PROPOSE a change to a manual field. It may never COMMIT one.

`entry["manual"]` lists the fields a human owns. Everything not in that list
behaves exactly as before. A refused write is recorded and surfaced in the run
report rather than dropped, because the fact worth knowing is not "the edit was
protected" but "automation and a human now disagree about this price" — which is
one click from being resolved and impossible to notice if it is swallowed.

Identical in principle to the rule already standing for the curated editorial
sections: a model may propose a change to a claim a human made, never commit one.
One principle, two places.
"""

# The fields a human can own. Deliberately not "any key": imageProbe, imageCheck
# and deadImages are bookkeeping the stages need in order to stay correct, and
# letting a human freeze them would break the loop-avoidance they exist for.
MANUAL_FIELDS = frozenset({
    "brand", "model", "displayBrand", "displayModel", "ref", "cat", "desc", "specs",
    "edition", "price", "priceNum", "date", "status", "tier", "rank", "buy",
    "buyLabel", "buyKind", "source", "image", "imageCredit", "conf", "tags",
})

# Proposals a run wanted to make and was not allowed to. Module-level because the
# alternative is threading a collector through every stage signature for a list
# that is empty on almost every run. Appends are atomic under the GIL, which is
# all the thread pools here require.
PROPOSALS: list[dict] = []


def is_manual(entry: dict, field: str) -> bool:
    return field in (entry.get("manual") or [])


def guarded_set(entry: dict, field: str, value, why: str = "") -> bool:
    """Write `field` unless a human owns it. Returns True if the write happened."""
    if is_manual(entry, field):
        if entry.get(field) != value:
            PROPOSALS.append({"id": entry.get("id"), "field": field,
                              "from": entry.get(field), "to": value, "why": why})
        return False
    entry[field] = value
    return True


def mark_manual(entry: dict, fields: list[str]) -> None:
    """Record that a human now owns these fields."""
    owned = set(entry.get("manual") or []) | {f for f in fields if f in MANUAL_FIELDS}
    entry["manual"] = sorted(owned)
    entry["editedOn"] = today()
    entry["editedBy"] = "admin"


def release_manual(entry: dict, fields: list[str] | None = None) -> None:
    """Hand fields back to automation. None releases everything."""
    if fields is None:
        entry.pop("manual", None)
        return
    owned = set(entry.get("manual") or []) - set(fields)
    if owned:
        entry["manual"] = sorted(owned)
    else:
        entry.pop("manual", None)


def week_anchor(day: str | None = None) -> str:
    """The Monday of the week containing `day`. The ledger key.

    Monday rather than a rolling seven days on purpose: a rolling window means
    the answer to "how much is left?" changes while nobody is running anything,
    which is impossible to reason about from a run report. A named day is
    checkable by a human against a calendar."""
    d = dt.date.fromisoformat(day or today())
    return (d - dt.timedelta(days=d.weekday())).isoformat()


def spend_carried(meta: dict) -> tuple[float, str]:
    """What has already been spent this week, and which week that is.

    Returns 0 when the recorded week is not the current one — that IS the
    rollover, and doing it on read means it happens even on a run that spends
    nothing, rather than waiting for the next paid run to notice."""
    rec = meta.get("spend") or {}
    week = week_anchor()
    if rec.get("weekStart") != week:
        return 0.0, week
    try:
        return max(0.0, float(rec.get("cad") or 0.0)), week
    except (TypeError, ValueError):
        # A corrupt ledger must not hand out a free budget. Treating it as
        # "nothing spent" would be the failure this whole function exists to
        # prevent, so it reads as fully spent instead and a human can reset it.
        log("    ! spend ledger is unreadable — treating the week as fully spent")
        return float("inf"), week


def effective_budget(meta: dict, default_cad: float) -> tuple[float, bool]:
    """The ceiling in force, and whether it is a one-week override.

    "Raise it to 10 for this week" has to MEAN this week, or it is just a
    permanent raise that nobody remembers to undo — which is the same silent
    drift this codebase keeps catching elsewhere. So an override is stamped with
    the week it belongs to and simply stops applying when that week rolls over.
    Nobody has to remember anything.

    Fails SAFE in both directions: an override for another week, or one that will
    not parse, falls back to the standing ceiling rather than the raised one. A
    corrupt override must never be the reason a run spends more.
    """
    ov = meta.get("ceilingOverride") or {}
    if ov.get("weekStart") != week_anchor():
        return default_cad, False
    try:
        raised = float(ov.get("cad"))
    except (TypeError, ValueError):
        log("    ! ceiling override is unreadable — falling back to the standing ceiling")
        return default_cad, False
    if raised <= 0:
        return default_cad, False
    return raised, True


def record_spend(meta: dict, model: "Model") -> None:
    meta["spend"] = {"weekStart": week_anchor(), "cad": round(model.week_cad, 4)}


def is_retracted(entry: dict) -> bool:
    """Entries are never deleted — a mistaken one is part of the audit trail and a
    sold-out one is the historical record. `retracted` stops it rendering."""
    return bool(entry.get("retracted"))


# ------------------------------------------------- takedowns: the suppression list
"""
We publish photographs we do not own, under an editorial-use rationale, with a
published address for rights holders to object to. Honouring an objection is TWO
steps and only the second one actually holds.

Nulling `image` on its own lasts until the next photograph pass, which re-reads
the same source article, finds the same og:image, and writes it straight back —
so a removal would silently undo itself within a day of the daily schedule. The
suppression list is what makes it permanent. It is the difference between
complying with a takedown and appearing to comply with one, and it is exactly the
same shape of bug as `deadImages`: two stages that disagree, with the weaker one
winning on a timer.

Kept inside data.json rather than a file of its own on purpose — the refresh
workflow refuses to commit anything except data.json, so a separate file could
be written by hand but never maintained by the job or the admin panel.

Two shapes, both honoured everywhere an image URL is considered:
    {"url": "https://…/photo.jpg", "on": "2026-08-05", "note": "…"}
    {"domain": "example.com",      "on": "2026-08-05", "note": "…"}
A domain entry is for an outlet that objects wholesale rather than to one image.
"""


def _norm_url(url: str) -> str:
    """Compare URLs the way a takedown request means them: same picture, ignoring
    a tracking query string or a capitalised host."""
    try:
        p = urllib.parse.urlsplit((url or "").strip())
    except ValueError:
        return (url or "").strip().lower()
    return urllib.parse.urlunsplit(("https", p.netloc.lower().removeprefix("www."), p.path, "", ""))


def suppressions(payload: dict) -> list[dict]:
    return payload.get("suppressed") or []


def is_suppressed(url: str | None, rules: list[dict]) -> bool:
    if not url:
        return False
    norm, host = _norm_url(url), domain_of(url)
    for r in rules:
        if r.get("url") and _norm_url(r["url"]) == norm:
            return True
        d = (r.get("domain") or "").lower().removeprefix("www.")
        if d and (host == d or host.endswith("." + d)):
            return True
    return False


def suppress_image(payload: dict, url: str, note: str = "") -> int:
    """Action a takedown. Records the rule, then clears the picture everywhere it
    is currently used. Returns how many entries were cleared.

    Deliberately does NOT touch `source`, `imageCredit` history or the entry
    itself: the objection is to republishing the photograph, not to the fact that
    the outlet reported the watch. The entry keeps its provenance and simply
    carries no picture, which the register is already built to render honestly."""
    rules = payload.setdefault("suppressed", [])
    if not any(_norm_url(r.get("url", "")) == _norm_url(url) for r in rules if r.get("url")):
        rules.append({"url": url, "on": today(), "note": note or "takedown request"})
    return enforce_suppressions(payload)


def enforce_suppressions(payload: dict) -> int:
    """Clear every suppressed image currently in the data. Runs at load, before
    any stage reads an image, so a rule added by hand or by the admin panel takes
    effect on the very next run rather than whenever stage 7 gets round to it."""
    rules = suppressions(payload)
    if not rules:
        return 0
    cleared = 0
    for w in payload.get("watches", []):
        if is_suppressed(w.get("image"), rules):
            w["image"] = None
            w["imageCredit"] = None
            w["imageSize"] = None
            # A permanent verdict, so the photograph stage does not spend a fetch
            # on this article every run only to be refused at the end of it.
            w["imageProbe"] = {"date": today(), "result": "none", "note": "suppressed on request"}
            cleared += 1
    return cleared


# ---------------------------------------------------------- stage 3: photos


def photo_candidates(watches: list[dict]) -> list[dict]:
    out = []
    for w in watches:
        if w.get("image"):
            continue
        # A human who cleared a manual image is asking for automatic resolution
        # again, so `manual` containing "image" with no image is not a block —
        # but a human who set one and had it die (the rot check FLAGS rather than
        # clears a manual image, see stage 7) must not have a replacement chosen
        # for them. That case never reaches here, because the image is still set.
        if is_retracted(w):
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


def stage_photos(watches: list[dict], batch: int = 0, suppressed: list[dict] | None = None) -> dict:
    """Uncapped by default. Reading an og:image tag is a fetch and a parse — no
    model call, no judgement, no cost — so the per-run cap this used to carry
    was throttling the only free stage in the job and stretching a one-run pass
    across seven weeks. `batch` survives as a manual override for testing.

    Politeness is per-OUTLET, not global: eight parallel requests spread over
    eight sites is fine, eight at one site is not. Requests to the same host are
    serialised and spaced by PHOTO_HOST_DELAY, so 200 fetches take a few minutes
    and no single outlet notices."""
    rules = suppressed or []
    targets = photo_candidates(watches)
    if batch:
        targets = targets[:batch]
    log(f"\n[3] PHOTOGRAPHS — probing {len(targets)} sources "
        f"({sum(1 for w in watches if w.get('image'))}/{len(watches)} resolved)"
        + (f" [capped at {batch}]" if batch else ""))
    summary = {"resolved": [], "none": [], "blocked": [], "dead": [], "stale_source": []}

    limiter = HostLimiter(PHOTO_HOST_DELAY)

    def probe(w: dict) -> tuple[dict, str | None, str]:
        src = w.get("source", "")
        raw, note = limiter.run(src, lambda: fetch(src))
        if raw is None:
            return w, None, note
        img = og_image(raw, w["source"])
        # Refuse to re-adopt a URL stage 7 already proved dead, or the two
        # stages would hand the same broken picture back and forth every week.
        if img and img in (w.get("deadImages") or []):
            return w, None, "og:image is a URL already proven dead"
        # The takedown gate. This is the check that makes a removal permanent:
        # without it the article still offers the picture and we would republish
        # it on the next run, having been asked not to.
        if img and is_suppressed(img, rules):
            return w, None, "og:image is suppressed on request"
        return w, img, "ok" if img else "no og:image"

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for w, img, note in pool.map(probe, targets):
            if img:
                w["image"] = img
                w["imageCredit"] = outlet_for(w["source"])
                w.pop("imageProbe", None)
                # Measured now, while we are already talking to this host, so
                # the lightbox can cap enlargement at native size.
                size = limiter.run(img, lambda: image_dimensions(img))
                if size:
                    w["imageSize"] = list(size)
                summary["resolved"].append(w)
            elif note == "no og:image":
                w["imageProbe"] = {"date": today(), "result": "none"}
                summary["none"].append(w)
            elif note == "og:image is suppressed on request":
                # Permanent, not a retry candidate — the article will keep
                # offering it and we will keep declining. "none" is the right
                # verdict because as far as this register is concerned there is
                # no photograph available for this entry.
                w["imageProbe"] = {"date": today(), "result": "none", "note": note}
                summary["none"].append(w)
            elif note.startswith("og:image is a URL already proven dead"):
                # The article is fine; its picture is not. Worth another look
                # in 28 days — outlets do sometimes repair their own images —
                # but reported as its own thing rather than as "unreachable",
                # which would be a lie about the source.
                w["imageProbe"] = {"date": today(), "result": "blocked", "note": note}
                summary["stale_source"].append(w)
            else:
                result = probe_result_for(note)
                w["imageProbe"] = {"date": today(), "result": result, "note": note}
                summary["dead" if result == "dead" else "blocked"].append(w)

    log(f"    resolved {len(summary['resolved'])} · no og:image {len(summary['none'])} · "
        f"dead source {len(summary['dead'])} · unreachable {len(summary['blocked'])}"
        + (f" · source still offering a dead image {len(summary['stale_source'])}"
           if summary["stale_source"] else ""))
    return summary


# ---------------------------------------------------- stage 8: the buy links
"""
"Buy online now" is the strongest claim this register makes, and for a large
share of entries the link behind it is a brand homepage or a category page.
Telling a reader to go and find it themselves is exactly the aggregator
behaviour the site exists to beat.

The second-order failure is worse than the first, and it is why this is not
cosmetic: the Monday stock check fetches these same URLs and judges availability
from them. A homepage cannot report that a watch is sold out — it reads as
perfectly fine for ever. So for those entries the verification is structurally
incapable of detecting the thing it exists to detect, and a green "Stock checked"
note on one of them asserts more than we know.

Classification is by EVIDENCE, not by URL shape:
  product — the page names this watch AND offers a way to buy it
  listing — the page names this watch but sells nothing (a review, a spec page)
  brand   — the page never names it (homepage, category, collection)
  none    — there is no URL to check

A fetch failure is NOT a classification. Chat's four values have no slot for
"we could not tell", and calling an unreachable page `brand` would invent a fact
from silence — the one thing this job never does. Those keep whatever buyKind
they had and are reported separately.
"""

# Words that appear in half the watch names ever made. Matching on these would
# let a category page claim it names a specific watch.
_GENERIC = {
    "watch", "watches", "limited", "edition", "automatic", "chronograph", "steel",
    "titanium", "bronze", "black", "blue", "green", "white", "silver", "gold",
    "dial", "series", "collection", "special", "auto", "date", "diver", "gmt",
    "the", "and", "with", "for", "new", "mens", "womens", "piece", "pieces",
}

# Purchase affordance, in the MARKUP rather than the prose — a cart button is a
# form, an attribute or a schema.org Offer long before it is a word on screen.
_CART = re.compile(
    r"add[\s_-]*to[\s_-]*(cart|bag|basket)|/cart/add|single_add_to_cart_button|"
    r"add_to_cart_button|data-product-id|\bbuy\s+now\b|\bpre-?order\b|"
    r'"@type"\s*:\s*"Offer"|itemprop=["\']offers|name="add"|id="AddToCart',
    re.I,
)


def _distinctive(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", text.lower()) if t not in _GENERIC}


def names_the_watch(entry: dict, text: str) -> bool:
    """Does this page actually identify THIS watch? A reference number is the
    strongest signal; otherwise most of the distinctive words in the model name
    have to appear. Erring towards 'no' is deliberate — a false negative
    under-claims, a false positive tells a reader to buy something that is not
    there."""
    low = text.lower()
    ref = str(entry.get("ref") or "").strip()
    if ref and ref != "—" and len(ref) >= 4:
        squashed = re.sub(r"[^a-z0-9]", "", ref.lower())
        if len(squashed) >= 4 and squashed in re.sub(r"[^a-z0-9]", "", low):
            return True
    tokens = _distinctive(entry.get("model", ""))
    if not tokens:
        tokens = _distinctive(entry.get("brand", ""))
    if not tokens:
        return False
    hit = sum(1 for t in tokens if t in low)
    return hit / len(tokens) >= 0.6


def classify_buy(entry: dict) -> tuple[str | None, str]:
    url = entry.get("buy") or ""
    if not url.startswith("http"):
        return "none", "no url"
    raw, note = fetch(url)
    if raw is None:
        return None, note                      # silence: not a classification
    text = page_text(raw)
    if len(text) < MIN_PAGE_TEXT:
        return None, "page unreadable"
    named = names_the_watch(entry, text)
    sells = bool(_CART.search(raw)) or bool(jsonld_availability(raw))
    if named and sells:
        return "product", "names the watch and offers a way to buy it"
    if named:
        return "listing", "names the watch but offers no purchase"
    return "brand", "does not name this watch (homepage or category page)"


def stage_buy_links(watches: list[dict], only_rank: int | None = None) -> dict:
    targets = [w for w in watches if only_rank is None or w["rank"] <= only_rank]
    log(f"\n[8] BUY LINKS — classifying {len(targets)} links by evidence")
    summary = {"kinds": collections.Counter(), "unreadable": [], "demote": [], "changed": []}
    limiter = HostLimiter(PHOTO_HOST_DELAY)

    def probe(w: dict) -> tuple[dict, str | None, str]:
        kind, why = limiter.run(w.get("buy", ""), lambda: classify_buy(w))
        return w, kind, why

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for i, (w, kind, why) in enumerate(pool.map(probe, targets), 1):
            if kind is None:
                summary["unreadable"].append((w, why))
                continue
            if w.get("buyKind") and w["buyKind"] != kind:
                summary["changed"].append((w, w["buyKind"], kind))
            if not guarded_set(w, "buyKind", kind, why):
                # A human classified this link. Record the evidence anyway — it
                # is what they will want to look at when deciding whether to
                # release the field — but do not act on it.
                w["buyCheck"] = {"date": today(), "note": why, "manual": True}
                continue
            w["buyCheck"] = {"date": today(), "note": why}
            summary["kinds"][kind] += 1
            # The claim has to be earned: "Buy online now" means a page where the
            # reader can actually buy it.
            if w["rank"] == 0 and kind != "product":
                summary["demote"].append((w, kind))
            if i % 25 == 0:
                log(f"    ...{i}/{len(targets)}")

    log("    " + " · ".join(f"{k} {n}" for k, n in summary["kinds"].most_common())
        + f" · unreadable {len(summary['unreadable'])}")
    if summary["demote"]:
        log(f"    {len(summary['demote'])} entries claim 'Buy online now' without a product page")
    return summary


def apply_buy_demotions(summary: dict) -> int:
    """Tie the tier to the link. An entry we cannot point at a purchase page for
    should not be telling readers they can buy it online — it becomes a retailer
    enquiry until a real product URL is found. This LOWERS the headline
    'buyable online' figure, and that is the point: the current number is partly
    unearned.

    Re-derives through apply_tier rather than assigning a tier directly, so the
    stored rank is always something rank_for() would produce. Anything else
    drifts the moment another stage re-derives it."""
    # Counted from what actually moved, not from how many were queued: apply_tier
    # refuses and files a proposal when a human owns the tier, so counting the
    # queue would have the run report claiming demotions that never happened.
    moved = 0
    for w, _kind in summary["demote"]:
        before = w.get("rank")
        apply_tier(w)
        if w.get("rank") != before:
            moved += 1
    return moved


# ------------------------------------------------- stage 7: rotted image URLs
"""
The photograph stage only ever looks at entries with NO image, so an image URL
that dies after we resolved it is invisible to it forever — the row just renders
a broken picture. A 25-entry sample of the live data on 2026-08-04 found one
already dead (Spinnaker, 404), which puts the real number somewhere around 9 of
224. Not theoretical.

EVERY image, every run. This stage used to check a rotating subset of 40 on the
reasoning that rot is slow and requests are worth saving. That was wrong twice
over. A HEAD request costs no model call, no tokens and no budget, so there was
never anything to save — and sampling 40 of 224 meant a photograph could rot and
stay broken on the page for six weeks while the checker reported all clear. The
throttle was the expensive thing, not the requests. `batch` survives as a manual
override for testing and nothing else.

Ordering still matters even at full sweep: oldest-checked first, so if a run is
ever cut short the entries that go unchecked are the ones checked most recently.

The loop this has to avoid: clearing a dead image would send the entry back to
the photograph stage, which would re-read the same source article, find the same
dead og:image, and write it straight back. So a URL proven dead is remembered in
`deadImages` and the photograph stage will not re-adopt it. An entry with no
photograph is honest; an entry with a broken one is not.
"""

IMAGE_CHECK_BATCH = 0      # 0 = every resolved photograph, every run. See above.
MAX_DEAD_REMEMBERED = 4    # enough to break the loop without growing forever


def image_check_candidates(watches: list[dict], batch: int) -> list[dict]:
    have = [w for w in watches if w.get("image")]
    # Ordering only bites when someone passes a batch for testing: at the default
    # full sweep every entry is checked regardless. Note that a healthy entry no
    # longer carries a stamp at all (see the loop below), so this now sorts
    # "everything that is not currently failing" as equal — which is correct,
    # because among healthy entries there is nothing to prioritise.
    have.sort(key=lambda w: -days_since((w.get("imageCheck") or {}).get("date")))
    return have[:batch] if batch else have


def stage_image_rot(watches: list[dict], batch: int = IMAGE_CHECK_BATCH) -> dict:
    targets = image_check_candidates(watches, batch)
    total = sum(1 for w in watches if w.get("image"))
    log(f"\n[7] IMAGE ROT — re-checking {len(targets)} of {total} resolved photographs")
    summary = {"rotted": [], "ok": 0, "unclear": [], "flagged": []}
    limiter = HostLimiter(PHOTO_HOST_DELAY)

    def probe(w: dict) -> tuple[dict, str, str]:
        url = w["image"]
        result, detail = limiter.run(url, lambda: check_image(url))
        return w, result, detail

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for w, result, detail in pool.map(probe, targets):
            if result != "ok" and is_manual(w, "image"):
                # A HUMAN CHOSE THIS PICTURE. The machine reports the problem; it
                # does not overrule the choice. Clearing it would send the entry
                # back to automatic resolution and quietly replace a deliberate
                # editorial decision with an og:image scrape — which is exactly
                # the "weaker rule wins on a timer" failure this codebase keeps
                # having. Flagged, loudly, and left alone.
                w["imageCheck"] = {"date": today(), "result": result, "note": detail,
                                   "manual": True}
                summary["flagged"].append((w, detail))
                continue
            if result == "ok":
                # A pass is recorded on the RUN, not on the entry. Two reasons,
                # and the second is the important one.
                #
                # Mechanically: once this became a full daily sweep, stamping
                # every healthy entry rewrote 224 lines of data.json every day
                # for no information — a diff that large and that meaningless
                # hides the one line that did change, and the git history is
                # this register's audit trail.
                #
                # Editorially: this checker can prove a URL is dead. It can
                # never prove one is healthy for a reader — it is not their
                # browser, their network or their region. A per-entry "checked
                # and fine on this date" invites exactly the over-reading that
                # a clean sweep does not license, and it would sit one column
                # away from `verified`, which IS an evidenced claim. Keeping
                # only the failures makes the file say what we actually know.
                w.pop("imageCheck", None)
                summary["ok"] += 1
                continue
            w["imageCheck"] = {"date": today(), "result": result, "note": detail}
            if result == "unclear":
                # Silence. The photograph stays; we simply learned nothing.
                summary["unclear"].append((w, detail))
            else:
                dead = w["image"]
                remembered = [u for u in (w.get("deadImages") or []) if u != dead]
                w["deadImages"] = ([dead] + remembered)[:MAX_DEAD_REMEMBERED]
                w["image"] = None
                w["imageCredit"] = None
                # Clear the source probe too, so the photograph stage takes a
                # fresh look at the article this run rather than in 28 days.
                w.pop("imageProbe", None)
                summary["rotted"].append((w, detail))

    log(f"    still good {summary['ok']} · rotted and cleared {len(summary['rotted'])} "
        f"· no answer {len(summary['unclear'])}"
        + (f" · MANUAL AND BROKEN, needs a human {len(summary['flagged'])}"
           if summary["flagged"] else ""))
    return summary


# --------------------------------------- stage 9: source and calendar links
"""
The other half of the link sweep. Stage 7 checks image URLs and stage 8 checks
buy URLs, which between them covered roughly 480 of the register's ~750 links
while the run report said "full sweep". This closes the gap.

The two link types are treated DIFFERENTLY on purpose, because a dead one means
a different thing in each case:

  SOURCE — provenance. Losing it does not invalidate the watch: the edition was
    still announced, the price was still reported. But every confidence rating
    on this site rests on a source, so a `high` confidence pointing at a 404 is
    a claim quietly resting on nothing. Recorded on the entry, never auto-cleared
    and never used to demote — that is a judgement for a person.

  CALENDAR — curated. These were written by hand, so a dead one is flagged for a
    human rather than acted on, exactly like the editorial claims.

Nothing here spends: fetch and parse, no model call.
"""


def stage_links(watches: list[dict], calendar: dict | None = None) -> dict:
    sources = [w for w in watches if (w.get("source") or "").startswith("http")]
    cal_items = []
    for key in ("drops", "events"):
        for item in (calendar or {}).get(key, []) or []:
            if (item.get("url") or "").startswith("http"):
                cal_items.append((key, item))

    log(f"\n[9] SOURCE + CALENDAR LINKS — {len(sources)} sources, {len(cal_items)} calendar")
    summary = {"ok": 0, "dead": [], "unclear": [], "cal_dead": [], "by_outlet": collections.Counter()}
    limiter = HostLimiter(PHOTO_HOST_DELAY)

    def probe_source(w: dict) -> tuple[dict, str, str]:
        url = w["source"]
        result, detail = limiter.run(url, lambda: check_link(url))
        return w, result, detail

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for w, result, detail in pool.map(probe_source, sources):
            if result == "ok":
                # Same rule as the photograph sweep: a pass is recorded on the
                # run, not on the entry. A per-entry "source fine today" would
                # rewrite every line of data.json daily to say nothing, and would
                # assert more than a checker outside a reader's browser can know.
                w.pop("sourceCheck", None)
                summary["ok"] += 1
                continue
            w["sourceCheck"] = {"date": today(), "result": result, "note": detail}
            if result == "dead":
                summary["dead"].append((w, detail))
                summary["by_outlet"][outlet_for(w["source"])] += 1
            else:
                summary["unclear"].append((w, detail))

    for key, item in cal_items:
        result, detail = limiter.run(item["url"], lambda: check_link(item["url"]))
        if result == "dead":
            summary["cal_dead"].append((key, item, detail))

    log(f"    sources still good {summary['ok']} · DEAD {len(summary['dead'])} "
        f"· no answer {len(summary['unclear'])}"
        + (f" · calendar links dead {len(summary['cal_dead'])}" if summary["cal_dead"] else ""))
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
        NAMING_SCHEMA, max_tokens=4000, stage="ledger names",
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

    notes = model.search(SEARCH_PROMPT.format(since=since), PRESS_DOMAINS, stage="new releases")
    if not notes:
        log("    no research returned")
        return summary
    summary["notes"] = notes

    parsed = model.structured(EXTRACT_PROMPT.format(notes=notes[:60000]),
                              EXTRACT_SCHEMA, max_tokens=32000, stage="new releases")
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


# -------------------------------------------------------- stage 6: calendar
"""
The refresh spec covered `watches` and said nothing about `calendar`, so the
calendar has been quietly rotting: a "Dated opportunities" list advertising a
drop that happened last week is the small, visible kind of rot that tells a
reader nobody is home — and it needs no research to notice, only a date.

So this stage is deterministic and free. Expiry is arithmetic, not judgement:
no model call, no cost, nothing for the spend guard to gate. Editorial claims
(`expected`, `notHappening`) are NOT rewritten by a model — those are curated
research, and quietly regenerating them would trade a stale claim for an
unreviewed one. They are stamped and surfaced when they go stale instead.

Nothing is deleted, exactly as with the register: an expired item moves to
`calendar.passed`, which the page does not render. That keeps the historical
record, and — because it invents no new visual treatment — it needs no ruling
from design to ship.
"""

CALENDAR_STALE_DAYS = 30   # how long an un-rechecked editorial claim may stand

MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
          "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
# "early/mid/late Oct" — the day a month-qualifier resolves to. Deliberately
# generous: an opportunity that lingers a few days too long is a smaller sin
# than one that vanishes while it is still live.
QUALIFIERS = {"early": 10, "mid": 20, "late": 0}   # 0 = end of month


def month_end(year: int, month: int) -> dt.date:
    return (dt.date(year + month // 12, month % 12 + 1, 1) - dt.timedelta(days=1))


def calendar_end(text: str) -> dt.date | None:
    """The last day an entry could still be true. Returns None when the string
    carries no date at all ("Live now"), which is a different thing from a date
    that has passed and is handled differently by the caller.

    Reads the LAST date in the string, so a range ("13–16 Aug 2026", "Now →
    Sept 2026") expires on its end rather than its start."""
    s = (text or "").strip()
    if not s:
        return None
    year_m = re.search(r"\b(20\d\d)\b", s)
    if not year_m:
        return None
    year = int(year_m.group(1))

    # Take the last month mentioned; a range's end month is the one that matters.
    months = [(m.start(), MONTHS[m.group(1).lower()[:3]])
              for m in re.finditer(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?",
                                   s, re.I)]
    if not months:
        q = re.search(r"\bQ([1-4])\b", s, re.I)
        return month_end(year, int(q.group(1)) * 3) if q else dt.date(year, 12, 31)
    at, month = months[-1]

    # A day number immediately before that month token ("16 Aug", "7–10 Dec").
    head = s[:at]
    days = re.findall(r"\b(\d{1,2})\b", head)
    if days:
        try:
            return dt.date(year, month, int(days[-1]))
        except ValueError:
            return month_end(year, month)

    for word, day in QUALIFIERS.items():
        if re.search(rf"\b{word}\b", head, re.I):
            return dt.date(year, month, day) if day else month_end(year, month)
    return month_end(year, month)


def stage_calendar(cal: dict, watches: list[dict]) -> dict:
    log("\n[6] CALENDAR — expiring anything whose date has passed")
    now = dt.date.fromisoformat(today())
    summary = {"expired": [], "undated": [], "stale": [], "resolved": []}
    passed = cal.setdefault("passed", [])
    by_url = {}
    for w in watches:
        for key in ("buy", "source"):
            if w.get(key):
                by_url.setdefault(w[key], w)

    for kind in ("drops", "events"):
        keep = []
        for item in cal.get(kind, []):
            end = calendar_end(item.get("date", ""))
            if end is None:
                # No date to expire on. These are "Live now" style entries, and
                # the register already knows whether they are still live — so
                # the linked watch going Gone is what retires them.
                linked = by_url.get(item.get("url", ""))
                if linked and linked.get("rank") == 6:
                    item["passedOn"], item["kind"] = today(), kind
                    item["passedBecause"] = f"{linked['brand']} {linked['model']} is now Gone"
                    passed.append(item)
                    summary["expired"].append(item)
                    continue
                summary["undated"].append(item)
                keep.append(item)
                continue
            if end < now:
                item["passedOn"], item["kind"] = today(), kind
                item["passedBecause"] = f"ended {end.isoformat()}"
                passed.append(item)
                summary["expired"].append(item)
                continue
            keep.append(item)
        cal[kind] = keep

    # Editorial claims are stamped, not rewritten. An unstamped claim counts as
    # stale on its first pass, which is correct — nobody has confirmed it since
    # it was written.
    for kind in ("expected", "notHappening"):
        for item in cal.get(kind, []):
            age = days_since(item.get("checkedOn"))
            if age >= CALENDAR_STALE_DAYS:
                summary["stale"].append((kind, item, age))

    log(f"    expired {len(summary['expired'])} · still undated {len(summary['undated'])}"
        f" · editorial claims needing a look {len(summary['stale'])}")
    return summary


# ------------------------------------------------------------------- report


def summary_n(rot: dict) -> int:
    return (rot["ok"] + len(rot["rotted"]) + len(rot["unclear"])
            + len(rot.get("flagged") or []))


def write_report(meta: dict, avail: dict, photos: dict, news: dict, verdict: str,
                 model: "Model | None" = None, cal: dict | None = None,
                 rot: dict | None = None, buy: dict | None = None,
                 links: dict | None = None) -> str:
    L = [f"# Refresh {today()}", "", f"**Outcome:** {verdict}", ""]

    # Spend goes near the top and is reported on EVERY run, generous ceiling or
    # not. The first few real numbers are worth more than any estimate of what
    # the right ceiling should be.
    if model is not None:
        L += ["## Spend", "",
              f"- **{model.cad:.2f} CAD this run** (${model.usd:.3f} USD at a fixed "
              f"{USD_TO_CAD} CAD/USD)",
              f"- **{model.week_cad:.2f} CAD this week** of a {model.budget_cad:.2f} CAD "
              f"ceiling, week beginning {week_anchor()}"
              + (f" — {model.carried_cad:.2f} CAD of it from earlier runs"
                 if model.carried_cad else ""),
              f"- {model.calls} model call(s) · {model.searches} web search(es) "
              f"· photographs cost nothing (no model call)", ""]
        # The unit costs, because the total cannot answer the question that
        # decides cadence: what does ONE stock check cost against ONE press
        # search? Averaging the total over the call count assumes every call
        # costs the same, and a 16k-token search carrying 18 web results plainly
        # does not. Measured per stage rather than inferred.
        if model.by_stage:
            L += ["| stage | calls | searches | CAD | CAD per call |",
                  "|---|---|---|---|---|"]
            for stage, usd in model.by_stage.most_common():
                n = model.calls_by_stage[stage]
                L += [f"| {stage} | {n} | {model.searches_by_stage[stage]} | "
                      f"{usd * USD_TO_CAD:.3f} | {(usd * USD_TO_CAD / n if n else 0):.4f} |"]
            L += [""]
        if model.stopped_at:
            L += [f"> **The ceiling was reached during the {model.stopped_at} stage.** "
                  f"{model.skipped} further call(s) were skipped and everything already "
                  "finished was committed — this is the guard working, not a failure. "
                  "Raise the `WEEKLY_BUDGET_CAD` repository variable if the register "
                  "needs more than this each week.", ""]

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

    if rot:
        L += ["## Rotted photographs", "",
              f"- Re-checked: **{summary_n(rot)}** of the resolved photographs (rotating subset)",
              f"- Still serving an image: **{rot['ok']}**",
              f"- **Rotted and cleared: {len(rot['rotted'])}** — these were rendering a "
              "broken picture to readers",
              f"- No answer (403 / timeout — photograph kept): **{len(rot['unclear'])}**", ""]
        if rot["rotted"]:
            L += [f"- **{w['brand']} {w['model']}** — {why}" for w, why in rot["rotted"]] + [""]

    if photos:
        L += ["## Photographs", "",
              f"- Resolved: **{len(photos['resolved'])}**",
              f"- Source has no og:image (will not retry): **{len(photos['none'])}**",
              f"- Source URL dead / 404 (will not retry): **{len(photos.get('dead', []))}**",
              f"- Source unreachable (retry in {PHOTO_RETRY_DAYS}d): **{len(photos['blocked'])}**",
              f"- Coverage now: **{meta.get('imagesResolved', 0)}/{meta.get('count', 0)}**", ""]
        if photos.get("stale_source"):
            L += [f"- Source still offering a URL already proven dead: "
                  f"**{len(photos['stale_source'])}**", ""]
        # The residue is a documented list, not a mystery. Grouping the failures
        # by outlet is the point: a hundred scattered misses is the shape of the
        # web, but a hundred at one domain is one fixable cause.
        residue = photos["none"] + photos.get("dead", []) + photos["blocked"]
        if residue:
            by_host: dict[str, list[str]] = {}
            for w in residue:
                by_host.setdefault(domain_of(w.get("source", "")) or "?", []).append(w["id"])
            worst = sorted(by_host.items(), key=lambda kv: -len(kv[1]))
            L += [f"### Why {len(residue)} did not resolve, by outlet", "",
                  "> A single outlet high on this list is one fix, not a permanent gap.", ""]
            L += [f"- `{host}` — **{len(ids)}**" for host, ids in worst[:15]] + [""]
            if len(worst) > 15:
                L += [f"- …and {len(worst) - 15} other outlet(s) with fewer than "
                      f"{len(worst[15][1]) + 1} each", ""]

    if cal:
        L += ["## Calendar", "",
              f"- Expired and moved out of the live list: **{len(cal['expired'])}**",
              f"- Still live but carrying no date: **{len(cal['undated'])}**",
              f"- Editorial claims older than {CALENDAR_STALE_DAYS} days: **{len(cal['stale'])}**", ""]
        if cal["expired"]:
            L += [f"- ~~{i.get('what', '?')}~~ — {i.get('passedBecause', 'expired')}"
                  for i in cal["expired"]] + [""]
        if cal["stale"]:
            # Deliberately a question for a person, not a rewrite by the model:
            # these are curated research claims, and replacing one with an
            # unreviewed generation trades a stale fact for an invented one.
            L += ["### Editorial claims due a re-check", "",
                  "> Not auto-rewritten — these are researched claims. Confirm or correct "
                  "them, then stamp `checkedOn` on the item in `data.json`.", ""]
            L += [f"- **{i.get('what', '?')}** ({kind}) — "
                  + ("never checked" if age >= 1e8 else f"last checked {int(age)} days ago")
                  for kind, i, age in cal["stale"]] + [""]

    if buy:
        kinds = buy["kinds"]
        L += ["## Buy links", "",
              "> The strongest claim this register makes is \"Buy online now\". This checks "
              "the link behind it by evidence: does the page name this watch, and can a "
              "reader actually buy it there?", "",
              f"- **product** (names it, sells it): **{kinds.get('product', 0)}**",
              f"- **listing** (names it, no purchase): **{kinds.get('listing', 0)}**",
              f"- **brand** (never names it — homepage or category): **{kinds.get('brand', 0)}**",
              f"- **none** (no URL at all): **{kinds.get('none', 0)}**",
              f"- unreadable, left unclassified: **{len(buy['unreadable'])}**", ""]
        if buy["demote"]:
            L += [f"### {len(buy['demote'])} entries claim \"Buy online now\" without a page "
                  "to buy from", "",
                  "> The second-order problem is the worse one: the Monday stock check reads "
                  "these same URLs. A homepage cannot report that a watch is sold out, so for "
                  "these entries the verification cannot detect the thing it exists to detect.",
                  ""]
            L += [f"- **{w['brand']} {w['model']}** — `{kind}` · {w['buy']}"
                  for w, kind in buy["demote"][:40]] + [""]
        if buy["changed"]:
            L += ["### Buy links that changed shape since last week", ""]
            L += [f"- **{w['brand']} {w['model']}** — {was} → {now}" for w, was, now in buy["changed"]] + [""]
        if buy["unreadable"]:
            L += ["<details><summary>Unreadable buy links "
                  f"({len(buy['unreadable'])}) — not classified, because silence is not "
                  "evidence</summary>", "",
                  "> These are also the entries whose weekly stock check cannot work: if we "
                  "cannot read the page, neither can the verifier.", ""]
            L += [f"- {w['brand']} {w['model']} — {why} · {w['buy']}" for w, why in buy["unreadable"]]
            L += ["", "</details>", ""]

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

    if links:
        L += ["## Source and calendar links", "",
              "> Provenance, not decoration: every confidence rating on this site rests on "
              "a source, so a `high` confidence pointing at a 404 is a claim resting on "
              "nothing. Nothing here is auto-cleared or auto-demoted — a dead source does "
              "not make the watch untrue, and deciding what it does mean is a person's job.",
              "",
              f"- sources still answering: **{links['ok']}**",
              f"- **dead: {len(links['dead'])}** — 404/410 or a soft-404 redirect to a bare "
              "domain root",
              f"- no answer (403, 429, 5xx, timeout — silence, not evidence): "
              f"**{len(links['unclear'])}**", ""]
        if links["dead"]:
            L += ["### Dead sources", ""]
            L += [f"- **{w['brand']} {w['model']}** ({w.get('conf', '?')} confidence) — "
                  f"{why} · {w['source']}" for w, why in links["dead"][:40]] + [""]
            if links["by_outlet"]:
                # The by-outlet grouping is the genuinely useful half: one domain
                # producing most of the rot is a fixable cause, spread thin is
                # just the shape of the web.
                L += ["Dead sources by outlet — a single domain dominating this list is a "
                      "fixable cause; spread thin is just the web:", ""]
                L += [f"- {outlet}: {n}" for outlet, n in links["by_outlet"].most_common()] + [""]
        if links["cal_dead"]:
            L += ["### Dead calendar links — curated, so these need a human", ""]
            L += [f"- ({key}) **{item.get('what', '?')}** — {why} · {item.get('url')}"
                  for key, item, why in links["cal_dead"]] + [""]

    # Proposals last, because they are the section a person has to act on: every
    # one is a place where this run and a human disagree about a fact. Refusing
    # the write is only half the rule — a guard that hides the disagreement just
    # moves the silent failure somewhere quieter.
    if PROPOSALS:
        L += [f"## {len(PROPOSALS)} proposed changes to fields a human owns", "",
              "> Automation may propose a change to a manual field and may never commit "
              "one, so none of these were applied. Each is either evidence the entry needs "
              "correcting, or evidence the field should be released back to automation. "
              "Both are decisions for a person.", ""]
        for p in PROPOSALS[:60]:
            L += [f"- `{p['id']}` **{p['field']}**: `{p['from']!r}` → `{p['to']!r}`"
                  + (f" — {p['why']}" if p.get("why") else "")]
        if len(PROPOSALS) > 60:
            L += [f"- …and {len(PROPOSALS) - 60} more"]
        L += [""]

    if rot and rot.get("flagged"):
        L += [f"### {len(rot['flagged'])} hand-picked photographs are broken", "",
              "> These were chosen by a person, so the rot check reports them rather than "
              "clearing them — replacing a deliberate choice with an og:image scrape is not "
              "the machine's call. They are rendering broken to readers until someone picks "
              "a new one or releases the field.", ""]
        L += [f"- **{w['brand']} {w['model']}** — {why} · {w.get('image')}"
              for w, why in rot["flagged"]] + [""]

    REPORT.write_text("\n".join(L))
    return "\n".join(L)


# --------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(description="Weekly refresh for the Watch Drop Index.")
    ap.add_argument("--stages", default="2,3,4,6,7,8,9", help="comma-separated stage numbers")
    ap.add_argument("--dry-run", action="store_true", help="change nothing on disk")
    ap.add_argument("--no-api", action="store_true", help="skip all model calls")
    ap.add_argument("--limit-checks", type=int, default=None)
    ap.add_argument("--photo-batch", type=int, default=0,
                    help="cap the photograph pass (0 = every entry that still has none)")
    ap.add_argument("--image-batch", type=int, default=IMAGE_CHECK_BATCH,
                    help="cap the rot check for testing (0 = all, and that is the default)")
    ap.add_argument("--demote-unearned", action="store_true",
                    help="drop 'Buy online now' entries that have no product page to buy from")
    ap.add_argument("--budget", type=float, default=WEEKLY_BUDGET_CAD,
                    help="weekly ceiling in CAD for model spend (0 = no ceiling)")
    ap.add_argument("--corrections", type=Path, default=None,
                    help="apply Lowell's admin export (Copy corrections JSON) into data.json")
    ap.add_argument("--takedown", metavar="URL", default=None,
                    help="action a takedown: suppress this image URL permanently and clear it")
    ap.add_argument("--takedown-note", default="",
                    help="who asked, so the reason survives in the data")
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

    # The weekly ledger. Without this the ceiling is per-invocation and the word
    # "weekly" is a promise the code does not keep — see Model.week_cad().
    carried, week_start = spend_carried(meta)
    budget, overridden = effective_budget(meta, args.budget)
    model = Model(enabled=not args.no_api, budget_cad=budget, carried_cad=carried)
    if overridden:
        log(f"    ceiling RAISED to {budget:.2f} CAD for the week of {week_start} "
            f"(standing ceiling {args.budget:.2f}) — lapses on its own next Monday")
    if carried:
        log(f"    already spent this week (from {week_start}): {carried:.2f} CAD "
            f"· {max(0.0, budget - carried):.2f} CAD left of the ceiling")
    if args.no_api:
        log("    (--no-api: fetch layer only, no model calls)")
    log(f"    budget: {budget:.2f} CAD" if budget > 0 else "    budget: none set")

    # Takedowns are honoured BEFORE any stage reads an image. A rule added by
    # hand, by the admin panel or by --takedown takes effect on this run, not
    # whenever the rot check next happens to visit that entry.
    if args.takedown:
        takedown_cleared = suppress_image(payload, args.takedown, args.takedown_note)
        log(f"    takedown recorded — {args.takedown}")
        log(f"    cleared from {takedown_cleared} entr"
            f"{'y' if takedown_cleared == 1 else 'ies'}; it will not be re-resolved")
    else:
        takedown_cleared = enforce_suppressions(payload)
        if takedown_cleared:
            log(f"    {takedown_cleared} suppressed image(s) cleared before any stage ran")
    if suppressions(payload):
        log(f"    suppression list: {len(suppressions(payload))} rule(s) in force")

    # Lowell's hand corrections go in before anything else looks at a name, so a
    # run can never write a display name over an edit he made this morning.
    if args.corrections:
        applied, unknown = apply_corrections(watches, args.corrections)
        log(f"    corrections applied to {applied} entr{'y' if applied == 1 else 'ies'}"
            + (f" · {len(unknown)} unknown id(s): {', '.join(unknown[:5])}" if unknown else ""))

    # Stage order is the budget's priority order: the two stages that spend
    # money run first, most valuable first, so a tight ceiling truncates the
    # least valuable work rather than whatever happened to be last. Photographs
    # run LAST because they cost nothing — fetch and parse, no model call — so
    # they are never the thing a budget stop takes away. Running them after the
    # new-releases search also means this week's additions get their pictures
    # this week instead of next.
    avail = photos = news = cal = rot = buy = links = {}
    if 2 in stages:
        avail = stage_availability(watches, model, args.limit_checks)
    if 4 in stages:
        news = stage_new_releases(watches, model, meta.get("updated", "2026-01-01"))
    # Rot check BEFORE the photograph pass, so an image cleared this run is
    # re-resolved this run rather than next week. Both stages are free.
    if 7 in stages:
        rot = stage_image_rot(watches, args.image_batch)
    if 3 in stages:
        photos = stage_photos(watches, args.photo_batch, suppressions(payload))
    # Free: fetch and parse, no model call. Runs every week because buy links
    # rot and change shape without telling anyone.
    if 8 in stages:
        buy = stage_buy_links(watches)
        if args.demote_unearned:
            n = apply_buy_demotions(buy)
            if n:
                log(f"    demoted {n} entries out of 'Buy online now' — the claim was "
                    "not backed by a page a reader can buy from")
    # Free and deterministic, so it runs whatever the budget did — the calendar
    # rotting is the one failure a reader can see without checking anything.
    if 6 in stages:
        cal = stage_calendar(payload.setdefault("calendar", {}), watches)
    # The other half of the link sweep. Free, and it runs last because it is the
    # only stage that reports rather than repairs — nothing downstream waits on
    # it. Placed after the calendar so it sees whatever that stage retired.
    if 9 in stages:
        links = stage_links(watches, payload.get("calendar"))

    log(f"\nSPEND — {model.cad:.2f} CAD of {budget:.2f} "
        f"({model.calls} model call{'' if model.calls == 1 else 's'}, "
        f"{model.searches} web search{'' if model.searches == 1 else 'es'}, "
        f"${model.usd:.3f} USD at {USD_TO_CAD} CAD/USD)")

    # --- Stage 5. Guardrails first, then meta, then disk.
    gone_now = len(avail.get("gone", []))
    if gone_now > start_count * GONE_BLAST_RADIUS:
        log(f"\nREFUSING TO COMMIT: {gone_now} entries would flip to Gone "
            f"({gone_now / start_count:.0%} of the register, cap is {GONE_BLAST_RADIUS:.0%}).")
        log("That pattern means the fetch layer broke, not that the market cleared.")
        write_report(meta, avail, photos, news, f"BLOCKED — {gone_now} Gone flips exceeds the "
                                                f"{GONE_BLAST_RADIUS:.0%} blast-radius cap. Not committed.", model, cal, rot, buy)
        return 20

    # Silence is a failure — but only silence we actually went looking for.
    # Entries the ceiling skipped were never fetched, so they are not evidence
    # of a broken fetch layer; counting them here would turn a tight budget into
    # a red build every Monday, which is the opposite of what the guard is for.
    attempted = avail.get("checked", 0) - avail.get("budget_skipped", 0)
    if 2 in stages and attempted and avail.get("read", 0) == 0:
        log(f"\nFAILING: {attempted} availability checks and not one page was readable.")
        log("Silence on this scale is a broken fetch layer, not a quiet week.")
        write_report(meta, avail, photos, news, "FAILED — zero pages readable across "
                                                f"{attempted} checks. Not committed.", model, cal, rot, buy)
        return 21

    meta["updated"] = today()
    meta["count"] = len(watches)
    meta["brands"] = len({w["brand"] for w in watches})
    meta["imagesResolved"] = sum(1 for w in watches if w.get("image"))
    # Where a clean sweep is recorded now that healthy entries carry no stamp of
    # their own. One date for the run, which is all a clean sweep actually
    # establishes — read it as "nothing was found broken on this date", never as
    # "every photograph works", which no checker outside a reader's browser can
    # say. Only stamped when the stage actually ran, so it can never claim a
    # sweep that a --stages flag skipped.
    if rot:
        meta["lastImageSweep"] = today()
    # Written on EVERY run, including free ones: that is what rolls the week over
    # on a Monday whether or not anything paid has run yet.
    record_spend(meta, model)
    meta["revision"] = int(meta.get("revision", 0)) + 1

    changed = json.dumps(payload, sort_keys=True) != before
    if not changed:
        log("\nNo changes to commit.")
        write_report(meta, avail, photos, news, "No changes.", model, cal, rot, buy, links)
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
    if cal.get("expired"):
        parts.append(f"{len(cal['expired'])} calendar entries expired")
    if rot.get("rotted"):
        parts.append(f"{len(rot['rotted'])} rotted photos cleared")
    # A takedown is the most material change this job can make and it must never
    # land under "no material change" — that commit is the record that a rights
    # holder's request was honoured, and it has to be findable in the log.
    if takedown_cleared:
        parts.append(f"{takedown_cleared} photograph"
                     f"{'' if takedown_cleared == 1 else 's'} suppressed on request")
    subject = f"refresh {today()} — " + (", ".join(parts) if parts else "no material change")

    if args.dry_run:
        log(f"\n--dry-run: would write data.json and commit as:\n    {subject}")
    else:
        DATA.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        log(f"\nWrote data.json — revision {meta['revision']}, {meta['count']} entries")

    write_report(meta, avail, photos, news, subject, model, cal, rot, buy, links)
    Path(ROOT / "refresh-subject.txt").write_text(subject + "\n")
    log(f"Commit subject: {subject}")
    log(f"Model calls: {model.calls}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
