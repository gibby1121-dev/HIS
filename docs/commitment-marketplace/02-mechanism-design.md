# B. Mechanism Designer — auction theorist

*Prompt: evaluate descending-clock-with-private-reserve for a thin market with
unique goods and non-repeat participants. Buyer waiting, collusion, reserve
leakage. Propose two alternatives and argue why each might beat it.*

---

## 0. A premise correction that changes the analysis

The brief asserts (§1, §9.2) that there are **no repeat participants**. That is
true of sellers and false of buyers.

The seller sells one combine in a lifetime. The buyers — regional dealers,
flippers, fleet buyers, owner-operators upgrading on a cycle — transact
repeatedly, know each other, and in many categories are the same fifteen phone
numbers year after year. The market is one-shot on one side and repeated on the
other.

That asymmetry is the single most important structural fact in the design, and
the brief drops it. Every conclusion below follows from it: a repeated-game
buyer pool facing one-shot sellers is the textbook environment for tacit
collusion, and it is also why the buy side — not the sell side — is where
revenue and commitment devices should sit.

---

## 1. Buyer incentives to wait

Take a buyer with private value `v`, facing a published, deterministic price
path `p(t)` descending to a known terminal price `p_T`. Let `λ` be the per-step
hazard that some rival takes the item.

The buyer accepts at step `t` only if

    v − p(t)  ≥  (1 − λ)·[ v − p(t+1) ]

i.e. immediate surplus must beat discounted surplus from waiting one more step.
Rearranged, the buyer buys now only when

    λ·(v − p(t))  ≥  p(t) − p(t+1)

**The willingness to buy early is entirely a function of `λ`.** The step size
only matters relative to it. As `λ → 0`, the condition fails at every step and
the buyer's optimal strategy is to wait for `p_T`.

This produces the result that should govern the whole design:

> **A fully published, deterministic descending path with a known endpoint,
> in a market with negligible rival hazard, is strategically equivalent to a
> posted price at `p_T` — arriving late.**

It is not merely no better than posting the floor. It is strictly worse, by the
carrying cost of the delay and by the information the seller surrendered on the
way down. Every intermediate price on the path is a price no one will ever pay.

So the mechanism has bite only if at least one of these holds:

- **(a) `λ` is material and believed.** Requires visible or credible rival demand.
- **(b) `p_T` is unknown.** Requires *not* publishing the endpoint — which is in
  tension with the "commitment" framing.
- **(c) The buyer has an exogenous clock.** Real and underexploited: contract
  award dates, planting and harvest windows, a driver starting in three weeks,
  Section 179 / fiscal-year-end depreciation timing. When the buyer's own
  deadline precedes the seller's terminal date, `λ` is irrelevant — waiting has
  a private cost.
- **(d) Termination is stochastic.** If the listing may end at any step for
  reasons the buyer cannot observe, waiting carries genuine risk of total loss.

(a) cannot be manufactured honestly by an interested platform. (b) weakens the
commitment story but is recoverable. **(c) and (d) are where the design should
live**, and neither appears in the brief.

Practical consequence of (c): **stop thinking of the clock as the seller's
schedule and start setting it against the buyer's calendar.** A descending
window that terminates the week before spring planting, or in the last week of
December, borrows a forcing function that already exists in the buyer's
business and costs you nothing to create.

---

## 2. Collusion with 5–20 buyers

A public descending clock is the **most** collusion-friendly major format, and
this is a well-established result, not a speculation.

Under sealed-bid or ascending formats, a ring member who defects wins the entire
item immediately and profitably. Defection is fast, unilateral, and rewarded, so
rings need enforcement to survive.

Under an asynchronous public descending clock with no rival visibility, the ring
needs **no agreement and no enforcement at all**. "Nobody buys before day 21" is
not a cartel rule that must be policed — it is what each buyer's individually
optimal strategy already recommends (see §1). Tacit collusion here is
self-enforcing precisely because it is indistinguishable from rational patience.
There is nothing to defect *from*.

Two aggravating factors specific to your design:

- **Your transparency arms the ring.** A published path plus published telemetry
  is a shared monitoring device. In a thin market, transparency about *demand*
  is anti-seller: it lets buyers verify that no one has jumped, which is exactly
  the information a ring would otherwise have to pay to acquire.
- **The buy side is the repeated side.** These fifteen dealers meet again next
  month. Reputational enforcement, should it ever be needed, is already
  available to them. It is not available to your one-shot seller.

**Implication:** never publish watcher counts, offer counts, or view counts on a
live listing. Uncertainty about rival demand is not a UX deficiency to be
polished away — it is the seller's only remaining asset, and the product's job
is to protect it.

---

## 3. Reserve leakage

Leakage happens through three channels. Only one of them is widely noticed.

**Channel 1 — the endpoint.** If the published path terminates at the reserve,
the reserve is published. This is total leakage and it is the default outcome of
a naive implementation.

**Channel 2 — the slope.** If slope is a function of the reserve (e.g. "we
descend faster when the seller's floor is far below the ask"), then the slope is
a sufficient statistic for the reserve. Any buyer with two listings' worth of
observations inverts the mapping. This is the channel the brief's Q3 is asking
about, and it has a clean, structural fix:

> **Make the slope a published deterministic function of *public* telemetry
> only. Forbid the reserve from entering that function — not by policy, but by
> service topology (see the architecture document, §Reserve isolation).**

If `slope = f(public signal)` and `f` is published, then the slope reveals
exactly what buyers can already see and nothing more. Leakage through this
channel becomes zero *by construction*, and you get a bonus: publishing `f`
makes the schedule auditable, which is what turns a commitment into a credible
one.

**Channel 3 — behavior over the seller population.** Even with 1 and 2 sealed,
buyers observe which listings terminate early. Over a cohort, early
terminations correlate with reachable reserves and teach the pool where floors
sit in each category. This is unavoidable and acceptable; it is ordinary market
learning, not a leak of any individual's number.

The mitigation for Channel 1 is also the mitigation for §1's waiting problem,
which is why it is the highest-value single change to the mechanism:

> **Publish the rule and the next N steps. Never publish the terminal price or
> the terminal date. Terminate stochastically.**

Concretely: the listing may end at any step because the seller may accept a
standing offer at any time, and buyers are never told whether standing offers
exist. This restores `λ > 0` without requiring you to lie about demand, and it
leaves the reserve unstated forever. The seller commits to descending; they
never commit to how far, and no one learns where the floor was unless it is met.

---

## 4. Sellers pulling out mid-clock

Without a bond, "commitment" is cheap talk, the badge is fraudulent, and the
badge is the entire buyer-side value proposition. A tier that anyone can exit
for free is a tier that means nothing, and buyers price it accordingly within
one season.

Do not solve this with platform terms of service. Solve it with the instrument
this industry already has and courts already understand: **a consignment
agreement with a no-sale fee and liquidated damages.** The seller signs the same
kind of paper they would sign to put the unit in your ring. Withdrawal mid-clock
forfeits a deposit; sale below the path is a breach.

You own an auction company. Commitment is a contract you already have on file,
not a feature you need to build.

---

## 5. Alternative mechanism I — Sealed-bid call for offers with a private reserve

Buyers submit binding, funded offers by a published deadline. The seller accepts
the best offer or none. The reserve is never referenced publicly.

**Why it may beat the clock:**

- **It uses buyer uncertainty instead of requiring you to manufacture rival
  hazard.** A bidder cannot observe rivals, so they must bid their value, not
  their guess about the seller's patience. The `λ` problem disappears because
  there is no "later" to wait for.
- **No capitulation schedule.** The seller never publishes a descending number,
  which also removes the pride objection that kills adoption (see the customer
  walkthrough).
- **Collusion is materially harder.** A defector takes the whole item at a price
  no one else sees. That is the classic reason sealed-bid formats resist rings
  better than open descending ones.
- **Zero reserve leakage by construction.** The reserve is used once,
  privately, at acceptance time.
- **It fits the seller's mental model.** "Best and final offers by the 14th" is
  how farm ground and estates already trade in the Midwest. No auction theory
  required.

**Weakness:** with one bidder it degenerates to a negotiation. But it degenerates
*no worse than the clock does*, and unlike the clock it does not teach the buyer
pool where the seller's floor is on the way down.

---

## 6. Alternative mechanism II — Declining reserve on a live auction ("rolling consignment")

Keep the ring. Keep the gavel. Move the clock from the **ask** to the **reserve**.

The unit runs in your next sale with a reserve. If it does not clear, the reserve
steps down by a contracted percentage and it runs in the following sale. And the
next. The descent is published as a *rule the seller has signed*, and the buyer
pool knows the rule.

**Why it may beat the clock:**

- **It keeps the real forcing function.** Price is discovered by rival bidders in
  a live, synchronous session where co-presence is genuine. You are not
  simulating rivalry; you have it.
- **The commitment lands on the party that needs to make it.** The seller
  commits to a descending floor. The buyer still has to outbid the person
  standing next to them.
- **It is shippable this quarter with zero new trust infrastructure.** This is a
  clause in a consignment contract, not a marketplace. Settlement, title, lien
  payoff, escrow, and dispute handling already exist and already work.
- **It produces the exact dataset the oracle thesis needs** — committed sellers,
  known descending floors, real hammer outcomes — at a fraction of the cost, and
  it produces it whether or not the venue idea is ever built.
- **It is honest about `λ`.** Buyers who wait for the next sale face a genuine
  hazard: someone in the room takes it.

**Weakness:** discrete sale dates limit granularity, and it does not serve
sellers who refuse the ring outright — but per the red team's objection 2, that
population is adversely selected anyway.

---

## 7. What I would actually build

Ranked, and the ranking is the recommendation:

1. **Rolling declining-reserve consignment** (§6). Cheapest, uses the assets you
   already own, ships as paper.
2. **Funded standing orders on the buy side** — a binding, escrow-backed
   threshold ("I will take it at ≤ $85k, good for 30 days"), never disclosed to
   anyone. This is the single highest-leverage addition in this entire
   evaluation: it is simultaneously (i) the missing `λ`, because neither buyers
   nor the seller know whether one exists, (ii) a revenue line on the side of the
   market that has budget, and (iii) precisely the "threshold-firing" primitive
   the agent layer in §7 of the brief wants — except binding and funded rather
   than advisory.
3. **Sealed-bid call for offers** (§5) for units that refuse the ring.
4. **The published descending clock, last** — and only with stochastic
   termination, an unpublished endpoint, a slope frozen at authoring time, and a
   bonded commitment. Absent all four, it is a posted price with extra steps and
   a leaked floor.

---

## 8. On the adaptive-slope question (brief Q2)

Both sides, then the resolution.

**For publishing the slope up front:** it is the only version that is a
*commitment*. It is verifiable, agent-consumable, and immune to the accusation
that you steepened the descent to serve a buyer. It also cannot be gamed,
because there is no live input to game.

**For adapting to live telemetry:** it is responsive — the §5 diagnostic states
argue for steepening when impressions decay, and a frozen slope wastes the
signal you spent the whole pipeline building.

**Resolution — and this is a decision, not a compromise.** An adaptive slope has
a defect that does not appear anywhere in the brief:

> **The moment the slope becomes a published function of live telemetry, the
> telemetry becomes an attack surface.** A buyer who wants a steeper descent
> withholds detail views, or manufactures the "watchlist without leads" pattern,
> or lets a listing decay before engaging. On the repeated side of a thin market
> — the side that transacts every month and will absolutely notice — this is not
> hypothetical. And the agent layer you are proposing to build hands them the
> automation to do it at zero marginal cost.

Therefore:

- **Within a listing: freeze the slope.** Set it at authoring time from
  pre-listing signal and category priors. Publish the rule. Never move it in
  response to that listing's own live telemetry.
- **Across listings: adapt freely.** Re-fit `f` between cohorts against realized
  hammer outcomes. The learning loop lives at the population level, where no
  single buyer has leverage over the input.

This gets you the responsiveness of an adaptive system, the credibility of a
committed one, and no manipulable feedback loop inside any individual sale.
