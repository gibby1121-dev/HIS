# CLAUDE.md — HIS (Heartland Iron Solutions)

## What this repository is

Equipment-market tooling for the Heartland Iron Solutions / Mid-Iowa auction
business. The core deliverable is the **Sandhills Market Snapshot pipeline**
(`market_snapshot.py`): it merges lot inventory with Sandhills WebStats
traffic, computes a Buyer Engagement Score, overlays regional market trends,
and renders a NotebookLM-ready Markdown document.

The first seller-facing product is the **Trade-In Check** (`trade_in_check.py`
+ the `tradein/` package) for owner-sellers of large row-crop iron: it reads a
dealer quote (Claude, evidence-verified), unbundles the trade over-allowance and
financing, values the trade on a hammer basis calibrated to MIA's own results,
and compares trading with consigning. See `TRADE_IN_CHECK_README.md`; the
research and sources behind it are in `docs/RESEARCH.md`.

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
python3 trade_in_check.py sample      # Trade-In Check on synthetic sample
python3 -m tradein.backtest sample    # leave-one-out accuracy
pytest                                # unit tests
```

Inputs: `inventory.csv`, `webstats.csv`, `market_trends.csv` (sample/template
data is committed). Output: `notebooklm_source.md` — **generated, git-ignored,
never commit it**.

Trade-In Check inputs live in one folder: `trade_deal.json`, optional
`comps.csv` (every row declares `PriceBasis`: hammer / with_bp / asking) and
optional `mia_results/*Auction Summary*.xlsx`. Everything in `sample/` is
**synthetic**. Outputs `trade_in_report.md` and `mia_desk_sheet.md` are
generated and git-ignored. Output is a decision aid and CPA-ready facts, **never
tax advice or an appraisal**. `config/mia_terms.json` placeholders
(verified=false) must not be presented to operators as MIA's real terms.

## Rules for agent sessions

1. **PRs always target `main`.** Never open a PR whose base is another
   `claude/*` or feature branch.
2. One venture per repo; one topic per PR.
3. Run `pytest` before pushing changes to `market_snapshot.py` or
   `tradein/`; CI runs the tests plus smoke runs of both tools and the
   backtest on the sample data. Tests never call the Anthropic API (the
   intake client is mocked).
4. Delete your feature branch after merge.
5. Keep required input columns in sync across `market_snapshot.py`,
   `MARKET_SNAPSHOT_README.md`, and the tests if they change (same for
   `tradein/comps.py` / `TRADE_IN_CHECK_README.md`).
6. Never value a trade from asking prices, and never add a market fact to
   `config/market_facts.json` without a dated source.
