# CLAUDE.md — HIS (Heartland Iron Solutions)

## What this repository is

Equipment-market tooling for the Heartland Iron Solutions / Mid-Iowa auction
business. The core deliverable is the **Sandhills Market Snapshot pipeline**
(`market_snapshot.py`): it merges lot inventory with Sandhills WebStats
traffic, computes a Buyer Engagement Score, overlays regional market trends,
and renders a NotebookLM-ready Markdown document.

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

## Repo map

- `market_snapshot.py` — the pipeline (import-safe; all work runs under `main()`).
- `MARKET_SNAPSHOT_README.md` — what the pipeline does and how to run it (user-facing).
- `run_market_snapshot.sh` / `run_market_snapshot.bat` — one-shot runners (Unix / Windows) with env checks.
- `tests/test_market_snapshot.py` — unit tests (run with `pytest`).
- `inventory.csv`, `webstats.csv`, `market_trends.csv` — committed sample/template inputs.
- `AGENTIC_WORKSPACE_AUDIT.md` — background audit notes; not part of the pipeline.

## How to run

Targets **Python 3.11** (the version CI runs). `requirements.txt` pins only
`pandas`; `pytest` is a dev-only dependency and must be installed separately.

```bash
pip install -r requirements.txt pytest   # pytest is NOT in requirements.txt
python3 market_snapshot.py                # uses CSVs in the current directory
./run_market_snapshot.sh                  # one-shot runner with env checks (Unix)
run_market_snapshot.bat                   # same, on Windows
pytest                                    # unit tests
```

Inputs: `inventory.csv`, `webstats.csv`, `market_trends.csv` (sample/template
data is committed). Output: `notebooklm_source.md` — **generated, git-ignored,
never commit it**.

## Rules for agent sessions

1. **PRs always target `main`.** Never open a PR whose base is another
   `claude/*` or feature branch.
2. One venture per repo; one topic per PR.
3. Run `pytest` before pushing changes to `market_snapshot.py`; CI runs the
   tests plus a full pipeline smoke run on the sample CSVs.
4. Delete your feature branch after merge.
5. Keep required input columns in sync across `market_snapshot.py`,
   `MARKET_SNAPSHOT_README.md`, and the tests if they change.
