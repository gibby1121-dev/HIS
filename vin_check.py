#!/usr/bin/env python3
"""
VIN checker — ghost-listing triage for sourcing runs
====================================================

Sourcing sweeps (see the Want.it / FSBO workflows) come back full of leads
scraped from dealer sites, aggregator feeds, and search-engine summaries. A
large share of those are **ghost listings**: auto-generated SEO landing pages
for every year/model/trim permutation a dealer *could* stock, whether or not a
single unit is on the ground. They exist to generate phone calls.

This tool separates "a real machine that was actually built" from "a page that
wants you to call."

What it does
------------
1. **Validates the VIN check digit** (ISO 3779 position-9 arithmetic). A VIN
   invented out of thin air fails this roughly 90% of the time, so a failure is
   near-proof of fabrication and a pass is a real, well-formed VIN.
2. **Decodes the structure** — world manufacturer identifier, model year
   (disambiguated across the 30-year code cycle), assembly plant, and the
   sequential build number.
3. **Emits verification URLs** — the manufacturer window sticker (the Monroney
   label, which only exists if the factory actually built that unit, and which
   lists the real option codes) and the NHTSA vPIC decoder.

What it deliberately does NOT do
--------------------------------
No network calls. The tool is offline and deterministic: it hands you the URLs
to open rather than fetching them. That keeps it testable, keeps it working
behind restrictive egress policies, and keeps a sourcing run from hammering
third-party services. Open the printed URLs in a browser to finish the check.

A valid check digit proves the number is well-formed. A window sticker proves
the factory built it. **Neither proves the unit is on that lot today** — that
still takes a VIN from the seller up front and a timestamped photo.

Usage
-----
    python3 vin_check.py 1FT8W4DM6TED77655 1FT8W4DM1TED70984
    python3 vin_check.py --file candidates.txt
    python3 vin_check.py --csv candidates.csv --column VIN
    python3 vin_check.py --csv candidates.csv --json > verified.json

Exit codes: 0 = every VIN valid, 1 = at least one invalid, 2 = bad input.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

VIN_LENGTH = 17

# I, O and Q are excluded from VINs precisely so they cannot be confused with
# 1 and 0 — their presence means a transcription error or a fabrication.
INVALID_LETTERS = frozenset("IOQ")

# ISO 3779 transliteration: letters map onto 1-9, skipping the excluded three.
TRANSLITERATION = {
    **{str(d): d for d in range(10)},
    **dict(zip("ABCDEFGH", range(1, 9))),
    **dict(zip("JKLMN", range(1, 6))),
    "P": 7,
    "R": 9,
    **dict(zip("STUVWXYZ", range(2, 10))),
}

# Positional weights for the check-digit sum. Position 9 (the check digit
# itself) carries weight 0 so it cannot influence its own calculation.
WEIGHTS = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)

CHECK_DIGIT_INDEX = 8
MODEL_YEAR_INDEX = 9
PLANT_INDEX = 10
SEQUENCE_INDEX = 11

# Position 10 encodes model year on a 30-year cycle, so every code is
# ambiguous (T is both 1996 and 2026). Position 7 breaks the tie: North
# American light vehicles from 2010 on carry a letter there, earlier ones a
# digit. See _resolve_model_year.
_YEAR_CODES = "ABCDEFGHJKLMNPRSTVWXY123456789"
MODEL_YEAR_CYCLE = {
    # 1980-2000 use letters, 2001-2009 digits, then letters again from 2010.
    code: (1980 + offset, 2010 + offset)
    for offset, code in enumerate(_YEAR_CODES[:21])
}
MODEL_YEAR_CYCLE.update({str(d): (2000 + d, 2000 + d) for d in range(1, 10)})

DISAMBIGUATION_INDEX = 6  # position 7, zero-indexed

# Common Ford assembly plants (position 11). Deliberately conservative — codes
# outside this table report as unknown rather than guessing, since a wrong
# plant name in a sourcing report is worse than an honest blank.
FORD_PLANTS = {
    "A": "Atlanta Assembly, Hapeville GA",
    "C": "Ontario Truck Plant, Oakville ON",
    "D": "Ohio Assembly, Avon Lake OH",
    "E": "Kentucky Truck Plant, Louisville KY",
    "F": "Dearborn Truck Plant, Dearborn MI",
    "G": "Chicago Assembly, Chicago IL",
    "K": "Kansas City Assembly, Claycomo MO",
    "L": "Michigan Assembly, Wayne MI",
    "U": "Louisville Assembly Plant, Louisville KY",
    "W": "Wayne Assembly, Wayne MI",
    "X": "St. Thomas Assembly, Ontario",
}

# Ford / Lincoln world manufacturer identifiers, used to decide whether the
# Ford window-sticker service is the right lookup for a given VIN.
FORD_WMIS = frozenset(
    {
        "1FA", "1FB", "1FC", "1FD", "1FM", "1FT",
        "2FA", "2FB", "2FC", "2FM", "2FT",
        "3FA", "3FB", "3FE", "3FM", "3FT",
        "5LM", "5LT", "5LK",
    }
)

FORD_STICKER_URL = "https://www.windowsticker.forddirect.com/windowsticker.pdf?vin={vin}"
NHTSA_DECODE_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/decodevinvalues/{vin}?format=json"


class VinError(ValueError):
    """Raised when a string cannot be treated as a VIN at all."""


def normalize(vin: str) -> str:
    """Upper-case a VIN and strip separators sellers paste in."""
    return "".join(vin.split()).replace("-", "").upper()


def check_digit(vin: str) -> str:
    """Return the check digit position 9 *should* hold for this VIN."""
    vin = normalize(vin)
    if len(vin) != VIN_LENGTH:
        raise VinError(f"expected {VIN_LENGTH} characters, got {len(vin)}")

    total = 0
    for position, (character, weight) in enumerate(zip(vin, WEIGHTS)):
        if position == CHECK_DIGIT_INDEX:
            continue  # the check digit is excluded from its own sum
        try:
            total += TRANSLITERATION[character] * weight
        except KeyError:
            raise VinError(
                f"invalid character {character!r} at position {position + 1}"
            ) from None

    remainder = total % 11
    return "X" if remainder == 10 else str(remainder)


def _resolve_model_year(vin: str) -> int | None:
    """Resolve position 10 to a calendar year, or None if the code is unknown.

    The year code repeats every 30 years. Position 7 disambiguates: North
    American light vehicles built 2010 and later carry a letter there, earlier
    ones a digit.

    CAVEAT: that convention is defined for *light* vehicles. Class 8 tractors
    and other heavy trucks frequently carry a digit at position 7 whatever the
    year, so a late-model heavy truck can resolve 30 years early. Treat the
    year on a Class 8 VIN as a hint and confirm it against the NHTSA decode.
    """
    early, late = MODEL_YEAR_CYCLE.get(vin[MODEL_YEAR_INDEX], (None, None))
    if early is None:
        return None
    if early == late:  # digit codes (2001-2009) are unambiguous
        return early
    return late if vin[DISAMBIGUATION_INDEX].isalpha() else early


def is_ford(vin: str) -> bool:
    """True when the world manufacturer identifier belongs to Ford or Lincoln."""
    return normalize(vin)[:3] in FORD_WMIS


def window_sticker_url(vin: str) -> str | None:
    """Ford window-sticker (Monroney) URL, or None for non-Ford VINs.

    A sticker coming back is proof the factory built this exact unit, and it
    lists the real option codes — which is how you confirm a package like
    Platinum Plus (773A) rather than taking a listing's word for it.
    """
    vin = normalize(vin)
    return FORD_STICKER_URL.format(vin=vin) if is_ford(vin) else None


def nhtsa_url(vin: str) -> str:
    """Free NHTSA vPIC decoder URL — works for every make."""
    return NHTSA_DECODE_URL.format(vin=normalize(vin))


def inspect(vin: str) -> dict:
    """Validate and decode a single VIN into a report-ready record.

    Never raises: malformed input comes back as ``valid=False`` with a reason,
    so one bad row in a candidate list cannot abort a whole sourcing sweep.
    """
    raw = vin
    vin = normalize(vin)
    record: dict = {
        "vin": vin,
        "raw": raw,
        "valid": False,
        "reason": None,
        "model_year": None,
        "wmi": None,
        "plant": None,
        "plant_code": None,
        "sequence": None,
        "window_sticker_url": None,
        "nhtsa_url": None,
    }

    if len(vin) != VIN_LENGTH:
        record["reason"] = f"wrong length: {len(vin)} characters, expected {VIN_LENGTH}"
        return record

    bad = sorted(set(vin) & INVALID_LETTERS)
    if bad:
        record["reason"] = f"contains {', '.join(bad)} — never used in VINs"
        return record

    try:
        expected = check_digit(vin)
    except VinError as exc:
        record["reason"] = str(exc)
        return record

    actual = vin[CHECK_DIGIT_INDEX]
    if actual != expected:
        record["reason"] = (
            f"check digit mismatch: position 9 is {actual!r}, should be {expected!r}"
        )
        return record

    plant_code = vin[PLANT_INDEX]
    record.update(
        valid=True,
        model_year=_resolve_model_year(vin),
        wmi=vin[:3],
        plant_code=plant_code,
        plant=FORD_PLANTS.get(plant_code) if is_ford(vin) else None,
        sequence=vin[SEQUENCE_INDEX:],
        window_sticker_url=window_sticker_url(vin),
        nhtsa_url=nhtsa_url(vin),
    )
    return record


def inspect_all(vins) -> list[dict]:
    """Inspect an iterable of VINs, preserving input order."""
    return [inspect(vin) for vin in vins]


# --------------------------------------------------------------------------- #
# Input collection                                                            #
# --------------------------------------------------------------------------- #
def read_vins_from_file(path: Path) -> list[str]:
    """One VIN per line. Blank lines and '#' comments are ignored."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [
        stripped
        for line in lines
        if (stripped := line.strip()) and not stripped.startswith("#")
    ]


def read_vins_from_csv(path: Path, column: str) -> list[str]:
    """Pull a VIN column out of a candidate-list CSV."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise VinError(f"{path.name} is empty")
        if column not in reader.fieldnames:
            raise VinError(
                f"{path.name} has no {column!r} column "
                f"(found: {', '.join(reader.fieldnames)})"
            )
        return [row[column].strip() for row in reader if row.get(column, "").strip()]


# --------------------------------------------------------------------------- #
# Rendering                                                                   #
# --------------------------------------------------------------------------- #
def format_table(records: list[dict]) -> str:
    """Human-readable summary for a sourcing run."""
    lines = []
    valid = [r for r in records if r["valid"]]
    invalid = [r for r in records if not r["valid"]]

    lines.append("=" * 72)
    lines.append(" VIN CHECK — ghost-listing triage")
    lines.append("=" * 72)

    for record in records:
        if record["valid"]:
            year = record["model_year"] or "year?"
            if record["plant"]:
                plant = record["plant"]
            elif record["wmi"] in FORD_WMIS:
                plant = f"plant {record['plant_code']} (unrecognized code)"
            else:
                plant = f"plant {record['plant_code']} (not decoded — non-Ford)"
            lines.append(f"\n  [VALID]   {record['vin']}")
            lines.append(f"            {year} · {plant} · build #{record['sequence']}")
        else:
            lines.append(f"\n  [INVALID] {record['raw']}")
            lines.append(f"            {record['reason']}")

    if valid:
        lines.append("\n" + "-" * 72)
        lines.append(" Confirm the factory actually built these — open each URL:")
        lines.append("-" * 72)
        for record in valid:
            url = record["window_sticker_url"] or record["nhtsa_url"]
            lines.append(f"  {record['vin']}  {url}")

    lines.append("\n" + "-" * 72)
    lines.append(
        f" {len(valid)} valid · {len(invalid)} invalid · {len(records)} checked"
    )
    lines.append(
        " A valid VIN and a window sticker prove the unit was BUILT. Neither"
    )
    lines.append(
        " proves it is on a lot today — get the VIN from the seller up front"
    )
    lines.append(" and a timestamped photo before anyone drives anywhere.")
    lines.append("-" * 72)
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vin_check.py",
        description="Validate and decode VINs from a sourcing run, and emit "
        "window-sticker URLs that prove a unit was actually built.",
    )
    parser.add_argument("vins", nargs="*", help="VINs to check")
    parser.add_argument(
        "--file", type=Path, help="text file with one VIN per line"
    )
    parser.add_argument("--csv", type=Path, help="CSV file containing a VIN column")
    parser.add_argument(
        "--column", default="VIN", help="VIN column name in --csv (default: VIN)"
    )
    parser.add_argument(
        "--json", action="store_true", help="emit JSON records instead of a table"
    )
    parser.add_argument(
        "--urls-only",
        action="store_true",
        help="print only verification URLs for valid VINs, one per line",
    )
    return parser


def collect_vins(args: argparse.Namespace) -> list[str]:
    vins = list(args.vins)
    if args.file:
        vins.extend(read_vins_from_file(args.file))
    if args.csv:
        vins.extend(read_vins_from_csv(args.csv, args.column))
    return vins


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        vins = collect_vins(args)
    except (VinError, OSError) as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 2

    if not vins:
        sys.stderr.write(
            "ERROR: no VINs given. Pass them as arguments, or use --file / --csv.\n"
        )
        return 2

    records = inspect_all(vins)

    if args.json:
        print(json.dumps(records, indent=2))
    elif args.urls_only:
        for record in records:
            if record["valid"]:
                print(record["window_sticker_url"] or record["nhtsa_url"])
    else:
        print(format_table(records))

    return 0 if all(record["valid"] for record in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
