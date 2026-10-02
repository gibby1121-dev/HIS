"""CPA-ready facts for a trade vs. a separate sale. Never tax advice.

Rules as researched 2026-10 (primary sources listed in docs/RESEARCH.md):

* Since TCJA (exchanges after 2017-12-31), IRC §1031 covers real property
  only. Trading farm machinery is a taxable sale of the old unit plus a
  purchase of the new one. Gain is reported on Form 4797; gain up to prior
  depreciation is §1245 recapture (ordinary income).
* §1245 gain on business machinery is not self-employment income
  (IRC §1402(a)(3)(C)); depreciation on the new unit does reduce SE earnings.
* §453(i): recapture is recognized in the year of sale even on an
  installment sale.
* OBBBA (Pub. L. 119-21): 100% bonus depreciation for property acquired and
  placed in service after 2025-01-19. §179 2026 limit reported at $2.56M
  (secondary source; Rev. Proc. 2025-32 not read directly).

Why it matters here: an over-allowance (inflated allowance AND inflated new
price) raises reported recapture now and the new unit's basis by the same
amount. Federal income tax roughly washes if the new unit is fully expensed
in the same year; SE tax does not (recapture isn't SE income, extra
depreciation reduces it). That asymmetry is a question for the operator's
CPA, so the summary surfaces the numbers and the question, not an answer.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TaxFacts:
    trade_amount_realized: float      # allowance as stated on the contract
    sell_amount_realized: float | None  # hammer less selling expenses
    fmv_estimate: float               # our open-market (hammer) value
    over_allowance: float | None      # stated allowance − implied trade value
    trade_new_basis: float            # contract price on the trade deal
    sell_new_basis: float | None      # cash price if bought without trade
    adjusted_basis: float | None
    trade_gain: float | None
    sell_gain: float | None
    questions: list[str]


def facts(*, allowance: float, implied_trade_value: float | None, quoted_price: float,
          cash_price: float | None, hammer_mid: float, selling_expenses: float,
          adjusted_basis: float | None, state: str) -> TaxFacts:
    sell_realized = hammer_mid - selling_expenses
    over = allowance - implied_trade_value if implied_trade_value is not None else None
    q = [
        "Is the stated trade allowance close to fair market value? If it is inflated, "
        "recapture on the old unit and basis in the new unit both go up by the same amount. "
        "How does that affect self-employment tax, the §179 limit, and state bonus conformity "
        "for this return?",
        "Will the new unit be placed in service this tax year, and will it be expensed "
        "(100% bonus / §179) or depreciated? That decides whether recapture on the old unit "
        "is offset this year.",
        "December vs. January: which tax year should the old unit's sale land in? "
        "Note §453(i): recapture is taxed in the year of sale even on installment terms.",
        "Does farm income averaging (Schedule J) apply to the gain?",
    ]
    if (state or "").upper() == "SD":
        q.append("South Dakota farm-machinery excise is charged on the cash difference after "
                 "trade-in: confirm the current rate and how a separate sale would be taxed.")
    return TaxFacts(
        trade_amount_realized=allowance,
        sell_amount_realized=sell_realized,
        fmv_estimate=hammer_mid,
        over_allowance=over,
        trade_new_basis=quoted_price,
        sell_new_basis=cash_price,
        adjusted_basis=adjusted_basis,
        trade_gain=None if adjusted_basis is None else allowance - adjusted_basis,
        sell_gain=None if adjusted_basis is None else sell_realized - adjusted_basis,
        questions=q,
    )
