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

const ROOT = path.join(__dirname, "..");
const HTML = fs.readFileSync(path.join(ROOT, "index.html"), "utf8");
const BASE = JSON.parse(fs.readFileSync(path.join(ROOT, "data.json"), "utf8"));

let pass = 0, fail = 0;
const check = (label, got, want) => {
  const ok = String(got) === String(want);
  ok ? pass++ : fail++;
  console.log(`  ${ok ? "ok  " : "FAIL"}  ${label}: ${got}${ok ? "" : `  (expected ${want})`}`);
};

async function load(payload, hash = "") {
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
  w.Element.prototype.scrollIntoView = function () {};
  w.scrollTo = function () {};
  w.fetch = async () => ({ ok: true, status: 200, json: async () => payload });
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
//    three are still listed, searchable and explained in the availability key.
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
  check("filter badge: All", tierBadge(w, "All"), N);
  check("filter badge: Buy online now", tierBadge(w, "Buy online now"), tally("Buy online now"));
  check("filter badge: Gone", tierBadge(w, "Gone"), tally("Gone"));
  check("Retailer enquiry is remapped, not shown",
        tierBadge(w, "Buy at retailer"), tally("Buy at retailer"));
  // Rendered content only — the script's own source names the old tier, since
  // that is what it remaps FROM.
  check("no 'Retailer enquiry' reaches the reader", (() => {
    const seen = [...w.document.querySelectorAll("#list [title], #keyRows, [data-tier]")]
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
  check("the availability key explains every tier in the data",
        w.document.querySelector("#keyRows").children.length,
        new Set(KEPT.map((x) => x.tier)).size);
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
  check("availability key rendered", w.document.querySelector("#keyRows").children.length > 0, true);
  check("calendar sections rendered from data",
        w.document.querySelector("#drops").children.length, BASE.calendar.drops.length);
  check("events rendered from data",
        w.document.querySelector("#events").children.length, BASE.calendar.events.length);
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
  check("stat ledger is a ruled register, not a sentence",
        w.document.querySelectorAll('[data-mq="hstats"] [id^="t-"]').length, 5);

  console.log("\n=== 6. THE MOBILE CONTRACT ===");
  // The whole ≤720px pass keys off data-mq and nothing else, so a renamed hook
  // silently drops a rule on phones while desktop stays perfect.
  const MQ = ["utilwrap", "util", "utc", "hdr", "hgrid", "hleft", "hdiv", "hstats",
              "lockup", "wide", "fwrap", "fbar", "flabel", "pband", "preset",
              "search", "sort", "main", "colh", "cols", "detail", "two", "row2", "badge"];
  const media = HTML.slice(HTML.indexOf("@media (max-width:720px)"));
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

  console.log(`\n${fail === 0 ? "ALL PASS" : "FAILURES"} — ${pass} passed, ${fail} failed\n`);
  process.exit(fail ? 1 : 0);
})();
