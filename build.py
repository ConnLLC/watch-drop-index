#!/usr/bin/env python3
"""
Build index.html for the Watch Drop Index.

Design direction: "The Catalogue" — v1 LOCKED (desktop + mobile), design brief of
2026-08-04 05:53 UTC. The markup and every inline style value below are ported
verbatim from the design reference; they are the spec, not suggestions. If you
are restyling this, change the reference first — Code makes no design decisions
on this project. Anything ambiguous goes to Design on the RELAY thread.

The page reads data.json at runtime, so routine updates need NO rebuild — change
data.json, commit, done. Only run this when the template itself changes.

Four things in here are load-bearing and easy to break:

  * The #t-* / #c-* ids and the `.n` badge inside each [data-tier] button are a
    contract with the weekly refresh. Every figure on the page is re-read from
    data.json at load; without those hooks the site keeps advertising whatever
    the numbers were the day it was built.

  * The data-mq attributes are the entire mobile pass. The @media block keys off
    them and nothing else, so renaming one silently drops a rule at ≤720px while
    desktop stays perfect.

  * The wordmark's clock is real. Hand positions come from negative CSS
    animation-delays computed against local time, and the letter spacing is
    aligned on measured glyph bearings, re-measured once webfonts land.

  * Lower sections are margined by a computed symmetric pad, not a max-width.
    It reads documentElement.clientWidth — never 100vw, which includes the
    scrollbar and would break the alignment against the stats column.
"""
import json, os, html, re
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "data.json")) as fh:
    payload = json.load(fh)

meta = payload["meta"]
items = payload["watches"]

# Every entry stays in the register and in every derived figure — nothing is
# deleted (design's amended ruling, 2026-08-04 06:08). Only the FILTER BUTTONS
# are narrowed to the four actionable tiers; the other three are still listed,
# searchable, sorted into rank position, and explained in the availability key.
# TIERS is in sort order, which is not the same as rank order.
TIERS = ["Buy online now", "Buy at retailer", "Drop upcoming", "Waitlist or ballot",
         "AD or boutique", "In person only", "Gone"]
FILTERABLE = ["Buy online now", "Buy at retailer", "Drop upcoming", "Gone"]

# SCOPE (Lowell, 2026-08-04): a production cap is not a limited edition. Six
# entries are filtered OUT of the register at the display layer — data.json keeps
# all 252, so an entry reappears by itself the week its edition is confirmed.
# The same three patterns live in the runtime script; they are the definition of
# what this site indexes, and the two copies must not drift.
NOT_LE = [re.compile(r"not formally limited", re.I),
          re.compile(r"^capped", re.I),
          re.compile(r"annually", re.I)]


def in_scope(entry):
    edition = str(entry.get("edition", "")).strip()
    return not any(rx.search(edition) for rx in NOT_LE)


_kept = [dict(i, tier="Buy at retailer", rank=3) if i["tier"] == "Retailer enquiry" else i
         for i in items if in_scope(i)]
counts = Counter(i["tier"] for i in _kept)

# The comp carries these as style-hover / style-focus attributes, which are a
# design-tool construct rather than real HTML. The @media block and the keyframes
# are lifted verbatim from the reference helmet. Everything else stays inline,
# exactly as delivered.
CSS = """
body{margin:0;background:#f4f1ea;border-top:5px solid #17130d}
a{color:#8a5a2b}a:hover{color:#17130d}
::selection{background:#17130d;color:#f4f1ea}
input::placeholder{color:#a09786}
@keyframes wdi-spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
@keyframes wdi-badge-in{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
@keyframes wdi-dateflip{0%{transform:translateY(0)}42%{transform:translateY(-140%)}42.01%{transform:translateY(140%)}100%{transform:translateY(0)}}
input[type=search]:focus{border-color:#17130d}
.wdi-btn:hover{border-color:#17130d;color:#17130d}
.wdi-row:hover{background:#ece7da}
.wdi-cta:hover{background:#8a5a2b;border-color:#8a5a2b;color:#f4f1ea}
.wdi-badge:hover{border-color:#17130d}
.wdi-sort:hover{color:#17130d}
.wdi-ghost:hover{background:#17130d;color:#f4f1ea}
/* PROVISIONAL — pending design's ruling, flagged twice on the RELAY thread. The
   comp specifies no focus state, and the rows are div[role=button], so a
   keyboard user would otherwise have no way to see where they are. Uses only
   ink from the approved palette; no new value has been invented. */
.wdi-row:focus-visible{outline:1px solid #17130d;outline-offset:-1px;background:#ece7da}
/* Lifted verbatim from the v1.3 reference helmet (design, 2026-08-04 18:12).
   The stat ledger being hidden rather than removed is now design's own rule —
   #t-buy/#t-total/#t-gone/#t-brands/#t-updated are the weekly refresh's
   hydration contract and have to stay in the DOM to be rewritten.
   Row grids key off nth-child, so the six children of [data-mq="cols"] are
   positional: dot, brand+model, Released, Edition, USD, chevron. Reordering
   them silently rearranges the phone layout. */
@media (max-width:720px){
  [data-mq="utilwrap"]{padding:0 20px !important}
  [data-mq="util"]{gap:12px}
  [data-mq="utc"]{display:none !important}
  [data-mq="hdr"]{padding:26px 20px 0 !important}
  [data-mq="hgrid"]{display:block !important}
  [data-mq="hleft"]{max-width:none !important}
  [data-mq="hdiv"]{display:none !important}
  [data-mq="hstats"]{display:none !important}
  [data-mq="lockup"]{font-size:34px !important}
  [data-mq="wide"]{width:100% !important;margin-left:0 !important;margin-right:0 !important;padding-left:0 !important}
  div[data-mq="wide"]{margin-top:16px !important}
  [data-mq="fwrap"]{position:static !important}
  [data-mq="fbar"]{padding:10px 20px 12px !important;display:flex;flex-wrap:wrap;gap:6px;align-items:center}
  [data-mq="fbar"] > div{display:contents}
  [data-mq="flabel"]{display:none !important}
  [data-mq="fbar"] button{padding:7px 10px !important;font-size:11.5px !important}
  [data-mq="pband"],[data-mq="preset"]{display:none !important}
  [data-mq="search"]{flex:1 1 140px;min-width:140px;width:auto !important;margin:0 !important}
  [data-mq="sort"]{flex:1 1 104px;min-width:104px;max-width:170px;width:auto !important;margin:0 !important}
  [data-mq="main"]{padding:0 20px !important}
  [data-mq="colh"]{grid-template-columns:16px minmax(0,1fr) 96px !important;gap:12px !important}
  [data-mq="colh"] > *:nth-child(3), [data-mq="colh"] > *:nth-child(4), [data-mq="colh"] > *:nth-child(6){display:none !important}
  [data-mq="colh"] > *:nth-child(2) > span:first-child{width:auto !important}
  [data-mq="cols"]{grid-template-columns:16px minmax(0,1fr) 96px !important;grid-template-rows:auto auto;gap:1px 12px !important;min-height:38px !important;padding:8px 4px 8px 2px !important}
  [data-mq="cols"] > *:nth-child(1){grid-row:1/3}
  [data-mq="cols"] > *:nth-child(2){grid-row:1/3;flex-direction:column;align-items:flex-start;gap:1px !important;line-height:1.35 !important}
  [data-mq="cols"] > *:nth-child(5){line-height:1.35 !important}
  [data-mq="cols"] > *:nth-child(2) > span{width:auto !important;max-width:100% !important;overflow:hidden !important;text-overflow:ellipsis !important;white-space:nowrap !important;box-sizing:border-box}
  [data-mq="cols"] > *:nth-child(2) > span:last-child{font-size:15.5px !important}
  [data-mq="cols"] > *:nth-child(4){display:none !important}
  [data-mq="cols"] > *:nth-child(3){display:flex !important;grid-column:3;grid-row:2;border-left:none !important;line-height:1.3 !important;font-size:11px !important;align-self:center;justify-content:flex-end}
  [data-mq="cols"] > *:nth-child(5){grid-column:3;grid-row:1;align-self:center}
  [data-mq="cols"] > *:nth-child(6){display:none !important}
  [data-mq="detail"]{display:block !important;padding:8px 2px 22px 16px !important}
  [data-mq="detail"] > div:first-child{margin-bottom:18px}
  [data-mq="two"]{grid-template-columns:1fr !important}
  [data-mq="row2"]{grid-template-columns:1fr !important;gap:2px !important}
  [data-mq="badge"]{font-size:16px !important;right:14px !important;bottom:14px !important;padding:12px 38px 12px 14px !important}
}

/* ---- the tablet band ---------------------------------------------------
   Lowell, on an iPad, 2026-08-05: the search field wraps onto a line of its
   own. It does, and the cause is arithmetic rather than taste. The filter row
   is "Availability:" (a fixed 112px gutter) + five tier buttons + a 260px
   search box. Around 820px of viewport there is roughly 100px left for a box
   asking for 260, and because the row is flex-wrap the browser decides where
   items go from their BASE width — it wraps the search rather than shrinking
   it, so no amount of flex-shrink alone fixes this.

   Between 721 and 1100 the layout is therefore given the two concessions the
   phone layout already makes, rather than new ones invented here: the labels
   go (the buttons say what they filter) and the buttons tighten. That buys
   enough room for the search to hold the line at a usable size.

   NOT A DESIGN RULING — flagged to design. This is the plain mechanical fix
   for a defect on a real device, reusing decisions design already made one
   breakpoint down. If they want a different treatment for tablets, this is
   theirs to replace.

   Widths below are unverifiable from here: neither Code nor design has a
   browser at this size, so the numbers are reasoned from the type metrics, not
   measured. Lowell's iPad is the only instrument that can confirm it. */
@media (min-width:721px) and (max-width:1100px){
  [data-mq="flabel"]{display:none !important}
  [data-mq="fbar"] button{padding:5px 9px !important;font-size:11.5px !important}
  /* The basis is what matters: a wrapping flex row decides placement from the
     BASE width, not the shrunk one, which is why the 260px box jumps to its own
     line instead of narrowing. 170 leaves comfortable slack against the width
     estimate above — the point is that it cannot wrap, not that it is exactly
     as wide as it could be. margin-left:auto is kept so it stays right-aligned
     as on desktop; growing it to fill instead would need that margin removed
     and would strand the field mid-row at the top of the band. */
  [data-mq="search"]{width:auto !important;flex:0 1 170px;min-width:140px;margin-left:auto !important}
  [data-mq="sort"]{width:auto !important;flex:0 1 130px;min-width:110px}
}
"""

JS = r"""
(function () {
  /* Sort order, which is deliberately not rank order — "Buy at retailer" is
     rank 3 but sorts second. */
  var TIERS = ["Buy online now","Buy at retailer","Drop upcoming","Waitlist or ballot","AD or boutique","In person only","Gone"];
  /* Only these get a filter button. The other three still appear in the list,
     in search and in the availability key — they just have no chip of their own. */
  var FILTERABLE = ["Buy online now","Buy at retailer","Drop upcoming","Gone"];
  var HELP = __HELP__;
  /* Brand column shows the watch MANUFACTURER only. Default: the first name in a
     collab (the maker-first convention); MAKER overrides the four cases where the
     maker is listed second. The full collab string stays in the data, in the
     search hay and on the register plate. */
  var MAKER = __MAKER__;
  /* Editorial short titles for the ledger. Keep family + edition identity, drop
     calibre numbers, spec words, mm sizes, references and variant lists; ≤38
     characters. Every pair is an editorial decision, not a truncation — these
     come from design and are never regenerated mechanically. Entries added by
     the weekly job carry displayBrand/displayModel in data.json instead, and
     those win over these maps. */
  var SHORT = __SHORT__;
  var maker = function (b) { return MAKER[b] || (/[×\/]/.test(b) ? b.split(/\s*[×\/]\s*/)[0].trim() : b); };
  var shortModel = function (m) { return SHORT[m] || m; };
  var CONF = {
    high: "brand source, or several credible outlets agree",
    medium: "one credible source",
    low: "single aggregator, or an unresolved conflict"
  };

  var DOT = function (r) { return r === 0 ? "#1e6b41" : r <= 2 ? "#35597e" : r <= 5 ? "#97701c" : "#b0776b"; };
  var fmtFull = function (n) { return n >= 1e6 ? "$" + (n / 1e6).toFixed(2) + "M" : "$" + n.toLocaleString("en-US"); };
  /* The Edition column is a number or "N/A" — never prose. Status words beat
     digits, so "Unconfirmed, likely 100" reads N/A rather than 100. The full
     edition text stays on hover and in the expanded frame. */
  var shortEd = function (s) {
    var t = String(s || "").trim();
    if (/unconfirmed|not stated|not disclosed|not numbered|special edition|size not stated/i.test(t)) return "N/A";
    if (/^unique piece/i.test(t)) return "1";
    var tot = t.match(/([\d,]+)\s*total/i); if (tot) return tot[1];
    var nums = (t.match(/\d[\d,]*/g) || []).map(function (x) { return +x.replace(/,/g, ""); });
    if (!nums.length) return "N/A";
    if (/each/i.test(t) || /–|—|-\s*\d/.test(t.replace(/[\d,]+/, ""))) return /each/i.test(t) ? "N/A" : nums[0].toLocaleString("en-US");
    if (nums.length > 1 && /\//.test(t)) return nums.reduce(function (a, b) { return a + b; }, 0).toLocaleString("en-US");
    return nums[0].toLocaleString("en-US");
  };
  var edN = function (e) { var s = shortEd(e); return s === "N/A" ? 9e12 : +s.replace(/,/g, ""); };

  var MONTH = {jan:1,feb:2,mar:3,apr:4,may:5,jun:6,jul:7,aug:8,sep:9,oct:10,nov:11,dec:12};
  /* Auction-house date grammar: day-first, no ordinals, no commas, no slashes.
     May/June/July run in full, everything else is three letters — except Sept. */
  var AB = {jan:"Jan",feb:"Feb",mar:"Mar",apr:"Apr",may:"May",jun:"June",jul:"July",aug:"Aug",sep:"Sept",oct:"Oct",nov:"Nov",dec:"Dec"};
  /* One parser, used by BOTH the Released cell and its sort key, so the column
     can never sort by a date it isn't showing. It prefers the month anchored to
     2026 over an announce date: "Announced Dec 2025 for the Feb 2026 lunar year"
     is a February release, and sorting it under December is the regression this
     exists to prevent. */
  var datePick = function (ds) {
    ds = (ds || "").trim(); if (!ds) return null;
    var re = /(?:(\d{1,2})\s+)?(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?(?:\s+(\d{4}))?/gi;
    var ms = [], m; while ((m = re.exec(ds))) ms.push({ day: m[1] ? +m[1] : 0, mon: m[2], yr: m[3] });
    var find = function (f) { for (var i = 0; i < ms.length; i++) if (f(ms[i])) return ms[i]; return null; };
    return find(function (x) { return x.yr === "2026"; }) || find(function (x) { return !x.yr; }) || ms[0] || null;
  };
  var dkey = function (d) { var p = datePick(d.date); return p ? MONTH[p.mon.toLowerCase().slice(0, 3)] * 40 + p.day : 0; };
  /* The year always comes from the data string — never assumed to be 2026. */
  var fmtDate = function (ds) {
    ds = (ds || "").trim();
    if (!ds) return "—";
    var p = datePick(ds);
    var yr = (p && p.yr) || ((ds.match(/\b(20\d\d)\b/) || [])[1]) || "";
    if (p) {
      var monYr = AB[p.mon.toLowerCase().slice(0, 3)] + (yr ? " " + yr : "");
      return p.day ? p.day + " " + monYr : monYr;
    }
    var q = ds.match(/\bQ([1-4])\b/i);
    return q ? "Q" + q[1] + (yr ? " " + yr : "") : (yr || "TBC");
  };

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

  var state = { q: "", tier: "All", cat: "All", band: "All", sort: "tier", open: {},
                payload: null, showBadge: false, admin: false, editId: null, descEditId: null,
                /* Admin write path. `gh` holds the file as it was READ from the
                   GitHub API — its sha is the optimistic lock, so it is never
                   updated except by a successful load or a successful write. */
                gh: null, adminEdit: null, adminForm: {}, adminMsg: null };
  var DATA = [];

  /* Build flag, shipped ON: the formatted date sits in a beveled aperture that
     echoes the logo's 3-o'clock window. TBC and — stay outside it, because an
     empty date window betrays the metaphor. */
  var DATE_WIN = __DATEWIN__;

  /* ---- editor's overrides ------------------------------------------------- */
  /* Lowell's hand corrections, this device only, exported as JSON for the weekly
     job to fold into data.json. They outrank both the data's display fields and
     the baked-in maps. */
  function ovAll() { try { return JSON.parse(localStorage.getItem("wdi-admin-ov") || "{}"); } catch (e) { return {}; } }
  function ovSave(o) { try { localStorage.setItem("wdi-admin-ov", JSON.stringify(o)); } catch (e) {} render(); }
  /* Precedence, highest first: this device's edit, the field the weekly job
     wrote, then design's map. */
  function shownBrand(d) { var ov = ovAll()[d.id] || {}; return ov.displayBrand || d.displayBrand || maker(d.brand); }
  function shownModel(d) { var ov = ovAll()[d.id] || {}; return ov.displayModel || d.displayModel || shortModel(d.model); }

  /* ---- admin: writing to the register ------------------------------------ */
  /* Three capabilities — edit an entry, set or clear its photograph, add one —
     and all three are the same operation underneath: a JSON edit plus a commit.
     So they are built on the gate that already exists rather than on a new
     surface, and on the one write path GitHub gives a static site.

     THE CREDENTIAL. This page is static and public, so any secret the page needs
     is a published secret — there is no server to keep one behind. Lowell
     therefore PASTES a fine-grained PAT to start an editing session and it lives
     in sessionStorage for exactly that tab: never localStorage, never the repo,
     never the HTML, never a build artifact, never a URL, never an error message,
     never a log line. It dies when the tab closes. The blast radius if it leaks
     is one public hobby repo, which is proportionate; anything that widened it
     would not be. Scope it fine-grained → this repository only → Contents: Read
     and write → nothing else → 90 days. See README.

     With no token the panel is READ-ONLY and says so. It does not silently
     no-op: a save button that looks armed and does nothing is worse than one
     that is visibly disabled, because the edit appears to have been made. */
  var GH_REPO = "ConnLLC/watch-drop-index";
  var GH_PATH = "data.json";
  var GH_TOKEN_KEY = "wdi-gh-pat";

  /* The fields a person may edit here. Deliberately not "every key": imageProbe,
     imageCheck, deadImages and buyCheck are bookkeeping the refresh stages need
     in order to stay correct, and freezing one by hand would break the
     loop-avoidance it exists for. Mirrors MANUAL_FIELDS in scripts/refresh.py. */
  var ADMIN_FIELDS = ["brand", "model", "ref", "cat", "edition", "price", "date",
                      "status", "buy", "buyLabel", "source", "conf", "desc", "specs"];
  /* An entry with no price is fine — "Unconfirmed" is a legitimate value and the
     register is built to carry it. An entry with no SOURCE is not: without
     provenance it cannot have an honest confidence rating, which is the one
     thing separating this from an aggregator. */
  var ADMIN_REQUIRED = ["brand", "model", "source", "buy", "conf"];

  function ghToken() {
    try { return sessionStorage.getItem(GH_TOKEN_KEY) || ""; } catch (e) { return ""; }
  }
  function ghSetToken(t) {
    try {
      if (t) sessionStorage.setItem(GH_TOKEN_KEY, t);
      else sessionStorage.removeItem(GH_TOKEN_KEY);
    } catch (e) {}
  }

  /* btoa() throws on anything outside Latin-1 and this register is full of
     accented brand names, so the JSON goes through TextEncoder first. Getting
     this wrong fails on exactly the entries most worth editing. */
  function b64encode(str) {
    var bytes = new TextEncoder().encode(str), bin = "";
    for (var i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return btoa(bin);
  }
  function b64decode(b64) {
    var bin = atob(b64.replace(/\s/g, "")), bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new TextDecoder().decode(bytes);
  }

  function ghHeaders() {
    return { Authorization: "Bearer " + ghToken(), Accept: "application/vnd.github+json" };
  }

  /* Errors are deliberately rewritten rather than passed through. A GitHub error
     body can echo the request, and the request carries the token. */
  function ghError(res) {
    if (res.status === 401 || res.status === 403) {
      return "GitHub refused the token (" + res.status + "). It may be expired, or "
           + "scoped without Contents: Read and write on this repository.";
    }
    if (res.status === 404) {
      return "GitHub returned 404. A fine-grained token without access to this "
           + "repository looks identical to the repository not existing.";
    }
    if (res.status === 409) return "Conflict — the file moved underneath this edit.";
    return "GitHub returned " + res.status + ".";
  }

  function ghLoad() {
    return fetch("https://api.github.com/repos/" + GH_REPO + "/contents/" + GH_PATH
                 + "?ref=main&t=" + Date.now(), { headers: ghHeaders(), cache: "no-store" })
      .then(function (res) {
        if (!res.ok) throw new Error(ghError(res));
        return res.json();
      })
      .then(function (j) { return { sha: j.sha, payload: JSON.parse(b64decode(j.content)) }; });
  }

  /* OPTIMISTIC LOCKING, AND IT IS NOT OPTIONAL.
     The daily and weekly jobs commit to this same file on a schedule. Without
     this check a save built on a copy loaded ten minutes ago would silently
     erase whatever a run wrote in between — or a run would erase the edit. So:
     re-read the file immediately before writing, and if its sha has moved,
     REFUSE. Do not merge, do not retry, do not last-write-wins. Reload and show
     what changed, and let the person decide. */
  function ghSave(mutate, message) {
    var head;
    return ghLoad().then(function (fresh) {
      head = fresh;
      if (state.gh && state.gh.sha && state.gh.sha !== fresh.sha) {
        var e = new Error("stale");
        e.stale = true;
        e.changed = ghWhatChanged(state.gh.payload, fresh.payload);
        e.fresh = fresh;
        throw e;
      }
      var next = mutate(JSON.parse(JSON.stringify(fresh.payload)));
      if (!next) throw new Error("Nothing to save.");
      return fetch("https://api.github.com/repos/" + GH_REPO + "/contents/" + GH_PATH, {
        method: "PUT",
        headers: Object.assign({ "Content-Type": "application/json" }, ghHeaders()),
        body: JSON.stringify({
          message: message,
          content: b64encode(JSON.stringify(next, null, 2) + "\n"),
          sha: fresh.sha,
          branch: "main",
        }),
      }).then(function (res) {
        if (!res.ok) throw new Error(ghError(res));
        return res.json();
      }).then(function (j) {
        state.gh = { sha: j.content.sha, payload: JSON.parse(JSON.stringify(next)) };
        return j.commit && j.commit.html_url;
      });
    });
  }

  /* What a run changed while an edit was open. Shown on a refused save so the
     answer to "why did that not go through" is a list of facts rather than a
     retry. */
  function ghWhatChanged(was, now) {
    var byId = {}, out = [];
    (was.watches || []).forEach(function (w) { byId[w.id] = w; });
    (now.watches || []).forEach(function (w) {
      var b = byId[w.id];
      if (!b) return out.push(w.brand + " " + w.model + " — added");
      ADMIN_FIELDS.concat(["image"]).forEach(function (f) {
        if (JSON.stringify(b[f]) !== JSON.stringify(w[f])) {
          out.push(w.brand + " " + w.model + " — " + f + ": " + JSON.stringify(b[f])
                   + " → " + JSON.stringify(w[f]));
        }
      });
    });
    return out;
  }

  /* The id scheme, reproduced exactly: md5("brand|model" lowercased), first ten
     hex characters. Immutable once assigned — rewriting one orphans that watch's
     verification history — so a hand-added entry MUST land on the same id the
     refresh job would compute, or the two disagree about which watch this is.
     Web Crypto has no MD5, hence the implementation. Verified against the live
     register in test/template.test.js: all 252 ids reproduced. */
  function md5(s) {
    function rl(n, c) { return (n << c) | (n >>> (32 - c)); }
    function au(x, y) {
      var l = (x & 0xFFFF) + (y & 0xFFFF);
      return (((x >> 16) + (y >> 16) + (l >> 16)) << 16) | (l & 0xFFFF);
    }
    function cmn(q, a, b, x, s, t) { return au(rl(au(au(a, q), au(x, t)), s), b); }
    function ff(a,b,c,d,x,s,t){ return cmn((b & c) | (~b & d), a, b, x, s, t); }
    function gg(a,b,c,d,x,s,t){ return cmn((b & d) | (c & ~d), a, b, x, s, t); }
    function hh(a,b,c,d,x,s,t){ return cmn(b ^ c ^ d, a, b, x, s, t); }
    function ii(a,b,c,d,x,s,t){ return cmn(c ^ (b | ~d), a, b, x, s, t); }
    var bytes = new TextEncoder().encode(s);          /* UTF-8, like Python's */
    var n = bytes.length, words = [], i;
    for (i = 0; i < n; i++) words[i >> 2] = (words[i >> 2] || 0) | (bytes[i] << ((i % 4) * 8));
    words[n >> 2] = (words[n >> 2] || 0) | (0x80 << ((n % 4) * 8));
    var len = (((n + 8) >> 6) + 1) * 16;
    for (i = 0; i < len; i++) if (words[i] === undefined) words[i] = 0;
    words[len - 2] = n * 8;
    var a = 1732584193, b = -271733879, c = -1732584194, d = 271733878;
    var S = [7,12,17,22,5,9,14,20,4,11,16,23,6,10,15,21];
    var T = [-680876936,-389564586,606105819,-1044525330,-176418897,1200080426,
      -1473231341,-45705983,1770035416,-1958414417,-42063,-1990404162,1804603682,
      -40341101,-1502002290,1236535329,-165796510,-1069501632,643717713,-373897302,
      -701558691,38016083,-660478335,-405537848,568446438,-1019803690,-187363961,
      1163531501,-1444681467,-51403784,1735328473,-1926607734,-378558,-2022574463,
      1839030562,-35309556,-1530992060,1272893353,-155497632,-1094730640,681279174,
      -358537222,-722521979,76029189,-640364487,-421815835,530742520,-995338651,
      -198630844,1126891415,-1416354905,-57434055,1700485571,-1894986606,-1051523,
      -2054922799,1873313359,-30611744,-1560198380,1309151649,-145523070,-1120210379,
      718787259,-343485551];
    for (i = 0; i < len; i += 16) {
      var oa = a, ob = b, oc = c, od = d, j, f;
      for (j = 0; j < 64; j++) {
        var g = j < 16 ? j : j < 32 ? (5 * j + 1) % 16 : j < 48 ? (3 * j + 5) % 16 : (7 * j) % 16;
        f = j < 16 ? ff : j < 32 ? gg : j < 48 ? hh : ii;
        /* The mixing function must see a, b, c and d as they are NOW; rotating
           first feeds it b where it wants c and produces a plausible-looking
           digest that is wrong for every input. Rotate after. Sixty-four
           rotations of a four-cycle is the identity, so the accumulate below
           still lines up with a, b, c, d. */
        var mixed = f(a, b, c, d, words[i + g], S[(j >> 4) * 4 + (j % 4)], T[j]);
        a = d; d = c; c = b; b = mixed;
      }
      a = au(a, oa); b = au(b, ob); c = au(c, oc); d = au(d, od);
    }
    var hex = "";
    [a, b, c, d].forEach(function (v) {
      for (var k = 0; k < 4; k++) {
        hex += ("0" + ((v >> (k * 8)) & 255).toString(16)).slice(-2);
      }
    });
    return hex;
  }
  function makeId(brand, model) { return md5((brand + "|" + model).toLowerCase()).slice(0, 10); }

  /* ---- admin: the panel -------------------------------------------------- */
  var IN = "padding:7px 10px;border:1px solid #b9ae97;background:#fbf9f4;font-size:13px;"
         + "font-family:'Archivo',sans-serif;color:#17130d;border-radius:0;outline:none";
  var BTN = "border:1px solid #17130d;background:#17130d;color:#f4f1ea;padding:7px 14px;"
          + "font-family:'Archivo',sans-serif;font-size:11px;letter-spacing:.1em;"
          + "text-transform:uppercase;cursor:pointer";
  var BTN_OFF = "border:1px solid #c9c0ad;background:none;color:#a09786;padding:7px 14px;"
              + "font-family:'Archivo',sans-serif;font-size:11px;letter-spacing:.1em;"
              + "text-transform:uppercase;cursor:not-allowed";
  var GHOST = "border:1px solid #17130d;background:none;color:#17130d;padding:7px 14px;"
            + "font-family:'Archivo',sans-serif;font-size:11px;letter-spacing:.1em;"
            + "text-transform:uppercase;cursor:pointer";

  function adminNote(msg, tone) {
    state.adminMsg = msg ? { text: msg, tone: tone || "info" } : null;
    renderAdmin();
  }

  function adminEntry(id) {
    var src = (state.gh && state.gh.payload.watches) || state.payload.watches || [];
    for (var i = 0; i < src.length; i++) if (src[i].id === id) return src[i];
    return null;
  }

  /* The diff a person sees before anything is committed. No blind saves: every
     save names exactly what it will change, and the commit that results is one
     click from being reverted, which is the whole benefit of the data living in
     git rather than a database. */
  function adminDiff() {
    var form = state.adminForm || {}, base = state.adminEdit === "new" ? {} : (adminEntry(state.adminEdit) || {});
    var out = [];
    Object.keys(form).forEach(function (f) {
      var was = base[f] === undefined || base[f] === null ? "" : String(base[f]);
      if (String(form[f]) !== was) out.push({ field: f, from: was, to: String(form[f]) });
    });
    return out;
  }

  function renderAdmin() {
    var sec = el("#adminPanel");
    if (!sec) return;
    if (!state.admin) { sec.style.display = "none"; return; }
    sec.style.display = "";
    var tok = ghToken(), diff = adminDiff();

    var head = '<div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:0 0 14px">';
    if (tok) {
      head += '<span style="font-size:12px;color:#1e5c38;font-weight:600">Editing session open</span>' +
        '<span style="font-size:12px;color:#8a8071">' + (state.gh ? "register loaded · sha " + esc(state.gh.sha.slice(0, 7)) : "loading…") + '</span>' +
        '<button id="ghEnd" style="' + GHOST + '">End session</button>';
    } else {
      /* type=password so it is not shoulder-read or captured by a screenshot,
         autocomplete off so no browser offers to remember it, and it is never
         reflected back into the DOM after it is stored. */
      head += '<input id="ghTok" type="password" autocomplete="off" spellcheck="false" ' +
        'placeholder="Paste a fine-grained GitHub token" style="' + IN + ';width:320px">' +
        '<button id="ghStart" style="' + BTN + '">Start editing</button>' +
        '<span style="font-size:12px;color:#8a8071">Read-only until a token is pasted. ' +
        'This tab only — it is never stored, logged or committed.</span>';
    }
    head += '</div>';

    var msg = "";
    if (state.adminMsg) {
      var tone = state.adminMsg.tone === "bad" ? "#8a2b2b" : state.adminMsg.tone === "good" ? "#1e5c38" : "#8a8071";
      msg = '<p style="margin:0 0 14px;font-size:13px;line-height:1.5;color:' + tone + ';white-space:pre-wrap">' +
        esc(state.adminMsg.text) + '</p>';
    }

    var body = "";
    if (state.adminEdit) {
      var isNew = state.adminEdit === "new";
      var base = isNew ? {} : (adminEntry(state.adminEdit) || {});
      var owned = base.manual || [];
      body += '<div style="border-top:2px solid #17130d;padding-top:12px">' +
        '<div style="font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:#8a8071;font-weight:700;margin-bottom:10px">' +
        (isNew ? "New entry" : "Editing " + esc(base.brand + " — " + base.model) + " · " + esc(base.id)) + '</div>';
      body += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px">';
      ADMIN_FIELDS.forEach(function (f) {
        var v = state.adminForm[f] !== undefined ? state.adminForm[f]
              : (base[f] === undefined || base[f] === null ? "" : base[f]);
        var mine = owned.indexOf(f) >= 0;
        body += '<label style="display:block;font-size:11px;color:#8a8071">' +
          '<span style="letter-spacing:.1em;text-transform:uppercase;font-weight:700">' + esc(f) +
          (ADMIN_REQUIRED.indexOf(f) >= 0 ? ' <span style="color:#8a2b2b">required</span>' : '') +
          (mine ? ' <span style="color:#8a5a2b">yours</span>' : '') + '</span>' +
          '<input data-afield="' + esc(f) + '" value="' + esc(String(v)) + '" style="' + IN + ';width:100%;box-sizing:border-box;margin-top:3px"></label>';
      });
      body += '</div>';

      if (!isNew) {
        body += '<div style="margin-top:12px;display:flex;flex-wrap:wrap;gap:8px;align-items:center">' +
          '<span style="font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#8a8071;font-weight:700">Photograph</span>' +
          '<input id="aImg" value="' + esc(base.image || "") + '" placeholder="https://…" style="' + IN + ';flex:1;min-width:280px">' +
          '<button id="aImgSet" style="' + GHOST + '">Test &amp; set</button>' +
          '<button id="aImgClear" style="' + GHOST + '">Clear &amp; re-resolve</button></div>';
        /* Never delete. A mistaken entry is part of the audit trail and a
           sold-out one is the historical record; `retracted` stops it rendering
           without destroying either. */
        body += '<div style="margin-top:10px;display:flex;flex-wrap:wrap;gap:8px;align-items:center">' +
          '<button id="aRetract" style="' + GHOST + '">' + (base.retracted ? "Un-retract" : "Retract (hide, never delete)") + '</button>';
        if (owned.length) {
          body += '<button id="aRelease" style="' + GHOST + '">Release ' + owned.length +
            ' field' + (owned.length === 1 ? "" : "s") + ' back to automation</button>' +
            '<span style="font-size:12px;color:#8a8071">Yours: ' + esc(owned.join(", ")) + '</span>';
        }
        body += '</div>';
      }

      body += '<div style="margin-top:14px;border-top:1px solid #ddd6c8;padding-top:10px">';
      if (diff.length) {
        body += '<div style="font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:#8a8071;font-weight:700;margin-bottom:6px">' +
          diff.length + ' change' + (diff.length === 1 ? "" : "s") + ' to commit</div>';
        body += diff.map(function (c) {
          return '<div style="font-size:12.5px;color:#17130d;margin-bottom:3px"><b>' + esc(c.field) + '</b> ' +
            '<span style="color:#8a8071">' + esc(c.from || "(empty)") + '</span> → ' + esc(c.to) + '</div>';
        }).join("");
      } else {
        body += '<div style="font-size:12.5px;color:#8a8071">No changes yet.</div>';
      }
      body += '<div style="margin-top:10px;display:flex;gap:8px">' +
        '<button id="aSave" style="' + (tok && diff.length ? BTN : BTN_OFF) + '"' +
        (tok && diff.length ? "" : " disabled") + '>' +
        (tok ? "Preview said that — commit it" : "Read-only: no token") + '</button>' +
        '<button id="aCancel" style="' + GHOST + '">Cancel</button></div></div></div>';
    } else {
      body += '<div style="display:flex;gap:8px;flex-wrap:wrap">' +
        '<button id="aNew" style="' + GHOST + '">Add an entry</button>' +
        '<span style="font-size:12.5px;color:#8a8071">Open any row and use <b>Edit in the register</b> to change one.</span></div>';
    }
    el("#adminBody").innerHTML = head + msg + body;
  }

  function adminAction(node) {
    var id = node.id;

    if (id === "ghStart") {
      var v = (el("#ghTok").value || "").trim();
      if (!v) return adminNote("Paste a token first.", "bad");
      ghSetToken(v);
      el("#ghTok").value = "";           /* out of the DOM immediately */
      adminNote("Loading the register from GitHub…");
      return ghLoad().then(function (fresh) {
        state.gh = fresh;
        adminNote("Editing session open. " + fresh.payload.watches.length + " entries loaded.", "good");
      }).catch(function (err) {
        ghSetToken("");                  /* a token that cannot read is not a session */
        state.gh = null;
        adminNote(String(err.message || err), "bad");
      });
    }
    if (id === "ghEnd") {
      ghSetToken("");
      state.gh = null;
      state.adminEdit = null;
      state.adminForm = {};
      return adminNote("Session ended. The token is gone from this tab.", "info");
    }
    if (id === "aNew") { state.adminEdit = "new"; state.adminForm = {}; return adminNote(null); }
    if (id === "aCancel") { state.adminEdit = null; state.adminForm = {}; return adminNote(null); }
    if (node.hasAttribute && node.hasAttribute("data-aedit")) {
      state.adminEdit = node.getAttribute("data-aedit");
      state.adminForm = {};
      renderAdmin();
      var p = el("#adminPanel");
      if (p && p.scrollIntoView) p.scrollIntoView({ behavior: "smooth" });
      return;
    }

    if (id === "aImgSet") {
      var url = (el("#aImg").value || "").trim();
      if (!url) return adminNote("Nothing to set.", "bad");
      adminNote("Testing the image in this browser…");
      /* The truth test runs BEFORE the write, never after. The admin panel must
         not become the one path that can introduce a broken photograph. */
      return imageWorks(url).then(function (ok) {
        if (!ok) {
          return adminNote("REFUSED — that URL did not render as an image in this "
                           + "browser. It may be a 404, a hotlink block, or not an "
                           + "image at all. Nothing was written.", "bad");
        }
        var eid = state.adminEdit, host = "";
        try { host = new URL(url).hostname.replace(/^www\./, ""); } catch (e) {}
        return adminCommit(function (p) {
          var w = p.watches.filter(function (x) { return x.id === eid; })[0];
          if (!w) throw new Error("That entry is no longer in the file.");
          w.image = url;
          w.imageCredit = w.imageCredit || host;
          markManual(w, ["image", "imageCredit"]);
          return p;
        }, "Set the photograph for " + eid + " by hand\n\nManual edit through the admin "
         + "panel. The URL was rendered in a real browser before being written, and "
         + "`image` is now a manual field: the photograph pass will not re-resolve it, "
         + "and the rot check will flag it rather than clear it if it breaks.");
      });
    }

    if (id === "aImgClear") {
      var cid = state.adminEdit;
      return adminCommit(function (p) {
        var w = p.watches.filter(function (x) { return x.id === cid; })[0];
        if (!w) throw new Error("That entry is no longer in the file.");
        w.image = null;
        w.imageCredit = null;
        /* Clearing is a request to hand the photograph BACK to automation, so
           the manual claim on it is released rather than kept. */
        w.manual = (w.manual || []).filter(function (f) { return f !== "image" && f !== "imageCredit"; });
        if (!w.manual.length) delete w.manual;
        delete w.imageProbe;
        return p;
      }, "Clear the photograph for " + cid + " and return it to automatic resolution");
    }

    if (id === "aRetract") {
      var rid = state.adminEdit;
      return adminCommit(function (p) {
        var w = p.watches.filter(function (x) { return x.id === rid; })[0];
        if (!w) throw new Error("That entry is no longer in the file.");
        w.retracted = !w.retracted;
        if (!w.retracted) delete w.retracted;
        w.editedOn = todayISO();
        w.editedBy = "admin";
        return p;
      }, "Retract " + rid + " from the register\n\nHidden, not deleted. A mistaken entry "
       + "is part of the audit trail and a sold-out one is the historical record, so "
       + "nothing is ever removed from data.json.");
    }

    if (id === "aRelease") {
      var lid = state.adminEdit;
      return adminCommit(function (p) {
        var w = p.watches.filter(function (x) { return x.id === lid; })[0];
        if (!w) throw new Error("That entry is no longer in the file.");
        delete w.manual;
        return p;
      }, "Release " + lid + " back to automation\n\nEvery field on this entry is "
       + "automation's again; the next run may change any of them.");
    }

    if (id === "aSave") {
      var form = state.adminForm || {}, isNew = state.adminEdit === "new", eid2 = state.adminEdit;
      var missing = ADMIN_REQUIRED.filter(function (f) {
        var v = form[f] !== undefined ? form[f] : (isNew ? "" : (adminEntry(eid2) || {})[f]);
        return !String(v || "").trim();
      });
      if (missing.length) {
        return adminNote("Refused before committing — missing " + missing.join(", ") +
                         ". A missing price is fine; a missing source is not, because an "
                         + "entry with no provenance cannot carry an honest confidence "
                         + "rating.", "bad");
      }
      var fields = Object.keys(form);
      if (isNew) {
        var nid = makeId(form.brand, form.model);
        return adminCommit(function (p) {
          if (p.watches.some(function (x) { return x.id === nid; })) {
            /* Refuse on collision rather than overwrite: the id is derived from
               brand and model, so a collision means this watch is already in the
               register under another reading of its name. */
            throw new Error("An entry with id " + nid + " already exists — that brand and "
                            + "model are already in the register. Nothing was written.");
          }
          var w = { id: nid, image: null, imageCredit: null, verified: null,
                    soldOutOn: null, addedOn: todayISO(), tags: [], priceNum: null };
          ADMIN_FIELDS.forEach(function (f) { if (form[f] !== undefined) w[f] = form[f]; });
          w.rank = 2; w.tier = "Retailer enquiry";
          /* conf is chosen by the person, never defaulted high — a hand-added
             entry starts out claiming exactly as much as they said it does. */
          markManual(w, fields);
          p.watches.push(w);
          p.meta.count = p.watches.length;
          p.meta.brands = uniqueBrands(p.watches);
          return p;
        }, "Add " + form.brand + " " + form.model + " by hand\n\nEntered through the admin "
         + "panel. Its id is the same one the refresh job's scheme produces, so the two "
         + "agree about which watch this is. Tier starts at Retailer enquiry and is "
         + "earned upward by evidence, not asserted here.");
      }
      return adminCommit(function (p) {
        var w = p.watches.filter(function (x) { return x.id === eid2; })[0];
        if (!w) throw new Error("That entry is no longer in the file.");
        fields.forEach(function (f) { w[f] = form[f]; });
        if (form.price !== undefined) {
          var n = parseFloat(String(form.price).replace(/[^0-9.]/g, ""));
          w.priceNum = isNaN(n) ? null : n;
        }
        markManual(w, fields);
        p.meta.brands = uniqueBrands(p.watches);
        return p;
      }, "Correct " + fields.join(", ") + " on " + eid2 + " by hand\n\nManual edit through "
       + "the admin panel. These fields are now owned by a person: the refresh job may "
       + "propose a change to any of them and will never commit one.");
    }
  }

  function todayISO() { return new Date().toISOString().slice(0, 10); }
  function uniqueBrands(list) {
    var s = {};
    list.forEach(function (w) { s[w.brand] = 1; });
    return Object.keys(s).length;
  }
  /* Mirrors mark_manual() in scripts/refresh.py, including its refusal to let a
     human own bookkeeping fields. */
  function markManual(w, fields) {
    var owned = {};
    (w.manual || []).forEach(function (f) { owned[f] = 1; });
    fields.forEach(function (f) { if (ADMIN_FIELDS.concat(["image", "imageCredit"]).indexOf(f) >= 0) owned[f] = 1; });
    w.manual = Object.keys(owned).sort();
    w.editedOn = todayISO();
    w.editedBy = "admin";
  }

  /* Everything the panel commits goes through here, so the optimistic lock, the
     manual-field marking, the commit message and the surfaced commit URL are
     impossible to skip by adding another button later. */
  function adminCommit(mutate, message) {
    if (!ghToken()) return adminNote("No token — this session is read-only.", "bad");
    adminNote("Saving…");
    ghSave(mutate, message).then(function (url) {
      state.adminEdit = null;
      state.adminForm = {};
      adminNote("Committed. " + (url || "") + "\nOne click from being reverted, which is "
                + "the point of the data living in git.", "good");
      /* Re-read the register so the page shows what was just written rather
         than what it was showing before. */
      return fetch("data.json", { cache: "no-store" }).then(function (r) { return r.json(); })
        .then(function (p) { state.payload = p; });
    }).catch(function (err) {
      if (err && err.stale) {
        state.gh = err.fresh;
        adminNote("REFUSED — data.json changed since this edit was opened, so saving "
                  + "would have erased a scheduled run's work.\n\nWhat changed:\n"
                  + (err.changed.length ? err.changed.slice(0, 12).join("\n") : "(no field this panel tracks)")
                  + "\n\nThe register has been reloaded. Re-apply the edit and save again.", "bad");
        return;
      }
      adminNote(String(err && err.message || err), "bad");
    });
  }

  /* THE IMAGE TRUTH TEST, and this is the one place the browser is a BETTER
     instrument than the refresh job. CORS stops us reading a status code for a
     third-party image, but we do not need one: loading it as an Image and asking
     whether it decoded is precisely what a reader's browser does, from a real
     page, with a real referer. A pass here means more than a 200 from CI does.
     The admin panel must not become the one path that can introduce a broken
     photograph, so nothing is written until this resolves true. */
  function imageWorks(url) {
    return new Promise(function (resolve) {
      if (!/^https:\/\//.test(url || "")) return resolve(false);
      var img = new Image(), done = false;
      var finish = function (ok) { if (!done) { done = true; resolve(ok); } };
      img.onload = function () { finish(img.naturalWidth > 1 && img.naturalHeight > 1); };
      img.onerror = function () { finish(false); };
      setTimeout(function () { finish(false); }, 12000);
      img.src = url;
    });
  }

  /* ---- computed symmetric margins --------------------------------------- */
  /* The lower sections are not centred by a max-width — they carry an equal
     computed pad on both sides so the register lines up with the stats column
     above it. clientWidth, never 100vw: the latter counts the scrollbar and the
     alignment drifts by its width. */
  function applyMetrics() {
    var cw = document.documentElement.clientWidth;
    var colW = (Math.min(cw, 1200) - 157) / 2;
    var padRight = (30 + Math.max(0, colW - 400)) + "px";
    var regIndent = Math.max(0, Math.max(0, colW - 400) - Math.max(0, colW - 460)) + "px";
    var bar = el("#fbar"), main = el("#main");
    if (bar) bar.style.padding = "12px " + padRight + " 13px " + padRight;
    if (main) main.style.padding = "0 " + padRight + " 0 " + padRight;
    var wides = document.querySelectorAll('[data-mq="wide"]');
    for (var i = 0; i < wides.length; i++) wides[i].style.paddingLeft = regIndent;
  }

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

  /* ---- the date window --------------------------------------------------- */
  /* A real date, and it rolls at midnight the way a wheel does rather than
     silently swapping. Scheduled 80ms past midnight so it lands after the day
     has actually changed. */
  function applyDate(root) {
    var n = root.querySelector("[data-date]");
    if (n) n.textContent = new Date().getDate();
  }

  function flipDate() {
    var all = document.querySelectorAll("[data-date]");
    for (var i = 0; i < all.length; i++) {
      var n = all[i];
      n.style.animation = "wdi-dateflip .5s ease-in-out";
      (function (node) {
        setTimeout(function () { node.textContent = new Date().getDate(); }, 250);
        setTimeout(function () { node.style.animation = "none"; }, 700);
      })(n);
    }
  }

  function scheduleFlip() {
    var n = new Date();
    var next = new Date(n.getFullYear(), n.getMonth(), n.getDate() + 1, 0, 0, 0, 80);
    setTimeout(function () { flipDate(); scheduleFlip(); }, next - n);
  }

  /* ---- the dial ---------------------------------------------------------- */
  /* Plain on a reader's first ever visit, then a different treatment each time
     they come back. The masthead only — the corner badge is always plain. */
  var dialChoice = null;
  function pickDial() {
    if (dialChoice) return dialChoice;
    try {
      if (!localStorage.getItem("wdi-visited")) { dialChoice = "plain"; localStorage.setItem("wdi-visited", "1"); }
      else { var o = ["plain", "rim", "railroad", "guilloche", "lume"]; dialChoice = o[Math.floor(Math.random() * o.length)]; }
    } catch (e) { dialChoice = "plain"; }
    return dialChoice;
  }

  function applyDial(root) {
    var ds = pickDial();
    if (ds === "plain") return;
    var tpl = document.querySelector('template[data-dial="' + ds + '"]');
    var anchor = root.querySelector('[data-clock="hour"]');
    if (tpl && anchor) anchor.parentNode.insertBefore(tpl.content.cloneNode(true), anchor);
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

    var sBrand = shownBrand(d), sModel = shownModel(d);
    /* A bronze ° marks a row whose name or description has been edited. Admin
       only — a reader never sees the editorial machinery. */
    var mark = state.admin && (sBrand !== d.brand || sModel !== d.model || !!(ovAll()[d.id] || {}).desc) ? " °" : "";

    var dateShort = fmtDate(d.date);
    var useWin = DATE_WIN && dateShort !== "—" && dateShort !== "TBC";
    var dateInner = useWin
      ? '<span style="display:inline-block;max-width:100%;box-sizing:border-box;padding:1px 5px;background:#fdfbf5;border:1px solid #b9ae97;box-shadow:inset 1px 2px 2px rgba(23,19,13,.16), inset -1px -1px 1px rgba(255,255,255,.9);font-size:10.5px;line-height:1.35;color:#17130d;text-align:center;font-weight:600;overflow:hidden;text-overflow:ellipsis">' + esc(dateShort) + '</span>'
      : '<span style="overflow:hidden;text-overflow:ellipsis">' + esc(dateShort) + '</span>';

    /* Six children, and the phone layout addresses them by position — dot,
       brand+model, Released, Edition, USD, chevron. */
    var h = '<div data-id="' + esc(d.id) + '" style="border-bottom:1px solid ' + (open ? "#c9c0ad;background:#faf8f2" : "#d5cdbc") + '">' +
      '<div class="wdi-row" data-mq="cols" role="button" tabindex="0" aria-expanded="' + (open ? "true" : "false") + '" aria-controls="p-' + esc(d.id) + '"' +
      ' style="display:grid;grid-template-columns:16px minmax(0,1fr) 92px 70px 112px 16px;gap:14px;align-items:center;min-height:43px;padding:0 4px 0 2px;cursor:pointer">' +
      '<span style="width:7px;height:7px;border-radius:50%;justify-self:center;background:' + dot + '" title="' + esc(d.tier) + '"></span>' +
      '<span style="min-width:0;display:flex;align-items:baseline;gap:11px">' +
      '<span style="font-size:10.5px;letter-spacing:.11em;text-transform:uppercase;color:#8a8071;font-weight:650;flex:none;width:175px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(sBrand) + '</span>' +
      '<span title="' + esc(d.model) + '" style="' + modelStyle + '">' + esc(sModel + mark) + '</span></span>' +
      '<span title="' + esc(d.date) + '" style="font-size:12px;color:#8a8071;font-variant-numeric:tabular-nums;white-space:nowrap;overflow:hidden;border-left:1px solid #e9e4d8;align-self:stretch;display:flex;align-items:center;justify-content:flex-end;gap:4px;min-width:0">' + dateInner + '</span>' +
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
        /* referrerpolicy="no-referrer" is load-bearing, not a tidy-up. These are
           hotlinked press photographs, and several outlets serve an image to a
           direct request but refuse one carrying a foreign Referer — which is
           exactly what an <img> on this page sends. Opening the same URL in a
           tab works, so the empty-referer case is allowed; this tells the
           browser to make that request instead. Costs nothing, invisible, and
           it is the difference between a photograph and a broken-image box for
           any outlet with hotlink protection turned on. */
        '<img src="' + esc(d.image) + '" alt="' + esc(d.brand + " " + d.model) + '" loading="lazy" referrerpolicy="no-referrer"' +
        ' data-zoom="1" role="button" tabindex="0" aria-label="Enlarge the photograph of ' + esc(d.brand + " " + d.model) + '"' +
        /* Native size travels with the image so the viewer can refuse to
           upscale. Median here is 1600px and 211 of 217 are 900px or more, so
           enlarging is worth offering — but a 480px file blown up to fill a 4K
           display is worse than the inline thumbnail, not better. */
        (d.imageSize ? ' data-w="' + d.imageSize[0] + '" data-h="' + d.imageSize[1] + '"' : '') +
        ' style="width:100%;display:block;border:1px solid #ddd6c8;background:#ece7da;cursor:zoom-in">' +
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

    /* The caption ledger under the photograph — reference, release and how much
       we trust the entry, in the catalogue's own register style. */
    var cap = 'style="font-size:9.5px;letter-spacing:.15em;text-transform:uppercase;color:#8a8071;font-weight:700;padding-top:2px"';
    var capRow = 'style="display:grid;grid-template-columns:88px 1fr;gap:12px;padding:6px 0;border-bottom:1px solid #e9e4d8"';
    var ledger = '<div style="margin-top:12px;border-top:2px solid #17130d">' +
      '<div ' + capRow + '><span ' + cap + '>Reference</span><span style="font-size:12.5px;color:#17130d;font-variant-numeric:tabular-nums;letter-spacing:.03em;overflow-wrap:anywhere;text-align:right">' + esc(d.ref || "—") + '</span></div>' +
      '<div ' + capRow + '><span ' + cap + '>Released</span><span style="font-size:12.5px;color:#17130d;text-align:right">' + esc(d.date) + ' · ' + esc(d.cat) + '</span></div>' +
      '<div ' + capRow + ' title="' + esc(CONF[d.conf] || "") + '"><span ' + cap + '>Confidence</span><span style="font-size:12.5px;color:#17130d;text-transform:capitalize;text-align:right">' + esc(d.conf) + '</span></div>' +
      '</div>';

    var th = 'style="text-align:left;font-weight:700;color:#8a8071;font-size:10px;letter-spacing:.15em;text-transform:uppercase;padding:5px 18px 5px 0;vertical-align:top;white-space:nowrap;width:1px"';
    var td = 'style="padding:5px 0;vertical-align:top;border-bottom:1px solid #e9e4d8;color:#17130d"';
    var tdNum = 'style="padding:5px 0;vertical-align:top;border-bottom:1px solid #e9e4d8;color:#17130d;font-variant-numeric:tabular-nums"';
    var tdLast = 'style="padding:5px 0;vertical-align:top;color:#17130d"';

    var rows =
      '<tr><th ' + th + '>Availability</th><td ' + td + '><span style="display:inline-block;width:7px;height:7px;border-radius:50%;vertical-align:1px;margin-right:7px;background:' + dot + '"></span><b style="font-weight:650">' + esc(d.tier) + '</b><span style="color:#8a8071"> — ' + esc(HELP[d.tier] || "") + '</span></td></tr>' +
      '<tr><th ' + th + '>Price</th><td ' + tdNum + '>' + esc(d.price) + '</td></tr>' +
      '<tr><th ' + th + '>Edition</th><td ' + td + '>' + esc(d.edition) + '</td></tr>' +
      '<tr><th ' + th + '>Specification</th><td ' + tdLast + '>' + esc(d.specs) + '</td></tr>';

    var verified = d.verified
      ? '<p style="margin:0 0 10px;font-size:13px;line-height:1.5;color:#1e5c38"><span style="font-weight:700">✓ Stock checked ' + esc(d.verified.date) + '</span><span style="color:#3a342b"> — ' + esc(d.verified.note) + '</span></p>'
      : "";

    var tags = (d.tags || []).filter(function (t) { return t !== "Buy online"; });
    var tagLine = tags.length
      ? '<div style="font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:#8a8071;font-weight:600;margin:0 0 12px">' + esc(tags.join("  ·  ")) + '</div>'
      : "";

    var ctaStyle = "display:inline-block;font-size:13px;font-weight:600;letter-spacing:.02em;padding:11px 22px;border:1px solid #17130d;text-decoration:none;" +
      (d.rank <= 2 ? "background:#17130d;color:#f4f1ea" : "background:transparent;color:#17130d");
    var host = (function () { try { return new URL(d.source).hostname.replace(/^www\./, ""); } catch (e) { return "the source"; } })();

    /* The description is editable in place for an unlocked admin; everyone else
       gets the paragraph and nothing else. */
    var ov = ovAll()[d.id] || {};
    var descBlock;
    if (state.admin && state.descEditId === d.id) {
      descBlock = '<textarea id="descDraft" style="width:100%;box-sizing:border-box;min-height:110px;font-family:\'Newsreader\',serif;font-size:16px;line-height:1.5;color:#17130d;background:#fbf9f4;border:1px solid #b9ae97;padding:10px;margin:0 0 8px;border-radius:0;outline:none">' + esc(ov.desc || d.desc) + '</textarea>' +
        '<div style="display:flex;gap:12px;align-items:center;margin:0 0 12px">' +
        '<button data-desc-save="' + esc(d.id) + '" style="border:1px solid #17130d;background:#17130d;color:#f4f1ea;padding:6px 14px;font-family:\'Archivo\',sans-serif;font-size:11px;letter-spacing:.1em;text-transform:uppercase;cursor:pointer">Save</button>' +
        '<button data-desc-cancel="1" style="border:none;background:none;color:#8a5a2b;font-size:12px;text-decoration:underline;text-underline-offset:3px;cursor:pointer;font-family:\'Archivo\',sans-serif;padding:0">Cancel</button>' +
        '</div>';
    } else {
      descBlock = '<p style="font-family:\'Newsreader\',serif;font-size:17.5px;line-height:1.5;color:#17130d;margin:0 0 10px">' + esc(ov.desc || d.desc) + '</p>' +
        (state.admin
          ? '<p style="margin:-4px 0 10px;display:flex;gap:14px">' +
            '<a data-desc-edit="' + esc(d.id) + '" style="font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#8a5a2b;cursor:pointer;text-decoration:underline;text-underline-offset:3px">Edit description</a>' +
            '<a data-aedit="' + esc(d.id) + '" style="font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#8a5a2b;cursor:pointer;text-decoration:underline;text-underline-offset:3px">Edit in the register' +
            ((d.manual || []).length ? ' (' + (d.manual || []).length + ' yours)' : '') + '</a></p>'
          : "");
    }

    return '<div data-mq="detail" style="display:grid;grid-template-columns:310px minmax(0,1fr);gap:28px;padding:8px 4px 24px 32px">' +
      '<div style="min-width:0">' + fig + ledger + '</div>' +
      '<div style="min-width:0">' +
      descBlock +
      verified +
      '<table style="width:100%;border-collapse:collapse;font-size:13.5px;margin:0 0 12px"><tbody>' + rows + '</tbody></table>' +
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
    FILTERABLE.forEach(function (t) { if (byTier[t]) list.push({ key: t, label: t, n: byTier[t] }); });
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
      /* data-mq="pband" is what hides the price bands on a phone — price
         filtering is deliberately desktop-only. */
      out += '<button class="wdi-btn" data-mq="pband" data-band="' + esc(k) + '" style="' + btnStyle(state.band === k) + '">' + esc(k === "All" ? "Any" : k) + '</button>';
    });
    el("#bandBtns").innerHTML = out;
  }

  /* ---- sections from the calendar --------------------------------------- */
  function renderSections(cal, byTier) {
    var out = "";
    TIERS.forEach(function (t) {
      if (!byTier[t]) return;
      var r = t === "Gone" ? 6 : t === "Buy at retailer" ? 3 : t === "Drop upcoming" ? 1
            : t === "Waitlist or ballot" ? 3 : t === "AD or boutique" ? 4 : t === "In person only" ? 5 : 0;
      out += '<div data-mq="row2" style="display:grid;grid-template-columns:180px 1fr;gap:18px;padding:10px 0;border-bottom:1px solid #e9e4d8;font-size:13.5px;color:#8a8071">' +
        '<b style="color:#17130d;font-weight:650;display:flex;align-items:center;gap:9px"><span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:' + DOT(r) + '"></span>' + esc(t) + '</b>' +
        '<span>' + esc(HELP[t] || "") + '</span></div>';
    });
    el("#keyRows").innerHTML = out;

    var li = function (d, withWhere) {
      var detail = withWhere
        ? '<b style="color:#5c5546;font-weight:600">' + esc(d.where || "") + '</b> ' + esc(d.detail ? "— " + d.detail : "")
        : esc(d.detail || "");
      return '<li data-mq="row2" style="display:grid;grid-template-columns:168px 1fr;gap:20px;padding:14px 0;border-bottom:1px solid #e9e4d8">' +
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
    /* Ordered by the tier list, not by raw rank — the two are no longer the same
       thing now that "Buy at retailer" is remapped. */
    /* Brand and Model sort on the name the reader can actually see; Edition and
       Released sort on the same derived values their cells show. */
    if (sort === "tier") rows.sort(function (a, b) { return TIERS.indexOf(a.tier) - TIERS.indexOf(b.tier) || ((b.priceNum == null ? -1 : b.priceNum) - (a.priceNum == null ? -1 : a.priceNum)); });
    if (sort === "date") rows.sort(function (a, b) { return dkey(b) - dkey(a) || a.brand.localeCompare(b.brand); });
    if (sort === "dateAsc") rows.sort(function (a, b) { return dkey(a) - dkey(b) || a.brand.localeCompare(b.brand); });
    if (sort === "brand") rows.sort(function (a, b) { return shownBrand(a).localeCompare(shownBrand(b)) || a.model.localeCompare(b.model); });
    if (sort === "brandDesc") rows.sort(function (a, b) { return shownBrand(b).localeCompare(shownBrand(a)) || a.model.localeCompare(b.model); });
    if (sort === "model") rows.sort(function (a, b) { return shownModel(a).localeCompare(shownModel(b)); });
    if (sort === "modelDesc") rows.sort(function (a, b) { return shownModel(b).localeCompare(shownModel(a)); });
    if (sort === "priceAsc") rows.sort(function (a, b) { return (a.priceNum == null ? 9e12 : a.priceNum) - (b.priceNum == null ? 9e12 : b.priceNum); });
    if (sort === "priceDesc") rows.sort(function (a, b) { return (b.priceNum == null ? -1 : b.priceNum) - (a.priceNum == null ? -1 : a.priceNum); });
    if (sort === "edition") rows.sort(function (a, b) { return edN(a.edition) - edN(b.edition); });
    if (sort === "editionDesc") rows.sort(function (a, b) { return edN(b.edition) - edN(a.edition); });

    var byTier = {};
    DATA.forEach(function (d) { byTier[d.tier] = (byTier[d.tier] || 0) + 1; });

    el("#loading").style.display = "none";
    el("#empty").style.display = rows.length ? "none" : "block";
    el("#list").innerHTML = rows.map(rowHTML).join("");

    renderChrome(byTier);
    renderArrows();
    renderJournal();
    renderAdmin();
    hydrate(byTier);
  }

  /* ---- sortable headers -------------------------------------------------- */
  /* First click sorts each column the way it is most often wanted — brands and
     models A–Z, newest releases first, smallest editions first, biggest money
     first. A second click on the same header reverses it. */
  var SORTCOLS = { brand: ["brand", "brandDesc"], model: ["model", "modelDesc"], date: ["date", "dateAsc"],
                   edition: ["edition", "editionDesc"], price: ["priceDesc", "priceAsc"] };

  function renderArrows() {
    Object.keys(SORTCOLS).forEach(function (c) {
      var pair = SORTCOLS[c], n = el("#arr-" + c);
      if (n) n.textContent = state.sort === pair[0] ? " ▾" : state.sort === pair[1] ? " ▴" : "";
    });
  }

  function sortByColumn(c) {
    var pair = SORTCOLS[c];
    if (!pair) return;
    state.sort = state.sort === pair[0] ? pair[1] : pair[0];
    /* The pulldown has no option for a header sort, so it drops back to its
       label state rather than lying about what the list is ordered by. */
    var sel = el("#sort");
    if (sel) sel.value = ["tier", "date", "brand", "priceAsc", "priceDesc", "edition"].indexOf(state.sort) >= 0 ? state.sort : "tier";
    render();
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

  /* ---- editor's journal (admin only) ------------------------------------- */
  /* Every entry whose ledger name differs from the register data, and where the
     difference came from. The export is what the weekly job folds back into
     data.json — see README, "corrections JSON". */
  function renderJournal() {
    var sec = el("#journal");
    if (!sec) return;
    if (!state.admin) { sec.style.display = "none"; return; }
    sec.style.display = "";
    var OV = ovAll();
    var out = "";
    DATA.forEach(function (d) {
      var ov = OV[d.id] || {};
      var sb = shownBrand(d), sm = shownModel(d);
      if (sb === d.brand && sm === d.model && !ov.desc) return;
      var src = (ov.displayBrand || ov.displayModel || ov.desc) ? "your edit"
              : (d.displayBrand || d.displayModel) ? "weekly job" : "AI editorial";
      out += '<div style="border-bottom:1px solid #e9e4d8">' +
        '<div style="display:grid;grid-template-columns:minmax(0,1.15fr) 22px minmax(0,1fr) 92px 42px;gap:12px;padding:9px 0;font-size:13px;align-items:baseline">' +
        '<span style="color:#8a8071">' + esc(d.brand + " — " + d.model) + '</span>' +
        '<span style="color:#8a5a2b;text-align:center">→</span>' +
        '<span style="color:#17130d;font-weight:600">' + esc(sb + " — " + sm) + '</span>' +
        '<span style="font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:#a09786">' + src + '</span>' +
        '<a data-jedit="' + esc(d.id) + '" style="font-size:12px;color:#8a5a2b;cursor:pointer;text-decoration:underline;text-underline-offset:3px;text-align:right">Edit</a>' +
        '</div>';
      if (state.editId === d.id) {
        out += '<div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:2px 0 14px">' +
          '<input id="editBrand" value="' + esc(sb) + '" placeholder="Brand shown" style="width:200px;padding:7px 10px;border:1px solid #b9ae97;background:#fbf9f4;font-size:13px;font-family:\'Archivo\',sans-serif;color:#17130d;border-radius:0;outline:none">' +
          '<input id="editModel" value="' + esc(sm) + '" placeholder="Model shown" style="flex:1;min-width:260px;padding:7px 10px;border:1px solid #b9ae97;background:#fbf9f4;font-size:13px;font-family:\'Archivo\',sans-serif;color:#17130d;border-radius:0;outline:none">' +
          '<button data-jsave="' + esc(d.id) + '" style="border:1px solid #17130d;background:#17130d;color:#f4f1ea;padding:7px 14px;font-family:\'Archivo\',sans-serif;font-size:11px;letter-spacing:.1em;text-transform:uppercase;cursor:pointer">Save</button>' +
          '<button data-jclear="' + esc(d.id) + '" style="border:1px solid #b9ae97;background:none;color:#8a8071;padding:7px 12px;font-family:\'Archivo\',sans-serif;font-size:11px;letter-spacing:.1em;text-transform:uppercase;cursor:pointer">Clear my edit</button>' +
          '<button data-jcancel="1" style="border:none;background:none;color:#8a5a2b;font-size:12px;text-decoration:underline;text-underline-offset:3px;cursor:pointer;font-family:\'Archivo\',sans-serif;padding:0">Cancel</button>' +
          '</div>';
      }
      out += '</div>';
    });
    el("#journalRows").innerHTML = out;
    el("#ovCount").textContent = Object.keys(OV).length + " correction(s) on this device";
  }

  /* ---- the admin gate ----------------------------------------------------- */
  /* The reference opens the journal on ?admin=1. That is fine in a design tool
     and useless on a public site, so the live gate is a shared secret: the URL
     carries ?admin=<token> and only its SHA-256 is ever published here. The
     token is Lowell's; it is not in this repository, and the digest below tells
     an attacker nothing they can use. Once it matches, the session remembers,
     so the token need not stay in the address bar.
     Nothing here writes to the register — corrections live in this browser and
     leave as JSON — so a secret link is proportionate protection for editorial
     machinery rather than for data. */
  var ADMIN_HASH = "__ADMINHASH__";
  var ADMIN_KEY = "wdi-admin-ok";

  function sha256Hex(s) {
    if (!(window.crypto && crypto.subtle && window.TextEncoder)) return Promise.resolve(null);
    return crypto.subtle.digest("SHA-256", new TextEncoder().encode(s)).then(function (buf) {
      return Array.prototype.map.call(new Uint8Array(buf), function (b) {
        return ("0" + b.toString(16)).slice(-2);
      }).join("");
    }).catch(function () { return null; });
  }

  function unlockAdmin() {
    var tok = new URLSearchParams(location.search).get("admin");
    var remembered = false;
    try { remembered = sessionStorage.getItem(ADMIN_KEY) === "1"; } catch (e) {}
    if (remembered) { state.admin = true; return Promise.resolve(); }
    if (!tok || !ADMIN_HASH) return Promise.resolve();
    return sha256Hex(tok).then(function (h) {
      if (h && h === ADMIN_HASH) {
        state.admin = true;
        try { sessionStorage.setItem(ADMIN_KEY, "1"); } catch (e) {}
        /* Take the token back out of the address bar so it does not travel in a
           referer, a screenshot or a shared link. */
        history.replaceState(null, "", location.pathname + location.hash);
      }
    });
  }

  /* ---- corner badge ------------------------------------------------------ */
  /* Mounted and unmounted rather than shown and hidden, so the .6s rise replays
     each time it appears — and so its clock is re-synced on every mount. It
     arrives the moment the masthead wordmark disappears under the sticky bar,
     measured rather than assumed, so it does not depend on the header's height
     staying what it was the day this was written. */
  function badgeWanted() {
    var lg = el("#lockup");
    if (!lg) return window.scrollY > 430;
    var st = el("#fbarwrap");
    return lg.getBoundingClientRect().bottom <= (st ? st.offsetHeight : 0);
  }

  function setBadge(on) {
    var host = el("#badgeHost");
    if (on && !host.firstChild) {
      var tpl = el("#badgeTpl");
      host.appendChild(tpl.content.cloneNode(true));
      var node = host.firstElementChild;
      applyBearings(node);
      applyDelays(node);
      applyDate(node);
      node.addEventListener("click", function () { window.scrollTo({ top: 0, behavior: "smooth" }); });
      node.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); window.scrollTo({ top: 0, behavior: "smooth" }); }
      });
    } else if (!on && host.firstChild) {
      host.innerHTML = "";
    }
  }

  /* ---- the enlarged photograph ------------------------------------------- */
  /* Opens at NATIVE size, capped to the viewport — never upscaled. These are
     press og:image files; stretching a 480px one across a 4K display makes it
     softer than the thumbnail it came from. Focus goes into the dialog on open
     and returns to the exact photograph on close, so a keyboard user is not
     dumped back at the top of the register. */
  var zoomReturn = null;

  function openZoom(img) {
    var box = el("#lightbox"), big = el("#lightboxImg"), cap = el("#lightboxCap");
    if (!box || !big) return;
    var w = parseInt(img.getAttribute("data-w"), 10);
    big.src = img.getAttribute("src");
    big.alt = img.getAttribute("alt") || "";
    /* No native width recorded means we cannot promise it will not blur, so it
       is capped at the viewport and no further. */
    big.style.maxWidth = w ? "min(94vw, " + w + "px)" : "94vw";
    var fig = img.closest("figure");
    var credit = fig && fig.querySelector("figcaption");
    cap.textContent = (img.getAttribute("alt") || "") + (credit ? " — " + credit.textContent.trim() : "");
    box.style.display = "flex";
    /* The page behind must not scroll away under the dialog. */
    document.documentElement.style.overflow = "hidden";
    zoomReturn = img;
    box.focus();
  }

  function closeZoom() {
    var box = el("#lightbox");
    if (!box || box.style.display === "none") return;
    box.style.display = "none";
    el("#lightboxImg").src = "";
    document.documentElement.style.overflow = "";
    if (zoomReturn && document.contains(zoomReturn)) zoomReturn.focus();
    zoomReturn = null;
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
    applyMetrics();
    var lock = el("#lockup");
    applyDial(lock);
    applyBearings(lock);
    applyDelays(lock);
    applyDate(lock);
    scheduleFlip();
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(function () {
        applyBearings(el("#lockup"));
        var b = el("#badgeHost").firstElementChild;
        if (b) applyBearings(b);
      });
    }

    window.addEventListener("scroll", function () {
      var v = badgeWanted();
      if (v !== state.showBadge) { state.showBadge = v; setBadge(v); }
    }, { passive: true });

    /* Re-pads only. The reference re-renders on resize but leaves the badge's
       visibility to the scroll handler, so resizing never mounts or unmounts it
       — matched deliberately rather than "improved". */
    window.addEventListener("resize", applyMetrics);

    /* Bound on the document rather than per input, because the panel re-renders
       its own markup on every keystroke's worth of state change and per-node
       listeners would be lost with it. Reads into state.adminForm only — the
       diff and the commit both come from there, so what is previewed is exactly
       what is written. */
    document.addEventListener("input", function (e) {
      var f = e.target.getAttribute && e.target.getAttribute("data-afield");
      if (!f) return;
      state.adminForm[f] = e.target.value;
      /* Re-render the diff without rebuilding the inputs under the cursor. */
      var d = adminDiff();
      var box = el("#adminBody");
      if (box) {
        var save = box.querySelector("#aSave");
        if (save) {
          save.disabled = !(ghToken() && d.length);
          save.setAttribute("style", ghToken() && d.length ? BTN : BTN_OFF);
        }
      }
    });

    el("#q").addEventListener("input", function (e) { state.q = e.target.value; render(); });
    el("#sort").addEventListener("change", function (e) { state.sort = e.target.value; render(); });
    el("#reset").addEventListener("click", function () {
      state.q = ""; state.tier = "All"; state.cat = "All"; state.band = "All"; state.sort = "tier";
      el("#q").value = ""; el("#sort").value = "tier";
      dropHash(); render();
    });

    /* Clicking the enlarged photograph, or anywhere around it, closes. */
    el("#lightbox").addEventListener("click", closeZoom);

    document.addEventListener("click", function (e) {
      var zoom = e.target.closest("[data-zoom]");
      if (zoom) {
        /* Must not also toggle the row shut underneath the dialog. */
        e.stopPropagation();
        return openZoom(zoom);
      }
      var b = e.target.closest("[data-tier],[data-band]");
      if (b) {
        if (b.hasAttribute("data-tier")) state.tier = b.getAttribute("data-tier");
        else state.band = b.getAttribute("data-band");
        return render();
      }
      var head = e.target.closest("[data-sortcol]");
      if (head) return sortByColumn(head.getAttribute("data-sortcol"));

      /* Editor's controls. All of them live inside the row or the journal, so
         they are matched before the row toggle — otherwise clicking Save would
         also collapse the entry underneath it. */
      var ed = e.target.closest("[data-desc-edit],[data-desc-save],[data-desc-cancel],[data-jedit],[data-jsave],[data-jclear],[data-jcancel],#copyPatch");
      if (ed) {
        e.stopPropagation();
        var o = ovAll(), id;
        if (ed.hasAttribute("data-desc-edit")) { state.descEditId = ed.getAttribute("data-desc-edit"); return render(); }
        if (ed.hasAttribute("data-desc-cancel")) { state.descEditId = null; return render(); }
        if (ed.hasAttribute("data-desc-save")) {
          id = ed.getAttribute("data-desc-save");
          o[id] = Object.assign({}, o[id], { desc: el("#descDraft").value });
          state.descEditId = null;
          return ovSave(o);
        }
        if (ed.hasAttribute("data-jedit")) { state.editId = ed.getAttribute("data-jedit"); return render(); }
        if (ed.hasAttribute("data-jcancel")) { state.editId = null; return render(); }
        if (ed.hasAttribute("data-jsave")) {
          id = ed.getAttribute("data-jsave");
          o[id] = Object.assign({}, o[id], { displayBrand: el("#editBrand").value, displayModel: el("#editModel").value });
          state.editId = null;
          return ovSave(o);
        }
        if (ed.hasAttribute("data-jclear")) {
          delete o[ed.getAttribute("data-jclear")];
          state.editId = null;
          return ovSave(o);
        }
        if (ed.id === "copyPatch" && navigator.clipboard) {
          return navigator.clipboard.writeText(JSON.stringify(ovAll(), null, 2));
        }
        return;
      }
      /* The write path. Kept in its own dispatcher because everything below it
         can commit to the repository, and that is worth being able to read as
         one block rather than finding interleaved with display handlers. */
      var ad = e.target.closest("#ghStart,#ghEnd,#aNew,#aCancel,#aSave,#aImgSet,#aImgClear," +
                                "#aRetract,#aRelease,[data-aedit]");
      if (ad) {
        e.stopPropagation();
        return adminAction(ad);
      }

      var row = e.target.closest(".wdi-row");
      if (row) toggle(row.parentNode.getAttribute("data-id"));
    });

    /* The comp makes rows a div[role=button], which — unlike a real button —
       does not activate on Enter or Space. Restored explicitly. */
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") return closeZoom();
      if (e.key !== "Enter" && e.key !== " ") return;
      var zoom = e.target.closest && e.target.closest("[data-zoom]");
      if (zoom) { e.preventDefault(); e.stopPropagation(); return openZoom(zoom); }
      var head = e.target.closest && e.target.closest("[data-sortcol]");
      if (head) { e.preventDefault(); return sortByColumn(head.getAttribute("data-sortcol")); }
      var row = e.target.closest && e.target.closest(".wdi-row");
      if (!row) return;
      e.preventDefault();
      toggle(row.parentNode.getAttribute("data-id"));
    });

    window.addEventListener("hashchange", function () {
      var id = location.hash.slice(1);
      if (id && !state.open[id]) openById(id, true);
    });

    unlockAdmin().then(function () { return fetch("data.json", { cache: "no-store" }); })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (p) {
        state.payload = p;
        /* SCOPE, Lowell's ruling of 2026-08-04: a production cap is not a limited
           edition. Filtered at the display layer only — data.json still holds all
           252, so if a weekly run ever confirms one of these as a real numbered
           edition, it reappears here on its own. Every figure on the page counts
           what survives this filter.
           Entries whose edition is unconfirmed, "special" or not disclosed DO
           stay (their Edition cell reads N/A) — revisit later.
           The only other transformation is the "Retailer enquiry" remap, applied
           once here so nothing downstream has to know the old name. */
        var NOT_LE = [/not formally limited/i, /^capped/i, /annually/i];
        DATA = (p.watches || [])
          /* Retracted entries are hidden here and nowhere else. Nothing is ever
             deleted from data.json — a mistaken entry is part of the audit trail
             and a sold-out one is the historical record — so retraction is a
             display rule, exactly like the production-cap scope rule beside it. */
          .filter(function (w) { return !w.retracted; })
          .filter(function (w) { var e = String(w.edition || "").trim(); return !NOT_LE.some(function (rx) { return rx.test(e); }); })
          .map(function (w) { return w.tier === "Retailer enquiry" ? Object.assign({}, w, { tier: "Buy at retailer", rank: 3 }) : w; });
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

  /* A named surface for test/template.test.js, which otherwise cannot reach
     anything inside this IIFE. Exposing it costs nothing that was not already
     available: this is a public static page, so whatever the page can do a
     console on the page can do, and nothing here holds a secret — the token
     lives in sessionStorage, which is equally reachable either way. What it
     buys is real: the id scheme below MUST agree with Python's md5 on all 252
     existing entries, and a hand-added entry whose id disagrees is a watch the
     refresh job thinks is a different watch. That is worth an assertion. */
  window.WDI = {
    md5: md5, makeId: makeId, b64encode: b64encode, b64decode: b64decode,
    ghError: ghError, ghWhatChanged: ghWhatChanged, ghSave: ghSave,
    ghSetToken: ghSetToken, ghToken: ghToken, imageWorks: imageWorks,
    renderAdmin: renderAdmin, adminDiff: adminDiff, markManual: markManual,
    state: state,
  };
})();
"""

TIER_HELP = {
    "Buy online now": "Add to cart on a brand webshop or an authorised online retailer.",
    "Drop upcoming": "Announced with a date. Nothing to buy yet.",
    "Buy at retailer": "Available for purchase now at physical retail — not online. We list what we know about where.",
    "Waitlist or ballot": "Entry by lottery, ballot or waitlist.",
    "AD or boutique": "Allocation only. Never sold online.",
    "In person only": "Sold at an event or a single physical location.",
    "Gone": "Sold out, closed or fully allocated.",
}

# Brand display names. A collab shows the MANUFACTURER, which is the first name
# by convention — MAKER_OVERRIDE is only for the four where it is listed second.
MAKER_OVERRIDE = {
    "Worn & Wound × BOLDR": "BOLDR",
    "The Armoury × Naoya Hida": "Naoya Hida & Co.",
    "Omega / Swatch": "Swatch",
    "Swatch × Audemars Piguet": "Swatch",
}

# Editorial short titles for the ledger column, from design (v1.2). Keep the family
# and the edition identity, drop calibre numbers, spec words, sizes, references and
# variant lists; 38 characters is the ceiling. These are editorial decisions and
# are never regenerated — a new entry gets a displayModel in data.json instead.
SHORT_MODEL = {
    "Navitimer B01 Chronograph 43 \"Tribute to Concorde\"": "Navitimer \"Tribute to Concorde\"",
    "Antarctique \"Frozen Meteor\" (38.5 & 40.5mm)": "Antarctique \"Frozen Meteor\"",
    "Antarctique Dark Sector Titanium \"Cosmic Blue\"": "Antarctique Dark Sector \"Cosmic Blue\"",
    "\"Ice Forest at Dawn\" Spring Drive U.F.A.": "\"Ice Forest at Dawn\" U.F.A.",
    "Master Collection Moon Phase \"Year of the Horse\"": "Master Moon Phase \"Year of the Horse\"",
    "Le Régulateur Esprit Flinqué (blue & grey)": "Le Régulateur Esprit Flinqué",
    "× Alain Silberstein Régulateur Tourbillon Blue": "× Silberstein Régulateur Tourbillon",
    "US 250 Anthracite Navigator (SSNAV-D Auto Type II)": "US 250 Anthracite Navigator",
    "Iced Sea Automatic Date 0 Oxygen LE 300 — coral dial": "Iced Sea 0 Oxygen LE 300 (coral)",
    "Iced Sea Automatic Date 0 Oxygen LE 700 — subfossil wood dial": "Iced Sea 0 Oxygen LE 700 (subfossil)",
    "Star Legacy Nicolas Rieussec Chronograph LE 821": "Star Legacy Rieussec Chrono LE 821",
    "Lou Gehrig Limited Edition (Big Crown Pointer Date)": "Lou Gehrig Limited Edition",
    "\"Starry Sky\" 2026 series (SSH187 / HAB005 / HAB006 / HAB004 / SSJ039)": "\"Starry Sky\" 2026 series",
    "Marinemaster 1968 Heritage Diver × JAMSTEC": "Marinemaster 1968 × JAMSTEC",
    "Speedtimer Mechanical Chronograph 145th Anniversary": "Speedtimer 145th Anniversary",
    "5 Sports \"Rally Diver\" (38mm green / 42mm blue)": "5 Sports \"Rally Diver\"",
    "SEGA 65th Anniversary Chronograph (2 colourways)": "SEGA 65th Anniversary Chronograph",
    "936 S Black Chronograph, Fully Tegimented LE": "936 S Black Tegimented LE",
    "Croft Mid-Size Automatic \"Dolphin Project\"": "Croft \"Dolphin Project\"",
    "Field Watch with a Twist (Whirlpool / Storm)": "Field Watch with a Twist",
    "T-Race MotoGP 2026 Automatic Chronograph": "T-Race MotoGP 2026 Chronograph",
    "Trente-Deux × Exquisite Timepieces Purple LE": "Trente-Deux Purple LE",
    "GS9 Club member exclusive \"Minato-nezumi\"": "GS9 Club \"Minato-nezumi\"",
    "Aston Martin Aramco Formula One Navitimer B01": "Navitimer Aston Martin F1",
    "Navitimer B01 \"North America\" Limited Edition": "Navitimer \"North America\" LE",
    "Top Time B01 41 \"Tribute to DB5\" (Aston Martin)": "Top Time \"Tribute to DB5\"",
    "Mudmaster × Team Land Cruiser Toyota Auto Body": "Mudmaster × Team Land Cruiser",
    "Mille Miglia GTS Power Control \"Grigio-Blu\"": "Mille Miglia GTS \"Grigio-Blu\"",
    "The Citizen — Eco-Drive 50th Anniversary": "The Citizen Eco-Drive 50th",
    "Spirit of Big Bang Moon Phase \"Impact\" All Black": "Spirit of Big Bang \"Impact\" All Black",
    "Meister Chronoscope Edition (\"Classics in Captivating Colors\")": "Meister Chronoscope Edition",
    "F77 MKII Stone Dials (lapis / meteorite / aventurine)": "F77 MKII Stone Dials",
    "Seamaster Diver 300M Chronograph \"007 First Light\"": "Seamaster 300M \"007 First Light\"",
    "Seamaster Diver 300M Milano Cortina 2026": "Seamaster 300M Milano Cortina 2026",
    "Seamaster Diver 300M Paralympic Winter Games Milano Cortina": "Seamaster 300M Paralympic 2026",
    "Speedmaster Moonwatch Professional \"Masters Green\"": "Speedmaster Moonwatch \"Masters Green\"",
    "20th Anniversary raffles — LM101 Longhorn & M.A.D.1S": "LM101 Longhorn & M.A.D.1S raffles",
    "Conquer 2026 Limited Edition Chronograph": "Conquer 2026 LE Chronograph",
    "Lange 1 Tourbillon Perpetual Calendar \"Lumen\"": "Lange 1 Tourbillon Perpetual \"Lumen\"",
    "Minute Repeater Resonance 12:59 First Edition": "Minute Repeater Resonance 12:59",
    "Royal Oak Concept Flying Tourbillon \"Yoon & Verbal\"": "Royal Oak Concept \"Yoon & Verbal\"",
    "Villeret Calendrier Chinois Traditionnel \"Year of the Horse\"": "Villeret \"Year of the Horse\"",
    "Classique 7185 Chinese New Year \"Year of the Horse\"": "Classique 7185 \"Year of the Horse\"",
    "Classique Tourbillon Sidéral 7255PT/2N/9VU": "Classique Tourbillon Sidéral",
    "Marine Tourbillon Équation Marchante 5887PT/YS/5WV": "Marine Tourbillon Équation Marchante",
    "America250 Avenger Night Mission Chronograph": "America250 Avenger Night Mission",
    "Navitimer B19 Perpetual Calendar, full platinum": "Navitimer B19 Perpetual (platinum)",
    "Octo Finissimo Ultra Tourbillon Platinum": "Octo Finissimo Ultra Tourbillon",
    "L.U.C Quattro Spirit 25 \"Straw Marquetry\"": "L.U.C Quattro \"Straw Marquetry\"",
    "Goldfeather — Imari Nabeshima porcelain dial": "Goldfeather Imari Nabeshima",
    "Goldfeather — Urushi maki-e blue gradient": "Goldfeather Urushi maki-e",
    "Antarctique Tourbillon Titanium \"Cosmic Blue\"": "Antarctique Tourbillon \"Cosmic Blue\"",
    "Faubourg de Cracovie \"Crossroads\" Victory Green Chronograph": "Faubourg de Cracovie \"Crossroads\"",
    "La Esmeralda Tourbillon \"A Secret\" Eternity Edition (Red)": "La Esmeralda \"A Secret\" Eternity",
    "SeaQ Panorama Date \"Northern Tide\" 43.2mm": "SeaQ Panorama \"Northern Tide\"",
    "Seventies Chronograph XV Limited Edition": "Seventies Chronograph XV LE",
    "Balancier 3 Titanium Blue (2026 edition)": "Balancier 3 Titanium Blue",
    "Endeavour Minute Repeater Cylindrical Tourbillon Skeleton \"Cosmic Rain\"": "Endeavour Repeater \"Cosmic Rain\"",
    "Endeavour Perpetual Calendar Concept Tantalum": "Endeavour Perpetual Tantalum",
    "Streamliner Alpine Drivers + Mechanics Pink Edition (set)": "Streamliner Alpine Pink Edition set",
    "Streamliner Small Seconds Lime Green Enamel": "Streamliner Lime Green Enamel",
    "Big Bang Tourbillon \"GOAT\" (Novak Djokovic)": "Big Bang Tourbillon \"GOAT\"",
    "Classic Fusion Titanium \"Retroverse\" (The Hour Glass)": "Classic Fusion \"Retroverse\"",
    "Spirit of Big Bang Moon Phase \"Impact\" Diamond Sapphire": "Spirit of Big Bang \"Impact\" Diamond",
    "Spirit of Big Bang Moon Phase \"Impact\" Sapphire Osmium": "Spirit of Big Bang \"Impact\" Osmium",
    "Big Pilot's Watch Perpetual Calendar Ceralume": "Big Pilot Perpetual Ceralume",
    "Master Grande Tradition Tourbillon Jumping Date": "Master Tourbillon Jumping Date",
    "Master Hybris Artistica \"Inventiva Gyrotourbillon à Stratosphère\"": "Hybris Artistica Gyrotourbillon",
    "Master Hybris Mechanica Ultra-Thin Minute Repeater": "Hybris Mechanica Minute Repeater",
    "Reverso One \"La Vallée des Merveilles\" (3 models)": "Reverso One \"Vallée des Merveilles\"",
    "Reverso Tribute Enamel \"Hokusai Waterfalls\" (4 models)": "Reverso Tribute \"Hokusai Waterfalls\"",
    "Reverso Tribute Monoface \"Or Deco Cocktail\" (3 gem-set)": "Reverso Tribute \"Or Deco Cocktail\"",
    "LM Perpetual Chromatic Editions (3 gem-set)": "LM Perpetual Chromatic Editions",
    "Hölstein Edition 2026 (Artelier Small Seconds)": "Hölstein Edition 2026",
    "Radiomir California Bronzo + Platinumtech \"Experience\" set": "Radiomir California \"Experience\" set",
    "Submersible Navy SEALs \"Afniotech Experience\"": "Submersible Navy SEALs \"Afniotech\"",
    "Toric Chronographe Rattrapante Platinum": "Toric Rattrapante Platinum",
    "Nautilus 50th Anniversary Pocket Watch 958G-001": "Nautilus 50th Pocket Watch",
    "Modello Due UT2-NST \"Natural Selection\"": "Modello Due \"Natural Selection\"",
    "Métiers d'Art \"Tribute to Great Civilisations II\" (4 models)": "Métiers d'Art \"Great Civilisations II\"",
    "Overseas Self-Winding Ultra-Thin, Platinum": "Overseas Ultra-Thin Platinum",
    "Chronomaster Revival \"Liberty II\" (steel & carbon)": "Chronomaster Revival \"Liberty II\"",
    "Chronomaster Sport Skeleton, diamond-set rose gold": "Chronomaster Sport Skeleton rose gold",
    "Monaco Chronograph × Goodwood Festival of Speed": "Monaco Chronograph × Goodwood",
    "NH TYPE 2C-2 (porcelain dial) · TYPE 1E · TYPE 5B / 5B-1": "NH TYPE 2C-2 · 1E · 5B",
    "1965 Heritage Diver — Shohei Ohtani (grey & blue)": "1965 Heritage Diver Shohei Ohtani",
    "Les Cabinotiers Minute Repeater Tourbillon Skeleton": "Les Cabinotiers Repeater Tourbillon",
}

# The half-dial detail treatments. Every one is clipped to the same sector as the
# arc so nothing ever paints behind the letters. The masthead picks one per
# visit; the corner badge is always plain, so these live only in the masthead.
DIALS = {
    "rim": '<span style="position:absolute;left:-1.72em;top:-1.72em;width:3.44em;height:3.44em;border:.055em solid #17130d;border-radius:50%;opacity:.75;clip-path:polygon(50% -4%, 104% -4%, 104% 104%, 33% 104%, 33% 60%, 50% 60%);filter:drop-shadow(.04em .05em .04em rgba(23,19,13,.3))"></span>',
    "railroad": (
        '<span style="position:absolute;left:-1.45em;top:-1.45em;width:2.9em;height:2.9em;border:1px solid #17130d;border-radius:50%;opacity:.32;clip-path:polygon(50% -3%, 103% -3%, 103% 103%, 34% 103%, 34% 60%, 50% 60%)"></span>'
        + "".join(
            f'<span style="position:absolute;left:0;top:0;width:.05em;height:.16em;background:#17130d;opacity:.5;transform:translate(-50%,-50%) rotate({a}deg) translateY(-1.37em)"></span>'
            for a in (0, 30, 60, 120, 150, 180)
        )
    ),
    "guilloche": (
        '<span style="position:absolute;left:-1.08em;top:-1.08em;width:2.16em;height:2.16em;border-radius:50%;border:1px solid rgba(23,19,13,.25);background:repeating-conic-gradient(rgba(23,19,13,.13) 0deg 2deg, rgba(23,19,13,0) 2deg 5deg);clip-path:polygon(50% -3%, 103% -3%, 103% 103%, 34% 103%, 34% 60%, 50% 60%)"></span>'
        '<span style="position:absolute;left:-.72em;top:-.72em;width:1.44em;height:1.44em;border-radius:50%;border:1px solid rgba(23,19,13,.18);clip-path:polygon(50% -3%, 103% -3%, 103% 103%, 34% 103%, 34% 60%, 50% 60%)"></span>'
    ),
    "lume": (
        '<span style="position:absolute;left:0;top:0;width:.18em;height:.16em;background:#8a5a2b;clip-path:polygon(50% 100%,0 0,100% 0);transform:translate(-50%,-50%) rotate(0deg) translateY(-1.38em)"></span>'
        + "".join(
            f'<span style="position:absolute;left:0;top:0;width:.11em;height:.11em;border-radius:50%;background:#8a5a2b;opacity:.85;transform:translate(-50%,-50%) rotate({a}deg) translateY(-1.38em)"></span>'
            for a in (30, 60, 120, 150, 180)
        )
    ),
}

DIAL_TEMPLATES = "".join(
    f'<template data-dial="{k}">{v}</template>' for k, v in DIALS.items()
)

# z-index 1 on the window, 2 on the hands, 3 on the centre cap: without it the
# guilloche and railroad rings paint across the date window (design, v1.1 §5).
DATE_WINDOW = (
    '<span style="position:absolute;left:.86em;top:-.23em;width:.54em;height:.46em;background:#fdfbf5;z-index:1;'
    'border:.035em solid #b9ae97;box-shadow:inset .02em .05em .07em rgba(23,19,13,.3), inset -.02em -.03em .05em rgba(255,255,255,.95), 0 .02em .03em rgba(255,255,255,.7);'
    'display:flex;align-items:center;justify-content:center;overflow:hidden">'
    '<span data-date style="font-family:\'Archivo\',sans-serif;font-weight:600;font-size:.3em;color:#17130d;'
    'line-height:1;font-variant-numeric:tabular-nums;animation:none"></span></span>'
)


def lockup(px):
    """The stacked wordmark. `px` drives the canvas measurement for the optical
    bearings. The masthead and the badge differ in three delivered ways, and only
    those three: the WATCH row's optical shift, the seconds hand's paper keyline
    and counterweight, and whether a dial treatment can appear at all.

    Both hour and minute hands carry a paper underlay rather than a box-shadow.
    A shadow is clipped away by clip-path, which is what made the badge's hands
    vanish over the ink letters — design's fix of 2026-08-04 04:04."""
    big = px == 46
    shift = "-3px" if big else "-.065em"
    hand_hour = (
        '<span style="position:absolute;left:-.17em;bottom:-.05em;width:.34em;height:1.2em;background:#f4f1ea;clip-path:polygon(50% 0,100% 12%,74% 100%,26% 100%,0 12%)"></span>'
        '<span style="position:absolute;left:-.12em;bottom:0;width:.24em;height:1.13em;background:#17130d;clip-path:polygon(50% 0,100% 12%,74% 100%,26% 100%,0 12%)"></span>'
    )
    hand_min = (
        '<span style="position:absolute;left:-.15em;bottom:-.05em;width:.3em;height:1.6em;background:#f4f1ea;clip-path:polygon(50% 0,100% 10%,72% 100%,28% 100%,0 10%)"></span>'
        '<span style="position:absolute;left:-.1em;bottom:0;width:.2em;height:1.53em;background:#17130d;clip-path:polygon(50% 0,100% 10%,72% 100%,28% 100%,0 10%)"></span>'
    )
    hand_sec = (
        '<span style="position:absolute;left:-.06em;bottom:-.45em;width:.12em;height:2.02em;background:#f4f1ea"></span>'
        '<span style="position:absolute;left:-.025em;bottom:-.4em;width:.05em;height:1.92em;background:#8a5a2b"></span>'
        '<span style="position:absolute;left:-.09em;bottom:-.5em;width:.18em;height:.18em;border-radius:50%;background:#8a5a2b;box-shadow:0 0 0 1px #f4f1ea"></span>'
        if big else
        '<span style="position:absolute;left:-.025em;bottom:-.4em;width:.05em;height:1.92em;background:#8a5a2b"></span>'
    )
    return f'''<span style="display:block;width:3.9em"><span style="display:flex;justify-content:space-between;width:3.6em;position:relative;left:{shift}"><span data-b="wl">W</span><span>A</span><span>T</span><span>C</span><span data-b="hr">H</span></span></span>
      <span style="position:relative;display:block;width:3.9em;height:1em">
        <span style="position:absolute;left:0;top:0;display:flex;justify-content:space-between;align-items:center;width:2.85em;height:1em"><span data-b="dl">D</span><span>R</span><span>O</span><span>P</span></span>
        <span style="position:absolute;right:0;top:.17em;width:.6em;height:.6em;border-radius:50%;background:#8a5a2b"><span style="position:absolute;left:50%;top:50%;width:0;height:0">
          <span style="position:absolute;left:-1.7em;top:-1.7em;width:3.4em;height:3.4em;border:1px solid #17130d;border-radius:50%;opacity:.6;clip-path:polygon(50% -3%, 103% -3%, 103% 103%, 34% 103%, 34% 60%, 50% 60%)"></span>
          {DATE_WINDOW}
          <span data-clock="hour" style="position:absolute;left:0;top:0;width:0;height:0;z-index:2;animation:wdi-spin 43200s linear infinite">{hand_hour}</span>
          <span data-clock="min" style="position:absolute;left:0;top:0;width:0;height:0;z-index:2;animation:wdi-spin 3600s linear infinite">{hand_min}</span>
          <span data-clock="sec" style="position:absolute;left:0;top:0;width:0;height:0;z-index:2;animation:wdi-spin 60s linear infinite">{hand_sec}</span>
          <span style="position:absolute;left:-.1em;top:-.1em;width:.2em;height:.2em;border-radius:50%;background:#17130d;z-index:3;box-shadow:0 0 0 1px #f4f1ea"></span>
        </span></span>
      </span>
      <span style="display:block;width:3.9em;position:relative"><span style="display:flex;justify-content:space-between;width:3.6em"><span data-b="il">I</span><span>N</span><span>D</span><span>E</span><span data-b="xr">X</span></span><span style="position:absolute;right:-.62em;bottom:.06em;font-size:.24em;color:#8a8071;letter-spacing:.08em;font-weight:600">™</span></span>'''


# The admin gate. Only the SHA-256 of Lowell's link token is published; the token
# itself lives at ~/.watchdrop-admin and is never committed. No file, no gate —
# the editor's journal simply cannot be reached, which is the right way to fail.
_hash_file = os.path.join(HERE, "admin-hash.txt")
ADMIN_HASH = ""
if os.path.exists(_hash_file):
    with open(_hash_file) as fh:
        ADMIN_HASH = fh.read().strip()

# Design's dateWindow prop. Shipped ON.
DATE_WINDOW_COLUMN = True

dom = meta.get("domain", "")
SCRIPT = (JS
          .replace("__HELP__", json.dumps(TIER_HELP, ensure_ascii=False))
          .replace("__MAKER__", json.dumps(MAKER_OVERRIDE, ensure_ascii=False))
          .replace("__SHORT__", json.dumps(SHORT_MODEL, ensure_ascii=False))
          .replace("__DATEWIN__", "true" if DATE_WINDOW_COLUMN else "false")
          .replace("__ADMINHASH__", ADMIN_HASH))
assert not re.search(r"__[A-Z]+__", SCRIPT), "an injection placeholder went unfilled"

SECTION_RULE = '<div style="width:26px;height:2px;background:#17130d;margin:{m}"></div>'
H2 = ('<h2 style="font-family:\'Newsreader\',serif;font-size:25px;font-weight:500;color:#17130d;'
      'margin:{m};letter-spacing:-.01em">{t}</h2>')
STAT_LABEL = ('font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;'
              'color:#8a8071;font-weight:700')
STAT_ROW = ('display:flex;justify-content:space-between;align-items:baseline;'
            'padding:9px 0;border-bottom:1px solid #e9e4d8')

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

  <div data-mq="utilwrap" style="max-width:1140px;margin:0 auto;padding:0 30px">
    <div data-mq="util" style="display:flex;justify-content:space-between;align-items:baseline;padding:11px 0 10px;border-bottom:1px solid #ddd6c8;font-size:10.5px;letter-spacing:.18em;text-transform:uppercase;color:#8a8071;font-weight:600">
      <span>{html.escape(dom)}</span>
      <span>Refreshed weekly<span data-mq="utc"> · Mondays 09:00 UTC</span></span>
    </div>
  </div>

  <header data-mq="hdr" style="max-width:1140px;margin:0 auto;padding:38px 30px 0">
    <div data-mq="hgrid" style="display:grid;grid-template-columns:1fr 1px 1fr;gap:0 48px;align-items:center">
    <div data-mq="hleft" style="justify-self:end;width:100%;max-width:460px;display:grid;justify-items:center;text-align:center;position:relative">
    <div id="lockup" data-logo-px="46" data-mq="lockup" aria-label="Watch Drop Index" style="display:grid;justify-items:center;row-gap:0;line-height:1;font-family:'Newsreader',serif;font-size:46px;font-weight:600;letter-spacing:0;color:#17130d;margin:0 auto;width:max-content">
      {lockup(46)}
    </div>
    <div data-mq="wide" style="display:flex;align-items:center;justify-content:center;gap:16px;margin:24px -48px 0 0;width:calc(100% + 48px);box-sizing:border-box;padding-left:0">
      <div style="flex:.25 1 0;height:1px;background:#c9c0ad"></div>
      <div style="font-size:11px;letter-spacing:.32em;text-transform:uppercase;color:#17130d;font-weight:600;white-space:nowrap">The Limited-Edition Register</div>
      <div style="flex:.25 1 0;height:1px;background:#c9c0ad"></div>
    </div>
    <p data-mq="wide" style="font-family:'Newsreader',serif;font-style:italic;font-size:15px;line-height:1.5;color:#5c5546;margin:6px -48px 0 0;text-wrap:balance;width:calc(100% + 48px);box-sizing:border-box;padding-left:0;text-align:center">Track Release &amp; Availability of Limited Edition Watches</p></div>
    <div data-mq="hdiv" style="background:#ddd6c8;align-self:stretch;min-height:180px"></div>
    <div data-mq="hstats" style="justify-self:start;width:100%;max-width:400px;font-variant-numeric:tabular-nums">
      <div style="font-size:10px;letter-spacing:.22em;text-transform:uppercase;color:#8a8071;font-weight:700;padding-bottom:8px">The register at a glance</div>
      <div style="border-top:2px solid #17130d">
        <div style="{STAT_ROW}"><span style="{STAT_LABEL}">Buyable online today</span><b id="t-buy" style="color:#1e6b41;font-weight:700;font-size:15px">{counts.get('Buy online now', 0)}</b></div>
        <div style="{STAT_ROW}"><span style="{STAT_LABEL}">Limited runs tracked</span><b id="t-total" style="color:#17130d;font-weight:700;font-size:15px">{len(_kept)}</b></div>
        <div style="{STAT_ROW}"><span style="{STAT_LABEL}">Confirmed gone</span><b id="t-gone" style="color:#17130d;font-weight:700;font-size:15px">{counts.get('Gone', 0)}</b></div>
        <div style="{STAT_ROW}"><span style="{STAT_LABEL}">Brands</span><b id="t-brands" style="color:#17130d;font-weight:700;font-size:15px">{len({i['brand'] for i in _kept})}</b></div>
        <div style="{STAT_ROW}"><span style="{STAT_LABEL}">Updated</span><span id="t-updated" style="color:#17130d;font-weight:600;font-size:13px">{html.escape(meta['updated'])}</span></div>
      </div>
    </div>
    </div>
  </header>

  <div id="fbarwrap" data-mq="fwrap" style="position:sticky;top:0;z-index:30;background:#f4f1ea;border-bottom:2px solid #17130d">
    <div id="fbar" data-mq="fbar" style="max-width:1200px;box-sizing:border-box;margin:0 auto;padding:12px 30px 13px 30px">
      <div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center">
        <span data-mq="flabel" style="font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:#8a8071;font-weight:700;width:112px;flex:none;white-space:nowrap">Availability:</span>
        <span id="tierBtns" style="display:contents"></span>
        <input id="q" data-mq="search" type="search" placeholder="Search brand, model, reference…" style="margin-left:auto;width:260px;padding:7px 12px;border:1px solid #ddd6c8;background:#fbf9f4;font-size:13px;font-family:'Archivo',sans-serif;color:#17130d;border-radius:0;outline:none">
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:8px">
        <span data-mq="flabel" style="font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:#8a8071;font-weight:700;width:112px;flex:none;white-space:nowrap">Price:</span>
        <span id="bandBtns" style="display:contents"></span>
        <button id="reset" data-mq="preset" style="border:none;background:none;padding:5px 10px;font-size:12px;font-family:'Archivo',sans-serif;color:#8a5a2b;cursor:pointer;text-decoration:underline;text-underline-offset:3px">Reset</button>
        <select id="sort" data-mq="sort" style="margin-left:auto;width:150px;padding:6px 8px;border:1px solid #ddd6c8;background:#fbf9f4;font-size:12.5px;font-family:'Archivo',sans-serif;color:#17130d;border-radius:0;cursor:pointer">
          <option value="tier">Sort by</option>
          <option value="date">Newest first</option>
          <option value="brand">Brand A–Z</option>
          <option value="priceAsc">Price: low to high</option>
          <option value="priceDesc">Price: high to low</option>
          <option value="edition">Smallest edition first</option>
        </select>
      </div>
    </div>
  </div>

  <main id="main" data-mq="main" style="max-width:1200px;box-sizing:border-box;margin:0 auto;padding:0 30px 0 30px">

    <!-- The header's Brand label carries the same 175px + 11px gap as the row
         below it, so "Model" sits exactly over the model column. All five
         labels sort; JS only writes the ▾/▴ into the arr- spans. -->
    <div data-mq="colh" style="display:grid;grid-template-columns:16px minmax(0,1fr) 92px 70px 112px 16px;gap:14px;padding:10px 4px 8px 2px;font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:#8a8071;font-weight:700">
      <span></span><span style="display:flex;gap:11px"><span class="wdi-sort" data-sortcol="brand" role="button" tabindex="0" style="width:175px;flex:none;cursor:pointer;white-space:nowrap">Brand<span id="arr-brand"></span></span><span class="wdi-sort" data-sortcol="model" role="button" tabindex="0" style="cursor:pointer;white-space:nowrap">Model<span id="arr-model"></span></span></span><span class="wdi-sort" data-sortcol="date" role="button" tabindex="0" style="text-align:right;border-left:1px solid #ddd6c8;align-self:stretch;display:flex;align-items:center;justify-content:flex-end;cursor:pointer;white-space:nowrap">Released<span id="arr-date"></span></span><span class="wdi-sort" data-sortcol="edition" role="button" tabindex="0" style="text-align:right;border-left:1px solid #ddd6c8;align-self:stretch;display:flex;align-items:center;justify-content:flex-end;cursor:pointer;white-space:nowrap">Edition<span id="arr-edition"></span></span><span class="wdi-sort" data-sortcol="price" role="button" tabindex="0" style="text-align:right;border-left:1px solid #ddd6c8;align-self:stretch;display:flex;align-items:center;justify-content:flex-end;cursor:pointer;white-space:nowrap">USD<span id="arr-price"></span></span><span></span>
    </div>

    <div id="loading" style="padding:70px 0;text-align:center;font-family:'Newsreader',serif;font-style:italic;font-size:17px;color:#8a8071;border-top:2px solid #17130d">Loading the register…</div>
    <div id="empty" style="display:none;padding:70px 0;text-align:center;font-family:'Newsreader',serif;font-style:italic;font-size:17px;color:#8a8071;border-top:2px solid #17130d">Nothing matches those filters.</div>

    <div id="list" style="border-top:2px solid #17130d"></div>

    <!-- Editor's journal. Rendered to the reference exactly, but it only ever
         mounts for an unlocked admin (see adminUnlocked() in the script) — on
         the live site the query string alone is not a gate. -->
    <!-- The write path. Same gate as the journal: it only ever mounts for an
         unlocked admin, and on the live site the query string alone is not a
         gate. Read-only until a token is pasted, and visibly so — a save button
         that looks armed and quietly does nothing is worse than a disabled one,
         because the edit appears to have been made. -->
    <section id="adminPanel" style="display:none">
      <div style="width:26px;height:2px;background:#8a5a2b;margin:64px 0 0"></div>
      {H2.format(m='12px 0 4px', t='The register — editing')}
      <p style="color:#8a8071;font-size:13.5px;margin:0 0 14px;max-width:720px">Edits here commit straight to <code>data.json</code> on <code>main</code>, which on this repository is the deploy. Every save is previewed first, names what it changed, and is one click from being reverted. Fields you edit become <b>yours</b>: the refresh job may propose a change to them and will never make one.</p>
      <div id="adminBody"></div>
    </section>

    <section id="journal" style="display:none">
      <div style="width:26px;height:2px;background:#8a5a2b;margin:64px 0 0"></div>
      {H2.format(m='12px 0 4px', t="Editor's journal — name changes")}
      <p style="color:#8a8071;font-size:13.5px;margin:0 0 10px;max-width:720px">Every entry whose ledger name differs from the register data, and the source of the change. Your corrections apply immediately on this device and export for the weekly job. Rows carry a bronze ° where a name or description has been changed. Descriptions are edited inside the entry — open its row.</p>
      <div style="display:flex;align-items:baseline;gap:16px;margin:0 0 14px">
        <button id="copyPatch" class="wdi-ghost" style="border:1px solid #17130d;background:none;padding:6px 12px;font-family:'Archivo',sans-serif;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#17130d;cursor:pointer">Copy corrections JSON</button>
        <span id="ovCount" style="font-size:12px;color:#8a8071;font-variant-numeric:tabular-nums"></span>
      </div>
      <div id="journalRows" style="border-top:2px solid #17130d"></div>
    </section>

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

    <section data-mq="two" style="display:grid;grid-template-columns:1fr 1fr;gap:44px">
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
      <div data-mq="two" style="display:grid;grid-template-columns:1fr 1fr;gap:44px">
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
      <p style="margin-top:30px;padding-top:14px;border-top:1px solid #e9e4d8;font-size:11px;letter-spacing:.14em;text-transform:uppercase;font-weight:600;text-align:center;color:#8a8071">Watch Drop Index · {html.escape(dom)} · revision <span id="c-rev">{meta['revision']}</span> · <span id="c-imgs">{sum(1 for i in _kept if i.get('image'))}</span> of <span id="c-total">{len(_kept)}</span> photographs resolved · every entry links to the source it came from</p>
      <p style="margin-top:10px;font-size:10px;letter-spacing:.1em;text-align:center;color:#a09786">WATCH DROP INDEX™ is a trademark of Conn LLC, Toronto, Ontario, Canada. All rights reserved.</p>
    </footer>

  </main>

  <!-- The enlarged photograph. Lowell's ask, 2026-08-05. Mechanism only: this
       is deliberately plain — every value below is from the approved palette
       and nothing decorative has been invented. FLAGGED TO DESIGN for a
       treatment; the markup is stable and the CSS is theirs to replace.
       It stays on the page, so it does not touch the one-outbound-click rule. -->
  <div id="lightbox" role="dialog" aria-modal="true" aria-label="Photograph" tabindex="-1"
       style="display:none;position:fixed;inset:0;z-index:60;background:rgba(23,19,13,.94);
              align-items:center;justify-content:center;flex-direction:column;gap:16px;
              padding:28px;box-sizing:border-box;cursor:zoom-out">
    <img id="lightboxImg" alt="" referrerpolicy="no-referrer"
         style="display:block;max-width:94vw;max-height:82vh;width:auto;height:auto;border:1px solid #3a342b">
    <div id="lightboxCap" style="font-size:11px;letter-spacing:.04em;color:#c9c0ad;text-align:center;max-width:70ch"></div>
  </div>

  <div id="badgeHost"></div>
  <template id="badgeTpl"><div class="wdi-badge" data-logo-px="20" data-mq="badge" role="button" tabindex="0" title="Back to top" style="position:fixed;right:24px;bottom:22px;z-index:40;display:grid;justify-items:center;row-gap:0;line-height:1;font-family:'Newsreader',serif;font-size:20px;font-weight:600;letter-spacing:0;color:#17130d;cursor:pointer;background:#f4f1ea;border:1px solid #c9c0ad;padding:16px 44px 16px 18px;box-shadow:0 6px 26px rgba(23,19,13,.28);animation:wdi-badge-in .6s cubic-bezier(.22,.61,.36,1) both">{lockup(20)}</div></template>
  {DIAL_TEMPLATES}
</div>
<script>{SCRIPT}</script>
</body></html>
"""

with open(os.path.join(HERE, "index.html"), "w") as fh:
    fh.write(HTML)
print(f"built index.html — template only; entries load from data.json at runtime")
_filterable = sum(counts.get(t, 0) for t in FILTERABLE)
print(f"  register: {len(_kept)} entries · {_filterable} in the four filterable tiers")
print(f"  buyable online: {counts.get('Buy online now', 0)} · gone: {counts.get('Gone', 0)} · size: {len(HTML)//1024} KB")
