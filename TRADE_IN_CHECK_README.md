# Trade-In Check

The first HIS / MIA product for owner-sellers of large row-crop iron (4WD and
high-HP row-crop tractors, combines, planters, self-propelled sprayers, grain
carts). It targets the **trade-in squeeze**: the dealer folds the trade value
into the new-unit deal, so the operator can't see what the trade is worth on the
open market.

## What it does

1. **Unbundles the dealer deal.** A large trade allowance can be paid for by a
   smaller discount on the new unit. The real trade value is:

   ```
   implied trade value = trade allowance − (quoted price with trade − cash price without trade)
   ```

   If the operator has the dealer's cash (no-trade) price, the tool uses it.
   If not, it estimates the cash price from an assumed dealer discount, flags
   the number as estimated, and tells the operator to get the cash price in
   writing.
2. **Values the trade on the open market** from comparable sales in
   `comps.csv`. Each comp is adjusted to the trade's model year and hours, then
   weighted by similarity (make/model, year, hours) and recency. The result is
   a weighted median with a P25–P75 range and a High / Medium / Low confidence
   grade. When there are few close comps, the range is widened.
3. **Nets out the cost of selling it yourself**: commission, transport, prep,
   and the carrying cost while the unit sells.
4. **Compares the two routes.** The **trade-in spread** is net open-market
   proceeds minus the implied trade value: roughly what the operator pays for
   the convenience of trading. The report gives a verdict
   (🔴 squeezed / 🟡 close / 🟢 strong), two break-even counter-offers (a higher
   allowance, or a lower price at the same allowance), and the questions to ask
   the dealer.

The output, `trade_in_report.md`, is a seller-facing summary. You can read it as
it is or load it into NotebookLM or Claude as a source. It is a **decision aid,
not an appraisal and not tax advice**. Tax effects such as depreciation
recapture are not modelled, and the report tells the operator to take it to
their CPA.

## Run it

```bash
pip install -r requirements.txt
python3 trade_in_check.py                  # uses trade_deal.json + comps.csv here
python3 trade_in_check.py /path/to/folder  # inputs in another folder
```

The exit code is 0 on success. It is 1 when an input is missing or malformed,
and the error names the problem.

## Inputs

### `trade_deal.json` — one dealer quote

| Field | Required | Notes |
|---|---|---|
| `trade_unit.category` | yes | Must match `Category` in comps (e.g. `4WD Tractor`). |
| `trade_unit.make`, `.model`, `.year`, `.hours` | yes | |
| `trade_unit.description` | no | Configuration notes; printed in the report. |
| `dealer_quote.quoted_price_with_trade` | yes | New-unit price on the trade deal. |
| `dealer_quote.trade_allowance` | yes | |
| `dealer_quote.cash_price_no_trade` | no | Use it whenever you have it. `null` means estimate it. |
| `dealer_quote.new_unit` | no | Label for the new unit. |
| `as_of` | no | `YYYY-MM-DD`; comps dated after this are ignored. Defaults to today. |
| `operator` | no | Name printed on the report. |
| `assumptions.*` | no | Overrides the defaults below. Unknown keys are rejected. |

Default assumptions are listed in `DEFAULT_ASSUMPTIONS` in
`trade_in_check.py`, and every value used is printed in the report:
dealer cash discount 8%, commission 5%, transport $2,500, prep $1,500, 45 days
to sell at an 8% cost of money, comp adjustments of 7% per model year and 4% per
1,000 hours, a recency half-life of 180 days, and a maximum comp age of 730
days. **These are placeholders.** Replace them with MIA's actual commission
schedule and observed dealer discounts before you show results to customers.

### `comps.csv` — comparable sales

Required columns: `Category, Make, Model, Year, Hours, SalePrice, SaleDate`.
Optional columns: `SaleType, Region, Notes`.

Use **realized** prices (auction results, confirmed retail sales), not asking
prices. Rows with an unparseable year, hours, price, or date are dropped.

> **The committed `comps.csv` and `trade_deal.json` are synthetic sample data.**
> They exist for demos and tests and are not market data. Replace them with
> real auction results before you quote numbers to an operator.

## Next steps (not built yet)

- **Intake:** extract the deal fields from a photographed or PDF dealer quote
  with an LLM, so the operator never fills in JSON.
- **Comps feed:** populate `comps.csv` from MIA sale results plus auction-result
  exports, matched on configuration (tracks vs. wheels, PTO, separator hours,
  row count / spacing).
- **Market timing overlay:** add category trend signals, for example tight
  used high-HP tractor inventory, to the report as negotiation context.
