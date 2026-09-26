#!/usr/bin/env python3
"""
Marketplace post-pack builder ("List.it")
=========================================

Turns a TractorHouse inventory export into ready-to-post Facebook Marketplace
packs: one folder per unit with the listing text and the crew's own photos,
plus a ``queue.csv`` tracker that Grant fills in as he posts and takes down.

Photos come from the crew's intake folder, never from TractorHouse. The
TractorHouse images carry Sandhills watermarks; do not download, crop, or
un-watermark them. Name intake photos ``<StockNumber>_<NN>.jpg`` (e.g.
``SN1001_01.jpg``, ``LOT042_03.jpg``) and they are matched to units by stock
number.

Posting stays a human click: the packs stop at "ready to publish". Meta does
not offer a listing API for Marketplace, and scripted posting violates its
terms.

Usage
-----
    python3 marketplace_pack.py --inventory ExportInventory.csv \\
        --photos "Photos/" --out marketplace_queue \\
        --phone "515-555-0100" --location "Ames, IA" \\
        --sale-note "Sells at Mid-Iowa online auction closing Oct 14"
"""

from __future__ import annotations

import argparse
import re
import shutil
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
# Canonical field -> accepted header spellings. Headers are compared after
# lower-casing and stripping everything but letters and digits, so
# "Stock #", "Stock Number" and "StockNumber" all resolve the same way.
COLUMN_ALIASES = {
    "stock": ["StockNumber", "Stock Number", "Stock #", "Stock No", "Lot Number", "Lot"],
    "year": ["Year", "Model Year"],
    "make": ["Make", "Manufacturer"],
    "model": ["Model"],
    "category": ["AssetCategory", "Category", "Type"],
    "price": ["ListPrice", "Price", "Asking Price", "Retail Price"],
    "hours": ["Hours", "Engine Hours", "Meter", "Meter Reading"],
    "serial": ["Serial Number", "Serial", "SerialNumber", "VIN"],
    "description": ["Description", "Comments", "Detailed Description"],
    "listing_url": ["Listing URL", "ListingURL", "URL", "Link"],
}
REQUIRED_FIELDS = ("stock", "year", "make", "model")

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png"}
MAX_PHOTOS = 10  # keep the pack to the best shots; first photo is the cover
TITLE_MAX = 99
DESCRIPTION_MAX = 1800  # leaves room under Marketplace's description limit

QUEUE_CSV = "queue.csv"
QUEUE_COLUMNS = [
    "StockNumber", "Status", "Title", "Price", "PhotoCount",
    "MarketplaceURL", "PostedDate", "TakenDownDate", "Notes",
]
STATUS_READY = "READY"
STATUS_NEEDS_PHOTOS = "NEEDS_PHOTOS"
STATUS_NEEDS_PRICE = "NEEDS_PRICE"


class PackError(RuntimeError):
    """Raised when an input is missing or the wrong shape."""


@dataclass
class Unit:
    stock: str
    year: str
    make: str
    model: str
    category: str = ""
    price: float | None = None
    hours: float | None = None
    serial: str = ""
    description: str = ""
    listing_url: str = ""
    photos: list[Path] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Load                                                                         #
# --------------------------------------------------------------------------- #
def _norm(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(header).lower())


def resolve_columns(columns) -> dict[str, str]:
    """Map canonical field names to the actual headers present in the export."""
    by_norm = {_norm(c): c for c in columns}
    resolved = {}
    for fld, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if _norm(alias) in by_norm:
                resolved[fld] = by_norm[_norm(alias)]
                break
    missing = [f for f in REQUIRED_FIELDS if f not in resolved]
    if missing:
        raise PackError(
            f"Inventory export is missing required field(s): {', '.join(missing)}. "
            f"Found columns: {', '.join(map(str, columns))}. "
            "Add the new header spelling to COLUMN_ALIASES."
        )
    return resolved


def _text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    # Years and stock numbers often arrive as floats ("2019.0").
    return text[:-2] if re.fullmatch(r"\d+\.0", text) else text


def _number(value) -> float | None:
    if isinstance(value, str):
        value = re.sub(r"[^0-9.]", "", value)
    num = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(num) or num <= 0 else float(num)


def load_units(path: Path) -> list[Unit]:
    if not path.exists():
        raise PackError(f"Inventory export '{path}' was not found.")
    try:
        frame = pd.read_csv(path, dtype=str)
    except Exception as exc:
        raise PackError(f"Could not parse '{path.name}': {exc}") from exc
    if frame.empty:
        raise PackError(f"'{path.name}' contains no data rows.")

    cols = resolve_columns(frame.columns)
    units, seen = [], set()
    for _, row in frame.iterrows():
        get = lambda f: row[cols[f]] if f in cols else None  # noqa: E731
        stock = _text(get("stock"))
        if not stock or stock in seen:
            continue
        seen.add(stock)
        units.append(
            Unit(
                stock=stock,
                year=_text(get("year")),
                make=_text(get("make")),
                model=_text(get("model")),
                category=_text(get("category")),
                price=_number(get("price")),
                hours=_number(get("hours")),
                serial=_text(get("serial")),
                description=_text(get("description")),
                listing_url=_text(get("listing_url")),
            )
        )
    return units


# --------------------------------------------------------------------------- #
# Photos                                                                       #
# --------------------------------------------------------------------------- #
_PHOTO_RE = re.compile(r"^(?P<stock>.+?)[_-](?P<seq>\d{1,3})$")


def _stock_key(stock: str) -> str:
    """Case-insensitive key that treats 'LOT042', 'lot42' and '42' alike."""
    key = stock.strip().lower()
    key = re.sub(r"^lot", "", key)
    if key.isdigit():
        key = key.lstrip("0") or "0"
    return key


def index_photos(photo_dir: Path) -> dict[str, list[Path]]:
    """Group intake photos by stock key, ordered by their sequence number."""
    if not photo_dir.is_dir():
        raise PackError(f"Photo folder '{photo_dir}' was not found.")
    grouped: dict[str, list[tuple[int, Path]]] = {}
    for path in photo_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in PHOTO_EXTENSIONS:
            continue
        match = _PHOTO_RE.match(path.stem)
        if not match:
            continue
        key = _stock_key(match["stock"])
        grouped.setdefault(key, []).append((int(match["seq"]), path))
    return {k: [p for _, p in sorted(v)] for k, v in grouped.items()}


# --------------------------------------------------------------------------- #
# Listing text                                                                 #
# --------------------------------------------------------------------------- #
def build_title(unit: Unit) -> str:
    parts = [unit.year, unit.make, unit.model]
    title = " ".join(p for p in parts if p)
    if unit.hours:
        title += f", {unit.hours:,.0f} hrs"
    return title[:TITLE_MAX].rstrip(" ,")


def build_description(
    unit: Unit, phone: str = "", location: str = "", sale_note: str = ""
) -> str:
    lines = [build_title(unit)]
    specs = []
    if unit.hours:
        specs.append(f"Hours: {unit.hours:,.0f}")
    if unit.serial:
        specs.append(f"Serial: {unit.serial}")
    if unit.category:
        specs.append(f"Category: {unit.category}")
    specs.append(f"Stock #: {unit.stock}")
    lines += ["", *specs]
    if unit.description:
        lines += ["", unit.description]
    if sale_note:
        lines += ["", sale_note]
    if unit.listing_url:
        lines += ["", f"Full details and more photos: {unit.listing_url}"]
    contact = " | ".join(p for p in (f"Call/text {phone}" if phone else "", location) if p)
    if contact:
        lines += ["", contact]
    text = "\n".join(lines)
    return text if len(text) <= DESCRIPTION_MAX else text[: DESCRIPTION_MAX - 3] + "..."


def unit_status(unit: Unit) -> str:
    if not unit.photos:
        return STATUS_NEEDS_PHOTOS
    if unit.price is None:
        return STATUS_NEEDS_PRICE
    return STATUS_READY


# --------------------------------------------------------------------------- #
# Write packs                                                                  #
# --------------------------------------------------------------------------- #
def _safe_dirname(stock: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", stock)


def write_pack(unit: Unit, out_dir: Path, **text_opts) -> Path:
    pack = out_dir / _safe_dirname(unit.stock)
    if pack.exists():
        shutil.rmtree(pack)
    pack.mkdir(parents=True)
    for i, src in enumerate(unit.photos, start=1):
        shutil.copy2(src, pack / f"{i:02d}{src.suffix.lower()}")
    price = f"{unit.price:,.0f}" if unit.price else "(set before posting)"
    listing = (
        f"TITLE\n{build_title(unit)}\n\n"
        f"PRICE\n{price}\n\n"
        f"CATEGORY\n{unit.category or 'Tools & equipment'}\n\n"
        f"CONDITION\nUsed\n\n"
        f"DESCRIPTION\n{build_description(unit, **text_opts)}\n"
    )
    (pack / "listing.txt").write_text(listing, encoding="utf-8")
    return pack


def build_queue(
    inventory: Path,
    photo_dir: Path,
    out_dir: Path,
    phone: str = "",
    location: str = "",
    sale_note: str = "",
    max_photos: int = MAX_PHOTOS,
) -> "pd.DataFrame":
    units = load_units(inventory)
    photos = index_photos(photo_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Preserve Grant's posting log across re-runs.
    queue_path = out_dir / QUEUE_CSV
    prior = {}
    if queue_path.exists():
        old = pd.read_csv(queue_path, dtype=str).fillna("")
        prior = {r["StockNumber"]: r for _, r in old.iterrows()}

    rows = []
    for unit in units:
        unit.photos = photos.get(_stock_key(unit.stock), [])[:max_photos]
        status = unit_status(unit)
        if status != STATUS_NEEDS_PHOTOS:
            write_pack(unit, out_dir, phone=phone, location=location, sale_note=sale_note)
        row = {
            "StockNumber": unit.stock,
            "Status": status,
            "Title": build_title(unit),
            "Price": f"{unit.price:.0f}" if unit.price else "",
            "PhotoCount": len(unit.photos),
            "MarketplaceURL": "", "PostedDate": "", "TakenDownDate": "", "Notes": "",
        }
        old = prior.get(unit.stock)
        if old is not None:
            for col in ("MarketplaceURL", "PostedDate", "TakenDownDate", "Notes"):
                row[col] = old.get(col, "")
            if row["TakenDownDate"]:
                row["Status"] = "TAKEN_DOWN"
            elif row["MarketplaceURL"]:
                row["Status"] = "POSTED"
        rows.append(row)

    # Units already posted that dropped out of inventory must come down.
    current = {u.stock for u in units}
    for stock, old in prior.items():
        if stock in current:
            continue
        row = {c: old.get(c, "") for c in QUEUE_COLUMNS}
        if old.get("MarketplaceURL") and not old.get("TakenDownDate"):
            row["Status"] = "TAKE_DOWN"
        rows.append(row)

    queue = pd.DataFrame(rows, columns=QUEUE_COLUMNS)
    queue.to_csv(queue_path, index=False)
    return queue


# --------------------------------------------------------------------------- #
# Entrypoint                                                                   #
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--inventory", required=True, type=Path,
                        help="TractorHouse ExportInventory CSV")
    parser.add_argument("--photos", required=True, type=Path,
                        help="Crew photo intake folder (<Stock>_<NN>.jpg)")
    parser.add_argument("--out", default=Path("marketplace_queue"), type=Path)
    parser.add_argument("--phone", default="")
    parser.add_argument("--location", default="")
    parser.add_argument("--sale-note", default="",
                        help="Line added to every description, e.g. auction close date")
    parser.add_argument("--max-photos", type=int, default=MAX_PHOTOS)
    args = parser.parse_args(argv)

    try:
        queue = build_queue(
            args.inventory, args.photos, args.out,
            phone=args.phone, location=args.location,
            sale_note=args.sale_note, max_photos=args.max_photos,
        )
    except PackError as exc:
        sys.stderr.write(f"!! PACK BUILD HALTED: {exc}\n")
        return 1

    counts = queue["Status"].value_counts().to_dict()
    print(f"Wrote {len(queue)} units to {args.out / QUEUE_CSV}")
    for status, n in sorted(counts.items()):
        print(f"  {status:<13} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
