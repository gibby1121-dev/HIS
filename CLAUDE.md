# CLAUDE.md — HIS (Heartland Iron Solutions)

## Who HIS is (read before framing any work)

**Heartland Iron Solutions (HIS) is an AI agency that specializes in heavy
equipment as its initial vertical.** It is **not** an auction company, not an
equipment marketing shop with AI tooling, and not a consulting practice. HIS
sells intelligence, matchmaking, and valuation; its moat is agent-and-process
IP.

- **Mid-Iowa Auction Co. (MIA)** is a separate business: Matt Paglia's
  auction house, which is HIS's day-one channel and proving ground. MIA stays
  on Sandhills as its system of record. Do not merge the two.
- HIS segments: **HIS Advantage** (valuation and advisory), **HIS Auction
  Service** (the MIA operations pillar), and **Gavel** (price discovery,
  adjacent).
- Positioning follows the **Epiphany Standard**. HIS-branded copy never uses
  *auction/auctioneer*, *consignor/consignment*, or *salesman*. Show the work
  and let the iron be the subject.
- Canonical source: the Drive Vault brief
  `HIS_Identity_Brief_and_Facebook_Strategy_v0.1.md`, which rests on
  `HIS_AIAgency_Vision_v0`. Doctrine changes go through Jane via the Hallway.

## What this repository is

Equipment-market tooling for HIS. Much of it runs on data from MIA's
Sandhills account. The core deliverable is the **Sandhills Market Snapshot pipeline**
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

## How to run

```bash
pip install -r requirements.txt
python3 market_snapshot.py            # uses CSVs in the current directory
./run_market_snapshot.sh              # one-shot runner with env checks
python3 meta_pilot.py --help          # Meta pilot: unit pages, catalog, Gavel Reports
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
