# Hallway Task/Results Log

A small, queryable, SQLite-backed ledger of closed tasks across agents and
ventures. It replaces the manual `Hallway_Daily_Task_Results_Log` Google Doc:
one row per closed task, appended automatically where a chokepoint exists,
queryable without reconstructing the day from scratch.

## Why this exists (and what it deliberately is not)

The Drive log worked only if every agent remembered to append a row — and that
is exactly what kept failing. **The problem was capture, not storage.** So the
value here is not "a database" (storage is trivial); it is:

1. **A frozen schema** so every row is consistent and sortable, and
2. **An append path cheap enough to wire into a session-end hook**, so the
   write stops depending on anyone remembering.

This is intentionally *not* a service yet. It is a file + CLI + hook. When the
Hermes VPS is stood up and a capture path exists for chat sessions, this table
ports over with a `sqlite3 task_log.db .dump` and reload — no redesign — and
the Drive log retires in that same move (no parallel systems).

## Schema (frozen contract)

The table is a strict superset of the Drive log's columns, so importing the old
doc is a column-map. Do not rename or drop columns without updating this file,
`task_log.py`, and the tests together.

| column           | meaning                                             |
|------------------|-----------------------------------------------------|
| `id`             | autoincrement row id                                |
| `logged_at`      | ISO-8601 UTC timestamp the row was recorded         |
| `task_date`      | business date `YYYY-MM-DD` (defaults to today, UTC) |
| `agent`          | who ran it — Jane, Grant, Claude, …                 |
| `venture`        | HIS, MIA, personal, …                               |
| `classification` | **separation tier:** `personal` \| `joint` \| `operational` (enforced) |
| `task`           | what was done                                       |
| `output_link`    | where it landed — URL / path / PR                   |
| `status`         | `done` \| `blocked` \| `in_progress` \| `cancelled` |
| `run_id`         | session/run id — enables idempotent re-logging      |
| `surface`        | `chat` \| `ops` \| `code`                           |

`classification` is validated on every write so the ledger stays sortable under
the Kent-personal / Joint / Operational split from day one. `venture` is the
finer-grained axis (which business); `classification` is the coarse separation
axis (whose data / which boundary).

The database file (`task_log.db`) is **git-ignored** — it is data, not source.

## Usage

```bash
# Create the database (idempotent; append also creates it on first use)
python3 task_log.py init

# Log a closed task
python3 task_log.py append \
    --agent Grant --venture MIA --classification operational \
    --task "Posted post-sale auction recap" --status done \
    --output-link "https://drive/recap-0713" --surface ops

# What ran yesterday?
python3 task_log.py query --yesterday

# What did Grant touch this week?
python3 task_log.py query --agent Grant --week

# Everything personal-classified (separation review)
python3 task_log.py query --classification personal --json
```

Query filters: `--agent --venture --classification --status --surface --run-id
--date --since --until`, plus the shortcuts `--today --yesterday --week`,
`--limit N`, and `--json`. Point at an alternate database with `--db PATH` (or
the `TASKLOG_DB` env var).

## Automatic capture: the session-end hook

`hooks/tasklog_session_end.py` is the capture chokepoint for agent (Claude
Code) sessions. Wired into the **Stop** hook, it records the session's row
automatically instead of relying on memory. Drive it with environment
variables:

| env var                 | default       | notes                              |
|-------------------------|---------------|------------------------------------|
| `TASKLOG_TASK`          | *(required)*  | no value → nothing auto-logged     |
| `TASKLOG_AGENT`         | `Claude`      |                                    |
| `TASKLOG_VENTURE`       | `HIS`         |                                    |
| `TASKLOG_CLASSIFICATION`| `operational` | `personal`\|`joint`\|`operational` |
| `TASKLOG_STATUS`        | `done`        |                                    |
| `TASKLOG_OUTPUT_LINK`   | —             |                                    |
| `TASKLOG_RUN_ID`        | —             | makes re-fires idempotent          |
| `TASKLOG_SURFACE`       | `code`        |                                    |
| `TASKLOG_DB`            | `task_log.db` |                                    |
| `TASKLOG_ENFORCE`       | —             | `1` → session with no row exits ≠0 |

Wire it in `.claude/settings.json`:

```json
{ "hooks": { "Stop": [ { "hooks": [
    { "type": "command", "command": "python3 hooks/tasklog_session_end.py" }
] } ] } }
```

By default a session with no `TASKLOG_TASK` only prints a reminder (exit 0, so
it never strands a session). Set `TASKLOG_ENFORCE=1` to give it teeth — the
Stop hook then blocks the close until a row exists.

**Coverage, stated honestly:** this enforces capture for ops/code sessions,
which have a session-end chokepoint. Chat sessions (Jane) do not have one yet,
so for now they still append with the `append` command. Closing that gap is a
prerequisite before retiring the Drive log — see below.

## Migration path to Hermes

1. Stand up the service on the Hermes VPS; expose a thin append endpoint whose
   payload mirrors these columns exactly.
2. Add a chat-surface capture path so Jane's rows are recorded without manual
   appends.
3. Port existing rows: `sqlite3 task_log.db .dump` → load on Hermes.
4. Retire the Drive log in the same change — one system, not two.
