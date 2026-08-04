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

(async () => {
  // Expectations are DERIVED from data.json, never hardcoded. Pinning them to
  // one day's snapshot would make this fail every time the refresh does its job.
  const tally = (t) => BASE.watches.filter((x) => x.tier === t).length;
  const N = BASE.watches.length;

  console.log("\n=== 1. THE PAGE MATCHES THE CURRENT data.json ===");
  let w = await load(BASE);
  check("rows rendered", rows(w), N);
  check("masthead: buyable online", txt(w, "#t-buy"), tally("Buy online now"));
  check("masthead: runs tracked", txt(w, "#t-total"), N);
  check("masthead: confirmed gone", txt(w, "#t-gone"), tally("Gone"));
  check("masthead: brands", txt(w, "#t-brands"), new Set(BASE.watches.map((x) => x.brand)).size);
  check("masthead: updated", txt(w, "#t-updated"), BASE.meta.updated);
  check("colophon: revision", txt(w, "#c-rev"), BASE.meta.revision);
  check("colophon: photos resolved", txt(w, "#c-imgs"), BASE.watches.filter((x) => x.image).length);
  check("colophon: total", txt(w, "#c-total"), N);
  check("filter badge: All", tierBadge(w, "All"), N);
  check("filter badge: Buy online now", tierBadge(w, "Buy online now"), tally("Buy online now"));
  check("filter badge: Gone", tierBadge(w, "Gone"), tally("Gone"));

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
        new Set(BASE.watches.map((x) => x.brand)).size + 4);
  check("masthead: updated", txt(w, "#t-updated"), "2026-08-10");
  check("colophon: revision", txt(w, "#c-rev"), BASE.meta.revision + 1);
  check("filter badge: All", tierBadge(w, "All"), N + 4);
  check("filter badge: Gone", tierBadge(w, "Gone"), tally("Gone") + 2);

  console.log("\n=== 3. DEEP LINK  /#<id> ===");
  const target = BASE.watches.find(x => x.image);           // one with a photograph
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

  console.log(`\n${fail === 0 ? "ALL PASS" : "FAILURES"} — ${pass} passed, ${fail} failed\n`);
  process.exit(fail ? 1 : 0);
})();
