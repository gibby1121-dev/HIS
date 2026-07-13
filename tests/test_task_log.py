"""Tests for the Hallway task/results log.

Cover the append/validation contract, the query filters and convenience
windows, idempotent re-logging by run_id, and the session-end hook's
capture behaviour.
"""

import importlib
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import task_log as tl


@pytest.fixture
def conn(tmp_path):
    c = tl.connect(tmp_path / "test.db")
    yield c
    c.close()


def _append(conn, **overrides):
    base = dict(
        agent="Grant",
        venture="MIA",
        classification="operational",
        task="Ran auction recap",
        status="done",
    )
    base.update(overrides)
    return tl.append(conn, **base)


class TestAppendValidation:
    def test_append_returns_row_id_and_persists(self, conn):
        new_id = _append(conn)
        assert new_id == 1
        rows = tl.query(conn)
        assert len(rows) == 1
        assert rows[0]["agent"] == "Grant"
        assert rows[0]["classification"] == "operational"

    def test_task_date_defaults_to_today(self, conn):
        _append(conn)
        # Compare against the module's UTC "today" to avoid TZ edge flakiness.
        assert tl.query(conn)[0]["task_date"] == tl._today_iso()

    def test_missing_required_field_raises(self, conn):
        with pytest.raises(tl.TaskLogError, match="task is required"):
            _append(conn, task="")

    def test_bad_classification_raises(self, conn):
        with pytest.raises(tl.TaskLogError, match="classification must be one of"):
            _append(conn, classification="misc")

    def test_bad_status_raises(self, conn):
        with pytest.raises(tl.TaskLogError, match="status must be one of"):
            _append(conn, status="finished")

    def test_classification_and_status_are_normalized(self, conn):
        _append(conn, classification="Operational", status="In-Progress")
        row = tl.query(conn)[0]
        assert row["classification"] == "operational"
        assert row["status"] == "in_progress"

    def test_bad_date_raises(self, conn):
        with pytest.raises(tl.TaskLogError, match="date must be YYYY-MM-DD"):
            _append(conn, task_date="07/13/2026")

    def test_blank_output_link_stored_as_null(self, conn):
        _append(conn, output_link="   ")
        assert tl.query(conn)[0]["output_link"] is None


class TestIdempotency:
    def test_same_run_id_and_task_does_not_duplicate(self, conn):
        first = _append(conn, run_id="sess-1", task="Merged listings")
        second = _append(conn, run_id="sess-1", task="Merged listings")
        assert first == second
        assert len(tl.query(conn)) == 1

    def test_same_run_id_different_task_inserts(self, conn):
        _append(conn, run_id="sess-1", task="Merged listings")
        _append(conn, run_id="sess-1", task="Posted recap")
        assert len(tl.query(conn, run_id="sess-1")) == 2

    def test_no_run_id_allows_duplicates(self, conn):
        _append(conn, task="dup")
        _append(conn, task="dup")
        assert len(tl.query(conn)) == 2


class TestQuery:
    def test_filter_by_agent(self, conn):
        _append(conn, agent="Grant")
        _append(conn, agent="Jane")
        rows = tl.query(conn, agent="Grant")
        assert len(rows) == 1 and rows[0]["agent"] == "Grant"

    def test_date_window_since_until(self, conn):
        _append(conn, task="old", task_date="2026-07-01")
        _append(conn, task="mid", task_date="2026-07-08")
        _append(conn, task="new", task_date="2026-07-13")
        rows = tl.query(conn, since="2026-07-05", until="2026-07-10")
        assert [r["task"] for r in rows] == ["mid"]

    def test_ordering_newest_business_date_first(self, conn):
        _append(conn, task="a", task_date="2026-07-01")
        _append(conn, task="b", task_date="2026-07-13")
        assert [r["task"] for r in tl.query(conn)] == ["b", "a"]

    def test_limit(self, conn):
        for i in range(5):
            _append(conn, task=f"t{i}")
        assert len(tl.query(conn, limit=2)) == 2

    def test_query_bad_classification_raises(self, conn):
        with pytest.raises(tl.TaskLogError):
            tl.query(conn, classification="nonsense")


class TestCli:
    def test_append_then_query_json(self, tmp_path, capsys):
        db = str(tmp_path / "cli.db")
        rc = tl.main(
            [
                "--db", db, "append",
                "--agent", "Grant", "--venture", "MIA",
                "--classification", "operational",
                "--task", "Kicked CI", "--status", "done",
                "--output-link", "https://example/pr/1", "--surface", "code",
            ]
        )
        assert rc == 0
        assert "logged task-result #1" in capsys.readouterr().out

        rc = tl.main(["--db", db, "query", "--agent", "Grant", "--json"])
        assert rc == 0
        out = capsys.readouterr().out
        assert '"task": "Kicked CI"' in out
        assert '"output_link": "https://example/pr/1"' in out

    def test_query_yesterday_shortcut(self, tmp_path, capsys):
        db = str(tmp_path / "cli.db")
        y = (date.today() - timedelta(days=1)).isoformat()
        tl.main(
            ["--db", db, "append", "--agent", "Jane", "--venture", "HIS",
             "--classification", "joint", "--task", "Y task", "--status", "done",
             "--date", y]
        )
        capsys.readouterr()
        tl.main(["--db", db, "append", "--agent", "Jane", "--venture", "HIS",
                 "--classification", "joint", "--task", "Today task", "--status", "done"])
        capsys.readouterr()
        tl.main(["--db", db, "query", "--yesterday"])
        out = capsys.readouterr().out
        assert "Y task" in out and "Today task" not in out

    def test_bad_classification_exits_2(self, tmp_path, capsys):
        db = str(tmp_path / "cli.db")
        rc = tl.main(
            ["--db", db, "append", "--agent", "X", "--venture", "HIS",
             "--classification", "bogus", "--task", "t", "--status", "done"]
        )
        assert rc == 2
        assert "classification must be one of" in capsys.readouterr().err


class TestSessionEndHook:
    @pytest.fixture
    def hook(self):
        spec = importlib.util.spec_from_file_location(
            "tasklog_session_end",
            Path(__file__).resolve().parent.parent / "hooks" / "tasklog_session_end.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_auto_logs_when_task_env_set(self, hook, tmp_path, monkeypatch):
        db = str(tmp_path / "hook.db")
        monkeypatch.setenv("TASKLOG_DB", db)
        monkeypatch.setenv("TASKLOG_TASK", "Persistence buildout")
        monkeypatch.setenv("TASKLOG_RUN_ID", "run-42")
        assert hook.main() == 0
        rows = tl.query(tl.connect(db), run_id="run-42")
        assert len(rows) == 1
        assert rows[0]["agent"] == "Claude"  # default
        assert rows[0]["surface"] == "code"  # default

    def test_idempotent_across_two_fires(self, hook, tmp_path, monkeypatch):
        db = str(tmp_path / "hook.db")
        monkeypatch.setenv("TASKLOG_DB", db)
        monkeypatch.setenv("TASKLOG_TASK", "Persistence buildout")
        monkeypatch.setenv("TASKLOG_RUN_ID", "run-42")
        hook.main()
        hook.main()
        assert len(tl.query(tl.connect(db))) == 1

    def test_advisory_when_no_task(self, hook, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("TASKLOG_DB", str(tmp_path / "hook.db"))
        monkeypatch.delenv("TASKLOG_TASK", raising=False)
        monkeypatch.delenv("TASKLOG_ENFORCE", raising=False)
        assert hook.main() == 0
        assert "no TASKLOG_TASK set" in capsys.readouterr().err

    def test_enforce_blocks_when_no_task(self, hook, tmp_path, monkeypatch):
        monkeypatch.setenv("TASKLOG_DB", str(tmp_path / "hook.db"))
        monkeypatch.delenv("TASKLOG_TASK", raising=False)
        monkeypatch.setenv("TASKLOG_ENFORCE", "1")
        assert hook.main() == 2
