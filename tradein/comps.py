"""Comparable sales: loading and price-basis normalization.

The single most common error in comparing a dealer trade number with "the
market" is mixing price bases:

* **asking** — a retail listing price. Sandhills' EVI spread (asking over
  auction) ran 31–40% for 100+ HP tractors and combines through 2026.
  Asking prices are never used to value the trade; they are reported
  separately so the operator can see why "it's listed for $X online" is not
  what the unit brings.
* **with_bp** — an auction price that includes the buyer's premium (e.g.
  Purple Wave's "contract price" is bid + premium). The seller never
  receives the premium, so it is removed using the row's
  ``BuyerPremiumPct`` and optional per-lot ``BuyerPremiumCap``.
* **hammer** — the auction hammer price. This is the seller's gross and the
  basis every valuation in this package works in.

Every comp row must declare its ``PriceBasis``; there is no silent default.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .categories import OTHER, classify, normalize_category

REQUIRED_COLS = {"Make", "Model", "Year", "Hours", "Price", "SaleDate", "PriceBasis"}
BASES = {"hammer", "with_bp", "asking"}


class CompsError(ValueError):
    pass


def load_comps(path: Path) -> pd.DataFrame:
    if not Path(path).exists():
        raise CompsError(f"Comps file '{path}' was not found.")
    try:
        raw = pd.read_csv(path, dtype=str)
    except Exception as exc:  # pandas parse errors vary
        raise CompsError(f"Could not parse comps file '{path}': {exc}") from exc
    if raw.empty:
        raise CompsError(f"Comps file '{path}' has no rows.")
    missing = REQUIRED_COLS - set(raw.columns)
    if missing:
        raise CompsError(
            f"Comps file '{path}' is missing column(s): {', '.join(sorted(missing))}. "
            f"Required: {', '.join(sorted(REQUIRED_COLS))}."
        )
    return normalize(raw)


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(r"[$,%\s]", "", regex=True), errors="coerce"
    )


def normalize(raw: pd.DataFrame) -> pd.DataFrame:
    """Return comps with a ``Hammer`` column (seller-gross basis).

    Asking rows are kept (``Hammer`` is NaN) so they can be reported, but
    they are excluded from valuation.
    """
    df = raw.copy()
    for col in ("Make", "Model"):
        df[col] = df[col].fillna("").astype(str).str.strip()
    df["Year"] = _num(df["Year"])
    df["Hours"] = _num(df["Hours"])
    df["Price"] = _num(df["Price"])
    df["SaleDate"] = pd.to_datetime(df["SaleDate"], errors="coerce")
    df["PriceBasis"] = df["PriceBasis"].fillna("").str.strip().str.lower()

    bad_basis = sorted(set(df["PriceBasis"]) - BASES)
    if bad_basis:
        raise CompsError(
            f"Unknown PriceBasis value(s): {', '.join(repr(b) for b in bad_basis)}. "
            f"Use one of: {', '.join(sorted(BASES))}."
        )

    bp = _num(df["BuyerPremiumPct"]) if "BuyerPremiumPct" in df.columns else pd.Series(
        float("nan"), index=df.index
    )
    needs_bp = (df["PriceBasis"] == "with_bp") & bp.isna()
    if needs_bp.any():
        rows = ", ".join(str(i + 2) for i in df.index[needs_bp][:10])
        raise CompsError(
            "Comps priced 'with_bp' need BuyerPremiumPct so the premium can be "
            f"removed (CSV line(s) {rows}). Premiums differ by auction house; "
            "they are not guessed."
        )
    df["BuyerPremiumPct"] = bp

    cap = _num(df["BuyerPremiumCap"]) if "BuyerPremiumCap" in df.columns else pd.Series(
        float("nan"), index=df.index
    )
    df["BuyerPremiumCap"] = cap
    hammer = df["Price"].where(df["PriceBasis"] == "hammer")
    with_bp = df["PriceBasis"] == "with_bp"
    stripped = [
        strip_premium(p, b, c) if w else h
        for p, b, c, w, h in zip(df["Price"], bp, cap, with_bp, hammer)
    ]
    df["Hammer"] = pd.Series(stripped, index=df.index, dtype=float)

    if "Category" in df.columns:
        cat = df["Category"].map(normalize_category)
    else:
        cat = pd.Series(OTHER, index=df.index)
    inferred = [classify(mk, md) for mk, md in zip(df["Make"], df["Model"])]
    df["Category"] = [c if c != OTHER else i for c, i in zip(cat, inferred)]

    df = df.dropna(subset=["Year", "Hours", "Price", "SaleDate"])
    df = df[df["Price"] > 0]
    return df.reset_index(drop=True)


def strip_premium(total: float, bp_pct: float, cap: float | None = None) -> float:
    """Hammer price from a buyer's-premium-inclusive total.

    Premium = min(hammer × bp_pct, cap). Caps matter more than the headline
    rate on big iron: a 10% premium capped at $4,125 on a $450k tractor is
    under 1%, uncapped it is $45,000.
    """
    if pd.isna(total):
        return float("nan")
    rate = bp_pct / 100.0
    uncapped = total / (1 + rate)
    if cap is None or pd.isna(cap) or uncapped * rate <= cap:
        return uncapped
    return total - cap


def sold(df: pd.DataFrame) -> pd.DataFrame:
    """Realized sales only (hammer basis)."""
    return df[df["Hammer"].notna()].copy()


def asking(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["PriceBasis"] == "asking"].copy()
