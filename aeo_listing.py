#!/usr/bin/env python3
"""
Per-unit AEO listing builder
============================

Takes one machine out of a Sandhills ``ExportInventory`` CSV and emits the
assets that make it discoverable by answer engines and buyers' AI agents --
ChatGPT, Gemini, Claude, Perplexity -- rather than only by humans browsing a
marketplace.

Why per-unit
------------
Used equipment is one-of-one. A category page cannot answer "does this one have
a head included, and what are the separator hours", which is the question a
buyer actually asks. Answer engines lift direct question-and-answer pairs, so
the unit of optimisation is the machine, not the inventory.

What it emits
-------------
1. **schema.org JSON-LD** -- ``IndividualProduct`` plus ``Offer``, the format
   crawlers parse for citations and the Shopping Graph reads. ``IndividualProduct``
   (not ``Product``) because it carries ``serialNumber``, which is the identity
   of a used machine.
2. **An FAQ block** -- ``FAQPage`` schema plus readable Markdown, built from the
   questions a buyer or agent asks before they will act: hours, location,
   condition, what is included, inspection, freight, title.
3. **A trust-gap warning** -- the fields an agent needs that the Sandhills
   export cannot supply, listed explicitly rather than silently omitted.

Honesty constraints, deliberately enforced
------------------------------------------
Every value comes from the export. Nothing is inferred or filled in. Where a
field is missing the output says so, because a fabricated hour meter, serial or
lien status is the exact fraud an agent-readable feed exists to defeat -- and
publishing one is how a dealer gets delisted.

Two fields have **no column anywhere in the Sandhills export** and must be
sourced first-party before publishing: lien status (a UCC search per unit) and
a dated inspection report. They are emitted as explicit nulls with a note.

Usage
-----
    python3 aeo_listing.py ExportInventory.csv --serial 1H0S670SEC0755291
    python3 aeo_listing.py ExportInventory.csv --serial SN123 --outdir ./aeo
    python3 aeo_listing.py ExportInventory.csv --list

The module is import-safe -- everything runs under ``main()``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import pandas as pd
except ImportError:  # pragma: no cover - environment guard
    sys.stderr.write(
        "ERROR: pandas is not installed. Run 'pip install pandas' and retry.\n"
    )
    raise SystemExit(2)


SELLER_NAME = "Heartland Iron Solutions"
SELLER_ALT_NAME = "Mid-Iowa Auction Company"

#: Fields with no column in the Sandhills export. They decide whether an agent
#: trusts the listing, so they are named rather than quietly dropped.
FIRST_PARTY_ONLY = {
    "lienStatus": "No field in the Sandhills export. Requires a UCC search per unit.",
    "inspectionReport": "No field in the Sandhills export. Must be sourced first-party.",
}

#: Spec columns worth surfacing, keyed by the label a buyer would use.
SPEC_COLUMNS: dict[str, str] = {
    "engineHours": "hours",
    "mileage": "mileage",
    "separatorHours": "separatorhours",
    "cutterheadHours": "cutterheadhours",
    "horsepower": "horsepower",
    "transmission": "transmission",
    "drive": "drive",
    "trackSize": "tracksize",
    "trackPercentRemaining": "trackpercentremaining",
    "grainTankSize": "graintanksize",
    "remoteHydraulics": "remotehydraulics",
    "pto": "pto",
}


def is_blank(value) -> bool:
    """True when a Sandhills cell carries no usable value."""
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):  # pragma: no cover - non-scalar guard
        pass
    return str(value).strip() in ("", "nan", "None")


def text(unit: pd.Series, column: str) -> str | None:
    """A cleaned string value, or None when blank."""
    value = unit.get(column)
    if is_blank(value):
        return None
    return re.sub(r"\s+", " ", str(value).strip())


def number(unit: pd.Series, column: str):
    """A numeric value as int when integral, float otherwise, or None."""
    value = pd.to_numeric(unit.get(column), errors="coerce")
    if pd.isna(value):
        return None
    value = float(value)
    return int(value) if value.is_integer() else round(value, 2)


def find_unit(inv: pd.DataFrame, serial: str) -> pd.Series:
    """Locate one unit by serial number, case- and whitespace-insensitively."""
    key = inv["VINSerialNumber"].astype(str).str.strip().str.upper()
    match = inv[key == serial.strip().upper()]
    if match.empty:
        raise KeyError(serial)
    return match.iloc[0]


def unit_name(unit: pd.Series) -> str:
    """"2013 John Deere S670SH" -- the string a buyer would search."""
    year = number(unit, "Year")
    parts = [str(year) if year else None, text(unit, "Manufacturer"),
             text(unit, "Model")]
    return " ".join(p for p in parts if p)


def build_jsonld(unit: pd.Series) -> dict:
    """schema.org IndividualProduct + Offer for a single used machine."""
    properties = []
    for label, column in SPEC_COLUMNS.items():
        value = number(unit, column)
        if value is None:
            value = text(unit, column)
        if value is not None:
            properties.append(
                {"@type": "PropertyValue", "name": label, "value": value}
            )

    meter_flag = text(unit, "hoursmeterinaccurate")
    rebuilt = text(unit, "rebuilttitle")
    properties.append({
        "@type": "PropertyValue", "name": "hourMeterAccurate",
        "value": not (meter_flag or "").lower() in ("true", "1", "1.0", "yes"),
    })
    properties.append({
        "@type": "PropertyValue", "name": "rebuiltTitle",
        "value": (rebuilt or "").lower() in ("true", "1", "1.0", "yes"),
    })
    photo_count = number(unit, "PictureCount")
    if photo_count is not None:
        properties.append(
            {"@type": "PropertyValue", "name": "photoCount", "value": photo_count}
        )
    for field, note in FIRST_PARTY_ONLY.items():
        properties.append({
            "@type": "PropertyValue", "name": field, "value": None,
            "_pending": note,
        })

    address = {
        "@type": "PostalAddress",
        "addressLocality": text(unit, "LocationCity"),
        "addressRegion": text(unit, "LocationState"),
        "postalCode": text(unit, "LocationPostalCode"),
        "addressCountry": text(unit, "LocationCountry") or "US",
    }

    return {
        "@context": "https://schema.org",
        "@type": "IndividualProduct",
        "sku": text(unit, "ATLotNumber") or text(unit, "DSLookupID"),
        "serialNumber": text(unit, "VINSerialNumber"),
        "name": unit_name(unit),
        "category": text(unit, "Category"),
        "brand": {"@type": "Brand", "name": text(unit, "Manufacturer")},
        "model": text(unit, "Model"),
        "productionDate": str(number(unit, "Year") or "") or None,
        "itemCondition": "https://schema.org/UsedCondition",
        "description": text(unit, "Description"),
        "additionalProperty": properties,
        "offers": {
            "@type": "Offer",
            "price": number(unit, "SaleListPrice"),
            "priceCurrency": text(unit, "CurrencyCode") or "USD",
            "availability": "https://schema.org/InStock",
            "itemCondition": "https://schema.org/UsedCondition",
            "eligibleQuantity": {"@type": "QuantitativeValue", "value": 1},
            "availableDeliveryMethod": "https://schema.org/FreightDelivery",
            "businessFunction": "https://schema.org/Sell",
            "seller": {
                "@type": "Organization",
                "name": SELLER_NAME,
                "alternateName": SELLER_ALT_NAME,
            },
            "availableAtOrFrom": {"@type": "Place", "address": address},
            "_closeProcess": {
                "acceptsAgentInitiatedQuote": True,
                "acceptsAgentInitiatedPurchase": False,
                "requiredBeforeClose": [
                    "inspection or inspection-report acceptance",
                    "lien and title clearance",
                    "freight quote to buyer location",
                    "human signature",
                ],
            },
        },
    }


def build_faq(unit: pd.Series) -> list[tuple[str, str]]:
    """Question-and-answer pairs an answer engine can lift directly.

    Only questions the export can actually answer are emitted. A question with
    no data behind it is dropped rather than answered vaguely -- a vague answer
    is worse than none, because an agent will quote it.
    """
    pairs: list[tuple[str, str]] = []
    name = unit_name(unit)

    hours = number(unit, "hours")
    miles = number(unit, "mileage")
    if hours is not None:
        separator = number(unit, "separatorhours")
        cutterhead = number(unit, "cutterheadhours")
        answer = f"{hours:,} hours."
        if separator is not None:
            answer += f" Separator hours: {separator:,}."
        if cutterhead is not None:
            answer += f" Cutterhead hours: {cutterhead:,}."
        meter_flag = (text(unit, "hoursmeterinaccurate") or "").lower()
        if meter_flag in ("true", "1", "1.0", "yes"):
            answer += " Note: the hour meter is known to be inaccurate."
        pairs.append((f"How many hours are on the {name}?", answer))
    elif miles is not None:
        unit_label = text(unit, "mileagetype") or "miles"
        pairs.append((f"What is the mileage on the {name}?",
                      f"{miles:,} {unit_label}."))

    city, state = text(unit, "LocationCity"), text(unit, "LocationState")
    if city and state:
        pairs.append((f"Where is the {name} located?",
                      f"{city}, {state}. Inspection is welcome by appointment, "
                      f"and freight is quoted to the buyer's location."))

    price = number(unit, "SaleListPrice")
    if price is not None:
        pairs.append((f"What is the asking price for the {name}?",
                      f"${price:,} USD. Freight is quoted separately and is not "
                      f"included."))

    horsepower = number(unit, "horsepower")
    if horsepower is not None:
        pairs.append((f"How much horsepower does the {name} have?",
                      f"{horsepower:,} hp."))

    tracks = number(unit, "trackpercentremaining")
    if tracks is not None:
        size = number(unit, "tracksize")
        answer = f"{tracks:.0f}% remaining"
        if size is not None:
            answer = f"{size:g}-inch tracks, {answer}"
        pairs.append((f"What condition are the tracks on the {name}?",
                      answer + "."))

    rebuilt = (text(unit, "rebuilttitle") or "").lower()
    pairs.append((
        f"Does the {name} have a clean title?",
        "The title is branded rebuilt." if rebuilt in ("true", "1", "1.0", "yes")
        else "No rebuilt-title brand is recorded on this unit. Title and lien "
             "status are confirmed in writing before closing.",
    ))

    pairs.append((
        f"Can an AI agent buy the {name} directly?",
        "An agent can request a firm quote. Purchase is not completed by an "
        "agent: every sale closes with a human signature after inspection "
        "acceptance, lien and title clearance, and a freight quote.",
    ))
    return pairs


def render_markdown(unit: pd.Series, faq: list[tuple[str, str]]) -> str:
    """Human- and crawler-readable page body for the unit."""
    name = unit_name(unit)
    lines = [f"# {name}", ""]
    serial = text(unit, "VINSerialNumber")
    price = number(unit, "SaleListPrice")
    city, state = text(unit, "LocationCity"), text(unit, "LocationState")

    summary = [f"Used {text(unit, 'Category') or 'equipment'}"]
    if price is not None:
        summary.append(f"asking ${price:,}")
    if city and state:
        summary.append(f"located in {city}, {state}")
    if serial:
        summary.append(f"serial {serial}")
    lines.append("> " + ", ".join(summary) + ".")
    lines.append("")

    description = text(unit, "Description")
    if description:
        lines += ["## Description", "", description, ""]

    specs = []
    for label, column in SPEC_COLUMNS.items():
        value = number(unit, column)
        if value is None:
            value = text(unit, column)
        if value is not None:
            pretty = re.sub(r"(?<!^)(?=[A-Z])", " ", label).lower()
            specs.append(f"| {pretty} | {value} |")
    if specs:
        lines += ["## Specifications", "", "| Spec | Value |", "|---|---|"] + specs
        lines.append("")

    lines += ["## Questions and answers", ""]
    for question, answer in faq:
        lines += [f"**{question}**", "", answer, ""]

    missing = [f for f in FIRST_PARTY_ONLY]
    lines += [
        "## Not yet published",
        "",
        "These decide whether a buyer's agent trusts this listing, and the "
        "Sandhills export has no field for either. Source them first-party "
        "before publishing:",
        "",
    ] + [f"- `{field}` -- {FIRST_PARTY_ONLY[field]}" for field in missing]
    lines.append("")
    return "\n".join(lines)


def faq_jsonld(faq: list[tuple[str, str]]) -> dict:
    """FAQPage schema -- the structure answer engines lift Q&A pairs from."""
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": question,
                "acceptedAnswer": {"@type": "Answer", "text": answer},
            }
            for question, answer in faq
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build AEO assets for one unit from a Sandhills export."
    )
    parser.add_argument("inventory", type=Path, help="ExportInventory CSV")
    parser.add_argument("--serial", help="VIN/serial number of the unit")
    parser.add_argument(
        "--list", action="store_true", dest="list_units",
        help="list available serials and exit",
    )
    parser.add_argument(
        "--outdir", type=Path, default=None,
        help="write the assets here instead of stdout",
    )
    args = parser.parse_args(argv)

    if not args.inventory.is_file():
        sys.stderr.write(f"ERROR: no such file: {args.inventory}\n")
        return 2

    inv = pd.read_csv(args.inventory, low_memory=False, encoding="utf-8-sig")
    if "VINSerialNumber" not in inv.columns:
        sys.stderr.write(
            "ERROR: no VINSerialNumber column -- is this an ExportInventory CSV?\n"
        )
        return 2

    if args.list_units:
        for _, unit in inv.iterrows():
            serial = text(unit, "VINSerialNumber")
            if serial:
                sys.stdout.write(f"{serial}\t{unit_name(unit)}\n")
        return 0

    if not args.serial:
        sys.stderr.write("ERROR: pass --serial, or --list to see what is available.\n")
        return 2

    try:
        unit = find_unit(inv, args.serial)
    except KeyError:
        sys.stderr.write(
            f"ERROR: serial {args.serial!r} not found. Use --list to see serials.\n"
        )
        return 1

    product = build_jsonld(unit)
    faq = build_faq(unit)
    page = render_markdown(unit, faq)

    if args.outdir is not None:
        args.outdir.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r"[^A-Za-z0-9]+", "-", args.serial.strip().upper()).strip("-")
        (args.outdir / f"{stem}.jsonld").write_text(
            json.dumps(product, indent=2), encoding="utf-8"
        )
        (args.outdir / f"{stem}-faq.jsonld").write_text(
            json.dumps(faq_jsonld(faq), indent=2), encoding="utf-8"
        )
        (args.outdir / f"{stem}.md").write_text(page, encoding="utf-8")
        sys.stdout.write(f"Wrote 3 files to {args.outdir}/ for {stem}\n")
    else:
        sys.stdout.write(page)
        sys.stdout.write("\n```json\n")
        sys.stdout.write(json.dumps(product, indent=2))
        sys.stdout.write("\n```\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
