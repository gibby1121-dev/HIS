# CLAUDE.md — HIS (Heartland Iron Solutions)

## What this repository is

Equipment-market tooling for the Heartland Iron Solutions / Mid-Iowa auction
business. The core deliverable is the **Sandhills Market Snapshot pipeline**
(`market_snapshot.py`): it merges lot inventory with Sandhills WebStats
traffic, computes a Buyer Engagement Score, overlays regional market trends,
and renders a NotebookLM-ready Markdown document.

The first seller-facing product is the **Trade-In Check** (`trade_in_check.py`)
for owner-sellers of large row-crop iron: it unbundles a dealer trade-in quote,
values the trade against comparable sales, and shows what the operator gives
up by trading instead of selling. See `TRADE_IN_CHECK_README.md`.

## What this repository is NOT

Do **not** add work for other ventures here. In particular:

- **Soil-biology venture** (investor decks): migrated out to
  `gibby1121-dev/soil-biology` on 2026-07-03. Do not re-add deck content here.
- **Health Advisor / personal health material**: never belongs in this repo.
  (See closed PR #2 — its branch is pending migration to a private repo.)
- Marketing/creator research, knowledge-OS visualizations, or anything not
  related to equipment-market tooling.

If a task doesn't fit the equipment-tooling scope, say so instead of
committing it here.

## How to run

```bash
pip install -r requirements.txt
python3 market_snapshot.py            # uses CSVs in the current directory
./run_market_snapshot.sh              # one-shot runner with env checks
python3 trade_in_check.py             # uses trade_deal.json + comps.csv
pytest                                # unit tests
```

Inputs: `inventory.csv`, `webstats.csv`, `market_trends.csv` (sample/template
data is committed). Output: `notebooklm_source.md` — **generated, git-ignored,
never commit it**.

Trade-In Check inputs: `trade_deal.json`, `comps.csv` (synthetic sample data is
committed). Output: `trade_in_report.md` — generated, git-ignored. Its output
is a decision aid and CPA-ready summary, **never tax advice or an appraisal**.

## Rules for agent sessions

1. **PRs always target `main`.** Never open a PR whose base is another
   `claude/*` or feature branch.
2. One venture per repo; one topic per PR.
3. Run `pytest` before pushing changes to `market_snapshot.py` or
   `trade_in_check.py`; CI runs the tests plus smoke runs of both tools on
   the sample data.
4. Delete your feature branch after merge.
5. Keep required input columns in sync across `market_snapshot.py`,
   `MARKET_SNAPSHOT_README.md`, and the tests if they change (same for
   `trade_in_check.py` / `TRADE_IN_CHECK_README.md`).
