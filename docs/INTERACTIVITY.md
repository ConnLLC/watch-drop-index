# Interactivity — specification only, deliberately not built

Filed 2026-08-05. **Nothing in this document is implemented, and none of it should be
built without being asked for.** It exists so that the admin tools shipped alongside it did
not quietly foreclose any of it.

The framing, and it is the right one: the site is a **statement of record** first, and
gains utility as an audience arrives. Voting is wanted eventually, not now.

---

## 1. Why the GitHub token cannot do this

The admin panel writes to `data.json` with a GitHub PAT held in `sessionStorage`. That
works because exactly one trusted person ever holds it. Votes come from anonymous
strangers, so the same mechanism would mean **shipping a write-capable token to the
public** — which is giving every visitor commit access to the repository.

Separately, git is not a database:

- concurrent votes are merge conflicts,
- every vote triggers a Pages rebuild,
- the API rate limit is the wrong shape entirely.

Interactivity needs a real write endpoint. There is no clever way around this, and anyone
who thinks they have found one has found a way to publish a write token.

## 2. Shape when it comes

- A **Cloudflare Worker + KV or D1**. Generous free tier, and a `workers.dev` endpoint is
  callable cross-origin, so the domain does not have to move off NameSilo. Supabase or
  Firebase are equally valid.
- **Votes keyed by entry `id`.** The id is already immutable — `md5("brand|model")[:10]`,
  never rewritten because doing so orphans that watch's verification history — so the key
  is stable across every future refresh. This is a dependency the admin work already
  satisfies rather than one to add later.
- **Counts read at page load; the static site stays static.** Votes never enter
  `data.json`. The register's git history is an audit trail of availability, and mixing
  engagement data into it makes that history worth less.

## 3. Abuse — the part that decides whether the numbers mean anything

Without mitigation, one person with a script sets the rankings, and then the numbers are
worse than no numbers because they look like evidence.

Minimum: rate limit per hashed-IP per day. Store a **salted hash, never a raw IP** — this
is a hobby register and there is no reason for it to hold identifiable data. No accounts at
first.

## 4. Cold start — a real risk to credibility

Every watch showing zero reads as abandoned. Suppress display below a threshold rather than
publishing a wall of noughts.

## 5. The editorial constraint, and it is the important one

**The seven availability marks describe DISTRIBUTION, NOT DEMAND.** That distinction is the
spine of this register: "AD or boutique" means the brand does not sell it online, not that
it is hard to get.

A vote count is a pure demand signal. Put it next to those marks and it *will* be read as
one, and "popular" will start bleeding into "hard to get". When this is built, votes must
be **visually and semantically separate** from the availability system. That is a
constraint, not a preference, and design owns how it is honoured.

## 6. Adjacent, sharing the same endpoint

- **Watchlist / notify-me on a drop.** Genuinely useful on a site about time-limited
  things, and it drives return visits. Note: collecting emails is personal data and
  triggers a privacy notice. The site currently collects **nothing**, which is a good
  position to leave deliberately rather than lose accidentally.
- **"I own this"** — a fact rather than an opinion, and better fitted to a register.

## 7. The one we already have, and it is better than votes

The register **already measures demand**: `soldOutOn` minus `addedOn` is time-to-sell-out.

A watch that goes from "Buy online now" to "Gone" in 48 hours is *revealed* preference, not
stated preference. It is unstuffable, needs no backend, has no cold start and no abuse
surface, and it is already instrumented — `soldOutOn` is stamped by the availability stage
whenever an entry flips.

"Sold out in 3 days" is simultaneously a fact and a popularity signal, which is precisely
the shape this site is good at. It needs no permission from anyone and gets more valuable
every month the register runs.

**If an opinion layer is ever wanted, start here.**
