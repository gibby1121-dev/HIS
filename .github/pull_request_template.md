<!--
Issue-Driven Development: no PR without an approved issue behind it.
Keep it to ONE topic. PRs always target `main`.
-->

## Linked issue

Closes #<!-- issue number -->

<!-- No issue? Stop and open one first. Work without an approved issue gets closed. -->

## What & why

<!-- What does this change, and what value from the issue does it deliver? -->

## Scope check

- [ ] Traces back to an approved issue that passed the value gate.
- [ ] One topic only — unrelated changes belong in their own PR.
- [ ] Equipment-market tooling only (not soil-biology, health, or marketing/creator work — see CLAUDE.md).
- [ ] Base branch is `main`.

## Verification

- [ ] `pytest` passes locally (required for changes to `market_snapshot.py`).
- [ ] If required input columns changed, they're in sync across `market_snapshot.py`, `MARKET_SNAPSHOT_README.md`, and the tests.
- [ ] I'll delete this feature branch after merge.
