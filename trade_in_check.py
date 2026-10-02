#!/usr/bin/env python3
"""
Trade-In Check — unbundle a dealer trade-in quote
=================================================

Wedge product for owner-sellers of large row-crop iron (4WD / high-HP
tractors, combines, planters, sprayers, grain carts) who are being offered a
trade-in on a new unit.

The dealer quotes a new-unit price *with* the trade and a trade allowance.
Because the two numbers are bundled, a generous-looking allowance can be paid
for by a thinner discount on the new unit. This tool:

1. **Unbundles the dealer deal.** Implied trade value =
   trade allowance − (quoted price with trade − cash price without trade).
   The cash price is used if the operator has it; otherwise it is estimated
   from an assumed dealer discount and clearly flagged.
2. **Values the trade on the open market** from comparable sales
   (``comps.csv``): each comp is adjusted to the subject's year and hours,
   weighted by similarity and recency, and summarised as a weighted median
   with a P25–P75 range and a confidence grade.
3. **Nets out the cost of selling it yourself**: commission, transport, prep,
   and the carrying cost of waiting for the sale.
4. **Compares the two routes** and reports the "trade-in spread": how much
   the operator gives up (or gains) by trading, plus a counter-offer target
   and the questions to put to the dealer.

Output is ``trade_in_report.md``, a seller-facing Markdown summary that can be
read as-is or dropped into NotebookLM / Claude as a source.

This is a decision aid, not an appraisal and not tax advice.

Usage
-----
    python3 trade_in_check.py                   # trade_deal.json + comps.csv here
    python3 trade_in_check.py path/to/folder    # inputs in another folder
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import pandas as pd
except ImportError:  # pragma: no cover - environment guard
    sys.stderr.write(
        "ERROR: pandas is not installed. Run 'pip install pandas' and retry.\n"
    )
    raise SystemExit(2)


# --------------------------------------------------------------------------- #
# Configuration                                                                #
# --------------------------------------------------------------------------- #
DEAL_JSON = "trade_deal.json"
COMPS_CSV = "comps.csv"
OUTPUT_MD = "trade_in_report.md"

REQUIRED_COMP_COLS = {
    "Category",
    "Make",
    "Model",
    "Year",
    "Hours",
    "SalePrice",
    "SaleDate",
}

# Default modelling assumptions. Every one can be overridden in the deal file's
# "assumptions" block and every one is printed in the report.
DEFAULT_ASSUMPTIONS = {
    # Typical discount off the quoted price a cash (no-trade) buyer could get.
    # Only used when the dealer's cash price is not supplied.
    "dealer_discount_pct": 8.0,
    # Cost of selling the trade unit yourself.
    "commission_pct": 5.0,
    "transport_cost": 2500.0,
    "prep_cost": 1500.0,
    "days_to_sell": 45,
    "annual_interest_pct": 8.0,
    # Comp adjustments: value change per model year and per 1,000 hours.
    "depreciation_per_year_pct": 7.0,
    "value_per_1000_hours_pct": 4.0,
    # Comp weighting.
    "recency_half_life_days": 180,
    "max_comp_age_days": 730,
}


class TradeCheckError(RuntimeError):
    """Raised when an input is missing, unreadable, or the wrong shape."""


# --------------------------------------------------------------------------- #
# Inputs                                                                       #
# --------------------------------------------------------------------------- #
@dataclass
class TradeUnit:
    category: str
    make: str
    model: str
    year: int
    hours: float
    description: str = ""


@dataclass
class DealerQuote:
    new_unit: str
    quoted_price: float  # new-unit price on the trade deal
    trade_allowance: float
    cash_price: float | None = None  # new-unit price with no trade, if known


@dataclass
class Deal:
    trade: TradeUnit
    quote: DealerQuote
    operator: str = ""
    as_of: _dt.date = field(default_factory=_dt.date.today)
    assumptions: dict = field(default_factory=lambda: dict(DEFAULT_ASSUMPTIONS))


def _require(obj: dict, key: str, where: str):
    if key not in obj or obj[key] in (None, ""):
        raise TradeCheckError(f"Deal file is missing '{where}.{key}'.")
    return obj[key]


def _number(value, where: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise TradeCheckError(f"'{where}' must be a number, got {value!r}.") from exc
    if math.isnan(out) or out < 0:
        raise TradeCheckError(f"'{where}' must be a non-negative number, got {value!r}.")
    return out


def parse_deal(raw: dict) -> Deal:
    """Validate a deal dict (as loaded from ``trade_deal.json``)."""
    t = _require(raw, "trade_unit", "deal")
    q = _require(raw, "dealer_quote", "deal")

    trade = TradeUnit(
        category=str(_require(t, "category", "trade_unit")).strip(),
        make=str(_require(t, "make", "trade_unit")).strip(),
        model=str(_require(t, "model", "trade_unit")).strip(),
        year=int(_number(_require(t, "year", "trade_unit"), "trade_unit.year")),
        hours=_number(_require(t, "hours", "trade_unit"), "trade_unit.hours"),
        description=str(t.get("description", "")).strip(),
    )

    cash = q.get("cash_price_no_trade")
    quote = DealerQuote(
        new_unit=str(q.get("new_unit", "new unit")).strip(),
        quoted_price=_number(
            _require(q, "quoted_price_with_trade", "dealer_quote"),
            "dealer_quote.quoted_price_with_trade",
        ),
        trade_allowance=_number(
            _require(q, "trade_allowance", "dealer_quote"),
            "dealer_quote.trade_allowance",
        ),
        cash_price=None
        if cash in (None, "")
        else _number(cash, "dealer_quote.cash_price_no_trade"),
    )
    if quote.cash_price is not None and quote.cash_price > quote.quoted_price:
        raise TradeCheckError(
            "dealer_quote.cash_price_no_trade is higher than the quoted price "
            "with trade; check the quote."
        )

    assumptions = dict(DEFAULT_ASSUMPTIONS)
    unknown = set(raw.get("assumptions", {})) - set(DEFAULT_ASSUMPTIONS)
    if unknown:
        raise TradeCheckError(
            f"Unknown assumption(s): {', '.join(sorted(unknown))}. "
            f"Valid keys: {', '.join(DEFAULT_ASSUMPTIONS)}."
        )
    for key, value in raw.get("assumptions", {}).items():
        assumptions[key] = _number(value, f"assumptions.{key}")

    as_of = raw.get("as_of")
    try:
        as_of_date = _dt.date.fromisoformat(as_of) if as_of else _dt.date.today()
    except ValueError as exc:
        raise TradeCheckError(f"'as_of' must be YYYY-MM-DD, got {as_of!r}.") from exc

    return Deal(
        trade=trade,
        quote=quote,
        operator=str(raw.get("operator", "")).strip(),
        as_of=as_of_date,
        assumptions=assumptions,
    )


def load_deal(path: Path) -> Deal:
    if not path.exists():
        raise TradeCheckError(f"Deal file '{path.name}' was not found in {path.parent}.")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TradeCheckError(f"Could not parse '{path.name}': {exc}") from exc
    return parse_deal(raw)


def load_comps(path: Path) -> "pd.DataFrame":
    if not path.exists():
        raise TradeCheckError(f"Comps file '{path.name}' was not found in {path.parent}.")
    try:
        comps = pd.read_csv(path)
    except Exception as exc:
        raise TradeCheckError(f"Could not parse '{path.name}': {exc}") from exc
    if comps.empty:
        raise TradeCheckError(f"Comps file '{path.name}' contains no data rows.")
    missing = REQUIRED_COMP_COLS - set(comps.columns)
    if missing:
        raise TradeCheckError(
            f"Comps file '{path.name}' is missing required column(s): "
            f"{', '.join(sorted(missing))}. Found: {', '.join(comps.columns)}."
        )
    return clean_comps(comps)


def clean_comps(comps: "pd.DataFrame") -> "pd.DataFrame":
    comps = comps.copy()
    for col in ("Category", "Make", "Model"):
        comps[col] = comps[col].astype(str).str.strip()
    for col in ("Year", "Hours", "SalePrice"):
        comps[col] = pd.to_numeric(comps[col], errors="coerce")
    comps["SaleDate"] = pd.to_datetime(comps["SaleDate"], errors="coerce")
    comps = comps.dropna(subset=["Year", "Hours", "SalePrice", "SaleDate"])
    return comps[comps["SalePrice"] > 0].reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Open-market valuation                                                        #
# --------------------------------------------------------------------------- #
@dataclass
class Valuation:
    low: float
    mid: float
    high: float
    comps: "pd.DataFrame"  # selected comps with AdjustedPrice and Weight
    model_matches: int
    effective_n: float
    confidence: str


def weighted_quantile(values, weights, q: float) -> float:
    """Weighted quantile using the midpoint-of-cumulative-weight convention."""
    pairs = sorted(zip(values, weights))
    vals = [v for v, _ in pairs]
    wts = [w for _, w in pairs]
    total = sum(wts)
    if total <= 0:
        raise ValueError("weights must sum to a positive number")
    cum, positions = 0.0, []
    for w in wts:
        positions.append((cum + w / 2) / total)
        cum += w
    if q <= positions[0]:
        return vals[0]
    if q >= positions[-1]:
        return vals[-1]
    for i in range(1, len(vals)):
        if q <= positions[i]:
            span = positions[i] - positions[i - 1]
            frac = (q - positions[i - 1]) / span if span else 0.0
            return vals[i - 1] + frac * (vals[i] - vals[i - 1])
    return vals[-1]  # pragma: no cover


def _norm(s: str) -> str:
    return " ".join(str(s).lower().split())


def value_trade(trade: TradeUnit, comps: "pd.DataFrame", as_of: _dt.date, a: dict) -> Valuation:
    """Adjust comparable sales to the trade unit and summarise them."""
    pool = comps[comps["Category"].map(_norm) == _norm(trade.category)].copy()
    age_days = (pd.Timestamp(as_of) - pool["SaleDate"]).dt.days
    pool = pool[(age_days >= 0) & (age_days <= a["max_comp_age_days"])].copy()
    if pool.empty:
        raise TradeCheckError(
            f"No comparable sales for category '{trade.category}' in the last "
            f"{int(a['max_comp_age_days'])} days. Add comps before running a check."
        )
    pool["AgeDays"] = (pd.Timestamp(as_of) - pool["SaleDate"]).dt.days

    # Adjust each comp's price to the subject's year and hours.
    dep = a["depreciation_per_year_pct"] / 100.0
    per_khr = a["value_per_1000_hours_pct"] / 100.0
    year_factor = (1 - dep) ** (pool["Year"] - trade.year)
    hours_factor = (1 + per_khr * (pool["Hours"] - trade.hours) / 1000.0).clip(lower=0.5)
    pool["AdjustedPrice"] = pool["SalePrice"] * year_factor * hours_factor

    # Similarity × recency weights.
    same_make = pool["Make"].map(_norm) == _norm(trade.make)
    same_model = same_make & (pool["Model"].map(_norm) == _norm(trade.model))
    w_make_model = same_model * 1.0 + (same_make & ~same_model) * 0.5 + (~same_make) * 0.25
    w_year = 1.0 / (1.0 + (pool["Year"] - trade.year).abs() / 2.0)
    w_hours = 1.0 / (1.0 + (pool["Hours"] - trade.hours).abs() / 1500.0)
    w_recency = 0.5 ** (pool["AgeDays"] / a["recency_half_life_days"])
    pool["Weight"] = w_make_model * w_year * w_hours * w_recency
    pool["ModelMatch"] = same_model

    vals, wts = pool["AdjustedPrice"].tolist(), pool["Weight"].tolist()
    mid = weighted_quantile(vals, wts, 0.5)
    low = weighted_quantile(vals, wts, 0.25)
    high = weighted_quantile(vals, wts, 0.75)

    effective_n = sum(wts) ** 2 / sum(w * w for w in wts)
    model_matches = int(same_model.sum())
    near_model = int((same_model & ((pool["Year"] - trade.year).abs() <= 2)).sum())
    if near_model >= 4 and effective_n >= 4:
        confidence = "High"
    elif model_matches >= 2 and effective_n >= 2.5:
        confidence = "Medium"
    else:
        confidence = "Low"
        # Thin comps: widen the range so the report doesn't overstate precision.
        low, high = min(low, mid * 0.88), max(high, mid * 1.12)

    pool = pool.sort_values("Weight", ascending=False).reset_index(drop=True)
    return Valuation(low, mid, high, pool, model_matches, effective_n, confidence)


# --------------------------------------------------------------------------- #
# Unbundle + compare                                                           #
# --------------------------------------------------------------------------- #
@dataclass
class Comparison:
    cash_price: float
    cash_price_estimated: bool
    hidden_discount: float  # quoted_price - cash_price
    implied_trade_value: float
    net_open_market: dict  # low / mid / high
    selling_costs_mid: dict
    spread: dict  # net_open_market - implied_trade_value (positive = dealer keeps it)
    trade_route_cost: float  # cash out of pocket if trading
    sell_route_cost: dict  # cash price - net open-market proceeds
    verdict: str
    counter_allowance: float
    counter_quoted_price: float  # new-unit price that makes trading break even


def selling_costs(gross: float, a: dict) -> dict:
    commission = gross * a["commission_pct"] / 100.0
    carrying = gross * a["annual_interest_pct"] / 100.0 * a["days_to_sell"] / 365.0
    costs = {
        "Commission": commission,
        "Transport": a["transport_cost"],
        "Prep / cleanup": a["prep_cost"],
        "Carrying cost while it sells": carrying,
    }
    costs["Total"] = sum(costs.values())
    return costs


def compare(deal: Deal, val: Valuation) -> Comparison:
    a, q = deal.assumptions, deal.quote
    if q.cash_price is not None:
        cash_price, estimated = q.cash_price, False
    else:
        cash_price, estimated = q.quoted_price * (1 - a["dealer_discount_pct"] / 100.0), True

    hidden_discount = q.quoted_price - cash_price
    implied = q.trade_allowance - hidden_discount

    net = {k: v - selling_costs(v, a)["Total"] for k, v in
           (("low", val.low), ("mid", val.mid), ("high", val.high))}
    spread = {k: net[k] - implied for k in net}

    # Material = more than 2% of the trade's open-market value or $5,000.
    threshold = max(5000.0, 0.02 * val.mid)
    if spread["low"] > threshold:
        verdict = "squeezed"
    elif spread["high"] < -threshold:
        verdict = "strong"
    else:
        verdict = "close"

    return Comparison(
        cash_price=cash_price,
        cash_price_estimated=estimated,
        hidden_discount=hidden_discount,
        implied_trade_value=implied,
        net_open_market=net,
        selling_costs_mid=selling_costs(val.mid, a),
        spread=spread,
        trade_route_cost=q.quoted_price - q.trade_allowance,
        sell_route_cost={k: cash_price - net[k] for k in net},
        verdict=verdict,
        counter_allowance=q.trade_allowance + max(spread["mid"], 0.0),
        counter_quoted_price=q.quoted_price - max(spread["mid"], 0.0),
    )


# --------------------------------------------------------------------------- #
# Report                                                                       #
# --------------------------------------------------------------------------- #
def _money(v: float) -> str:
    return f"-${-v:,.0f}" if v < 0 else f"${v:,.0f}"


VERDICT_TEXT = {
    "squeezed": (
        "🔴 **The trade is leaving money on the table.** Even at the low end of "
        "the open-market range, selling it yourself nets more than the dealer "
        "is really paying for it."
    ),
    "close": (
        "🟡 **The trade is in the fair range.** The gap between trading and "
        "selling is within the uncertainty of the comps — the convenience of "
        "trading may be worth it, but there's room to negotiate."
    ),
    "strong": (
        "🟢 **The dealer's trade offer is strong.** It beats what you'd likely "
        "net selling it yourself, even at the high end of the range."
    ),
}


def build_report(deal: Deal, val: Valuation, cmp: Comparison, generated_on: str) -> str:
    t, q, a = deal.trade, deal.quote, deal.assumptions
    unit = f"{t.year} {t.make} {t.model}"
    L: list[str] = []

    L.append(f"# Trade-In Check — {unit}")
    L.append("")
    who = f" for {deal.operator}" if deal.operator else ""
    L.append(
        f"_Prepared{who} on {generated_on}, using comps through "
        f"{deal.as_of.isoformat()}. Decision aid only: not an appraisal and "
        "not tax advice._"
    )
    L.append("")

    # ---- Bottom line ----------------------------------------------------
    L.append("## Bottom Line")
    L.append("")
    L.append(VERDICT_TEXT[cmp.verdict])
    L.append("")
    s = cmp.spread
    if s["mid"] >= 0:
        L.append(
            f"- **Trade-in spread: {_money(s['mid'])}** (range {_money(s['low'])} "
            f"to {_money(s['high'])}). That's roughly what the dealer keeps by "
            "taking your trade, compared with what you'd net selling it yourself."
        )
    else:
        L.append(
            f"- **Trade-in premium: {_money(-s['mid'])}** (spread range "
            f"{_money(s['low'])} to {_money(s['high'])}). The dealer is paying "
            "more for your trade than you'd likely net selling it yourself."
        )
    L.append(
        f"- The dealer's **{_money(q.trade_allowance)} allowance** is really worth "
        f"**{_money(cmp.implied_trade_value)}** once the "
        f"{'estimated ' if cmp.cash_price_estimated else ''}cash-price discount "
        f"you'd get without a trade ({_money(cmp.hidden_discount)}) is taken out."
    )
    L.append(
        f"- Open-market value of your {unit}: **{_money(val.mid)}** "
        f"(likely range {_money(val.low)}–{_money(val.high)}; "
        f"**{val.confidence} confidence**, {len(val.comps)} comps)."
    )
    L.append("")

    # ---- Unbundled dealer deal -----------------------------------------
    L.append("## The Dealer Deal, Unbundled")
    L.append("")
    L.append("| Line | Amount |")
    L.append("|---|---|")
    L.append(f"| Quoted price on {q.new_unit} (with trade) | {_money(q.quoted_price)} |")
    cp_label = "Estimated cash price, no trade" if cmp.cash_price_estimated else "Cash price, no trade"
    L.append(f"| {cp_label} | {_money(cmp.cash_price)} |")
    L.append(f"| Discount you'd get without a trade | {_money(cmp.hidden_discount)} |")
    L.append(f"| Trade allowance shown | {_money(q.trade_allowance)} |")
    L.append(f"| **Real (implied) trade value** | **{_money(cmp.implied_trade_value)}** |")
    L.append("")
    if cmp.cash_price_estimated:
        L.append(
            f"> The cash price is **estimated** using a {a['dealer_discount_pct']:.1f}% "
            "discount off the quote. Ask the dealer for a written cash price on "
            "the new unit without a trade — it's the single number that "
            "settles what your trade is really worth to them."
        )
        L.append("")

    # ---- Side by side ---------------------------------------------------
    L.append("## Trade vs. Sell It Yourself")
    L.append("")
    L.append("| | Trade with dealer | Sell yourself (low / mid / high) |")
    L.append("|---|---|---|")
    L.append(
        f"| New unit price | {_money(q.quoted_price)} | {_money(cmp.cash_price)} |"
    )
    n = cmp.net_open_market
    L.append(
        f"| Credit for your old unit | {_money(q.trade_allowance)} | "
        f"{_money(n['low'])} / {_money(n['mid'])} / {_money(n['high'])} (net) |"
    )
    sc = cmp.sell_route_cost
    L.append(
        f"| **Net cost to change units** | **{_money(cmp.trade_route_cost)}** | "
        f"**{_money(sc['low'])} / {_money(sc['mid'])} / {_money(sc['high'])}** |"
    )
    L.append("")
    L.append(
        "Selling yourself means doing the work and carrying the old unit until "
        "it sells. Trading buys you a single transaction and no gap between "
        "units. The spread above is what that convenience is costing you."
    )
    L.append("")

    L.append("### Cost of selling it yourself (at mid value)")
    L.append("")
    L.append("| Item | Amount |")
    L.append("|---|---|")
    for k, v in cmp.selling_costs_mid.items():
        label = f"**{k}**" if k == "Total" else k
        amt = f"**{_money(v)}**" if k == "Total" else _money(v)
        L.append(f"| {label} | {amt} |")
    L.append("")

    # ---- Negotiation ----------------------------------------------------
    L.append("## What to Take Back to the Dealer")
    L.append("")
    if cmp.verdict == "strong":
        L.append(
            "- The trade number holds up against the market. Focus negotiation "
            "on the new-unit price, warranty, and delivery terms instead."
        )
    else:
        L.append(
            f"- **Counter on the trade:** at the same {_money(q.quoted_price)} "
            f"quote, ask for a trade allowance of about "
            f"**{_money(cmp.counter_allowance)}**."
        )
        L.append(
            f"- **Or counter on the price:** keep the {_money(q.trade_allowance)} "
            f"allowance and ask for the new unit at about "
            f"**{_money(cmp.counter_quoted_price)}**."
        )
    L.append(
        "- Ask: *\"What's your cash price on the new unit if I don't trade?\"* "
        "and *\"What would you pay for my unit outright if I bought elsewhere?\"* "
        "Get both in writing."
    )
    L.append(
        "- Ask whether precision tech (receiver, display, activations) is "
        "included in the allowance. If not, it can be pulled and sold separately."
    )
    L.append("")

    # ---- Comps ----------------------------------------------------------
    L.append("## Comparable Sales Used")
    L.append("")
    L.append(
        f"{len(val.comps)} sales in the last {int(a['max_comp_age_days'])} days; "
        f"{val.model_matches} are the same make and model; effective sample size "
        f"{val.effective_n:.1f}. Each sale is adjusted to a {t.year} with "
        f"{t.hours:,.0f} hours; higher weight means a closer comp."
    )
    L.append("")
    L.append(
        "| Sale Date | Unit | Hours | Region | Sale Type | Sold For | "
        "Adjusted to Yours | Weight |"
    )
    L.append("|---|---|---|---|---|---|---|---|")
    total_w = val.comps["Weight"].sum()
    for _, r in val.comps.head(12).iterrows():
        L.append(
            f"| {r['SaleDate'].date().isoformat()} | "
            f"{int(r['Year'])} {r['Make']} {r['Model']} | {r['Hours']:,.0f} | "
            f"{r.get('Region', '—') if pd.notna(r.get('Region')) else '—'} | "
            f"{r.get('SaleType', '—') if pd.notna(r.get('SaleType')) else '—'} | "
            f"{_money(r['SalePrice'])} | {_money(r['AdjustedPrice'])} | "
            f"{r['Weight'] / total_w:.0%} |"
        )
    if len(val.comps) > 12:
        L.append(f"| … | {len(val.comps) - 12} lower-weight comps not shown | | | | | | |")
    L.append("")
    if val.confidence == "Low":
        L.append(
            "> **Low confidence:** there are few close comps for this unit, so "
            "the range has been widened. Treat the open-market value as a "
            "starting point and get a second opinion before acting on it."
        )
        L.append("")

    # ---- Assumptions & disclaimer --------------------------------------
    L.append("## Assumptions")
    L.append("")
    L.append(f"- Trade unit: {unit}, {t.hours:,.0f} hours"
             + (f" — {t.description}" if t.description else "") + ".")
    if cmp.cash_price_estimated:
        L.append(f"- Dealer cash discount (estimated): {a['dealer_discount_pct']:.1f}%.")
    L.append(f"- Selling commission: {a['commission_pct']:.1f}%; transport "
             f"{_money(a['transport_cost'])}; prep {_money(a['prep_cost'])}.")
    L.append(f"- Time to sell: {int(a['days_to_sell'])} days at "
             f"{a['annual_interest_pct']:.1f}% annual cost of money.")
    L.append(f"- Comp adjustments: {a['depreciation_per_year_pct']:.1f}% per model "
             f"year, {a['value_per_1000_hours_pct']:.1f}% per 1,000 hours.")
    L.append("")
    L.append(
        "_The tax effect of trading vs. selling (including depreciation "
        "recapture) is not modelled here. Take this summary to your CPA before "
        "you decide._"
    )
    L.append("")
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# Orchestration                                                                #
# --------------------------------------------------------------------------- #
def run(base_dir: Path) -> Path:
    deal = load_deal(base_dir / DEAL_JSON)
    comps = load_comps(base_dir / COMPS_CSV)
    val = value_trade(deal.trade, comps, deal.as_of, deal.assumptions)
    cmp = compare(deal, val)
    generated_on = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    out = base_dir / OUTPUT_MD
    out.write_text(build_report(deal, val, cmp, generated_on), encoding="utf-8")
    print(f"  [OK] Open-market value {_money(val.mid)} ({val.confidence} confidence, "
          f"{len(val.comps)} comps)")
    print(f"  [OK] Real trade value {_money(cmp.implied_trade_value)}; "
          f"trade-in spread {_money(cmp.spread['mid'])} -> {cmp.verdict}")
    print(f"  [OK] Wrote {out.name}")
    return out


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    base_dir = Path(argv[0]).resolve() if argv else Path(__file__).resolve().parent
    try:
        run(base_dir)
    except TradeCheckError as exc:
        sys.stderr.write(f"\n!! TRADE-IN CHECK HALTED: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
