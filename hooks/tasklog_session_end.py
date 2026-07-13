#!/usr/bin/env python3
"""Session-end task-log hook — the capture chokepoint for ops/code sessions.

The manual Drive log failed because the write depended on someone remembering.
Agent (Claude Code) sessions already have an enforced chokepoint: the Stop
hook that runs before a session closes. Wiring the log-append into that hook is
what converts "remember to append" into "the session records its own row."

Behaviour, driven by environment variables:

  TASKLOG_TASK            what was done            (required to auto-log)
  TASKLOG_AGENT           who ran it               (default: "Claude")
  TASKLOG_VENTURE         HIS | MIA | personal     (default: "HIS")
  TASKLOG_CLASSIFICATION  personal|joint|operational (default: "operational")
  TASKLOG_STATUS          done|blocked|in_progress|cancelled (default: "done")
  TASKLOG_OUTPUT_LINK     where it landed          (optional)
  TASKLOG_RUN_ID          session/run id           (optional; makes re-logs idempotent)
  TASKLOG_SURFACE         chat|ops|code            (default: "code")
  TASKLOG_DB              database path            (default: repo task_log.db)
  TASKLOG_ENFORCE         if "1", a session with no logged row exits non-zero

If TASKLOG_TASK is set, the row is written automatically and the hook exits 0.
If it is not set, the hook prints a reminder. That reminder is advisory by
default (exit 0) so it never strands a session; set TASKLOG_ENFORCE=1 to give
it teeth (exit 2 -> the Stop hook blocks the close until a row exists).

Wire it in `.claude/settings.json`:

  { "hooks": { "Stop": [ { "hooks": [
      { "type": "command",
        "command": "python3 hooks/tasklog_session_end.py" } ] } ] } }
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import task_log  # noqa: E402


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if (value is not None and value.strip()) else default


def main() -> int:
    db = _env("TASKLOG_DB", task_log.DEFAULT_DB)
    run_id = _env("TASKLOG_RUN_ID")
    task = _env("TASKLOG_TASK")
    enforce = _env("TASKLOG_ENFORCE") == "1"

    conn = task_log.connect(db)
    try:
        # If a row already exists for this run, we're done — nothing to enforce.
        if run_id:
            existing = task_log.query(conn, run_id=run_id)
            if existing:
                return 0

        if not task:
            msg = (
                "task-log: no TASKLOG_TASK set for this session; "
                "no task-result row recorded."
            )
            if enforce:
                print(f"error: {msg} (TASKLOG_ENFORCE=1)", file=sys.stderr)
                return 2
            print(msg, file=sys.stderr)
            return 0

        try:
            new_id = task_log.append(
                conn,
                agent=_env("TASKLOG_AGENT", "Claude"),
                venture=_env("TASKLOG_VENTURE", "HIS"),
                classification=_env("TASKLOG_CLASSIFICATION", "operational"),
                task=task,
                status=_env("TASKLOG_STATUS", "done"),
                output_link=_env("TASKLOG_OUTPUT_LINK"),
                run_id=run_id,
                surface=_env("TASKLOG_SURFACE", "code"),
            )
        except task_log.TaskLogError as exc:
            print(f"task-log: could not record row: {exc}", file=sys.stderr)
            return 2 if enforce else 0

        print(f"task-log: recorded task-result #{new_id}", file=sys.stderr)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
