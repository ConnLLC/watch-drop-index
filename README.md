# Watch Drop Index

**watchdropindex.com** — the limited-edition register.

Every limited-run watch of 2026: what it costs, whether you can still get one, and
where to buy it. Limited editions only — no regular production, no restocks.

252 entries · 94 brands · 60 currently buyable online.

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

For that to hold, the figures in the masthead, the availability filter counts and the
colophon are all re-read from `data.json` at load rather than trusted as built. The
build-time values stay in the markup as the pre-JavaScript default. **If you rewrite the
template, keep the `#t-*` and `#c-*` anchors** — without them the page keeps advertising
whatever the numbers were the day it was built, which quietly breaks the freshness claim
the whole site rests on. `test/template.test.js` fails loudly if they go missing.

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

## The weekly refresh

`.github/workflows/refresh.yml` runs `scripts/refresh.py` at 09:00 UTC each Monday, and
on demand via **Actions → weekly refresh → Run workflow**. It runs in CI rather than as
a scheduled chat session so the API key lives in Actions secrets, the job runs whether or
not anyone is logged in anywhere, failures surface as red runs instead of silence, and
every change is an attributable, revertible commit.

Because Pages deploys from `main`, **the commit is the deploy**.

Each run:

1. **Loads** `data.json` and validates it. If it doesn't parse, the run aborts having
   changed nothing.
2. **Re-checks availability** for every entry at rank 0–2 — about 90 purchase pages.
   Each page is fetched, reduced to text, and judged by the model against the entry's
   current tier. Positive evidence of a sell-out flips the entry to `Gone`, stamps
   `soldOutOn`, and writes a `verified` note quoting the page. Entries move **up** too:
   a pre-order opening or stock appearing online promotes them.
3. **Backfills photographs** by reading `og:image` from each entry's source article,
   36 per run. Sources with no `og:image` and dead URLs are recorded so they aren't
   probed again every week.
4. **Searches the watch press** for limited editions announced since `meta.updated`,
   restricted to a fixed list of credible outlets, then converts the findings into
   entries — refusing any candidate without a source URL, a buy URL, or limited-edition
   status.
5. **Commits** with a summarising message and a full report in the body.

### What it needs

One repository secret: **`ANTHROPIC_API_KEY`** (Settings → Secrets and variables →
Actions). Nothing else — the job pushes with the built-in `GITHUB_TOKEN`.

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

### Running it by hand

```bash
pip install anthropic requests
export ANTHROPIC_API_KEY=...

python3 test/refresh_test.py                      # decision-logic tests, no key needed
python3 scripts/refresh.py --dry-run              # full run, writes nothing
python3 scripts/refresh.py --stages 3 --no-api    # photograph backfill only, no key needed
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
