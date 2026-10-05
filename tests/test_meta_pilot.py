"""Tests for the HIS Meta pilot: unit pages, catalog feed, and Gavel Reports."""

import csv
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import meta_pilot as mp

SAMPLE = ROOT / "sample" / "meta_pilot"
AS_OF = date(2026, 10, 5)


@pytest.fixture
def photos(tmp_path):
    folder = tmp_path / "Photos"
    folder.mkdir()
    for name in ("SN2001_02.jpg", "SN2001_01.jpg", "LOT02002_01.JPG", "notes.txt"):
        (folder / name).write_bytes(b"\xff\xd8\xff")
    return folder


@pytest.fixture
def units(photos):
    inv = mp.load_inventory(SAMPLE / "inventory_sample.csv")
    pilot = mp.load_pilot(SAMPLE / "pilot_units_sample.csv")
    return mp.build_units(inv, pilot, mp.index_photos(photos))


def _unit(**overrides):
    base = dict(
        stock="X1", year="2019", make="Deere", model="8R", price=115_000.0,
        category="Tractors", description="", hours=None, miles=None, city="",
        state="IA", serial="", seller_name="S", start_date=date(2026, 9, 1),
        market_value=100_000.0, ladder=[115_000.0, 104_000.0, 99_000.0],
    )
    base.update(overrides)
    return mp.Unit(**base)


def _metrics(**overrides):
    base = dict(reach=5_000, impressions=10_000, spend=100.0, link_clicks=50,
                thruplays=300, avg_watch=6.0, leads=0, messages=0, page_views=40,
                saves=0, contacts=0, top_regions=[], inquiries=0)
    base.update(overrides)
    base["inquiries"] = sum(base[k] or 0 for k in ("leads", "messages", "contacts"))
    return base


class TestLoading:
    def test_photos_are_ordered_and_matched_loosely(self, units):
        by_stock = {u.stock: u for u in units}
        assert [p.name for p in by_stock["SN2001"].photos] == ["SN2001_01.jpg", "SN2001_02.jpg"]
        # LOT02002_01.JPG is stock "2002", not "SN2002", so it must not match.
        assert by_stock["SN2002"].photos == []

    def test_lot_prefix_and_zeros_match(self, tmp_path):
        (tmp_path / "LOT042_01.jpg").write_bytes(b"x")
        assert "42" in mp.index_photos(tmp_path)

    def test_unknown_pilot_unit_fails_loud(self, tmp_path):
        pilot = tmp_path / "pilot.csv"
        pilot.write_text("StockNumber,seller_name,start_date\nNOPE,S,2026-09-01\n")
        inv = mp.load_inventory(SAMPLE / "inventory_sample.csv")
        with pytest.raises(mp.InputError, match="not in the inventory export"):
            mp.build_units(inv, mp.load_pilot(pilot), {})

    def test_missing_inventory_column_names_found_columns(self, tmp_path):
        path = tmp_path / "inv.csv"
        path.write_text("StockNumber,Year\nA,2019\n")
        with pytest.raises(mp.InputError, match="Columns found"):
            mp.load_inventory(path)

    def test_ladder_parses_money_strings(self):
        assert mp.parse_ladder("$289,000; 279000 ;") == [289000.0, 279000.0]


class TestPages:
    def test_page_carries_pixel_events_with_catalog_id(self, units, tmp_path):
        result = mp.build_pages(units, tmp_path / "site", "123", "https://u.example.com")
        assert result["built"] == ["SN2001"]
        page = (tmp_path / "site" / "SN2001" / "index.html").read_text()
        assert "fbq('init', \"123\")" in page
        assert "'ViewContent'" in page and "AddToWishlist" in page
        assert '"content_ids": ["SN2001"]' in page
        assert '"serialNumber": "1RW8340RCKD012345"' in page
        assert (tmp_path / "site" / "SN2001" / "photo-2.jpg").exists()

    def test_unit_without_crew_photos_gets_no_page(self, units, tmp_path):
        result = mp.build_pages(units, tmp_path / "site", "1", "https://u.example.com")
        assert any("SN2002" in s for s in result["skipped"])
        assert not (tmp_path / "site" / "SN2002").exists()

    def test_rejected_words_in_description_are_flagged_not_edited(self, units, tmp_path):
        unit = next(u for u in units if u.stock == "SN2001")
        unit.description = "Consignment unit from the June auction."
        result = mp.build_pages([unit], tmp_path / "site", "1", "https://u.example.com")
        assert result["warnings"] and "auction" in result["warnings"][0]
        assert "Consignment unit" in (tmp_path / "site" / "SN2001" / "index.html").read_text()

    def test_his_template_copy_passes_epiphany_standard(self, units, tmp_path):
        unit = next(u for u in units if u.stock == "SN2001")
        unit.description = ""
        page = mp.render_unit_page(unit, "1", "https://u.example.com", "555", "https://m.me/x")
        report = mp.render_report(unit, _metrics(), AS_OF)
        for text in (page, report):
            visible = text.split("<body>", 1)[1]
            assert mp.epiphany_hits(visible) == []

    def test_description_is_html_escaped(self, units):
        unit = next(u for u in units if u.stock == "SN2001")
        unit.description = "<script>alert(1)</script>"
        assert "<script>alert(1)" not in mp.render_unit_page(unit, "1", "https://u", "", "")


    def test_export_text_cannot_close_inline_scripts(self, units):
        unit = next(u for u in units if u.stock == "SN2001")
        unit.model = "8R</script><script>alert(1)</script>"
        page = mp.render_unit_page(unit, "1", "https://u", "", "")
        assert "</script><script>alert(1)" not in page


class TestCatalog:
    def test_rows_match_page_ids_and_skip_reasons(self, units):
        rows, skipped = mp.build_catalog(units, "https://u.example.com")
        assert [r["id"] for r in rows] == ["SN2001"]
        row = rows[0]
        assert row["link"] == "https://u.example.com/SN2001/"
        assert row["image_link"].endswith("/SN2001/photo-1.jpg")
        assert row["price"] == "289000.00 USD"
        assert row["condition"] == "used"
        assert any("SN2002" in s and "crew photos" in s for s in skipped)

    def test_write_catalog_has_meta_required_columns(self, units, tmp_path):
        rows, _ = mp.build_catalog(units, "https://u.example.com")
        out = tmp_path / "feed.csv"
        mp.write_catalog(rows, out)
        header = next(csv.reader(out.open()))
        for column in ("id", "title", "description", "availability", "condition",
                       "price", "link", "image_link", "brand"):
            assert column in header


class TestReport:
    def test_metrics_sum_regions_and_weight_watch_time(self):
        ads = mp.load_ads(SAMPLE / "ads_export_sample.csv")
        metrics = mp.unit_metrics(ads, _unit(stock="SN2001"))
        assert metrics["reach"] == 8100
        assert metrics["spend"] == pytest.approx(273.5)
        assert metrics["saves"] == 11
        expected = (7.8 * 14100 + 6.9 * 3900) / 18000
        assert metrics["avg_watch"] == pytest.approx(expected)
        assert metrics["top_regions"][0] == ("Iowa", 6200)

    def test_ad_set_match_does_not_bleed_into_longer_ids(self):
        ads = pd.DataFrame({"ad_set": ["HIS | SN20011"], "reach": ["9"], "impressions": ["9"]})
        assert mp.unit_metrics(ads, _unit(stock="SN2001")) is None

    def test_missing_required_ads_column_fails_loud(self, tmp_path):
        path = tmp_path / "ads.csv"
        path.write_text("Ad set name,Impressions\nX,1\n")
        with pytest.raises(mp.InputError, match="reach"):
            mp.load_ads(path)

    @pytest.mark.parametrize("unit_kw,metric_kw,expected", [
        ({}, {"leads": 2}, "Hold and work the conversations"),
        ({"start_date": date(2026, 10, 1)}, {}, "Hold: too early to call"),
        ({}, {"reach": 200}, "Hold: too early to call"),
        ({}, {"avg_watch": 2.1}, "Reposition the creative"),
        ({}, {}, "Step down the ladder"),
        ({"price": 102_000.0}, {"saves": 3}, "Hold: buyers are watching"),
        ({"price": 102_000.0}, {}, "Widen the audience"),
    ])
    def test_recommendation_paths(self, unit_kw, metric_kw, expected):
        move, _ = mp.recommend(_unit(**unit_kw), _metrics(**metric_kw), AS_OF)
        assert move == expected

    def test_step_down_names_the_committed_next_step(self):
        _, reason = mp.recommend(_unit(), _metrics(), AS_OF)
        assert "$104,000" in reason

    def test_no_matching_ad_set_says_so(self):
        move, reason = mp.recommend(_unit(), None, AS_OF)
        assert move == "No data yet" and "X1" in reason

    def test_price_position_unknown_without_market_value(self):
        label, ratio = mp.price_position(_unit(market_value=None))
        assert ratio is None and "unknown" in label

    def test_end_to_end_cli_on_sample(self, tmp_path, capsys):
        code = mp.main([
            "report", "--inventory", str(SAMPLE / "inventory_sample.csv"),
            "--pilot", str(SAMPLE / "pilot_units_sample.csv"),
            "--ads", str(SAMPLE / "ads_export_sample.csv"),
            "--as-of", "2026-10-05", "--out", str(tmp_path / "r"),
        ])
        assert code == 0
        out = capsys.readouterr().out
        assert "SN2001: Step down the ladder" in out
        assert "SN2002: Hold and work the conversations" in out
        report = (tmp_path / "r" / "SN2001.html").read_text()
        assert "You hold the gavel" in report and "$279,000" in report

    def test_cli_rejects_non_https_base_url(self, photos, capsys):
        code = mp.main([
            "catalog", "--inventory", str(SAMPLE / "inventory_sample.csv"),
            "--pilot", str(SAMPLE / "pilot_units_sample.csv"),
            "--photos", str(photos), "--base-url", "http://insecure.example.com",
        ])
        assert code == 2
        assert "https://" in capsys.readouterr().err


class TestBrand:
    def test_his_brand_file_matches_built_in_default(self):
        assert mp.load_brand(ROOT / "brands" / "his.json") == mp.HIS_BRAND

    def test_client_brand_renders_everywhere(self, units, tmp_path):
        brand = mp.Brand(name="Prairie Fleet Co", report_name="Demand Report",
                         decision_line="Your call. {name} advises.",
                         rejected_words=("cheap",), price_zone=0.05)
        unit = next(u for u in units if u.stock == "SN2001")
        page = mp.render_unit_page(unit, "1", "https://u", "", "", brand)
        report = mp.render_report(unit, _metrics(), AS_OF, brand)
        assert "Prairie Fleet Co" in page and "Heartland" not in page
        assert "Demand Report" in report and "Your call. Prairie Fleet Co advises." in report
        assert "Heartland" not in report and "Gavel" not in report

    def test_client_thresholds_drive_the_recommendation(self):
        strict = mp.Brand(price_zone=0.01)
        unit = _unit(price=103_000.0)
        assert mp.recommend(unit, _metrics(), AS_OF)[0] == "Widen the audience"
        assert mp.recommend(unit, _metrics(), AS_OF, strict)[0] == "Step down the ladder"

    def test_client_rejected_words_replace_his_list(self):
        brand = mp.Brand(rejected_words=("cheap",))
        assert mp.epiphany_hits("cheap auction iron", brand.rejected_words) == ["cheap"]

    def test_unknown_brand_key_fails_loud(self, tmp_path):
        path = tmp_path / "b.json"
        path.write_text('{"name": "X", "colour": "red"}')
        with pytest.raises(mp.InputError, match="colour"):
            mp.load_brand(path)

    def test_template_loads(self):
        assert mp.load_brand(ROOT / "brands" / "client_template.json").rejected_words == ()
