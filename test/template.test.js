// Verifies the template against a REAL DOM: baseline render, then a simulated
// weekly refresh that only rewrites data.json. index.html is never rebuilt between
// the two — that is the whole point of the check.
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
  });
  const w = dom.window;
  w.Element.prototype.scrollIntoView = function () {};
  w.fetch = async () => ({ ok: true, status: 200, json: async () => payload });
  w.document.dispatchEvent(new w.Event("DOMContentLoaded", { bubbles: true }));
  await new Promise(r => setTimeout(r, 60)); // let boot()'s awaits settle
  return w;
}

const txt = (w, sel) => w.document.querySelector(sel)?.textContent.trim();
const tierBadge = (w, tier) =>
  w.document.querySelector(`[data-tier="${tier}"] .n`)?.textContent.trim();

(async () => {
  // Expectations are DERIVED from data.json, never hardcoded. The whole point of
  // this file is that the page tracks the data; pinning it to one day's snapshot
  // would make it fail every time the weekly refresh does its job.
  const tally = (t) => BASE.watches.filter((x) => x.tier === t).length;
  const N = BASE.watches.length;

  console.log("\n=== 1. THE PAGE MATCHES THE CURRENT data.json ===");
  let w = await load(BASE);
  check("rows rendered", w.document.querySelectorAll(".item").length, N);
  check("masthead: buyable online", txt(w, "#t-buy"), tally("Buy online now"));
  check("masthead: runs tracked", txt(w, "#t-total"), N);
  check("masthead: confirmed gone", txt(w, "#t-gone"), tally("Gone"));
  check("masthead: brands", txt(w, "#t-brands"), new Set(BASE.watches.map((x) => x.brand)).size);
  check("masthead: updated", txt(w, "#t-updated"), BASE.meta.updated);
  check("colophon: revision", txt(w, "#c-rev"), BASE.meta.revision);
  check("colophon: photos resolved", txt(w, "#c-imgs"), BASE.watches.filter((x) => x.image).length);
  check("filter badge: All", tierBadge(w, "All"), N);
  check("filter badge: Buy online now", tierBadge(w, "Buy online now"), tally("Buy online now"));
  check("filter badge: Gone", tierBadge(w, "Gone"), tally("Gone"));

  console.log("\n=== 2. SIMULATED WEEKLY REFRESH — data.json only, index.html untouched ===");
  // 4 new watches from a brand-new brand; 2 existing 'Buy online now' entries flip to Gone.
  const next = JSON.parse(JSON.stringify(BASE));
  const flipped = next.watches.filter(x => x.tier === "Buy online now").slice(0, 2);
  flipped.forEach(x => {
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
  next.meta.count = next.watches.length;

  w = await load(next);
  check("rows rendered", w.document.querySelectorAll(".item").length, N + 4);
  check("masthead: buyable online", txt(w, "#t-buy"), tally("Buy online now") - 2 + 4);
  check("masthead: runs tracked", txt(w, "#t-total"), N + 4);
  check("masthead: confirmed gone", txt(w, "#t-gone"), tally("Gone") + 2);
  check("masthead: brands", txt(w, "#t-brands"),
        new Set(BASE.watches.map((x) => x.brand)).size + 4);
  check("masthead: updated", txt(w, "#t-updated"), "2026-08-10");
  check("colophon: revision", txt(w, "#c-rev"), BASE.meta.revision + 1);
  check("colophon: total", txt(w, "#c-total"), N + 4);
  check("filter badge: All", tierBadge(w, "All"), N + 4);
  check("filter badge: Buy online now", tierBadge(w, "Buy online now"), tally("Buy online now") - 2 + 4);
  check("filter badge: Gone", tierBadge(w, "Gone"), tally("Gone") + 2);

  console.log("\n=== 3. DEEP LINK  /#<id> ===");
  const target = BASE.watches.find(x => x.image);           // one with a photograph
  w = await load(BASE, "#" + target.id);
  const item = [...w.document.querySelectorAll(".item")].find(x => x.dataset.id === target.id);
  check("target row exists", !!item, true);
  check("target row auto-expanded", item.classList.contains("open"), true);
  check("aria-expanded set", item.querySelector(".bar").getAttribute("aria-expanded"), "true");
  check("panel has content", item.querySelector(".panel").innerHTML.length > 200, true);
  check("photograph rendered in panel", !!item.querySelector(".panel img"), true);
  check("image credit shown", item.querySelector("figcaption")?.textContent.includes(target.imageCredit), true);
  check("no other row expanded", w.document.querySelectorAll(".item.open").length, 1);
  check("unknown hash is ignored", (await load(BASE, "#deadbeef99")).document.querySelectorAll(".item.open").length, 0);

  console.log("\n=== 4. KEYBOARD / ARIA ===");
  w = await load(BASE);
  const first = w.document.querySelector(".item");
  const bar = first.querySelector(".bar");
  check("row control is a native <button>", bar.tagName, "BUTTON");
  check("aria-controls points at its panel", bar.getAttribute("aria-controls"), "p-" + first.dataset.id);
  check("panel id matches", first.querySelector(".panel").id, "p-" + first.dataset.id);
  check("starts collapsed", bar.getAttribute("aria-expanded"), "false");
  // A native button fires a click on both Enter and Space; the handler is delegated
  // on click, so activating it by keyboard follows exactly this path.
  bar.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  check("activation expands", first.classList.contains("open"), true);
  check("aria-expanded flips to true", bar.getAttribute("aria-expanded"), "true");
  check("hash updated for sharing", w.location.hash, "#" + first.dataset.id);
  bar.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  check("activation collapses again", first.classList.contains("open"), false);
  check("hash cleared on collapse", w.location.hash, "");
  check("focus ring style present", HTML.includes(".bar:focus-visible"), true);

  console.log(`\n${fail === 0 ? "ALL PASS" : "FAILURES"} — ${pass} passed, ${fail} failed\n`);
  process.exit(fail ? 1 : 0);
})();
