# C. Systems Architect

*Prompt: data model, service boundaries, agent-facing API contract, scaling
break points. Assume §5 signal data is available daily. Also covers the signal
validity questions (Q5–Q7), because the back-test harness is architecture.*

---

## 0. Where this repository actually is today

Before designing anything, the honest baseline, from the code in this repo:

| Brief §5 requires | `market_snapshot.py` today |
|---|---|
| impressions, detail views, watchlists, leads as distinct funnel stages | `REQUIRED_WEBSTATS_COLS = {"StockNumber", "Views"}` — a single collapsed metric |
| week-over-week impression decay | no time dimension at all; `DaysOnMarket` is a scalar on a snapshot |
| a score that separates top-of-funnel from bottom-of-funnel failure | `BuyerEngagementScore = Views / DaysOnMarket` — one ratio that cannot distinguish them |
| valuation bands (auction / wholesale / market / asking / retail) | `ListPrice` and `AuctionValue` only |

Two things follow, and the first one is nearly free:

1. **`webstats.csv` already carries `UniqueVisitors`, `Inquiries`, and
   `SavedToWatchlist`.** The funnel is in the file and the pipeline discards it.
   Every diagnostic state in §5 needs those columns, and three of the four need
   them as a *time series*.
2. **The pipeline overwrites its inputs' history every run.** Nothing in §5 is
   computable without daily snapshots, and today they are thrown away. The single
   highest-value, lowest-cost action in this entire evaluation is:

   > **Start persisting a dated row per listing per day, today, before any of
   > this is built.** Every week you wait is a week of training data that does
   > not exist. The signal layer cannot be back-filled from a snapshot.

That is step zero and it does not require agreeing with any other conclusion in
this directory.

---

## 1. Data model

Natural keys matter here more than usual, because the whole thesis rests on
joining behavior to valuation on the same physical machine.

**Identity**

- `asset` — one physical machine. PK `asset_id`; natural keys `vin` and
  `serial_number`, plus `(make, model, year)`. Serial/VIN normalization is the
  hard part: the same machine appears as `A6L01234`, `A6L-01234`, and
  `a6l01234` across three source exports. Resolution is a service, not a
  `str.strip()`.
- `party` — seller, buyer, lienholder, inspector, transporter. Identity-verified
  for anyone who can be bound by an offer.

**Listing and commitment**

- `listing` — one attempt to sell one `asset` at one venue. State machine:
  `DRAFT → LISTED → COMMITTED → LIVE → {SOLD, WITHDRAWN, EXPIRED} → SETTLING → CLOSED`.
- `commitment` — tier (`POSTING` | `SELLING`), signed consignment document ref,
  bond/deposit ref, `reserve_ref` (a pointer, never a value — see §3).
- `price_schedule` — **immutable, versioned, content-addressed**. Fields:
  `schedule_id`, `listing_id`, `rule_id` (which published `f` produced it),
  `inputs_digest`, `steps[]`, `signature`, `authored_at`, `signed_by`.
- `price_step` — `(schedule_id, step_index, effective_at, price)`. Precomputed
  rows, never arithmetic at read time.

**Signal**

- `signal_observation` — `(listing_id, source, observed_on, impressions,
  detail_views, watchlists, leads, featured_ad_active, photo_count, ...)`.
  One row per listing per source per day. Append-only. This table is the asset.
- `valuation` — `(asset_id, provider, as_of, auction, wholesale, market, asking,
  retail)`. Slowly changing; keep every vintage.
- `score_run` — `(listing_id, model_version, run_at, score, state, verb)`.
  Versioned so a score can always be reproduced from its inputs.

**Demand and settlement**

- `standing_order` — a funded buy-side threshold: `(party_id, spec, max_price,
  expires_at, escrow_ref)`. Never disclosed, never counted publicly.
- `offer` — binding, stamped against a `step_id` (not a wall-clock timestamp).
- `settlement` — escrow, title status, lien payoff, inspection report,
  transport. Mostly workflow around humans; model it as a case, not a
  transaction.

---

## 2. Service boundaries

```
  ingest ──► identity resolution ──► signal store (append-only)
                                          │
                                          ▼
                                   scoring (batch, versioned)
                                          │
                                          ▼
                          schedule authoring  ◄── human approval + signature
                                          │
                                          ▼
                    publication (immutable, signed, CDN) ──► agent feed (read)
                                          ▲                          │
                                          │                          ▼
                          listing state machine ◄────────── offers / standing orders (write)
                                          │
                                          ▼
                                    settlement (case workflow)
```

Four boundary rules carry real weight:

**Signals are eventually consistent; the price path is strongly consistent.**
Telemetry arrives daily in batch and may be late, revised, or missing. A price
step is a legal commitment. Never let the second depend on the freshness of the
first — which is another argument for freezing the slope at authoring time
(mechanism design §8): a frozen schedule cannot be corrupted by a late or bad
signal load.

**The published path is an artifact, not a query.** Precompute every step,
hash the step list, sign it, serve it from a CDN. Once published, steps are
immutable; the only permitted mutation is terminating the whole listing. If a
price can be recomputed at read time, two agents can see two prices, and the
commitment is worthless.

**Offers bind to `step_id`, not to a timestamp.** This removes the entire class
of race conditions at step boundaries and makes "what price was in effect" a
lookup rather than an argument.

**Settlement is a separate system with a separate failure domain.** It is
allowed to be slow, human, and stateful. Nothing in the read path may block on
it.

### Reserve isolation

The reserve gets its own encrypted store behind its own access boundary, and
**the scoring and schedule-authoring services have no read credential for it.**

This is the topology-level enforcement of the mechanism designer's §3: if `f`
cannot read the reserve, `f` cannot leak it, and that property is verifiable by
inspecting IAM policy rather than by trusting a code review. Reserve
comparison happens in one place — a small `reserve_check(listing_id, price) →
bool` service that takes a price and returns a boolean, and never returns a
number to anything.

---

## 3. Agent-facing contract (Q9)

The important realization: **a deterministic published schedule needs no
polling.** If the full future path is signed and published, an agent fetches it
once and evaluates thresholds locally, forever. Polling is only needed for
*state changes*.

That inverts the usual design:

**Read path — public, unauthenticated.** Maximum agent reach is the point of
being an oracle; an auth wall on public prices defeats the strategy.

- `GET /v1/listings/{id}` — asset, spec, condition, inspection ref, current
  step, `schedule_id`, `signature`.
- `GET /v1/listings/{id}/schedule` — the signed step list, the `rule_id`, and
  the digest of the public inputs that produced it. **Includes the next N
  steps. Does not include the terminal price or terminal date.**
- `GET /v1/rules/{rule_id}` — the published slope function `f`. This is what
  makes the commitment auditable.
- `GET /v1/changes?since={cursor}` — cursor-based change feed, listing-level
  state transitions only. This is the sole thing worth polling.
- `POST /v1/webhooks` — push for terminal events (`SOLD`, `WITHDRAWN`,
  `EXPIRED`, `SCHEDULE_TERMINATED`). Signed payloads, at-least-once, so
  consumers must be idempotent.
- MCP server wrapping the same read surface, so an agent can call it
  conversationally without an integration project.

**Write path — authenticated, identity-bound.**

- OAuth client credentials per agent, but an offer or standing order must carry
  a **verified human or corporate principal**, because it is a binding
  commitment of funds. An agent acts *for* a party; it is never the party.
- `POST /v1/listings/{id}/offers` — idempotency key required, binds to
  `step_id`.
- `POST /v1/standing-orders` — funded threshold, escrow ref required.

**Threshold-firing semantics.** Two tiers, and the distinction is the business:

- *Advisory* (free, client-side): the agent has the path, computes its own
  trigger, and notifies its principal. Costs you nothing, spreads reach.
- *Binding* (paid, server-side): a funded standing order that executes
  automatically when a step crosses it. This is the revenue line, and per the
  mechanism designer it is also the mechanism's missing rival hazard.

**Never publish demand.** No watcher counts, no view counts, no
"3 agents are tracking this." It would be the most requested feature and it
would hand the buy side a collusion-monitoring tool. Make the omission explicit
and documented so it does not get "fixed" by a well-meaning PM in year two.

---

## 4. Signal validity (Q5–Q7)

**Does funnel shape transfer across categories and price points?**

Partially, and only after normalization. Raw counts do not transfer — a
$25k skid steer and a $400k combine differ by an order of magnitude in
impressions for reasons that have nothing to do with pricing. What can transfer
are **stage-to-stage conversion ratios expressed as within-category-week
percentiles**: impression→detail-view rate, detail-view→watchlist rate,
watchlist→lead rate.

**How to falsify it.** Fit the score within one category with enough completed
sales (Class 8 trucks). Then predict a held-out, structurally different
category (ag tractors) with no re-fitting. If the coefficient signs flip, or
the calibration curve on the held-out category is flat, the transfer assumption
is dead and the score must be built per-category — which changes the volume
requirements below by an order of magnitude. Run this test *before* building a
cross-category product. It is a week of work against data you already have.

The specific falsifier for the money signal in §5: does the
*high-detail-views + rising-watchlists + zero-leads* state actually predict a
lower realized-price-to-ask ratio and longer days-to-sale, out of sample? If it
does not, that state is folklore and the product's central claim is unsupported.

**Confounds besides price.** Featured-ad spend (the platform sells impressions
directly — this alone can dominate the top of the funnel and it is in the
webstats export as an ad flag), photo count and quality, description
completeness, listing age interacting with algorithmic decay, day-of-week and
seasonality, buyer-density proximity, "call for price" versus a displayed
number, make/model desirability independent of condition, and whether the unit
is also listed elsewhere.

**Separating a pricing failure from a photography failure, statistically.**
Use a sequential hurdle model, one stage per funnel transition, with a genuine
exclusion restriction:

- Stage 1 (impression → detail view): grid-displayed price, photo features
  (count, resolution, has-interior, has-hour-meter/odometer shot), title text,
  featured-ad flag.
- Stage 2 (detail view → watchlist/lead): full price context (ask relative to
  the valuation bands), condition disclosure, inspection report presence.

Photo features enter stage 1 and are **excluded** from stage 2; the ask/market
ratio dominates stage 2. That exclusion is what identifies the two failures
separately, rather than the current heuristic reading of one blended ratio.

But the decisive point is not the model:

> **Your real asset is not the data — it is the ability to randomize.** You
> control the ask and the photos on consigned units. Randomly re-shoot half of
> a matched cohort. Randomly assign price-step sizes. No incumbent can do this;
> they observe, you can intervene. One randomized photo experiment on 60 units
> settles a question that no amount of observational modeling will.

**Minimum volume (Q7).** The honest answer is about calibration, not count. To
detect a moderate effect (d ≈ 0.4) at 80% power needs roughly 100 outcomes per
cell, and cells are category × price band × season. Realistically:

- **< 200 completed sales with hammer outcomes:** it is a heuristic. Label it
  one. Do not publish it as a score.
- **~500–1,000 outcomes:** defensible for a single category, *if* you publish a
  calibration curve and a Brier score alongside every prediction.
- **Cross-category pooling** via percentile normalization is what gets you to
  those numbers faster — and it is exactly the assumption the falsification test
  above is designed to check first.

A well-calibrated score on 300 sales is more defensible than an uncalibrated one
on 30,000. Publish the calibration, always, including the misses. It is also the
best defense against the competitor's inevitable "his sample is one regional
dealer account" attack.

---

## 5. Break points: 100 listings vs. 100,000

**At 100 listings, nothing technical breaks.** It all fits in one Postgres
instance with a nightly job. Do not build streaming, a service mesh, or a
lakehouse. The binding constraints are human: schedule authoring, inspection
scheduling, title and lien work. Expect a week of ops per listing spread across
its life. **The organization is the bottleneck, and it is measured in people.**

**At 100,000, five things break, in this order:**

1. **Identity resolution.** Serial/VIN matching across sources at scale is a
   dedicated entity-resolution problem with a human review queue. At 100 you
   eyeball it; at 100k, a 2% mismatch rate is 2,000 machines with wrong
   valuations attached, and wrong valuations become wrong prices, which is a
   legal problem rather than a data-quality one.
2. **Score sparsity.** Counter-intuitively, 100k listings does *not* fix thin
   cells. Category × region × price band × season fragments faster than volume
   accumulates, and the tail categories stay unpowered forever. Plan for a
   hierarchical model with explicit shrinkage toward category means, and for
   refusing to score cells that lack support.
3. **Settlement headcount.** Scales linearly. This is the actual wall. Escrow,
   title, lien payoff, and dispute handling do not get cheaper per unit, and the
   brief correctly identifies this layer as mandatory. A software company with a
   linear-headcount cost center is an auction company with worse margins — which
   is the structural tension the synthesis document takes up.
4. **Step-boundary thundering herd.** If every schedule steps at 00:00 UTC,
   every agent's threshold fires simultaneously and the whole buy side arrives in
   the same second. Fix cheaply and early: derive each listing's step time from
   `hash(listing_id) % 1440` minutes, so descents spread across the day. Costs
   one line at authoring time and cannot be retrofitted onto published
   schedules.
5. **Regulatory surface.** Fifty states of title, lien perfection, sales-tax
   nexus, and auctioneer licensing. This binds well before 100k and it is the
   one break point that cannot be engineered around.

---

## 6. Build order

1. **Persist daily signal snapshots.** Today. Nothing else works without it.
2. **Widen the pipeline to the full funnel** — `UniqueVisitors`, `Inquiries`,
   `SavedToWatchlist` are already in `webstats.csv` and already discarded. Keep
   the required-column lists in `market_snapshot.py`, `MARKET_SNAPSHOT_README.md`,
   and the tests in sync, per this repo's rules.
3. **Back-test against hammer prices.** Falsify the transfer assumption before
   building on it.
4. **Publish the rule `f` and the calibration curve.** The oracle is credible
   or it is nothing.
5. **Only then** the schedule authoring, the public path, and the feed.

Steps 1–4 have standalone value to the existing auction business even if the
marketplace is never built. That is the correct property for a first phase.
