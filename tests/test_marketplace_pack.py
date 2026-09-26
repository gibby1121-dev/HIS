"""Tests for the Marketplace post-pack builder."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import marketplace_pack as mp


def _write_inventory(path, rows, header=None):
    header = header or ["Stock #", "Year", "Make", "Model", "Category", "Price", "Hours"]
    frame = pd.DataFrame(rows, columns=header)
    frame.to_csv(path, index=False)
    return path


def _touch(folder, name):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(b"jpg")


@pytest.fixture
def workspace(tmp_path):
    inv = _write_inventory(
        tmp_path / "ExportInventory.csv",
        [
            ["SN1001", "2019", "John Deere", "8335R", "Tractors", "$189,500", "3100"],
            ["LOT042", "2014", "Case IH", "Magnum 340", "Tractors", "", "5200"],
            ["SN1003", "2018", "Kinze", "3600", "Planters", "42000", ""],
        ],
    )
    photos = tmp_path / "Photos"
    for name in ("SN1001_02.jpg", "SN1001_01.JPG", "SN1001_10.jpg", "lot42_01.jpg",
                 "notes.txt", "random.jpg"):
        _touch(photos, name)
    return inv, photos, tmp_path / "queue"


class TestColumns:
    def test_resolves_header_variants(self):
        cols = mp.resolve_columns(["Stock Number", "YEAR", "Make", "Model", "Asking Price"])
        assert cols["stock"] == "Stock Number"
        assert cols["price"] == "Asking Price"

    def test_missing_required_field_fails_loudly(self):
        with pytest.raises(mp.PackError, match="model"):
            mp.resolve_columns(["StockNumber", "Year", "Make"])


class TestPhotos:
    def test_orders_by_sequence_and_matches_lot_prefix(self, workspace):
        _, photos, _ = workspace
        index = mp.index_photos(photos)
        assert [p.name for p in index["sn1001"]] == [
            "SN1001_01.JPG", "SN1001_02.jpg", "SN1001_10.jpg"
        ]
        assert mp._stock_key("LOT042") in index
        assert "random" not in index


class TestText:
    def test_title_includes_hours_and_respects_limit(self):
        unit = mp.Unit("A1", "2019", "John Deere", "8335R", hours=3100)
        assert mp.build_title(unit) == "2019 John Deere 8335R, 3,100 hrs"
        long = mp.Unit("A1", "2019", "X" * 150, "Y")
        assert len(mp.build_title(long)) <= mp.TITLE_MAX

    def test_description_carries_contact_and_link(self):
        unit = mp.Unit("A1", "2019", "JD", "8335R",
                       listing_url="https://www.tractorhouse.com/listing/1")
        text = mp.build_description(unit, phone="515-555-0100", location="Ames, IA",
                                    sale_note="Sells Oct 14")
        assert "Stock #: A1" in text
        assert "Sells Oct 14" in text
        assert "tractorhouse.com/listing/1" in text
        assert "Call/text 515-555-0100 | Ames, IA" in text


class TestBuildQueue:
    def test_statuses_and_packs(self, workspace):
        inv, photos, out = workspace
        queue = mp.build_queue(inv, photos, out, max_photos=2).set_index("StockNumber")

        assert queue.loc["SN1001", "Status"] == mp.STATUS_READY
        assert queue.loc["SN1001", "Price"] == "189500"
        assert queue.loc["LOT042", "Status"] == mp.STATUS_NEEDS_PRICE
        assert queue.loc["SN1003", "Status"] == mp.STATUS_NEEDS_PHOTOS

        pack = out / "SN1001"
        assert sorted(p.name for p in pack.iterdir()) == ["01.jpg", "02.jpg", "listing.txt"]
        assert "189,500" in (pack / "listing.txt").read_text()
        assert not (out / "SN1003").exists()

    def test_rerun_keeps_posting_log_and_flags_takedowns(self, workspace, tmp_path):
        inv, photos, out = workspace
        mp.build_queue(inv, photos, out)
        log = pd.read_csv(out / mp.QUEUE_CSV, dtype=str).fillna("")
        log.loc[log.StockNumber == "SN1001", "MarketplaceURL"] = "https://fb.com/m/1"
        log.loc[log.StockNumber == "LOT042", "MarketplaceURL"] = "https://fb.com/m/2"
        log.to_csv(out / mp.QUEUE_CSV, index=False)

        # SN1001 sold and dropped out of the export.
        _write_inventory(inv, [
            ["LOT042", "2014", "Case IH", "Magnum 340", "Tractors", "95000", "5200"],
        ])
        queue = mp.build_queue(inv, photos, out).set_index("StockNumber")
        assert queue.loc["LOT042", "Status"] == "POSTED"
        assert queue.loc["LOT042", "MarketplaceURL"] == "https://fb.com/m/2"
        assert queue.loc["SN1001", "Status"] == "TAKE_DOWN"


def test_main_reports_bad_input(tmp_path, capsys):
    (tmp_path / "Photos").mkdir()
    code = mp.main(["--inventory", str(tmp_path / "missing.csv"),
                    "--photos", str(tmp_path / "Photos")])
    assert code == 1
    assert "not found" in capsys.readouterr().err
