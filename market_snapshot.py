#!/usr/bin/env python3
"""
Sandhills Market Snapshot pipeline
==================================

Cleans and merges the internal lot inventory sheet with the Sandhills WebStats
traffic log, scores every item with a Buyer Engagement Score, cross-references
regional supply-and-demand shifts from an exported Sandhills Market Report, and
writes a single, NotebookLM-ready Markdown document (``notebooklm_source.md``).

Stages
------
1. Load + validate the three CSV inputs (inventory, webstats, market trends).
2. Clean and merge inventory + webstats on StockNumber (falling back to
   AssetCategory) and compute Buyer Engagement Score = Views / Days on Market.
3. Cross-reference inventory against regional market trends and flag
   "hot-selling" categories: regional inventory dropping while pricing or
   auction values are rising.
4. Render notebooklm_source.md with a "Hot-Selling Action Items" section
   pinned to the top, followed by the full merged dataset.

The module is import-safe (everything runs under ``main()``) so the bundling
shell script can drive it and surface clean exit codes.
"""

from __future__ import annotations

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
# Configuration: file names and the columns each input is required to provide. #
# --------------------------------------------------------------------------- #
INVENTORY_CSV = "inventory.csv"
WEBSTATS_CSV = "webstats.csv"
MARKET_TRENDS_CSV = "market_trends.csv"
OUTPUT_MD = "notebooklm_source.md"

REQUIRED_INVENTORY_COLS = {
    "StockNumber",
    "AssetCategory",
    "ListPrice",
    "AuctionValue",
    "DaysOnMarket",
}
REQUIRED_WEBSTATS_COLS = {"StockNumber", "Views"}
REQUIRED_TREND_COLS = {
    "AssetCategory",
    "RegionalInventoryChangePct",
    "RegionalPriceChangePct",
    "AuctionValueChangePct",
}


class PipelineError(RuntimeError):
    """Raised when an input is missing, unreadable, or the wrong shape.

    The bundling shell script keys off the non-zero exit code this produces so
    operators get a loud, specific alert when a file format changes.
    """


# --------------------------------------------------------------------------- #
# Small console helpers so the live run reads like a status feed.             #
# --------------------------------------------------------------------------- #
def info(msg: str) -> None:
    print(f"  [..] {msg}", flush=True)


def ok(msg: str) -> None:
    print(f"  [OK] {msg}", flush=True)


def step(msg: str) -> None:
    print(f"\n==> {msg}", flush=True)


# --------------------------------------------------------------------------- #
# Stage 1 - load + validate                                                    #
# --------------------------------------------------------------------------- #
def load_csv(path: Path, required_cols: set[str], label: str) -> "pd.DataFrame":
    """Read a CSV and assert it carries the columns the pipeline depends on."""
    info(f"Reading {label} from '{path.name}' ...")
    if not path.exists():
        raise PipelineError(
            f"{label} file '{path.name}' was not found in {path.parent}."
        )
    try:
        frame = pd.read_csv(path)
    except Exception as exc:  # pandas raises a wide variety of parse errors
        raise PipelineError(f"Could not parse {label} '{path.name}': {exc}") from exc

    if frame.empty:
        raise PipelineError(f"{label} '{path.name}' contains no data rows.")

    missing = required_cols - set(frame.columns)
    if missing:
        raise PipelineError(
            f"{label} '{path.name}' is missing required column(s): "
            f"{', '.join(sorted(missing))}. "
            f"Found columns: {', '.join(frame.columns)}. "
            "The source file format may have changed."
        )
    ok(f"{label}: {len(frame)} rows, {len(frame.columns)} columns validated.")
    return frame


# --------------------------------------------------------------------------- #
# Stage 2 - clean + merge + score                                              #
# --------------------------------------------------------------------------- #
def clean_inventory(inv: "pd.DataFrame") -> "pd.DataFrame":
    inv = inv.copy()
    inv["StockNumber"] = inv["StockNumber"].astype(str).str.strip()
    inv["AssetCategory"] = inv["AssetCategory"].astype(str).str.strip()
    for col in ("ListPrice", "AuctionValue", "DaysOnMarket"):
        inv[col] = pd.to_numeric(inv[col], errors="coerce")
    inv = inv.drop_duplicates(subset="StockNumber")
    return inv


def clean_webstats(web: "pd.DataFrame") -> "pd.DataFrame":
    web = web.copy()
    web["StockNumber"] = web["StockNumber"].astype(str).str.strip()
    web["Views"] = pd.to_numeric(web["Views"], errors="coerce").fillna(0)
    # Collapse any duplicate stock rows in the traffic log to a single total.
    numeric_cols = web.select_dtypes("number").columns.tolist()
    web = web.groupby("StockNumber", as_index=False)[numeric_cols].sum()
    return web


def merge_and_score(inv: "pd.DataFrame", web: "pd.DataFrame") -> "pd.DataFrame":
    """Merge on StockNumber and compute Buyer Engagement Score = Views / DOM."""
    info("Merging inventory and webstats on StockNumber ...")
    merged = inv.merge(web, on="StockNumber", how="left", suffixes=("", "_web"))

    matched = merged["Views"].notna().sum()
    info(f"Matched {matched} of {len(merged)} lots to web traffic by StockNumber.")

    # Fall back to category-level average views for any lot with no direct match.
    if merged["Views"].isna().any():
        info("Backfilling unmatched lots with category-average views ...")
        cat_avg = web_category_average(inv, web)
        merged["Views"] = merged.apply(
            lambda r: cat_avg.get(r["AssetCategory"], 0.0)
            if pd.isna(r["Views"])
            else r["Views"],
            axis=1,
        )

    merged["Views"] = merged["Views"].fillna(0)

    # Buyer Engagement Score: avoid divide-by-zero on a 0-day listing.
    dom = merged["DaysOnMarket"].replace(0, pd.NA)
    merged["BuyerEngagementScore"] = (merged["Views"] / dom).round(2)
    merged["BuyerEngagementScore"] = merged["BuyerEngagementScore"].fillna(0)

    merged = merged.sort_values("BuyerEngagementScore", ascending=False)
    ok(f"Buyer Engagement Score computed for {len(merged)} items.")
    return merged


def web_category_average(inv: "pd.DataFrame", web: "pd.DataFrame") -> dict[str, float]:
    """Average views per asset category, used to backfill unmatched lots."""
    if "AssetCategory" in web.columns:
        return web.groupby("AssetCategory")["Views"].mean().to_dict()
    joined = inv[["StockNumber", "AssetCategory"]].merge(web, on="StockNumber")
    return joined.groupby("AssetCategory")["Views"].mean().to_dict()


# --------------------------------------------------------------------------- #
# Stage 3 - market-trend cross-reference                                       #
# --------------------------------------------------------------------------- #
def flag_hot_categories(trends: "pd.DataFrame") -> "pd.DataFrame":
    """Return trend rows where regional inventory is falling while price or
    auction value is rising -- the classic supply-down / demand-up squeeze."""
    info("Scanning regional supply-and-demand shifts ...")
    t = trends.copy()
    for col in (
        "RegionalInventoryChangePct",
        "RegionalPriceChangePct",
        "AuctionValueChangePct",
    ):
        t[col] = pd.to_numeric(t[col], errors="coerce")

    inventory_dropping = t["RegionalInventoryChangePct"] < 0
    value_rising = (t["RegionalPriceChangePct"] > 0) | (t["AuctionValueChangePct"] > 0)
    hot = t[inventory_dropping & value_rising].copy()
    hot = hot.sort_values("RegionalInventoryChangePct")  # steepest drop first
    ok(f"Flagged {len(hot)} hot regional segment(s).")
    return hot


def match_inventory_to_hot(
    scored: "pd.DataFrame", hot: "pd.DataFrame"
) -> "pd.DataFrame":
    """Cross-reference our scored inventory against the hot segments.

    Matches on AssetCategory, and additionally on Region when both sides carry
    it, so a category that is hot in one region doesn't drag in lots sitting in
    a cold one.
    """
    info("Cross-referencing our lots against hot regional segments ...")
    if hot.empty:
        return scored.iloc[0:0].copy()

    hot_keys = hot[["AssetCategory"]].drop_duplicates()
    use_region = "Region" in scored.columns and "Region" in hot.columns
    if use_region:
        hot_keys = hot[["AssetCategory", "Region"]].drop_duplicates()
        match = scored.merge(hot_keys, on=["AssetCategory", "Region"], how="inner")
    else:
        match = scored.merge(hot_keys, on="AssetCategory", how="inner")

    match = match.sort_values("BuyerEngagementScore", ascending=False)
    ok(f"{len(match)} of our lots sit in hot-selling segments.")
    return match


# --------------------------------------------------------------------------- #
# Stage 4 - render Markdown                                                     #
# --------------------------------------------------------------------------- #
def _money(value) -> str:
    return f"${value:,.0f}" if pd.notna(value) else "n/a"


def build_markdown(
    scored: "pd.DataFrame",
    hot: "pd.DataFrame",
    hot_inventory: "pd.DataFrame",
    generated_on: str,
) -> str:
    lines: list[str] = []

    # ---- Title -----------------------------------------------------------
    lines.append("# Sandhills Market Snapshot")
    lines.append("")
    lines.append(f"_Generated {generated_on} — source document for Google NotebookLM._")
    lines.append("")
    lines.append(
        "This document merges internal lot inventory with Sandhills WebStats "
        "traffic and overlays Sandhills Market Report regional trends. Every "
        "lot carries a **Buyer Engagement Score** (web Views ÷ Days on Market): "
        "higher means more buyer interest per day on the lot."
    )
    lines.append("")

    # ---- Hot-Selling Action Items (pinned to the top) --------------------
    lines.append("## 🔥 Hot-Selling Action Items")
    lines.append("")
    if hot_inventory.empty:
        lines.append(
            "_No current lots fall in a hot-selling regional segment "
            "(regional inventory dropping while price or auction value rises)._"
        )
        lines.append("")
    else:
        lines.append(
            "These lots sit in regional segments where **supply is shrinking "
            "while pricing or auction values are climbing** — prioritize them "
            "for pricing reviews and outreach."
        )
        lines.append("")
        lines.append(
            "| Stock # | Category | Region | Make/Model | List Price | "
            "Auction Value | Engagement | Why It's Hot |"
        )
        lines.append("|---|---|---|---|---|---|---|---|")

        hot_lookup = _hot_lookup(hot)
        for _, r in hot_inventory.iterrows():
            why = hot_lookup.get(
                (r.get("AssetCategory"), r.get("Region")),
                hot_lookup.get((r.get("AssetCategory"), None), "supply down / value up"),
            )
            make_model = " ".join(
                str(r[c]) for c in ("Make", "Model") if c in r and pd.notna(r[c])
            ).strip() or "—"
            lines.append(
                f"| {r.get('StockNumber','—')} | {r.get('AssetCategory','—')} | "
                f"{r.get('Region','—')} | {make_model} | "
                f"{_money(r.get('ListPrice'))} | {_money(r.get('AuctionValue'))} | "
                f"{r.get('BuyerEngagementScore','—')} | {why} |"
            )
        lines.append("")

    # ---- Regional trend signals -----------------------------------------
    lines.append("### Regional Trend Signals Behind These Flags")
    lines.append("")
    if hot.empty:
        lines.append("_No regional segments currently meet the hot-selling criteria._")
        lines.append("")
    else:
        lines.append(
            "| Category | Region | Inventory Δ% | Price Δ% | Auction Δ% |"
        )
        lines.append("|---|---|---|---|---|")
        for _, r in hot.iterrows():
            lines.append(
                f"| {r.get('AssetCategory','—')} | {r.get('Region','—')} | "
                f"{r['RegionalInventoryChangePct']:+.1f} | "
                f"{r['RegionalPriceChangePct']:+.1f} | "
                f"{r['AuctionValueChangePct']:+.1f} |"
            )
        lines.append("")

    # ---- Full merged dataset --------------------------------------------
    lines.append("## Full Lot Inventory — Merged & Scored")
    lines.append("")
    lines.append(
        f"All {len(scored)} lots, ranked by Buyer Engagement Score (highest first)."
    )
    lines.append("")
    lines.append(
        "| Rank | Stock # | Category | Region | Make/Model | Year | "
        "List Price | Auction Value | Views | Days on Market | Engagement |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for rank, (_, r) in enumerate(scored.iterrows(), start=1):
        make_model = " ".join(
            str(r[c]) for c in ("Make", "Model") if c in r and pd.notna(r[c])
        ).strip() or "—"
        year = int(r["Year"]) if "Year" in r and pd.notna(r["Year"]) else "—"
        views = int(r["Views"]) if pd.notna(r["Views"]) else 0
        dom = int(r["DaysOnMarket"]) if pd.notna(r["DaysOnMarket"]) else "—"
        lines.append(
            f"| {rank} | {r.get('StockNumber','—')} | {r.get('AssetCategory','—')} | "
            f"{r.get('Region','—')} | {make_model} | {year} | "
            f"{_money(r.get('ListPrice'))} | {_money(r.get('AuctionValue'))} | "
            f"{views:,} | {dom} | {r.get('BuyerEngagementScore','—')} |"
        )
    lines.append("")

    # ---- Plain-language summary for the AI reader ------------------------
    lines.append("## Dataset Summary")
    lines.append("")
    lines.append(f"- Total lots: **{len(scored)}**")
    lines.append(f"- Asset categories: **{scored['AssetCategory'].nunique()}**")
    lines.append(
        f"- Average Buyer Engagement Score: "
        f"**{scored['BuyerEngagementScore'].mean():.2f}**"
    )
    if not scored.empty:
        top = scored.iloc[0]
        lines.append(
            f"- Highest-engagement lot: **{top.get('StockNumber','—')}** "
            f"({top.get('AssetCategory','—')}) at "
            f"**{top.get('BuyerEngagementScore','—')}** views/day."
        )
    lines.append(f"- Lots in hot-selling segments: **{len(hot_inventory)}**")
    lines.append("")

    return "\n".join(lines)


def _hot_lookup(hot: "pd.DataFrame") -> dict:
    """Build a (category, region) -> human-readable reason map."""
    lookup: dict = {}
    for _, r in hot.iterrows():
        reasons = []
        reasons.append(f"supply {r['RegionalInventoryChangePct']:+.1f}%")
        if r["RegionalPriceChangePct"] > 0:
            reasons.append(f"price {r['RegionalPriceChangePct']:+.1f}%")
        if r["AuctionValueChangePct"] > 0:
            reasons.append(f"auction {r['AuctionValueChangePct']:+.1f}%")
        text = ", ".join(reasons)
        lookup[(r.get("AssetCategory"), r.get("Region"))] = text
        lookup.setdefault((r.get("AssetCategory"), None), text)
    return lookup


# --------------------------------------------------------------------------- #
# Orchestration                                                                #
# --------------------------------------------------------------------------- #
def run(base_dir: Path) -> Path:
    import datetime as _dt

    generated_on = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    step("Stage 1/4  Loading and validating source files")
    inv_raw = load_csv(base_dir / INVENTORY_CSV, REQUIRED_INVENTORY_COLS, "Inventory")
    web_raw = load_csv(base_dir / WEBSTATS_CSV, REQUIRED_WEBSTATS_COLS, "WebStats")
    trends_raw = load_csv(
        base_dir / MARKET_TRENDS_CSV, REQUIRED_TREND_COLS, "Market Report"
    )

    step("Stage 2/4  Cleaning, merging, and scoring")
    inv = clean_inventory(inv_raw)
    web = clean_webstats(web_raw)
    scored = merge_and_score(inv, web)

    step("Stage 3/4  Cross-referencing regional market trends")
    hot = flag_hot_categories(trends_raw)
    hot_inventory = match_inventory_to_hot(scored, hot)

    step("Stage 4/4  Rendering NotebookLM source document")
    markdown = build_markdown(scored, hot, hot_inventory, generated_on)
    out_path = base_dir / OUTPUT_MD
    out_path.write_text(markdown, encoding="utf-8")
    ok(f"Wrote {out_path.name} ({len(markdown):,} characters).")
    return out_path


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    base_dir = Path(argv[0]).resolve() if argv else Path(__file__).resolve().parent

    print("=" * 64, flush=True)
    print(" SANDHILLS MARKET SNAPSHOT — NotebookLM source builder", flush=True)
    print("=" * 64, flush=True)
    print(f" Working directory: {base_dir}", flush=True)

    try:
        out_path = run(base_dir)
    except PipelineError as exc:
        sys.stderr.write(f"\n!! PIPELINE HALTED: {exc}\n")
        return 1
    except Exception as exc:  # pragma: no cover - last-resort guard
        sys.stderr.write(f"\n!! UNEXPECTED ERROR: {exc}\n")
        return 3

    print("\n" + "=" * 64, flush=True)
    print(f" DONE. Drop '{out_path.name}' into Google NotebookLM to start", flush=True)
    print(" chatting with your live market snapshot.", flush=True)
    print("=" * 64, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
