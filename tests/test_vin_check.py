"""Tests for the VIN checker.

These cover the check-digit arithmetic that separates real VINs from
fabricated ones, the model-year disambiguation across the 30-year code cycle,
and the CLI contract (exit codes) that sourcing scripts depend on.

The "known good" fixtures are real 2026 Ford F-450 Super Duty VINs collected
during a Platinum Plus sourcing sweep — every one is a genuine Kentucky Truck
Plant build, which makes them a useful regression net for the arithmetic.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import vin_check as vc

# Real 2026 F-450 DRW builds out of Kentucky Truck Plant.
KNOWN_GOOD = [
    "1FT8W4DM6TED77655",
    "1FT8W4DM9TEE16481",
    "1FT8W4DM1TEE64377",
    "1FT8W4DM1TED70984",
    "1FT8W4DM0TEC11034",
    "1FT8W4DM6TEC12138",
    "1FT8W4DM4TEC22764",
    "1FT8W4DM9TED70330",
    "1FT8W4DMXTEC89756",  # check digit X
    "1FT8W4DM5TEE91467",
    "1FT8W4DM8TEC38224",
    "1FT8W4DM8TED83022",
]


class TestCheckDigit:
    @pytest.mark.parametrize("vin", KNOWN_GOOD)
    def test_known_real_vins_validate(self, vin):
        assert vc.inspect(vin)["valid"] is True

    def test_check_digit_x_is_handled(self):
        # A remainder of 10 is written as X, not as a digit.
        assert vc.check_digit("1FT8W4DMXTEC89756") == "X"

    def test_single_character_corruption_is_caught(self):
        # This is the whole point: a made-up VIN almost never checks out.
        corrupted = "1FT8W4DM6TED77656"  # last digit bumped
        record = vc.inspect(corrupted)
        assert record["valid"] is False
        assert "check digit" in record["reason"]

    def test_transposed_characters_are_caught(self):
        record = vc.inspect("1FT8W4DM6TED77565")
        assert record["valid"] is False

    def test_check_digit_rejects_wrong_length(self):
        with pytest.raises(vc.VinError):
            vc.check_digit("1FT8W4DM6TED776")


class TestRejections:
    @pytest.mark.parametrize("letter", ["I", "O", "Q"])
    def test_excluded_letters_are_rejected(self, letter):
        vin = "1FT8W4DM6TED7765" + letter
        record = vc.inspect(vin)
        assert record["valid"] is False
        assert letter in record["reason"]

    def test_short_vin_reports_length(self):
        record = vc.inspect("1FT8W4DM6")
        assert record["valid"] is False
        assert "wrong length" in record["reason"]

    def test_empty_string_does_not_raise(self):
        assert vc.inspect("")["valid"] is False

    def test_garbage_does_not_raise(self):
        # One bad row must never abort a whole candidate sweep.
        assert vc.inspect("call for price!!")["valid"] is False


class TestNormalization:
    def test_lowercase_is_accepted(self):
        assert vc.inspect("1ft8w4dm6ted77655")["valid"] is True

    def test_spaces_and_dashes_are_stripped(self):
        record = vc.inspect(" 1FT8W4DM6-TED77655 ")
        assert record["valid"] is True
        assert record["vin"] == "1FT8W4DM6TED77655"

    def test_raw_input_is_preserved_for_reporting(self):
        assert vc.inspect(" 1ft8w4dm6ted77655 ")["raw"] == " 1ft8w4dm6ted77655 "


class TestDecode:
    def test_model_year_resolves_to_current_cycle(self):
        # Position 7 is a letter -> 2010+ cycle, so T is 2026 not 1996.
        assert vc.inspect("1FT8W4DM6TED77655")["model_year"] == 2026

    def test_model_year_falls_back_to_earlier_cycle(self):
        # Position 7 numeric -> pre-2010 cycle. Positions 7 and 10 are all
        # _resolve_model_year reads, so a synthetic string is enough here.
        assert vc._resolve_model_year("1FT8W44M6TED77655") == 1996

    def test_digit_year_codes_are_unambiguous(self):
        assert vc._resolve_model_year("1FT8W4DM65ED77655") == 2005

    def test_plant_is_decoded_for_ford(self):
        record = vc.inspect("1FT8W4DM6TED77655")
        assert record["plant_code"] == "E"
        assert "Kentucky Truck Plant" in record["plant"]

    def test_unrecognized_plant_code_reports_none_rather_than_guessing(self):
        record = vc.inspect("1FT8W4DM5TZD77655")
        assert record["valid"] is True
        assert record["plant_code"] == "Z"
        assert record["plant"] is None

    def test_class_8_year_ambiguity_is_documented_behavior(self):
        # Heavy trucks often carry a digit at position 7 regardless of year,
        # so the light-vehicle disambiguation rule resolves them 30 years
        # early. Locked in here so it reads as a known limit, not a bug --
        # VIN_CHECK_README.md tells users to confirm Class 8 years via NHTSA.
        record = vc.inspect("1XPWD40X1ED215307")  # Peterbilt
        assert record["valid"] is True
        assert record["model_year"] == 1984

    def test_sequence_is_the_last_six_characters(self):
        assert vc.inspect("1FT8W4DM6TED77655")["sequence"] == "D77655"

    def test_wmi_is_the_first_three(self):
        assert vc.inspect("1FT8W4DM6TED77655")["wmi"] == "1FT"


class TestVerificationUrls:
    def test_ford_vin_gets_a_window_sticker_url(self):
        url = vc.window_sticker_url("1FT8W4DM6TED77655")
        assert url.startswith("https://www.windowsticker.forddirect.com/")
        assert "1FT8W4DM6TED77655" in url

    def test_non_ford_vin_gets_no_window_sticker(self):
        # A Peterbilt WMI — Ford's service would not know it.
        assert vc.window_sticker_url("1XPWD40X1ED215307") is None

    def test_every_vin_gets_an_nhtsa_url(self):
        assert "1XPWD40X1ED215307" in vc.nhtsa_url("1XPWD40X1ED215307")

    def test_is_ford_recognizes_lincoln(self):
        assert vc.is_ford("5LMJJ2LT0KEL01234") is True


class TestInputs:
    def test_file_reader_skips_blanks_and_comments(self, tmp_path):
        path = tmp_path / "candidates.txt"
        path.write_text(
            "# Platinum Plus sweep\n"
            "1FT8W4DM6TED77655\n"
            "\n"
            "   1FT8W4DM9TEE16481   \n",
            encoding="utf-8",
        )
        assert vc.read_vins_from_file(path) == [
            "1FT8W4DM6TED77655",
            "1FT8W4DM9TEE16481",
        ]

    def test_csv_reader_pulls_the_named_column(self, tmp_path):
        path = tmp_path / "candidates.csv"
        path.write_text(
            "Dealer,VIN,Price\n"
            "Krietz,1FT8W4DM1TED70984,143960\n"
            "TVE,1FT8W4DM6TEC12138,\n",
            encoding="utf-8",
        )
        assert vc.read_vins_from_csv(path, "VIN") == [
            "1FT8W4DM1TED70984",
            "1FT8W4DM6TEC12138",
        ]

    def test_csv_reader_names_the_missing_column(self, tmp_path):
        path = tmp_path / "candidates.csv"
        path.write_text("Dealer,Serial\nKrietz,123\n", encoding="utf-8")
        with pytest.raises(vc.VinError, match="no 'VIN' column"):
            vc.read_vins_from_csv(path, "VIN")

    def test_csv_reader_skips_rows_with_no_vin(self, tmp_path):
        path = tmp_path / "candidates.csv"
        path.write_text("VIN\n1FT8W4DM6TED77655\n\n", encoding="utf-8")
        assert vc.read_vins_from_csv(path, "VIN") == ["1FT8W4DM6TED77655"]


class TestCli:
    def test_all_valid_exits_zero(self, capsys):
        assert vc.main(["1FT8W4DM6TED77655"]) == 0
        assert "VALID" in capsys.readouterr().out

    def test_any_invalid_exits_one(self, capsys):
        # Scripts key off this: a nonzero exit means something needs eyes.
        assert vc.main(["1FT8W4DM6TED77655", "1FT8W4DM6TED77656"]) == 1
        assert "INVALID" in capsys.readouterr().out

    def test_no_input_exits_two(self, capsys):
        assert vc.main([]) == 2
        assert "no VINs given" in capsys.readouterr().err

    def test_missing_csv_exits_two(self, capsys):
        assert vc.main(["--csv", "does_not_exist.csv"]) == 2
        assert "ERROR" in capsys.readouterr().err

    def test_json_output_is_parseable(self, capsys):
        vc.main(["--json", "1FT8W4DM6TED77655"])
        records = json.loads(capsys.readouterr().out)
        assert records[0]["model_year"] == 2026

    def test_urls_only_prints_one_url_per_valid_vin(self, capsys):
        vc.main(["--urls-only", "1FT8W4DM6TED77655", "1FT8W4DM6TED77656"])
        lines = capsys.readouterr().out.strip().splitlines()
        assert len(lines) == 1  # the invalid VIN is not offered for lookup
        assert lines[0].startswith("https://")

    def test_table_carries_the_on_the_ground_caveat(self, capsys):
        vc.main(["1FT8W4DM6TED77655"])
        assert "proves it is on a lot today" in capsys.readouterr().out
