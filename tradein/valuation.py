"""Open-market value of the trade unit, on a hammer (seller-gross) basis.

Two independent anchors, reported side by side and then blended:

1. **Comps** — realized sales of the same category, adjusted to the trade
   unit's year and hours and weighted by similarity and recency. When there
   are enough sales the year/hours adjustment rates are *fitted from the
   comps* (log-linear least squares); otherwise documented defaults are used
   and the report says so.
2. **Sandhills VIP+ × MIA calibration** — the Sandhills auction estimate for
   this unit, scaled by how MIA's own hammer prices have actually landed
   against Sandhills estimates in that category.

When the anchors disagree by more than ``DISAGREE_PCT`` the report flags it:
that's a unit somebody needs to look at, not a number to quote.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .mia import Calibration

DEFAULT_DEP_PER_YEAR = 0.07
DEFAULT_PER_1000_HRS = 0.04
DEP_BOUNDS = (0.02, 0.15)
HRS_BOUNDS = (0.0, 0.12)
MIN_FIT_SALES = 8
RECENCY_HALF_LIFE_DAYS = 180
MAX_COMP_AGE_DAYS = 730
DISAGREE_PCT = 15.0
# Range = 10th-90th weighted percentile of adjusted comps. An interquartile
# range covered only ~55% of held-out sales in backtest: too narrow to call
# "likely".
RANGE_Q = (0.10, 0.90)


class ValuationError(ValueError):
    pass


@dataclass
class Unit:
    category: str
    make: str
    model: str
    year: int
    hours: float
    serial: str = ""
    config: str = ""
    sandhills_vip: dict = field(default_factory=dict)  # auction/wholesale/market/asking


@dataclass
class Anchor:
    name: str
    low: float
    mid: float
    high: float
    detail: str


@dataclass
class Valuation:
    low: float
    mid: float
    high: float
    confidence: str
    anchors: list[Anchor]
    comps: pd.DataFrame          # used sold comps with AdjustedHammer, Weight
    asking: pd.DataFrame         # similar asking listings (context only)
    dep_per_year: float
    per_1000_hrs: float
    rates_fitted: bool
    flags: list[str]

    @property
    def asking_gap_pct(self) -> float | None:
        """How far similar units' asking prices sit above our hammer mid."""
        if self.asking.empty or self.mid <= 0:
            return None
        return (float(self.asking["AdjustedAsking"].median()) / self.mid - 1) * 100


def weighted_quantile(values, weights, q: float) -> float:
    pairs = sorted(zip(values, weights))
    vals = [v for v, _ in pairs]
    wts = [w for _, w in pairs]
    total = sum(wts)
    if total <= 0:
        raise ValueError("weights must sum to a positive number")
    cum, pos = 0.0, []
    for w in wts:
        pos.append((cum + w / 2) / total)
        cum += w
    if q <= pos[0]:
        return vals[0]
    if q >= pos[-1]:
        return vals[-1]
    for i in range(1, len(vals)):
        if q <= pos[i]:
            span = pos[i] - pos[i - 1]
            frac = (q - pos[i - 1]) / span if span else 0.0
            return vals[i - 1] + frac * (vals[i] - vals[i - 1])
    return vals[-1]  # pragma: no cover


def _norm(s) -> str:
    return " ".join(str(s).lower().split())


def fit_rates(sold: pd.DataFrame) -> tuple[float, float, bool]:
    """Fit per-year and per-1000-hour value change from the comps.

    log(price) = a + b·year + c·hours + model fixed effects. Returns
    (depreciation per year, loss per 1,000 hrs, fitted?). Falls back to
    defaults when the sample is small or the fit is implausible.
    """
    if len(sold) < MIN_FIT_SALES or sold["Year"].nunique() < 2:
        return DEFAULT_DEP_PER_YEAR, DEFAULT_PER_1000_HRS, False
    y = np.log(sold["Hammer"].to_numpy(dtype=float))
    models = pd.get_dummies(sold["Model"].map(_norm), drop_first=True, dtype=float)
    X = np.column_stack([
        np.ones(len(sold)),
        sold["Year"].to_numpy(dtype=float),
        sold["Hours"].to_numpy(dtype=float) / 1000.0,
        models.to_numpy() if models.shape[1] else np.empty((len(sold), 0)),
    ])
    if np.linalg.matrix_rank(X) < X.shape[1]:
        X = X[:, :3]
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    dep = 1 - math.exp(-coef[1])           # value lost per year older
    per_khr = 1 - math.exp(coef[2])        # value lost per 1,000 extra hours
    if not (DEP_BOUNDS[0] <= dep <= DEP_BOUNDS[1]) or not (
        HRS_BOUNDS[0] <= per_khr <= HRS_BOUNDS[1]
    ):
        return DEFAULT_DEP_PER_YEAR, DEFAULT_PER_1000_HRS, False
    return dep, per_khr, True


def _adjust(price: pd.Series, year: pd.Series, hours: pd.Series, unit: Unit,
            dep: float, per_khr: float) -> pd.Series:
    year_f = (1 - dep) ** (unit.year - year)
    hrs_f = ((1 - per_khr) ** ((unit.hours - hours) / 1000.0))
    return price * year_f * hrs_f


MIN_CONFORMAL_SALES = 8
CONFORMAL_COVERAGE = 0.80


def _loo_halfwidth(sold: pd.DataFrame, as_of: dt.date) -> tuple[float, int] | None:
    """80th-percentile leave-one-out % error over this comp pool.

    Each sale is valued from the others exactly as the trade unit is; the
    error distribution sizes the reported range so its stated coverage is
    measured, not assumed.
    """
    if len(sold) < MIN_CONFORMAL_SALES:
        return None
    errs = []
    for idx in sold.index:
        r = sold.loc[idx]
        u = Unit(r["Category"], r["Make"], r["Model"], int(r["Year"]), float(r["Hours"]))
        a = _comps_anchor(u, sold.drop(index=idx), as_of, conformal=False)[0]
        if a:
            errs.append(abs(a.mid / r["Hammer"] - 1))
    if len(errs) < MIN_CONFORMAL_SALES - 1:
        return None
    return float(np.quantile(errs, CONFORMAL_COVERAGE)), len(errs)


def _comps_anchor(unit: Unit, comps: pd.DataFrame, as_of: dt.date, conformal: bool = True):
    same_cat = comps[comps["Category"] == unit.category].copy()
    age = (pd.Timestamp(as_of) - same_cat["SaleDate"]).dt.days
    same_cat = same_cat[(age >= 0) & (age <= MAX_COMP_AGE_DAYS)]
    same_cat["AgeDays"] = (pd.Timestamp(as_of) - same_cat["SaleDate"]).dt.days
    sold = same_cat[same_cat["Hammer"].notna()].copy()
    ask = same_cat[same_cat["PriceBasis"] == "asking"].copy()
    if sold.empty:
        return None, sold, ask, DEFAULT_DEP_PER_YEAR, DEFAULT_PER_1000_HRS, False

    dep, per_khr, fitted = fit_rates(sold)
    sold["AdjustedHammer"] = _adjust(sold["Hammer"], sold["Year"], sold["Hours"], unit, dep, per_khr)
    if not ask.empty:
        ask["AdjustedAsking"] = _adjust(ask["Price"], ask["Year"], ask["Hours"], unit, dep, per_khr)

    same_make = sold["Make"].map(_norm) == _norm(unit.make)
    same_model = same_make & (sold["Model"].map(_norm) == _norm(unit.model))
    w_mm = same_model * 1.0 + (same_make & ~same_model) * 0.5 + (~same_make) * 0.25
    w_year = 1.0 / (1.0 + (sold["Year"] - unit.year).abs() / 2.0)
    w_hrs = 1.0 / (1.0 + (sold["Hours"] - unit.hours).abs() / 1500.0)
    w_rec = 0.5 ** (sold["AgeDays"] / RECENCY_HALF_LIFE_DAYS)
    sold["Weight"] = w_mm * w_year * w_hrs * w_rec
    sold["ModelMatch"] = same_model

    vals, wts = sold["AdjustedHammer"].tolist(), sold["Weight"].tolist()
    mid = weighted_quantile(vals, wts, 0.5)
    low = weighted_quantile(vals, wts, RANGE_Q[0])
    high = weighted_quantile(vals, wts, RANGE_Q[1])
    eff_n = sum(wts) ** 2 / sum(w * w for w in wts)
    near = int((same_model & ((sold["Year"] - unit.year).abs() <= 2)).sum())
    if near >= 4 and eff_n >= 4:
        conf = "High"
    elif int(same_model.sum()) >= 2 and eff_n >= 2.5:
        conf = "Medium"
    else:
        conf = "Low"
        low, high = min(low, mid * 0.88), max(high, mid * 1.12)
    range_note = "10th–90th percentile of adjusted sales"
    if conformal:
        hw = _loo_halfwidth(sold.drop(columns=["AdjustedHammer", "Weight", "ModelMatch"]), as_of)
        if hw:
            q, n_bt = hw
            low, high = min(low, mid * (1 - q)), max(high, mid * (1 + q))
            range_note = (f"range sized so {CONFORMAL_COVERAGE:.0%} of {n_bt} held-out sales "
                          f"fell within ±{q:.0%} of their predicted value")
    sold = sold.sort_values("Weight", ascending=False).reset_index(drop=True)
    anchor = Anchor(
        "Comparable sales", low, mid, high,
        f"{len(sold)} realized sales ({int(same_model.sum())} same model), "
        f"effective sample {eff_n:.1f}, {conf.lower()} confidence; {range_note}",
    )
    anchor.confidence = conf  # type: ignore[attr-defined]
    return anchor, sold, ask, dep, per_khr, fitted


def _vip_anchor(unit: Unit, cal: Calibration | None) -> Anchor | None:
    vip = (unit.sandhills_vip or {}).get("auction")
    if not vip:
        return None
    c = cal.for_category(unit.category) if cal else None
    if c is None:
        why = ("no MIA sale history loaded" if cal is None else
               "MIA history doesn't yet show calibration beating raw Sandhills for "
               f"{unit.category.lower()}s on held-out lots")
        return Anchor("Sandhills VIP+ auction value (uncalibrated)",
                      vip * 0.9, vip, vip * 1.1, f"{why.capitalize()}; ±10% shown, not measured")
    # Center on the shrunk ratio; spread by the observed interquartile range.
    spread_lo = c.median_ratio - c.p25_ratio
    spread_hi = c.p75_ratio - c.median_ratio
    mid = vip * c.applied_ratio
    return Anchor(
        "Sandhills VIP+ × MIA results",
        vip * (c.applied_ratio - spread_lo), mid, vip * (c.applied_ratio + spread_hi),
        f"VIP+ auction ${vip:,.0f}; MIA hammer ran {c.median_ratio:.0%} of Sandhills "
        f"estimate across {c.lots} {c.category.lower()} lots "
        f"(middle half {c.p25_ratio:.0%}–{c.p75_ratio:.0%}); applied {c.applied_ratio:.0%}. "
        f"Held-out check: {cal.validation[unit.category][1]:.1f}% median error vs "
        f"{cal.validation[unit.category][0]:.1f}% raw Sandhills",
    )


def value_unit(unit: Unit, comps: pd.DataFrame | None, as_of: dt.date,
               calibration: Calibration | None = None) -> Valuation:
    flags: list[str] = []
    empty = pd.DataFrame()
    comps_anchor, sold, ask, dep, per_khr, fitted = (None, empty, empty,
                                                     DEFAULT_DEP_PER_YEAR,
                                                     DEFAULT_PER_1000_HRS, False)
    if comps is not None and len(comps):
        comps_anchor, sold, ask, dep, per_khr, fitted = _comps_anchor(unit, comps, as_of)
    vip_anchor = _vip_anchor(unit, calibration)

    anchors = [a for a in (comps_anchor, vip_anchor) if a]
    if not anchors:
        raise ValuationError(
            f"No realized sales for '{unit.category}' in the last "
            f"{MAX_COMP_AGE_DAYS} days and no Sandhills VIP+ value for the unit. "
            "Add hammer-basis comps or the VIP+ auction value."
        )

    if comps_anchor and vip_anchor:
        conf = getattr(comps_anchor, "confidence", "Low")
        w_comps = {"High": 0.6, "Medium": 0.5, "Low": 0.3}[conf]
        mid = w_comps * comps_anchor.mid + (1 - w_comps) * vip_anchor.mid
        low = min(comps_anchor.low, vip_anchor.low)
        high = max(comps_anchor.high, vip_anchor.high)
        gap = abs(comps_anchor.mid / vip_anchor.mid - 1) * 100
        if gap > DISAGREE_PCT:
            flags.append(
                f"Comps and the calibrated Sandhills value disagree by {gap:.0f}%. "
                "Check configuration and condition in person before quoting a number."
            )
            confidence = "Low"
        else:
            confidence = "High" if conf == "High" else "Medium"
    else:
        only = anchors[0]
        low, mid, high = only.low, only.mid, only.high
        confidence = getattr(only, "confidence", "Medium" if vip_anchor and calibration else "Low")

    if not fitted and len(sold):
        flags.append(
            f"Year/hours adjustments use defaults ({dep:.0%}/model year, "
            f"{per_khr:.0%}/1,000 hrs): too few sales to fit them."
        )
    return Valuation(low, mid, high, confidence, anchors, sold, ask, dep, per_khr, fitted, flags)
