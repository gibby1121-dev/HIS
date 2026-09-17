#!/usr/bin/env python3
"""
Google Merchant Center feed builder
===================================

Turns a Sandhills ``ExportInventory`` CSV into a Google Merchant Center product
feed, which is the on-ramp to Google's agentic shopping surfaces (AI Mode,
Gemini, and UCP-powered checkout).

The hard part is not the Merchant Center signup -- it is mapping a 400-column
Sandhills export onto Merchant Center's attribute schema for goods that are
one-of-one, have no GTIN, and sell for six figures. That mapping is what this
module is.

Read this before you run it
---------------------------
**Merchant Center requires a ``link`` and an ``image_link`` for every item, and
both must resolve on a domain you have verified and claimed.** There is no way
around that: a feed of items whose landing pages do not exist will be
disapproved. So the website is a hard prerequisite, not a nice-to-have.

Pass ``--base-url`` to point at where the per-unit pages will live. Run
``aeo_listing.py`` to generate those pages. Until the pages are live, use
``--dry-run`` to see what the feed will contain and how many rows would be
rejected.

One-of-a-kind goods
-------------------
Used equipment has no GTIN. Google's documented path for this is to set
``identifier_exists`` to ``no``, which declares the absence rather than leaving
a required field blank. Submitting ``identifier_exists=no`` *together with* a
GTIN is read as contradictory data, so this module emits brand and MPN (which
Google accepts alongside the declaration) and never a fabricated GTIN.

``condition`` is ``used`` for every row, and every item ships as a single unit.

Usage
-----
    python3 merchant_feed.py ExportInventory.csv --dry-run
    python3 merchant_feed.py ExportInventory.csv \
        --base-url https://www.example.com/equipment --out feed.tsv

The module is import-safe -- everything runs under ``main()``.
"""

from __future__ import annotations

import argparse
import csv
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


#: Merchant Center columns, in feed order.
FEED_COLUMNS = (
    "id", "title", "description", "link", "image_link", "availability",
    "price", "condition", "brand", "mpn", "identifier_exists",
    "google_product_category", "product_type", "shipping_label",
    "custom_label_0", "custom_label_1",
)

#: Sandhills InventoryType -> Google product taxonomy path.
#: Trucks and trailers belong under Vehicles; everything else under Heavy
#: Machinery. Google accepts the full text path in place of the numeric ID.
CATEGORY_MAP = {
    "Trucks": "Vehicles & Parts > Vehicles > Motor Vehicles > Trucks",
    "Trailers": "Vehicles & Parts > Vehicles > Trailers",
    "Motorsports": "Vehicles & Parts > Vehicles > Motor Vehicles",
    "Recreational_Vehicles": "Vehicles & Parts > Vehicles > Motor Vehicles",
}
DEFAULT_CATEGORY = "Business & Industrial > Heavy Machinery"

#: Below this, a listing is too thin to be worth a feed row -- Merchant Center
#: will take it but a buyer's agent has nothing to act on.
MIN_TITLE_PARTS = 2
MAX_TITLE = 150
MAX_DESCRIPTION = 5000


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


def clean(value) -> str:
    """Collapse whitespace; empty string when blank."""
    if is_blank(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def slug(value: str) -> str:
    """URL- and filename-safe form of a serial number."""
    return re.sub(r"[^A-Za-z0-9]+", "-", value.strip().upper()).strip("-")


def build_title(unit: pd.Series) -> str:
    """Year + make + model + category, which is how buyers phrase the search."""
    year = pd.to_numeric(unit.get("Year"), errors="coerce")
    parts = [
        "" if pd.isna(year) else f"{int(year)}",
        clean(unit.get("Manufacturer")),
        clean(unit.get("Model")),
    ]
    parts = [p for p in parts if p]
    if len(parts) < MIN_TITLE_PARTS:
        return ""
    title = " ".join(parts)
    category = clean(unit.get("Category"))
    if category:
        # "Tractors - 300 HP or Greater" -> "Tractors"
        head = category.split("-")[0].strip()
        if head and head.lower() not in title.lower():
            title = f"{title} {head}"
    return title[:MAX_TITLE]


def build_description(unit: pd.Series) -> str:
    """The seller's description, with the key specs appended if absent from it.

    Merchant Center requires a description, and a thin one costs impressions.
    Specs already present in the text are not repeated.

    Returns an empty string when the unit has neither seller text nor any
    substantive spec. A serial number on its own is not a description -- it
    would pass Merchant Center's validation and tell a buyer nothing, so such a
    unit is better skipped and fixed in Sandhills than listed hollow.
    """
    body = clean(unit.get("Description"))
    substantive = []
    hours = pd.to_numeric(unit.get("hours"), errors="coerce")
    miles = pd.to_numeric(unit.get("mileage"), errors="coerce")
    if not pd.isna(hours) and "hour" not in body.lower():
        substantive.append(f"{int(hours):,} hours")
    if not pd.isna(miles) and "mile" not in body.lower():
        substantive.append(f"{int(miles):,} miles")
    city, state = clean(unit.get("LocationCity")), clean(unit.get("LocationState"))
    if city and state and city.lower() not in body.lower():
        substantive.append(f"located in {city}, {state}")

    if not body and not substantive:
        return ""

    extras = list(substantive)
    serial = clean(unit.get("VINSerialNumber"))
    if serial and serial.lower() not in body.lower():
        extras.append(f"serial {serial}")

    parts = [p for p in (body, ". ".join(extras)) if p]
    description = ". ".join(parts).replace("..", ".")
    return description[:MAX_DESCRIPTION]


def build_row(unit: pd.Series, base_url: str) -> tuple[dict | None, str]:
    """One feed row, or ``(None, reason)`` when the unit cannot be listed."""
    serial = clean(unit.get("VINSerialNumber"))
    if not serial:
        return None, "no serial number (needed as the feed id)"

    title = build_title(unit)
    if not title:
        return None, "cannot build a title (missing year, make and model)"

    price = pd.to_numeric(unit.get("SaleListPrice"), errors="coerce")
    if pd.isna(price) or price <= 0:
        return None, "no asking price"

    photos = pd.to_numeric(unit.get("PictureCount"), errors="coerce")
    if pd.isna(photos) or photos < 1:
        return None, "no photos (image_link is required)"

    description = build_description(unit)
    if not description:
        return None, "no description"

    inventory_type = clean(unit.get("InventoryType"))
    stem = slug(serial)
    currency = clean(unit.get("CurrencyCode")) or "USD"

    return {
        "id": stem,
        "title": title,
        "description": description,
        "link": f"{base_url.rstrip('/')}/{stem}",
        "image_link": f"{base_url.rstrip('/')}/{stem}/photo-1.jpg",
        "availability": "in_stock",
        "price": f"{price:.2f} {currency}",
        "condition": "used",
        "brand": clean(unit.get("Manufacturer")),
        "mpn": clean(unit.get("Model")),
        # Declares the absence of a GTIN rather than leaving it blank. Never
        # paired with a GTIN -- Google reads that combination as contradictory.
        "identifier_exists": "no",
        "google_product_category": CATEGORY_MAP.get(
            inventory_type, DEFAULT_CATEGORY
        ),
        "product_type": clean(unit.get("Category")),
        "shipping_label": "freight_quote",
        "custom_label_0": inventory_type,
        "custom_label_1": clean(unit.get("LocationState")),
    }, ""


def build_feed(inv: pd.DataFrame, base_url: str) -> tuple[list[dict], dict[str, int]]:
    """Feed rows plus a tally of why each skipped unit was skipped."""
    rows: list[dict] = []
    skipped: dict[str, int] = {}
    for _, unit in inv.iterrows():
        row, reason = build_row(unit, base_url)
        if row is None:
            skipped[reason] = skipped.get(reason, 0) + 1
        else:
            rows.append(row)
    return rows, skipped


def write_tsv(rows: list[dict], path: Path) -> None:
    """Tab-separated feed, which Merchant Center accepts directly."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(FEED_COLUMNS), delimiter="\t",
            quoting=csv.QUOTE_MINIMAL, extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a Google Merchant Center feed from a Sandhills export."
    )
    parser.add_argument("inventory", type=Path, help="ExportInventory CSV")
    parser.add_argument(
        "--base-url",
        help="where per-unit pages live, e.g. https://example.com/equipment",
    )
    parser.add_argument("--out", type=Path, default=None, help="write the TSV here")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="report what the feed would contain without needing a real base URL",
    )
    args = parser.parse_args(argv)

    if not args.inventory.is_file():
        sys.stderr.write(f"ERROR: no such file: {args.inventory}\n")
        return 2
    if not args.dry_run and not args.base_url:
        sys.stderr.write(
            "ERROR: pass --base-url (the domain must be verified and claimed in\n"
            "Merchant Center, and the per-unit pages must resolve), or use\n"
            "--dry-run to preview the feed first.\n"
        )
        return 2

    inv = pd.read_csv(args.inventory, low_memory=False, encoding="utf-8-sig")
    base_url = args.base_url or "https://REPLACE-ME.example.com/equipment"
    rows, skipped = build_feed(inv, base_url)

    sys.stdout.write(f"{len(inv)} units in the export\n")
    sys.stdout.write(f"{len(rows)} listable in a Merchant Center feed\n")
    if skipped:
        sys.stdout.write(f"{sum(skipped.values())} skipped:\n")
        for reason, count in sorted(skipped.items(), key=lambda kv: -kv[1]):
            sys.stdout.write(f"  {count:4d}  {reason}\n")

    if args.dry_run:
        sys.stdout.write(
            "\nDry run -- nothing written. Every row needs a resolving link and\n"
            "image_link on a domain claimed in Merchant Center before submitting.\n"
        )
        return 0

    out = args.out or Path("merchant_feed.tsv")
    write_tsv(rows, out)
    sys.stdout.write(f"\nWrote {out} ({len(rows)} rows)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
