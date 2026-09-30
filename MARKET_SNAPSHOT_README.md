# Sandhills Market Snapshot Pipeline

A self-contained Python pipeline that merges internal lot inventory with
Sandhills WebStats traffic, scores buyer engagement, overlays regional
Sandhills Market Report trends, and produces a single Markdown document
(`notebooklm_source.md`) formatted for **Google NotebookLM**.

## What it does

1. **Loads & validates** three CSV inputs and fails loudly if a column is
   missing or a file is empty (i.e. if a source export's format changed).
2. **Cleans & merges** `inventory.csv` + `webstats.csv` on `StockNumber`
   (backfilling unmatched lots with category-average views).
3. **Scores** every lot with a **Buyer Engagement Score = Views ÷ Days on
   Market**.
4. **Cross-references** inventory against `market_trends.csv`, flagging asset
   categories where regional **inventory is dropping** while **price or auction
   value is rising**.
5. **Assigns a retail marketing play** to every lot (see below).
6. **Renders** `notebooklm_source.md` with a **🔥 Hot-Selling Action Items**
   section pinned to the top, then **📣 Retail Marketing Plays**, followed by
   the full ranked dataset.

## Retail marketing plays

Each lot gets exactly one play; rules are checked top to bottom and the first
match wins. "Median" is across the current inventory.

| Play | Rule | Action |
|---|---|---|
| **Hold & Feature** | In a hot segment and engagement ≥ median | Hold price, buy featured placement, answer inquiries same day. |
| **Fix the Listing** | Views ≥ median but inquiry rate (Inquiries ÷ Views) < median | Refresh photos/video, add hours and service history, make price and call to action obvious. |
| **Move to Auction** | ≥ 90 days on market and not in a hot segment | Offer the consignor the next Mid-Iowa sale. |
| **Reprice / Boost** | ≥ 60 days on market and engagement < median | Step price toward auction value or push via email blast / social. |
| **Steady** | Everything else | Keep the listing current. |

"Fix the Listing" needs the optional `Inquiries` column in `webstats.csv`;
without it that play is skipped. Day thresholds are `STALE_DAYS` and
`AUCTION_DAYS` at the top of `market_snapshot.py`.

## Files

| File | Purpose |
|---|---|
| `market_snapshot.py` | The full pipeline (all stages). |
| `run_market_snapshot.sh` | Executive one-shot runner (macOS/Linux). |
| `run_market_snapshot.bat` | Executive one-shot runner (Windows). |
| `inventory.csv` | Internal lot inventory sheet (sample/template). |
| `webstats.csv` | Sandhills WebStats traffic log (sample/template). |
| `market_trends.csv` | Exported Sandhills Market Report (sample/template). |
| `notebooklm_source.md` | **Generated output** — upload this to NotebookLM. |
| `requirements.txt` | Python dependencies (`pandas`). |

## Run it

**macOS / Linux**

```bash
./run_market_snapshot.sh
```

**Windows**

```bat
run_market_snapshot.bat
```

The runner checks for Python and pandas (auto-installing pandas if needed),
validates the inputs, streams live status as the data is merged and validated,
and confirms the deliverable. On any file-format or environment problem it
stops with a clear alert and a non-zero exit code.

You can also run the Python script directly:

```bash
python3 market_snapshot.py            # uses the current directory
python3 market_snapshot.py /path/to/data   # point at another data folder
```

## Expected input columns

- **inventory.csv**: `StockNumber, AssetCategory, ListPrice, AuctionValue,
  DaysOnMarket` (plus optional `Make, Model, Year, Region`).
- **webstats.csv**: `StockNumber, Views` (plus any optional traffic metrics;
  `Inquiries` enables the "Fix the Listing" play).
- **market_trends.csv**: `AssetCategory, RegionalInventoryChangePct,
  RegionalPriceChangePct, AuctionValueChangePct` (plus optional `Region`).

Swap the sample CSVs for your real exports — keep the column headers the same
and the pipeline will pick them up automatically.

## Next step

Upload the generated `notebooklm_source.md` into Google NotebookLM as a source,
then chat with your live market snapshot immediately.
