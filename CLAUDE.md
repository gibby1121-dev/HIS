# CLAUDE.md — HIS (Heartland Iron Solutions)

## What this repository is

Equipment-market tooling for the Heartland Iron Solutions / Mid-Iowa auction
business. The core deliverable is the **Sandhills Market Snapshot pipeline**
(`market_snapshot.py`): it merges lot inventory with Sandhills WebStats
traffic, computes a Buyer Engagement Score, overlays regional market trends,
and renders a NotebookLM-ready Markdown document.

Secondary component: the **Hallway task/results log** (`task_log.py`,
`hooks/tasklog_session_end.py`) — a SQLite-backed ledger of closed tasks across
agents/ventures, hosted here at the owner's direction pending the Hermes VPS
buildout. It is cross-venture operational infra (rows carry a
`personal | joint | operational` classification), not equipment tooling; it
lives here as a deliberate exception, not a precedent for adding other
ventures. See `TASK_LOG_README.md`, including the Hermes migration path that
eventually moves it out.

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
pytest                                # unit tests
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
6. Keep the task-log schema in sync across `task_log.py`, `TASK_LOG_README.md`,
   and `tests/test_task_log.py` if columns or the enforced
   classification/status vocabularies change.
