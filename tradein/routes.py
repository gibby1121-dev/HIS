"""Net-to-operator by route, and the dealer's side of the trade.

Routes for the old unit:

* **Trade** — the dealer's real (implied) trade value, today, no work.
* **Consign at MIA** — expected hammer less MIA commission, prep, transport,
  and the cost of money until the check clears.

The dealer's side: a dealer books a trade at actual cash value (ACV) and has
to dispose of it. Industry valuation tiers (Iron Solutions IronGuides) put
dealer-to-dealer wholesale above forced (auction) liquidation, and
dealer-expected resale ("Resale Cash") above both. Farm Equipment's dealer
benchmarks cite used-equipment gross margin targets around 8% (actual
industry averages ran ~2-5% in 2012-2016). From that we bracket what a dealer
can rationally pay: auction value is its floor (it can always send the unit
to auction); expected resale less margin, recon and holding is its ceiling.
"""

from __future__ import annotations

from dataclasses import dataclass

from .valuation import Valuation

# Dealer economics assumptions; every one is printed in the desk sheet.
DEALER_MARGIN_PCT = 8.0        # Farm Equipment benchmark target (8% x 2 turns)
DEALER_MARGIN_ACTUAL_PCT = 3.7  # Farm Equipment: 5-yr average actual used margin (2012-16)
DEALER_RECON_PCT = 2.0         # not published; placeholder
DEALER_HOLD_DAYS = 120         # 2-3 turns/yr target; 4WD/high-HP turns slower in 2026
DEALER_FLOORPLAN_APR = 8.0     # placeholder floorplan cost of money
RESALE_OVER_AUCTION = 1.15     # fallback resale/hammer ratio when no VIP+ market value


@dataclass
class ConsignNet:
    hammer: float
    commission_pct: float
    commission: float
    prep: float
    transport: float
    days_to_cash: int
    carrying: float
    net: float


@dataclass
class DealerView:
    floor: float           # auction hammer: what the dealer gets by wholesaling to auction
    resale: float          # expected retail resale (Resale Cash)
    ceiling: float         # ACV at the 8% target margin
    ceiling_high: float    # ACV at the ~3.7% margin dealers actually averaged
    basis: str


def commission_pct(hammer: float, terms: dict) -> float:
    for tier in terms["commission"]["tiers"]:
        if tier["up_to"] is None or hammer <= tier["up_to"]:
            return float(tier["pct"])
    return float(terms["commission"]["tiers"][-1]["pct"])  # pragma: no cover


def _v(terms: dict, key: str) -> float:
    v = terms.get(key, 0)
    return float(v["value"] if isinstance(v, dict) else v)


def consign_net(hammer: float, terms: dict, operator_apr: float) -> ConsignNet:
    pct = commission_pct(hammer, terms)
    commission = hammer * pct / 100.0
    prep = _v(terms, "seller_prep_cost")
    transport = _v(terms, "seller_transport_cost")
    days = int(_v(terms, "days_to_next_sale") + _v(terms, "settlement_days"))
    carrying = hammer * operator_apr / 100.0 * days / 365.0
    net = hammer - commission - prep - transport - carrying
    return ConsignNet(hammer, pct, commission, prep, transport, days, carrying, net)


def dealer_view(val: Valuation, sandhills_vip: dict | None) -> DealerView:
    vip = sandhills_vip or {}
    if vip.get("market"):
        resale, basis = float(vip["market"]), "Sandhills VIP+ market value"
    else:
        resale = val.mid * RESALE_OVER_AUCTION
        basis = f"hammer estimate × {RESALE_OVER_AUCTION:.2f} (no VIP+ market value supplied)"
    hold = resale * DEALER_FLOORPLAN_APR / 100.0 * DEALER_HOLD_DAYS / 365.0
    acv = lambda margin: resale * (1 - (margin + DEALER_RECON_PCT) / 100.0) - hold  # noqa: E731
    return DealerView(floor=val.mid, resale=resale,
                      ceiling=max(acv(DEALER_MARGIN_PCT), val.mid),
                      ceiling_high=max(acv(DEALER_MARGIN_ACTUAL_PCT), val.mid), basis=basis)


# South Dakota taxes farm machinery under a separate excise on the cash
# difference after trade-in (SDCL 10-46E-1). Statutory 4.5%; whether the
# 2023 temporary cut applies to this excise was not verified.
STATE_TRADE_TAX = {"SD": 4.5}
EXEMPT_STATES = {"IA", "IL", "NE", "MN", "MO", "WI", "KS", "IN"}


def trade_tax_advantage(state: str, implied_trade_value: float) -> float:
    """Tax saved by trading vs. selling separately and buying at cash price.

    Where tax applies to the cash difference only, trading removes the trade
    value from the taxable amount. Zero in states where ag machinery is exempt.
    """
    rate = STATE_TRADE_TAX.get((state or "").upper())
    if not rate or implied_trade_value <= 0:
        return 0.0
    return implied_trade_value * rate / 100.0
