# Trade-In Check

HIS / Mid-Iowa Auction's first product for owner-sellers of large row-crop
iron. It takes the dealer's bundled trade-in quote and works out four things:
- what the dealer is **really** paying for the trade;
- what the unit **actually** brings at auction, measured against MIA's own results;
- whether the operator should trade or consign;
- what to say to the dealer.

The research behind every rule and number is in [`docs/RESEARCH.md`](docs/RESEARCH.md).

## What it does that an operator can't do alone

1. **Reads the dealer's quote itself.** An operator photographs the worksheet or forwards
   the PDF. Claude extracts the fields, and **every number has to come with the
   exact text it was read from**. A number that doesn't appear in that text is
   dropped. If the quote's arithmetic doesn't add up, that becomes a question for
   the operator rather than a silent fix. (`tradein/intake.py`)
2. **Separates out what the dealer is withholding.** The real trade value is the
   allowance minus the discount a no-trade buyer would have gotten. When the
   operator doesn't have the no-trade cash price, nothing is assumed. Instead the
   tool solves for the **break-even no-trade price** and gives the operator one
   question to ask the dealer.
3. **Puts a floor under the over-allowance.** A dealer can't pay more for a trade
   than its expected resale value less margin, reconditioning and floorplan. Any
   allowance above that ceiling has to be coming back out of the new-unit price.
4. **Values the 0% financing as well.** At the operator's own borrowing rate, the
   subsidy is worth a dollar amount. Any cash-in-lieu offer below that amount is
   worse. Lenders such as AgDirect let an operator take the cash *and* finance it.
5. **Uses hammer prices only.** Comparable sales must state their price basis.
   Buyer's premiums are stripped out, including capped ones. Asking prices are
   never used to set a value; they're shown only to explain why "it's listed for
   $X online" is not what the unit brings. Sandhills asking prices ran 31–40% above
   auction in 2026.
6. **Calibrates against MIA's own sale results.** The Sandhills VIP+ auction value
   is scaled by how MIA hammer prices have actually landed against Sandhills
   estimates in that category. The calibration validates itself: it's used only
   for categories where it beats raw Sandhills on lots held out of the fit.
7. **Measures its own value ranges.** The comps range is sized from leave-one-out
   errors, so a statement like "80% of held-out sales fell within ±X%" is measured
   rather than assumed.
8. **Gives the CPA facts and questions, never advice.** Since 2018, a trade is a
   sale plus a purchase. The report shows the amount realized and the new-unit
   basis under each route, and flags the issues to raise with the CPA:
   over-allowance and self-employment tax, bonus depreciation and §179,
   December vs. January timing, and §453(i). For South Dakota operators it also
   counts the excise saved by trading.

## Run it

```bash
pip install -r requirements.txt
python3 trade_in_check.py sample                  # synthetic demo
python3 trade_in_check.py FOLDER                  # FOLDER/trade_deal.json (+ comps.csv, mia_results/)
python3 trade_in_check.py FOLDER --quote worksheet.jpg --notes "2021 9RX 640, 2,050 hrs, 36in tracks"
python3 -m tradein.backtest FOLDER                # measure accuracy on your data first
```

It writes two files:
- `trade_in_report.md` for the operator.
- `mia_desk_sheet.md` for internal use: the consignment pitch, a reserve ceiling, value anchors, and an unverified-items checklist.

Exit codes: 0 means OK; 1 means bad input; 2 means the quote needs answers first.

To read a quote, `--quote` needs Anthropic API credentials (`ANTHROPIC_API_KEY`
or an `ant auth login` profile). It uses `claude-opus-5-5` with structured
output. Server-side refusal fallback (`fallbacks: "default"`) is enabled.

## Inputs (all in one folder)

| File | Required | What it is |
|---|---|---|
| `trade_deal.json` | yes | The quote and trade unit. See `sample/trade_deal.json`. Written for you by `--quote`. |
| `comps.csv` | one of these two | Realized sales. Required columns: `Make, Model, Year, Hours, Price, PriceBasis, SaleDate`. `PriceBasis` is one of `hammer`, `with_bp` (also give `BuyerPremiumPct`, and `BuyerPremiumCap` if the premium is capped) or `asking`. Optional columns: `Category, Source, Region, Config`. |
| `trade_unit.sandhills_vip` | one of these two | `{"auction": …, "market": …}` from the Sandhills dealer account (VIP+). |
| `mia_results/*Auction Summary*.xlsx` | optional | MIA's post-sale exports. These turn on calibration. |

`config/mia_terms.json` holds MIA's seller terms. **The commission bracket
breakpoints, settlement days, days to next sale and prep cost are placeholders.**
The published commission range is 3–6%. Every report lists the unverified
items until you replace them. `config/market_facts.json` holds the dated,
sourced market context.

## Before an operator sees a number

1. Replace `config/mia_terms.json` placeholders with MIA's real schedule and sale calendar.
2. Drop real Auction Summary Reports into `mia_results/` and real hammer comps into `comps.csv`.
3. Run `python3 -m tradein.backtest FOLDER`. If the comps model's median error or range coverage is poor for a category, don't quote that category yet.
4. **Everything in `sample/` is synthetic.**

## Layout

```
trade_in_check.py      CLI
tradein/categories.py  make/model -> row-crop category
tradein/comps.py       comps loading, price-basis normalization, buyer's-premium stripping
tradein/mia.py         Auction Summary / ExportFleet loaders, self-validating calibration
tradein/valuation.py   comps + calibrated-Sandhills anchors, fitted adjustments, measured ranges
tradein/deal.py        quote decomposition, break-even, financing value
tradein/routes.py      consign net, dealer ceiling, SD excise
tradein/tax.py         CPA facts and questions
tradein/analyze.py     orchestration and verdict
tradein/report.py      operator report and MIA desk sheet
tradein/intake.py      Claude quote reader with evidence verification
tradein/backtest.py    leave-one-out accuracy on your data
```
