# HIS — Heartland Iron Solutions

Equipment-market tooling for the Heartland Iron Solutions / Mid-Iowa auction
business.

The core deliverable is the **Sandhills Market Snapshot pipeline** — see
[`MARKET_SNAPSHOT_README.md`](MARKET_SNAPSHOT_README.md) for what it does and
how to run it.

The first seller-facing product is the **Trade-In Check**. It reads a dealer's
trade-in quote on large row-crop equipment (photo or PDF) and works out what the
dealer is really paying for the trade, including any over-allowance and the
value of 0% financing. It values the unit on a hammer basis calibrated to
Mid-Iowa's own sale results, and tells the operator whether to trade or consign.
See [`TRADE_IN_CHECK_README.md`](TRADE_IN_CHECK_README.md) and
[`docs/RESEARCH.md`](docs/RESEARCH.md).

Repo rules and agent guidance live in [`CLAUDE.md`](CLAUDE.md).

> **Note:** the regenerative soil-biology venture (investor decks) lives in
> its own repository, `gibby1121-dev/soil-biology`. Do not add deck content here.
