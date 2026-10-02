"""Render the operator report and the internal MIA desk sheet."""

from __future__ import annotations

from .analyze import Analysis


def m(v: float | None) -> str:
    if v is None:
        return "—"
    return f"-${-v:,.0f}" if v < 0 else f"${v:,.0f}"


def pct(v: float | None) -> str:
    return "—" if v is None else f"{v:.1f}%"


VERDICT = {
    "squeezed": "🔴 **The dealer is paying less for your trade than it would net you consigned.**",
    "close": "🟡 **The trade is in the fair range.** The gap is inside the uncertainty "
             "of the market value. Trading may be worth the convenience, but there's room to push.",
    "strong": "🟢 **The dealer is paying well for your trade.** It beats what you'd likely net "
              "consigning it. Negotiate the new unit, not the trade.",
    "need_cash_price": "🟠 **This quote can't be judged yet: it's missing the no-trade cash price.** "
                       "The single number below tells you exactly what to ask for.",
}


def _unit(a: Analysis) -> str:
    u = a.unit
    return f"{u.year} {u.make} {u.model}"


def operator_report(a: Analysis, generated: str) -> str:
    u, q, v, d = a.unit, a.quote, a.valuation, a.decomposition
    c = a.consign
    L: list[str] = []
    L += [f"# Trade-In Check: {_unit(a)}", ""]
    who = f" for {a.operator.name}" if a.operator.name else ""
    L += [f"_Prepared{who} by Heartland Iron Solutions / Mid-Iowa Auction on {generated}. "
          f"Market data through {a.as_of.isoformat()}. A decision aid: not an appraisal, "
          "not tax advice._", ""]

    # ---- Bottom line -------------------------------------------------------
    head = VERDICT[a.verdict]
    if a.verdict in ("squeezed", "strong") and d.implied_trade_value is not None:
        if a.certain:
            head += " That holds across the whole likely value range."
        else:
            edge = a.spread["low"] if a.verdict == "squeezed" else a.spread["high"]
            end = "low" if a.verdict == "squeezed" else "high"
            if edge > 0:
                at_edge = f"consigning would still net {m(edge)} more"
            elif edge < 0:
                at_edge = f"trading would net {m(-edge)} more"
            else:
                at_edge = "it's even"
            head += (f" That's at the middle estimate of your unit's value; at the {end} end "
                     f"of the range, {at_edge}.")
    L += ["## Bottom line", "", head, ""]
    if d.implied_trade_value is not None:
        s = a.spread
        L.append(f"- The dealer shows **{m(q.trade_allowance)}** for your trade, but they're "
                 f"withholding a **{m(d.withheld_discount)}** discount you'd get without a trade. "
                 f"What they're really paying for it is **{m(d.implied_trade_value)}**.")
        L.append(f"- Consigned at Mid-Iowa, it would likely net you **{m(c['mid'].net)}** "
                 f"(range {m(c['low'].net)}–{m(c['high'].net)}) after commission and costs.")
        if s["mid"] >= 0:
            L.append(f"- **Trading costs you about {m(s['mid'])}** (range {m(s['low'])} to "
                     f"{m(s['high'])}) compared with consigning.")
        else:
            L.append(f"- **Trading puts about {m(-s['mid'])} more in your pocket** than consigning "
                     f"(range {m(-s['high'])} to {m(-s['low'])}).")
        if a.tax_advantage_trade:
            L.append(f"- Already counted: {a.operator.state} taxes farm machinery only on the cash "
                     f"difference after a trade, which saves you about {m(a.tax_advantage_trade)} versus "
                     "selling separately (at the 4.5% statutory rate; confirm the current rate).")
    else:
        be = a.breakeven
        L.append(f"- Ask the dealer one question: **\"What's your cash price on the {q.new_unit} "
                 f"if I don't trade anything in?\"**")
        if a.min_withheld_discount > 0:
            L.append(f"- The {m(q.trade_allowance)} allowance is about **{m(a.min_withheld_discount)} "
                     f"more than a dealer could pay for this unit** even on the thin used margins "
                     f"dealers have actually averaged (estimate: {m(a.dealer.ceiling_high)}, see below). "
                     "Expect roughly that much or more to be coming back out of your new-unit price.")
        if a.verdict == "squeezed":
            ref = c["low"].net if a.certain else c["mid"].net
            L.append(f"- Whatever they answer, the {m(q.trade_allowance)} allowance is already below "
                     f"the {m(ref)} your unit "
                     + ("nets consigned even at the low end of its value range"
                        if a.certain else "nets consigned at the middle estimate of its value")
                     + ", before any withheld discount comes out. A no-trade price can only "
                     "make the real trade value lower.")
        else:
            L.append(f"- **If their no-trade price is below {m(d.breakeven_cash_price)}** "
                     f"(more than {pct(be['mid'])} off this quote), the trade is paying you less "
                     f"than consigning at Mid-Iowa nets. Above that, the trade wins.")
            if be["high"] > 0:
                L.append(f"- Given the uncertainty in your unit's value, the line runs from "
                         f"{pct(be['high'])} to {pct(be['low'])} off the quote.")
            else:
                L.append(f"- If your unit sells at the high end of its range, the trade loses at "
                         f"any no-trade price; at the low end the line is {pct(be['low'])} off the quote.")
            if d.quote_discount_off_list_pct is not None:
                L.append(f"- For reference, this quote is {pct(d.quote_discount_off_list_pct)} "
                         f"off the {m(q.list_price)} list price.")
    if d.financing and d.financing.better != "cash" and d.financing.subsidy_value > 0:
        L.append(f"- The dealer financing is worth about **{m(d.financing.subsidy_value)}** in "
                 f"today's dollars at your {a.operator.borrow_apr:.1f}% borrowing rate. "
                 "See the financing section before you take any cash-in-lieu offer.")
    L.append("")

    # ---- The deal, unbundled ----------------------------------------------
    L += ["## The dealer deal, unbundled", "", "| Line | Amount |", "|---|---|"]
    if q.list_price:
        L.append(f"| List price, {q.new_unit} | {m(q.list_price)} |")
    L.append(f"| Quoted price with your trade | {m(q.quoted_price_with_trade)} |")
    L.append(f"| Trade allowance shown | {m(q.trade_allowance)} |")
    L.append(f"| Cash difference (quote − allowance) | {m(d.cash_difference)} |")
    if q.cash_price_no_trade is not None:
        L.append(f"| Cash price with no trade | {m(q.cash_price_no_trade)} |")
        L.append(f"| Discount withheld because you're trading | {m(d.withheld_discount)} |")
        L.append(f"| **What the dealer is really paying for your trade** | **{m(d.implied_trade_value)}** |")
    else:
        L.append("| Cash price with no trade | **ask the dealer** |")
    if q.trade_payoff:
        L.append(f"| Lien payoff on your trade (dealer pays off) | {m(q.trade_payoff)} |")
        L.append(f"| Your equity in the trade | {m(d.trade_equity)} |")
    for ch in q.other_charges:
        L.append(f"| {ch.get('label', 'Other charge')} | {m(float(ch.get('amount', 0) or 0))} |")
    if d.cash_due != d.cash_difference:
        L.append(f"| **Cash due (difference + lien payoff + charges)** | **{m(d.cash_due)}** |")
    L.append("")

    # ---- Open market --------------------------------------------------------
    L += ["## What your machine brings on the open market", ""]
    L.append(f"Expected **auction hammer: {m(v.mid)}** (likely {m(v.low)}–{m(v.high)}, "
             f"{v.confidence.lower()} confidence). Hammer is what the seller grosses: "
             "buyer's premiums are stripped out of every comparable.")
    L.append("")
    for an in v.anchors:
        L.append(f"- **{an.name}:** {m(an.mid)} ({m(an.low)}–{m(an.high)}). {an.detail}.")
    gap = v.asking_gap_pct
    if gap is not None:
        L.append(f"- **Listings you see online:** similar units are *asking* about {gap:.0f}% "
                 f"more than they bring at auction ({len(v.asking)} listings, adjusted to your "
                 "year and hours). Don't measure the dealer's offer against asking prices.")
    for f in a.market_facts:
        L.append(f"- _{f['as_of']}:_ {f['text']} ([source]({f['source']}))")
    L.append("")

    # ---- Trade vs consign ---------------------------------------------------
    L += ["## Trade it vs. consign it at Mid-Iowa", "",
          "| | Trade to dealer | Consign at Mid-Iowa (low / mid / high) |", "|---|---|---|"]
    tv = m(d.implied_trade_value) if d.implied_trade_value is not None else "needs cash price"
    L.append(f"| Hammer / value | {tv} | {m(c['low'].hammer)} / {m(c['mid'].hammer)} / {m(c['high'].hammer)} |")
    L.append(f"| Commission | — | {m(c['low'].commission)} / {m(c['mid'].commission)} / "
             f"{m(c['high'].commission)} ({c['mid'].commission_pct:.0f}% at mid) |")
    L.append(f"| Prep + transport | — | {m(c['mid'].prep + c['mid'].transport)} |")
    L.append(f"| Cost of waiting for the check ({c['mid'].days_to_cash} days) | — | {m(c['mid'].carrying)} |")
    if a.tax_advantage_trade:
        L.append(f"| {a.operator.state} excise saved by trading | {m(a.tax_advantage_trade)} | — |")
    L.append(f"| **Net to you** | **{tv}** | **{m(c['low'].net)} / {m(c['mid'].net)} / {m(c['high'].net)}** |")
    L.append(f"| Time to cash | at delivery | about {c['mid'].days_to_cash} days |")
    L.append("")
    L.append("Mid-Iowa charges nothing if the unit doesn't sell, and you can set a reserve. "
             "Consigning means a gap between selling the old unit and taking delivery of the "
             "new one. Plan the sale date around delivery.")
    L.append("")

    # ---- Financing ----------------------------------------------------------
    if d.financing:
        fv, f = d.financing, q.financing
        L += ["## The financing is a second bundle", ""]
        L.append(f"{f.apr:.2f}% for {f.term_months} months"
                 + (f" ({f.waiver_months}-month interest waiver)" if f.waiver_months else "")
                 + f" on {m(fv.amount_financed)}: {fv.payments} payments of {m(fv.payment)}. "
                 f"At your own {a.operator.borrow_apr:.1f}% borrowing rate those payments are "
                 f"worth {m(fv.pv_at_operator_rate)} today, so the rate is worth "
                 f"**{m(fv.subsidy_value)}** to you.")
        L.append("")
        if fv.better == "ask":
            L.append(f"- OEM programs are usually low rate **or** a cash discount. Ask what the "
                     f"cash-in-lieu is. **Anything under {m(fv.subsidy_value)} is worth less than "
                     "the financing.**")
        elif fv.better == "cash":
            L.append(f"- The {m(fv.cash_in_lieu)} cash-in-lieu beats the rate. Take the cash and "
                     "finance elsewhere: lenders like AgDirect don't make you choose between OEM "
                     "rebates and financing.")
        else:
            L.append(f"- Keep the financing: it's worth more than the {m(fv.cash_in_lieu)} "
                     "cash-in-lieu offer.")
        L.append("- Make sure the rate isn't being paid for by a thinner discount: get the "
                 "no-trade cash price with *and* without the program.")
        L.append("")

    # ---- Dealer's side ------------------------------------------------------
    dv = a.dealer
    L += ["## What the dealer can afford to pay", ""]
    L.append(f"A dealer can always send your unit to auction, so about **{m(dv.floor)}** "
             f"(expected hammer) is the least it should pay. If it retails your unit at about "
             f"{m(dv.resale)} ({dv.basis}), it can pay roughly **{m(dv.ceiling)}–{m(dv.ceiling_high)}**: "
             "the low figure at the 8% used margin dealers target, the high figure at the "
             "~3.7% they've actually averaged. These are estimates: they also assume 2% "
             "reconditioning and 120 days of floorplan at 8%.")
    L.append("")
    if a.verdict in ("squeezed", "close", "need_cash_price"):
        target = max(c["mid"].net, min(dv.ceiling, c["high"].net))
        walk = c["mid"].net - (a.tax_advantage_trade or 0)
        L.append(f"- **Walk-away point:** a real trade value under **{m(walk)}** means "
                 "consigning nets you more"
                 + (f" (after the {m(a.tax_advantage_trade)} {a.operator.state} excise saved by trading)."
                    if a.tax_advantage_trade else "."))
        if d.implied_trade_value is None:
            L.append(f"- **Counter:** your target real trade value is **{m(target)}**. Once you have "
                     f"the no-trade price P, the allowance on this quote should be at least "
                     f"{m(target)} + ({m(q.quoted_price_with_trade)} − P).")
        elif target > d.implied_trade_value:
            L.append(f"- **Counter:** ask for a real trade value of **{m(target)}**: an allowance of "
                     f"**{m(q.trade_allowance + target - d.implied_trade_value)}** at the same quote, "
                     f"or the same allowance with the cash difference down "
                     f"{m(target - d.implied_trade_value)}.")
        else:
            L.append("- The trade value is already at or above a realistic target. Push on the "
                     "new unit's price instead.")
    L.append("")

    # ---- Before you sign ----------------------------------------------------
    L += ["## Before you sign", ""]
    L.append("- **Get an itemized invoice**: new-unit price, trade allowance, cash, financing "
             "and fees each on its own line. Your CPA needs it, and it pins the dealer to the numbers.")
    L.append("- **Precision tech:** activations on an integrated StarFire receiver stay with the "
             "receiver. G5 display licenses can be moved: deactivate them in Operations Center "
             "*before* the unit leaves. Decide whether receivers and displays go with the trade "
             "or come off; if they go, they should be in the allowance.")
    if q.trade_payoff:
        L.append(f"- **Lien:** the dealer pays off {m(q.trade_payoff)}. Get the payoff letter "
                 "and a UCC-3 termination.")
    if q.other_charges:
        L.append(f"- **Other charges** ({m(d.other_charges_total)}): ask which are negotiable "
                 "and whether a no-trade buyer pays them too.")
    L.append("")

    # ---- CPA ---------------------------------------------------------------
    t = a.tax
    L += ["## For your CPA (facts and questions, not advice)", "",
          "Since 2018, a machinery trade generally isn't a like-kind exchange: it's reported as a "
          "sale of the old unit plus a purchase of the new one, with the new unit's basis at its "
          "full price. Ask your CPA how the stated allowance and price will be reported. The "
          "table shows the figures they'll want.", "",
          "| | Trade | Sell separately |", "|---|---|---|"]
    L.append(f"| Old unit: stated sale amount | {m(t.trade_amount_realized)} (trade allowance) | "
             f"{m(t.sell_amount_realized)} (est. hammer less selling costs) |")
    L.append(f"| New unit: basis | {m(t.trade_new_basis)} (contract price) | "
             f"{m(t.sell_new_basis) if t.sell_new_basis else 'cash price'} |")
    if t.adjusted_basis is not None:
        L.append(f"| Gain on old unit (adjusted basis {m(t.adjusted_basis)}) | "
                 f"{m(t.trade_gain)} | {m(t.sell_gain)} |")
    if t.over_allowance:
        L.append(f"| Allowance above real trade value | {m(t.over_allowance)} | — |")
    L.append("")
    for qn in t.questions:
        L.append(f"- {qn}")
    L.append("")

    # ---- Comps & assumptions -----------------------------------------------
    if len(v.comps):
        L += ["## Comparable sales used", "",
              f"Adjusted to a {u.year} with {u.hours:,.0f} hours at "
              f"{v.dep_per_year:.1%}/model year and {v.per_1000_hrs:.1%}/1,000 hours "
              f"({'fitted from these sales' if v.rates_fitted else 'default rates'}).", "",
              "| Date | Unit | Hours | Source | Hammer | Adjusted | Weight |",
              "|---|---|---|---|---|---|---|"]
        tw = v.comps["Weight"].sum()
        for _, r in v.comps.head(12).iterrows():
            src = r.get("Source", "") if isinstance(r.get("Source", ""), str) else ""
            L.append(f"| {r['SaleDate'].date()} | {int(r['Year'])} {r['Make']} {r['Model']} | "
                     f"{r['Hours']:,.0f} | {src or '—'} | {m(r['Hammer'])} | "
                     f"{m(r['AdjustedHammer'])} | {r['Weight'] / tw:.0%} |")
        L.append("")
    if a.warnings:
        L += ["## Caveats", ""] + [f"- {w}" for w in a.warnings] + [""]
    return "\n".join(L)


def desk_sheet(a: Analysis, generated: str) -> str:
    """Internal MIA sheet: what to quote, how sure we are, what's unverified."""
    v, c, d, dv = a.valuation, a.consign, a.decomposition, a.dealer
    L = [f"# MIA desk sheet: {_unit(a)} ({a.unit.category})", "",
         f"_Internal. Generated {generated}. Operator: {a.operator.name or '—'} ({a.operator.state})._", "",
         f"**Verdict:** {a.verdict}  ·  **Value confidence:** {v.confidence}", "",
         "## Consignment pitch", "",
         f"- Expected hammer {m(v.mid)} (range {m(v.low)}–{m(v.high)}).",
         f"- Suggested reserve: no higher than {m(v.low)} (low end of range); "
         "a reserve above the range risks a no-sale.",
         f"- Operator nets {m(c['mid'].net)} at mid after {c['mid'].commission_pct:.0f}% commission.",
         f"- Dealer ACV estimate: {m(dv.ceiling)} (8% target margin) to {m(dv.ceiling_high)} "
         f"(3.7% actual average); floor {m(dv.floor)}. Recon/floorplan inputs are placeholders.", ""]
    if d.implied_trade_value is not None:
        L.append(f"- Dealer's real trade value {m(d.implied_trade_value)}; spread vs. consign "
                 f"{m(a.spread['mid'])} at mid.")
    else:
        L.append(f"- Break-even no-trade price {m(d.breakeven_cash_price)}. Get the operator "
                 "to ask the dealer for the cash price, then rerun.")
    if a.min_withheld_discount > 0:
        L.append(f"- Allowance exceeds even the 3.7%-margin ACV by {m(a.min_withheld_discount)}: roughly that "
                 "much over-allowance is baked into the new-unit price.")
    L += ["", "## Value anchors", ""]
    for an in v.anchors:
        L.append(f"- {an.name}: {m(an.low)} / {m(an.mid)} / {m(an.high)}. {an.detail}")
    L += ["", "## Before this goes to the operator", ""]
    checks = list(a.warnings)
    if not a.unit.sandhills_vip.get("auction"):
        checks.append("Pull the Sandhills VIP+ auction/market values for this serial and rerun "
                      "(adds the calibrated anchor and the dealer resale basis).")
    if v.confidence == "Low":
        checks.append("Low confidence: inspect the unit or find more same-model hammer comps.")
    checks.append("Confirm configuration (tracks vs wheels, PTO, hitch, tire/track condition, "
                  "precision package) against the comps used.")
    L += [f"- [ ] {x}" for x in checks]
    L.append("")
    return "\n".join(L)
