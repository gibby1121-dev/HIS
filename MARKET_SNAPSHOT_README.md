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
5. **Renders** `notebooklm_source.md` with a **🔥 Hot-Selling Action Items**
   section pinned to the top, followed by the full ranked dataset.

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
- **webstats.csv**: `StockNumber, Views` (plus any optional traffic metrics).
- **market_trends.csv**: `AssetCategory, RegionalInventoryChangePct,
  RegionalPriceChangePct, AuctionValueChangePct` (plus optional `Region`).

Swap the sample CSVs for your real exports — keep the column headers the same
and the pipeline will pick them up automatically.

## Next step

Upload the generated `notebooklm_source.md` into Google NotebookLM as a source,
then chat with your live market snapshot immediately.
