# Consignee buyer-contact sheet

Turns a Sandhills **AT/PreAT Auction Summary Report** export into a
per-consignee contact sheet: for each lot that sold, the seller gets their net
proceeds figure — buyer's premium stripped off — alongside the winning
bidder's name, phone, email, and address, so they know who is about to call
them about pickup.

## Run it

```bash
pip install -r requirements.txt
python3 consignee_buyer_contacts.py AT_PreAT_Auction_Summary_Report.xlsx
```

Writes `consignee_buyer_contacts.xlsx` (one row per lot, grouped by
consignee). Override with `-o/--output`.

## How the premium is stripped

The export carries both sides of the transaction:

| Column | Meaning |
|---|---|
| `Final Auction Price` | what the buyer paid (hammer + premium) |
| `USD Hammer Sold Price` | what the lot hammered at |
| `Buyer's Premium Price` | the premium itself |

The consignee-facing number is the **hammer price**, written to
`Net to Consignee (Hammer)`. It is taken from `USD Hammer Sold Price` and
cross-checked against `Final Auction Price − Buyer's Premium Price`.

- The two disagree by more than a cent → the lot is **flagged on stderr**, not
  silently shipped to a seller.
- Hammer price missing but the other two present → falls back to the derived
  value rather than sending a blank.
- No usable price at all → flagged.

Premium columns are dropped from the output entirely. Pass `--reconcile` to
keep `Final Auction Price`, `Buyer's Premium Price`, and
`Buyer's Premium Percent` for an internal check before the sheet goes out.

## Output columns

`Seller` · `Stock Number` · `Year` · `Manufacture` · `Model` · `Sold Date` ·
`Net to Consignee (Hammer)` · `Winning Bidder` · `Phone` · `Email` · `Address`

## Required input columns

The `Details` sheet (header on row 5, three title rows above it) must provide:

`Seller`, `Year`, `Manufacture`, `Model`, `Stock Number`, `Sold Date`,
`Final Auction Price`, `USD Hammer Sold Price`, `Buyer's Premium Price`,
`Winning Bidder`, `Address`, `Phone`, `Email`

A missing column is a hard failure (exit 2). An export whose `Details` sheet
has headers but no rows exits 1 with a message to re-pull the date range.

## Privacy

The generated sheet contains buyer contact details and is **git-ignored** —
never commit it. Regenerate it from the export instead.

## Tests

```bash
pytest tests/test_consignee_buyer_contacts.py
```
