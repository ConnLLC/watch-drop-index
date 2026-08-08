# Watch Drop Index

**watchdropindex.com** — the limited-edition register.

Every limited-run watch of 2026: what it costs, whether you can still get one, and
where to buy it. Limited editions only — no regular production, no restocks.

252 entries researched · 246 on the register · 55 currently buyable online.

Six entries are held back because a production cap is not a limited edition — see
**Scope** below. They stay in the data and return by themselves if an edition size is
ever confirmed.

---

## How it works

```
index.html            The site. Template only. Reads data.json in the browser.
data.json             The source of truth. Every watch, plus the calendar sections.
build.py              Regenerates index.html. Only needed when the TEMPLATE changes.
scripts/refresh.py    The weekly refresh job.
test/refresh_test.py  Decision-logic tests for the refresh. No API key needed.
test/template.test.js Renders index.html in a DOM and checks it against data.json.
.nojekyll             Stops GitHub Pages running Jekyll over the files.
netlify.toml          Config if you host on Netlify instead. Inert on Pages.
robots.txt
sitemap.xml
404.html
```

The important property: **routine updates never touch `index.html`.** The page fetches
`data.json` at load, so adding a watch or flipping something to sold-out is a one-file
change. Commit `data.json`, Pages redeploys, done. `build.py` is only for layout changes.

For that to hold, every figure on the page — the masthead tally, the availability filter
counts, the colophon — is re-read from `data.json` at load rather than trusted as built.
The build-time values stay in the markup as the pre-JavaScript default. **If you rewrite
the template, keep the `#t-*` and `#c-*` anchors and the `.n` badge inside each
`[data-tier]` button** — without them the page keeps advertising whatever the numbers were
the day it was built, which quietly breaks the freshness claim the whole site rests on.
`test/template.test.js` fails loudly if they go missing.

## Design

The look is **"The Catalogue"** — an auction-catalogue register: warm paper, ink, bronze,
Newsreader for the serif voice and Archivo for the interface, ruled columns, no cards or
pills. Design owns it; this repo implements it. **Code makes no design decisions here** —
if something visual is ambiguous or missing, it gets asked, not invented.

Two pieces are less ordinary than they look:

- **The wordmark is a working clock.** WATCH / DROP / INDEX are justified to a single
  measure, and the bronze dot that serves as DROP's fifth character is the pivot for real
  hour, minute and second hands. They are pure CSS rotations; local time enters only as a
  negative `animation-delay`. The outer letters hang on their *ink* edge rather than their
  advance width, using glyph bearings measured from the font via canvas and re-measured
  once the webfont lands. If canvas metrics are unavailable the lettering falls back to
  default spacing rather than taking the page down.
- **The corner badge** mounts past 430px of scroll and unmounts below it, rather than
  being shown and hidden, so its entrance replays and its clock re-syncs each time.

- **The phone layout is a different ledger, not a squeezed one.** Below 720px each row
  becomes a double-deck — brand over model on the left, price over release date on the
  right — the filter bar stops being sticky, and price bands leave entirely. The whole
  pass keys off `data-mq` attributes and nothing else, so **renaming one silently drops a
  rule on phones while desktop stays perfect.** The row grid addresses its six children by
  position (dot, brand+model, Released, Edition, USD, chevron); reordering them rearranges
  the phone layout. `test/template.test.js` checks every hook is both present and styled.

### Scope — what counts as a limited edition

Lowell's ruling, 2026-08-04: **a production cap is not a limited edition.** An entry whose
`edition` matches `/not formally limited/i`, `/^capped/i` or `/annually/i` is filtered out
at the *display* layer — six today. `data.json` keeps them, and every figure on the page
counts what survives the filter, so the moment a weekly run confirms a real edition size
the entry reappears on its own. That is the mechanism; don't hand-edit data to force one
on. Entries whose size is unconfirmed, undisclosed or "special edition" **stay** — their
Edition column reads `N/A`.

The same three patterns live in `build.py`, in the page's script and in
`scripts/refresh.py`. The tests assert all three copies agree.

### Ledger names

The register reads like a register: the brand column names the **manufacturer** only, and
the model column carries a short editorial title (≤38 characters). The full strings are
never lost — they stay in `data.json`, in the search index and on hover.

Resolution order, highest first: an editor's correction (see below) → `displayBrand` /
`displayModel` in `data.json` → the maps design baked into `build.py`. A collab shows the
first-named party unless a `MAKER_OVERRIDE` says otherwise, since the maker is named first
by convention.

### The editor's journal

`?admin=<token>` opens an editor-only section listing every entry whose ledger name
differs from the data, with inline editing and a **Copy corrections JSON** export.
Corrections live in `localStorage` on that device only — nothing on the site changes for
anyone else until the export is folded into `data.json`:

```
python3 scripts/refresh.py --corrections ~/Downloads/corrections.json --stages ""
```

The gate is a shared secret: only the SHA-256 of the token is published, in
`admin-hash.txt` and in the page. The token itself is Lowell's, lives at
`~/.watchdrop-admin`, and is never committed. Rotate by writing a new digest to
`admin-hash.txt` and rebuilding; delete the file and the journal simply cannot be reached.
Nothing behind the gate writes to the register, so this protects editorial machinery
rather than data.

### Editing the register from the page

Behind the same `?admin=` gate, **The register — editing** can change an entry, set or
clear a photograph, and add an entry. All three are the same operation underneath: a JSON
edit plus a commit, through the GitHub Contents API — the one write path a static site has.

**The token.** This page is static and public, so any secret the page needs is a published
secret; there is no server to keep one behind. So Lowell **pastes a fine-grained PAT** to
start an editing session:

> Settings → Developer settings → Personal access tokens → Fine-grained tokens →
> **Only select repositories: `ConnLLC/watch-drop-index`** → Repository permissions →
> **Contents: Read and write** → nothing else → 90-day expiry.

It is held in `sessionStorage` for that tab only — never `localStorage`, never the repo,
never the HTML, never a build artifact, never a URL, never an error message. It dies when
the tab closes. GitHub's own error bodies are rewritten before display, because an error
body can echo the request and the request carries the token. With no token the panel is
**read-only and says so**: the save button is visibly disabled rather than silently doing
nothing, because a save that looks armed and no-ops is worse than one that is greyed out.

Blast radius if it leaks is one public hobby repo. That is proportionate; anything wider
would not be.

**Optimistic locking is mandatory.** The daily and weekly jobs commit to this same file on
a schedule. Every save re-reads `data.json` immediately before writing, and if the `sha`
has moved it is **refused** — not merged, not retried, not last-write-wins. The panel
reloads and shows what changed underneath the edit. A last-write-wins panel would silently
erase a scheduled run, or a run would erase the edit.

**A human edit wins, permanently, until a human releases it.** Fields you change are added
to the entry's `manual` list, and from then on the refresh job may **propose** a change to
them and will **never commit** one; proposals are collected in the run report. The same
holds for a photograph you choose by hand: the photograph pass will not re-resolve it, and
if it breaks the rot check **flags** it rather than clearing it — a person chose that
picture, so the machine reports the problem instead of overruling the choice. One click
releases a field back to automation. Identical in principle to the standing rule for the
curated editorial claims: propose, never commit.

**Nothing is ever deleted.** A mistaken entry is part of the audit trail and a sold-out one
is the historical record, so "remove" is a `retracted` flag that stops it rendering.

Two details worth knowing if you touch this code:

- **Ids are MD5.** The scheme is `md5("brand|model".lower())[:10]` and it is immutable —
  rewriting one orphans that watch's verification history. Web Crypto has no MD5, so the
  panel carries its own implementation, and `test/template.test.js` asserts it reproduces
  **all 252 existing ids**. A hand-added entry whose id disagrees is a watch the refresh
  job thinks is a different watch.
- **A manually entered image URL is truth-tested before it is written**, by loading it as
  an `Image` and checking it decoded. This is the one place the browser is a *better*
  instrument than CI: it is a real browser, on the real page, with a real referer. CORS
  stops us reading a status code, and we do not need one.

### Running it locally

Browsers block `fetch()` on `file://`, so opening `index.html` by double-clicking shows
a load error. Serve it instead:

```bash
python3 -m http.server 8000
# then open http://localhost:8000
```

---

## Deploying

Pages serves `main` from `/ (root)` — live at
[connllc.github.io/watch-drop-index](https://connllc.github.io/watch-drop-index/).

**Custom domain.** Settings → Pages → Custom domain → `www.watchdropindex.com`, then at
the registrar add a `CNAME` for `www` pointing at `connllc.github.io` and remove any
conflicting `A` records on the apex. Enable "Enforce HTTPS" once it validates.

**On caching.** Pages serves `data.json` with a fixed `Cache-Control: max-age=600` and
gives you no way to change it. That's fine here: the page requests it with
`fetch("data.json", {cache: "no-store"})`, so a reader always gets the current file
rather than a ten-minute-old copy. If that fetch option is ever dropped, the freshness
claim silently starts drifting.

Every update becomes a commit, so the repo history doubles as an audit trail of when
each watch sold out — which for a site about availability is content, not just hygiene.

---

## The refresh — two schedules, split by cost

Both workflows run `scripts/refresh.py`; they differ only in which stages they ask for and
whether they are allowed to spend.

| | `daily.yml` — daily sweep | `refresh.yml` — weekly refresh |
|---|---|---|
| When | 09:00 UTC, every day | 09:00 UTC, Mondays |
| Stages | 7, 3, 6, 8, 9 | 2, 4, then 7, 3, 6, 8, 9 |
| Cost | **zero, structurally** | model calls, capped by `WEEKLY_BUDGET_CAD` |

**The split exists because a single cadence was wrong in both directions.** Link checks,
photograph resolution and calendar expiry are fetch-and-parse — no model call, no tokens,
no budget — so running them weekly made them seven times slower than necessary for no
saving whatever. The calendar makes the case on its own: a drop that expires on a Thursday
would sit on the site advertising itself until the following Monday. A broken photograph
is now visible for one day instead of seven.

The daily job **cannot** spend. That is enforced two ways rather than trusted: it passes
`--no-api`, and no `ANTHROPIC_API_KEY` is given to it. One is a switch, the other is an
absence.

The weekly job runs the free stages too, so a watch found by the new-release search gets
its photograph, its buy-link classification and its tier in the same run instead of waiting
for tomorrow. Both jobs share a `concurrency` group and rebase before pushing, since both
rewrite `data.json`.

**The link sweep is now complete**, which it previously was not while claiming to be.
Stage 7 checks image URLs, stage 8 checks buy URLs, and stage 9 checks source and calendar
URLs — roughly 750 requests, free, every run. All three classify by evidence rather than by
status code alone: a 403 or 429 is a bot wall and means *silence*, never rot, and a **soft
404** — a deep URL that 301s to a bare domain root because the article or product was pulled
— counts as dead however clean its 200 looks.

Each link type gets a different action, because a dead one means a different thing:
**image** → cleared, so the photograph pass re-resolves it; **buy** → feeds `buyKind`, since
a dead URL cannot be `product`; **source** → flagged on the entry and never auto-cleared,
because losing provenance does not untrue the watch but every confidence rating rests on
it; **calendar** → flagged for a human, since those are curated.

**The real ceiling is politeness, not money.** Seven times the frequency is seven times the
load on other people's servers, and three outlets already refuse this client. `HostLimiter`
serialises and spaces requests per outlet, so no one site sees a burst — but if the
`blocked` counts in the run report start climbing, this cadence is the first thing to
reconsider, whatever it costs. A register that gets itself blocked verifies nothing at all.

**Still owed:** a paid-stage cadence tiered by volatility rather than uniform across 252
entries. A rank-0 buyable entry's order window can close in hours; a rank-4 allocation
piece has not been buyable since announcement and will not become so. Waiting on the first
real cost figure from a guarded run.

It all runs in CI rather than as a scheduled chat session so the API key lives in Actions
secrets, the job runs whether or not anyone is logged in anywhere, failures surface as red
runs instead of silence, and every change is an attributable, revertible commit.

Because Pages deploys from `main`, **the commit is the deploy**.

Each run:

1. **Loads** `data.json` and validates it. If it doesn't parse, the run aborts having
   changed nothing.
2. **Re-checks availability** for every entry at rank 0–2 — about 90 purchase pages.
   Each page is fetched, reduced to text, and judged by the model against the entry's
   current tier. Positive evidence of a sell-out flips the entry to `Gone`, stamps
   `soldOutOn`, and writes a `verified` note quoting the page. Entries move **up** too:
   a pre-order opening or stock appearing online promotes them.
3. **Backfills photographs** by reading `og:image` from each entry's source article —
   **every entry that still has none, every run.** This stage makes no model call, so it
   costs nothing and is never what a budget stop takes away. Politeness is per-outlet:
   requests to the same site are serialised and spaced 1.5s apart while different sites
   run in parallel, so a full ~200-entry pass takes a few minutes and no one outlet
   notices. Sources with no `og:image` and dead URLs are recorded so they aren't probed
   again every week; the report groups whatever didn't resolve **by outlet**, because a
   hundred failures at one domain is one fixable cause and a hundred spread thin is just
   the shape of the web.
4. **Searches the watch press** for limited editions announced since `meta.updated`,
   restricted to a fixed list of credible outlets, then converts the findings into
   entries — refusing any candidate without a source URL, a buy URL, or limited-edition
   status.
5. **Names anything new for the ledger** — a `displayBrand` when a collab's maker is named
   second, a `displayModel` when the model runs past 38 characters. It will not guess:
   an uncertain maker or a short title that introduces a word absent from the full name
   leaves the field unset and goes into the report for design to rule on.
6. **Re-checks resolved photographs for rot.** The photograph stage only looks at entries
   with *no* image, so a URL that dies after we resolved it is invisible to it forever and
   the row renders a broken picture. This checks a **rotating subset** (40 per run, oldest
   first, so everything cycles in ~6 weeks) with a HEAD — falling back to a one-byte
   ranged GET for hosts that refuse HEAD. Only positive evidence clears a photograph: a
   404/410, or a 200 handing back something that isn't an image (a soft 404). **A 403 or a
   timeout is silence and the photograph is kept** — a hotlink-blocking CDN must never be
   able to delete a good picture.

   A cleared URL is remembered in `deadImages`, because otherwise the two stages would
   loop: clear the image, re-read the article, find the same dead `og:image`, write it
   straight back, every week forever. A *different* image on the same article is still
   adopted normally, so an outlet repairing its page is picked up.
7. **Expires the calendar.** A "Dated opportunities" list still advertising last week's
   drop is the small, visible rot that tells a reader nobody is home — and catching it
   needs arithmetic, not research, so this stage is deterministic and free. Anything whose
   date has passed moves out of `calendar.drops` / `calendar.events` into
   `calendar.passed` (nothing is deleted, and the page doesn't render `passed`, so no
   visual treatment had to be invented). A range expires on its **end**; "Mid-Aug 2026"
   and "Now → Sept 2026" resolve generously, because an opportunity lingering a day too
   long beats one vanishing while it's still live. An entry with no date at all ("Live
   now") is retired by the register instead: the watch it links to going `Gone` is the
   evidence.

   `expected` and `notHappening` are curated research, so the job **does not rewrite
   them** — replacing a stale claim with an unreviewed generation trades one problem for
   a worse one. Anything unconfirmed for 30 days is listed in the report; confirm or
   correct it, then stamp `checkedOn` on the item.
8. **Classifies every buy link by evidence.** "Buy online now" is the strongest claim the
   register makes, so it has to be earned. Each buy URL is fetched and judged on two
   questions — does the page *name this watch* (by reference number, or by most of the
   distinctive words in its model name), and does it carry a *purchase affordance* (a cart
   form, an add-to-bag button, a schema.org `Offer`, a pre-order)? That yields `buyKind`:
   `product` · `listing` (names it, sells nothing) · `brand` (never names it — a homepage
   or category page) · `none`.

   **An unreachable page is not a classification.** Calling it `brand` would invent a fact
   from silence, so those keep whatever they had and are reported separately.

   The tier is then tied to the link: rank 0 requires `buyKind == product`. This lives
   *inside* `rank_for()` rather than as a pass on top of it — two rules that disagree would
   mean the weaker one wins every Monday, when an availability check re-derives the tier
   and silently restores a claim we had just taken away. Evidence can only ever demote,
   never promote, and unknown never moves anything.

   The second-order reason this matters more than it looks: the weekly stock check reads
   these same URLs. **A homepage cannot report that a watch is sold out** — it reads as
   fine for ever — so for those entries the verification is structurally incapable of
   detecting the thing it exists to detect.
9. **Commits** with a summarising message and a full report in the body.

Stages run **2 → 4 → 7 → 3 → 8 → 6**, which is the budget's priority order (below): the paid
stages go first, most valuable first, and the free ones go last. A side benefit is that a watch
found this week gets its photograph this week rather than next.

### What it needs

One repository secret: **`ANTHROPIC_API_KEY`** (Settings → Secrets and variables →
Actions). Nothing else — the job pushes with the built-in `GITHUB_TOKEN`.

### The spend ceiling

A weekly ceiling in Canadian dollars, **changeable without editing code**: set the
repository *variable* `WEEKLY_BUDGET_CAD` (Settings → Secrets and variables → Actions →
**Variables**). A variable rather than a secret, so the current value can be read as well
as changed. Default 5. `USD_TO_CAD` overrides the conversion rate, deliberately a fixed
number — at this precision a stale rate is fine and an FX API is one more thing that can
break on a Monday morning.

Every model call is priced from its actual `usage` block at the published per-token rates,
plus $10 per 1,000 web searches. **Every run reports what it spent**, generous ceiling or
not — the first few real numbers are worth more than any estimate of what the ceiling
should be.

Hitting the ceiling is **not a failure**. The run stops calling the model, commits
everything it finished, and says in the report what it skipped; the job stays green,
because a red badge every week for working as designed teaches everyone to ignore the
badge. Stopping half-way is safe because a refused call returns the same "no answer" an
unreadable page does — so the rules below leave the entry alone, exactly as they would on
a 403.

The Anthropic console cap is monthly and in USD, which makes it a coarse backstop only.
This guard is the real control and the only thing that understands "weekly" or "CAD".

**Rates that expire are in the table with their expiry date.** Sonnet 5's introductory
pricing lapses on 2026-08-31 and rises 50% the next day; `PRICES` carries the schedule and
the run date does the switching. A hard-coded introductory rate would leave the ceiling
under-counting by half the moment it lapsed — and a budget guard that under-counts does
not fail loudly, it quietly lets the run spend past the limit it exists to hold. An
unrecognised model is priced at the dearest card we know rather than at zero, for the same
reason: over-reporting is a nuisance, under-reporting is the failure.

### Which model runs which stage

| Stage | Model | Why |
|---|---|---|
| `search-and-verify` | `claude-sonnet-5` | The model only **proposes** candidate addresses. `refresh.py` does the judging: it fetches every proposal, refuses editorial hosts by name, and refuses the entry's own source URL outright. A noisier candidate list is a cost the gate already absorbs — it was that gate, not the model, that caught a Hypebeast article offered as a buy link. |
| everything else | `claude-opus-5` | Availability is the case that decides it: that stage can **move a tier** on the strength of what the model says it read, and no downstream code re-checks the judgement. It is exactly the wrong place to trade accuracy for price. |

Both are repository *variables*, so the lever can be pulled or put back without a deploy:
`WDI_SEARCH_MODEL` overrides the search stage, `WDI_MODEL` the default for every other
stage. Unset arrives from Actions as an empty string, which is read as *no opinion* and
falls back to the defaults above. The per-stage cost table in every run report names the
model each stage ran on — without it a per-call figure is uninterpretable, and comparing
this week's to last week's across a model change is precisely the mistake it prevents.

### The rules that matter more than coverage

These are enforced in code and covered by `test/refresh_test.py`, which gates the job:

- **An unreadable page changes nothing.** A 403, a timeout, a bot wall, a JavaScript-only
  page and a page with too little text are all *silence*, not evidence. Hodinkee, Farer
  and Junghans block automated reads; expect 60–75% of checks to return a usable answer.
  That is fine. False confidence is not.
- **Gone requires proof.** An entry only flips to `Gone` on a high-confidence verdict
  backed by a verbatim quote from the page. "Contact us", "find a boutique" and an
  unrecognisable page never demote anything — those describe distribution, not demand.
- **The blast radius is capped.** If a run wants to flip more than 15% of the register to
  `Gone`, it refuses to commit and opens an issue instead. That pattern means the fetch
  layer broke, not that the market cleared.
- **Silence is a failure.** If not one page in the availability pass was readable, the
  run fails red rather than reporting a quiet week.
- **Entries are never deleted and ids are never rewritten.** Sold-out watches are the
  historical record; the premise of the site is knowing what's gone.
- **A ledger name is never guessed.** A wrong maker attribution is a factual claim about
  who built a watch, and an invented model word is worse than a long one. Both leave the
  field unset — the entry shows its full name, which is plain but true — and the name is
  listed under *For design* in the report.
- **An editor's correction is never overwritten.** Once a name is set by hand it outranks
  everything the job can produce.

### Running it by hand

```bash
pip install anthropic requests
export ANTHROPIC_API_KEY=...

python3 test/refresh_test.py                      # decision-logic tests, no key needed
python3 scripts/refresh.py --dry-run              # full run, writes nothing
python3 scripts/refresh.py --stages 3 --no-api    # photograph backfill only, no key needed
python3 scripts/refresh.py --budget 1.00          # tighter ceiling for one run
python3 scripts/refresh.py                        # the real thing
```

Exit codes: `0` committed · `10` nothing changed · `20` blast radius exceeded ·
`21` fetch layer silent · `1` hard error.

---

## Data model

Each object in `data.json → watches[]`:

| Field | Notes |
|---|---|
| `id` | Stable hash of brand + model. **Never change it** — updates match on this. |
| `brand` `model` `ref` | Identity. `ref` may be `—`. |
| `cat` | Swiss majors · Independents · Japanese · Accessible & micro |
| `desc` `specs` | Prose description; one-line spec summary. |
| `edition` | Free text ("250 pieces", "Unconfirmed"). The list view abbreviates it. |
| `price` | Display string exactly as sourced, including currency notes. |
| `priceNum` | USD number for sorting and price bands. `null` if unknown. |
| `date` | Release or announcement date, free text. |
| `status` | Available · Pre-order · Upcoming · Waitlist · Allocation · Event only · Sold out |
| `tier` `rank` | Availability tier and its sort rank. See below. |
| `buy` `buyLabel` | Purchase URL and the label rendered on the button. |
| `source` | Where the information came from. Credited in the expanded view. |
| `image` `imageCredit` | Photograph URL and the outlet to credit. `null` until resolved. |
| `displayBrand` | Optional. Overrides the brand shown in the ledger — written only when a collab's maker is named *second*. |
| `displayModel` | Optional. Overrides the model shown in the ledger. ≤38 characters, and only words that appear in the full name. |
| `conf` | `high` · `medium` · `low`. Load-bearing — see below. |
| `verified` | `{date, note}` when a purchase page was actually read. `null` otherwise. |
| `soldOutOn` `addedOn` | Dates for the audit trail. |

Tier ranks, which drive the default sort:

```
0 Buy online now      3 Waitlist or ballot     6 Gone
1 Drop upcoming       4 AD or boutique
2 Retailer enquiry    5 In person only
```

---

## Editorial rules

These are what separate this from an auto-generated aggregator. Don't erode them.

- **Limited editions only.** Numbered runs, capped annual production, ballot pieces,
  single-retailer exclusives. Unnumbered special editions may be listed but must be
  labelled as such. No regular production. **No restocks.**
- **Tiers describe distribution, not demand.** "AD or boutique" means the brand doesn't
  sell it online. It is not a guess about whether stock exists.
- **Stock claims require a check.** The green mark means someone read that purchase page
  on that date. Everything else is classified by distribution model. Never blur the two.
- **Confidence is stated honestly.** A lot of 2026 pricing exists only on aggregator
  sites. Saying so is the point.
- **One outbound click.** The only link a visitor should follow off the site is the one
  that buys the watch. Attribution links stay subordinate.

## Method

Relocated here from the foot of the site on 2026-08-05, when the material below the
register was cut. It was written for a collaborator rather than a visitor, and this is
where a collaborator reads it.

- **Limited editions only.** Numbered runs, capped annual production, ballot pieces and
  single-retailer exclusives. Unnumbered special editions are included but labelled as
  such.
- **Confidence is stated, not implied.** High means a brand source or several credible
  outlets agree; medium means one credible source; low means a single aggregator or an
  unresolved conflict.
- **Stock status is only claimed where checked.** Entries with a green check had their
  purchase page read on that date. Everything else is classified by how the brand
  distributes. The one-sentence version of this is the only piece of it that still
  appears on the site, because it is what a reader needs to interpret the mark.
- **Converted prices are marked with a tilde.** Sorting uses the USD estimate, so ranking
  near a band boundary is approximate.
- **Photographs are drawn from the reporting outlet** that covered each release, credited
  beneath the image, and used to identify the watch being indexed. See **Takedowns**
  below for what happens when a rights holder objects.

## Known gaps

The honest record of what the register does not know. Kept deliberately — an index that
does not publish its own holes is claiming more coverage than it has. Each of these is
researchable and none of them is blocked.

- Grand Seiko and Seiko's H2 2026 announcements are not yet captured. The source roundup
  used covers January–June only, so a whole half-year of Seiko, Grand Seiko, Credor and
  Citizen limited editions is missing. `plus9time.com` is the thorough source.
- F.P. Journe surfaced no 2026 limited edition across four independent sources. That is
  almost certainly a search-coverage failure rather than a real absence.
- Casio rarely discloses G-Shock edition sizes; only the MR-G Phoenix carries a confirmed
  number.
- Minase, Knot, Zelos, Certina, Mido, Rado, Nomos and Zodiac are not researched to
  completion.
- Rolex issued no numbered limited editions in 2026.
- Open price conflicts, each dragging an entry's confidence rating down until one
  authoritative source settles it: Patek 5810/1G-001 (CHF 60,000 vs 75,000),
  AP × AMBUSH (USD 225,000 vs 267,000), Doxa × Hodinkee edition size (200 vs 250).
- **Verification coverage.** Only a small fraction of entries carry a real `verified`
  stock check; the rest are classified by distribution model. That is sound reasoning
  but it is not the same claim, and "we actually checked" is the site's differentiator.
  A backfill over the buyable tiers is specified and waiting on a measured cost figure.

## Takedowns

Photographs are published under an editorial-use rationale: they come from the
publication that reported each release and are credited individually. That position holds
only while a rights holder has an obvious route to object, which is why
`wdi-takedown@conn.llc` is permanently visible in the site footer.

**The address is deliberately on `conn.llc`, not on the site's own domain.**
`takedown@watchdropindex.com` was the obvious choice and it was the choice, until it was
tested. `watchdropindex.com` has no mailbox of its own and depends on registrar
forwarding — and forwarding breaks SPF, because the message arrives at the destination
from the forwarder rather than the original sender, while the domain publishes a hard fail
(`v=spf1 a mx -all`). The likely result is a takedown notice filed silently as spam, which
is the same black hole as publishing no address at all, except that it looks like due
process. `conn.llc` runs Cloudflare Email Routing, which rewrites the envelope sender on
forward and therefore re-establishes SPF rather than breaking it. Conn LLC is also already
named in the footer as the trademark holder, so this is the honest address rather than a
workaround. **If the address ever moves back to the site's domain, that domain needs a real
mailbox first, not forwarding.**

Honouring a request is **two steps, not one**: null the entry's `image`, *and* add the URL
to the do-not-resolve list. Step one alone lasts exactly until the next photograph pass,
which re-reads the same article, finds the same `og:image` and puts it back — so a removal
would undo itself within a day. Two steps is the difference between complying and
appearing to comply.

One command does both:

```bash
python3 scripts/refresh.py --stages "" --takedown "https://…/photo.jpg" \
  --takedown-note "who asked, and when"
```

It records the rule in `data.json` under `suppressed`, clears that picture from every entry
using it, and leaves the entry, its source link and its provenance intact — the objection
is to republishing the photograph, not to the fact that the outlet reported the watch. The
entry simply carries no picture, which the register already renders honestly.

The list is enforced at load on **every** run, before any stage reads an image, so a rule
added by hand or through the admin panel takes effect immediately rather than whenever the
rot check next visits that entry. Two rule shapes are honoured:

```jsonc
{"url": "https://…/photo.jpg", "on": "2026-08-05", "note": "…"}   // one photograph
{"domain": "example.com",      "on": "2026-08-05", "note": "…"}   // an outlet, wholesale
```

URL matching ignores a tracking query string and a `www.` prefix; a domain rule covers
subdomains but not lookalike domains.
