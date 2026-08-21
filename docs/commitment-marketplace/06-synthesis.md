# Synthesis — convergence, divergence, and the decisions that remain

*Compare the five roles. Where they converge is probably true. Where they
diverge sharply is where the real design decision lives.*

---

## 1. Convergence — five independent roles, same conclusions

These were reached from different premises by roles with opposing incentives.
Treat them as findings, not opinions.

**C1. Supply is the binding constraint. Not buyers, not technology.**
The red team gets there through adverse selection (committed sellers with
realistic floors already consign to auctions; the clock inherits the residual).
The customer gets there through the tier question ("I pick posting, every
time"). The competitor gets there through pattern-matching ("it always ends
with 60 listings"). The mechanism designer gets there through commitment
credibility (an unbonded tier badge means nothing). **Four roles, four routes,
one answer.** Nothing else in the concept matters until the selling tier fills
with units that would not have gone to the ring anyway.

**C2. The published descending clock, as specified, transfers surplus to
buyers.** The formal result is in mechanism design §1: with negligible rival
hazard and a known endpoint, the mechanism is strategically equivalent to
posting the floor, late. The customer confirms it from the other end — he'd
rather hold a year than post a public countdown. The clock has bite only with
stochastic termination, an unpublished endpoint, a frozen slope, and a bond.
All four, or it is a posted price with extra steps and a leaked floor.

**C3. The trust layer is the real business, and it does not scale as software.**
Every role agrees it is mandatory. The architect prices it: settlement headcount
scales linearly and is the wall at 100k listings. The competitor confirms it
from the outside — *"never build the trust layer, partner for it, it's the worst
business in this chain."* So it is both the moat and the ceiling, and any plan
that treats it as a one-time build is wrong about the cost structure.

**C4. The auctioneer converts the seller, not the app.** The customer states it
outright: same mechanism, same numbers, delivered by a person he knows, and he
signs today. The competitor's playbook never contemplates attacking that
relationship because it can't. This reframes the product: **an internal tool
that tells a person what to say and when to call**, not a self-serve funnel.

**C5. The signal layer is rented from the declared adversary — and the brief
never mentions it.** Red team objection 3 and competitor option 2 land on this
independently, and it is the most under-defended point in the concept. The
telemetry and valuation feeds arrive through a dealer account under the
incumbent's ToS. The competitor's kill costs one email and needs no
justification. There is no answer to this in the brief.

**C6. The oracle is the durable asset; the marketplace is the fragile one.**
Even the competitor says so, and says it against interest: *"I can copy a
mechanic. I can't manufacture ground truth."* Real hammer prices from completed
sales, joined to behavior, are the one asset that cannot be bought, rented, or
terminated.

---

## 2. Divergence — where the real decisions live

### D1. Is this a venue, or an instrument? **← the fork**

The brief assumes a venue: listings, tiers, a feed, settlement. The mechanism
designer's strongest alternative (rolling declining reserve, §6) is not a venue
at all — it is a **clause in a consignment contract**. Same commitment, same
descending floor, same data, but it runs through the ring that already exists
and requires essentially no new trust infrastructure.

The architect's build order points the same way: steps 1–4 (persist snapshots,
widen the funnel, back-test, publish calibration) have standalone value to the
existing auction business whether or not a marketplace is ever built.

**Recommendation: instrument first. The venue is a hypothesis the instrument can
test for a fraction of the cost.** Nothing about shipping the declining-reserve
consignment forecloses the venue later; the reverse is not true.

### D2. Publish the slope, or adapt it? *(Q2)*

The brief treats the slope as a live output of the signal layer. The mechanism
designer identifies a defect that resolves it: **once the slope is a published
function of live telemetry, the telemetry becomes an attack surface**, and the
agent layer the brief proposes hands the repeated-participant buy side the
automation to exploit it (suppress detail views, manufacture the
watchlist-without-leads pattern, steer the descent).

**Decision: freeze the slope within a listing; adapt `f` across cohorts.** Set it
at authoring time from pre-listing signal, publish the rule, never move it in
response to that listing's own telemetry. Re-fit between cohorts against realized
hammer outcomes, where no single buyer has leverage. This is enforced in the
topology, not in policy: the scoring service holds no read credential for the
reserve, so `f` cannot leak what it cannot see.

### D3. Who pays? *(Q11)*

**The obvious answer is the seller.** They receive the liquidity, they own the
asset, and consignment fees are how this industry already works.

**Argue against it — three reasons it is wrong here:**

1. **It reproduces the incumbent's incentive.** A seller-funded product must
   please sellers, and the entire value of this one is telling sellers things
   they do not want to hear. You would rebuild the conflict you set out to
   exploit.
2. **The customer walkthrough prices the willingness to pay at approximately
   zero.** He picks the free tier on reflex and refuses account creation. An
   emotionally attached, unsophisticated, one-time seller will not pay for
   software; he'll pay a commission on money he actually received, which is a
   success fee, not a product.
3. **The premise that buyers are non-repeat is false** (mechanism design §0).
   The buy side is the *repeated* side: dealers, flippers and fleet buyers with
   budgets, purchasing processes, and a standing need for deal flow.

**Recommendation:**
- **Buy side pays for the mechanism.** Funded standing orders, holds/options,
  and write access to the agent feed. This is revenue from the side that has
  budget — and per mechanism design §7 it is simultaneously the fix for the
  waiting problem, because an unobservable standing order is the rival hazard
  the clock lacks.
- **Sell side pays only on success**, through the existing auction rate card.
  No subscription, no listing fee, nothing that requires him to value software.
- **The oracle stays free and public.** Its job is authority, not revenue —
  and per the competitor, authority is the contested ground.

The elegance of charging buyers is that the payment *is* the mechanism: a
binding, funded, undisclosed threshold is both the product and the missing
forcing function.

### D4. Converting want-to-sell into need-to-sell *(Q4)*

The brief asks how to convert. **Mostly, don't — find them instead.** Need is a
real-world state with a public or semi-public trail: estate and probate filings,
retirement dispersals, UCC lien filings and note maturities, divorce, delivered
equipment upgrades, lease returns, aged dealer trade-ins. Prospecting against
those signals is cheaper and more honest than persuasion. (This repo's `fsbo`
skill is already the prospecting half of exactly this motion.)

For genuine want-to-sell sellers, two non-coercive devices, in order of power:

1. **Make the counterfactual concrete: a guaranteed minimum.** "We'll write you
   a check for $X today, or you can run it." Nothing converts a wish into a
   decision like a real alternative with a number on it, and an operator with
   hammer-price history is uniquely positioned to underwrite it. It carries
   principal risk and it is the strongest device available — which is the
   trade-off to make deliberately, not to stumble into.
2. **Price the waiting, in dollars, out loud.** The customer named the exact
   framing that lands: *"that truck is costing you $412 a month, and you have
   already spent $1,100 holding out for $4,000."* Not a score. Not a dashboard.
   A monthly dollar figure, said on the phone.

What does not work: teaching him the mechanism, showing him a score, or asking
him to type his floor into a form.

### D5. Who builds this instead? *(Q13)*

Three classes, ordered by how much of the problem they already own:

- **The auction consolidators** (Ritchie Bros / IronPlanet class). They have
  national buyer density, settlement and title at scale, licensing across
  states, and hammer data at 100x volume. What they lack is the willingness to
  disrupt a fee structure that works — a classic incumbent's dilemma, and a real
  window, but a closing one.
- **The lenders and captive finance arms — the sleeper, and the most
  interesting answer.** *The need-to-sell signal already lives in a loan
  servicing system.* They know the payoff (the actual private floor), the
  maturity date (a real forcing function), the collateral, and the delinquency
  trajectory — before the seller has admitted anything to himself. They can
  originate the need-to-sell population at zero acquisition cost, and they have
  cost of capital to take principal positions. They do not have the yard, the
  buyers, or the desire to be in the equipment business, which is precisely why
  a partnership is more likely than competition.
- **Insurance total-loss and fleet lease-return operators.** Deadlines by
  construction, volume by construction. They already run forced-disposition
  processes; the descending mechanic is a natural extension.

What all of them have that the regional auction operator does not: **national
buyer density, cost of capital, and a fifty-state legal footprint.** What none
of them have: the willingness to publish a number that indicts their own fee
structure.

---

## 3. The five most consequential changes to the concept

1. **Start persisting daily per-listing snapshots now.** The signal layer cannot
   be back-filled, and the funnel columns are already sitting unused in
   `webstats.csv`. Every week of delay is training data that will never exist.
2. **Ship the mechanism as a consignment clause, not a marketplace** — a
   declining reserve on the existing ring. Tests the entire thesis this season,
   at close to zero cost, with the trust layer already in place.
3. **Move the money to the buy side.** Funded, undisclosed standing orders:
   revenue, forcing function, and agent primitive in one object.
4. **Never publish demand, and never publish the endpoint.** No watcher counts,
   no offer counts, no terminal price or date. Buyer uncertainty is the seller's
   only remaining asset in a thin market; publishing demand hands the repeated
   side a collusion-monitoring tool.
5. **Fix the data dependency before it is load-bearing.** Negotiate redistribution
   rights explicitly, or build the oracle on outcome data you own outright
   (your own hammer prices), which is also the only asset the competitor
   concedes he cannot copy.

---

## 4. The test that settles it

Every role, asked independently what would change their mind, converged on the
same experiment — and it is one that almost no one else in this market could
run:

> Take matched pairs of comparable units — same category, same condition band,
> same season — and assign them at random between the ring and the clock.
> Compare realized price net of fees and net of carrying cost over the
> additional days on market.

You control both venues, you own the outcome data, and you can randomize. That
last capability is the genuinely scarce asset here: **the incumbents can only
observe; you can intervene.** The same design settles the photography-versus-
pricing confound (architect §4), the score's validity, and the central claim of
the brief, on a cohort of a few dozen units in one selling season.

Run it before building the settlement plumbing, not after.

---

## Question index

| # | Question | Where answered |
|---|---|---|
| 1 | Failure modes of a published declining ask | [02](02-mechanism-design.md) §1, §2, §4; [01](01-red-team.md) Obj. 1 |
| 2 | Published vs. adaptive slope | [02](02-mechanism-design.md) §8; decision in §D2 above |
| 3 | Reserve interacting with public descent without leaking | [02](02-mechanism-design.md) §3; enforcement in [03](03-architecture.md) §2 |
| 4 | Converting want-to-sell into need-to-sell | §D4 above |
| 5 | Does funnel shape transfer? How to falsify it | [03](03-architecture.md) §4 |
| 6 | Confounds; separating pricing from photography failure | [03](03-architecture.md) §4 |
| 7 | Minimum volume before the score is defensible | [03](03-architecture.md) §4 |
| 8 | Data model and service boundaries | [03](03-architecture.md) §1–§2 |
| 9 | Agent-facing interface | [03](03-architecture.md) §3 |
| 10 | Break points at 100 vs. 100,000 listings | [03](03-architecture.md) §5 |
| 11 | Who pays — argue against the obvious answer | §D3 above |
| 12 | Single most likely cause of death | [01](01-red-team.md) |
| 13 | Who builds this instead | §D5 above |

## Premises in the brief that the evaluation contradicts

| Brief claim | Finding |
|---|---|
| §1, §9.2 — "no repeat buyers" | False on the buy side. Buyers are the *repeated* side of a one-shot-seller market. This drives the collusion analysis ([02](02-mechanism-design.md) §0, §2) and the who-pays answer (§D3). |
| §2 — "the forcing function is the deadline, not the audience" | The deadline ends an auction; visible rival bidders raise the price. Removing co-presence removes the pressure ([01](01-red-team.md) Obj. 1). |
| §2 — incumbents "structurally and permanently" cannot respond | Their revenue is concentrated in dealer subscriptions, they already sell pricing guidance, and the properties sit alongside auction operations ([05](05-competitor.md)). |
| §4 — "uniqueness is what makes the descending mechanic bite" | Uniqueness makes the *item* scarce; it does not make *demand* visible, and visible rival demand is what the mechanic requires ([02](02-mechanism-design.md) §1). |
| §8 — telemetry joined to valuation is a proprietary asset | It is a subscription under the adversary's terms of service ([01](01-red-team.md) Obj. 3, [05](05-competitor.md) Option 2). |
