# Watch Drop Index

**watchdropindex.com** — the limited-edition register.

Every limited-run watch of 2026: what it costs, whether you can still get one, and
where to buy it. Limited editions only — no regular production, no restocks.

252 entries · 94 brands · 60 currently buyable online.

---

## How it works

```
index.html    The site. Template only (~31 KB). Reads data.json in the browser.
data.json     The source of truth. Every watch, plus the calendar sections.
build.py      Regenerates index.html. Only needed when the TEMPLATE changes.
.nojekyll     Stops GitHub Pages running Jekyll over the files.
netlify.toml  Config if you host on Netlify instead. Harmless on Pages.
robots.txt
sitemap.xml
404.html
```

The important property: **routine updates never touch `index.html`.** The page fetches
`data.json` at load, so adding a watch or flipping something to sold-out is a one-file
change. Commit `data.json`, Pages redeploys, done. `build.py` is only for layout changes.

### Running it locally

Browsers block `fetch()` on `file://`, so opening `index.html` by double-clicking shows
a load error. Serve it instead:

```bash
python3 -m http.server 8000
# then open http://localhost:8000
```

---

## Deploying to GitHub Pages

1. Create a repo — `watch-drop-index` — and push these files to the root of `main`.
2. **Settings → Pages → Source:** "Deploy from a branch", `main`, `/ (root)`. Save.
3. Live in ~2 minutes at `https://<you>.github.io/watch-drop-index/`.
4. **Custom domain:** Settings → Pages → Custom domain → `www.watchdropindex.com`.
   GitHub will tell you the DNS records; at your registrar add a `CNAME` for `www`
   pointing at `<you>.github.io`, and enable "Enforce HTTPS" once it validates.

Every update becomes a commit, so the repo history doubles as an audit trail of when
each watch sold out — which for a site about availability is content, not just hygiene.

---

## The weekly refresh

The refresh is a **scheduled Claude task**, not a cron job, because it has to read live
retail pages and judge what they say. Each Monday it:

1. Fetches `data.json` from the live site.
2. Opens the purchase page for every entry currently marked **Buy online now**,
   **Drop upcoming** or **Retailer enquiry** — about 90 pages — and reads stock status.
3. Flips anything that's gone to `Gone`, stamps `soldOutOn`, and writes a `verified`
   note recording the date and what the page actually said.
4. Resolves missing photographs by reading the `og:image` of each entry's source
   article, in batches, until coverage is complete.
5. Searches the week's watch press for limited editions announced since the last run
   and appends them with `addedOn` set.
6. Commits `data.json` to the repo. Pages redeploys automatically.

### What it needs from you

A **fine-grained personal access token**, scoped as narrowly as possible:

- GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
- **Repository access:** Only select repositories → `watch-drop-index`
- **Permissions:** Repository permissions → Contents → **Read and write**. Nothing else.
- **Expiry:** 90 days. Set a reminder to rotate it.

That token lives in the scheduled task's configuration. Be clear-eyed about the
trade-off: it's a credential stored in a task prompt. Scoped this way the worst case if
it leaks is that someone can edit one hobby repo — no access to your account, your other
repos, or anything else. Rotate on expiry and it stays contained.

### Failure modes to expect

- **Bot protection.** Hodinkee, Farer and Junghans already block automated reads.
  Expect 60–75% of checks to return a usable answer. The rule is that an unreadable page
  leaves the entry **unchanged** — never flip something to sold out because a bot filter
  said no.
- **Photograph coverage** will plateau below 100%. Some sources have no `og:image`, and
  a few hotlinks will rot over time; the `onerror` handler degrades to a caption.
- **Silence is a failure.** If a run reports zero changes across 90 checks, something
  broke — that's not a quiet week, that's a bug.

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
