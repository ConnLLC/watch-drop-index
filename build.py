#!/usr/bin/env python3
"""
Build index.html for the Watch Drop Index.

Design direction: "The Catalogue" (design draft 1, approved 2026-08-04). The
markup and every inline style value below are ported verbatim from the design
reference; they are the spec, not suggestions. If you are restyling this, change
the reference first — Code makes no design decisions on this project.

The page reads data.json at runtime, so routine updates need NO rebuild — change
data.json, commit, done. Only run this when the template itself changes.

Two things in here are load-bearing and easy to break:

  * The #t-* / #c-* ids and the `.n` badge inside each [data-tier] button are a
    contract with the weekly refresh. Every figure on the page is re-read from
    data.json at load; without those hooks the site keeps advertising whatever
    the numbers were the day it was built.

  * The wordmark's clock is real. Hand positions come from negative CSS
    animation-delays computed against local time, and the letter spacing is
    aligned on measured glyph bearings, re-measured once webfonts land.
"""
import json, os, html
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "data.json")) as fh:
    payload = json.load(fh)

meta = payload["meta"]
items = payload["watches"]

TIERS = ["Buy online now", "Drop upcoming", "Retailer enquiry", "Waitlist or ballot",
         "AD or boutique", "In person only", "Gone"]
counts = Counter(i["tier"] for i in items)
buy_now = counts.get("Buy online now", 0)

# The comp carries these as style-hover / style-focus attributes, which are a
# design-tool construct rather than real HTML. Everything else stays inline,
# exactly as delivered.
CSS = """
body{margin:0;background:#f4f1ea;border-top:5px solid #17130d}
a{color:#8a5a2b}a:hover{color:#17130d}
::selection{background:#17130d;color:#f4f1ea}
input::placeholder{color:#a09786}
@keyframes wdi-spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
@keyframes wdi-badge-in{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
input[type=search]:focus{border-color:#17130d}
.wdi-btn:hover{border-color:#17130d;color:#17130d}
.wdi-row:hover{background:#ece7da}
.wdi-cta:hover{background:#8a5a2b;border-color:#8a5a2b;color:#f4f1ea}
.wdi-badge:hover{border-color:#17130d}
/* PROVISIONAL — pending design's ruling. The comp specifies no focus state, and
   the rows are div[role=button], so a keyboard user would otherwise have no way
   to see where they are. Uses only ink from the approved palette; no new value
   has been invented. */
.wdi-row:focus-visible{outline:1px solid #17130d;outline-offset:-1px;background:#ece7da}
"""

JS = r"""
(function () {
  var TIERS = ["Buy online now","Drop upcoming","Retailer enquiry","Waitlist or ballot","AD or boutique","In person only","Gone"];
  var HELP = __HELP__;
  var CONF = {
    high: "brand source, or several credible outlets agree",
    medium: "one credible source",
    low: "single aggregator, or an unresolved conflict"
  };

  var DOT = function (r) { return r === 0 ? "#1e6b41" : r <= 2 ? "#35597e" : r <= 5 ? "#97701c" : "#b0776b"; };
  var fmtC = function (n) { return n >= 1e6 ? "$" + (n / 1e6).toFixed(1) + "M" : n >= 1000 ? "$" + Math.round(n / 1000) + "k" : "$" + n; };
  var fmtFull = function (n) { return n >= 1e6 ? "$" + (n / 1e6).toFixed(2) + "M" : "$" + n.toLocaleString("en-US"); };
  var shortEd = function (s) {
    var t = String(s);
    if (/unconfirmed|not disclosed|not stated/i.test(t)) return "—";
    var nums = t.match(/\d[\d,]*/g);
    if (!nums) return t.length > 16 ? t.slice(0, 15) + "…" : t;
    if (/each|per (colour|color|version|metal|size|colourway)/i.test(t)) return nums[0] + " ea.";
    if (nums.length > 1) return nums.slice(0, 2).join(" + ");
    return nums[0];
  };
  var MONTH = {jan:1,feb:2,mar:3,apr:4,may:5,jun:6,jul:7,aug:8,sep:9,oct:10,nov:11,dec:12};
  var dkey = function (d) { var m = (d.date || "").toLowerCase().match(/(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)/); return m ? MONTH[m[1]] : 0; };

  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
    return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]; }); };
  var el = function (s) { return document.querySelector(s); };

  var BANDS = {
    "All": function () { return true; },
    "<$1k": function (d) { return d.priceNum != null && d.priceNum < 1000; },
    "$1k–5k": function (d) { return d.priceNum != null && d.priceNum >= 1000 && d.priceNum < 5000; },
    "$5k–15k": function (d) { return d.priceNum != null && d.priceNum >= 5000 && d.priceNum < 15000; },
    "$15k–50k": function (d) { return d.priceNum != null && d.priceNum >= 15000 && d.priceNum < 50000; },
    "$50k–250k": function (d) { return d.priceNum != null && d.priceNum >= 50000 && d.priceNum < 250000; },
    "$250k+": function (d) { return d.priceNum != null && d.priceNum >= 250000; },
    "No price": function (d) { return d.priceNum == null; }
  };

  var state = { q: "", tier: "All", cat: "All", band: "All", sort: "tier", open: {}, payload: null, showBadge: false };
  var DATA = [];

  /* ---- the clock -------------------------------------------------------- */
  /* Hand positions are pure CSS rotation; local time enters only as a negative
     animation-delay, i.e. "start as though you had already been running this
     long". Recomputed whenever a lockup is mounted — the corner badge mounts
     minutes after the masthead, and reusing the masthead's delay would leave
     its seconds hand visibly behind. */
  function clockDelays() {
    var t = new Date();
    var s = t.getSeconds() + t.getMilliseconds() / 1000;
    var m = t.getMinutes() * 60 + s;
    var h = (t.getHours() % 12) * 3600 + m;
    return { hour: (-h) + "s", min: (-m) + "s", sec: (-s) + "s" };
  }

  function applyDelays(root) {
    var d = clockDelays();
    var map = { hour: d.hour, min: d.min, sec: d.sec };
    ["hour", "min", "sec"].forEach(function (k) {
      var n = root.querySelector('[data-clock="' + k + '"]');
      if (n) n.style.animationDelay = map[k];
    });
  }

  /* ---- optical alignment of the wordmark -------------------------------- */
  /* The three lines are justified to one measure, so the outer letters have to
     hang on their ink edge rather than their advance width. Bearings come from
     the font itself via canvas metrics; W carries an extra optical hang. */
  var mctx = null;
  function applyBearings(root) {
    if (!root) return;
    var px = root.getAttribute("data-logo-px");
    if (!px) return;
    if (mctx === null) {
      try { mctx = document.createElement("canvas").getContext("2d"); } catch (e) { mctx = false; }
      if (!mctx || !mctx.measureText) mctx = false;
    }
    /* No canvas, or a build of it without text metrics: the wordmark keeps its
       default spacing rather than taking the whole page down with it. */
    if (mctx === false) return;
    mctx.font = "600 " + px + "px Newsreader";
    if (!("actualBoundingBoxLeft" in mctx.measureText("W"))) { mctx = false; return; }
    var mL = function (ch) { return mctx.measureText(ch).actualBoundingBoxLeft.toFixed(2) + "px"; };
    var mR = function (ch) { var mm = mctx.measureText(ch); return (mm.actualBoundingBoxRight - mm.width).toFixed(2) + "px"; };
    var set = function (key, prop, val) {
      var n = root.querySelector('[data-b="' + key + '"]');
      if (n) n.style[prop] = val;
    };
    set("wl", "marginLeft", "calc(" + mL("W") + " - .08em)");
    set("dl", "marginLeft", mL("D"));
    set("il", "marginLeft", mL("I"));
    set("hr", "marginRight", mR("H"));
    set("xr", "marginRight", mR("X"));
  }

  /* ---- rows ------------------------------------------------------------- */
  function rowHTML(d) {
    var open = !!state.open[d.id];
    var approx = d.priceNum != null && !/^\$/.test(String(d.price || ""));
    var na = d.priceNum == null;
    var dot = DOT(d.rank);
    var modelStyle = "font-family:'Newsreader',serif;font-size:16.5px;line-height:1.25;color:#17130d;min-width:0;" +
      (open ? "white-space:normal" : "overflow:hidden;text-overflow:ellipsis;white-space:nowrap");
    var priceStyle = "text-align:right;font-variant-numeric:tabular-nums;border-left:1px solid #e9e4d8;align-self:stretch;line-height:43px;" +
      (na ? "font-size:12px;color:#a09786;font-style:italic" : "font-size:13.5px;color:#17130d;font-weight:650");
    var priceRow = na ? "on request" : (approx ? "~" : "") + fmtFull(d.priceNum);

    var h = '<div data-id="' + esc(d.id) + '" style="border-bottom:1px solid ' + (open ? "#c9c0ad;background:#faf8f2" : "#e9e4d8") + '">' +
      '<div class="wdi-row" role="button" tabindex="0" aria-expanded="' + (open ? "true" : "false") + '" aria-controls="p-' + esc(d.id) + '"' +
      ' style="display:grid;grid-template-columns:16px minmax(0,1fr) 130px 112px 16px;gap:14px;align-items:center;min-height:43px;padding:0 4px 0 2px;cursor:pointer">' +
      '<span style="width:7px;height:7px;border-radius:50%;justify-self:center;background:' + dot + '" title="' + esc(d.tier) + '"></span>' +
      '<span style="min-width:0;display:flex;align-items:baseline;gap:11px">' +
      '<span style="font-size:10.5px;letter-spacing:.11em;text-transform:uppercase;color:#8a8071;font-weight:650;flex:none;max-width:175px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(d.brand) + '</span>' +
      '<span style="' + modelStyle + '">' + esc(d.model) + '</span></span>' +
      '<span title="' + esc(d.edition) + '" style="font-size:12.5px;color:#8a8071;text-align:right;font-variant-numeric:tabular-nums;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;border-left:1px solid #e9e4d8;align-self:stretch;line-height:43px">' + esc(shortEd(d.edition)) + '</span>' +
      '<span style="' + priceStyle + '">' + esc(priceRow) + '</span>' +
      '<span style="color:#a09786;font-size:10px;text-align:center">' + (open ? "▾" : "▸") + '</span>' +
      '</div>';

    h += '<div id="p-' + esc(d.id) + '">' + (open ? detailHTML(d, dot) : "") + '</div></div>';
    return h;
  }

  function detailHTML(d, dot) {
    var fig;
    if (d.image) {
      fig = '<figure style="margin:0">' +
        '<img src="' + esc(d.image) + '" alt="' + esc(d.brand + " " + d.model) + '" loading="lazy" style="width:100%;display:block;border:1px solid #ddd6c8;background:#ece7da">' +
        '<figcaption style="font-size:11px;color:#8a8071;margin-top:7px;letter-spacing:.04em">Photograph · ' + esc(d.imageCredit || "source") + '</figcaption></figure>';
    } else {
      var plate = (d.ref && d.ref !== "—") ? d.ref : String(d.brand || "").toUpperCase();
      fig = '<figure style="margin:0"><div style="border:1px solid #d5cdbc;background:#eeeadf;padding:9px">' +
        '<div style="border:1px solid #ddd6c8;padding:44px 20px;text-align:center;display:grid;gap:12px;justify-items:center">' +
        '<div style="font-size:9.5px;letter-spacing:.28em;text-transform:uppercase;color:#a09786;font-weight:600">Register entry</div>' +
        '<div style="font-size:15px;letter-spacing:.08em;color:#17130d;font-weight:600;font-variant-numeric:tabular-nums">' + esc(plate) + '</div>' +
        '<div style="width:26px;height:1px;background:#c9c0ad"></div>' +
        '<div style="font-family:\'Newsreader\',serif;font-style:italic;font-size:13.5px;color:#8a8071;line-height:1.5;max-width:200px">No photograph in the register yet — queued for the weekly pass.</div>' +
        '</div></div></figure>';
    }

    var th = 'style="text-align:left;font-weight:700;color:#8a8071;font-size:10px;letter-spacing:.15em;text-transform:uppercase;padding:7px 18px 7px 0;vertical-align:top;white-space:nowrap;width:1px"';
    var td = 'style="padding:7px 0;vertical-align:top;border-bottom:1px solid #e9e4d8;color:#17130d"';
    var tdNum = 'style="padding:7px 0;vertical-align:top;border-bottom:1px solid #e9e4d8;color:#17130d;font-variant-numeric:tabular-nums"';

    var rows =
      '<tr><th ' + th + '>Availability</th><td ' + td + '><span style="display:inline-block;width:7px;height:7px;border-radius:50%;vertical-align:1px;margin-right:7px;background:' + dot + '"></span><b style="font-weight:650">' + esc(d.tier) + '</b><span style="color:#8a8071"> — ' + esc(HELP[d.tier] || "") + '</span></td></tr>' +
      '<tr><th ' + th + '>Price</th><td ' + tdNum + '>' + esc(d.price) + '</td></tr>' +
      '<tr><th ' + th + '>Edition</th><td ' + td + '>' + esc(d.edition) + '</td></tr>' +
      '<tr><th ' + th + '>Reference</th><td style="padding:7px 0;vertical-align:top;border-bottom:1px solid #e9e4d8;color:#17130d;font-variant-numeric:tabular-nums;letter-spacing:.03em">' + esc(d.ref || "—") + '</td></tr>' +
      '<tr><th ' + th + '>Specification</th><td ' + td + '>' + esc(d.specs) + '</td></tr>' +
      '<tr><th ' + th + '>Released</th><td ' + td + '>' + esc(d.date) + ' · ' + esc(d.cat) + '</td></tr>' +
      '<tr><th ' + th + '>Confidence</th><td style="padding:7px 0;vertical-align:top;color:#17130d"><b style="font-weight:650;text-transform:capitalize">' + esc(d.conf) + '</b><span style="color:#8a8071"> — ' + esc(CONF[d.conf] || "") + '</span></td></tr>';

    var verified = d.verified
      ? '<p style="margin:0 0 16px;font-size:13px;line-height:1.5;color:#1e5c38"><span style="font-weight:700">✓ Stock checked ' + esc(d.verified.date) + '</span><span style="color:#3a342b"> — ' + esc(d.verified.note) + '</span></p>'
      : "";

    var tags = (d.tags || []).filter(function (t) { return t !== "Buy online"; });
    var tagLine = tags.length
      ? '<div style="font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:#8a8071;font-weight:600;margin:0 0 18px">' + esc(tags.join("  ·  ")) + '</div>'
      : "";

    var ctaStyle = "display:inline-block;font-size:13px;font-weight:600;letter-spacing:.02em;padding:11px 22px;border:1px solid #17130d;text-decoration:none;" +
      (d.rank <= 2 ? "background:#17130d;color:#f4f1ea" : "background:transparent;color:#17130d");
    var host = (function () { try { return new URL(d.source).hostname.replace(/^www\./, ""); } catch (e) { return "the source"; } })();

    return '<div style="display:grid;grid-template-columns:310px minmax(0,1fr);gap:34px;padding:10px 4px 34px 32px">' + fig +
      '<div style="min-width:0">' +
      '<p style="font-family:\'Newsreader\',serif;font-size:17.5px;line-height:1.55;color:#17130d;margin:0 0 14px">' + esc(d.desc) + '</p>' +
      verified +
      '<table style="width:100%;border-collapse:collapse;font-size:13.5px;margin:0 0 16px"><tbody>' + rows + '</tbody></table>' +
      tagLine +
      '<div style="display:flex;align-items:center;gap:18px;flex-wrap:wrap">' +
      '<a class="wdi-cta" href="' + esc(d.buy) + '" target="_blank" rel="noopener" style="' + ctaStyle + '">' + esc(d.buyLabel || (d.rank <= 2 ? "Buy" : "Where to find it")) + '</a>' +
      '<a href="' + esc(d.source) + '" target="_blank" rel="noopener" style="font-size:12px;color:#8a8071;text-decoration:underline;text-underline-offset:3px">Reported by ' + esc(host) + '</a>' +
      '</div></div></div>';
  }

  /* ---- filter chrome ---------------------------------------------------- */
  function btnStyle(on) {
    return "border:1px solid " + (on ? "#17130d;background:#17130d;color:#f4f1ea" : "#d5cdbc;background:transparent;color:#5c5546") +
      ";padding:5px 11px;font-size:12px;font-family:'Archivo',sans-serif;cursor:pointer;white-space:nowrap;border-radius:0";
  }

  function renderChrome(byTier) {
    var out = "";
    var list = [{ key: "All", label: "All", n: DATA.length }];
    TIERS.forEach(function (t) { if (byTier[t]) list.push({ key: t, label: t, n: byTier[t] }); });
    list.forEach(function (b) {
      var on = state.tier === b.key;
      var s = btnStyle(on);
      if (b.key === "Buy online now" && !on) s += ";color:#1e6b41;border-color:#b5c9b6";
      if (b.key === "Buy online now" && on) s += ";background:#1e6b41;border-color:#1e6b41";
      out += '<button class="wdi-btn" data-tier="' + esc(b.key) + '" style="' + s + '">' + esc(b.label) +
        '<span class="n" style="font-variant-numeric:tabular-nums;opacity:.55;margin-left:6px;font-size:11px">' + b.n + '</span></button>';
    });
    el("#tierBtns").innerHTML = out;

    out = "";
    Object.keys(BANDS).forEach(function (k) {
      out += '<button class="wdi-btn" data-band="' + esc(k) + '" style="' + btnStyle(state.band === k) + '">' + esc(k === "All" ? "Any" : k) + '</button>';
    });
    el("#bandBtns").innerHTML = out;

    var cats = [];
    DATA.forEach(function (d) { if (cats.indexOf(d.cat) < 0) cats.push(d.cat); });
    cats.sort();
    out = '<button class="wdi-btn" data-cat="All" style="' + btnStyle(state.cat === "All") + '">All segments</button>';
    cats.forEach(function (c) {
      out += '<button class="wdi-btn" data-cat="' + esc(c) + '" style="' + btnStyle(state.cat === c) + '">' + esc(c) + '</button>';
    });
    el("#catBtns").innerHTML = out;
  }

  /* ---- sections from the calendar --------------------------------------- */
  function renderSections(cal, byTier) {
    var out = "";
    TIERS.forEach(function (t) {
      if (!byTier[t]) return;
      out += '<div style="display:grid;grid-template-columns:180px 1fr;gap:18px;padding:10px 0;border-bottom:1px solid #e9e4d8;font-size:13.5px;color:#8a8071">' +
        '<b style="color:#17130d;font-weight:650;display:flex;align-items:center;gap:9px"><span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:' + DOT(TIERS.indexOf(t)) + '"></span>' + esc(t) + '</b>' +
        '<span>' + esc(HELP[t] || "") + '</span></div>';
    });
    el("#keyRows").innerHTML = out;

    var li = function (d, withWhere) {
      var detail = withWhere
        ? '<b style="color:#5c5546;font-weight:600">' + esc(d.where || "") + '</b> ' + esc(d.detail ? "— " + d.detail : "")
        : esc(d.detail || "");
      return '<li style="display:grid;grid-template-columns:168px 1fr;gap:20px;padding:14px 0;border-bottom:1px solid #e9e4d8">' +
        '<div style="font-size:13px;font-weight:650;color:#17130d;font-variant-numeric:tabular-nums">' + esc(d.date) + '</div>' +
        '<div><div style="font-weight:600;color:#17130d;margin-bottom:2px;font-size:14px">' + esc(d.what) + '</div>' +
        '<div style="font-size:13.5px;color:#8a8071;line-height:1.5">' + detail + '</div></div></li>';
    };
    el("#drops").innerHTML = (cal.drops || []).map(function (d) { return li(d, false); }).join("");
    el("#events").innerHTML = (cal.events || []).map(function (d) { return li(d, true); }).join("");

    var note = function (n) {
      return '<div style="margin-bottom:16px"><b style="color:#17130d;display:block;margin-bottom:2px;font-size:14px">' + esc(n.what) + '</b>' +
        '<p style="margin:0;font-size:13.5px;color:#8a8071;line-height:1.5">' + esc(n.detail) + '</p></div>';
    };
    el("#notHappening").innerHTML = (cal.notHappening || []).map(note).join("");
    el("#expected").innerHTML = (cal.expected || []).map(note).join("");
  }

  /* ---- main render ------------------------------------------------------ */
  function render() {
    var q = state.q.trim().toLowerCase();
    var rows = DATA.filter(function (d) {
      if (state.tier !== "All" && d.tier !== state.tier) return false;
      if (state.cat !== "All" && d.cat !== state.cat) return false;
      if (!(BANDS[state.band] || BANDS.All)(d)) return false;
      if (q) {
        var hay = (d.brand + " " + d.model + " " + d.ref + " " + d.desc + " " + d.specs + " " + (d.tags || []).join(" ") + " " + d.edition + " " + d.cat + " " + d.tier).toLowerCase();
        if (!q.split(/\s+/).every(function (tok) { return hay.indexOf(tok) >= 0; })) return false;
      }
      return true;
    });
    var sort = state.sort;
    if (sort === "tier") rows.sort(function (a, b) { return a.rank - b.rank || ((b.priceNum == null ? -1 : b.priceNum) - (a.priceNum == null ? -1 : a.priceNum)); });
    if (sort === "date") rows.sort(function (a, b) { return dkey(b) - dkey(a) || a.brand.localeCompare(b.brand); });
    if (sort === "brand") rows.sort(function (a, b) { return a.brand.localeCompare(b.brand) || a.model.localeCompare(b.model); });
    if (sort === "priceAsc") rows.sort(function (a, b) { return (a.priceNum == null ? 9e12 : a.priceNum) - (b.priceNum == null ? 9e12 : b.priceNum); });
    if (sort === "priceDesc") rows.sort(function (a, b) { return (b.priceNum == null ? -1 : b.priceNum) - (a.priceNum == null ? -1 : a.priceNum); });
    if (sort === "edition") rows.sort(function (a, b) { var n = function (s) { var m = String(s).replace(/,/g, "").match(/\d+/); return m ? +m[0] : 9e12; }; return n(a.edition) - n(b.edition); });

    var byTier = {};
    DATA.forEach(function (d) { byTier[d.tier] = (byTier[d.tier] || 0) + 1; });

    el("#loading").style.display = "none";
    el("#empty").style.display = rows.length ? "none" : "block";
    el("#list").innerHTML = rows.map(rowHTML).join("");

    var priced = rows.map(function (r) { return r.priceNum; }).filter(function (v) { return v != null; }).sort(function (a, b) { return a - b; });
    el("#tally").textContent = rows.length + " of " + DATA.length +
      (priced.length ? " · " + fmtC(priced[0]) + "–" + fmtC(priced[priced.length - 1]) + " · median " + fmtC(priced[Math.floor(priced.length / 2)]) : "");

    renderChrome(byTier);
    hydrate(byTier);
  }

  /* Every figure on the page is re-read from the data. Without this the weekly
     refresh would update data.json while the page kept quoting build-time
     numbers, and the freshness claim in the masthead would quietly go stale. */
  function hydrate(byTier) {
    var m = (state.payload && state.payload.meta) || {};
    var put = function (sel, v) { var n = el(sel); if (n) n.textContent = v; };
    put("#t-buy", byTier["Buy online now"] || 0);
    put("#t-total", DATA.length);
    put("#t-gone", byTier["Gone"] || 0);
    put("#t-brands", (function () { var s = {}; DATA.forEach(function (d) { s[d.brand] = 1; }); return Object.keys(s).length; })());
    put("#t-updated", m.updated || "");
    put("#c-rev", m.revision == null ? "" : m.revision);
    put("#c-imgs", DATA.filter(function (d) { return d.image; }).length);
    put("#c-total", DATA.length);
  }

  /* ---- corner badge ------------------------------------------------------ */
  /* Mounted and unmounted rather than shown and hidden, so the .6s rise replays
     each time it appears — and so its clock is re-synced on every mount. */
  function setBadge(on) {
    var host = el("#badgeHost");
    if (on && !host.firstChild) {
      var tpl = el("#badgeTpl");
      host.appendChild(tpl.content.cloneNode(true));
      var node = host.firstElementChild;
      applyBearings(node);
      applyDelays(node);
      node.addEventListener("click", function () { window.scrollTo({ top: 0, behavior: "smooth" }); });
      node.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); window.scrollTo({ top: 0, behavior: "smooth" }); }
      });
    } else if (!on && host.firstChild) {
      host.innerHTML = "";
    }
  }

  /* ---- deep link --------------------------------------------------------- */
  /* /#<id> opens that watch. Deliberately one page with anchors rather than a
     page per watch. */
  function openById(id, focus) {
    if (!DATA.some(function (x) { return x.id === id; })) return false;
    state.open[id] = true;
    render();
    var item = null, all = document.querySelectorAll("[data-id]");
    for (var i = 0; i < all.length; i++) if (all[i].getAttribute("data-id") === id) { item = all[i]; break; }
    if (item) {
      item.scrollIntoView({ block: "center" });
      if (focus) item.querySelector(".wdi-row").focus();
    }
    return true;
  }
  var dropHash = function () { history.replaceState(null, "", location.pathname + location.search); };

  function toggle(id) {
    if (state.open[id]) { delete state.open[id]; if (location.hash === "#" + id) dropHash(); }
    else { state.open[id] = true; history.replaceState(null, "", "#" + id); }
    render();
  }

  /* ---- boot -------------------------------------------------------------- */
  /* Idempotent on purpose. Everything here is a document-level listener, so a
     second call would double every one of them and each click would toggle a row
     open and straight back shut. A browser fires DOMContentLoaded once, but this
     is cheap insurance against anything that replays it. */
  var booted = false;
  function boot() {
    if (booted) return;
    booted = true;
    applyBearings(el("#lockup"));
    applyDelays(el("#lockup"));
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(function () {
        applyBearings(el("#lockup"));
        var b = el("#badgeHost").firstElementChild;
        if (b) applyBearings(b);
      });
    }

    window.addEventListener("scroll", function () {
      var v = window.scrollY > 430;
      if (v !== state.showBadge) { state.showBadge = v; setBadge(v); }
    }, { passive: true });

    el("#q").addEventListener("input", function (e) { state.q = e.target.value; render(); });
    el("#sort").addEventListener("change", function (e) { state.sort = e.target.value; render(); });
    el("#reset").addEventListener("click", function () {
      state.q = ""; state.tier = "All"; state.cat = "All"; state.band = "All"; state.sort = "tier";
      el("#q").value = ""; el("#sort").value = "tier";
      dropHash(); render();
    });

    document.addEventListener("click", function (e) {
      var b = e.target.closest("[data-tier],[data-band],[data-cat]");
      if (b) {
        if (b.hasAttribute("data-tier")) state.tier = b.getAttribute("data-tier");
        else if (b.hasAttribute("data-band")) state.band = b.getAttribute("data-band");
        else state.cat = b.getAttribute("data-cat");
        return render();
      }
      var row = e.target.closest(".wdi-row");
      if (row) toggle(row.parentNode.getAttribute("data-id"));
    });

    /* The comp makes rows a div[role=button], which — unlike a real button —
       does not activate on Enter or Space. Restored explicitly. */
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" && e.key !== " ") return;
      var row = e.target.closest && e.target.closest(".wdi-row");
      if (!row) return;
      e.preventDefault();
      toggle(row.parentNode.getAttribute("data-id"));
    });

    window.addEventListener("hashchange", function () {
      var id = location.hash.slice(1);
      if (id && !state.open[id]) openById(id, true);
    });

    fetch("data.json", { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (p) {
        state.payload = p;
        DATA = p.watches || [];
        render();
        renderSections(p.calendar || {}, (function () { var b = {}; DATA.forEach(function (d) { b[d.tier] = (b[d.tier] || 0) + 1; }); return b; })());
        var deep = location.hash.slice(1);
        if (deep) openById(deep, false);
      })
      .catch(function () {
        el("#loading").innerHTML = "Could not load <code>data.json</code>.<br><br>If you are opening this file directly from disk, browsers block the request. Run <code>python3 -m http.server</code> in this folder and open localhost:8000 instead.";
      });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
"""

TIER_HELP = {
    "Buy online now": "Add to cart on a brand webshop or an authorised online retailer.",
    "Drop upcoming": "Announced with a date. Nothing to buy yet.",
    "Retailer enquiry": "At retail, but not purchasable online — call or visit.",
    "Waitlist or ballot": "Entry by lottery, ballot or waitlist.",
    "AD or boutique": "Allocation only. Never sold online.",
    "In person only": "Sold at an event or a single physical location.",
    "Gone": "Sold out, closed or fully allocated.",
}


def lockup(px, ident):
    """The stacked wordmark. `px` drives the canvas measurement for the optical
    bearings; the clock markup differs slightly between the two sizes, exactly as
    the reference delivers it — the masthead hands carry paper keylines behind
    them, the badge hands use a box-shadow instead."""
    big = px == 46
    hand_hour = (
        '<span style="position:absolute;left:-.17em;bottom:-.05em;width:.34em;height:1.2em;background:#f4f1ea;clip-path:polygon(50% 0,100% 12%,74% 100%,26% 100%,0 12%)"></span>'
        '<span style="position:absolute;left:-.12em;bottom:0;width:.24em;height:1.13em;background:#17130d;clip-path:polygon(50% 0,100% 12%,74% 100%,26% 100%,0 12%)"></span>'
        if big else
        '<span style="position:absolute;left:-.12em;bottom:0;width:.24em;height:1.13em;background:#17130d;clip-path:polygon(50% 0,100% 12%,74% 100%,26% 100%,0 12%);box-shadow:0 0 0 1px #f4f1ea"></span>'
    )
    hand_min = (
        '<span style="position:absolute;left:-.15em;bottom:-.05em;width:.3em;height:1.6em;background:#f4f1ea;clip-path:polygon(50% 0,100% 10%,72% 100%,28% 100%,0 10%)"></span>'
        '<span style="position:absolute;left:-.1em;bottom:0;width:.2em;height:1.53em;background:#17130d;clip-path:polygon(50% 0,100% 10%,72% 100%,28% 100%,0 10%)"></span>'
        if big else
        '<span style="position:absolute;left:-.1em;bottom:0;width:.2em;height:1.53em;background:#17130d;clip-path:polygon(50% 0,100% 10%,72% 100%,28% 100%,0 10%);box-shadow:0 0 0 1px #f4f1ea"></span>'
    )
    hand_sec = (
        '<span style="position:absolute;left:-.06em;bottom:-.45em;width:.12em;height:2.02em;background:#f4f1ea"></span>'
        '<span style="position:absolute;left:-.025em;bottom:-.4em;width:.05em;height:1.92em;background:#8a5a2b"></span>'
        '<span style="position:absolute;left:-.09em;bottom:-.5em;width:.18em;height:.18em;border-radius:50%;background:#8a5a2b;box-shadow:0 0 0 1px #f4f1ea"></span>'
        if big else
        '<span style="position:absolute;left:-.025em;bottom:-.4em;width:.05em;height:1.92em;background:#8a5a2b"></span>'
    )
    return f'''<span style="display:block;width:3.9em"><span style="display:flex;justify-content:space-between;width:3.6em"><span data-b="wl">W</span><span>A</span><span>T</span><span>C</span><span data-b="hr">H</span></span></span>
      <span style="position:relative;display:block;width:3.9em;height:1em">
        <span style="position:absolute;left:0;top:0;display:flex;justify-content:space-between;align-items:center;width:2.85em;height:1em"><span data-b="dl">D</span><span>R</span><span>O</span><span>P</span></span>
        <span style="position:absolute;right:0;top:.17em;width:.6em;height:.6em;border-radius:50%;background:#8a5a2b"><span style="position:absolute;left:50%;top:50%;width:0;height:0">
          <span style="position:absolute;left:-1.7em;top:-1.7em;width:3.4em;height:3.4em;border:1px solid #17130d;border-radius:50%;opacity:.6;clip-path:polygon(50% -3%, 103% -3%, 103% 103%, 34% 103%, 34% 60%, 50% 60%)"></span>
          <span data-clock="hour" style="position:absolute;left:0;top:0;width:0;height:0;animation:wdi-spin 43200s linear infinite">{hand_hour}</span>
          <span data-clock="min" style="position:absolute;left:0;top:0;width:0;height:0;animation:wdi-spin 3600s linear infinite">{hand_min}</span>
          <span data-clock="sec" style="position:absolute;left:0;top:0;width:0;height:0;animation:wdi-spin 60s linear infinite">{hand_sec}</span>
          <span style="position:absolute;left:-.1em;top:-.1em;width:.2em;height:.2em;border-radius:50%;background:#17130d;box-shadow:0 0 0 1px #f4f1ea"></span>
        </span></span>
      </span>
      <span style="display:block;width:3.9em"><span style="display:flex;justify-content:space-between;width:3.6em"><span data-b="il">I</span><span>N</span><span>D</span><span>E</span><span data-b="xr">X</span></span></span>'''


dom = meta.get("domain", "")
SECTION_RULE = '<div style="width:26px;height:2px;background:#17130d;margin:{m}"></div>'
H2 = ('<h2 style="font-family:\'Newsreader\',serif;font-size:25px;font-weight:500;color:#17130d;'
      'margin:{m};letter-spacing:-.01em">{t}</h2>')

HTML = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Watch Drop Index — the limited-edition register</title>
<meta name="description" content="{html.escape(meta['tagline'])}">
<link rel="canonical" href="https://www.{dom}/">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Watch Drop Index">
<meta property="og:title" content="Watch Drop Index — the limited-edition register">
<meta property="og:description" content="{html.escape(meta['tagline'])}">
<meta property="og:url" content="https://www.{dom}/">
<meta name="twitter:card" content="summary">
<meta name="theme-color" content="#f4f1ea">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='6' fill='%2317130d'/%3E%3Ccircle cx='16' cy='17.5' r='8' fill='none' stroke='%238a5a2b' stroke-width='2'/%3E%3Cpath d='M16 13.5v4l2.8 2' stroke='%23f4f1ea' stroke-width='1.9' stroke-linecap='round' fill='none'/%3E%3Crect x='13.4' y='4' width='5.2' height='2.8' rx='1' fill='%238a5a2b'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400..700;1,6..72,400..700&family=Archivo:ital,wght@0,400..700;1,400..700&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head><body>
<div style="min-height:100vh;background:#f4f1ea;color:#3a342b;font-family:'Archivo',sans-serif;font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased">

  <div style="max-width:1140px;margin:0 auto;padding:0 30px">
    <div style="display:flex;justify-content:space-between;align-items:baseline;padding:11px 0 10px;border-bottom:1px solid #ddd6c8;font-size:10.5px;letter-spacing:.18em;text-transform:uppercase;color:#8a8071;font-weight:600">
      <span>{html.escape(dom)}</span>
      <span>Refreshed weekly · Mondays 09:00 UTC</span>
    </div>
  </div>

  <header style="max-width:1140px;margin:0 auto;padding:34px 30px 0;text-align:center">
    <div id="lockup" data-logo-px="46" aria-label="Watch Drop Index" style="display:grid;justify-items:center;row-gap:0;line-height:1;font-family:'Newsreader',serif;font-size:46px;font-weight:600;letter-spacing:0;color:#17130d;margin:0 auto;width:max-content">
      {lockup(46, "lockup")}
    </div>
    <div style="display:flex;align-items:center;gap:16px;margin:18px auto 0;max-width:720px">
      <div style="flex:1;height:1px;background:#c9c0ad"></div>
      <div style="font-size:11px;letter-spacing:.32em;text-transform:uppercase;color:#17130d;font-weight:600;white-space:nowrap">The Limited-Edition Register · 2026</div>
      <div style="flex:1;height:1px;background:#c9c0ad"></div>
    </div>
    <p style="font-family:'Newsreader',serif;font-style:italic;font-size:19px;line-height:1.5;color:#5c5546;margin:14px auto 0;white-space:nowrap">Track The Release &amp; Availability of Limited Edition Watches</p>
    <p style="margin:22px 0 0;padding:12px 0;border-top:1px solid #ddd6c8;border-bottom:1px solid #ddd6c8;font-size:13px;color:#8a8071;font-variant-numeric:tabular-nums">
      <b id="t-buy" style="color:#1e6b41;font-weight:700">{buy_now}</b> buyable online today
      <span style="margin:0 10px;color:#c9c0ad">·</span>
      <b id="t-total" style="color:#17130d;font-weight:700">{len(items)}</b> limited runs tracked
      <span style="margin:0 10px;color:#c9c0ad">·</span>
      <b id="t-gone" style="color:#17130d;font-weight:700">{counts.get('Gone', 0)}</b> confirmed gone
      <span style="margin:0 10px;color:#c9c0ad">·</span>
      <b id="t-brands" style="color:#17130d;font-weight:700">{meta['brands']}</b> brands
      <span style="margin:0 10px;color:#c9c0ad">·</span>
      updated <span id="t-updated" style="color:#17130d;font-weight:600">{html.escape(meta['updated'])}</span>
    </p>
  </header>

  <div style="position:sticky;top:0;z-index:30;background:#f4f1ea;border-bottom:2px solid #17130d">
    <div style="max-width:1140px;margin:0 auto;padding:12px 30px 13px">
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
        <input id="q" type="search" placeholder="Search brand, model, reference, movement…" style="flex:1;min-width:220px;padding:8px 12px;border:1px solid #ddd6c8;background:#fbf9f4;font-size:13.5px;font-family:'Archivo',sans-serif;color:#17130d;border-radius:0;outline:none">
        <select id="sort" style="padding:8px 10px;border:1px solid #ddd6c8;background:#fbf9f4;font-size:12.5px;font-family:'Archivo',sans-serif;color:#3a342b;border-radius:0">
          <option value="tier">Most obtainable first</option>
          <option value="date">Newest first</option>
          <option value="brand">Brand A–Z</option>
          <option value="priceAsc">Price: low to high</option>
          <option value="priceDesc">Price: high to low</option>
          <option value="edition">Smallest edition first</option>
        </select>
        <span id="tally" style="margin-left:auto;font-size:12px;color:#8a8071;font-variant-numeric:tabular-nums;white-space:nowrap"></span>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:10px">
        <span style="font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:#8a8071;font-weight:700;margin-right:4px">Availability</span>
        <span id="tierBtns" style="display:contents"></span>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:8px">
        <span style="font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:#8a8071;font-weight:700;margin-right:4px">Price</span>
        <span id="bandBtns" style="display:contents"></span>
        <span style="font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:#8a8071;font-weight:700;margin:0 4px 0 12px">Segment</span>
        <span id="catBtns" style="display:contents"></span>
        <button id="reset" style="border:none;background:none;padding:5px 10px;font-size:12px;font-family:'Archivo',sans-serif;color:#8a5a2b;cursor:pointer;text-decoration:underline;text-underline-offset:3px">Reset</button>
      </div>
    </div>
  </div>

  <main style="max-width:1140px;margin:0 auto;padding:0 30px">

    <div style="display:grid;grid-template-columns:16px minmax(0,1fr) 130px 112px 16px;gap:14px;padding:10px 4px 8px 2px;font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:#8a8071;font-weight:700">
      <span></span><span>Brand &amp; model</span><span style="text-align:right;border-left:1px solid #ddd6c8;align-self:stretch;display:flex;align-items:center;justify-content:flex-end">Edition</span><span style="text-align:right;border-left:1px solid #ddd6c8;align-self:stretch;display:flex;align-items:center;justify-content:flex-end">USD</span><span></span>
    </div>

    <div id="loading" style="padding:70px 0;text-align:center;font-family:'Newsreader',serif;font-style:italic;font-size:17px;color:#8a8071;border-top:2px solid #17130d">Loading the register…</div>
    <div id="empty" style="display:none;padding:70px 0;text-align:center;font-family:'Newsreader',serif;font-style:italic;font-size:17px;color:#8a8071;border-top:2px solid #17130d">Nothing matches those filters.</div>

    <div id="list" style="border-top:2px solid #17130d"></div>

    <section>
      {SECTION_RULE.format(m='64px 0 0')}
      {H2.format(m='12px 0 4px', t='Reading the availability marks')}
      <p style="color:#8a8071;font-size:13.5px;margin:0 0 16px;max-width:720px">Assigned from how the brand actually sells the watch — not a guess at demand.</p>
      <div id="keyRows" style="border-top:1px solid #ddd6c8"></div>
    </section>

    <section>
      {SECTION_RULE.format(m='56px 0 0')}
      {H2.format(m='12px 0 4px', t='Dated opportunities')}
      <p style="color:#8a8071;font-size:13.5px;margin:0 0 16px">Drops, order windows and deadlines with a date attached.</p>
      <ul id="drops" style="list-style:none;padding:0;margin:0;border-top:1px solid #ddd6c8"></ul>
    </section>

    <section>
      {SECTION_RULE.format(m='56px 0 0')}
      {H2.format(m='12px 0 16px', t='Where the rest of 2026 gets announced')}
      <ul id="events" style="list-style:none;padding:0;margin:0;border-top:1px solid #ddd6c8"></ul>
    </section>

    <section style="display:grid;grid-template-columns:1fr 1fr;gap:44px">
      <div>
        {SECTION_RULE.format(m='56px 0 0')}
        {H2.format(m='12px 0 16px', t='Not happening in 2026')}
        <div id="notHappening"></div>
      </div>
      <div>
        {SECTION_RULE.format(m='56px 0 0')}
        {H2.format(m='12px 0 16px', t='Expected but unannounced')}
        <div id="expected"></div>
      </div>
    </section>

    <footer style="margin-top:64px;border-top:2px solid #17130d;padding:26px 0 80px;font-size:13.5px;color:#8a8071">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:44px">
        <div>
          <h3 style="font-family:'Newsreader',serif;font-size:17px;color:#17130d;margin:0 0 10px;font-weight:600">Method</h3>
          <ul style="margin:0;padding-left:18px;line-height:1.55">
            <li style="margin-bottom:6px"><b style="color:#17130d;font-weight:600">Limited editions only.</b> Numbered runs, capped annual production, ballot pieces and single-retailer exclusives. Unnumbered special editions are included but labelled as such.</li>
            <li style="margin-bottom:6px"><b style="color:#17130d;font-weight:600">Confidence is stated, not implied.</b> High means a brand source or several credible outlets agree; medium means one credible source; low means a single aggregator or an unresolved conflict.</li>
            <li style="margin-bottom:6px"><b style="color:#17130d;font-weight:600">Stock status is only claimed where checked.</b> Entries with a green check had their purchase page read on that date. Everything else is classified by how the brand distributes.</li>
            <li style="margin-bottom:6px"><b style="color:#17130d;font-weight:600">Converted prices are marked with a tilde.</b> Sorting uses the USD estimate, so ranking near a band boundary is approximate.</li>
            <li style="margin-bottom:6px"><b style="color:#17130d;font-weight:600">Photographs are drawn from the reporting outlet</b> that covered each release, credited beneath the image, and used to identify the watch being indexed.</li>
          </ul>
        </div>
        <div>
          <h3 style="font-family:'Newsreader',serif;font-size:17px;color:#17130d;margin:0 0 10px;font-weight:600">Known gaps</h3>
          <ul style="margin:0;padding-left:18px;line-height:1.55">
            <li style="margin-bottom:6px">Grand Seiko and Seiko's H2 2026 announcements are not yet captured.</li>
            <li style="margin-bottom:6px">F.P. Journe surfaced no 2026 limited edition across four independent sources — likely a coverage gap.</li>
            <li style="margin-bottom:6px">Casio rarely discloses G-Shock edition sizes; only the MR-G Phoenix carries a confirmed number.</li>
            <li style="margin-bottom:6px">Minase, Knot, Zelos, Certina, Mido, Rado, Nomos and Zodiac are not researched to completion.</li>
            <li style="margin-bottom:6px">Rolex issued no numbered limited editions in 2026.</li>
            <li style="margin-bottom:6px">Open price conflicts: Patek 5810/1G-001, AP × AMBUSH, Doxa × Hodinkee edition size.</li>
          </ul>
        </div>
      </div>
      <p style="margin-top:30px;padding-top:14px;border-top:1px solid #e9e4d8;font-size:11px;letter-spacing:.14em;text-transform:uppercase;font-weight:600;text-align:center;color:#8a8071">Watch Drop Index · {html.escape(dom)} · revision <span id="c-rev">{meta['revision']}</span> · <span id="c-imgs">{meta.get('imagesResolved', 0)}</span> of <span id="c-total">{len(items)}</span> photographs resolved · every entry links to the source it came from</p>
    </footer>

  </main>

  <div id="badgeHost"></div>
  <template id="badgeTpl"><div class="wdi-badge" data-logo-px="20" role="button" tabindex="0" title="Back to top" style="position:fixed;right:24px;bottom:22px;z-index:40;display:grid;justify-items:center;row-gap:0;line-height:1;font-family:'Newsreader',serif;font-size:20px;font-weight:600;letter-spacing:0;color:#17130d;cursor:pointer;background:#f4f1ea;border:1px solid #c9c0ad;padding:16px 44px 16px 18px;box-shadow:0 6px 26px rgba(23,19,13,.28);animation:wdi-badge-in .6s cubic-bezier(.22,.61,.36,1) both">{lockup(20, "badge")}</div></template>
</div>
<script>{JS.replace('__HELP__', json.dumps(TIER_HELP, ensure_ascii=False))}</script>
</body></html>
"""

with open(os.path.join(HERE, "index.html"), "w") as fh:
    fh.write(HTML)
print(f"built index.html — template only; {len(items)} entries load from data.json at runtime")
print(f"  buyable online: {buy_now} · photos: {meta.get('imagesResolved',0)} · size: {len(HTML)//1024} KB")
