"""Smoke tests for the Sandhills Market Snapshot pipeline.

These cover the scoring math, the hot-category flagging criteria, and the
loud-failure validation contract that the executive runners depend on.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import market_snapshot as ms


def _inventory(**overrides):
    base = {
        "StockNumber": ["A1", "A2", "A3"],
        "AssetCategory": ["Dozer", "Dozer", "Excavator"],
        "ListPrice": [100_000, 90_000, 150_000],
        "AuctionValue": [80_000, 70_000, 120_000],
        "DaysOnMarket": [10, 0, 20],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def _webstats():
    return pd.DataFrame({"StockNumber": ["A1", "A3"], "Views": [50, 100]})


class TestMergeAndScore:
    def test_engagement_score_is_views_per_day(self):
        scored = ms.merge_and_score(
            ms.clean_inventory(_inventory()), ms.clean_webstats(_webstats())
        )
        a1 = scored.set_index("StockNumber").loc["A1"]
        assert a1["BuyerEngagementScore"] == pytest.approx(5.0)  # 50 / 10

    def test_zero_days_on_market_does_not_divide_by_zero(self):
        scored = ms.merge_and_score(
            ms.clean_inventory(_inventory()), ms.clean_webstats(_webstats())
        )
        a2 = scored.set_index("StockNumber").loc["A2"]
        assert a2["BuyerEngagementScore"] == 0

    def test_unmatched_lot_backfills_category_average_views(self):
        scored = ms.merge_and_score(
            ms.clean_inventory(_inventory()), ms.clean_webstats(_webstats())
        )
        a2 = scored.set_index("StockNumber").loc["A2"]
        # A2 has no webstats row; Dozer category average is A1's 50 views.
        assert a2["Views"] == pytest.approx(50.0)

    def test_duplicate_webstats_rows_are_summed(self):
        web = pd.DataFrame({"StockNumber": ["A1", "A1"], "Views": [30, 20]})
        cleaned = ms.clean_webstats(web)
        assert len(cleaned) == 1
        assert cleaned["Views"].iloc[0] == 50


class TestFlagHotCategories:
    def test_flags_supply_down_value_up(self):
        trends = pd.DataFrame(
            {
                "AssetCategory": ["Dozer", "Excavator", "Crane"],
                "RegionalInventoryChangePct": [-5.0, -3.0, 2.0],
                "RegionalPriceChangePct": [4.0, -1.0, 5.0],
                "AuctionValueChangePct": [-2.0, -2.0, 5.0],
            }
        )
        hot = ms.flag_hot_categories(trends)
        # Dozer: supply down + price up -> hot. Excavator: nothing rising.
        # Crane: supply rising -> not hot.
        assert list(hot["AssetCategory"]) == ["Dozer"]

    def test_no_hot_categories_yields_empty_match(self):
        scored = ms.merge_and_score(
            ms.clean_inventory(_inventory()), ms.clean_webstats(_webstats())
        )
        hot = ms.flag_hot_categories(
            pd.DataFrame(
                {
                    "AssetCategory": ["Dozer"],
                    "RegionalInventoryChangePct": [1.0],
                    "RegionalPriceChangePct": [1.0],
                    "AuctionValueChangePct": [1.0],
                }
            )
        )
        assert ms.match_inventory_to_hot(scored, hot).empty


class TestRetailComps:
    def test_missing_file_is_skipped_not_fatal(self, tmp_path):
        assert ms.load_retail_comps(tmp_path / "nope.csv") is None

    def test_derives_sold_and_ratio_from_asking(self, tmp_path):
        p = tmp_path / ms.RETAIL_COMPS_CSV
        p.write_text(
            "Model,AuctionPrice,RetailAsking\n"
            "8285R,187750,159100\n"
        )
        comps = ms.load_retail_comps(p)
        assert comps is not None
        row = comps.iloc[0]
        # Retail sold estimated at 90% of asking, ratio = auction / sold - 1.
        assert row["RetailSoldEst"] == pytest.approx(143190.0)
        assert row["AuctionVsRetailSoldPct"] == pytest.approx(31.1, abs=0.1)

    def test_missing_required_column_is_skipped(self, tmp_path):
        p = tmp_path / ms.RETAIL_COMPS_CSV
        p.write_text("Model,AuctionPrice\n8285R,187750\n")
        assert ms.load_retail_comps(p) is None

    def test_tracker_section_renders_when_comps_present(self, tmp_path):
        repo = Path(__file__).resolve().parent.parent
        for name in (ms.INVENTORY_CSV, ms.WEBSTATS_CSV, ms.MARKET_TRENDS_CSV):
            (tmp_path / name).write_text((repo / name).read_text())
        (tmp_path / ms.RETAIL_COMPS_CSV).write_text(
            "SaleDate,Make,Model,Year,Hours,AuctionPrice,RetailAsking\n"
            "2026-08-05,John Deere,8285R,2013,3600,187750,159100\n"
        )
        text = ms.run(tmp_path).read_text()
        assert "Auction → Retail Tracker" in text


class TestLoadCsvValidation:
    def test_missing_file_raises_pipeline_error(self, tmp_path):
        with pytest.raises(ms.PipelineError, match="was not found"):
            ms.load_csv(tmp_path / "missing.csv", {"StockNumber"}, "Inventory")

    def test_missing_column_raises_pipeline_error(self, tmp_path):
        p = tmp_path / "inv.csv"
        p.write_text("StockNumber,ListPrice\nA1,100\n")
        with pytest.raises(ms.PipelineError, match="missing required column"):
            ms.load_csv(p, {"StockNumber", "Views"}, "WebStats")

    def test_empty_file_raises_pipeline_error(self, tmp_path):
        p = tmp_path / "empty.csv"
        p.write_text("StockNumber,Views\n")
        with pytest.raises(ms.PipelineError, match="no data rows"):
            ms.load_csv(p, {"StockNumber", "Views"}, "WebStats")


class TestEndToEnd:
    def test_full_run_on_sample_data(self, tmp_path):
        repo = Path(__file__).resolve().parent.parent
        for name in (ms.INVENTORY_CSV, ms.WEBSTATS_CSV, ms.MARKET_TRENDS_CSV):
            (tmp_path / name).write_text((repo / name).read_text())
        out = ms.run(tmp_path)
        text = out.read_text()
        assert "# Sandhills Market Snapshot" in text
        assert "Hot-Selling Action Items" in text
