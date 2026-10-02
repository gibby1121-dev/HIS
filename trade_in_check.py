#!/usr/bin/env python3
"""Trade-In Check: is the dealer paying a fair price for the operator's trade?

Usage
-----
  python3 trade_in_check.py [FOLDER]
      Reads FOLDER/trade_deal.json, FOLDER/comps.csv (optional) and
      FOLDER/mia_results/*Auction Summary*.xlsx (optional). Writes
      FOLDER/trade_in_report.md (operator) and FOLDER/mia_desk_sheet.md (internal).

  python3 trade_in_check.py [FOLDER] --quote QUOTE.jpg [--quote PAGE2.pdf] [--notes "..."]
      First reads the dealer quote with Claude (needs Anthropic API
      credentials), writes FOLDER/trade_deal.json plus the questions the quote
      leaves open, then runs the check if enough is known.

Exit codes: 0 ok, 1 bad/missing input, 2 the quote needs answers before a
check can run.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from tradein.analyze import analyze, load_inputs
from tradein.comps import CompsError
from tradein.deal import DealError
from tradein.mia import MiaDataError
from tradein.report import desk_sheet, operator_report
from tradein.valuation import ValuationError

INPUT_ERRORS = (DealError, CompsError, MiaDataError, ValuationError, json.JSONDecodeError)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", nargs="?", default=".")
    ap.add_argument("--quote", action="append", default=[], help="dealer quote image/PDF (repeatable)")
    ap.add_argument("--notes", default="", help="operator's own description of the trade unit")
    args = ap.parse_args(argv)
    folder = Path(args.folder).resolve()
    deal_path = folder / "trade_deal.json"

    if args.quote:
        from tradein.intake import IntakeError, extract_deal
        try:
            result = extract_deal([Path(p) for p in args.quote], notes=args.notes)
        except IntakeError as exc:
            sys.stderr.write(f"!! Could not read the quote: {exc}\n")
            return 1
        deal_path.write_text(json.dumps(result.deal, indent=2), encoding="utf-8")
        print(f"  [OK] Read the quote -> {deal_path.name}")
        for w in result.dropped:
            print(f"  [!!] Dropped unverifiable value: {w}")
        if result.questions:
            print("  [??] Still needed before a check can run:")
            for qn in result.questions:
                print(f"       - {qn}")
        if not result.ready:
            return 2

    try:
        raw = json.loads(deal_path.read_text(encoding="utf-8"))
        comps, cal = load_inputs(folder)
        a = analyze(raw, comps, cal)
    except FileNotFoundError:
        sys.stderr.write(f"!! No deal file at {deal_path}\n")
        return 1
    except INPUT_ERRORS as exc:
        sys.stderr.write(f"!! TRADE-IN CHECK HALTED: {exc}\n")
        return 1

    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    (folder / "trade_in_report.md").write_text(operator_report(a, stamp), encoding="utf-8")
    (folder / "mia_desk_sheet.md").write_text(desk_sheet(a, stamp), encoding="utf-8")
    v = a.valuation
    print(f"  [OK] Hammer estimate ${v.mid:,.0f} ({v.low:,.0f}-{v.high:,.0f}, {v.confidence})")
    print(f"  [OK] Verdict: {a.verdict}")
    print("  [OK] Wrote trade_in_report.md and mia_desk_sheet.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
