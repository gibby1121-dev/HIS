# Concept Brief: A Commitment-Based Marketplace for Unique, One-Time-Sale Assets

*Source of record. This is the brief as submitted, unedited. The evaluation
documents in this directory respond to it.*

---

## 1. The market this is built for

Single unique items, sold once, by a seller who will likely never sell another one.

- Used heavy equipment (Class 8 trucks, ag tractors, combines, construction iron) is the proving ground.
- The structure — not the category — is what matters. It applies equally to a rare yo-yo or a Bugatti.

Defining traits of this market:

- **n = 1.** No product line, no SKU, no comparable sales in any meaningful volume.
- **No brand development.** The seller has no reputation and will never build one.
- **No repeat buyers.** One-time buyer meets one-time seller. Neither will transact again.
- **Asking price carries zero information.** With no comps and no sales history, the ask is an anchor derived from a loan payoff, a neighbor's claim, or hope. It is a wish with a decimal point, not a price.

## 2. The problem

An auction discovers price fast because the clock runs out and the gavel *has* to fall. The forcing function is the deadline, not the audience.

A listing has no forcing function. So seller inertia silently substitutes for price discovery. Units sit at 30, 90, 180+ days while the seller concludes "the market is soft" rather than "I am 11% high."

Critically, **the incumbent platforms cannot fix this.** Listing sites monetize *time on site* — renewals, featured ads, bump-ups. A platform that told a seller "drop 8% and it clears Thursday" would cannibalize its own revenue. The gap is structural and permanent.

## 3. The core insight: want-to-sell vs. need-to-sell

Sellers are two populations that current platforms treat as one:

| | Want-to-sell | Need-to-sell / going-to-sell |
|---|---|---|
| Motivation | "I'd move it at my number" | Retirement, estate, divorce, note due, upgrade landed |
| Clock | None | Real, often unstated |
| Price floor | Undeclared, effectively infinite | Exists, private, reachable |
| Behavior at 90 days | Renews, shrugs | Would have taken less in week 3 |

Every seller has a want price. Only some have a need price — but the ones who do can't signal it, and buyers can't detect it.

**Consequence:** buyers waste most of their search time on listings from sellers who will never actually move. A venue where *every listing is a committed seller* is worth far more to a buyer than one with 10x the inventory and no way to tell ghosts from real sellers. That is the liquidity flywheel.

## 4. The mechanism

The seller is asked one question: **are you posting, or are you selling?**

**Posting tier** — free, permanent, bulletin board. No clock, no obligations. Explicitly labeled as such so buyers can filter it out.

**Selling tier** — the seller commits to two things:
1. A **private reserve** (their real floor — never published, never revealed).
2. A **clock** — a published, declining ask on a fixed schedule.

The seller never has to disclose their need price. They only have to acknowledge one exists. The descending ask walks them from want toward need publicly and on a schedule; the transaction closes when the market meets them.

**Why a descending clock works here specifically:** in a product-line market, waiting is free — another unit appears next week. When n = 1, waiting risks losing the item entirely to a buyer with a lower threshold. Uniqueness is what makes the descending mechanic bite. The same trait that makes this market impossible to comp is what makes the mechanism function.

## 5. The signal layer — how the clock's slope is set

Even with no comps, the *funnel* is comparable across wildly dissimilar items. You aren't comping the machine; you're comping the market's reaction to the machine. Every serious buyer who scrolls past is casting a vote.

Available per-listing telemetry: impressions, detail views, watchlists/saves, email leads, days aging. Available valuation data: auction, wholesale, market, asking, retail estimates.

Diagnostic states:

- **High impressions, low detail-view rate** → top-of-funnel failure. Photos, title, or grid-displayed price. Not a price problem. Fixable at zero cost.
- **Strong detail views + rising watchlists + zero leads** → the money signal. They looked, they liked it, they *saved it*, and they didn't call. This is a buyer waiting for the seller to blink. Price is above clearing but within reach.
- **Impressions decaying week-over-week** → algorithmic burial. Traffic already spent; a later price cut cannot resurrect it. Argues for a steeper early slope.
- **Days aging beyond category median with ask above market** → quantify carrying cost (interest, insurance, yard space, depreciation, opportunity cost) and show the seller the dollar cost of being stubborn.

The score converts to one number and one verb: **hold, adjust, or drop the hammer.** Sellers do not act on dashboards. They act on a single number that embarrasses them.

## 6. The trust layer

In a no-brand, no-repeat market, **something must substitute for reputation**, because neither party has one and neither will build one. This is the entire historical reason auction houses exist: condition verification, title/lien clearance, escrow and fund settlement, dispute handling between two strangers who will never meet again.

This is a hard requirement, not a feature. A pure-software entrant has to acquire or build it and will spend years and at least one lawsuit doing so.

## 7. The agent layer

The end state is person → agent → agent → person. But agents are poor negotiators without ground truth and excellent at *watching and triggering*.

A published, machine-readable, declining price path converts the problem from **negotiation** (which agents do badly) to **matching** (which agents already do well). A buyer's agent holding a want — "T880, under 500k miles, under $85k" — doesn't haggle. It monitors a price path and fires at a threshold.

Implication: don't build an agent aggregation layer or compete on LLM infrastructure. Expose the price path, the signal score, and inventory as a callable service (MCP server + open feed spec) so any agent on any platform can consume it. Be the oracle agents call, not the marketplace they must join. Oracles need only be *right*; marketplaces need two-sided liquidity to survive.

## 8. What already exists (assets, not hypotheticals)

- An operating auction company with an established regional brand and existing trust/settlement infrastructure.
- Daily ingestion of per-listing performance telemetry joined to per-unit valuation data on serial number — both halves of the signal in one row. Valuation providers can't see behavior; platforms can see behavior but won't publish it.
- Existing consignor and buyer relationships for design-partner testing.
- Real hammer prices from completed sales to back-test predictions against ground truth.

## 9. Constraints — do not design these away

1. **n = 1.** Any answer that relies on comparable-sales volume, product catalogs, or SKUs is out of scope.
2. **No repeat participants.** Reputation systems, seller ratings, and loyalty mechanics have little to work with.
3. **High-value, low-frequency, physically located goods.** Inspection, transport, title, and lien realities dominate.
4. **The seller is often unsophisticated and emotionally attached.** UX cannot require them to understand auction theory.
5. **Incumbent distribution is hostile.** Existing platforms profit from listings that don't sell.
6. **Do not rebuild eBay, Craigslist, or a generic marketplace.** If the proposed design works equally well for a product line, it has missed the point.

---

## Questions for evaluation

### Mechanism design
1. What are the failure modes of a published declining ask in a thin market? Specifically: buyer sniping/waiting behavior, collusion when the buyer pool is small (5–20 real buyers), and sellers pulling out mid-clock.
2. Should the slope be published up front, or adaptive to live telemetry? Argue both. What does each do to buyer waiting behavior?
3. How should a private reserve interact with a public descending price without leaking the reserve through the slope itself?
4. What mechanism converts a want-to-sell seller into a need-to-sell seller without coercion?

### Signal validity
5. Does the funnel-shape-transfers assumption hold across categories and price points? How would you falsify it with historical data?
6. What confounds impressions/views/watchlists/leads besides price? How do you separate a pricing failure from a photography failure statistically, not just heuristically?
7. What is the minimum listing volume needed before the score is defensible?

### Architecture
8. Design the data model and service boundaries for: signal ingestion → score → clock schedule → public price path → agent-callable feed → settlement.
9. What does the agent-facing interface look like concretely? Schema, polling vs. push, authentication, threshold-firing semantics.
10. Where does this break at 100 listings vs. 100,000?

### Business
11. Who pays — buyer side or seller side? Argue against the obvious answer.
12. What is the strongest argument this fails? Not a risk list — the single most likely cause of death.
13. Who builds this instead, and what do they have that the incumbent auction operator doesn't?

---

## Role prompts

**A. Red team.** *"You are a skeptical market-design economist. This concept will fail. Identify the single most likely cause of death and the three strongest structural objections. Do not list generic risks. Do not be encouraging."*

**B. Mechanism designer.** *"You are an auction theorist. Evaluate the descending-clock-with-private-reserve mechanism for a thin market with unique goods and non-repeat participants. Analyze buyer incentives to wait, collusion risk, and reserve leakage. Propose two alternative mechanisms and argue why each might beat this one."*

**C. Systems architect.** *"Design the technical architecture. Data model, service boundaries, the agent-facing API contract, and the scaling break points. Assume the signal data described in section 5 is available daily."*

**D. The customer.** *"You are a 58-year-old owner-operator selling one semi truck after 30 years. You have never used an online auction. Walk through this experience and tell me exactly where you'd quit, get confused, or refuse."*

**E. The competitor.** *"You run a major equipment listing platform whose revenue depends on listing renewals. This concept threatens you. How do you kill it, copy it, or co-opt it?"*

Then compare answers. Where all five converge is probably true. Where they diverge sharply is where the real design decision lives.
