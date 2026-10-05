#!/usr/bin/env python3
"""
HIS Meta pilot: unit pages, Meta catalog feed, and Gavel Reports
=================================================================

Phase 1 of the HIS seller platform. Every pilot unit gets three things:

1. **A unit landing page** (``pages``). This is a static HTML page on an
   HIS-owned domain, carrying the Meta Pixel. Opening the page fires
   ``ViewContent``, the "Save this unit" button fires ``AddToWishlist``, and
   the call and message buttons fire ``Contact``. All three events carry the
   unit's catalog id in ``content_ids``, so Meta can tie them back to the
   catalog item and retarget people who looked at it.
2. **A Meta catalog row** (``catalog``). The CSV data feed for Commerce
   Manager. It uses the same ids as the pages, which is what makes catalog ads
   and retargeting work.
3. **A Gavel Report** (``report``). This is a private one-page HTML report for
   the seller, built from an Ads Manager export. It shows reach, attention,
   interest, inquiries, where the unit's price sits against the market, and a
   suggested next move. The seller makes the call; the report records the
   decision they made.

House rules this tool enforces
------------------------------
- **Crew photos only.** Images come from the intake folder
  (``<StockNumber>_<NN>.jpg``, the same convention as ``marketplace_pack.py``),
  never from TractorHouse or Sandhills. A unit without crew photos gets no
  page and no catalog row.
- **Truth standard.** Every number on a page or report comes from the export,
  the pilot sheet, or Meta. Nothing is filled in. Missing values are shown as
  missing.
- **Epiphany Standard.** HIS-authored copy never uses the rejected words. Seller
  descriptions from the export are checked, and any hits are reported so a
  person can rewrite them. The tool does not silently edit them.

Usage
-----
    python3 meta_pilot.py pages   --inventory ExportInventory.csv \
        --pilot pilot_units.csv --photos Photos/ --pixel-id 1234567890 \
        --base-url https://units.example.com --out site
    python3 meta_pilot.py catalog --inventory ExportInventory.csv \
        --pilot pilot_units.csv --photos Photos/ \
        --base-url https://units.example.com --out meta_catalog.csv
    python3 meta_pilot.py report  --inventory ExportInventory.csv \
        --pilot pilot_units.csv --ads ads_export.csv --out reports

See META_PILOT_README.md for the Meta-side setup and the pilot sheet format.
The module is import-safe: everything runs under ``main()``.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

try:
    import pandas as pd
except ImportError:  # pragma: no cover - environment guard
    sys.stderr.write(
        "ERROR: pandas is not installed. Run 'pip install pandas' and retry.\n"
    )
    raise SystemExit(2)


BRAND = "Heartland Iron Solutions"

#: Rejected vocabulary under the Epiphany Standard (Vault doctrine, 2026-07-03).
REJECTED_WORDS = (
    "salesman", "salesmen", "auction", "auctions", "auctioneer", "auctioneers",
    "consignor", "consignors", "consignment", "consignments",
)

#: Sandhills header spellings accepted for each field. The first one is the
#: canonical name used inside this module.
INVENTORY_ALIASES: dict[str, tuple[str, ...]] = {
    "StockNumber": ("StockNumber", "Stock Number", "Stock #", "Stock"),
    "Year": ("Year",),
    "Make": ("Manufacturer", "Make"),
    "Model": ("Model",),
    "Price": ("SaleListPrice", "ListPrice", "Price"),
    "Category": ("Category", "AssetCategory"),
    "Description": ("Description",),
    "Hours": ("hours", "Hours"),
    "Miles": ("mileage", "Mileage", "Miles"),
    "City": ("LocationCity", "City"),
    "State": ("LocationState", "State"),
    "Serial": ("VINSerialNumber", "SerialNumber", "Serial Number", "VIN"),
}
REQUIRED_INVENTORY = ("StockNumber", "Year", "Make", "Model")

#: Pilot sheet columns. ``market_value`` is HIS's valuation for the unit;
#: ``ladder`` is the seller's pre-committed price steps, highest first,
#: separated by semicolons.
PILOT_REQUIRED = ("StockNumber", "seller_name", "start_date")
PILOT_OPTIONAL = ("market_value", "ladder", "decision", "decision_date")

#: Ads Manager export headers vary with the columns picked and the account
#: currency. Each metric accepts several spellings; ``spend`` also matches any
#: "Amount spent (XXX)" header.
ADS_ALIASES: dict[str, tuple[str, ...]] = {
    "ad_set": ("Ad set name", "Ad Set Name", "Campaign name"),
    "reach": ("Reach",),
    "impressions": ("Impressions",),
    "spend": ("Amount spent", "Amount spent (USD)", "Spend"),
    "link_clicks": ("Link clicks", "Clicks (all)"),
    "thruplays": ("ThruPlays",),
    "avg_watch": ("Video average play time", "Average video play time"),
    "leads": ("Leads", "On-Facebook leads"),
    "messages": ("Messaging conversations started",),
    "page_views": ("Website content views", "Content views"),
    "saves": ("Website adds to wishlist", "Adds to wishlist"),
    "contacts": ("Website contacts", "Contacts"),
    "region": ("Region",),
}
REQUIRED_ADS = ("ad_set", "reach", "impressions")
SUMMED_METRICS = (
    "reach", "impressions", "spend", "link_clicks", "thruplays", "leads",
    "messages", "page_views", "saves", "contacts",
)

#: Recommendation thresholds. These are pilot starting points, not doctrine.
#: Tune them once the pilot has real numbers.
MIN_DAYS_FOR_CALL = 7          # under this, it is too early to judge
MIN_REACH_FOR_CALL = 1_000     # under this, too few people have seen the unit
WEAK_WATCH_SECONDS = 3.0       # the MIA reels problem: drop-off inside 3 s
PRICE_ZONE = 0.10              # Gavel: within 10% of market is "in the zone"

PHOTO_PATTERN = re.compile(r"^(?:lot)?0*([a-z0-9-]+?)_(\d+)\.(jpe?g|png)$", re.I)
MAX_PHOTOS = 20


class InputError(ValueError):
    """An input file is missing a column or a value this tool needs."""


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------

def is_blank(value) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):  # pragma: no cover - non-scalar guard
        pass
    return str(value).strip() in ("", "nan", "None")


def clean(value) -> str:
    return "" if is_blank(value) else re.sub(r"\s+", " ", str(value).strip())


def slug(value: str) -> str:
    """Catalog id, URL path, and Pixel ``content_id`` for a unit."""
    return re.sub(r"[^A-Za-z0-9]+", "-", str(value).strip().upper()).strip("-")


def stock_key(value: str) -> str:
    """Match key for stock numbers: case-, LOT-prefix- and zero-insensitive."""
    key = str(value).strip().lower()
    key = key[3:] if key.startswith("lot") else key
    return key.lstrip("0") or "0"


def to_number(value) -> float | None:
    """Parse "$1,234.50", "4.2s" or 12 into a float; None when blank."""
    if is_blank(value):
        return None
    text = re.sub(r"[^0-9.\-]", "", str(value))
    try:
        return float(text) if text not in ("", "-", ".") else None
    except ValueError:
        return None


def money(value: float | None) -> str:
    return "not set" if value is None else f"${value:,.0f}"


def script_safe(text: str) -> str:
    """JSON for an inline <script>: export text cannot close the tag early."""
    return text.replace("</", "<\\/")


def epiphany_hits(text: str) -> list[str]:
    """Rejected words found in ``text``, lower-cased, in order of appearance."""
    found = re.findall(r"[A-Za-z]+", text.lower())
    return [w for w in found if w in REJECTED_WORDS]


def resolve_columns(
    df: pd.DataFrame, aliases: dict[str, tuple[str, ...]], required: tuple[str, ...],
    source: str,
) -> pd.DataFrame:
    """Rename known header spellings to canonical names. Fails loud on gaps."""
    renames: dict[str, str] = {}
    for canonical, spellings in aliases.items():
        for spelling in spellings:
            if spelling in df.columns:
                renames[spelling] = canonical
                break
        else:
            if canonical == "spend":
                money_cols = [c for c in df.columns if c.startswith("Amount spent")]
                if money_cols:
                    renames[money_cols[0]] = "spend"
    missing = [c for c in required if c not in renames.values()]
    if missing:
        raise InputError(
            f"{source} is missing required column(s) {missing}. "
            f"Columns found: {list(df.columns)}. If the export uses a new "
            f"spelling, add it to the aliases in meta_pilot.py."
        )
    return df.rename(columns=renames)


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

@dataclass
class Unit:
    stock: str
    year: str
    make: str
    model: str
    price: float | None
    category: str
    description: str
    hours: float | None
    miles: float | None
    city: str
    state: str
    serial: str
    seller_name: str
    start_date: date
    market_value: float | None
    ladder: list[float] = field(default_factory=list)
    decision: str = ""
    decision_date: str = ""
    photos: list[Path] = field(default_factory=list)

    @property
    def unit_id(self) -> str:
        return slug(self.stock)

    @property
    def title(self) -> str:
        return " ".join(p for p in (self.year, self.make, self.model) if p)

    @property
    def location(self) -> str:
        return ", ".join(p for p in (self.city, self.state) if p)


def load_inventory(path: Path) -> pd.DataFrame:
    inv = pd.read_csv(path, dtype=str, encoding="utf-8-sig", low_memory=False)
    if inv.empty:
        raise InputError(f"{path} has no rows.")
    return resolve_columns(inv, INVENTORY_ALIASES, REQUIRED_INVENTORY, str(path))


def load_pilot(path: Path) -> pd.DataFrame:
    pilot = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    missing = [c for c in PILOT_REQUIRED if c not in pilot.columns]
    if missing:
        raise InputError(
            f"{path} is missing pilot column(s) {missing}. "
            f"Required: {list(PILOT_REQUIRED)}; optional: {list(PILOT_OPTIONAL)}."
        )
    if pilot.empty:
        raise InputError(f"{path} has no pilot units.")
    return pilot


def index_photos(photo_dir: Path | None) -> dict[str, list[Path]]:
    """Crew photos by stock key, ordered by their ``_NN`` number."""
    found: dict[str, list[tuple[int, Path]]] = {}
    if photo_dir is None or not photo_dir.is_dir():
        return {}
    for path in photo_dir.iterdir():
        match = PHOTO_PATTERN.match(path.name)
        if match and path.is_file():
            key = stock_key(match.group(1))
            found.setdefault(key, []).append((int(match.group(2)), path))
    return {k: [p for _, p in sorted(v)][:MAX_PHOTOS] for k, v in found.items()}


def parse_ladder(text: str) -> list[float]:
    steps = [to_number(part) for part in str(text).split(";")]
    return [s for s in steps if s is not None]


def build_units(
    inv: pd.DataFrame, pilot: pd.DataFrame, photos: dict[str, list[Path]],
) -> list[Unit]:
    """Join the pilot sheet onto the export. Fails loud on unknown stock numbers."""
    by_key = {stock_key(s): row for s, row in zip(inv["StockNumber"], inv.to_dict("records"))}
    units: list[Unit] = []
    for prow in pilot.to_dict("records"):
        stock = clean(prow.get("StockNumber"))
        row = by_key.get(stock_key(stock))
        if row is None:
            raise InputError(
                f"Pilot unit {stock!r} is not in the inventory export. "
                f"Check the stock number or pull a fresh export."
            )
        try:
            start = date.fromisoformat(clean(prow.get("start_date")))
        except ValueError as exc:
            raise InputError(
                f"Pilot unit {stock!r} has start_date {prow.get('start_date')!r}; "
                f"use YYYY-MM-DD."
            ) from exc
        year = to_number(row.get("Year"))
        units.append(Unit(
            stock=clean(row.get("StockNumber")),
            year="" if year is None else str(int(year)),
            make=clean(row.get("Make")),
            model=clean(row.get("Model")),
            price=to_number(row.get("Price")),
            category=clean(row.get("Category")),
            description=clean(row.get("Description")),
            hours=to_number(row.get("Hours")),
            miles=to_number(row.get("Miles")),
            city=clean(row.get("City")),
            state=clean(row.get("State")),
            serial=clean(row.get("Serial")),
            seller_name=clean(prow.get("seller_name")),
            start_date=start,
            market_value=to_number(prow.get("market_value")),
            ladder=parse_ladder(prow.get("ladder", "")),
            decision=clean(prow.get("decision")),
            decision_date=clean(prow.get("decision_date")),
            photos=photos.get(stock_key(stock), []),
        ))
    return units


# --------------------------------------------------------------------------
# Unit pages
# --------------------------------------------------------------------------

PIXEL_BASE = """<script>
!function(f,b,e,v,n,t,s){{if(f.fbq)return;n=f.fbq=function(){{n.callMethod?
n.callMethod.apply(n,arguments):n.queue.push(arguments)}};if(!f._fbq)f._fbq=n;
n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;
t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}}(window,
document,'script','https://connect.facebook.net/en_US/fbevents.js');
fbq('init', {pixel_id});
fbq('track', 'PageView');
fbq('track', 'ViewContent', {event_params});
function hisTrack(name) {{ fbq('track', name, {event_params}); }}
</script>"""


def event_params(unit: Unit) -> str:
    params: dict = {"content_ids": [unit.unit_id], "content_type": "product",
                    "content_name": unit.title}
    if unit.price is not None:
        params.update(value=unit.price, currency="USD")
    return script_safe(json.dumps(params))


def json_ld(unit: Unit, base_url: str) -> str:
    """schema.org IndividualProduct (carries serialNumber) with an Offer."""
    data: dict = {
        "@context": "https://schema.org",
        "@type": "IndividualProduct",
        "name": unit.title,
        "brand": {"@type": "Brand", "name": unit.make} if unit.make else None,
        "model": unit.model or None,
        "serialNumber": unit.serial or None,
        "category": unit.category or None,
        "url": f"{base_url}/{unit.unit_id}/",
        "image": [f"{base_url}/{unit.unit_id}/photo-{i + 1}{p.suffix.lower()}"
                  for i, p in enumerate(unit.photos)],
        "itemCondition": "https://schema.org/UsedCondition",
    }
    if unit.price is not None:
        data["offers"] = {"@type": "Offer", "price": f"{unit.price:.2f}",
                          "priceCurrency": "USD",
                          "availability": "https://schema.org/InStock",
                          "seller": {"@type": "Organization", "name": BRAND}}
    return script_safe(json.dumps(
        {k: v for k, v in data.items() if v not in (None, [])}, indent=2))


def spec_rows(unit: Unit) -> list[tuple[str, str]]:
    rows = [("Year", unit.year), ("Make", unit.make), ("Model", unit.model),
            ("Category", unit.category), ("Serial", unit.serial),
            ("Location", unit.location)]
    if unit.hours is not None:
        rows.append(("Hours", f"{unit.hours:,.0f}"))
    if unit.miles is not None:
        rows.append(("Miles", f"{unit.miles:,.0f}"))
    return [(k, v if v else "not listed") for k, v in rows]


def render_unit_page(unit: Unit, pixel_id: str, base_url: str, phone: str,
                     messenger_url: str) -> str:
    e = html.escape
    params = event_params(unit)
    gallery = "\n".join(
        f'<img src="photo-{i + 1}{p.suffix.lower()}" alt="{e(unit.title)} photo {i + 1}"'
        f' loading="lazy">' for i, p in enumerate(unit.photos))
    specs = "\n".join(f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in spec_rows(unit))
    price = money(unit.price) if unit.price is not None else "Price on request"
    buttons = ['<button type="button" onclick="hisTrack(\'AddToWishlist\');'
               'this.textContent=\'Saved. We will keep you posted.\'">Save this unit</button>']
    if phone:
        buttons.append(f'<a href="tel:{e(phone)}" onclick="hisTrack(\'Contact\')">Call {e(phone)}</a>')
    if messenger_url:
        buttons.append(f'<a href="{e(messenger_url)}" onclick="hisTrack(\'Contact\')">Message us</a>')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(unit.title)} | {BRAND}</title>
<meta property="og:title" content="{e(unit.title)}">
<meta property="og:type" content="product">
<meta property="og:url" content="{e(base_url)}/{unit.unit_id}/">
<meta property="og:image" content="{e(base_url)}/{unit.unit_id}/photo-1{unit.photos[0].suffix.lower()}">
<meta property="product:retailer_item_id" content="{unit.unit_id}">
<script type="application/ld+json">
{json_ld(unit, base_url)}
</script>
{PIXEL_BASE.format(pixel_id=json.dumps(str(pixel_id)), event_params=params)}
<noscript><img height="1" width="1" style="display:none" alt=""
src="https://www.facebook.com/tr?id={e(str(pixel_id))}&ev=PageView&noscript=1"></noscript>
<style>
body{{font-family:system-ui,sans-serif;margin:0;color:#1d1d1b;background:#fff}}
main{{max-width:860px;margin:0 auto;padding:16px}}
.gallery{{display:grid;gap:8px;grid-template-columns:repeat(auto-fill,minmax(240px,1fr))}}
.gallery img{{width:100%;height:auto;border-radius:6px}}
table{{border-collapse:collapse;width:100%}}th,td{{text-align:left;padding:6px;border-bottom:1px solid #ddd}}
.actions{{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}}
.actions a,.actions button{{padding:10px 16px;border-radius:6px;border:1px solid #1d1d1b;
background:#fff;color:#1d1d1b;font:inherit;text-decoration:none;cursor:pointer}}
.price{{font-size:1.6em;font-weight:700}}
</style></head>
<body><main>
<p>{BRAND}</p>
<h1>{e(unit.title)}</h1>
<p class="price">{e(price)}</p>
<div class="actions">{''.join(buttons)}</div>
<div class="gallery">{gallery}</div>
<h2>Specs</h2>
<table>{specs}</table>
<h2>Details</h2>
<p>{e(unit.description) if unit.description else 'No description listed yet.'}</p>
</main></body></html>
"""


def build_pages(units: list[Unit], out: Path, pixel_id: str, base_url: str,
                phone: str = "", messenger_url: str = "") -> dict[str, list[str]]:
    """Write one folder per unit. Returns built ids, skips, and copy warnings."""
    result: dict[str, list[str]] = {"built": [], "skipped": [], "warnings": []}
    out.mkdir(parents=True, exist_ok=True)
    for unit in units:
        if not unit.photos:
            result["skipped"].append(f"{unit.stock}: no crew photos in the intake folder")
            continue
        hits = epiphany_hits(unit.description)
        if hits:
            result["warnings"].append(
                f"{unit.stock}: description uses rejected word(s) {sorted(set(hits))}; "
                f"rewrite it before the page goes live")
        folder = out / unit.unit_id
        folder.mkdir(parents=True, exist_ok=True)
        for i, photo in enumerate(unit.photos):
            shutil.copyfile(photo, folder / f"photo-{i + 1}{photo.suffix.lower()}")
        (folder / "index.html").write_text(
            render_unit_page(unit, pixel_id, base_url, phone, messenger_url),
            encoding="utf-8")
        result["built"].append(unit.unit_id)
    return result


# --------------------------------------------------------------------------
# Meta catalog feed
# --------------------------------------------------------------------------

CATALOG_COLUMNS = (
    "id", "title", "description", "availability", "condition", "price", "link",
    "image_link", "additional_image_link", "brand", "product_type",
    "custom_label_0", "custom_label_1",
)


def catalog_row(unit: Unit, base_url: str) -> tuple[dict | None, str]:
    if not unit.photos:
        return None, "no crew photos"
    if unit.price is None or unit.price <= 0:
        return None, "no asking price"
    if not unit.make:
        return None, "no make (Meta requires brand)"
    description = unit.description or (
        f"{unit.title}. " + ". ".join(f"{k}: {v}" for k, v in spec_rows(unit)
                                       if v != "not listed"))
    page = f"{base_url}/{unit.unit_id}/"
    images = [f"{page}photo-{i + 1}{p.suffix.lower()}" for i, p in enumerate(unit.photos)]
    return {
        "id": unit.unit_id,
        "title": unit.title[:200],
        "description": description[:9999],
        "availability": "in stock",
        "condition": "used",
        "price": f"{unit.price:.2f} USD",
        "link": page,
        "image_link": images[0],
        "additional_image_link": ",".join(images[1:10]),
        "brand": unit.make,
        "product_type": unit.category,
        "custom_label_0": unit.state,
        "custom_label_1": unit.category.split("-")[0].strip(),
    }, ""


def build_catalog(units: list[Unit], base_url: str) -> tuple[list[dict], list[str]]:
    rows, skipped = [], []
    for unit in units:
        row, reason = catalog_row(unit, base_url)
        if row is None:
            skipped.append(f"{unit.stock}: {reason}")
        else:
            rows.append(row)
    return rows, skipped


def write_catalog(rows: list[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CATALOG_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)


# --------------------------------------------------------------------------
# Gavel Report
# --------------------------------------------------------------------------

def load_ads(path: Path) -> pd.DataFrame:
    ads = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    if ads.empty:
        raise InputError(f"{path} has no rows.")
    return resolve_columns(ads, ADS_ALIASES, REQUIRED_ADS, str(path))


def unit_metrics(ads: pd.DataFrame, unit: Unit) -> dict | None:
    """Sum the ad-set rows whose name contains the unit's id.

    Ad sets must be named with the unit id (see the README naming rule). With a
    Region breakdown there is one row per region; reach is summed across
    regions, which is safe because a person is counted in one region only.
    Average watch time is weighted by impressions.
    """
    pattern = re.compile(rf"(?<![A-Z0-9]){re.escape(unit.unit_id)}(?![A-Z0-9])")
    mask = ads["ad_set"].fillna("").map(lambda n: bool(pattern.search(slug(n))))
    rows = ads[mask]
    if rows.empty:
        return None
    metrics: dict = {}
    for name in SUMMED_METRICS:
        if name in rows.columns:
            values = [to_number(v) for v in rows[name]]
            metrics[name] = sum(v for v in values if v is not None)
        else:
            metrics[name] = None
    if "avg_watch" in rows.columns:
        pairs = [(to_number(w), to_number(i) or 0)
                 for w, i in zip(rows["avg_watch"], rows["impressions"])]
        pairs = [(w, i) for w, i in pairs if w is not None]
        weight = sum(i for _, i in pairs)
        metrics["avg_watch"] = (sum(w * i for w, i in pairs) / weight if weight
                                else (pairs[0][0] if pairs else None))
    else:
        metrics["avg_watch"] = None
    if "region" in rows.columns:
        by_region = {}
        for region, reach in zip(rows["region"], rows["reach"]):
            if clean(region):
                by_region[clean(region)] = by_region.get(clean(region), 0) + (to_number(reach) or 0)
        metrics["top_regions"] = sorted(by_region.items(), key=lambda kv: -kv[1])[:5]
    else:
        metrics["top_regions"] = []
    metrics["inquiries"] = sum(metrics[k] or 0 for k in ("leads", "messages", "contacts"))
    return metrics


def price_position(unit: Unit) -> tuple[str, float | None]:
    """Asking price against HIS's market value: (label, ratio)."""
    if unit.price is None or not unit.market_value:
        return "unknown (asking price or market value not set)", None
    ratio = unit.price / unit.market_value
    if ratio > 1 + PRICE_ZONE:
        return f"above the zone ({ratio - 1:+.1%} vs market)", ratio
    if ratio < 1 - PRICE_ZONE:
        return f"below the zone ({ratio - 1:+.1%} vs market)", ratio
    return f"in the zone ({ratio - 1:+.1%} vs market)", ratio


def next_ladder_step(unit: Unit) -> float | None:
    if unit.price is None:
        return unit.ladder[0] if unit.ladder else None
    lower = [step for step in unit.ladder if step < unit.price]
    return max(lower) if lower else None


def recommend(unit: Unit, metrics: dict | None, as_of: date) -> tuple[str, str]:
    """(move, reason). Suggestions only: the seller holds the gavel."""
    days = (as_of - unit.start_date).days
    if metrics is None:
        return "No data yet", (
            "No ad set in the export matches this unit. Check that its ad set "
            f"name contains {unit.unit_id}.")
    if metrics["inquiries"]:
        return "Hold and work the conversations", (
            f"{metrics['inquiries']:.0f} buyer inquiries came in. Demand is talking; "
            "answer every one before touching price.")
    if days < MIN_DAYS_FOR_CALL or (metrics["reach"] or 0) < MIN_REACH_FOR_CALL:
        return "Hold: too early to call", (
            f"{days} days live and {metrics['reach'] or 0:,.0f} people reached. "
            f"Give it at least {MIN_DAYS_FOR_CALL} days and "
            f"{MIN_REACH_FOR_CALL:,} people before reading the signal.")
    watch = metrics["avg_watch"]
    if watch is not None and watch < WEAK_WATCH_SECONDS:
        return "Reposition the creative", (
            f"People watch {watch:.1f} s on average, so they leave before seeing "
            "the machine. Reshoot the walkaround with the best shot in the first "
            "second. This is a creative problem, not a price problem.")
    label, ratio = price_position(unit)
    if ratio is not None and ratio > 1 + PRICE_ZONE:
        step = next_ladder_step(unit)
        target = (f" Your committed next step is {money(step)}." if step
                  else " No lower ladder step is set; agree one before moving.")
        saved = metrics["saves"] or 0
        interest = (f" {saved:.0f} people saved it, so the interest is there and "
                    "the price is the likely blocker." if saved else "")
        return "Step down the ladder", (
            f"People are seeing it and watching it, but nobody is asking, and "
            f"the price is {label}.{interest}{target}")
    if (metrics["saves"] or 0) > 0:
        return "Hold: buyers are watching", (
            f"{metrics['saves']:.0f} people saved the unit and the price is {label}. "
            "Saved-unit audiences get retargeted automatically; give it time.")
    return "Widen the audience", (
        f"The price is {label} and attention holds, but no saves or inquiries yet. "
        "Test a wider radius or a second audience before moving the price.")


def render_report(unit: Unit, metrics: dict | None, as_of: date) -> str:
    e = html.escape
    move, reason = recommend(unit, metrics, as_of)
    label, _ = price_position(unit)
    m = metrics or {}

    def num(key: str, fmt: str = "{:,.0f}") -> str:
        value = m.get(key)
        return "not tracked" if value is None else fmt.format(value)

    rows = [
        ("People reached", num("reach")),
        ("Times shown", num("impressions")),
        ("Average watch time", num("avg_watch", "{:.1f} s")),
        ("Watched the full walkaround", num("thruplays")),
        ("Clicked through to the unit page", num("link_clicks")),
        ("Unit page views", num("page_views")),
        ("Saved the unit", num("saves")),
        ("Leads", num("leads")),
        ("Message conversations", num("messages")),
        ("Call or message clicks on the page", num("contacts")),
        ("Ad spend to date", "not tracked" if m.get("spend") is None else money(m["spend"])),
    ]
    table = "\n".join(f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in rows)
    regions = "".join(f"<li>{e(r)}: {reach:,.0f} people</li>" for r, reach in m.get("top_regions", []))
    ladder = ", ".join(money(s) for s in unit.ladder) or "not set"
    decision = (f"{e(unit.decision)} ({e(unit.decision_date or 'date not logged')})"
                if unit.decision else "No decision logged yet.")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Gavel Report: {e(unit.title)}</title>
<style>
body{{font-family:system-ui,sans-serif;margin:0;color:#1d1d1b;background:#fff}}
main{{max-width:760px;margin:0 auto;padding:16px}}
table{{border-collapse:collapse;width:100%}}th,td{{text-align:left;padding:6px;border-bottom:1px solid #ddd}}
.move{{border:2px solid #1d1d1b;border-radius:8px;padding:12px 16px;margin:16px 0}}
.move strong{{font-size:1.3em}}
</style></head>
<body><main>
<p>{BRAND} | Gavel Report | as of {as_of.isoformat()}</p>
<h1>{e(unit.title)}</h1>
<p>Prepared for {e(unit.seller_name)}. Live since {unit.start_date.isoformat()}
({(as_of - unit.start_date).days} days).</p>
<h2>Where your price sits</h2>
<p>Asking {e(money(unit.price))}. Market value {e(money(unit.market_value))}.
Your price is {e(label)}.</p>
<p>Your committed price ladder: {e(ladder)}</p>
<h2>What the market is doing with your iron</h2>
<table>{table}</table>
{f'<h3>Where the attention is coming from</h3><ul>{regions}</ul>' if regions else ''}
<div class="move"><p>Suggested move</p><strong>{e(move)}</strong><p>{e(reason)}</p></div>
<h2>Your call</h2>
<p>You hold the gavel. HIS suggests; you decide.</p>
<p>Decision on record: {decision}</p>
</main></body></html>
"""


def build_reports(units: list[Unit], ads: pd.DataFrame, out: Path,
                  as_of: date) -> list[tuple[str, str]]:
    out.mkdir(parents=True, exist_ok=True)
    summary = []
    for unit in units:
        metrics = unit_metrics(ads, unit)
        move, _ = recommend(unit, metrics, as_of)
        (out / f"{unit.unit_id}.html").write_text(
            render_report(unit, metrics, as_of), encoding="utf-8")
        summary.append((unit.stock, move))
    return summary


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _base_url(value: str) -> str:
    if not value.startswith("https://"):
        raise InputError("--base-url must be an https:// address on an HIS-owned domain.")
    return value.rstrip("/")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HIS Meta pilot tooling.")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--inventory", type=Path, required=True, help="Sandhills ExportInventory CSV")
        p.add_argument("--pilot", type=Path, required=True, help="pilot units sheet (CSV)")

    p_pages = sub.add_parser("pages", help="build unit landing pages with the Meta Pixel")
    common(p_pages)
    p_pages.add_argument("--photos", type=Path, required=True, help="crew photo intake folder")
    p_pages.add_argument("--pixel-id", required=True, help="Meta Pixel (dataset) id")
    p_pages.add_argument("--base-url", required=True, help="https://… where the pages will be hosted")
    p_pages.add_argument("--phone", default="", help="phone number for the call button")
    p_pages.add_argument("--messenger-url", default="", help="m.me link for the message button")
    p_pages.add_argument("--out", type=Path, default=Path("site"))

    p_cat = sub.add_parser("catalog", help="build the Meta catalog CSV feed")
    common(p_cat)
    p_cat.add_argument("--photos", type=Path, required=True, help="crew photo intake folder")
    p_cat.add_argument("--base-url", required=True, help="same base URL as the pages")
    p_cat.add_argument("--out", type=Path, default=Path("meta_catalog.csv"))

    p_rep = sub.add_parser("report", help="build Gavel Reports from an Ads Manager export")
    common(p_rep)
    p_rep.add_argument("--ads", type=Path, required=True, help="Ads Manager export (CSV)")
    p_rep.add_argument("--as-of", default=None, help="report date YYYY-MM-DD (default today)")
    p_rep.add_argument("--out", type=Path, default=Path("gavel_reports"))

    args = parser.parse_args(argv)
    try:
        inv = load_inventory(args.inventory)
        pilot = load_pilot(args.pilot)
        photos = index_photos(getattr(args, "photos", None))
        units = build_units(inv, pilot, photos)

        if args.command == "pages":
            result = build_pages(units, args.out, args.pixel_id, _base_url(args.base_url),
                                 args.phone, args.messenger_url)
            print(f"Built {len(result['built'])} unit page(s) in {args.out}/")
            for line in result["skipped"]:
                print(f"  SKIPPED  {line}")
            for line in result["warnings"]:
                print(f"  WARNING  {line}")
            return 0

        if args.command == "catalog":
            rows, skipped = build_catalog(units, _base_url(args.base_url))
            write_catalog(rows, args.out)
            print(f"Wrote {args.out} ({len(rows)} catalog row(s))")
            for line in skipped:
                print(f"  SKIPPED  {line}")
            for row in rows:
                hits = epiphany_hits(row["description"])
                if hits:
                    print(f"  WARNING  {row['id']}: description uses rejected "
                          f"word(s) {sorted(set(hits))}; rewrite before upload")
            return 0

        as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
        summary = build_reports(units, load_ads(args.ads), args.out, as_of)
        print(f"Wrote {len(summary)} Gavel Report(s) to {args.out}/")
        for stock, move in summary:
            print(f"  {stock}: {move}")
        return 0
    except (InputError, FileNotFoundError) as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
