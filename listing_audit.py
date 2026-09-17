#!/usr/bin/env python3
"""
Sandhills listing audit
=======================

Reads a Sandhills ``ExportInventory`` CSV (and, optionally, a
``WebstatsListings`` CSV) and reports the listing defects that cost sales but
are invisible in the Sandhills UI.

Three checks
------------
1. **Filter exclusion.** The free-text description claims a feature while the
   structured field that drives the buyer's search filter is blank. Buyers who
   filter on that feature never see the unit at all. This is the highest-value
   check: it finds units that are effectively unlisted.
2. **Completeness.** Scores every unit against the fields a buyer (or a buyer's
   AI agent) needs before they will trust a used machine: serial, year, make,
   model, price, location, photos, usage hours/miles, description.
3. **Triage.** With webstats joined, ranks units on real demand -- detail views
   per day, click-through rate, watchlist adds -- penalised for days listed, so
   the units worth pushing separate from the units worth repricing.

Notes on the Sandhills exports
------------------------------
``DetailsViews``, ``Impressions``, ``TotalWatchlists`` and ``TotalClicksToCall``
are **30-day windows**, not lifetime totals (verified: views divided by
views-per-day equals 30 for the large majority of rows). ``DaysAging`` *is*
lifetime. Reading the first set as lifetime totals badly understates current
traffic on an old listing, so this module labels them explicitly.

``WebstatsListings`` can carry several rows per serial when a unit has been
relisted; the best-performing row per serial is kept. Rows with a blank serial
are dropped rather than joined, otherwise they cross-match and fan the join out.

Usage
-----
    python3 listing_audit.py ExportInventory.csv [WebstatsListings.csv]
    python3 listing_audit.py --out audit.md ExportInventory.csv Webstats.csv

The module is import-safe -- everything runs under ``main()``.
"""

from __future__ import annotations

import argparse
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


# --------------------------------------------------------------------------- #
# Check 1 -- filter exclusion
# --------------------------------------------------------------------------- #

#: (description pattern, structured fields that drive the filter, buyer-facing label)
#:
#: A contradiction is raised only when the text matches AND *every* listed field
#: is blank. Several features are spelled across more than one Sandhills column
#: (a PTO has both ``haspto`` and ``pto`` for the size), so any one of them being
#: populated means the unit is still reachable by filter.
FILTER_RULES: list[tuple[str, tuple[str, ...], str]] = [
    (r"\b(full cab|cab[\s/,]*(heat|air|a/?c)|c/?h/?a\b|enclosed cab|cab w)",
     ("cab",), "cab"),
    (r"\b(a/?c\b|air ?cond|cab air|heat ?(&|and|/) ?air)",
     ("cabair",), "cab A/C"),
    (r"\b(4wd|4x4|mfwd|four wheel drive|awd)\b",
     ("drive",), "4WD/drive"),
    (r"\bthumb\b", ("thumb",), "thumb"),
    (r"\b(extend ?-? ?a ?-? ?hoe|extendahoe)\b", ("extendahoe",), "ExtendaHoe"),
    (r"\b(quick ?-? ?attach|quick ?-? ?tach)\b", ("quickattach",), "quick attach"),
    (r"\bpto\b", ("haspto", "pto"), "PTO"),
    (r"\b(auto ?-? ?steer|autosteer|auto ?-? ?track|guidance|gps|rtk)\b",
     ("gps", "autoguidance", "autoguidanceready"), "GPS/guidance"),
    (r"\bride ?control\b", ("ridecontrol",), "ride control"),
    (r"\b(3 ?-? ?point|three ?-? ?point|3pt)\b", ("threepointhitch",), "3-point"),
    (r"\brops\b", ("ropstype",), "ROPS"),
    (r"\b(kernel ?processor|kp\b)", ("kernelprocessor",), "kernel processor"),
    (r"\brock ?trap\b", ("rocktrap",), "rock trap"),
    (r"\b(chopper|spreader)\b",
     ("rearattachment", "choppingcapability"), "chopper/spreader"),
    (r"\b(two ?speed|2 ?speed)\b", ("twospeed",), "two speed"),
    (r"\b(aux(iliary)? hyd)", ("hydraux",), "aux hydraulics"),
]

#: Fields a buyer or buyer's agent needs before trusting a used machine.
#: ``photos`` and ``usage`` are computed rather than read straight off a column.
COMPLETENESS_FIELDS = (
    "serial", "year", "make", "model", "price", "location", "photos",
    "usage", "description",
)

MIN_PHOTOS = 6


def is_blank(value) -> bool:
    """True when a Sandhills cell carries no usable value.

    Sandhills writes unset booleans as an empty cell and unset numerics
    inconsistently, so ``0`` is treated as a real value here (a ``thumb`` of 0
    means "no thumb", which is information) while empty strings and the string
    ``"nan"`` are not.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return True
    if pd.isna(value):
        return True
    return str(value).strip() in ("", "nan", "None")


def load_inventory(path: Path) -> pd.DataFrame:
    """Read an ExportInventory CSV, tolerating the UTF-8 BOM Sandhills emits."""
    return pd.read_csv(path, low_memory=False, encoding="utf-8-sig")


def _serial_key(series: pd.Series) -> pd.Series:
    """Normalise a serial column to a join key, blanking unusable values."""
    key = series.astype(str).str.strip().str.upper()
    return key.where(~key.isin(["NAN", "", "NONE", "0"]))


def find_filter_exclusions(inv: pd.DataFrame) -> pd.DataFrame:
    """Units whose description claims a feature their filter fields omit.

    Returns one row per (unit, feature) contradiction, with the asking price so
    the result can be sorted by what the defect is costing.
    """
    rows = []
    price = pd.to_numeric(inv.get("SaleListPrice"), errors="coerce")
    for idx, unit in inv.iterrows():
        text = " ".join(
            str(unit.get(col) or "") for col in ("Description", "DisplayName")
        )
        text = re.sub(r"\s+", " ", text).lower()
        if not text.strip():
            continue
        for pattern, fields, label in FILTER_RULES:
            if not re.search(pattern, text):
                continue
            present = [f for f in fields if f in inv.columns]
            if present and all(is_blank(unit.get(f)) for f in present):
                rows.append({
                    "serial": unit.get("VINSerialNumber"),
                    "year": unit.get("Year"),
                    "make": unit.get("Manufacturer"),
                    "model": unit.get("Model"),
                    "category": unit.get("Category"),
                    "price": price.get(idx),
                    "feature": label,
                    "blank_fields": ", ".join(present),
                })
    return pd.DataFrame(rows, columns=[
        "serial", "year", "make", "model", "category", "price",
        "feature", "blank_fields",
    ])


def score_completeness(inv: pd.DataFrame) -> pd.DataFrame:
    """Per-unit presence of each field a buyer needs, plus a total out of nine."""
    price = pd.to_numeric(inv.get("SaleListPrice"), errors="coerce")
    photos = pd.to_numeric(inv.get("PictureCount"), errors="coerce")

    def filled(column: str) -> pd.Series:
        if column not in inv.columns:
            return pd.Series(False, index=inv.index)
        return ~inv[column].map(is_blank)

    scored = pd.DataFrame({
        "serial": filled("VINSerialNumber"),
        "year": filled("Year"),
        "make": filled("Manufacturer"),
        "model": filled("Model"),
        "price": price.notna(),
        "location": filled("LocationPostalCode"),
        "photos": photos.fillna(0) >= MIN_PHOTOS,
        "usage": filled("hours") | filled("mileage"),
        "description": filled("Description"),
    }, index=inv.index)
    scored["score"] = scored[list(COMPLETENESS_FIELDS)].sum(axis=1)
    return scored


def join_webstats(inv: pd.DataFrame, stats: pd.DataFrame) -> pd.DataFrame:
    """One-to-one join of inventory to webstats on serial number.

    Blank serials are dropped on both sides -- joining them cross-matches every
    unnumbered unit against every other and fans the row count out. Where a
    serial appears more than once in webstats (a relisted unit), the row with
    the most detail views is kept.
    """
    inv = inv.copy()
    stats = stats.copy()
    inv["_sn"] = _serial_key(inv["VINSerialNumber"])
    stats["_sn"] = _serial_key(stats["SerialNumber"])

    numeric = [
        "DetailsViews", "DailyDetailViews", "Impressions", "TotalWatchlists",
        "EmailLeads", "TotalClicksToCall", "DaysAging",
    ]
    for column in numeric:
        if column in stats.columns:
            stats[column] = pd.to_numeric(stats[column], errors="coerce")
    if "ClickThroughRate" in stats.columns:
        stats["ctr"] = pd.to_numeric(
            stats["ClickThroughRate"].astype(str).str.rstrip("%"), errors="coerce"
        )

    stats = stats[stats["_sn"].notna()]
    if "DetailsViews" in stats.columns:
        stats = stats.sort_values("DetailsViews", ascending=False)
    stats = stats.drop_duplicates("_sn", keep="first")

    keep = ["_sn", "ctr"] + [c for c in numeric if c in stats.columns]
    keep = [c for c in keep if c in stats.columns]
    inv = inv[inv["_sn"].notna()].drop_duplicates("_sn", keep="first")
    return inv.merge(stats[keep], on="_sn", how="inner")


def triage(merged: pd.DataFrame) -> pd.DataFrame:
    """Rank joined units on live demand, penalised for time on the market.

    Weighted percentile ranks rather than raw values, so a combine and a skid
    steer stay comparable. High score with few calls means push it; high days
    listed with real traffic and no calls means reprice it.
    """
    out = merged.copy()
    out["price"] = pd.to_numeric(out.get("SaleListPrice"), errors="coerce")

    def pct(column: str) -> pd.Series:
        if column not in out.columns:
            return pd.Series(0.0, index=out.index)
        return out[column].rank(pct=True).fillna(0.0)

    out["demand_score"] = (
        pct("DailyDetailViews") * 0.40
        + pct("ctr") * 0.25
        + pct("TotalWatchlists") * 0.20
        + (1 - pct("DaysAging")) * 0.15
    ).round(3)
    return out.sort_values("demand_score", ascending=False)


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #

def render_report(
    inv: pd.DataFrame,
    exclusions: pd.DataFrame,
    completeness: pd.DataFrame,
    triaged: pd.DataFrame | None,
) -> str:
    """Assemble the Markdown audit."""
    lines: list[str] = ["# Sandhills listing audit", ""]
    lines.append(f"{len(inv)} units in the export.")
    lines.append("")

    lines.append("## 1. Filter exclusion -- units invisible to a filtered search")
    lines.append("")
    if exclusions.empty:
        lines.append("No contradictions found.")
    else:
        affected = exclusions.drop_duplicates("serial")
        total = affected["price"].sum(skipna=True)
        lines.append(
            f"**{len(affected)} units** claim a feature in the description that "
            f"their structured field leaves blank, so buyers filtering on it "
            f"never see the unit. Combined asking price **${total:,.0f}**."
        )
        lines.append("")
        lines.append("| Year | Make | Model | Price | Missing filter field(s) |")
        lines.append("|---|---|---|---:|---|")
        grouped = exclusions.groupby(
            ["serial", "year", "make", "model", "price"], dropna=False
        )["feature"].apply(lambda s: ", ".join(sorted(set(s)))).reset_index()
        grouped = grouped.sort_values("price", ascending=False, na_position="last")
        for _, row in grouped.iterrows():
            year = "" if pd.isna(row["year"]) else f"{row['year']:.0f}"
            price = "" if pd.isna(row["price"]) else f"${row['price']:,.0f}"
            lines.append(
                f"| {year} | {row['make']} | {row['model']} | {price} "
                f"| {row['feature']} |"
            )
    lines.append("")

    lines.append("## 2. Completeness")
    lines.append("")
    total_units = len(completeness)
    for field in COMPLETENESS_FIELDS:
        filled = int(completeness[field].sum())
        pct = 100.0 * filled / total_units if total_units else 0.0
        lines.append(f"- `{field}` -- {filled}/{total_units} ({pct:.1f}%)")
    complete = int((completeness["score"] == len(COMPLETENESS_FIELDS)).sum())
    lines.append("")
    lines.append(
        f"**{complete} of {total_units}** units carry all "
        f"{len(COMPLETENESS_FIELDS)} fields."
    )
    lines.append("")

    lines.append("## 3. Triage")
    lines.append("")
    if triaged is None:
        lines.append("No webstats supplied -- pass a WebstatsListings CSV to rank demand.")
    else:
        lines.append(
            "Views, impressions, watchlists and calls below are **30-day "
            "windows**. Days listed is lifetime."
        )
        lines.append("")
        lines.append(
            "| Year | Make | Model | Price | Views/day | CTR % | Watch | Calls | Days |"
        )
        lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|")
        for _, row in triaged.head(20).iterrows():
            year = "" if pd.isna(row.get("Year")) else f"{row['Year']:.0f}"
            price = "" if pd.isna(row.get("price")) else f"${row['price']:,.0f}"

            def num(key: str, fmt: str = "{:.0f}") -> str:
                value = row.get(key)
                return "" if value is None or pd.isna(value) else fmt.format(value)

            lines.append(
                f"| {year} | {row.get('Manufacturer')} | {row.get('Model')} "
                f"| {price} | {num('DailyDetailViews', '{:.2f}')} "
                f"| {num('ctr', '{:.1f}')} | {num('TotalWatchlists')} "
                f"| {num('TotalClicksToCall')} | {num('DaysAging')} |"
            )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit a Sandhills ExportInventory CSV for listing defects."
    )
    parser.add_argument("inventory", type=Path, help="ExportInventory CSV")
    parser.add_argument(
        "webstats", type=Path, nargs="?", default=None,
        help="optional WebstatsListings CSV, to rank demand",
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help="write the Markdown report here instead of stdout",
    )
    args = parser.parse_args(argv)

    if not args.inventory.is_file():
        sys.stderr.write(f"ERROR: no such file: {args.inventory}\n")
        return 2

    inv = load_inventory(args.inventory)
    if "VINSerialNumber" not in inv.columns:
        sys.stderr.write(
            "ERROR: no VINSerialNumber column -- is this an ExportInventory CSV?\n"
        )
        return 2

    exclusions = find_filter_exclusions(inv)
    completeness = score_completeness(inv)

    triaged = None
    if args.webstats is not None:
        if not args.webstats.is_file():
            sys.stderr.write(f"ERROR: no such file: {args.webstats}\n")
            return 2
        stats = pd.read_csv(args.webstats, low_memory=False, encoding="utf-8-sig")
        if "SerialNumber" not in stats.columns:
            sys.stderr.write(
                "ERROR: no SerialNumber column -- is this a WebstatsListings CSV?\n"
            )
            return 2
        triaged = triage(join_webstats(inv, stats))

    report = render_report(inv, exclusions, completeness, triaged)
    if args.out is not None:
        args.out.write_text(report, encoding="utf-8")
        sys.stdout.write(f"Wrote {args.out}\n")
    else:
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
