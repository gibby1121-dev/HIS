"""Engine tests: comps normalization, MIA calibration, valuation, deal math,
routes, verdicts, and report rendering."""

import copy
import datetime as dt
import json
import math
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tradein import categories as cats  # noqa: E402
from tradein.analyze import analyze, load_inputs  # noqa: E402
from tradein.comps import CompsError, normalize, strip_premium  # noqa: E402
from tradein.deal import DealError, Financing, Quote, decompose, level_payment, value_financing  # noqa: E402
from tradein.mia import calibrate, load_auction_summary  # noqa: E402
from tradein.report import desk_sheet, operator_report  # noqa: E402
from tradein.routes import commission_pct, consign_net, trade_tax_advantage  # noqa: E402
from tradein.valuation import Unit, ValuationError, fit_rates, value_unit  # noqa: E402

AS_OF = dt.date(2026, 9, 30)
TERMS = json.loads((ROOT / "config" / "mia_terms.json").read_text())
SAMPLE_DEAL = json.loads((ROOT / "sample" / "trade_deal.json").read_text())


def comps_frame(rows):
    base = {"Category": "4WD Tractor", "Make": "John Deere", "Model": "9RX 640",
            "Year": 2021, "Hours": 2000, "PriceBasis": "hammer", "SaleDate": "2026-08-01"}
    return normalize(pd.DataFrame([{**base, **r} for r in rows]).astype(str))


def unit(**kw):
    base = dict(category="4WD Tractor", make="John Deere", model="9RX 640", year=2021, hours=2000)
    base.update(kw)
    return Unit(**base)


# --------------------------------------------------------------------------- #
class TestCategories:
    @pytest.mark.parametrize("make,model,cat", [
        ("John Deere", "9RX 640", cats.FOUR_WD), ("John Deere", "9570R", cats.FOUR_WD),
        ("John Deere", "9620RX", cats.FOUR_WD), ("Case IH", "Steiger 620 Quadtrac", cats.FOUR_WD),
        ("New Holland", "T9.645", cats.FOUR_WD), ("John Deere", "8R 410", cats.ROW_CROP),
        ("John Deere", "8370R", cats.ROW_CROP), ("Case IH", "Magnum 380", cats.ROW_CROP),
        ("John Deere", "S780", cats.COMBINE), ("John Deere", "X9 1100", cats.COMBINE),
        ("Case IH", "8250", cats.COMBINE), ("New Holland", "CR10.90", cats.COMBINE),
        ("John Deere", "DB60", cats.PLANTER), ("John Deere", "1775NT", cats.PLANTER),
        ("Kinze", "4905", cats.PLANTER), ("Kinze", "1300", cats.GRAIN_CART),
        ("John Deere", "R4045", cats.SPRAYER), ("John Deere", "412R", cats.SPRAYER),
        ("Hagie", "STS16", cats.SPRAYER), ("Case IH", "Patriot 4440", cats.SPRAYER),
        ("Brent", "1596", cats.GRAIN_CART), ("Bobcat", "S650", cats.OTHER),
    ])
    def test_classify(self, make, model, cat):
        assert cats.classify(make, model) == cat

    def test_normalize_category_labels(self):
        assert cats.normalize_category("Tractors - 4WD") == cats.FOUR_WD
        assert cats.normalize_category("Combine Corn Heads") == cats.HEADER
        assert cats.normalize_category("Sprayers - Self Propelled") == cats.SPRAYER


# --------------------------------------------------------------------------- #
class TestComps:
    def test_strip_uncapped_premium(self):
        assert strip_premium(495_000, 10) == pytest.approx(450_000)

    def test_strip_capped_premium(self):
        assert strip_premium(454_125, 10, 4_125) == pytest.approx(450_000)

    def test_cap_not_binding_on_small_lot(self):
        assert strip_premium(22_000, 10, 4_125) == pytest.approx(20_000)

    def test_with_bp_requires_premium_pct(self):
        with pytest.raises(CompsError, match="BuyerPremiumPct"):
            comps_frame([{"Price": 100, "PriceBasis": "with_bp"}])

    def test_unknown_basis_rejected(self):
        with pytest.raises(CompsError, match="Unknown PriceBasis"):
            comps_frame([{"Price": 100, "PriceBasis": "sold"}])

    def test_asking_rows_have_no_hammer(self):
        df = comps_frame([{"Price": 500_000, "PriceBasis": "asking"},
                          {"Price": 400_000}])
        assert df["Hammer"].isna().sum() == 1
        assert df["Hammer"].dropna().iloc[0] == 400_000

    def test_category_inferred_when_missing(self):
        raw = pd.DataFrame([{"Make": "John Deere", "Model": "S780", "Year": "2021", "Hours": "1000",
                             "Price": "300000", "PriceBasis": "hammer", "SaleDate": "2026-01-01"}])
        assert normalize(raw)["Category"].iloc[0] == cats.COMBINE


# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def mia_lots(tmp_path_factory):
    sys.path.insert(0, str(ROOT / "scripts"))
    import make_sample_mia_results as gen
    out = gen.main(str(tmp_path_factory.mktemp("mia")))
    return load_auction_summary(out)


class TestMia:
    def test_reads_export_layout(self, mia_lots):
        assert len(mia_lots) == 28
        row = mia_lots.iloc[0]
        assert row["Make"] == "John Deere" and row["Model"] == "9RX 640"
        assert row["FinalWithBP"] == pytest.approx(row["Hammer"] + min(row["Hammer"] * 0.1, 2500))

    def test_shrinkage_toward_one(self, mia_lots):
        cal = calibrate(mia_lots)
        c = cal.by_category[cats.FOUR_WD]
        assert c.applied_ratio == pytest.approx((c.lots * c.median_ratio + 5) / (c.lots + 5))
        assert abs(c.applied_ratio - 1) < abs(c.median_ratio - 1)

    def test_calibration_only_used_where_it_validates(self, mia_lots):
        cal = calibrate(mia_lots)
        for cat, (raw, calibrated) in cal.validation.items():
            used = cal.for_category(cat) is not None
            assert used == (calibrated < raw)

    def test_thin_category_not_calibrated(self, mia_lots):
        cal = calibrate(mia_lots)
        assert cal.for_category(cats.GRAIN_CART) is None  # 2 lots

    def test_missing_details_sheet(self, tmp_path):
        import openpyxl
        p = tmp_path / "Auction Summary Report x.xlsx"
        openpyxl.Workbook().save(p)
        from tradein.mia import MiaDataError
        with pytest.raises(MiaDataError, match="Details"):
            load_auction_summary(p)


# --------------------------------------------------------------------------- #
class TestValuation:
    def test_identical_comps(self):
        v = value_unit(unit(), comps_frame([{"Price": 400_000}] * 5), AS_OF)
        assert v.mid == pytest.approx(400_000)

    def test_fit_recovers_known_rates(self):
        rows = []
        for yr in (2019, 2020, 2021, 2022):
            for hrs in (1000, 2000, 3000):
                p = 400_000 * (0.92 ** (2021 - yr)) * (0.95 ** ((hrs - 2000) / 1000))
                rows.append({"Year": yr, "Hours": hrs, "Price": round(p)})
        dep, per_khr, fitted = fit_rates(comps_frame(rows))
        assert fitted
        assert dep == pytest.approx(0.08, abs=0.002)
        assert per_khr == pytest.approx(0.05, abs=0.002)

    def test_too_few_sales_use_defaults_and_flag(self):
        v = value_unit(unit(), comps_frame([{"Price": 400_000}] * 3), AS_OF)
        assert not v.rates_fitted
        assert any("defaults" in f for f in v.flags)

    def test_buyer_premium_removed_before_valuing(self):
        v = value_unit(unit(), comps_frame([{"Price": 440_000, "PriceBasis": "with_bp",
                                             "BuyerPremiumPct": 10}] * 4), AS_OF)
        assert v.mid == pytest.approx(400_000)

    def test_asking_listings_never_value_the_unit(self):
        v = value_unit(unit(), comps_frame([{"Price": 400_000}] * 4 +
                                           [{"Price": 600_000, "PriceBasis": "asking"}] * 4), AS_OF)
        assert v.mid == pytest.approx(400_000)
        assert v.asking_gap_pct == pytest.approx(50)

    def test_future_and_stale_comps_excluded(self):
        df = comps_frame([{"Price": 100_000, "SaleDate": "2027-01-01"},
                          {"Price": 100_000, "SaleDate": "2023-01-01"}])
        with pytest.raises(ValuationError):
            value_unit(unit(), df, AS_OF)

    def test_anchor_disagreement_flags_low_confidence(self):
        v = value_unit(unit(sandhills_vip={"auction": 300_000}),
                       comps_frame([{"Price": 400_000}] * 6), AS_OF)
        assert v.confidence == "Low"
        assert any("disagree" in f for f in v.flags)

    def test_vip_only(self):
        v = value_unit(unit(sandhills_vip={"auction": 350_000}), None, AS_OF)
        assert v.mid == pytest.approx(350_000)
        assert "uncalibrated" in v.anchors[0].name


# --------------------------------------------------------------------------- #
class TestDeal:
    def test_zero_rate_payment(self):
        assert level_payment(300_000, 0, 5, 1) == pytest.approx(60_000)

    def test_level_payment_matches_formula(self):
        assert level_payment(100_000, 12, 12, 12) == pytest.approx(8_884.88, abs=0.01)

    def test_zero_pct_is_worth_pv_gap(self):
        f = value_financing(Financing(apr=0, term_months=60, payments_per_year=1), 300_000, 7.0)
        pv = sum(60_000 / (1 + 0.07 / 12) ** (12 * k) for k in range(1, 6))
        assert f.pv_at_operator_rate == pytest.approx(pv)
        assert f.subsidy_value == pytest.approx(300_000 - pv)
        assert f.better == "ask"

    def test_cash_in_lieu_compared(self):
        f = value_financing(Financing(apr=0, term_months=60, cash_in_lieu=80_000), 300_000, 7.0)
        assert f.better == "cash"  # subsidy ~$54k < $80k

    def test_waiver_defers_payments(self):
        no = value_financing(Financing(apr=6, term_months=60, payments_per_year=12), 300_000, 7.0)
        w = value_financing(Financing(apr=6, term_months=60, payments_per_year=12, waiver_months=6),
                            300_000, 7.0)
        assert w.payments == 54
        assert w.subsidy_value > no.subsidy_value

    def test_implied_trade_value(self):
        d = decompose(Quote("x", 800_000, 450_000, cash_price_no_trade=740_000), 400_000, 7.0)
        assert d.withheld_discount == 60_000
        assert d.implied_trade_value == 390_000

    def test_breakeven_is_exactly_indifferent(self):
        q = Quote("x", 800_000, 450_000)
        d = decompose(q, 380_000, 7.0)
        q2 = Quote("x", 800_000, 450_000, cash_price_no_trade=d.breakeven_cash_price)
        assert decompose(q2, 380_000, 7.0).implied_trade_value == pytest.approx(380_000)

    def test_cash_price_above_quote_rejected(self):
        with pytest.raises(DealError):
            Quote("x", 800_000, 450_000, cash_price_no_trade=810_000).validate()


# --------------------------------------------------------------------------- #
class TestRoutes:
    def test_commission_brackets(self):
        assert commission_pct(20_000, TERMS) == 6.0
        assert commission_pct(400_000, TERMS) == 3.0

    def test_consign_net_arithmetic(self):
        c = consign_net(400_000, TERMS, 7.0)
        expected = 400_000 - 12_000 - 750 - 0 - 400_000 * 0.07 * c.days_to_cash / 365
        assert c.net == pytest.approx(expected)

    def test_sd_excise_favors_trade(self):
        assert trade_tax_advantage("SD", 400_000) == pytest.approx(18_000)

    @pytest.mark.parametrize("st", ["IA", "IL", "NE", "MN", "MO", "WI", "KS", "IN"])
    def test_exempt_states(self, st):
        assert trade_tax_advantage(st, 400_000) == 0


# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def sample_inputs():
    return load_inputs(ROOT / "sample")


def run(sample_inputs, **quote):
    raw = copy.deepcopy(SAMPLE_DEAL)
    raw["dealer_quote"].update(quote)
    return analyze(raw, *sample_inputs)


class TestVerdicts:
    def test_need_cash_price_without_it(self, sample_inputs):
        a = run(sample_inputs)
        assert a.verdict == "need_cash_price"
        assert a.decomposition.breakeven_cash_price is not None

    def test_squeezed(self, sample_inputs):
        a = run(sample_inputs, cash_price_no_trade=690_000)
        assert a.verdict == "squeezed"
        assert a.spread["mid"] > 0

    def test_strong(self, sample_inputs):
        a = run(sample_inputs, cash_price_no_trade=805_000)
        assert a.verdict == "strong"

    def test_squeezed_without_cash_price_when_allowance_is_low(self, sample_inputs):
        a = run(sample_inputs, trade_allowance=250_000, quoted_price_with_trade=700_000)
        assert a.verdict == "squeezed" and a.certain

    def test_over_allowance_lower_bound(self, sample_inputs):
        a = run(sample_inputs)
        assert a.min_withheld_discount == pytest.approx(455_000 - a.dealer.ceiling_high)
        assert a.dealer.ceiling_high > a.dealer.ceiling

    def test_sd_operator_counts_excise(self, sample_inputs):
        raw = copy.deepcopy(SAMPLE_DEAL)
        raw["dealer_quote"]["cash_price_no_trade"] = 740_000
        raw["operator"]["state"] = "SD"
        a = analyze(raw, *sample_inputs)
        assert a.tax_advantage_trade == pytest.approx(0.045 * a.decomposition.implied_trade_value)

    def test_unknown_machine_needs_category(self, sample_inputs):
        raw = copy.deepcopy(SAMPLE_DEAL)
        raw["trade_unit"].update({"category": "", "make": "Acme", "model": "Z1"})
        with pytest.raises(DealError, match="category"):
            analyze(raw, *sample_inputs)


class TestReports:
    @pytest.mark.parametrize("quote", [
        {}, {"cash_price_no_trade": 690_000}, {"cash_price_no_trade": 805_000},
        {"cash_price_no_trade": 740_000, "financing": None, "list_price": None,
         "other_charges": [], "trade_payoff": 120_000},
        {"financing": {"apr": 1.9, "term_months": 48, "payments_per_year": 12,
                       "waiver_months": 6, "cash_in_lieu": 25_000}},
    ])
    def test_reports_render_cleanly(self, sample_inputs, quote):
        a = run(sample_inputs, **quote)
        for text in (operator_report(a, "t"), desk_sheet(a, "t")):
            assert not re.search(r"\bNone\b|\bnan\b|\binf\b", text), text
            assert "not tax advice" in text or "Internal" in text

    def test_report_names_the_one_question(self, sample_inputs):
        text = operator_report(run(sample_inputs), "t")
        assert "cash price" in text and "if I don't trade anything in" in text


class TestCli:
    def test_end_to_end(self, tmp_path):
        import shutil
        shutil.copytree(ROOT / "sample", tmp_path / "s")
        import trade_in_check
        assert trade_in_check.main([str(tmp_path / "s")]) == 0
        assert (tmp_path / "s" / "trade_in_report.md").stat().st_size > 2000
        assert (tmp_path / "s" / "mia_desk_sheet.md").exists()

    def test_missing_deal_exit_1(self, tmp_path):
        import trade_in_check
        assert trade_in_check.main([str(tmp_path)]) == 1

    def test_bad_deal_exit_1(self, tmp_path):
        (tmp_path / "trade_deal.json").write_text(json.dumps({"trade_unit": {}}))
        import trade_in_check
        assert trade_in_check.main([str(tmp_path)]) == 1


# --------------------------------------------------------------------------- #
# Regression tests for defects found in adversarial review.
class TestReviewRegressions:
    def test_newer_unit_is_worth_more(self, sample_inputs):
        comps, _ = sample_inputs
        vals = [value_unit(unit(year=y, hours=2050), comps, AS_OF).mid for y in (2019, 2021, 2023)]
        assert vals[0] < vals[1] < vals[2]

    def test_single_older_comp_adjusts_up(self):
        v = value_unit(unit(year=2022), comps_frame([{"Price": 100_000, "Year": 2020}]), AS_OF)
        assert v.mid == pytest.approx(100_000 / 0.93 ** 2)

    def test_more_hours_worth_less(self):
        df = comps_frame([{"Price": 100_000, "Hours": 2000}])
        assert value_unit(unit(hours=3000), df, AS_OF).mid < value_unit(unit(hours=1000), df, AS_OF).mid

    def test_negative_breakeven_is_squeezed_not_unknown(self, sample_inputs):
        a = run(sample_inputs, trade_allowance=340_000)
        assert a.breakeven["mid"] <= 0
        assert a.verdict == "squeezed"
        text = operator_report(a, "t")
        assert "off this quote), the trade" not in text  # no impossible break-even line
        bottom = text[text.index("## Bottom line"):text.index("## The dealer deal")]
        assert not re.search(r"-\d+\.\d%", bottom)

    def test_cash_due_includes_payoff_and_charges(self, sample_inputs):
        a = run(sample_inputs, trade_payoff=150_000)
        d = a.decomposition
        assert d.cash_due == pytest.approx(812_000 - 455_000 + 150_000 + 4_800)
        assert d.financing.amount_financed == pytest.approx(d.cash_due)

    def test_allowance_at_or_above_quote_with_financing_does_not_crash(self, sample_inputs):
        a = run(sample_inputs, trade_allowance=812_000, other_charges=[])
        assert a.decomposition.financing is None

    def test_waiver_changes_value_with_annual_payments(self):
        base = value_financing(Financing(apr=3.9, term_months=60, payments_per_year=1), 300_000, 7.0)
        w = value_financing(Financing(apr=3.9, term_months=66, payments_per_year=1, waiver_months=6),
                            300_000, 7.0)
        assert w.subsidy_value > base.subsidy_value

    def test_uneven_term_rejected(self):
        with pytest.raises(DealError, match="divide"):
            value_financing(Financing(apr=3.9, term_months=18, payments_per_year=1), 300_000, 7.0)

    def test_zero_borrow_rate_respected(self, sample_inputs):
        raw = copy.deepcopy(SAMPLE_DEAL)
        raw["operator"]["borrow_apr"] = 0
        assert analyze(raw, *sample_inputs).operator.borrow_apr == 0

    def test_uncalibrated_sandhills_only_is_low_confidence(self):
        from tradein.mia import Calibration
        cal = Calibration({}, None, 0, 0, {})
        v = value_unit(unit(category=cats.SPRAYER, make="Hagie", model="STS16",
                            sandhills_vip={"auction": 200_000}), None, AS_OF, cal)
        assert v.confidence == "Low"

    def test_planter_comps_with_blank_hours_load(self):
        raw = pd.DataFrame([{"Make": "John Deere", "Model": "DB60", "Year": "2020", "Hours": "",
                             "Price": "170000", "PriceBasis": "hammer", "SaleDate": "2026-08-01"}] * 2)
        df = normalize(raw)
        assert len(df) == 2 and (df["Hours"] == 0).all()

    def test_planter_trade_without_hours(self, sample_inputs):
        raw = copy.deepcopy(SAMPLE_DEAL)
        raw["trade_unit"] = {"make": "John Deere", "model": "DB60", "year": 2020}
        a = analyze(raw, *sample_inputs)
        assert a.unit.hours == 0 and a.unit.category == cats.PLANTER

    def test_edge_wording_matches_sign(self, sample_inputs):
        for cash in (690_000, 760_000, 805_000):
            a = run(sample_inputs, cash_price_no_trade=cash)
            text = operator_report(a, "t")
            assert "close to even" not in text

    def test_cpa_section_is_framed_as_question(self, sample_inputs):
        text = operator_report(run(sample_inputs), "t")
        assert "treated as sold" not in text and "Ask your CPA" in text
