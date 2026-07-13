#!/usr/bin/env python3
"""Hallway task/results log — a small, queryable, SQLite-backed task ledger.

This is the automated successor to the manual `Hallway_Daily_Task_Results_Log`
Google Doc. Each closed task is one row. Agents (or a session-end hook) append
rows; humans query them ("what ran yesterday", "what did Grant touch this
week") without reconstructing the day from scratch.

Design notes (why this shape):
  * The problem it fixes is *capture*, not storage. Storage is trivial; the
    value is (a) a frozen schema so rows are consistent, and (b) an append path
    cheap enough to wire into a session-end hook so the write stops depending
    on anyone remembering. See `hooks/tasklog_session_end.py`.
  * The schema is a strict superset of the Drive log's columns
    (date, agent, venture, task, output link, status), so migrating the
    existing doc is a column-map, and porting this table to the Hermes VPS
    later is a `.dump` + reload — not a redesign.
  * `classification` (personal | joint | operational) is enforced on every
    row so the ledger stays sortable under the Kent-personal / Joint /
    Operational separation split from day one.

Stdlib only (sqlite3 + argparse) — no new dependencies.

Exit codes:
  0  success
  2  usage / validation error (bad classification, missing field, ...)
  3  storage error (cannot open or write the database)
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DEFAULT_DB = os.environ.get("TASKLOG_DB", "task_log.db")

# Frozen vocabularies. These are the contract other agents and the hook code to.
CLASSIFICATIONS = ("personal", "joint", "operational")
STATUSES = ("done", "blocked", "in_progress", "cancelled")

# Columns in append order. Kept explicit so the schema is greppable and the
# Drive-log → SQLite mapping is obvious.
SCHEMA = """
CREATE TABLE IF NOT EXISTS task_results (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    logged_at      TEXT NOT NULL,   -- ISO8601 UTC; when the row was recorded
    task_date      TEXT NOT NULL,   -- business date YYYY-MM-DD
    agent          TEXT NOT NULL,   -- Jane, Grant, Claude, ...
    venture        TEXT NOT NULL,   -- HIS, MIA, personal, ...
    classification TEXT NOT NULL,   -- personal | joint | operational
    task           TEXT NOT NULL,   -- what was done
    output_link    TEXT,            -- where it landed (URL / path / PR)
    status         TEXT NOT NULL,   -- done | blocked | in_progress | cancelled
    run_id         TEXT,            -- session/run id (dedupe + hook enforcement)
    surface        TEXT             -- chat | ops | code
);
CREATE INDEX IF NOT EXISTS idx_task_results_date  ON task_results(task_date);
CREATE INDEX IF NOT EXISTS idx_task_results_agent ON task_results(agent);
CREATE INDEX IF NOT EXISTS idx_task_results_run   ON task_results(run_id);
"""


class TaskLogError(Exception):
    """Raised on validation or storage problems. Message is shown to the user."""


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #
def connect(db_path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    """Open (creating if needed) the task-log database and ensure the schema."""
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)
        conn.commit()
    except sqlite3.Error as exc:  # pragma: no cover - defensive
        raise TaskLogError(f"could not open task log at {db_path!r}: {exc}") from exc
    return conn


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def _require(value: str | None, field: str) -> str:
    if value is None or not str(value).strip():
        raise TaskLogError(f"{field} is required")
    return str(value).strip()


def _validate_choice(value: str, field: str, allowed: tuple[str, ...]) -> str:
    v = value.strip().lower().replace("-", "_").replace(" ", "_")
    if v not in allowed:
        raise TaskLogError(
            f"{field} must be one of {', '.join(allowed)} (got {value!r})"
        )
    return v


def _validate_date(value: str, field: str) -> str:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise TaskLogError(f"{field} must be YYYY-MM-DD (got {value!r})") from exc


# --------------------------------------------------------------------------- #
# Append
# --------------------------------------------------------------------------- #
def append(
    conn: sqlite3.Connection,
    *,
    agent: str,
    venture: str,
    classification: str,
    task: str,
    status: str,
    output_link: str | None = None,
    task_date: str | None = None,
    run_id: str | None = None,
    surface: str | None = None,
) -> int:
    """Insert one task-result row. Returns the new row id.

    Idempotency: if a row already exists with the same (run_id, task) and
    run_id is set, the existing id is returned instead of inserting a
    duplicate. This makes the session-end hook safe to fire more than once.
    """
    row = {
        "logged_at": _utc_now_iso(),
        "task_date": _validate_date(task_date, "date") if task_date else _today_iso(),
        "agent": _require(agent, "agent"),
        "venture": _require(venture, "venture"),
        "classification": _validate_choice(
            _require(classification, "classification"), "classification", CLASSIFICATIONS
        ),
        "task": _require(task, "task"),
        "output_link": (output_link or "").strip() or None,
        "status": _validate_choice(_require(status, "status"), "status", STATUSES),
        "run_id": (run_id or "").strip() or None,
        "surface": (surface or "").strip() or None,
    }

    if row["run_id"]:
        existing = conn.execute(
            "SELECT id FROM task_results WHERE run_id = ? AND task = ?",
            (row["run_id"], row["task"]),
        ).fetchone()
        if existing:
            return int(existing["id"])

    cur = conn.execute(
        """
        INSERT INTO task_results
            (logged_at, task_date, agent, venture, classification,
             task, output_link, status, run_id, surface)
        VALUES
            (:logged_at, :task_date, :agent, :venture, :classification,
             :task, :output_link, :status, :run_id, :surface)
        """,
        row,
    )
    conn.commit()
    return int(cur.lastrowid)


# --------------------------------------------------------------------------- #
# Query
# --------------------------------------------------------------------------- #
def query(
    conn: sqlite3.Connection,
    *,
    agent: str | None = None,
    venture: str | None = None,
    classification: str | None = None,
    status: str | None = None,
    surface: str | None = None,
    run_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    on: str | None = None,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    """Return rows matching the given filters, newest business-date first."""
    clauses: list[str] = []
    params: list[object] = []

    def eq(col: str, val: str | None) -> None:
        if val:
            clauses.append(f"{col} = ?")
            params.append(val.strip())

    eq("agent", agent)
    eq("venture", venture)
    eq("surface", surface)
    eq("run_id", run_id)
    if classification:
        clauses.append("classification = ?")
        params.append(_validate_choice(classification, "classification", CLASSIFICATIONS))
    if status:
        clauses.append("status = ?")
        params.append(_validate_choice(status, "status", STATUSES))
    if on:
        clauses.append("task_date = ?")
        params.append(_validate_date(on, "date"))
    if since:
        clauses.append("task_date >= ?")
        params.append(_validate_date(since, "since"))
    if until:
        clauses.append("task_date <= ?")
        params.append(_validate_date(until, "until"))

    sql = "SELECT * FROM task_results"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY task_date DESC, id DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))

    return conn.execute(sql, params).fetchall()


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _render_table(rows: list[sqlite3.Row]) -> str:
    if not rows:
        return "(no matching task-log entries)"
    cols = ["task_date", "agent", "venture", "classification", "status", "task", "output_link"]
    headers = {c: c.replace("_", " ").title() for c in cols}
    widths = {
        c: max(len(headers[c]), *(len(str(r[c] or "")) for r in rows)) for c in cols
    }

    def fmt(values: dict) -> str:
        return "  ".join(str(values[c] or "").ljust(widths[c]) for c in cols)

    lines = [fmt(headers), "  ".join("-" * widths[c] for c in cols)]
    lines += [fmt(dict(r)) for r in rows]
    return "\n".join(lines)


def _render_json(rows: list[sqlite3.Row]) -> str:
    return json.dumps([dict(r) for r in rows], indent=2)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _add_query_window(args, kwargs: dict) -> None:
    """Translate --today/--yesterday/--week convenience flags into a window."""
    today = date.today()
    if args.today:
        kwargs["on"] = today.isoformat()
    if args.yesterday:
        kwargs["on"] = (today - timedelta(days=1)).isoformat()
    if args.week:
        kwargs["since"] = (today - timedelta(days=7)).isoformat()


def _cmd_append(conn: sqlite3.Connection, args) -> int:
    new_id = append(
        conn,
        agent=args.agent,
        venture=args.venture,
        classification=args.classification,
        task=args.task,
        status=args.status,
        output_link=args.output_link,
        task_date=args.date,
        run_id=args.run_id,
        surface=args.surface,
    )
    print(f"logged task-result #{new_id}")
    return 0


def _cmd_query(conn: sqlite3.Connection, args) -> int:
    kwargs = dict(
        agent=args.agent,
        venture=args.venture,
        classification=args.classification,
        status=args.status,
        surface=args.surface,
        run_id=args.run_id,
        since=args.since,
        until=args.until,
        on=args.date,
        limit=args.limit,
    )
    _add_query_window(args, kwargs)
    rows = query(conn, **kwargs)
    print(_render_json(rows) if args.json else _render_table(rows))
    return 0


def _cmd_init(conn: sqlite3.Connection, args) -> int:
    # connect() already ran the schema; this just confirms it loudly.
    print(f"task log ready at {args.db}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="task_log.py",
        description="Hallway task/results log (SQLite-backed successor to the Drive log).",
    )
    parser.add_argument("--db", default=DEFAULT_DB, help=f"database path (default: {DEFAULT_DB})")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the database and schema if missing")

    ap = sub.add_parser("append", help="log one closed task")
    ap.add_argument("--agent", required=True, help="who ran it (Jane, Grant, Claude, ...)")
    ap.add_argument("--venture", required=True, help="HIS, MIA, personal, ...")
    ap.add_argument(
        "--classification", required=True,
        help="separation tier: " + " | ".join(CLASSIFICATIONS),
    )
    ap.add_argument("--task", required=True, help="what was done")
    ap.add_argument(
        "--status", required=True, help="status: " + " | ".join(STATUSES)
    )
    ap.add_argument("--output-link", dest="output_link", help="where it landed (URL/path/PR)")
    ap.add_argument("--date", help="business date YYYY-MM-DD (default: today, UTC)")
    ap.add_argument("--run-id", dest="run_id", help="session/run id (enables idempotent re-logs)")
    ap.add_argument("--surface", help="chat | ops | code")

    qp = sub.add_parser("query", help="query the log")
    qp.add_argument("--agent")
    qp.add_argument("--venture")
    qp.add_argument("--classification")
    qp.add_argument("--status")
    qp.add_argument("--surface")
    qp.add_argument("--run-id", dest="run_id")
    qp.add_argument("--date", help="exact business date YYYY-MM-DD")
    qp.add_argument("--since", help="business date >= YYYY-MM-DD")
    qp.add_argument("--until", help="business date <= YYYY-MM-DD")
    qp.add_argument("--today", action="store_true", help="shortcut: date == today")
    qp.add_argument("--yesterday", action="store_true", help="shortcut: date == yesterday")
    qp.add_argument("--week", action="store_true", help="shortcut: last 7 days")
    qp.add_argument("--limit", type=int, help="max rows")
    qp.add_argument("--json", action="store_true", help="emit JSON instead of a table")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        conn = connect(args.db)
        try:
            if args.command == "append":
                return _cmd_append(conn, args)
            if args.command == "query":
                return _cmd_query(conn, args)
            if args.command == "init":
                return _cmd_init(conn, args)
        finally:
            conn.close()
    except TaskLogError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2  # pragma: no cover - argparse enforces a valid subcommand


if __name__ == "__main__":
    raise SystemExit(main())
