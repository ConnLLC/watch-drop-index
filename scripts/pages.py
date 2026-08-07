#!/usr/bin/env python3
"""
Per-watch pages, structured data, sitemap and feed.

WHY THESE EXIST, because it is not the reason you would guess. They are not a
second way to browse the register — the register is the experience and nothing
on it links here. They are LANDING TARGETS. "Watch drop" as a search term belongs
to pre-owned marketplaces and is not winnable; the queries we can win are
per-model ("Seiko x SEGA how many made"), and until now 246 of those competed
through a single URL. One page cannot rank for 246 model queries.

Called by build.py, which owns the palette and the lockup and passes them in, so
there is exactly one copy of the approved design language and this file makes no
visual decisions of its own.

THE FOUR RULES THAT ARE NOT MINE TO RELAX
  1. One outbound click. The buy link is the only link off-site; the source
     credit is subordinate. Nothing else leaves the domain.
  2. No entry point from the register. Lowell's constraint, checked by chat with
     him: these are reached from outside, never navigated to from the list.
  3. Structured data is a claim. offers.availability derives from the verified
     tier. InStock is emitted ONLY where a purchase page was actually read and
     classified as a product page — never from a tier name alone.
  4. Verification in front. It is the only thing about this register that no
     competitor can copy, because theirs are paid by referral.

URL STABILITY. A page's address is /w/<slug>-<id>.html, where the slug is
editorial and the id is not. Display names DO get edited (design's v1.2 ruling),
and an edit that silently 404s a page throws away whatever ranking it had. So
every path ever published is recorded in w/_paths.json, and a path that falls out
of use is left behind as a redirect to its replacement rather than deleted.
"""

from __future__ import annotations

import html
import json
import os
import re
import unicodedata

CANON = "https://www.watchdropindex.com"
PAGES_DIR = "w"
MANIFEST = os.path.join(PAGES_DIR, "_paths.json")
FEED_MAX = 50

# schema.org availability, derived — never asserted. The mapping is chat's
# (8437ba9f) with one tightening: InStock additionally requires that the buy page
# was read and classified `product`, so a tier we have not verified this week
# cannot put an in-stock claim in front of a crawler that will not read the caveat.
AVAIL = {
    "Buy online now": "https://schema.org/InStock",
    "Drop upcoming": "https://schema.org/PreOrder",
    "Gone": "https://schema.org/SoldOut",
}
AVAIL_DEFAULT = "https://schema.org/LimitedAvailability"


def availability(w):
    tier = w.get("tier")
    if tier == "Buy online now" and w.get("buyKind") != "product":
        return AVAIL_DEFAULT
    return AVAIL.get(tier, AVAIL_DEFAULT)


def slug(s):
    # × becomes "x" BEFORE the ascii fold, which would otherwise drop it. Collabs
    # are searched as "seiko x sega", so losing the x costs the exact long-tail
    # query the page exists to answer.
    s = str(s or "").replace("×", " x ")
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return re.sub(r"-{2,}", "-", s)[:70].strip("-")


def path_for(w):
    return f"{PAGES_DIR}/{slug(w['brand'] + ' ' + w['model'])}-{w['id']}.html"


def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def host_of(url):
    m = re.match(r"https?://([^/]+)", str(url or ""))
    return m.group(1).replace("www.", "", 1) if m else "the source"


def check_date(v):
    return (v.get("date") if isinstance(v, dict) else str(v or ""))[:10]


# --- the sentence a search result shows ------------------------------------
def description(w):
    """Honest, specific, and built from what we actually hold.

    Written for a search result, so the facts a person searched for come first:
    price, how many were made, whether it can still be had. Never asserts an
    availability we have not read — an unverified entry says what it is.
    """
    bits = []
    ed = str(w.get("edition") or "").strip()
    if ed and ed != "—":
        bits.append(ed if re.search(r"\d", ed) else "Edition size not disclosed")
    else:
        bits.append("Edition size not disclosed")
    price = str(w.get("price") or "").strip()
    if price and price != "—":
        bits.append(price)
    if w.get("date"):
        bits.append(f"released {w['date']}")
    sent = ", ".join(bits) + "."
    ver = w.get("verified")
    if ver:
        sent += f" Purchase page read {check_date(ver)}: {str(ver.get('note') if isinstance(ver, dict) else '').strip().rstrip('.')}."
    else:
        sent += f" Availability: {w.get('tier')}."
    return re.sub(r"\s+", " ", sent).strip()[:300]


def json_ld(w, url):
    """A Product node. Every field here is a claim to a machine that cannot read
    a caveat, so anything unverified is omitted rather than softened."""
    node = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": f"{w['brand']} {w['model']}",
        "brand": {"@type": "Brand", "name": w["brand"]},
        "description": description(w),
        "url": url,
        "category": w.get("cat"),
    }
    if w.get("image"):
        node["image"] = w["image"]
    ref = str(w.get("ref") or "").strip()
    if ref and ref != "—":
        node["mpn"] = ref
        node["sku"] = ref
    offer = {
        "@type": "Offer",
        "availability": availability(w),
        "url": w.get("buy") or url,
        "itemCondition": "https://schema.org/NewCondition",
    }
    if w.get("priceNum") is not None:
        offer["price"] = w["priceNum"]
        offer["priceCurrency"] = "USD"
    node["offers"] = offer
    return node


def site_ld(meta, count):
    """WebSite + Organization, emitted once on the index."""
    return [
        {"@context": "https://schema.org", "@type": "WebSite",
         "name": "Watch Drop Index", "url": CANON + "/",
         "description": meta.get("tagline"),
         "publisher": {"@type": "Organization", "name": "Conn LLC"}},
        {"@context": "https://schema.org", "@type": "Organization",
         "name": "Conn LLC", "url": CANON + "/",
         "address": {"@type": "PostalAddress", "addressLocality": "Toronto",
                     "addressRegion": "Ontario", "addressCountry": "CA"}},
    ]


def index_ld(meta, kept):
    """An ItemList of the register in display order, each item pointing at its own
    page. The list is the machine-readable table of contents; the Product detail
    lives on the page the item links to, which is where a crawler expects it."""
    items = [{"@type": "ListItem", "position": i + 1,
              "url": f"{CANON}/{path_for(w)}",
              "name": f"{w['brand']} {w['model']}"}
             for i, w in enumerate(kept)]
    return site_ld(meta, len(kept)) + [{
        "@context": "https://schema.org", "@type": "ItemList",
        "name": "Limited-edition watches of 2026",
        "description": meta.get("tagline"),
        "numberOfItems": len(items),
        "itemListOrder": "https://schema.org/ItemListOrderAscending",
        "itemListElement": items,
    }]


# --- the page ---------------------------------------------------------------
DOT = lambda r: "#1e6b41" if r == 0 else "#35597e" if r <= 2 else "#97701c" if r <= 5 else "#b0776b"

ROW = ('style="display:grid;grid-template-columns:112px 1fr;gap:14px;padding:8px 0;'
       'border-bottom:1px solid #e9e4d8"')
KEY = ('style="font-size:9.5px;letter-spacing:.15em;text-transform:uppercase;color:#8a8071;'
       'font-weight:700;padding-top:3px"')
VAL = 'style="font-size:14px;color:#17130d;overflow-wrap:anywhere"'


# The register's stylesheet, served once and cached, rather than 7.5 KB inlined
# into each of 246 pages. index.html keeps its inline copy — it is a single file
# with no build step and that property is deliberate — but at this multiple the
# arithmetic reverses.
#
# The two rules appended below are NOT new treatment. The mobile block indents
# [data-mq="detail"] by 16px because in the register it sits inside a row; on a
# standalone page there is no row and the indent reads as a misalignment.
# Neutralised here rather than by touching design's block. FLAGGED TO DESIGN.
PAGE_CSS_TAIL = """
@media (max-width:720px){
  [data-mq="detail"]{padding-left:0 !important;padding-right:0 !important}
}
"""


def page_html(w, meta, css, lockup, tier_help):
    url = f"{CANON}/{path_for(w)}"
    name = f"{w['brand']} {w['model']}"
    # The title is built for the query, not for us: a person searching this watch
    # types its name and then one of three words. All three are on the page.
    title = f"{name} — price, edition size and where to buy | Watch Drop Index"
    desc = description(w)
    dot = DOT(w.get("rank", 9))
    ver = w.get("verified")
    chk = w.get("buyCheck")

    og_img = (f'<meta property="og:image" content="{esc(w["image"])}">'
              f'<meta name="twitter:card" content="summary_large_image">'
              if w.get("image") else '<meta name="twitter:card" content="summary">')
    if w.get("image") and w.get("imageSize"):
        og_img += (f'<meta property="og:image:width" content="{w["imageSize"][0]}">'
                   f'<meta property="og:image:height" content="{w["imageSize"][1]}">')

    if w.get("image"):
        fig = (f'<figure style="margin:0"><img src="{esc(w["image"])}" alt="{esc(name)}" loading="lazy"'
               f' referrerpolicy="no-referrer"'
               f' style="width:100%;display:block;border:1px solid #ddd6c8;background:#ece7da">'
               f'<figcaption style="font-size:11px;color:#8a8071;margin-top:7px;letter-spacing:.04em">'
               f'Photograph · {esc(w.get("imageCredit") or "source")}</figcaption></figure>')
    else:
        plate = w["ref"] if w.get("ref") and w["ref"] != "—" else str(w["brand"]).upper()
        fig = ('<figure style="margin:0"><div style="border:1px solid #d5cdbc;background:#eeeadf;padding:9px">'
               '<div style="border:1px solid #ddd6c8;padding:44px 20px;text-align:center;display:grid;gap:12px;justify-items:center">'
               '<div style="font-size:9.5px;letter-spacing:.28em;text-transform:uppercase;color:#a09786;font-weight:600">Register entry</div>'
               f'<div style="font-size:15px;letter-spacing:.08em;color:#17130d;font-weight:600">{esc(plate)}</div>'
               '</div></div></figure>')

    # VERIFICATION FIRST — rule 4. This is the block that says what nobody else
    # on this subject can say, so it sits above the specification, not under it.
    if ver:
        verified = (f'<div style="border:1px solid #1e5c38;background:#f2f6f2;padding:13px 15px;margin:0 0 16px">'
                    f'<div style="font-size:9.5px;letter-spacing:.16em;text-transform:uppercase;color:#1e5c38;font-weight:700">Verified</div>'
                    f'<p style="margin:6px 0 0;font-size:13.5px;line-height:1.5;color:#17130d">'
                    f'We read the purchase page on {esc(check_date(ver))}. It said: '
                    f'{esc(str(ver.get("note") if isinstance(ver, dict) else ver))}</p></div>')
    elif chk:
        verified = (f'<div style="border:1px solid #d5cdbc;background:#f7f4ec;padding:13px 15px;margin:0 0 16px">'
                    f'<div style="font-size:9.5px;letter-spacing:.16em;text-transform:uppercase;color:#8a8071;font-weight:700">Buy link checked</div>'
                    f'<p style="margin:6px 0 0;font-size:13.5px;line-height:1.5;color:#17130d">'
                    f'{esc(check_date(chk))} — {esc(str(chk.get("note") if isinstance(chk, dict) else chk))}. '
                    f'No stock check has been run on this entry.</p></div>')
    else:
        verified = ('<div style="border:1px solid #d5cdbc;background:#f7f4ec;padding:13px 15px;margin:0 0 16px">'
                    '<div style="font-size:9.5px;letter-spacing:.16em;text-transform:uppercase;color:#8a8071;font-weight:700">Not yet verified</div>'
                    '<p style="margin:6px 0 0;font-size:13.5px;line-height:1.5;color:#17130d">'
                    'Nobody has read this watch&rsquo;s purchase page since it was indexed. '
                    'The availability below is what the source reported, not what we have confirmed.</p></div>')

    rows = "".join(
        f'<div {ROW}><span {KEY}>{k}</span><span {VAL}>{v}</span></div>'
        for k, v in [
            ("Availability", f'<span style="display:inline-block;width:7px;height:7px;border-radius:50%;'
                             f'vertical-align:1px;margin-right:7px;background:{dot}"></span>'
                             f'<b style="font-weight:650">{esc(w["tier"])}</b>'
                             f'<span style="color:#8a8071"> — {esc(tier_help.get(w["tier"], ""))}</span>'),
            ("Price", esc(w.get("price") or "—")),
            ("Edition", esc(w.get("edition") or "—")),
            ("Reference", esc(w.get("ref") or "—")),
            ("Released", f'{esc(w.get("date") or "—")} · {esc(w.get("cat") or "")}'),
            ("Specification", esc(w.get("specs") or "—")),
            ("Confidence", esc(str(w.get("conf") or "—")).capitalize()),
        ])

    cta_style = ("display:inline-block;font-size:13px;font-weight:600;letter-spacing:.02em;padding:11px 22px;"
                 "border:1px solid #17130d;text-decoration:none;"
                 + ("background:#17130d;color:#f4f1ea" if w.get("rank", 9) <= 2 else "background:transparent;color:#17130d"))

    ld = json.dumps(json_ld(w, url), ensure_ascii=False, separators=(",", ":"))

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(url)}">
<meta property="og:type" content="product">
<meta property="og:site_name" content="Watch Drop Index">
<meta property="og:title" content="{esc(name)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(url)}">
{og_img}
<meta name="theme-color" content="#f4f1ea">
<script type="application/ld+json">{ld}</script>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400..700;1,6..72,400..700&family=Archivo:ital,wght@0,400..700;1,400..700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="page.css">
</head><body>
<div style="min-height:100vh;background:#f4f1ea;color:#3a342b;font-family:'Archivo',sans-serif;font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased">
  <div style="max-width:900px;margin:0 auto;padding:0 30px">

    <div style="display:flex;justify-content:space-between;align-items:baseline;padding:11px 0 10px;border-bottom:1px solid #ddd6c8;font-size:10.5px;letter-spacing:.18em;text-transform:uppercase;color:#8a8071;font-weight:600">
      <span>watchdropindex.com</span><span>Register entry</span>
    </div>

    <header style="padding:34px 0 0;text-align:center">
      <a href="{CANON}/" style="text-decoration:none;display:inline-grid;justify-items:center;row-gap:0;line-height:1;font-family:'Newsreader',serif;font-size:26px;font-weight:600;color:#17130d">{lockup(26)}</a>
    </header>

    <main>
      <h1 style="font-family:'Newsreader',serif;font-size:34px;font-weight:600;line-height:1.15;color:#17130d;margin:30px 0 6px;letter-spacing:-.01em">{esc(name)}</h1>
      <p style="margin:0 0 26px;font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:#8a8071;font-weight:600">{esc(w.get("cat") or "")} · {esc(w.get("date") or "")}</p>

      <div data-mq="detail" style="display:grid;grid-template-columns:330px minmax(0,1fr);gap:32px;align-items:start">
        <div style="min-width:0">{fig}</div>
        <div style="min-width:0">
          <p style="font-family:'Newsreader',serif;font-size:18px;line-height:1.5;color:#17130d;margin:0 0 16px">{esc(w.get("desc") or "")}</p>
          {verified}
          <div style="border-top:2px solid #17130d;margin:0 0 18px">{rows}</div>
          <div style="display:flex;align-items:center;gap:18px;flex-wrap:wrap">
            <a href="{esc(w.get("buy") or "")}" target="_blank" rel="noopener" style="{cta_style}">{esc(w.get("buyLabel") or ("Buy" if w.get("rank", 9) <= 2 else "Where to find it"))}</a>
            <span style="font-size:12px;color:#8a8071">Reported by {esc(host_of(w.get("source")))}</span>
          </div>
        </div>
      </div>

      <!-- Back into the register, which is the experience. The deep link opens
           this entry in place. Internal, so it does not touch the one-outbound
           -click rule. -->
      <p style="margin:44px 0 0;padding-top:18px;border-top:1px solid #e9e4d8;font-size:13.5px">
        <a href="{CANON}/#{esc(w["id"])}" style="color:#8a5a2b;text-decoration:underline;text-underline-offset:3px">See this entry in the full register</a>
        <span style="color:#8a8071"> — every limited-run watch of 2026, with what it costs and whether you can still get one.</span>
      </p>
    </main>

    <footer style="margin:34px 0 0;padding:16px 0 40px;border-top:1px solid #e9e4d8;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#8a8071;text-align:center;font-weight:600">
      Watch Drop Index · updated {esc(meta.get("updated", ""))} · revision {esc(meta.get("revision", ""))}
      <div style="margin-top:9px;letter-spacing:.1em;font-size:10px;color:#a09786;text-transform:none">WATCH DROP INDEX™ is a trademark of Conn LLC. Photograph credited to its source; <a href="mailto:takedown@watchdropindex.com" style="color:#a09786">takedown@watchdropindex.com</a>.</div>
    </footer>

  </div>
</div>
</body></html>
"""


REDIRECT = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Moved — Watch Drop Index</title>
<link rel="canonical" href="{to}">
<meta http-equiv="refresh" content="0;url={to}">
<meta name="robots" content="noindex,follow">
</head><body><p>This entry has moved to <a href="{to}">{to}</a>.</p></body></html>
"""


# --- sitemap and feed --------------------------------------------------------
def sitemap(kept, updated):
    urls = [f"  <url><loc>{CANON}/</loc><lastmod>{updated}</lastmod>"
            f"<changefreq>daily</changefreq><priority>1.0</priority></url>"]
    for w in kept:
        urls.append(f"  <url><loc>{CANON}/{path_for(w)}</loc><lastmod>{updated}</lastmod>"
                    f"<changefreq>weekly</changefreq><priority>0.7</priority></url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(urls) + "\n</urlset>\n")


def feed_items(kept, limit=FEED_MAX):
    """What the register has DONE lately, newest first.

    An entry appears when something happened to it that a reader would care
    about: it was added, or it sold out. A recheck that changed nothing is not
    news and does not belong in a feed — it belongs in the week strip, which
    reports activity rather than events.
    """
    out = []
    for w in kept:
        if w.get("soldOutOn") and str(w["soldOutOn"])[:10] > str(w.get("addedOn") or "")[:10]:
            out.append((str(w["soldOutOn"])[:10], "sold out", w))
        elif w.get("addedOn"):
            out.append((str(w["addedOn"])[:10], "added", w))
    out.sort(key=lambda x: (x[0], x[2]["brand"]), reverse=True)
    return out[:limit]


def rfc822(d):
    import datetime as _dt
    try:
        return _dt.datetime.strptime(d, "%Y-%m-%d").strftime("%a, %d %b %Y 09:00:00 +0000")
    except ValueError:
        return d


def feed_xml(items, meta):
    parts = []
    for date, kind, w in items:
        url = f"{CANON}/{path_for(w)}"
        title = f"{w['brand']} {w['model']}" + (" — sold out" if kind == "sold out" else "")
        parts.append(
            f"    <item>\n"
            f"      <title>{esc(title)}</title>\n"
            f"      <link>{esc(url)}</link>\n"
            f"      <guid isPermaLink=\"false\">{esc(w['id'])}-{kind.replace(' ', '')}</guid>\n"
            f"      <pubDate>{rfc822(date)}</pubDate>\n"
            f"      <description>{esc(description(w))}</description>\n"
            f"    </item>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
            '  <channel>\n'
            '    <title>Watch Drop Index</title>\n'
            f'    <link>{CANON}/</link>\n'
            f'    <description>{esc(meta.get("tagline", ""))}</description>\n'
            '    <language>en</language>\n'
            f'    <lastBuildDate>{rfc822(str(meta.get("updated", "")))}</lastBuildDate>\n'
            f'    <atom:link href="{CANON}/feed.xml" rel="self" type="application/rss+xml"/>\n'
            + "\n".join(parts) + "\n  </channel>\n</rss>\n")


def feed_json(items, meta):
    return json.dumps({
        "version": "https://jsonfeed.org/version/1.1",
        "title": "Watch Drop Index",
        "home_page_url": CANON + "/",
        "feed_url": CANON + "/feed.json",
        "description": meta.get("tagline"),
        "items": [{
            "id": f"{w['id']}-{kind.replace(' ', '')}",
            "url": f"{CANON}/{path_for(w)}",
            "title": f"{w['brand']} {w['model']}" + (" — sold out" if kind == "sold out" else ""),
            "content_text": description(w),
            "date_published": f"{date}T09:00:00Z",
            **({"image": w["image"]} if w.get("image") else {}),
        } for date, kind, w in items],
    }, ensure_ascii=False, indent=1) + "\n"


# --- writing -----------------------------------------------------------------
def _write_if_changed(path, text):
    """Only touch a file whose bytes actually differ.

    The daily refresh commits whatever changed. If every page were rewritten on
    every run, each commit would carry 246 files and the diff would stop being
    able to tell anyone what the run did — which is the signal the whole record
    depends on.
    """
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            if fh.read() == text:
                return False
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return True


def write_all(root, meta, kept, css, lockup, tier_help):
    os.makedirs(os.path.join(root, PAGES_DIR), exist_ok=True)
    mpath = os.path.join(root, MANIFEST)
    old = {}
    if os.path.exists(mpath):
        with open(mpath, encoding="utf-8") as fh:
            old = json.load(fh)

    _write_if_changed(os.path.join(root, PAGES_DIR, "page.css"), css + PAGE_CSS_TAIL)

    current, changed = {}, 0
    for w in kept:
        rel = path_for(w)
        current[w["id"]] = rel
        if _write_if_changed(os.path.join(root, rel), page_html(w, meta, css, lockup, tier_help)):
            changed += 1

    # A path that used to serve an entry and no longer does is left behind
    # pointing at the replacement. Deleting it would throw away the ranking the
    # page exists to earn, and a 404 teaches a crawler the site is unreliable.
    live = set(current.values())
    retired = []
    for wid, rel in old.items():
        if rel not in live:
            to = f"{CANON}/{current[wid]}" if wid in current else f"{CANON}/"
            p = os.path.join(root, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            _write_if_changed(p, REDIRECT.format(to=to))
            retired.append(rel)

    _write_if_changed(mpath, json.dumps(current, indent=1, sort_keys=True) + "\n")

    updated = str(meta.get("updated", ""))
    _write_if_changed(os.path.join(root, "sitemap.xml"), sitemap(kept, updated))
    items = feed_items(kept)
    _write_if_changed(os.path.join(root, "feed.xml"), feed_xml(items, meta))
    _write_if_changed(os.path.join(root, "feed.json"), feed_json(items, meta))

    return {"pages": len(kept), "rewritten": changed, "retired": retired, "feed": len(items)}
