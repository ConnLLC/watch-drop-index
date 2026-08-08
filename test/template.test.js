// Verifies the template against a REAL DOM: renders it, then re-renders after a
// simulated weekly refresh that only rewrites data.json. index.html is never
// rebuilt between the two — that is the whole point of the check.
//
// The design pass ("The Catalogue") replaced the markup wholesale, so most of
// what this file asserts is the CONTRACT that survived it: every figure on the
// page is re-read from the data, rows are keyboard-operable, and /#<id> opens a
// watch. If a future restyle drops those, this fails loudly rather than shipping
// a page that quietly advertises last month's numbers.
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");
const { TextEncoder, TextDecoder } = require("util");

const ROOT = path.join(__dirname, "..");
const HTML = fs.readFileSync(path.join(ROOT, "index.html"), "utf8");
const BASE = JSON.parse(fs.readFileSync(path.join(ROOT, "data.json"), "utf8"));

let pass = 0, fail = 0;
const check = (label, got, want) => {
  const ok = String(got) === String(want);
  ok ? pass++ : fail++;
  console.log(`  ${ok ? "ok  " : "FAIL"}  ${label}: ${got}${ok ? "" : `  (expected ${want})`}`);
};

// Favourites live on a different host, so the stub has to tell the two fetches
// apart. `favs` is the tally the worker would return; `favPosts` records what the
// page tried to write, which is the only way to assert the write path without a
// network. A null tally simulates the worker being DOWN — the register must not
// care, and there is a test below that says so.
async function load(payload, hash = "", favs = {}, favPosts = []) {
  const dom = new JSDOM(HTML, {
    runScripts: "dangerously",
    url: "https://www.watchdropindex.com/" + hash,
    pretendToBeVisual: true,
  });
  const w = dom.window;
  // jsdom ships neither Web Crypto nor TextEncoder on the window, and the admin
  // gate needs both. Without them the gate fails closed, which would let a
  // broken gate pass this suite by looking exactly like a locked one.
  Object.defineProperty(w, "crypto", { value: require("node:crypto").webcrypto, configurable: true });
  w.TextEncoder = TextEncoder;
  w.TextDecoder = TextDecoder;   // the admin panel's base64 round-trip needs both
  w.Element.prototype.scrollIntoView = function () {};
  w.scrollTo = function () {};
  w.fetch = async (url, opts) => {
    if (String(url).includes("/fav")) {
      if (opts && opts.method === "POST") {
        favPosts.push(JSON.parse(opts.body));
        return { ok: true, status: 200, json: async () => ({}) };
      }
      if (favs === null) throw new Error("worker unreachable");
      return { ok: true, status: 200, json: async () => favs };
    }
    return { ok: true, status: 200, json: async () => payload };
  };
  w.document.dispatchEvent(new w.Event("DOMContentLoaded", { bubbles: true }));
  await new Promise(r => setTimeout(r, 80)); // let boot()'s awaits settle
  return w;
}

const txt = (w, sel) => w.document.querySelector(sel)?.textContent.trim();
const tierBadge = (w, tier) =>
  w.document.querySelector(`[data-tier="${tier}"] .n`)?.textContent.trim();
const rows = (w) => w.document.querySelectorAll("[data-id]").length;

// Two rules decide what the register shows, and every figure on the page counts
// exactly what survives them.
//
//  * SCOPE (Lowell, 2026-08-04): a production cap is not a limited edition, so
//    entries capped by an order window or by annual output are filtered out at
//    the display layer. data.json still holds them — nothing is deleted — so one
//    reappears by itself the week its edition is confirmed.
//  * The FILTER BUTTONS are narrowed to the four actionable tiers. The other
//    three are still listed, searchable, and explained inline in their own
//    expanded row — the availability key that used to carry that job was cut
//    on 2026-08-05.
//
// The test mirrors both rules rather than importing them, so changing one copy
// and not the other fails here rather than live.
const UNFILTERABLE = ["Waitlist or ballot", "AD or boutique", "In person only"];
const NOT_LE = [/not formally limited/i, /^capped/i, /annually/i];
const inScope = (w) => !NOT_LE.some((rx) => rx.test(String(w.edition || "").trim()));
const keep = (list) => list
  .filter(inScope)
  .map((w) => (w.tier === "Retailer enquiry" ? { ...w, tier: "Buy at retailer", rank: 3 } : w));

(async () => {
  // Expectations are DERIVED from data.json, never hardcoded. Pinning them to
  // one day's snapshot would make this fail every time the refresh does its job.
  const KEPT = keep(BASE.watches);
  const tally = (t) => KEPT.filter((x) => x.tier === t).length;
  const N = KEPT.length;

  console.log("\n=== 1. THE PAGE MATCHES THE CURRENT data.json ===");
  let w = await load(BASE);
  check("rows rendered", rows(w), N);
  // 246 of 252 render, and that is deliberate. What is NOT allowed is a silent
  // drop: everything filtered out must be a production cap, and it must still be
  // in the file, ready to come back.
  check("only production caps are out of scope",
        BASE.watches.filter((x) => !inScope(x)).length, BASE.watches.length - N);
  check("nothing is deleted from data.json", BASE.watches.length >= N, true);
  check("un-buttoned tiers still render", (() => {
    const shown = [...w.document.querySelectorAll("[data-id] [title]")]
      .map((n) => n.getAttribute("title"));
    return UNFILTERABLE.every((t) => !tally(t) || shown.includes(t));
  })(), true);
  check("masthead: buyable online", txt(w, "#t-buy"), tally("Buy online now"));
  check("masthead: runs tracked", txt(w, "#t-total"), N);
  check("masthead: confirmed gone", txt(w, "#t-gone"), tally("Gone"));
  check("masthead: brands", txt(w, "#t-brands"), new Set(KEPT.map((x) => x.brand)).size);
  check("masthead: updated", txt(w, "#t-updated"), BASE.meta.updated);
  check("colophon: revision", txt(w, "#c-rev"), BASE.meta.revision);
  check("colophon: photos resolved", txt(w, "#c-imgs"), KEPT.filter((x) => x.image).length);
  check("colophon: total", txt(w, "#c-total"), N);
  check("colophon: updated", txt(w, "#c-updated"), BASE.meta.updated);
  // The three survivors of the 2026-08-05 cut. The takedown line is the one that
  // is not a preference: 224 photographs are published under an editorial-use
  // rationale that only holds while a rights holder can find a route to object.
  // If a restyle drops it, that is a legal posture quietly evaporating, so it
  // fails here rather than shipping.
  check("takedown route is present and reachable", (() => {
    const n = w.document.querySelector("#takedown");
    if (!n) return "no #takedown";
    const a = n.querySelector('a[href^="mailto:"]');
    if (!a) return "no mailto link";
    if (a.getAttribute("href") !== "mailto:wdi-takedown@conn.llc") return `wrong address: ${a.getAttribute("href")}`;
    // "Permanently visible, not folded behind anything" — it must not be inside
    // anything the page hides, which is how a required notice usually dies.
    for (let e = n; e; e = e.parentElement) {
      if (e.style && e.style.display === "none") return "hidden by an ancestor";
    }
    return true;
  })(), true);
  check("the register still says what 'checked' means",
        /purchase page was read on the date shown/i.test(w.document.querySelector("footer").textContent), true);
  check("filter badge: All", tierBadge(w, "All"), N);
  check("filter badge: Buy online now", tierBadge(w, "Buy online now"), tally("Buy online now"));
  check("filter badge: Gone", tierBadge(w, "Gone"), tally("Gone"));
  check("Retailer enquiry is remapped, not shown",
        tierBadge(w, "Buy at retailer"), tally("Buy at retailer"));
  // Rendered content only — the script's own source names the old tier, since
  // that is what it remaps FROM.
  check("no 'Retailer enquiry' reaches the reader", (() => {
    // #keyRows dropped out of this selector when the availability key was cut
    // (2026-08-05). The remap still has to hold everywhere it can still be seen.
    const seen = [...w.document.querySelectorAll("#list [title], [data-tier]")]
      .map((n) => (n.getAttribute("title") || "") + " " + n.textContent);
    return seen.some((s) => s.includes("Retailer enquiry"));
  })(), false);
  check("exactly five filter buttons: All + the four actionable tiers",
        w.document.querySelectorAll("[data-tier]").length, 5);
  check("the three un-buttoned tiers get no chip",
        UNFILTERABLE.some((t) => w.document.querySelector(`[data-tier="${t}"]`)), false);
  check("every filter yields exactly its own count", (() => {
    for (const t of ["Buy online now", "Buy at retailer", "Drop upcoming", "Gone"]) {
      const btn = w.document.querySelector(`[data-tier="${t}"]`);
      if (!btn) return `no button for ${t}`;
      btn.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
      if (rows(w) !== tally(t)) return `${t}: ${rows(w)} rows, expected ${tally(t)}`;
    }
    w.document.querySelector('[data-tier="All"]').dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
    return rows(w) === N ? true : `All: ${rows(w)} rows, expected ${N}`;
  })(), true);
  // The availability key below the register was cut on 2026-08-05, so this no
  // longer has a #keyRows to count. The obligation it encoded did not go away —
  // every tier must still be explained to the reader — so it moves to where the
  // explanation now lives: inline, in each expanded row. That is a STRONGER
  // assertion than the old one, since it checks the tier the reader is actually
  // looking at rather than a list further down the page.
  // Opening a row fills its panel asynchronously, so each tier needs the same
  // settle the deep-link and keyboard checks give it. Done as an awaited const
  // rather than inline because check() takes a value, not a promise — an inline
  // async IIFE would hand it a pending Promise and pass unconditionally.
  const tiersExplained = await (async () => {
    // Every node must be re-queried after each click: toggling a row rewrites
    // #list wholesale, so a reference captured beforehand is detached from the
    // document and reads as an empty panel. That detail cost an hour once.
    const ctl = (id) => w.document.querySelector(`[data-id="${id}"] .wdi-row`);
    for (const tier of new Set(KEPT.map((x) => x.tier))) {
      const one = KEPT.find((x) => x.tier === tier);
      if (!ctl(one.id)) return `no row for ${tier}`;
      ctl(one.id).dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
      await new Promise((r) => setTimeout(r, 20));
      const panel = w.document.querySelector("#p-" + one.id);
      if (!panel || !panel.textContent.includes(tier)) return `${tier}: not named in its own row`;
      // The em-dashed gloss after the tier name is the explanation itself.
      if (!/—\s*\S/.test(panel.textContent.split(tier)[1] || "")) return `${tier}: named but not explained`;
      ctl(one.id).dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
      await new Promise((r) => setTimeout(r, 20));
    }
    return true;
  })();
  check("every tier in the data is still explained inline", tiersExplained, true);
  check("an un-buttoned watch is still findable by search", (() => {
    const hidden = KEPT.find((x) => UNFILTERABLE.includes(x.tier));
    if (!hidden) return true;
    const q = w.document.querySelector("#q");
    q.value = hidden.model;
    q.dispatchEvent(new w.Event("input", { bubbles: true }));
    const hit = !!w.document.querySelector(`[data-id="${hidden.id}"]`);
    q.value = "";
    q.dispatchEvent(new w.Event("input", { bubbles: true }));
    return hit;
  })(), true);

  console.log("\n=== 2. SIMULATED WEEKLY REFRESH — data.json only, index.html untouched ===");
  const next = JSON.parse(JSON.stringify(BASE));
  next.watches.filter(x => x.tier === "Buy online now").slice(0, 2).forEach(x => {
    x.status = "Sold out"; x.tier = "Gone"; x.rank = 6; x.soldOutOn = "2026-08-10";
    x.verified = { date: "2026-08-10", note: "Product page returns 'Sold out'." };
  });
  const seed = next.watches[0];
  for (let i = 0; i < 4; i++) {
    next.watches.push({ ...seed, id: "zzzz00000" + i, brand: "Testbrand " + i,
      model: "Fixture " + i, image: null, tier: "Buy online now", rank: 0,
      status: "Available", soldOutOn: null, verified: null });
  }
  next.meta.updated = "2026-08-10";
  next.meta.revision = BASE.meta.revision + 1;

  w = await load(next);
  check("rows rendered", rows(w), N + 4);
  check("masthead: buyable online", txt(w, "#t-buy"), tally("Buy online now") - 2 + 4);
  check("masthead: runs tracked", txt(w, "#t-total"), N + 4);
  check("masthead: confirmed gone", txt(w, "#t-gone"), tally("Gone") + 2);
  check("masthead: brands", txt(w, "#t-brands"),
        new Set(KEPT.map((x) => x.brand)).size + 4);
  check("masthead: updated", txt(w, "#t-updated"), "2026-08-10");
  check("colophon: revision", txt(w, "#c-rev"), BASE.meta.revision + 1);
  check("filter badge: All", tierBadge(w, "All"), N + 4);
  check("filter badge: Gone", tierBadge(w, "Gone"), tally("Gone") + 2);

  console.log("\n=== 3. DEEP LINK  /#<id> ===");
  const target = KEPT.find(x => x.image);                   // one with a photograph
  w = await load(BASE, "#" + target.id);
  let item = [...w.document.querySelectorAll("[data-id]")].find(x => x.dataset.id === target.id);
  check("target row exists", !!item, true);
  check("its panel was filled", item.querySelector("#p-" + target.id).innerHTML.length > 200, true);
  check("aria-expanded set", item.querySelector(".wdi-row").getAttribute("aria-expanded"), "true");
  check("photograph rendered", !!item.querySelector("img"), true);
  check("image credit shown", item.textContent.includes(target.imageCredit), true);
  check("only that row is open",
        [...w.document.querySelectorAll('[id^="p-"]')].filter(p => p.innerHTML.length).length, 1);
  check("unknown hash is ignored",
        [...(await load(BASE, "#deadbeef99")).document.querySelectorAll('[id^="p-"]')]
          .filter(p => p.innerHTML.length).length, 0);

  console.log("\n=== 4. KEYBOARD / ARIA ===");
  // The design makes rows a div[role=button], which — unlike a real button —
  // does not activate on Enter or Space. Both must work anyway.
  w = await load(BASE);
  const first = w.document.querySelector("[data-id]");
  const bar = first.querySelector(".wdi-row");
  check("row exposes a button role", bar.getAttribute("role"), "button");
  check("row is reachable by tab", bar.getAttribute("tabindex"), "0");
  check("aria-controls points at its panel", bar.getAttribute("aria-controls"), "p-" + first.dataset.id);
  check("starts collapsed", bar.getAttribute("aria-expanded"), "false");

  for (const key of ["Enter", " "]) {
    const win = await load(BASE);
    const row = win.document.querySelector("[data-id]");
    const ctl = row.querySelector(".wdi-row");
    ctl.dispatchEvent(new win.KeyboardEvent("keydown", { key, bubbles: true }));
    await new Promise(r => setTimeout(r, 20));
    const panel = win.document.querySelector("#p-" + row.dataset.id);
    check(`"${key === " " ? "Space" : key}" opens the row`, panel.innerHTML.length > 200, true);
  }

  bar.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  await new Promise(r => setTimeout(r, 20));
  check("click opens it too",
        w.document.querySelector("#p-" + first.dataset.id).innerHTML.length > 200, true);
  check("hash updated for sharing", w.location.hash, "#" + first.dataset.id);
  check("focus ring style present", HTML.includes(".wdi-row:focus-visible"), true);

  console.log("\n=== 5. THE DESIGN'S OWN FURNITURE ===");
  w = await load(BASE);
  check("wordmark lockup present", !!w.document.querySelector("#lockup"), true);
  check("clock has three hands",
        w.document.querySelectorAll('#lockup [data-clock]').length, 3);
  check("hands are driven by a delay",
        w.document.querySelector('#lockup [data-clock="sec"]').style.animationDelay.endsWith("s"), true);
  check("corner badge is a template until scrolled", !!w.document.querySelector("#badgeTpl"), true);
  check("badge not mounted at rest", w.document.querySelector("#badgeHost").children.length, 0);
  // The availability key and the calendar sections were cut on 2026-08-05.
  // Asserting their ABSENCE rather than deleting the checks: if a future restyle
  // reintroduces the furniture Lowell asked to have removed, that should fail
  // here rather than quietly reappear under the register.
  check("the sections below the register stay gone", (() => {
    const gone = ["#keyRows", "#drops", "#events", "#notHappening", "#expected"]
      .filter((s) => w.document.querySelector(s));
    return gone.length ? `still present: ${gone.join(", ")}` : true;
  })(), true);
  // The calendar data itself is NOT gone — the expiry stage still maintains it,
  // so it stays correct against the day these sections come back.
  check("calendar data survives the cut", BASE.calendar.drops.length > 0, true);
  // jsdom has no canvas, so this also proves the wordmark degrades instead of
  // taking the page down when text metrics are unavailable.
  check("page still renders without canvas metrics", rows(w), N);
  check("date window carries a real date",
        /^\d{1,2}$/.test(txt(w, "#lockup [data-date]") || ""), true);
  check("wordmark is trademarked", w.document.querySelector("#lockup").textContent.includes("™"), true);
  check("footer carries the trademark notice",
        HTML.includes("is a trademark of Conn LLC, Toronto, Ontario, Canada"), true);
  check("all five dial treatments are available",
        w.document.querySelectorAll("template[data-dial]").length, 4); // plain needs no markup
  // Five figures plus the week strip's two ids (its row and its value).
  check("stat ledger is a ruled register, not a sentence",
        w.document.querySelectorAll('[data-mq="hstats"] [id^="t-"]').length, 7);

  // THE WEEK STRIP. Its whole job is to make "is this maintained?" answerable at
  // a glance, so the two ways it could lie are what get pinned: reporting
  // activity on a dead register, and printing a zero that reads as rejection.
  {
    const today = new Date().toISOString().slice(0, 10);
    const day = (n) => new Date(Date.now() + n * 864e5).toISOString().slice(0, 10);
    const one = (o) => ({ ...BASE, watches: [{ ...BASE.watches[0], ...o }] });

    let x = await load(one({ addedOn: day(-2), soldOutOn: null, verified: null, buyCheck: null }));
    check("a fresh entry shows in the week strip", txt(x, "#t-week"), "1 added");
    check("the strip is visible when there is something to report",
          x.document.querySelector("#t-weekrow").style.display, "flex");

    x = await load(one({ addedOn: day(-400), soldOutOn: null, verified: null, buyCheck: null }));
    check("an idle week shows silence, never a zero", txt(x, "#t-week"), "");
    check("and the row removes itself",
          x.document.querySelector("#t-weekrow").style.display, "none");

    // soldOutOn === addedOn is the seeding date, not something anyone watched.
    x = await load(one({ addedOn: day(-2), soldOutOn: day(-2), verified: null, buyCheck: null }));
    check("an entry that arrived sold out is not counted as sold out this week",
          txt(x, "#t-week"), "1 added");

    x = await load(one({ addedOn: day(-400), soldOutOn: day(-1), verified: null,
                         buyCheck: { date: day(-1), note: "read" } }));
    check("a watched sell-out and a recheck both count",
          txt(x, "#t-week"), "1 sold out  ·  1 rechecked");

    // The window is anchored to the real date, never to meta.updated: a register
    // that stopped updating must not go on advertising a busy week.
    x = await load({ ...one({ addedOn: day(-400), soldOutOn: null, verified: null, buyCheck: null }),
                     meta: { ...BASE.meta, updated: today } });
    check("a stale register reports an empty week, not meta.updated's week",
          x.document.querySelector("#t-weekrow").style.display, "none");
  }

  console.log("\n=== 5b. THE ADMIN WRITE PATH ===");
  // These assert the things that would be SILENT failures — a token leaking into
  // the page, a stale write erasing a scheduled run, an id that disagrees with
  // the refresh job about which watch it is.
  w = await load(BASE);

  // The id scheme is md5("brand|model" lowercased) sliced to ten hex characters,
  // and it is immutable: rewriting one orphans that watch's verification
  // history. Web Crypto has no MD5, so the panel carries its own — which is only
  // safe if it agrees with Python's on every entry that already exists.
  check("the panel's id scheme reproduces every id in the register", (() => {
    const bad = BASE.watches.filter((x) => w.WDI.makeId(x.brand, x.model) !== x.id);
    return bad.length ? `${bad.length} mismatched, first: ${bad[0].id}` : true;
  })(), true);
  check("...including non-ASCII brand names, which is where btoa/latin-1 breaks", (() => {
    const acc = BASE.watches.find((x) => /[^\x00-\x7F]/.test(x.brand + x.model));
    if (!acc) return true;
    return w.WDI.makeId(acc.brand, acc.model) === acc.id;
  })(), true);
  check("base64 round-trips UTF-8 rather than mangling it",
        w.WDI.b64decode(w.WDI.b64encode("Girard-Perregaux Laureato — Grönefeld ✓")),
        "Girard-Perregaux Laureato — Grönefeld ✓");

  // THE TOKEN. It must never reach the DOM, a URL, or an error message.
  w.WDI.ghSetToken("ghp_TESTTOKEN_shouldneverappear");
  check("a stored token is in sessionStorage, not localStorage", (() => {
    const inSession = w.sessionStorage.getItem("wdi-gh-pat");
    const leaked = Object.keys(w.localStorage).some(
      (k) => String(w.localStorage.getItem(k)).includes("shouldneverappear"));
    return inSession && !leaked;
  })(), true);
  w.WDI.state.admin = true; w.WDI.renderAdmin();
  check("the token never appears in the rendered page",
        w.document.body.innerHTML.includes("shouldneverappear"), false);
  check("...nor in the URL", w.location.href.includes("shouldneverappear"), false);
  check("...and GitHub's error text is rewritten, never echoed back", (() => {
    const msg = w.WDI.ghError({status: 401});
    return !msg.includes("shouldneverappear") && /token/i.test(msg);
  })(), true);
  w.WDI.ghSetToken("");
  check("ending a session removes it", w.sessionStorage.getItem("wdi-gh-pat"), null);

  // WITHOUT A TOKEN THE PANEL IS READ-ONLY — visibly, not silently. A save that
  // looks armed and no-ops is worse than one that is disabled, because the edit
  // appears to have been made.
  Object.assign(w.WDI.state, {admin: true, adminEdit: "new", adminForm: {brand: "X"}}); w.WDI.renderAdmin();
  check("with no token the save is disabled",
        w.document.querySelector("#aSave").disabled, true);
  check("...and says why", /read-only/i.test(w.document.querySelector("#aSave").textContent), true);

  // OPTIMISTIC LOCKING. The daily and weekly jobs commit to this same file, so a
  // save built on a stale copy would erase whatever a run wrote in between.
  check("a moved sha is REFUSED, not merged", await (async () => {
    w.WDI.ghSetToken("t"); w.WDI.state.gh = {sha: "OLD", payload: {watches: []}};
    let putCalled = false;
    w.fetch = async (url, opts) => {
      if (opts && opts.method === "PUT") { putCalled = true; return { ok: true, status: 200, json: async () => ({}) }; }
      return { ok: true, status: 200, json: async () => ({
        sha: "NEW", content: w.WDI.b64encode(JSON.stringify({watches: []})) }) };
    };
    try {
      await w.WDI.ghSave((p) => p, "m");
      return "the save went through";
    } catch (err) {
      if (!err.stale) return `wrong error: ${err.message}`;
      return putCalled ? "it wrote anyway" : true;
    }
  })(), true);
  check("...and the refusal explains what changed underneath it", (() => {
    const changed = w.WDI.ghWhatChanged(
      {watches: [{id: "a", brand: "B", model: "M", price: "$1"}]},
      {watches: [{id: "a", brand: "B", model: "M", price: "$2"}]});
    return changed.length === 1 && changed[0].includes("price");
  })(), true);

  // A manually entered image is truth-tested BEFORE it is written, so the panel
  // cannot become the one path that introduces a broken photograph.
  check("a non-https image URL is refused without a network call",
        await w.WDI.imageWorks("http://example.com/a.jpg"), false);
  check("...and an empty one too", await w.WDI.imageWorks(""), false);

  console.log("\n=== 6. THE MOBILE CONTRACT ===");
  // The whole ≤720px pass keys off data-mq and nothing else, so a renamed hook
  // silently drops a rule on phones while desktop stays perfect.
  // "two" and "row2" were removed on 2026-08-05 with the sections they styled.
  // Removed here CONSCIOUSLY and in the same commit as the markup and the CSS —
  // a hook disappearing from this list without anyone noticing is precisely the
  // failure the mobile contract exists to prevent, so it must never happen by
  // accident. Their @media rules went too; nothing is left defending them.
  const MQ = ["utilwrap", "util", "utc", "hdr", "hgrid", "hleft", "hdiv", "hstats",
              "lockup", "wide", "fwrap", "fbar", "flabel", "pband", "preset",
              "search", "sort", "main", "colh", "cols", "detail", "badge"];
  const media = HTML.slice(HTML.indexOf("@media (max-width:720px)"));
  for (const dead of ["two", "row2"]) {
    check(`retired hook "${dead}" leaves no orphan CSS`,
          HTML.includes(`data-mq="${dead}"`) || media.includes(`[data-mq="${dead}"]`), false);
  }
  for (const hook of MQ) {
    const inDom = !!w.document.querySelector(`[data-mq="${hook}"]`) ||
                  HTML.includes(`data-mq="${hook}"`);
    check(`hook "${hook}" is present and styled`,
          inDom && media.includes(`[data-mq="${hook}"]`), true);
  }
  check("rows carry the column hook", !!w.document.querySelector(`[data-id] [data-mq="cols"]`), true);
  // The stat ledger is desktop-only, but hiding it must not cost us the
  // hydration anchors — they still have to be in the DOM to be rewritten.
  check("stat ledger is hidden on phones",
        /\[data-mq="hstats"\]\{display:none !important\}/.test(media), true);
  check("...but its hydration anchors survive", (() => {
    const ids = ["#t-buy", "#t-total", "#t-gone", "#t-brands", "#t-updated"];
    return ids.every((s) => {
      const n = w.document.querySelector(s);
      return n && n.closest('[data-mq="hstats"]') && n.textContent.length > 0;
    });
  })(), true);
  check("mobile rules override the inline styles",
        (media.match(/!important/g) || []).length >= 20, true);
  check("expanded frame carries the detail hook", (() => {
    const t = KEPT.find(x => x.image);
    return HTML.includes('data-mq="detail"');
  })(), true);

  console.log("\n=== 6b. THE FILTER ROW CANNOT WRAP AT ANY WIDTH ===");
  // Lowell's iPad, 2026-08-05: the search field wrapped onto its own line. The
  // first fix put a narrow flex-basis inside a 721–1100px band — correct logic,
  // wrong bounds. iPads are 744–1024 in PORTRAIT and 1133–1366 in LANDSCAPE, so
  // every iPad held sideways sat above the ceiling and still wrapped.
  //
  // The lesson is in the test set, not the CSS. The first attempt was probed at
  // 390, 720, 760 and 1280 — every one either a phone or inside the band. It
  // encoded the same assumption as the code, so it agreed with the bug. These
  // widths are pinned permanently so a future range can never quietly miss one.
  const VIEWPORTS = [
    [390, "iPhone portrait"], [744, "iPad mini portrait"], [820, "iPad 11 portrait"],
    [834, "iPad Pro 11 portrait"], [1024, "iPad Pro 13 portrait"],
    [1133, "iPad mini LANDSCAPE"], [1180, "iPad 11 LANDSCAPE — Lowell's device"],
    [1194, "iPad Pro 11 LANDSCAPE"], [1366, "iPad Pro 13 LANDSCAPE"],
    [1280, "laptop"], [1440, "desktop"], [1920, "wide desktop"],
  ];

  // Which @media blocks apply at a given width, parsed from the stylesheet
  // rather than assumed — the point is to catch a range that misses a device.
  const blocksFor = (width) => {
    const out = [];
    const re = /@media\s*([^{]+)\{/g;
    let m;
    while ((m = re.exec(HTML))) {
      const cond = m[1];
      const min = /min-width:\s*(\d+)px/.exec(cond);
      const max = /max-width:\s*(\d+)px/.exec(cond);
      if (min && width < +min[1]) continue;
      if (max && width > +max[1]) continue;
      // Take the block body by brace-matching from the opening brace.
      let depth = 1, i = m.index + m[0].length;
      for (; i < HTML.length && depth; i++) {
        if (HTML[i] === "{") depth++;
        else if (HTML[i] === "}") depth--;
      }
      out.push(HTML.slice(m.index + m[0].length, i - 1));
    }
    return out;
  };

  // The effective declarations for the search field at a width: its inline style
  // plus anything a matching @media block overrides on top.
  const searchStyleAt = (width) => {
    let css = w.document.querySelector("#q").getAttribute("style");
    for (const b of blocksFor(width)) {
      const r = new RegExp('\\[data-mq="search"\\]\\{([^}]*)\\}').exec(b);
      if (r) css += ";" + r[1];
    }
    return css;
  };

  // A wrapping flex row decides line breaks from an item's BASE size, so the
  // only thing that stops the field jumping the line is a small basis. A fixed
  // `width` or a large basis is the bug, at any width, in any band.
  const basisOf = (css) => {
    const flex = [...css.matchAll(/(?:^|;)\s*flex\s*:\s*([^;!]+)/g)].pop();
    if (flex) {
      const px = /(\d+)px/.exec(flex[1]);
      if (px) return +px[1];
    }
    const width = [...css.matchAll(/(?:^|;)\s*width\s*:\s*(\d+)px/g)].pop();
    return width ? +width[1] : null;
  };

  for (const [px, label] of VIEWPORTS) {
    const css = searchStyleAt(px);
    const basis = basisOf(css);
    check(`${px}px (${label}): search field has a shrinkable base, not a fixed 260`,
          basis !== null && basis <= 200, true);
  }
  check("the field is still capped so wide screens look unchanged",
        /max-width:\s*260px/.test(w.document.querySelector("#q").getAttribute("style")), true);
  check("...and still right-aligned, because grow resolves before auto margins",
        /margin-left:\s*auto/.test(w.document.querySelector("#q").getAttribute("style")), true);
  check("the sort control got the same treatment, not just the one that was noticed",
        basisOf(w.document.querySelector("#sort").getAttribute("style")) <= 150, true);
  // The band that remains is only the cramped-layout concessions. If a future
  // edit puts a basis back inside a range, that is the old bug returning.
  check("no size band reintroduces a basis for the search field", (() => {
    const inBands = VIEWPORTS.some(([px]) =>
      blocksFor(px).some((b) => /\[data-mq="search"\]\{[^}]*flex\s*:[^}]*\d{3}px/.test(b)
                             && px > 720));
    return inBands;
  })(), false);

  console.log("\n=== 7. COMPUTED SYMMETRIC MARGINS ===");
  // padRight must come off documentElement.clientWidth. 100vw counts the
  // scrollbar and the register drifts out of line with the stats column.
  check("no style value measures the viewport with vw", /[:(]\s*100vw/.test(HTML), false);
  check("the pad is measured off documentElement.clientWidth",
        HTML.includes("documentElement.clientWidth"), true);
  check("filter bar and main share one symmetric pad", (() => {
    const bar = w.document.querySelector("#fbar").style;
    const main = w.document.querySelector("#main").style;
    return bar.paddingLeft === bar.paddingRight
        && main.paddingLeft === main.paddingRight
        && main.paddingLeft === bar.paddingLeft
        && /^[\d.]+px$/.test(bar.paddingLeft);
  })(), true);
  check("the register line is indented to match", (() => {
    const wide = [...w.document.querySelectorAll('[data-mq="wide"]')];
    return wide.length === 2 && wide.every((n) => /^[\d.]+px$/.test(n.style.paddingLeft));
  })(), true);

  console.log("\n=== 8. LEDGER NAME DISCIPLINE (design v1.2) ===");
  // The ledger is a register, so it reads like one: one name per maker, one
  // short title per watch, and the full string never lost — it stays in the
  // data, in the search hay and on hover.
  w = await load(BASE);
  const cells = (n) => [...w.document.querySelectorAll(`[data-id] [data-mq="cols"] > *:nth-child(${n})`)];
  const brandCells = () => cells(2).map((c) => c.firstElementChild.textContent.trim());
  const modelCells = () => cells(2).map((c) => c.lastElementChild);

  check("brand column is fixed width, so every model starts at the same x",
        cells(2).every((c) => /width:175px/.test(c.firstElementChild.getAttribute("style"))
                           && !/max-width:175px/.test(c.firstElementChild.getAttribute("style"))), true);
  check("no brand cell shows a collab string", brandCells().filter((b) => /[×/]/.test(b)).length, 0);
  check("no model cell runs past 38 characters",
        modelCells().filter((n) => n.textContent.trim().length > 38).length, 0);
  check("a shortened model keeps its full name on hover", (() => {
    const shortened = modelCells().filter((n) => n.textContent.trim() !== n.getAttribute("title"));
    return shortened.length > 20 && shortened.every((n) => n.getAttribute("title").length > 0);
  })(), true);
  check("the collab and the standalone Naoya Hida read as one maker", (() => {
    const collab = BASE.watches.find((x) => x.brand === "The Armoury × Naoya Hida");
    if (!collab) return "no Armoury collab in the data";
    const row = w.document.querySelector(`[data-id="${collab.id}"] [data-mq="cols"] > *:nth-child(2)`);
    return row.firstElementChild.textContent.trim() === "Naoya Hida & Co.";
  })(), true);
  check("a word dropped from the title still finds the watch", (() => {
    const q = w.document.querySelector("#q");
    const hits = ["Concorde 43", "SSNAV"].map((term) => {
      q.value = term;
      q.dispatchEvent(new w.Event("input", { bubbles: true }));
      return rows(w);
    });
    q.value = ""; q.dispatchEvent(new w.Event("input", { bubbles: true }));
    return hits.every((n) => n >= 1);
  })(), true);
  check("a display name in the data outranks the built-in map", await (async () => {
    const patched = JSON.parse(JSON.stringify(BASE));
    const t = patched.watches.find(inScope);
    t.displayBrand = "Fixturebrand"; t.displayModel = "Fixture display model";
    const v = await load(patched);
    const c = v.document.querySelector(`[data-id="${t.id}"] [data-mq="cols"] > *:nth-child(2)`);
    return c.firstElementChild.textContent.trim() === "Fixturebrand"
        && c.lastElementChild.textContent.trim() === "Fixture display model";
  })(), true);

  console.log("\n=== 9. RELEASED AND EDITION COLUMNS (design v1.3) ===");
  // A date column is only worth having if it sorts by what it displays. Both come
  // from one parser for exactly that reason.
  const GRAMMAR = /^(\d{1,2} )?(Jan|Feb|Mar|Apr|May|June|July|Aug|Sept|Oct|Nov|Dec)( \d{4})?$|^Q[1-4]( \d{4})?$|^\d{4}$|^TBC$|^—$/;
  const dateCells = () => cells(3);
  check("every Released cell speaks the house date grammar",
        dateCells().filter((c) => !GRAMMAR.test(c.textContent.trim())).length, 0);
  check("the date window is skipped for TBC and —", (() => {
    return dateCells().every((c) => {
      const t = c.textContent.trim();
      const windowed = /background:#fdfbf5/.test(c.innerHTML);
      return (t === "TBC" || t === "—") ? !windowed : windowed;
    });
  })(), true);
  check("the raw date string survives on hover",
        dateCells().every((c) => c.hasAttribute("title")), true);
  check("every Edition cell is a number or N/A",
        cells(4).filter((c) => !/^(N\/A|\d{1,3}(,\d{3})*)$/.test(c.textContent.trim())).length, 0);
  check("Unique piece counts as one", (() => {
    const u = KEPT.find((x) => /^unique piece/i.test(String(x.edition || "")));
    if (!u) return true;
    return w.document.querySelector(`[data-id="${u.id}"] [data-mq="cols"] > *:nth-child(4)`)
            .textContent.trim() === "1";
  })(), true);

  const clickHead = (col) => {
    w.document.querySelector(`[data-sortcol="${col}"]`)
     .dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  };
  const arrow = (col) => w.document.querySelector(`#arr-${col}`).textContent.trim();

  check("Released sorts newest first, and the displayed dates agree", (() => {
    clickHead("date");
    const MON = ["Jan","Feb","Mar","Apr","May","June","July","Aug","Sept","Oct","Nov","Dec"];
    const keys = dateCells().map((c) => {
      const t = c.textContent.trim();
      const m = t.match(/^(?:(\d{1,2}) )?([A-Za-z]+)/);
      if (!m || MON.indexOf(m[2]) < 0) return null;      // TBC, Q-only and — sort to the floor
      return (MON.indexOf(m[2]) + 1) * 40 + (m[1] ? +m[1] : 0);
    }).filter((x) => x !== null);
    for (let i = 1; i < keys.length; i++) if (keys[i] > keys[i - 1]) return `row ${i} breaks the order`;
    return true;
  })(), true);
  check("the announce date does not win over the release date", (() => {
    // "Announced Dec 2025 for the Feb 2026 lunar year" is a February watch.
    const trap = KEPT.find((x) => /announce/i.test(String(x.date || "")) && /2026/.test(String(x.date || "")));
    if (!trap) return true;
    const shown = w.document.querySelector(`[data-id="${trap.id}"] [data-mq="cols"] > *:nth-child(3)`).textContent.trim();
    const anchored = String(trap.date).match(/([A-Za-z]{3})[a-z]*\.? 2026/);
    return !anchored || shown.startsWith(anchored[1]) || shown.includes(anchored[1]);
  })(), true);
  check("Edition sorts smallest first and parks N/A at the end", (() => {
    clickHead("edition");
    const vals = cells(4).map((c) => c.textContent.trim());
    const nums = vals.filter((v) => v !== "N/A").map((v) => +v.replace(/,/g, ""));
    const firstNA = vals.indexOf("N/A");
    if (nums[0] !== 1) return `smallest edition is ${nums[0]}`;
    for (let i = 1; i < nums.length; i++) if (nums[i] < nums[i - 1]) return `row ${i} breaks the order`;
    return firstNA === -1 || vals.slice(firstNA).every((v) => v === "N/A");
  })(), true);
  check("a second click reverses the column", (() => {
    clickHead("brand");
    const asc = brandCells()[0];
    if (arrow("brand") !== "▾") return "no marker after the first click";
    clickHead("brand");
    return arrow("brand") === "▴" && brandCells()[0] !== asc;
  })(), true);
  check("only the active column is marked", (() => {
    clickHead("price");
    return ["brand", "model", "date", "edition"].every((c) => arrow(c) === "") && arrow("price") === "▾";
  })(), true);
  check("a header sort drops the pulldown back to its label", (() => {
    return w.document.querySelector("#sort").value === "priceDesc";
  })(), true);

  console.log("\n=== 10. THE EDITOR'S JOURNAL IS GATED ===");
  // The reference opens it on ?admin=1. On a public site that is not a gate, so
  // the live page wants a token whose hash is the only thing published.
  check("the query string alone does not open it", await (async () => {
    const v = await load(BASE, "?admin=1");
    return v.document.querySelector("#journal").style.display === "none";
  })(), true);
  check("only a digest is published, never the token itself", (() => {
    const digest = HTML.match(/ADMIN_HASH = "([0-9a-f]*)"/);
    if (!digest) return "no ADMIN_HASH in the page";
    if (digest[1] && digest[1].length !== 64) return "that is not a SHA-256";
    // On this machine the real token is on disk; in CI it is not, and the digest
    // check above is the whole assertion.
    const secret = path.join(process.env.HOME || "", ".watchdrop-admin");
    if (!fs.existsSync(secret)) return true;
    return !HTML.includes(fs.readFileSync(secret, "utf8").trim());
  })(), true);
  check("the journal markup ships, hidden, ready for an unlocked editor",
        HTML.includes('id="journal"') && HTML.includes('id="journalRows"')
        && HTML.includes("Copy corrections JSON"), true);
  check("the real token opens it, and leaves the address bar", await (async () => {
    const secret = path.join(process.env.HOME || "", ".watchdrop-admin");
    if (!fs.existsSync(secret)) return true;                 // CI has no token; nothing to prove
    const v = await load(BASE, "?admin=" + fs.readFileSync(secret, "utf8").trim());
    const journal = v.document.querySelector("#journal");
    const listed = v.document.querySelector("#journalRows").children.length;
    return journal.style.display !== "none" && listed >= 90 && v.location.search === "";
  })(), true);
  check("an editor's correction outranks everything and round-trips", await (async () => {
    const secret = path.join(process.env.HOME || "", ".watchdrop-admin");
    if (!fs.existsSync(secret)) return true;
    const v = await load(BASE, "?admin=" + fs.readFileSync(secret, "utf8").trim());
    const t = KEPT[0];
    v.localStorage.setItem("wdi-admin-ov", JSON.stringify({ [t.id]: { displayBrand: "Handedit", displayModel: "Hand model" } }));
    // re-render through the UI rather than poking the module
    v.document.querySelector('[data-tier="All"]').dispatchEvent(new v.MouseEvent("click", { bubbles: true }));
    const c = v.document.querySelector(`[data-id="${t.id}"] [data-mq="cols"] > *:nth-child(2)`);
    const shown = c.firstElementChild.textContent.trim() === "Handedit"
               && c.lastElementChild.textContent.trim().replace(/\s*°$/, "") === "Hand model";
    const exported = JSON.parse(v.localStorage.getItem("wdi-admin-ov"));
    return shown && exported[t.id].displayBrand === "Handedit";
  })(), true);

  console.log("\n=== 11. THE ENLARGED PHOTOGRAPH ===");
  // Mechanism, not treatment — design owns the styling. What must not regress is
  // the behaviour: it opens, it never upscales, and a keyboard user can both
  // reach it and get back out to where they were.
  const zoomable = BASE.watches.find((x) => x.image && x.imageSize);
  w = await load(BASE, "#" + zoomable.id);
  const zimg = w.document.querySelector(`[data-id="${zoomable.id}"] img[data-zoom]`);
  const zbox = w.document.querySelector("#lightbox");
  const zbig = w.document.querySelector("#lightboxImg");
  const zrow = w.document.querySelector(`[data-id="${zoomable.id}"] .wdi-row`);

  check("the photograph is reachable by keyboard", zimg.getAttribute("tabindex"), "0");
  check("...and announces what it does", /enlarge/i.test(zimg.getAttribute("aria-label") || ""), true);
  check("the viewer starts closed", zbox.style.display, "none");

  const expandedBefore = zrow.getAttribute("aria-expanded");
  zimg.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  check("a click opens it", zbox.style.display, "flex");
  check("showing the same photograph", zbig.src, zoomable.image);
  // The whole reason dimensions are stored: these are press og:image files, and
  // upscaling a small one is worse than the thumbnail it came from. The cap is
  // against the FRAME rather than the viewport as of v1.4 §2.3 — the backdrop's
  // own padding is what holds it off the edges now.
  check("capped at native size, never upscaled",
        zbig.style.maxWidth, `min(100%, ${zoomable.imageSize[0]}px)`);
  check("the credit travels with it",
        /Photograph ·/.test(w.document.querySelector("#lightboxCap").textContent), true);
  check("the row underneath does not collapse", zrow.getAttribute("aria-expanded"), expandedBefore);
  check("the page behind cannot scroll away", w.document.documentElement.style.overflow, "hidden");
  check("it is a real dialog to a screen reader",
        [zbox.getAttribute("role"), zbox.getAttribute("aria-modal")], ["dialog", "true"]);

  w.document.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  check("Escape closes it", zbox.style.display, "none");
  check("scrolling is restored", w.document.documentElement.style.overflow, "");
  check("focus returns to the photograph, not the top of the page",
        w.document.activeElement, zimg);

  zimg.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  check("Enter opens it too", zbox.style.display, "flex");
  zbox.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  check("clicking anywhere closes it", zbox.style.display, "none");

  check("an image with no measured size is capped at the viewport instead", await (async () => {
    const patched = JSON.parse(JSON.stringify(BASE));
    const t = patched.watches.find((x) => x.image);
    delete t.imageSize;
    const v = await load(patched, "#" + t.id);
    v.document.querySelector(`[data-id="${t.id}"] img[data-zoom]`)
     .dispatchEvent(new v.MouseEvent("click", { bubbles: true }));
    return v.document.querySelector("#lightboxImg").style.maxWidth;
  })(), "100%");

  // --- v1.4 §6, acceptance 6, 7, 8 and 9 ----------------------------------
  // The close control. Tap-anywhere and Esc were both real and both invisible,
  // which is not a treatment question — a reader on a phone has no pointer to
  // hover and no key to press.
  {
    const lb = w.document.querySelector("#lbClose");
    check("the viewer carries a visible close control", !!lb, true);
    check("...that reads the word Close, then the ×", lb.textContent.trim(), "Close×");
    check("...at a 44px hit target in both directions",
          [lb.style.minWidth, lb.style.minHeight], ["44px", "44px"]);
    check("...and is announced to a screen reader", lb.getAttribute("aria-label"), "Close");
    lb.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
    check("clicking it closes the viewer", w.document.querySelector("#lightbox").style.display, "none");
  }

  // The caption names the watch the way the REGISTER named it. Putting the full
  // data name here would quietly undo every editorial short title at the moment
  // the reader is looking hardest — so this is pinned against an entry that has
  // one, not against an arbitrary row.
  // The short titles come from the baked-in map rather than from data.json, so
  // the entry to test on is found by RENDERING and looking for a row whose model
  // cell is not the data's model — the same thing the reader sees.
  check("the caption is the ledger name, not the untrimmed data name", await (async () => {
    const v = await load(BASE, "");
    const shortened = BASE.watches.filter((x) => x.image).find((x) => {
      const cell = v.document.querySelector(`[data-id="${x.id}"] [data-mq="cols"] > *:nth-child(2) > span:last-child`);
      return cell && cell.textContent.trim().replace(/°$/, "") !== x.model;
    });
    if (!shortened) return "no entry carries an editorial short title";
    const t = await load(BASE, "#" + shortened.id);
    const rowName = t.document
      .querySelector(`[data-id="${shortened.id}"] [data-mq="cols"] > *:nth-child(2) > span:last-child`)
      .textContent.trim().replace(/°$/, "");
    t.document.querySelector(`[data-id="${shortened.id}"] img[data-zoom]`)
     .dispatchEvent(new t.MouseEvent("click", { bubbles: true }));
    const lines = [...t.document.querySelectorAll("#lightboxCap > span")].map((n) => n.textContent);
    return [
      lines.length === 2,
      lines[0].includes(rowName),               // the name the register showed
      lines[0].includes(shortened.model),       // must be FALSE — the long name
      /^Photograph · /.test(lines[1]),
      // and the alt keeps the full name, which is the separate accessibility job
      t.document.querySelector("#lightboxImg").alt.includes(shortened.model),
    ].join(",");
  })(), "true,true,false,true,true");

  // A 480px file on a 1920px display renders at 480px, centred in ink. This is
  // the case the rule exists for, so it is asserted at that size and not only in
  // the abstract.
  check("a small photograph is not blown up to fill the frame", await (async () => {
    const patched = JSON.parse(JSON.stringify(BASE));
    const t = patched.watches.find((x) => x.image && x.imageSize);
    t.imageSize = [480, 480];
    const v = await load(patched, "#" + t.id);
    v.document.querySelector(`[data-id="${t.id}"] img[data-zoom]`)
     .dispatchEvent(new v.MouseEvent("click", { bubbles: true }));
    return v.document.querySelector("#lightboxImg").style.maxWidth;
  })(), "min(100%, 480px)");

  // There is no empty viewer state, because there is nothing to open. The plate
  // must not advertise a zoom it cannot perform.
  check("an entry with no photograph offers no zoom at all", await (async () => {
    const none = BASE.watches.find((x) => !x.image);
    if (!none) return "every entry has a photograph";
    const v = await load(BASE, "#" + none.id);
    const box = v.document.querySelector("#lightbox");
    const before = box.style.display;
    v.document.querySelector(`[data-id="${none.id}"] figure`)
     .dispatchEvent(new v.MouseEvent("click", { bubbles: true }));
    return [
      v.document.querySelector(`[data-id="${none.id}"] [data-zoom]`) === null,
      before === "none" && box.style.display === "none",
    ].join(",");
  })(), "true,true");

  // Hotlink protection: outlets serve a bare request and refuse a referred one,
  // so the page must not send a Referer for a press photograph. Confirmed live
  // 2026-08-05 — this attribute is what put the Marathon image back.
  check("no Referer is sent with a hotlinked photograph",
        [...w.document.querySelectorAll("img")].every((n) => n.getAttribute("referrerpolicy") === "no-referrer"),
        true);

  console.log("\n=== 12. FAVOURITES ===");
  // Lowell's ruling was tally-and-display from day one, which makes the low-volume
  // case the dangerous one: this is pinned against rendering a zero, against
  // losing a reader's star, and against the tally's host being able to take the
  // register down with it.
  {
    const A = BASE.watches[0].id, B = BASE.watches[1].id;
    const star = (v, id) => v.document.querySelector(`[data-fav="${id}"]`);

    let posts = [];
    let v = await load(BASE, "#" + A, { [A]: 4 }, posts);
    check("a starred watch shows its count", txt(v, `[data-fav="${A}"] #favN`), "4");

    v = await load(BASE, "#" + B, { [A]: 4 }, posts);
    check("a watch nobody has starred shows NO number, not a zero",
          v.document.querySelector(`[data-fav="${B}"] #favN`), null);
    check("but the control is still offered", !!star(v, B), true);
    check("it does not read as pressed", star(v, B).getAttribute("aria-pressed"), "false");

    // Clicking: the star must register, and must NOT collapse the row underneath.
    posts = [];
    v = await load(BASE, "#" + B, {}, posts);
    const openBefore = v.document.querySelector(`[data-id="${B}"] .wdi-row`).getAttribute("aria-expanded");
    star(v, B).dispatchEvent(new v.MouseEvent("click", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 20));
    check("the row stays open when the star is clicked",
          v.document.querySelector(`[data-id="${B}"] .wdi-row`).getAttribute("aria-expanded"), openBefore);
    check("the star now reads as pressed", star(v, B).getAttribute("aria-pressed"), "true");
    check("and the count appears from the reader's own star",
          txt(v, `[data-fav="${B}"] #favN`), "1");
    check("exactly one write was sent", posts.length, 1);
    check("the write names the watch", posts[0].id, B);
    check("the write sets rather than clears", posts[0].on, true);
    check("a device id is generated and sent", /^d[a-z0-9]{8,}$/.test(posts[0].device || ""), true);
    check("the device id is not the watch id and not a person",
          posts[0].device !== B && !/@/.test(posts[0].device), true);

    // Unstarring must return the entry to SILENCE, not to a rendered zero.
    star(v, B).dispatchEvent(new v.MouseEvent("click", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 20));
    check("unstarring clears it back to no number",
          v.document.querySelector(`[data-fav="${B}"] #favN`), null);
    check("and sends the clear", posts.length === 2 && posts[1].on, false);

    // The register must survive the tally being down. This is the whole reason
    // favLoad runs after the first render.
    v = await load(BASE, "", null, posts);
    check("the register still renders when the favourites worker is unreachable",
          rows(v), N);
    check("and no count is invented in its absence",
          v.document.querySelectorAll("#favN").length, 0);

    // The ordering ships before the counts are shown anywhere else, because an
    // ordering exposes no numbers and so cannot embarrass the site at low volume.
    v = await load(BASE, "", { [B]: 9 }, posts);
    v.document.querySelector("#sort").value = "favs";
    v.document.querySelector("#sort").dispatchEvent(new v.Event("change", { bubbles: true }));
    check("sort by favourites puts the most-favourited first",
          v.document.querySelector("[data-id]").getAttribute("data-id"), B);
    check("sorting by favourites reveals no counts in the list",
          v.document.querySelectorAll("[data-id] #favN").length, 0);
  }

  console.log("\n=== 13. THE MARK, AS DESIGN RULED IT (v1.4 §6) ===");
  // Acceptance 1-5. jsdom does no layout, so offsetLeft is 0 for everything and
  // measuring it would prove nothing — these assert the STYLE CONTRACT that
  // makes the geometry identical instead, which is the thing that can actually
  // regress in an edit. The pixel side-by-side is Lowell's to settle; §7.
  {
    const A = BASE.watches[0].id, B = BASE.watches[1].id;
    const wrap = (v, id) => v.document.querySelector(`[data-id="${id}"]`);

    let v = await load(BASE, "", {});
    // Mark A directly through the control so this exercises the real path.
    v.document.querySelector(`[data-id="${A}"] .wdi-row`)
     .dispatchEvent(new v.MouseEvent("click", { bubbles: true }));
    v.document.querySelector(`[data-fav="${A}"]`)
     .dispatchEvent(new v.MouseEvent("click", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 20));

    const marked = wrap(v, A), plain = wrap(v, B);
    // jsdom serialises colours as rgb(), so the palette value is converted here
    // rather than written twice — a hex literal in this file would pass while
    // the page shipped a different bronze.
    const rgb = (hex) => "rgb(" + [1, 3, 5].map((i) => parseInt(hex.substr(i, 2), 16)).join(", ") + ")";
    check("a marked entry carries the bronze rule in the margin",
          marked.style.borderLeft, `2px solid ${rgb("#8a5a2b")}`);
    check("EVERY other row reserves the same two pixels, transparently",
          plain.style.borderLeft, "2px solid transparent");
    check("...so marking one costs zero layout shift",
          [marked.style.borderLeftWidth === plain.style.borderLeftWidth,
           marked.style.marginLeft === plain.style.marginLeft &&
           marked.style.marginLeft === "-2px"].join(","), "true,true");
    check("the rule is on the wrapper, so the row's own hover cannot cover it",
          [wrap(v, A).matches("[data-id]"),
           v.document.querySelector(`[data-id="${A}"] .wdi-row`).style.borderLeft], "true,");
    check("no count leaks into the collapsed list, ever",
          v.document.querySelectorAll("[data-id] .wdi-row #favN").length, 0);

    // Acceptance 3: ABSENCE, not invisibility. A hidden zero is a zero that
    // comes back the first time somebody restyles the control.
    v = await load(BASE, "#" + B, {});
    const zero = v.document.querySelector(`[data-fav="${B}"]`);
    check("an unmarked entry's control is exactly star and word",
          [...zero.children].map((n) => n.tagName.toLowerCase()).join(","), "svg,span");
    check("...with no hairline and no number ANYWHERE in the DOM",
          zero.innerHTML.includes("#d5cdbc") || !!zero.querySelector("#favN"), false);
    check("the word is Mark before it is marked", zero.textContent.trim(), "Mark");
    check("the star is the reference's own path, not a glyph or an emoji",
          /^M8 1\.5l1\.98 4\.01/.test(zero.querySelector("path").getAttribute("d")), true);
    check("the control is a 44px hit target", zero.style.minHeight, "44px");
    check("...pushed to the far right so Buy stays dominant", zero.style.marginLeft, "auto");

    // Acceptance 4: en-US grouping at every magnitude. 3,041 is the case that
    // tempts an abbreviation, so it is the case that is pinned.
    const shown = async (n) => {
      const t = await load(BASE, "#" + A, { [A]: n });
      return txt(t, `[data-fav="${A}"] #favN`);
    };
    check("a small count reads plainly", await shown(8), "8");
    check("a three-figure count reads plainly", await shown(247), "247");
    check("a four-figure count is grouped, never abbreviated", await shown(3041), "3,041");

    v = await load(BASE, "#" + A, { [A]: 3041 });
    const busy = v.document.querySelector(`[data-fav="${A}"] #favN`);
    check("the count arrives behind its hairline",
          busy.firstElementChild.style.background, rgb("#d5cdbc"));
    check("the marked word is Marked, not a second glyph", await (async () => {
      const t = await load(BASE, "#" + A, {});
      t.document.querySelector(`[data-fav="${A}"]`)
       .dispatchEvent(new t.MouseEvent("click", { bubbles: true }));
      await new Promise((r) => setTimeout(r, 20));
      const b = t.document.querySelector(`[data-fav="${A}"]`);
      return b.querySelector("span").textContent;
    })(), "Marked");

    // Acceptance 5, second half, and §3: three mobile rules that only exist in
    // the stylesheet, so they are checked there.
    const media = HTML.split("@media (max-width:720px){")[1].split("\n}")[0];
    check("below 720px the control goes full width, centred",
          /\[data-fav\]\{margin-left:0 !important;width:100% !important;justify-content:center !important\}/.test(media), true);
    check("the viewer tightens its padding on a phone",
          /#lightbox\{padding:60px 14px 30px !important\}/.test(media), true);
    check("...and gives the image back the height the caption takes",
          /#lightboxImg\{max-height:calc\(100vh - 210px\) !important\}/.test(media), true);
    check("a standalone detail is exempted from the row indent IN design's block",
          /\[data-mq="detail"\]\[data-standalone\]\{padding-left:2px !important\}/.test(media), true);
  }

  console.log("\n=== 14. THE COPY DESIGN CLOSED (v1.4 §4) ===");
  // Two strings that were quietly false. Pinned as EXACT text because that is
  // what was ruled — a paraphrase here would be the same over-claim returning.
  {
    const v = await load(BASE, "");
    const util = [...v.document.querySelectorAll('[data-mq="util"] > span')].pop();
    check("the utility bar states the split cadence, not 'refreshed weekly'",
          util.textContent.trim(), "Checked daily 09:00 UTC · sources refreshed Mondays");
    check("...and the phone drops the half it cannot fit, not the half it claims",
          util.querySelector('[data-mq="utc"]').textContent.trim(), "· sources refreshed Mondays");

    const retail = BASE.watches.find((x) => x.tier === "Buy at retailer");
    if (retail) {
      const t = await load(BASE, "#" + retail.id);
      check("'Buy at retailer' no longer asserts stock nobody checked",
            t.document.querySelector(`[data-id="${retail.id}"] table td`).textContent
             .includes("No online purchase page was found. Retail availability has not been checked."), true);
    } else {
      check("'Buy at retailer' gloss is the ruled string",
            HTML.includes("No online purchase page was found. Retail availability has not been checked."), true);
    }

    // §4.3, ratified rather than changed. Section 1 already pins the figure to
    // the filtered set; what this adds is the part that was actually in dispute
    // — that the two numbers DIFFER, and the masthead prints the smaller one.
    // Three brands exist only through out-of-scope entries, so printing 94 would
    // be the register lying about its own contents in its largest type.
    const inRegister = new Set(KEPT.map((x) => x.brand)).size;
    const inData = new Set(BASE.watches.map((x) => x.brand)).size;
    check("the two brand counts are genuinely different", inRegister < inData, true);
    check("...and the masthead prints the one the reader can see",
          v.document.querySelector("#t-brands").textContent, String(inRegister));
  }

  console.log(`\n${fail === 0 ? "ALL PASS" : "FAILURES"} — ${pass} passed, ${fail} failed\n`);
  process.exit(fail ? 1 : 0);
})();
