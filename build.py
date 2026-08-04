#!/usr/bin/env python3
"""
Build index.html for the Watch Drop Index.

The page reads data.json at runtime, so routine updates need NO rebuild —
change data.json, commit, done. Only run this when the template itself changes.
"""
import json, os, html
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "data.json")) as fh:
    payload = json.load(fh)

meta = payload["meta"]
items = payload["watches"]
cal = payload["calendar"]

TIERS = ["Buy online now", "Drop upcoming", "Retailer enquiry", "Waitlist or ballot",
         "AD or boutique", "In person only", "Gone"]
TIER_HELP = {
    "Buy online now": "Add to cart on a brand webshop or an authorised online retailer.",
    "Drop upcoming": "Announced with a date. Nothing to buy yet.",
    "Retailer enquiry": "At retail, but not purchasable online — call or visit.",
    "Waitlist or ballot": "Entry by lottery, ballot or waitlist.",
    "AD or boutique": "Allocation only. Never sold online.",
    "In person only": "Sold at an event or a single physical location.",
    "Gone": "Sold out, closed or fully allocated.",
}
counts = Counter(i["tier"] for i in items)
cats = sorted({i["cat"] for i in items})
buy_now = counts.get("Buy online now", 0)

CSS = """
:root{
  --paper:#fbfaf8; --ink:#16130f; --body:#3d3833; --mute:#8b8279;
  --rule:#e3ded6; --rule2:#efebe4;
  --accent:#9a5b23; --live:#1c7a4a; --warn:#9a7318; --dead:#9c3a30;
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,"Times New Roman",serif;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--body);font-family:var(--sans);
  font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased}
a{color:var(--accent)}
.wrap{max-width:1120px;margin:0 auto;padding:0 26px}

/* ---- masthead ---- */
.mast{border-bottom:1px solid var(--ink);padding:30px 0 0}
.mast .wrap{padding-bottom:0}
.brandline{display:flex;align-items:baseline;gap:13px;flex-wrap:wrap}
.wordmark{font-family:var(--serif);font-size:33px;line-height:1;letter-spacing:-.015em;color:var(--ink);margin:0;font-weight:600}
.domain{font-family:var(--mono);font-size:11.5px;color:var(--mute);letter-spacing:.02em}
.descriptor{font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:var(--accent);
  font-weight:700;margin:11px 0 0;padding-top:9px;border-top:1px solid var(--rule)}
.standfirst{font-family:var(--serif);font-size:17.5px;line-height:1.45;color:var(--body);margin:13px 0 0;max-width:620px}
.tally{margin:16px 0 0;padding:11px 0 15px;font-size:13.5px;color:var(--mute);border-top:1px solid var(--rule2)}
.tally b{color:var(--ink);font-variant-numeric:tabular-nums;font-weight:650}
.tally .live{color:var(--live)}
.tally .sep{margin:0 9px;opacity:.4}

/* ---- filters ---- */
.filters{position:sticky;top:0;z-index:30;background:var(--paper);border-bottom:1px solid var(--ink);
  padding:11px 0 12px;margin-bottom:2px}
.frow{display:flex;flex-wrap:wrap;gap:7px;align-items:center}
.frow+.frow{margin-top:8px}
.flabel{font-size:10.5px;letter-spacing:.13em;text-transform:uppercase;color:var(--mute);font-weight:700;margin-right:3px}
input[type=search]{flex:1;min-width:200px;padding:7px 11px;border:1px solid var(--rule);background:#fff;
  border-radius:3px;font-size:14px;font-family:inherit;color:var(--ink)}
input[type=search]:focus{outline:none;border-color:var(--ink)}
select{padding:7px 9px;border:1px solid var(--rule);background:#fff;border-radius:3px;font-size:13.5px;font-family:inherit}
.f{border:1px solid var(--rule);background:transparent;border-radius:3px;padding:5px 11px;font-size:13px;
  cursor:pointer;font-family:inherit;color:var(--body);white-space:nowrap}
.f:hover{border-color:var(--ink);color:var(--ink)}
.f.on{background:var(--ink);border-color:var(--ink);color:var(--paper)}
.f .n{font-variant-numeric:tabular-nums;opacity:.5;margin-left:5px;font-size:11.5px}
.f.on .n{opacity:.7}
.f.live{color:var(--live);border-color:#bcdcc9}
.f.live.on{background:var(--live);border-color:var(--live);color:#fff}
.tally-inline{margin-left:auto;font-size:12.5px;color:var(--mute);font-variant-numeric:tabular-nums;white-space:nowrap}

/* ---- list ---- */
.list{border-top:1px solid var(--rule)}
.item{border-bottom:1px solid var(--rule2)}
.item.open{background:#fff;border-bottom-color:var(--rule)}
.bar{width:100%;display:grid;grid-template-columns:11px minmax(0,1fr) 108px 132px 15px;
  gap:14px;align-items:center;background:none;border:0;padding:11px 4px 11px 2px;
  text-align:left;font:inherit;color:inherit;cursor:pointer}
.bar:hover{background:#f5f2ec}
.bar:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.item.open .bar:hover{background:transparent}
.dot{width:7px;height:7px;border-radius:50%;background:var(--mute);justify-self:center}
.dot.d0{background:var(--live)}.dot.d1{background:#2f5d8a}.dot.d2{background:#2f5d8a}
.dot.d3,.dot.d4,.dot.d5{background:var(--warn)}.dot.d6{background:var(--dead);opacity:.55}
.who{min-width:0;display:flex;align-items:baseline;gap:10px}
.b{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--mute);font-weight:650;
  flex:none;max-width:170px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.m{font-family:var(--serif);font-size:16.5px;line-height:1.3;color:var(--ink);
  flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.item.open .m{white-space:normal}
.ed{font-size:12.5px;color:var(--mute);text-align:right;font-variant-numeric:tabular-nums;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pr{font-size:14.5px;color:var(--ink);text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
.pr.na{color:var(--mute);font-weight:400;font-size:13px}
.chev{color:var(--mute);font-size:11px;transition:transform .15s}
.item.open .chev{transform:rotate(90deg)}

/* ---- expanded ---- */
.panel{display:none;padding:4px 4px 24px 27px;grid-template-columns:300px minmax(0,1fr);gap:26px}
.item.open .panel{display:grid}
.shot{margin:0}
.shot img{width:100%;display:block;background:#f0ece5;border:1px solid var(--rule)}
.shot figcaption{font-size:11px;color:var(--mute);margin-top:6px;line-height:1.4}
.noshot{border:1px dashed var(--rule);padding:24px 14px;text-align:center;font-size:12px;color:var(--mute);background:#faf7f2}
.blurb{font-family:var(--serif);font-size:16px;line-height:1.55;color:var(--ink);margin:0 0 14px}
.tbl{width:100%;border-collapse:collapse;font-size:13.5px;margin-bottom:15px}
.tbl th{text-align:left;font-weight:600;color:var(--mute);font-size:10.5px;letter-spacing:.11em;
  text-transform:uppercase;padding:6px 16px 6px 0;vertical-align:top;white-space:nowrap;width:1px}
.tbl td{padding:6px 0;vertical-align:top;border-bottom:1px solid var(--rule2);color:var(--ink)}
.tbl tr:last-child td{border-bottom:none}
.tbl .ref{font-family:var(--mono);font-size:12.5px}
.status{display:inline-flex;align-items:center;gap:6px;font-weight:600}
.status .dot{justify-self:auto}
.hint{color:var(--mute);font-weight:400;margin-left:2px}
.chk{background:#eef7f1;border-left:2px solid var(--live);padding:8px 11px;font-size:12.5px;
  color:#1c5f3c;margin:0 0 15px;line-height:1.45}
.chk b{font-weight:650}
.tags{font-size:11.5px;color:var(--mute);margin-bottom:14px}
.tags span{border:1px solid var(--rule);border-radius:2px;padding:1px 7px;margin-right:5px;display:inline-block}
.cta{display:inline-block;background:var(--ink);color:var(--paper);text-decoration:none;font-size:14px;
  font-weight:600;padding:10px 18px;border-radius:3px}
.cta:hover{background:var(--accent);color:#fff}
.cta.off{background:transparent;color:var(--mute);border:1px solid var(--rule);font-weight:500}
.cta.off:hover{background:transparent;color:var(--body);border-color:var(--mute)}
.credit{font-size:11.5px;color:var(--mute);margin-top:10px}
.credit a{color:var(--mute)}

.empty{padding:60px;text-align:center;color:var(--mute)}
.loading{padding:60px;text-align:center;color:var(--mute);font-family:var(--serif);font-size:17px}

/* ---- sections ---- */
h2{font-family:var(--serif);font-size:23px;margin:46px 0 4px;color:var(--ink);font-weight:600;letter-spacing:-.01em}
.lede{color:var(--mute);font-size:14px;margin:0 0 15px;max-width:760px}
.cal{list-style:none;padding:0;margin:0;border-top:1px solid var(--rule)}
.cal li{display:grid;grid-template-columns:158px 1fr;gap:18px;padding:13px 0;border-bottom:1px solid var(--rule2)}
.cal .when{font-size:13px;font-weight:650;color:var(--ink);font-variant-numeric:tabular-nums}
.cal .what{font-weight:600;color:var(--ink);margin-bottom:2px}
.cal .det{font-size:13.5px;color:var(--mute)}
.note{border-left:2px solid var(--warn);padding:2px 0 2px 14px;margin-bottom:15px}
.note b{color:var(--ink);display:block;margin-bottom:2px}
.note p{margin:0;font-size:13.5px;color:var(--mute)}
.key{border-top:1px solid var(--rule);margin-top:6px}
.key div{display:grid;grid-template-columns:170px 1fr;gap:16px;padding:9px 0;border-bottom:1px solid var(--rule2);font-size:13.5px;color:var(--mute)}
.key b{color:var(--ink);font-weight:600;display:flex;align-items:center;gap:8px}
footer{margin-top:52px;border-top:1px solid var(--ink);padding:22px 0 70px;font-size:13.5px;color:var(--mute)}
footer h3{font-family:var(--serif);font-size:16px;color:var(--ink);margin:20px 0 7px;font-weight:600}
footer ul{margin:0 0 14px;padding-left:18px}footer li{margin-bottom:5px}
footer .colophon{margin-top:22px;padding-top:14px;border-top:1px solid var(--rule2);font-size:12.5px}

@media(max-width:800px){
  .bar{grid-template-columns:11px minmax(0,1fr) 104px 13px;gap:10px}
  .ed{display:none}
  .panel{grid-template-columns:1fr;padding-left:4px}
  .wordmark{font-size:27px}
  .filters{position:static}
}
"""

JS = r"""
const TIER_HELP = __TIERS__;
const state = {q:"", tier:"All", cat:"All", band:"All", sort:"tier", open:new Set()};
let DATA = [];

const BANDS = {
  "All": d=>true,
  "<$1k": d=>d.priceNum!=null&&d.priceNum<1000,
  "$1k–5k": d=>d.priceNum!=null&&d.priceNum>=1000&&d.priceNum<5000,
  "$5k–15k": d=>d.priceNum!=null&&d.priceNum>=5000&&d.priceNum<15000,
  "$15k–50k": d=>d.priceNum!=null&&d.priceNum>=15000&&d.priceNum<50000,
  "$50k–250k": d=>d.priceNum!=null&&d.priceNum>=50000&&d.priceNum<250000,
  "$250k+": d=>d.priceNum!=null&&d.priceNum>=250000,
  "No price": d=>d.priceNum==null
};
const el=s=>document.querySelector(s);
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const MONTH={jan:1,feb:2,mar:3,apr:4,may:5,jun:6,jul:7,aug:8,sep:9,oct:10,nov:11,dec:12};
const dkey=d=>{const m=(d.date||"").toLowerCase().match(/(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)/);return m?MONTH[m[1]]:0};
const fmt=n=>n>=1e6?"$"+(n/1e6).toFixed(1)+"M":n>=1000?"$"+Math.round(n/1000)+"k":"$"+n;
const shortEd=s=>{
  const t=String(s);
  if(/unconfirmed|not disclosed|not stated/i.test(t)) return "—";
  const nums=t.match(/\d[\d,]*/g);
  if(!nums) return t.length>16?t.slice(0,15)+"…":t;
  if(/each|per (colour|color|version|metal|size|colourway)/i.test(t)) return nums[0]+" ea.";
  if(nums.length>1) return nums.slice(0,2).join(" + ");
  return nums[0];
};

function row(d){
  const open = state.open.has(d.id);
  const priceCell = d.priceNum!=null
    ? `<div class="pr">${esc(fmt(d.priceNum))}</div>`
    : `<div class="pr na">on request</div>`;
  return `<div class="item${open?" open":""}" data-id="${d.id}">
    <button class="bar" aria-expanded="${open}" aria-controls="p-${d.id}">
      <span class="dot d${d.rank}" title="${esc(d.tier)}"></span>
      <span class="who"><span class="b">${esc(d.brand)}</span><span class="m">${esc(d.model)}</span></span>
      <span class="ed" title="${esc(d.edition)}">${esc(shortEd(d.edition))}</span>
      ${priceCell}
      <span class="chev">&#9654;</span>
    </button>
    <div class="panel" id="p-${d.id}">${open?detail(d):""}</div>
  </div>`;
}

function detail(d){
  const shot = d.image
    ? `<figure class="shot"><img src="${esc(d.image)}" alt="${esc(d.brand+" "+d.model)}" loading="lazy"
         onerror="this.closest('.shot').innerHTML='<div class=\\'noshot\\'>Image unavailable</div>'">
       <figcaption>Photograph via ${esc(d.imageCredit||"source")}</figcaption></figure>`
    : `<figure class="shot"><div class="noshot">No photograph yet<br><span style="opacity:.7">queued for the next refresh</span></div></figure>`;
  const buy = d.buy
    ? (d.rank<=2
        ? `<a class="cta" href="${esc(d.buy)}" target="_blank" rel="noopener">${esc(d.buyLabel||"Buy")}</a>`
        : `<a class="cta off" href="${esc(d.buy)}" target="_blank" rel="noopener">${esc(d.buyLabel||"Where to find it")}</a>`)
    : "";
  return shot + `<div class="meat">
    <p class="blurb">${esc(d.desc)}</p>
    ${d.verified?`<p class="chk"><b>Stock checked ${esc(d.verified.date)}</b> — ${esc(d.verified.note)}</p>`:""}
    <table class="tbl">
      <tr><th>Availability</th><td><span class="status"><span class="dot d${d.rank}"></span>${esc(d.tier)}</span>
        <span class="hint">— ${esc(TIER_HELP[d.tier]||"")}</span></td></tr>
      <tr><th>Price</th><td>${esc(d.price)}</td></tr>
      <tr><th>Edition</th><td>${esc(d.edition)}</td></tr>
      <tr><th>Reference</th><td class="ref">${esc(d.ref||"—")}</td></tr>
      <tr><th>Specification</th><td>${esc(d.specs)}</td></tr>
      <tr><th>Released</th><td>${esc(d.date)}</td></tr>
      <tr><th>Segment</th><td>${esc(d.cat)}</td></tr>
      <tr><th>Confidence</th><td>${esc(d.conf)}</td></tr>
    </table>
    ${(d.tags&&d.tags.length)?`<div class="tags">${d.tags.filter(t=>t!=="Buy online").map(t=>`<span>${esc(t)}</span>`).join("")}</div>`:""}
    ${buy}
    <p class="credit">Reported by <a href="${esc(d.source)}" target="_blank" rel="noopener">the source</a>.</p>
  </div>`;
}

function render(){
  const q=state.q.trim().toLowerCase();
  let rows=DATA.filter(d=>{
    if(state.tier!=="All"&&d.tier!==state.tier) return false;
    if(state.cat!=="All"&&d.cat!==state.cat) return false;
    if(!(BANDS[state.band]||BANDS.All)(d)) return false;
    if(q){
      const hay=(d.brand+" "+d.model+" "+d.ref+" "+d.desc+" "+d.specs+" "+(d.tags||[]).join(" ")
                 +" "+d.edition+" "+d.cat+" "+d.tier).toLowerCase();
      // every whitespace-separated token must appear somewhere, in any order
      if(!q.split(/\s+/).every(tok=>hay.includes(tok))) return false;
    }
    return true;
  });
  if(state.sort==="tier")      rows.sort((a,b)=>a.rank-b.rank||(b.priceNum??-1)-(a.priceNum??-1));
  if(state.sort==="date")      rows.sort((a,b)=>dkey(b)-dkey(a)||a.brand.localeCompare(b.brand));
  if(state.sort==="brand")     rows.sort((a,b)=>a.brand.localeCompare(b.brand)||a.model.localeCompare(b.model));
  if(state.sort==="priceAsc")  rows.sort((a,b)=>(a.priceNum??9e12)-(b.priceNum??9e12));
  if(state.sort==="priceDesc") rows.sort((a,b)=>(b.priceNum??-1)-(a.priceNum??-1));
  if(state.sort==="edition")   rows.sort((a,b)=>{const n=s=>{const m=String(s).replace(/,/g,"").match(/\d+/);return m?+m[0]:9e12};return n(a.edition)-n(b.edition)});

  const priced=rows.map(r=>r.priceNum).filter(v=>v!=null).sort((a,b)=>a-b);
  el("#tally").innerHTML = rows.length+" of "+DATA.length
    + (priced.length?" · "+fmt(priced[0])+"–"+fmt(priced[priced.length-1])+", med "+fmt(priced[Math.floor(priced.length/2)]):"");
  el("#list").innerHTML = rows.length ? rows.map(row).join("")
    : '<div class="empty">Nothing matches those filters.</div>';
}

// The masthead tally, availability counts and colophon are baked in at build time.
// A weekly refresh only rewrites data.json, so unless they are re-read from the
// payload the page keeps advertising last month's figures and a stale "updated"
// date — which is exactly the freshness claim the site rests on. Derive every
// count from the data itself; take only `updated` and `revision` from meta.
function hydrate(payload){
  const meta = payload.meta || {}, n = DATA.length;
  const byTier = {};
  DATA.forEach(d => byTier[d.tier] = (byTier[d.tier]||0) + 1);
  const put = (sel,v) => { const node = el(sel); if(node) node.textContent = v; };

  put("#t-buy",     byTier["Buy online now"] || 0);
  put("#t-total",   n);
  put("#t-gone",    byTier["Gone"] || 0);
  put("#t-brands",  new Set(DATA.map(d => d.brand)).size);
  put("#t-updated", meta.updated || "");
  put("#c-rev",     meta.revision ?? "");
  put("#c-imgs",    DATA.filter(d => d.image).length);
  put("#c-total",   n);

  document.querySelectorAll("[data-tier]").forEach(b => {
    const badge = b.querySelector(".n"); if(!badge) return;
    badge.textContent = b.dataset.tier === "All" ? n : (byTier[b.dataset.tier] || 0);
  });
}

// Deep link: /#<id> opens that entry on load. One page, one anchor — deliberately
// not per-watch pages.
function openById(id, focus){
  if(!DATA.some(x => x.id === id)) return false;
  state.open.add(id);
  render();
  const item = [...document.querySelectorAll(".item")].find(x => x.dataset.id === id);
  if(item){
    item.scrollIntoView({block:"center"});
    if(focus) item.querySelector(".bar").focus();
  }
  return true;
}
const dropHash = () => history.replaceState(null, "", location.pathname + location.search);

function bind(sel,key){
  document.querySelectorAll(sel).forEach(b=>b.addEventListener("click",()=>{
    state[key]=b.dataset[key];
    document.querySelectorAll(sel).forEach(x=>x.classList.toggle("on",x===b));
    render();
  }));
}

document.addEventListener("click",e=>{
  const bar=e.target.closest(".bar"); if(!bar) return;
  const item=bar.closest(".item"), id=item.dataset.id, d=DATA.find(x=>x.id===id);
  if(state.open.has(id)){ state.open.delete(id); item.classList.remove("open");
    bar.setAttribute("aria-expanded","false"); item.querySelector(".panel").innerHTML="";
    if(location.hash === "#"+id) dropHash();
  } else { state.open.add(id); item.classList.add("open");
    bar.setAttribute("aria-expanded","true"); item.querySelector(".panel").innerHTML=detail(d);
    history.replaceState(null, "", "#"+id); }
});

window.addEventListener("hashchange", () => {
  const id = location.hash.slice(1);
  if(id && !state.open.has(id)) openById(id, true);
});

async function boot(){
  let payload;
  try{
    const r=await fetch("data.json",{cache:"no-store"});
    if(!r.ok) throw new Error(r.status);
    payload=await r.json();
    DATA=payload.watches;
  }catch(err){
    el("#list").innerHTML='<div class="empty">Could not load <code>data.json</code>.<br><br>'
      +'If you are opening this file directly from disk, browsers block the request. '
      +'Run <code>python3 -m http.server</code> in this folder and open localhost:8000 instead.</div>';
    return;
  }
  el("#q").addEventListener("input",e=>{state.q=e.target.value;render()});
  el("#sort").addEventListener("change",e=>{state.sort=e.target.value;render()});
  bind("[data-tier]","tier"); bind("[data-cat]","cat"); bind("[data-band]","band");
  el("#reset").addEventListener("click",()=>{
    Object.assign(state,{q:"",tier:"All",cat:"All",band:"All",sort:"tier"});
    el("#q").value="";el("#sort").value="tier";
    document.querySelectorAll("[data-tier],[data-cat],[data-band]").forEach(x=>
      x.classList.toggle("on",x.dataset.tier==="All"||x.dataset.cat==="All"||x.dataset.band==="All"));
    render();
    dropHash();
  });
  hydrate(payload);
  render();
  const deep = location.hash.slice(1);
  if(deep) openById(deep, false);
}
document.addEventListener("DOMContentLoaded",boot);
"""

def cal_list(entries, with_where=False):
    out = []
    for e in entries:
        det = e.get("detail", "")
        det = (f'<b>{html.escape(e["where"])}</b>' + (" — " + html.escape(det) if det else "")) \
            if with_where and e.get("where") else html.escape(det)
        link = f' <a href="{html.escape(e["url"])}" target="_blank" rel="noopener">source</a>' if e.get("url") else ""
        out.append(f'<li><div class="when">{html.escape(e["date"])}</div>'
                   f'<div><div class="what">{html.escape(e["what"])}</div>'
                   f'<div class="det">{det}{link}</div></div></li>')
    return "\n".join(out)

# Every tier gets a button whether or not it currently has entries. The counts are
# rewritten from data.json at load, so a tier emptying out must not make its filter
# disappear — that would change the page's structure on a data-only commit, which is
# precisely what this architecture promises never to happen.
tier_f = f'<button class="f on" data-tier="All">All<span class="n">{len(items)}</span></button>'
for t in TIERS:
    cls = "f live" if t == "Buy online now" else "f"
    tier_f += (f'<button class="{cls}" data-tier="{html.escape(t)}" title="{html.escape(TIER_HELP[t])}">'
               f'{html.escape(t)}<span class="n">{counts.get(t, 0)}</span></button>')
cat_f = '<button class="f on" data-cat="All">All segments</button>' + "".join(
    f'<button class="f" data-cat="{html.escape(c)}">{html.escape(c)}</button>' for c in cats)
bands = ["<$1k", "$1k–5k", "$5k–15k", "$15k–50k", "$50k–250k", "$250k+", "No price"]
band_f = '<button class="f on" data-band="All">Any</button>' + "".join(
    f'<button class="f" data-band="{html.escape(b)}">{html.escape(b)}</button>' for b in bands)
key_rows = "".join(
    f'<div><b><span class="dot d{TIERS.index(t)}"></span>{html.escape(t)}</b><span>{html.escape(TIER_HELP[t])}</span></div>'
    for t in TIERS)

dom = meta.get("domain", "")
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
<meta name="theme-color" content="#fbfaf8">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='6' fill='%2316130f'/%3E%3Ccircle cx='16' cy='17.5' r='8' fill='none' stroke='%239a5b23' stroke-width='2'/%3E%3Cpath d='M16 13.5v4l2.8 2' stroke='%23fbfaf8' stroke-width='1.9' stroke-linecap='round' fill='none'/%3E%3Crect x='13.4' y='4' width='5.2' height='2.8' rx='1' fill='%239a5b23'/%3E%3C/svg%3E">
<style>{CSS}</style>
</head><body>

<header class="mast"><div class="wrap">
  <div class="brandline">
    <h1 class="wordmark">Watch Drop Index</h1>
    <span class="domain">{html.escape(dom)}</span>
  </div>
  <div class="descriptor">The limited-edition register</div>
  <p class="standfirst">{html.escape(meta['tagline'])}</p>
  <p class="tally">
    <b class="live" id="t-buy">{buy_now}</b> buyable online today<span class="sep">·</span>
    <b id="t-total">{len(items)}</b> limited runs tracked<span class="sep">·</span>
    <b id="t-gone">{counts.get('Gone', 0)}</b> confirmed gone<span class="sep">·</span>
    <b id="t-brands">{meta['brands']}</b> brands<span class="sep">·</span>
    updated <span id="t-updated">{html.escape(meta['updated'])}</span>, refreshed weekly
  </p>
</div></header>

<div class="filters"><div class="wrap">
  <div class="frow">
    <input id="q" type="search" placeholder="Search brand, model, reference, movement…">
    <select id="sort">
      <option value="tier">Most obtainable first</option>
      <option value="date">Newest first</option>
      <option value="brand">Brand A–Z</option>
      <option value="priceAsc">Price: low to high</option>
      <option value="priceDesc">Price: high to low</option>
      <option value="edition">Smallest edition first</option>
    </select>
    <span class="tally-inline" id="tally"></span>
  </div>
  <div class="frow"><span class="flabel">Availability</span>{tier_f}</div>
  <div class="frow"><span class="flabel">Price</span>{band_f}<span class="flabel" style="margin-left:8px">Segment</span>{cat_f}
    <button class="f" id="reset">Reset</button></div>
</div></div>

<div class="wrap">
  <div class="list" id="list"><div class="loading">Loading the register…</div></div>

  <h2>Reading the availability marks</h2>
  <p class="lede">Assigned from how the brand actually sells the watch — not a guess at demand.</p>
  <div class="key">{key_rows}</div>

  <h2>Dated opportunities</h2>
  <p class="lede">Drops, order windows and deadlines with a date attached.</p>
  <ul class="cal">{cal_list(cal['drops'])}</ul>

  <h2>Where the rest of 2026 gets announced</h2>
  <ul class="cal">{cal_list(cal['events'], with_where=True)}</ul>

  <h2>Not happening in 2026</h2>
  {''.join(f'<div class="note"><b>{html.escape(n["what"])}</b><p>{html.escape(n["detail"])} <a href="{html.escape(n["url"])}" target="_blank" rel="noopener">source</a></p></div>' for n in cal['notHappening'])}

  <h2>Expected but unannounced</h2>
  {''.join(f'<div class="note"><b>{html.escape(e["what"])}</b><p>{html.escape(e["detail"])}</p></div>' for e in cal['expected'])}

  <footer>
    <h3>Method</h3>
    <ul>
      <li><b>Limited editions only.</b> Numbered runs, capped annual production, ballot pieces and single-retailer exclusives. Unnumbered special editions are included but labelled as such.</li>
      <li><b>Confidence is stated, not implied.</b> High means a brand source or several credible outlets agree; medium means one credible source; low means a single aggregator or an unresolved conflict.</li>
      <li><b>Stock status is only claimed where checked.</b> Entries with a green check had their purchase page read on that date. Everything else is classified by how the brand distributes.</li>
      <li><b>Converted prices are marked with a tilde.</b> Sorting uses the USD estimate, so ranking near a band boundary is approximate.</li>
      <li><b>Photographs are drawn from the reporting outlet</b> that covered each release, credited beneath the image, and used to identify the watch being indexed.</li>
    </ul>
    <h3>Known gaps</h3>
    <ul>
      <li>Grand Seiko and Seiko's H2 2026 announcements are not yet captured.</li>
      <li>F.P. Journe surfaced no 2026 limited edition across four independent sources — likely a coverage gap.</li>
      <li>Casio rarely discloses G-Shock edition sizes; only the MR-G Phoenix carries a confirmed number.</li>
      <li>Minase, Knot, Zelos, Certina, Mido, Rado, Nomos and Zodiac are not researched to completion.</li>
      <li>Rolex issued no numbered limited editions in 2026.</li>
      <li>Open price conflicts: Patek 5810/1G-001, AP × AMBUSH, Doxa × Hodinkee edition size.</li>
    </ul>
    <p class="colophon">Watch Drop Index · {html.escape(dom)} · revision <span id="c-rev">{meta['revision']}</span> ·
      <span id="c-imgs">{meta.get('imagesResolved', 0)}</span> of <span id="c-total">{len(items)}</span> photographs resolved ·
      every entry links to the source it came from.</p>
  </footer>
</div>
<script>{JS.replace('__TIERS__', json.dumps({t: TIER_HELP[t] for t in TIERS}))}</script>
</body></html>
"""

with open(os.path.join(HERE, "index.html"), "w") as fh:
    fh.write(HTML)
print(f"built index.html — template only; {len(items)} entries load from data.json at runtime")
print(f"  buyable online: {buy_now} · photos: {meta.get('imagesResolved',0)} · size: {len(HTML)//1024} KB")
