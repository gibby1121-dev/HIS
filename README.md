# HIS — Heartland Iron Solutions

Equipment-market tooling for the Heartland Iron Solutions / Mid-Iowa auction
business.

The core deliverable is the **Sandhills Market Snapshot pipeline** — see
[`MARKET_SNAPSHOT_README.md`](MARKET_SNAPSHOT_README.md) for what it does and
how to run it. Repo rules and agent guidance live in [`CLAUDE.md`](CLAUDE.md).

## Tools

| Tool | What it does |
|------|--------------|
| [`market_snapshot.py`](MARKET_SNAPSHOT_README.md) | Merges lot inventory with Sandhills WebStats traffic, scores buyer engagement, overlays regional trends, renders a NotebookLM-ready document. |
| [`vin_check.py`](VIN_CHECK_README.md) | Validates and decodes VINs from a sourcing run and emits manufacturer window-sticker URLs — separates real units from ghost listings before anyone starts calling dealers. |

> **Note:** the regenerative soil-biology venture (investor decks) lives in
> its own repository, `gibby1121-dev/soil-biology`. Do not add deck content here.
