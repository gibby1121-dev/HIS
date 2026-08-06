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
