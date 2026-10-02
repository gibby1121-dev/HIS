"""Tests for the Trade-In Check: unbundling math, comp valuation, verdicts,
and the loud-failure validation contract."""

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import trade_in_check as tic

AS_OF = "2026-09-30"


def _deal(**quote):
    q = {"new_unit": "New 9RX", "quoted_price_with_trade": 800_000, "trade_allowance": 450_000}
    q.update(quote)
    return {
        "as_of": AS_OF,
        "trade_unit": {
            "category": "4WD Tractor",
            "make": "John Deere",
            "model": "9RX 640",
            "year": 2021,
            "hours": 2000,
        },
        "dealer_quote": q,
        "assumptions": {"transport_cost": 0, "prep_cost": 0, "commission_pct": 0,
                        "annual_interest_pct": 0},
    }


def _comps(prices, model="9RX 640", year=2021, hours=2000, date="2026-08-01"):
    n = len(prices)
    return tic.clean_comps(pd.DataFrame({
        "Category": ["4WD Tractor"] * n,
        "Make": ["John Deere"] * n,
        "Model": [model] * n,
        "Year": [year] * n,
        "Hours": [hours] * n,
        "SalePrice": prices,
        "SaleDate": [date] * n,
    }))


class TestWeightedQuantile:
    def test_equal_weights_median(self):
        assert tic.weighted_quantile([1, 2, 3], [1, 1, 1], 0.5) == pytest.approx(2)

    def test_heavy_weight_pulls_median(self):
        assert tic.weighted_quantile([100, 200], [9, 1], 0.5) < 150

    def test_bounds_clamp_to_extremes(self):
        assert tic.weighted_quantile([5, 9], [1, 1], 0.0) == 5
        assert tic.weighted_quantile([5, 9], [1, 1], 1.0) == 9


class TestValuation:
    def test_identical_comps_value_at_their_price(self):
        deal = tic.parse_deal(_deal())
        val = tic.value_trade(deal.trade, _comps([500_000] * 5), deal.as_of, deal.assumptions)
        assert val.mid == pytest.approx(500_000)

    def test_older_comp_is_adjusted_up(self):
        deal = tic.parse_deal(_deal())
        val = tic.value_trade(deal.trade, _comps([400_000], year=2020), deal.as_of,
                              deal.assumptions)
        # One model year older at 7%/yr -> 400k / 0.93.
        assert val.mid == pytest.approx(400_000 / 0.93)

    def test_higher_hours_comp_is_adjusted_up(self):
        deal = tic.parse_deal(_deal())
        val = tic.value_trade(deal.trade, _comps([400_000], hours=3000), deal.as_of,
                              deal.assumptions)
        assert val.mid == pytest.approx(400_000 * 1.04)

    def test_thin_comps_are_low_confidence_with_wider_range(self):
        deal = tic.parse_deal(_deal())
        val = tic.value_trade(deal.trade, _comps([500_000]), deal.as_of, deal.assumptions)
        assert val.confidence == "Low"
        assert val.low < val.mid < val.high

    def test_many_close_comps_are_high_confidence(self):
        deal = tic.parse_deal(_deal())
        val = tic.value_trade(deal.trade, _comps([490_000, 500_000, 505_000, 510_000, 495_000]),
                              deal.as_of, deal.assumptions)
        assert val.confidence == "High"

    def test_same_model_outweighs_other_model(self):
        deal = tic.parse_deal(_deal())
        comps = pd.concat([_comps([500_000]), _comps([300_000], model="9R 540")])
        val = tic.value_trade(deal.trade, comps, deal.as_of, deal.assumptions)
        assert val.mid > 400_000

    def test_stale_and_wrong_category_comps_are_excluded(self):
        deal = tic.parse_deal(_deal())
        stale = _comps([100_000], date="2023-01-01")
        other = _comps([100_000]).assign(Category="Combine")
        with pytest.raises(tic.TradeCheckError, match="No comparable sales"):
            tic.value_trade(deal.trade, pd.concat([stale, other]), deal.as_of,
                            deal.assumptions)


class TestUnbundle:
    def _run(self, comp_price, **quote):
        deal = tic.parse_deal(_deal(**quote))
        val = tic.value_trade(deal.trade, _comps([comp_price] * 5), deal.as_of,
                              deal.assumptions)
        return tic.compare(deal, val)

    def test_implied_trade_value_uses_known_cash_price(self):
        cmp = self._run(500_000, cash_price_no_trade=740_000)
        # 450k allowance minus the 60k discount the dealer withheld.
        assert cmp.implied_trade_value == pytest.approx(390_000)
        assert not cmp.cash_price_estimated

    def test_cash_price_estimated_from_discount_when_missing(self):
        cmp = self._run(500_000)
        assert cmp.cash_price_estimated
        assert cmp.cash_price == pytest.approx(800_000 * 0.92)

    def test_squeezed_verdict_and_counters_break_even(self):
        cmp = self._run(500_000, cash_price_no_trade=740_000)
        assert cmp.verdict == "squeezed"
        assert cmp.spread["mid"] == pytest.approx(110_000)
        # Either counter makes the trade route cost equal the sell route cost.
        assert cmp.counter_allowance == pytest.approx(560_000)
        assert cmp.counter_quoted_price - 450_000 == pytest.approx(cmp.sell_route_cost["mid"])

    def test_strong_verdict_when_dealer_pays_over_market(self):
        cmp = self._run(350_000, cash_price_no_trade=800_000)
        assert cmp.verdict == "strong"

    def test_close_verdict_inside_noise(self):
        cmp = self._run(452_000, cash_price_no_trade=800_000)
        assert cmp.verdict == "close"

    def test_selling_costs_reduce_net(self):
        costs = tic.selling_costs(400_000, dict(tic.DEFAULT_ASSUMPTIONS))
        assert costs["Commission"] == pytest.approx(20_000)
        assert costs["Total"] > 20_000


class TestValidation:
    def test_missing_trade_field_raises(self):
        raw = _deal()
        del raw["trade_unit"]["model"]
        with pytest.raises(tic.TradeCheckError, match="trade_unit.model"):
            tic.parse_deal(raw)

    def test_cash_price_above_quote_raises(self):
        with pytest.raises(tic.TradeCheckError, match="higher than the quoted price"):
            tic.parse_deal(_deal(cash_price_no_trade=900_000))

    def test_unknown_assumption_raises(self):
        raw = _deal()
        raw["assumptions"]["comission_pct"] = 5
        with pytest.raises(tic.TradeCheckError, match="Unknown assumption"):
            tic.parse_deal(raw)

    def test_comps_missing_column_raises(self, tmp_path):
        p = tmp_path / "comps.csv"
        p.write_text("Category,Make,Model\n4WD Tractor,John Deere,9RX 640\n")
        with pytest.raises(tic.TradeCheckError, match="missing required column"):
            tic.load_comps(p)


class TestEndToEnd:
    def test_full_run_on_sample_data(self, tmp_path):
        repo = Path(__file__).resolve().parent.parent
        for name in (tic.DEAL_JSON, tic.COMPS_CSV):
            (tmp_path / name).write_text((repo / name).read_text())
        text = tic.run(tmp_path).read_text()
        assert "# Trade-In Check" in text
        assert "The Dealer Deal, Unbundled" in text
        assert "not tax advice" in text

    def test_main_returns_1_on_bad_input(self, tmp_path):
        (tmp_path / tic.DEAL_JSON).write_text(json.dumps(_deal()))
        assert tic.main([str(tmp_path)]) == 1  # comps.csv missing
