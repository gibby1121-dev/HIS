"""Tests for the consignee buyer-contact sheet.

These cover the buyer's-premium math (the whole point of the sheet), the
reconciliation warning that keeps a bad number from reaching a seller, and the
empty-export guard that the 2026-08-26 pull tripped.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import consignee_buyer_contacts as cbc


def _details(**overrides):
    """A two-lot export: one clean 10% premium, one that doesn't reconcile."""
    base = {
        "Seller": ["Bar Diamond Farms", "Ackley Trucking"],
        "Year": [2018, 2020],
        "Manufacture": ["John Deere", "Peterbilt"],
        "Model": ["8320R", "579"],
        "Stock Number": ["MIA-1042", "MIA-1017"],
        "Auction End Date": ["8/26/2026", "8/26/2026"],
        "Sold Date": ["8/26/2026", "8/26/2026"],
        "Auction Value": [150_000, 70_000],
        "Market Value": [175_000, 82_000],
        "Wholesale Value": [140_000, 65_000],
        "Final Auction Price": [165_000.00, 88_000.00],
        "Sold on Pre-AuctionTime": ["No", "Yes"],
        "Sales Rep": ["Kent", "Kent"],
        "USD Hammer Sold Price": [150_000.00, 80_000.00],
        "Buyer's Premium Price": [15_000.00, 8_000.00],
        "Buyer's Premium Percent": [10.0, 10.0],
        "Winning Bidder": ["Dale Wurtz", "Cedar Valley Hauling"],
        "Address": ["Grundy Center, IA", "Cedar Falls, IA"],
        "Phone": ["319-555-0142", "319-555-0188"],
        "Email": ["dwurtz@example.com", "dispatch@example.com"],
    }
    base.update(overrides)
    return pd.DataFrame(base)


class TestStripBuyersPremium:
    def test_net_is_the_hammer_price_not_what_the_buyer_paid(self):
        frame, _ = cbc.strip_buyers_premium(_details())
        assert list(frame[cbc.NET_COL]) == [150_000.00, 80_000.00]

    def test_net_equals_final_minus_premium(self):
        details = _details()
        frame, _ = cbc.strip_buyers_premium(details)
        expected = details["Final Auction Price"] - details["Buyer's Premium Price"]
        assert frame[cbc.NET_COL].tolist() == pytest.approx(expected.tolist())

    def test_currency_strings_are_parsed(self):
        details = _details(
            **{
                "USD Hammer Sold Price": ["$150,000.00", "$80,000.00"],
                "Final Auction Price": ["$165,000.00", "$88,000.00"],
                "Buyer's Premium Price": ["$15,000.00", "$8,000.00"],
            }
        )
        frame, mismatches = cbc.strip_buyers_premium(details)
        assert frame[cbc.NET_COL].tolist() == [150_000.00, 80_000.00]
        assert mismatches.empty

    def test_missing_hammer_falls_back_to_final_minus_premium(self):
        details = _details(**{"USD Hammer Sold Price": [None, 80_000.00]})
        frame, mismatches = cbc.strip_buyers_premium(details)
        assert frame[cbc.NET_COL].tolist() == [150_000.00, 80_000.00]
        assert mismatches.empty

    def test_hammer_disagreeing_with_final_minus_premium_is_flagged(self):
        details = _details(**{"USD Hammer Sold Price": [149_000.00, 80_000.00]})
        _, mismatches = cbc.strip_buyers_premium(details)
        assert mismatches["Stock Number"].tolist() == ["MIA-1042"]

    def test_lot_with_no_usable_price_is_flagged(self):
        details = _details(
            **{
                "USD Hammer Sold Price": [None, 80_000.00],
                "Final Auction Price": [None, 88_000.00],
                "Buyer's Premium Price": [None, 8_000.00],
            }
        )
        _, mismatches = cbc.strip_buyers_premium(details)
        assert mismatches["Stock Number"].tolist() == ["MIA-1042"]


class TestBuildSheet:
    def test_premium_columns_are_stripped_by_default(self):
        frame, _ = cbc.strip_buyers_premium(_details())
        sheet = cbc.build_sheet(frame)
        assert cbc.PREMIUM_COL not in sheet.columns
        assert cbc.PREMIUM_PCT_COL not in sheet.columns
        assert cbc.FINAL_COL not in sheet.columns

    def test_reconcile_keeps_the_premium_columns(self):
        frame, _ = cbc.strip_buyers_premium(_details())
        sheet = cbc.build_sheet(frame, reconcile=True)
        for column in (cbc.FINAL_COL, cbc.PREMIUM_COL, cbc.PREMIUM_PCT_COL):
            assert column in sheet.columns

    def test_buyer_contact_details_are_carried_through(self):
        frame, _ = cbc.strip_buyers_premium(_details())
        sheet = cbc.build_sheet(frame).set_index("Stock Number")
        row = sheet.loc["MIA-1042"]
        assert row["Winning Bidder"] == "Dale Wurtz"
        assert row["Phone"] == "319-555-0142"
        assert row["Email"] == "dwurtz@example.com"

    def test_rows_are_grouped_by_consignee(self):
        frame, _ = cbc.strip_buyers_premium(_details())
        sheet = cbc.build_sheet(frame)
        assert sheet[cbc.SELLER_COL].tolist() == [
            "Ackley Trucking",
            "Bar Diamond Farms",
        ]


class TestEndToEnd:
    def _write_export(self, path, details):
        """Rebuild the export's shape: three title rows above the header."""
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            details.to_excel(
                writer, sheet_name="Details", index=False, startrow=cbc.HEADER_ROW
            )

    def test_writes_a_sheet_with_the_premium_stripped(self, tmp_path):
        source = tmp_path / "report.xlsx"
        output = tmp_path / "contacts.xlsx"
        self._write_export(source, _details())

        assert cbc.main([str(source), "-o", str(output)]) == 0

        sheet = pd.read_excel(output)
        assert len(sheet) == 2
        assert cbc.PREMIUM_COL not in sheet.columns
        assert sorted(sheet[cbc.NET_COL]) == [80_000.00, 150_000.00]

    def test_empty_export_fails_loudly(self, tmp_path):
        source = tmp_path / "empty.xlsx"
        output = tmp_path / "contacts.xlsx"
        self._write_export(source, _details().iloc[0:0])

        assert cbc.main([str(source), "-o", str(output)]) == 1
        assert not output.exists()

    def test_missing_column_is_rejected(self, tmp_path):
        source = tmp_path / "bad.xlsx"
        self._write_export(source, _details().drop(columns=["Buyer's Premium Price"]))

        with pytest.raises(SystemExit) as excinfo:
            cbc.main([str(source), "-o", str(tmp_path / "out.xlsx")])
        assert excinfo.value.code == 2


class TestReportVariants:
    """Both exports seen in the wild carry the columns we depend on.

    The 'AT/PreAT Auction Summary Report' has 'Sold on Pre-AuctionTime'; the
    plain 'Auction Summary Report' drops it and adds ListingID / Lot Number.
    Neither difference touches the premium math or the buyer contact fields.
    """

    def test_plain_auction_summary_variant_is_accepted(self, tmp_path):
        details = _details().drop(columns=["Sold on Pre-AuctionTime"])
        details.insert(0, "ListingID", [9001, 9002])
        details.insert(1, "Lot Number", [12, 47])

        source = tmp_path / "variant.xlsx"
        output = tmp_path / "contacts.xlsx"
        with pd.ExcelWriter(source, engine="openpyxl") as writer:
            details.to_excel(
                writer, sheet_name="Details", index=False, startrow=cbc.HEADER_ROW
            )

        assert cbc.main([str(source), "-o", str(output)]) == 0
        sheet = pd.read_excel(output)
        assert sorted(sheet[cbc.NET_COL]) == [80_000.00, 150_000.00]
        assert cbc.PREMIUM_COL not in sheet.columns
