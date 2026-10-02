"""Orchestration: deal file -> Analysis."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import categories
from .comps import NO_ENGINE, load_comps
from .deal import Decomposition, DealError, Financing, Quote, decompose
from .mia import Calibration, load_auction_history
from .routes import (ConsignNet, DealerView, consign_net, dealer_view,
                     trade_tax_advantage)
from .tax import TaxFacts, facts as tax_facts
from .valuation import Unit, Valuation, value_unit

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DEFAULT_OPERATOR_APR = 7.0  # KC Fed: Q2-2026 farm loans >$100k averaged just under 7%


@dataclass
class Operator:
    name: str = ""
    state: str = "IA"
    borrow_apr: float = DEFAULT_OPERATOR_APR
    old_unit_adjusted_basis: float | None = None


@dataclass
class Analysis:
    unit: Unit
    quote: Quote
    operator: Operator
    as_of: dt.date
    valuation: Valuation
    consign: dict[str, ConsignNet]          # low / mid / high hammer
    decomposition: Decomposition
    dealer: DealerView
    tax_advantage_trade: float | None       # SD-style excise saved by trading
    tax: TaxFacts
    verdict: str                            # squeezed | close | strong | need_cash_price
    certain: bool                           # holds across the whole value range
    spread: dict[str, float] | None         # consign net − implied trade value (± tax)
    breakeven: dict[str, float] | None      # no-trade discount % at low/mid/high
    market_facts: list[dict]
    terms: dict
    warnings: list[str] = field(default_factory=list)

    @property
    def min_withheld_discount(self) -> float:
        """Allowance above what a dealer can pay even at the thin ~3.7% used
        margin dealers have actually averaged: an estimated lower bound on the
        over-allowance (still rests on recon/floorplan assumptions)."""
        return max(0.0, self.quote.trade_allowance - self.dealer.ceiling_high)


def _num(v, where):
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", "").replace("$", ""))
    except ValueError as exc:
        raise DealError(f"'{where}' must be a number, got {v!r}.") from exc


def parse(raw: dict) -> tuple[Unit, Quote, Operator, dt.date]:
    try:
        t, q = raw["trade_unit"], raw["dealer_quote"]
    except KeyError as exc:
        raise DealError(f"Deal file is missing '{exc.args[0]}'.") from exc
    for k in ("make", "model", "year"):
        if t.get(k) in (None, ""):
            raise DealError(f"trade_unit.{k} is required.")
    cat = categories.normalize_category(t.get("category", "")) if t.get("category") else categories.OTHER
    if cat == categories.OTHER:
        cat = categories.classify(t["make"], t["model"])
    if cat == categories.OTHER:
        raise DealError(
            f"Can't tell what kind of machine a {t['make']} {t['model']} is. "
            "Set trade_unit.category (e.g. '4WD Tractor', 'Combine', 'Planter')."
        )
    if t.get("hours") in (None, ""):
        if cat not in NO_ENGINE:
            raise DealError("trade_unit.hours is required for a machine with an engine.")
        t = {**t, "hours": 0}
    unit = Unit(
        category=cat, make=str(t["make"]).strip(), model=str(t["model"]).strip(),
        year=int(_num(t["year"], "trade_unit.year")), hours=_num(t["hours"], "trade_unit.hours"),
        serial=str(t.get("serial", "") or ""), config=str(t.get("config", "") or ""),
        sandhills_vip={k: _num(v, f"sandhills_vip.{k}")
                       for k, v in (t.get("sandhills_vip") or {}).items() if v not in (None, "")},
    )
    fin = None
    if q.get("financing"):
        f = q["financing"]
        fin = Financing(
            apr=_num(f.get("apr"), "financing.apr") or 0.0,
            term_months=int(_num(f.get("term_months"), "financing.term_months") or 0),
            payments_per_year=int(_num(f.get("payments_per_year"), "financing.payments_per_year")
                                  if f.get("payments_per_year") not in (None, "") else 1),
            waiver_months=int(_num(f.get("waiver_months"), "financing.waiver_months") or 0),
            amount_financed=_num(f.get("amount_financed"), "financing.amount_financed"),
            cash_in_lieu=_num(f.get("cash_in_lieu"), "financing.cash_in_lieu"),
        )
        if fin.term_months <= 0:
            raise DealError("financing.term_months is required when financing is given.")
        if fin.payments_per_year not in (1, 2, 4, 12):
            raise DealError("financing.payments_per_year must be 1, 2, 4 or 12.")
    quote = Quote(
        new_unit=str(q.get("new_unit", "new unit")),
        quoted_price_with_trade=_num(q.get("quoted_price_with_trade"), "quoted_price_with_trade") or 0,
        trade_allowance=_num(q.get("trade_allowance"), "trade_allowance") or 0,
        list_price=_num(q.get("list_price"), "list_price"),
        cash_price_no_trade=_num(q.get("cash_price_no_trade"), "cash_price_no_trade"),
        trade_payoff=_num(q.get("trade_payoff"), "trade_payoff") or 0.0,
        other_charges=list(q.get("other_charges") or []),
        financing=fin,
    )
    quote.validate()
    o = raw.get("operator") or {}
    if isinstance(o, str):
        o = {"name": o}
    op = Operator(
        name=str(o.get("name", "")),
        state=str(o.get("state", "IA")).upper(),
        borrow_apr=(DEFAULT_OPERATOR_APR if o.get("borrow_apr") in (None, "")
                    else _num(o.get("borrow_apr"), "operator.borrow_apr")),
        old_unit_adjusted_basis=_num(o.get("old_unit_adjusted_basis"), "operator.old_unit_adjusted_basis"),
    )
    as_of = dt.date.fromisoformat(raw["as_of"]) if raw.get("as_of") else dt.date.today()
    return unit, quote, op, as_of


def _load_json(name: str) -> dict:
    return json.loads((CONFIG / name).read_text(encoding="utf-8"))


def analyze(raw: dict, comps: pd.DataFrame | None = None,
            calibration: Calibration | None = None,
            terms: dict | None = None) -> Analysis:
    unit, quote, op, as_of = parse(raw)
    terms = terms or _load_json("mia_terms.json")
    facts_all = _load_json("market_facts.json")["facts"]
    warnings: list[str] = []
    if not terms["commission"].get("verified"):
        warnings.append("MIA commission brackets are placeholders (published range is 3–6%).")

    if comps is not None and comps.attrs.get("dropped_rows"):
        warnings.append(f"{comps.attrs['dropped_rows']} comp row(s) skipped for a missing "
                        "year, hours, price or sale date.")
    val = value_unit(unit, comps, as_of, calibration)
    consign = {k: consign_net(h, terms, op.borrow_apr)
               for k, h in (("low", val.low), ("mid", val.mid), ("high", val.high))}
    dec = decompose(quote, consign["mid"].net, op.borrow_apr)
    dealer = dealer_view(val, unit.sandhills_vip)

    spread = breakeven = None
    tax_adv = None
    certain = False
    threshold = max(5000.0, 0.015 * val.mid)
    if dec.implied_trade_value is not None:
        tax_adv = trade_tax_advantage(op.state, dec.implied_trade_value)
        spread = {k: consign[k].net - dec.implied_trade_value - tax_adv for k in consign}
        # Direction from the middle estimate; certainty from the range.
        if spread["mid"] > threshold:
            verdict = "squeezed"
            certain = spread["low"] > 0
        elif spread["mid"] < -threshold:
            verdict = "strong"
            certain = spread["high"] < 0
        else:
            verdict = "close"
            certain = False
    else:
        qp, allow = quote.quoted_price_with_trade, quote.trade_allowance
        breakeven = {k: (allow - consign[k].net) / qp * 100 for k in consign}
        # A no-trade price can't be above the quote, so the real trade value is
        # at most the allowance. If the allowance is already below even the
        # low-end consign net, the trade is short no matter what the cash price is.
        # A no-trade price can't exceed the quote, so a break-even at or below
        # 0% means the trade loses whatever the dealer's cash price turns out to be.
        if breakeven["low"] <= 0:
            verdict, certain = "squeezed", True
        elif breakeven["mid"] <= 0:
            verdict, certain = "squeezed", False
        else:
            verdict, certain = "need_cash_price", False
        if op.state in ("SD",):
            warnings.append("South Dakota excise on the cash difference favors trading; "
                            "it can't be quantified until the cash price is known.")

    tf = tax_facts(
        allowance=quote.trade_allowance, implied_trade_value=dec.implied_trade_value,
        quoted_price=quote.quoted_price_with_trade, cash_price=quote.cash_price_no_trade,
        hammer_mid=val.mid,
        selling_expenses=consign["mid"].commission + consign["mid"].prep + consign["mid"].transport,
        adjusted_basis=op.old_unit_adjusted_basis, state=op.state,
    )
    mf = [f for f in facts_all if unit.category in f["categories"]]
    return Analysis(unit, quote, op, as_of, val, consign, dec, dealer, tax_adv, tf,
                    verdict, certain, spread, breakeven, mf, terms, warnings + val.flags)


def load_inputs(folder: Path) -> tuple[pd.DataFrame | None, Calibration | None]:
    """Comps (comps.csv) and MIA history (mia_results/*.xlsx) if present."""
    from .mia import calibrate
    comps = load_comps(folder / "comps.csv") if (folder / "comps.csv").exists() else None
    cal = None
    res = folder / "mia_results"
    if res.is_dir() and any(res.glob("*Auction Summary*.xlsx")):
        cal = calibrate(load_auction_history(res))
    return comps, cal
