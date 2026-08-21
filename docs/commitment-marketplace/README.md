# Commitment Marketplace — concept evaluation

Adversarial evaluation of the concept brief for a commitment-based marketplace
for unique, one-time-sale assets, with used heavy equipment as the proving
ground.

## Scope note

This is equipment-market design analysis for the Heartland Iron Solutions /
Mid-Iowa auction business, and it connects directly to the signal layer this
repository already builds (`market_snapshot.py`). It is documentation only —
**no pipeline code was changed.** The concrete implications for
`market_snapshot.py` are collected in
[`03-architecture.md`](03-architecture.md) §0 and §6, as recommendations for a
separate change.

## Contents

| Document | Role | What it contains |
|---|---|---|
| [`00-concept-brief.md`](00-concept-brief.md) | — | The brief as submitted, unedited. Source of record. |
| [`01-red-team.md`](01-red-team.md) | Skeptical market-design economist | Single most likely cause of death; three structural objections. |
| [`02-mechanism-design.md`](02-mechanism-design.md) | Auction theorist | Buyer waiting, collusion, reserve leakage, withdrawal; two alternative mechanisms; the slope decision. |
| [`03-architecture.md`](03-architecture.md) | Systems architect | Data model, service boundaries, agent API contract, signal validity and falsification, scaling break points. |
| [`04-customer-walkthrough.md`](04-customer-walkthrough.md) | 58-year-old owner-operator | Where he quits, gets confused, or refuses — in his own voice. |
| [`05-competitor.md`](05-competitor.md) | Incumbent listing platform | Kill, copy, co-opt — with costs. |
| [`06-synthesis.md`](06-synthesis.md) | — | Convergence, divergence, the five most consequential changes, the settling experiment, and a question index. |

**Start with [`06-synthesis.md`](06-synthesis.md)** if you read only one.

## Method

The brief specifies five adversarial roles and asks that the answers be compared
rather than averaged. Each role was answered on its own terms, in its own voice,
without reconciling it against the others; the synthesis was written afterward
from the five completed responses. Where a role contradicts the brief's stated
premises, the contradiction is preserved rather than smoothed — the premise
conflicts are tabulated at the end of the synthesis.

## The findings in one paragraph

Five roles converge on the same five points: supply is the binding constraint,
not buyers or technology; the published descending clock as specified hands
buyers a free option and needs stochastic termination, an unpublished endpoint,
a frozen slope, and a bond before it has any bite; the trust layer is the real
business and it scales as headcount, making it both the moat and the ceiling;
the auctioneer converts the seller, not the app; and the signal layer is rented
from the party the brief names as the adversary, which is the single most
under-defended point in the concept. The sharpest divergence — and the real
decision — is whether this is a **venue** or an **instrument**. The cheapest
version of the entire mechanism is a declining reserve written into a
consignment contract on the ring that already exists, which tests the whole
thesis this selling season for close to nothing.
