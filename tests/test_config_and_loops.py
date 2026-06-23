from health_advisor.config import load_config
from health_advisor.open_loops import load_open_loops


def test_master_and_references_load_first():
    cfg = load_config()
    order = cfg.load_order()
    assert order[0].key == "master"
    assert order[1].key == "references"


def test_topic_routing_adds_detail_file():
    cfg = load_config()
    order = cfg.load_order("insulin")
    keys = [f.key for f in order]
    assert "ir_stack_map" in keys
    # MASTER + References still first
    assert keys[0] == "master"


def test_scoped_search_query_uses_vault_parent():
    cfg = load_config()
    q = cfg.scoped_search_query("Labs_Log")
    assert cfg.vault_folder_id in q
    assert "title contains 'Labs_Log'" in q


def test_references_stale_pointer_recorded():
    cfg = load_config()
    ref = cfg.references
    assert ref.id == "1ovGfVPL8OW0GdOeoRAuJKE8asR3gDlGY"
    assert ref.stale_id_in_master == "1XCTnEyZDtOzM8CkF9EmVsnJ4vHqjIUgq"
    assert ref.id != ref.stale_id_in_master


def test_locked_file_flagged():
    cfg = load_config()
    assert cfg.get("morning_protocol").locked is True


def test_open_loops_summary_lists_medical():
    loops = load_open_loops()
    s = loops.summary()
    assert "physician" in s
    assert "[ ]" in s


def test_close_loop_marks_closed(tmp_path):
    loops = load_open_loops()
    n_open = len(loops.open())
    loops.close("stale-references-id", on="2026-06-23", note="reconciled in MASTER")
    assert len(loops.open()) == n_open - 1
    closed = loops.get("stale-references-id")
    assert closed.status == "closed"
    assert closed.closed_on == "2026-06-23"
    # save round-trips
    out = tmp_path / "loops.yaml"
    loops.save(out)
    again = load_open_loops(out)
    assert again.get("stale-references-id").status == "closed"
