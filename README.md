# Health Advisor

A Jane-side, health-scoped reference layer over Kent's Vault. Answers day-to-day
health questions grounded **only** in the canonical Vault files, follows the
filing conventions, and writes structured updates back to Drive.

**Personal reference, not medical advice.** Open medical questions get flagged
for a physician, not resolved here.

See **[`CLAUDE.md`](CLAUDE.md)** for the full operating contract the agent runs
under. This package is the machinery behind it.

## What it does
- **Read layer** — loads `Health_Stack_MASTER.md` + `Health_References.md` first,
  then the topic-specific detail file; caches per session.
- **Answer layer** — assembles a grounded `AnswerContext` (sources + expanded
  shorthand + triggered guardrails); refuses to answer with zero sources loaded.
- **Guardrails** — methylene-blue safety (MAOI/serotonin + G6PD + the
  same-scale-number dose trap), optimal-vs-standard lab ranges, and open
  medical-loop flags, attached automatically.
- **Write layer** — the connector has no in-place overwrite, so every write
  creates a new file: `download → decode → edit → encode → create_file → report
  new id → surface old id`. Handles the base64 transcription noise, asserts
  match counts before replacing, and degrades to a captured `PendingWrite` on a
  write-authorization outage.
- **Glossary / open-loops tracker** — expands Kent's shorthand; surfaces and
  closes the consolidated open loops.

The Vault file IDs and conventions live in `data/` (the editable source of
truth). The Drive connector is reached through a `DriveClient` protocol — in an
agent session that is the Google Drive MCP (see `CLAUDE.md` for the wiring).

## Use
```bash
pip install -e .            # PyYAML is the only dependency
python -m health_advisor    # status snapshot: open loops + pending writes
pytest -q                   # 35 tests
```

```python
from health_advisor.advisor import Advisor

advisor = Advisor(drive_client)            # drive_client implements DriveClient
ctx = advisor.prepare("what's my target fasting insulin", topic="insulin")
# -> ctx.sources (MASTER, References, IR map), ctx.flags (optimal-vs-standard),
#    ctx.normalized_query (shorthand expanded). The model answers from ctx.
```

## Layout
| Path | Role |
|---|---|
| `data/vault_files.yaml` | File-ID table + conventions (source of truth for IDs) |
| `data/glossary.yaml` | Kent's shorthand |
| `data/open_loops.yaml` | Consolidated open loops |
| `data/pending_writes.yaml` | Writes captured during the write outage |
| `health_advisor/config.py` | Config + load order + scoped search |
| `health_advisor/glossary.py` | Shorthand normalizer |
| `health_advisor/guardrails.py` | Guardrail-flag detection |
| `health_advisor/drive_io.py` | Create-new-file write loop, base64, safe edit |
| `health_advisor/open_loops.py` | Open-loops tracker |
| `health_advisor/advisor.py` | Read → answer-context → write orchestration |
