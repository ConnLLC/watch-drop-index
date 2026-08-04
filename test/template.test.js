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

// NOTHING is deleted from the register: all 252 entries render by default and
// every figure counts all of them. Only the FILTER BUTTONS are narrowed to the
// four actionable tiers — the other three are still listed, searchable and
// explained in the availability key. The test mirrors the rule rather than
// importing it, so changing one and not the other fails here rather than live.
const UNFILTERABLE = ["Waitlist or ballot", "AD or boutique", "In person only"];
const keep = (list) => list
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
  check("the whole file is the register — nothing dropped", N, BASE.watches.length);
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
  const MQ = ["hgrid", "hleft", "hdiv", "hstats", "lockup", "wide", "search", "sort",
              "flabel", "fbar", "cols", "detail", "two", "row2", "badge"];
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

  console.log(`\n${fail === 0 ? "ALL PASS" : "FAILURES"} — ${pass} passed, ${fail} failed\n`);
  process.exit(fail ? 1 : 0);
})();
