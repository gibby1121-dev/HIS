"""Dealer-quote decomposition.

A dealer quote bundles three prices into one "difference":

1. **The new unit's real price.** A trade deal is usually quoted off a price
   with less discount than a no-trade (cash) buyer would get. That withheld
   discount is the *over-allowance*: it makes the trade allowance look bigger
   than what the dealer is paying for the trade.
2. **The trade's real value** = allowance − withheld discount.
3. **The financing.** OEMs offer low/0% rate *or* a cash discount, not both.
   The subsidized rate has a cash value at the operator's own borrowing rate;
   if the dealer's cash-in-lieu offer is smaller, the financing wins. Outside
   lenders (e.g. AgDirect) let an operator take the cash discount and still
   finance.

When the dealer's no-trade cash price is unknown, nothing is assumed: the
engine solves for the **break-even discount** — the no-trade discount at which
the trade allowance equals what the operator would net consigning the unit.
That converts an unknowable question into one the operator can put to the
dealer in a single sentence.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class DealError(ValueError):
    pass


@dataclass
class Financing:
    apr: float                    # dealer/OEM rate, percent
    term_months: int
    payments_per_year: int = 1    # big ag is commonly annual; 12 for monthly
    waiver_months: int = 0        # interest-free period before the rate applies
    amount_financed: float | None = None
    cash_in_lieu: float | None = None  # discount offered instead of the rate


@dataclass
class Quote:
    new_unit: str
    quoted_price_with_trade: float
    trade_allowance: float
    list_price: float | None = None
    cash_price_no_trade: float | None = None
    trade_payoff: float = 0.0           # lien payoff on the trade unit
    other_charges: list[dict] = field(default_factory=list)  # freight, PDI, doc
    financing: Financing | None = None

    def validate(self) -> None:
        if self.quoted_price_with_trade <= 0:
            raise DealError("quoted_price_with_trade must be positive.")
        if self.trade_allowance < 0:
            raise DealError("trade_allowance cannot be negative.")
        if self.cash_price_no_trade is not None:
            if self.cash_price_no_trade > self.quoted_price_with_trade:
                raise DealError(
                    "cash_price_no_trade is above the quoted price with trade; "
                    "check the quote (a no-trade price should not be higher)."
                )
        if self.list_price is not None and self.list_price < self.quoted_price_with_trade:
            raise DealError("list_price is below the quoted price; check the quote.")


@dataclass
class FinancingValue:
    payment: float
    payments: int
    amount_financed: float
    pv_at_operator_rate: float
    subsidy_value: float           # amount financed − PV of payments
    cash_in_lieu: float | None
    better: str                    # "financing" | "cash" | "ask"


@dataclass
class Decomposition:
    cash_difference: float                 # quoted price − allowance
    cash_due: float                        # + lien payoff + other charges: the real check
    implied_trade_value: float | None      # allowance − withheld discount
    withheld_discount: float | None
    quote_discount_off_list_pct: float | None
    breakeven_discount_pct: float | None   # vs consign net; set when cash price unknown
    breakeven_cash_price: float | None
    trade_equity: float                    # allowance − lien payoff
    other_charges_total: float
    financing: FinancingValue | None


def level_payment(principal: float, apr: float, n: int, per_year: int) -> float:
    r = apr / 100.0 / per_year
    if r == 0:
        return principal / n
    return principal * r / (1 - (1 + r) ** -n)


def value_financing(f: Financing, default_amount: float, operator_apr: float) -> FinancingValue | None:
    """Cash value of a subsidized rate at the operator's own borrowing rate.

    Timing is in months: no payments (and no interest) during the waiver, then
    level payments every 12/payments_per_year months at the program rate. Each
    payment is discounted at the operator's rate compounded monthly.
    Returns None when there is nothing to finance.
    """
    amount = f.amount_financed if f.amount_financed is not None else default_amount
    if amount <= 0:
        return None
    if f.payments_per_year not in (1, 2, 4, 12):
        raise DealError("payments_per_year must be 1, 2, 4 or 12.")
    if f.apr < 0 or operator_apr < 0:
        raise DealError("rates cannot be negative.")
    step = 12 // f.payments_per_year
    remaining = f.term_months - f.waiver_months
    if remaining <= 0:
        raise DealError("waiver_months must be shorter than term_months.")
    if remaining % step:
        raise DealError(
            f"A {f.term_months}-month term with a {f.waiver_months}-month waiver doesn't divide "
            f"into payments every {step} months; check the financing terms."
        )
    n_pay = remaining // step
    pmt = level_payment(amount, f.apr, n_pay, f.payments_per_year)
    r_m = operator_apr / 100.0 / 12
    pv = sum(pmt / (1 + r_m) ** (f.waiver_months + step * k) for k in range(1, n_pay + 1))
    subsidy = amount - pv
    if f.cash_in_lieu is None:
        better = "ask"
    else:
        better = "financing" if subsidy > f.cash_in_lieu else "cash"
    return FinancingValue(pmt, n_pay, amount, pv, subsidy, f.cash_in_lieu, better)


def decompose(q: Quote, consign_net_mid: float, operator_apr: float) -> Decomposition:
    q.validate()
    diff = q.quoted_price_with_trade - q.trade_allowance
    charges = sum(float(c.get("amount", 0) or 0) for c in q.other_charges)
    cash_due = diff + q.trade_payoff + charges
    off_list = None
    if q.list_price:
        off_list = (q.list_price - q.quoted_price_with_trade) / q.list_price * 100

    if q.cash_price_no_trade is not None:
        withheld = q.quoted_price_with_trade - q.cash_price_no_trade
        implied = q.trade_allowance - withheld
        be_pct = be_price = None
    else:
        withheld = implied = None
        # Trade is worth exactly the consign net when the no-trade price is:
        be_price = q.quoted_price_with_trade - q.trade_allowance + consign_net_mid
        be_pct = (q.quoted_price_with_trade - be_price) / q.quoted_price_with_trade * 100

    fin = None
    if q.financing:
        fin = value_financing(q.financing, cash_due, operator_apr)

    return Decomposition(
        cash_difference=diff,
        cash_due=cash_due,
        implied_trade_value=implied,
        withheld_discount=withheld,
        quote_discount_off_list_pct=off_list,
        breakeven_discount_pct=be_pct,
        breakeven_cash_price=be_price,
        trade_equity=q.trade_allowance - q.trade_payoff,
        other_charges_total=charges,
        financing=fin,
    )
