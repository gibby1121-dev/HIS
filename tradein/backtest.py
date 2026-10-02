"""Leave-one-out backtests: how good are the numbers, measured on real sales?

Run against MIA's own data before trusting the engine with an operator:

    python3 -m tradein.backtest FOLDER

* **Comps model:** each realized sale is predicted from all the *other*
  sales (as if it were the trade unit), then compared with its actual
  hammer. Reports median absolute % error and how often the actual landed
  inside the predicted low–high range.
* **Sandhills calibration:** each MIA lot is predicted as Sandhills
  estimate × the category ratio learned from the *other* lots, compared with
  the raw Sandhills estimate. If calibration doesn't beat raw Sandhills on
  held-out lots, it shouldn't be used.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .mia import calibrate
from .valuation import Unit, ValuationError, value_unit


@dataclass
class BacktestResult:
    n: int
    median_abs_pct_err: float
    within_range_pct: float
    rows: pd.DataFrame


def backtest_comps(comps: pd.DataFrame, min_pool: int = 3) -> BacktestResult | None:
    sold = comps[comps["Hammer"].notna()].reset_index(drop=True)
    out = []
    for i, r in sold.iterrows():
        rest = comps.drop(index=comps.index[(comps["Hammer"].notna())][i])
        pool = rest[(rest["Category"] == r["Category"]) & rest["Hammer"].notna()]
        if len(pool) < min_pool:
            continue
        unit = Unit(r["Category"], r["Make"], r["Model"], int(r["Year"]), float(r["Hours"]))
        try:
            v = value_unit(unit, rest, r["SaleDate"].date())
        except ValuationError:
            continue
        out.append({"Unit": f"{int(r['Year'])} {r['Make']} {r['Model']}",
                    "Actual": r["Hammer"], "Predicted": v.mid, "Low": v.low, "High": v.high,
                    "AbsPctErr": abs(v.mid / r["Hammer"] - 1) * 100,
                    "InRange": v.low <= r["Hammer"] <= v.high})
    if not out:
        return None
    df = pd.DataFrame(out)
    return BacktestResult(len(df), float(df["AbsPctErr"].median()),
                          float(df["InRange"].mean() * 100), df)


def backtest_calibration(lots: pd.DataFrame, min_estimate: float = 25_000) -> pd.DataFrame | None:
    use = lots[lots["AuctionValue"].fillna(0).ge(min_estimate) & lots["Hammer"].fillna(0).gt(0)]
    use = use.reset_index(drop=True)
    rows = []
    for i, r in use.iterrows():
        cal = calibrate(use.drop(index=i), min_estimate)
        c = cal.for_category(r["Category"])
        if c is None:
            continue
        pred = r["AuctionValue"] * c.applied_ratio
        rows.append({"Category": r["Category"], "Actual": r["Hammer"],
                     "RawErrPct": abs(r["AuctionValue"] / r["Hammer"] - 1) * 100,
                     "CalibratedErrPct": abs(pred / r["Hammer"] - 1) * 100})
    return pd.DataFrame(rows) if rows else None


def main(argv: list[str] | None = None) -> int:
    from .analyze import load_inputs
    from .mia import load_auction_history
    argv = argv if argv is not None else sys.argv[1:]
    folder = Path(argv[0] if argv else ".")
    comps, _ = load_inputs(folder)
    if comps is not None:
        r = backtest_comps(comps)
        if r:
            print(f"Comps model, leave-one-out on {r.n} sales: median error "
                  f"{r.median_abs_pct_err:.1f}%, actual inside predicted range "
                  f"{r.within_range_pct:.0f}% of the time.")
    res = folder / "mia_results"
    if res.is_dir() and any(res.glob("*Auction Summary*.xlsx")):
        b = backtest_calibration(load_auction_history(res))
        if b is not None:
            print(f"Sandhills estimate vs MIA hammer, {len(b)} held-out lots: raw median error "
                  f"{b['RawErrPct'].median():.1f}%, calibrated {b['CalibratedErrPct'].median():.1f}%.")
            for cat, g in b.groupby("Category"):
                print(f"  {cat:24s} n={len(g):3d}  raw {g['RawErrPct'].median():5.1f}%  "
                      f"calibrated {g['CalibratedErrPct'].median():5.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
