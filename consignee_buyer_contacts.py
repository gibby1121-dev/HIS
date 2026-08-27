#!/usr/bin/env python3
"""
Consignee buyer-contact sheet
=============================

Turns a Sandhills "AT/PreAT Auction Summary Report" export into a per-consignee
contact sheet: for every lot that sold, the seller (consignee) gets the net
proceeds figure with the buyer's premium stripped off, plus the winning
bidder's contact details so they know who will be reaching out.

Buyer's premium handling
------------------------
The export carries both sides of the transaction:

    Final Auction Price   = what the buyer paid  (hammer + premium)
    USD Hammer Sold Price = what the lot hammered at
    Buyer's Premium Price = the premium itself

The consignee-facing number is the hammer price. This script takes it from
``USD Hammer Sold Price`` and cross-checks it against
``Final Auction Price - Buyer's Premium Price``; any lot where those two
disagree by more than a cent is reported so it can be reconciled by hand
rather than silently shipped to a seller.

By default the premium columns are dropped from the output entirely (that is
the "strip off" the sheet is for). Pass ``--reconcile`` to keep them for an
internal check before the sheet goes out.

Usage
-----
    python3 consignee_buyer_contacts.py REPORT.xlsx
    python3 consignee_buyer_contacts.py REPORT.xlsx -o sheet.xlsx --reconcile
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import pandas as pd
except ImportError:  # pragma: no cover - environment guard
    sys.stderr.write(
        "ERROR: pandas is not installed. Run 'pip install pandas' and retry.\n"
    )
    raise SystemExit(2)


# --------------------------------------------------------------------------- #
# Configuration: the export's shape and the columns we depend on.              #
# --------------------------------------------------------------------------- #
DETAILS_SHEET = "Details"
HEADER_ROW = 4  # 0-indexed; the export puts title/date-range/run-time above it.
DEFAULT_OUTPUT = "consignee_buyer_contacts.xlsx"

SELLER_COL = "Seller"
HAMMER_COL = "USD Hammer Sold Price"
FINAL_COL = "Final Auction Price"
PREMIUM_COL = "Buyer's Premium Price"
PREMIUM_PCT_COL = "Buyer's Premium Percent"
NET_COL = "Net to Consignee (Hammer)"

REQUIRED_COLS = {
    SELLER_COL,
    "Year",
    "Manufacture",
    "Model",
    "Stock Number",
    "Sold Date",
    HAMMER_COL,
    FINAL_COL,
    PREMIUM_COL,
    "Winning Bidder",
    "Address",
    "Phone",
    "Email",
}

# Column order of the consignee-facing sheet: what sold, what it netted, and
# who is going to call about it.
OUTPUT_COLS = [
    SELLER_COL,
    "Stock Number",
    "Year",
    "Manufacture",
    "Model",
    "Sold Date",
    NET_COL,
    "Winning Bidder",
    "Phone",
    "Email",
    "Address",
]

# Kept only under --reconcile, inserted right after the net figure.
RECONCILE_COLS = [FINAL_COL, PREMIUM_COL, PREMIUM_PCT_COL]

MONEY_COLS = {NET_COL, FINAL_COL, PREMIUM_COL}


def load_details(path: Path) -> pd.DataFrame:
    """Read the Details sheet, skipping the export's three title rows."""
    if not path.is_file():
        sys.stderr.write(f"ERROR: no such file: {path}\n")
        raise SystemExit(2)

    try:
        frame = pd.read_excel(path, sheet_name=DETAILS_SHEET, header=HEADER_ROW)
    except ValueError:
        sys.stderr.write(
            f"ERROR: {path.name} has no '{DETAILS_SHEET}' sheet. This does not "
            "look like an AT/PreAT Auction Summary Report export.\n"
        )
        raise SystemExit(2)

    missing = REQUIRED_COLS - set(frame.columns)
    if missing:
        sys.stderr.write(
            "ERROR: export is missing required column(s): "
            f"{', '.join(sorted(missing))}\n"
        )
        raise SystemExit(2)

    # Trailing blank rows are common in these exports; a lot with no seller and
    # no stock number is padding, not a sale.
    frame = frame.dropna(how="all")
    return frame


def _money(series: pd.Series) -> pd.Series:
    """Coerce a currency column to float, tolerating '$1,234.00' strings."""
    cleaned = (
        series.astype(str)
        .str.replace(r"[$,]", "", regex=True)
        .str.strip()
        .replace({"": None, "nan": None, "None": None})
    )
    return pd.to_numeric(cleaned, errors="coerce")


def strip_buyers_premium(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Add the consignee-facing net column and flag lots that don't reconcile.

    Returns ``(frame_with_net, mismatches)``. A mismatch is any row where the
    reported hammer price differs from ``final - premium`` by more than a cent,
    or where the hammer price is missing outright.
    """
    frame = frame.copy()
    hammer = _money(frame[HAMMER_COL])
    final = _money(frame[FINAL_COL])
    premium = _money(frame[PREMIUM_COL]).fillna(0.0)

    derived = final - premium
    frame[NET_COL] = hammer

    # Where the export omitted the hammer price but gave us both other figures,
    # fall back to the derived value rather than shipping a blank to a seller.
    fallback = hammer.isna() & derived.notna()
    frame.loc[fallback, NET_COL] = derived[fallback]

    disagrees = hammer.notna() & derived.notna() & ((hammer - derived).abs() > 0.01)
    unusable = frame[NET_COL].isna()
    mismatches = frame.loc[disagrees | unusable].copy()

    return frame, mismatches


def build_sheet(frame: pd.DataFrame, reconcile: bool = False) -> pd.DataFrame:
    """Select and order the consignee-facing columns, sorted by consignee."""
    columns = list(OUTPUT_COLS)
    if reconcile:
        insert_at = columns.index(NET_COL) + 1
        columns[insert_at:insert_at] = [
            col for col in RECONCILE_COLS if col in frame.columns
        ]

    sheet = frame[[col for col in columns if col in frame.columns]].copy()
    sort_keys = [key for key in (SELLER_COL, "Stock Number") if key in sheet.columns]
    if sort_keys and not sheet.empty:
        sheet = sheet.sort_values(sort_keys, kind="stable").reset_index(drop=True)
    return sheet


def write_sheet(sheet: pd.DataFrame, path: Path) -> None:
    """Write the sheet to xlsx with readable column widths and money formats."""
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        sheet.to_excel(writer, sheet_name="Consignee Contacts", index=False)
        worksheet = writer.sheets["Consignee Contacts"]

        for idx, column in enumerate(sheet.columns, start=1):
            letter = worksheet.cell(row=1, column=idx).column_letter
            longest = max(
                [len(str(column))]
                + [len(str(value)) for value in sheet[column].head(200)]
            )
            worksheet.column_dimensions[letter].width = min(max(longest + 2, 12), 42)

            if column in MONEY_COLS:
                for row in range(2, len(sheet) + 2):
                    worksheet.cell(row=row, column=idx).number_format = (
                        '"$"#,##0.00'
                    )

        worksheet.freeze_panes = "A2"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a per-consignee buyer-contact sheet from an AT/PreAT "
            "Auction Summary Report, with the buyer's premium stripped off."
        )
    )
    parser.add_argument("report", type=Path, help="the exported .xlsx report")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(DEFAULT_OUTPUT),
        help=f"output .xlsx path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--reconcile",
        action="store_true",
        help="keep the final-price and premium columns for an internal check",
    )
    args = parser.parse_args(argv)

    frame = load_details(args.report)
    if frame.empty:
        sys.stderr.write(
            f"ERROR: {args.report.name} contains no sold lots — the Details "
            "sheet has headers but no rows. Re-pull the export for a date "
            "range that actually has sales.\n"
        )
        return 1

    frame, mismatches = strip_buyers_premium(frame)
    sheet = build_sheet(frame, reconcile=args.reconcile)
    write_sheet(sheet, args.output)

    sellers = sheet[SELLER_COL].nunique() if SELLER_COL in sheet.columns else 0
    print(f"Wrote {args.output} — {len(sheet)} lot(s) across {sellers} consignee(s).")
    print(f"Buyer's premium stripped; '{NET_COL}' is the seller-facing figure.")

    if not mismatches.empty:
        print(
            f"\nWARNING: {len(mismatches)} lot(s) did not reconcile "
            "(hammer != final - premium, or no usable price). Check these "
            "before sending:",
            file=sys.stderr,
        )
        for _, row in mismatches.iterrows():
            print(
                f"  - {row.get('Stock Number', '?')} "
                f"({row.get(SELLER_COL, 'unknown seller')})",
                file=sys.stderr,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
