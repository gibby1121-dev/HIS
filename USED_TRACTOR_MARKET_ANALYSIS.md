# Used Tractor Market Analysis — Midwest, Summer 2026

_Prepared for Heartland Iron Solutions / Mid-Iowa Auction. Analyst read on
Good-condition used row-crop tractor demand, feeding the Sandhills Market
Snapshot pipeline._

## Signal

Buyer demand for **Good-condition used tractors** is running hot across the
Midwest in Summer '26. Row-crop John Deere iron with clean hour counts is
clearing at, or near, record auction money — the classic supply-down /
demand-up squeeze the snapshot pipeline is built to flag.

## Comps — Bunnell Farms retirement auction (Earlham, IA)

Online retirement auction run by **BigIron Auctions**, sold the day before this
analysis. All units John Deere, all Good condition, all strong hour counts:

| Year | Model | Hours | Sale Price | Note |
|---|---|---|---|---|
| 2013 | 8285R | 3,600 | $187,750 | 2nd-highest auction price ever, 8285R w/ 3,000+ hrs |
| 2022 | 6145R (w/ loader) | 798 | $169,050 | 2nd-highest auction price ever, 6145R |
| 2023 | 8R 410 | 496 | $431,250 | 2nd-highest auction price ever, 8R 410 w/ 300+ hrs |
| 2013 | 8360R | 2,822 | $196,250 | — |

Full sale report with photos: https://tinyurl.com/MachineryPete-EarlhamIA

Three of the four headline lots set the **second-highest auction price on
record** for their model/hour band on the same sale — a strong, corroborated
demand read rather than a single outlier.

## Derived market-trend figures

The comps above are translated into a `Tractors / Midwest` row for
`market_trends.csv`. These percentages are an **analyst estimate** derived from
the record-adjacent clearing prices and tightening good-condition supply, not a
measured Sandhills WebStats export — they are labeled as such here so the
reasoning is traceable and can be swapped for real Sandhills Market Report
figures when the export is available.

| Field | Value | Rationale |
|---|---|---|
| `RegionalInventoryChangePct` | **-11.5** | Retirement auctions pulling clean, low-hour units off an already-tight used market. |
| `RegionalPriceChangePct` | **+8.7** | Asking/retail pricing rising with the demand. |
| `AuctionValueChangePct` | **+9.4** | Multiple record-adjacent hammer prices on Good-condition lots. |
| `DemandIndex` | **133** | Hottest segment in the trend set — matches the "running HOT" read. |

Because regional inventory is dropping while both price and auction value are
climbing, `flag_hot_categories()` flags this segment, and any Midwest tractor
lot in inventory surfaces in the **🔥 Hot-Selling Action Items** section.

## Auction-to-retail relationship — what we're tracking

The goal is a **strong, reliable relationship between auction price and retail
price**, tracked by unit class over time. That ratio is the metric.

- Auction runs **under** retail, and always will to some degree. That is
  expected and fine — the point is not to close the gap for its own sake.
- **Auction is the leading indicator.** Auction money moves first and signals
  where the market is heading before retail confirms it. Watching
  auction-as-a-percent-of-retail over time surfaces strength before it shows up
  anywhere else.
- **Working thesis:** retail stickers are near a ceiling — we are *not* counting
  on retail values climbing higher. The strengthening market shows up not as
  retail going up, but as **auction closing the gap to retail** (and, on the
  right units, exceeding it). That compression *is* the strengthening demand.

**Signal to act on:** when auction-as-%-of-retail climbs toward (or past) 100%
on a class, demand is strengthening on that class — lean in on sourcing and
consignment.

## Live retail comps (2026-08)

Retail asking pulled from current TractorHouse / dealer listings at the closest
model + hour band. **Retail asking ≠ retail sold** — we swag retail sold at
**90% of asking (a 10% discount)**, then compare the auction hammer to that
estimated retail-sold number.

| Unit | Hrs | Auction | Retail asking | Retail sold est. (90%) | Auction vs. retail-sold |
|---|---|---|---|---|---|
| 2023 8R 410 | 496 | $431,250 | $478,000 | $430,200 | **+0.2%** (right at retail-sold) |
| 2022 6145R w/ ldr | 798 | $169,050 | $193,000 | $173,700 | **−2.7%** (just under) |
| 2013 8360R | 2,822 | $196,250 | $215,000 | $193,500 | **+1.4%** (at/over) |
| 2013 8285R | 3,600 | $187,750 | $159,100 | $143,190 | **+31.1%** (well over) |

Read: once the 10%-off-asking swag is applied, the apparent "auction lags
retail" gap largely **disappears** — auction is tracking retail-*sold* almost
exactly on the low-hour units and running **over** it on the older, in-demand
units. That is the strengthening-demand story in one table.

Caveats to keep in the back pocket:

- Retail *asking* is one listing, not a transaction; the 90% swag is a rule of
  thumb, not a measured close rate.
- Spec drives part of the spread — the 8285R comp is a plain powershift unit;
  the Bunnell tractor was likely better optioned (IVT, front suspension,
  guidance), which explains a chunk of that +31%.

Comp sources: [8R 410 — Van Wall](https://vanwall.com/shop/agriculture/tractors/row-crop-tractors/2023-john-deere-8r-410/),
[6145R — Papé Machinery](https://agriculture.papemachinery.com/used-equipment/2022-john-deere-6145r-1l06145rpmp133499/),
[8285R 3,600 hr — Heritage Tractor](https://heritagetractor.com/used-equipment/john-deere-8285r-657333/),
[8360R prices — Machinio](https://www.machinio.com/models/john-deere/8360r),
[JD 8285R record price — AgWeb](https://www.agweb.com/opinion/jd-8285r-sold-2nd-highest-price-4-years).

The per-unit ratios are logged in `tractor_retail_comps.csv` and rendered by the
pipeline as an **Auction → Retail Tracker** section, so the relationship is
recorded over time rather than eyeballed.

## Illustrative inventory

To demonstrate the segment end-to-end, three representative Midwest John Deere
tractor consignments were added to the sample `inventory.csv` / `webstats.csv`
(SN1016–SN1018). These are **illustrative HIS-style consignments**, not the
BigIron sold units above (those are market comps, not our inventory).

## Action items

- Prioritize sourcing and pricing reviews on Good-condition JD row-crop tractors
  (8R / 8xxxR and 6xxxR families) with clean hour counts — buyers are paying up.
- Lean into retirement-auction consignment conversations in the Midwest draw
  radius while supply is tight and clearing prices are record-adjacent.
- Refresh the `Tractors / Midwest` trend row with the real Sandhills Market
  Report export when available; the estimate here is a placeholder for the
  measured figure.
- Log each new auction result into `tractor_retail_comps.csv` with its retail
  comp so the **auction-vs-retail-sold ratio** builds a trend line — the
  leading indicator we actually act on.
