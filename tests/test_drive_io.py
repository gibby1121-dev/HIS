import base64

import pytest

from health_advisor.config import CREATE_FILE_DEFAULTS
from health_advisor.drive_io import (
    DriveClient,
    MatchCountError,
    PendingWrite,
    WriteOutage,
    build_create_params,
    decode_b64,
    edit_then_write,
    encode_b64,
    prepend_entry,
    safe_replace,
    sanitize_b64,
    write_new_version,
)

PARENT = "1HE8eb-B2mdGfz8D6MEs8L3ZFZoV6nXz6"


# --- base64 ---

def test_sanitize_strips_noise_and_fixes_padding():
    clean = encode_b64("hello world")
    noisy = "\n  " + clean[:4] + "✓" + clean[4:] + " \t"  # stray non-ascii + ws
    assert decode_b64(noisy) == "hello world"


def test_roundtrip_unicode():
    s = "optimal < 6 µIU/mL — tighter than standard"
    assert decode_b64(encode_b64(s)) == s


def test_sanitize_returns_valid_b64_bytes():
    out = sanitize_b64("ab*cd")
    # length multiple of 4 after padding
    assert len(out) % 4 == 0
    base64.b64decode(out)  # does not raise


# --- safe replace ---

def test_safe_replace_exact_one():
    assert safe_replace("old id here", "old id", "new id") == "new id here"


def test_safe_replace_wrong_count_raises():
    with pytest.raises(MatchCountError):
        safe_replace("a a a", "a", "b", expected=1)


def test_safe_replace_zero_match_raises():
    with pytest.raises(MatchCountError):
        safe_replace("nothing", "missing", "x")


# --- prepend (newest on top) ---

def test_prepend_at_top():
    out = prepend_entry("existing", "new line")
    assert out.startswith("new line")
    assert "existing" in out


def test_prepend_under_anchor():
    doc = "# Section 3\nold entry\n"
    out = prepend_entry(doc, "2026-06-23 fresh", anchor="# Section 3")
    lines = out.splitlines()
    assert lines[0] == "# Section 3"
    assert "2026-06-23 fresh" in lines[1] or "2026-06-23 fresh" in lines[2]
    assert out.index("fresh") < out.index("old entry")


def test_prepend_missing_anchor_raises():
    with pytest.raises(MatchCountError):
        prepend_entry("doc", "x", anchor="# Nope")


# --- create params ---

def test_build_create_params_has_markdown_flags():
    p = build_create_params("Foo.md", "body", PARENT)
    assert p["disableConversionToGoogleType"] is True
    assert p["contentMimeType"] == "text/markdown"
    assert decode_b64(p["content_b64"]) == "body"
    assert p["parent_id"] == PARENT


# --- write loop + outage ---

class _OkClient:
    def __init__(self):
        self.calls = []

    def download_b64(self, file_id):
        return encode_b64("old id: KEEP\nbody")

    def create_file(self, *, title, content_b64, parent_id, **kwargs):
        self.calls.append(kwargs)
        return "NEW_FILE_ID"


class _OutageClient(_OkClient):
    def create_file(self, **kwargs):
        raise RuntimeError("write authorization failed")


def test_write_new_version_reports_old_id():
    res = write_new_version(
        _OkClient(), title="t.md", new_content="x", parent_id=PARENT, old_id="OLD"
    )
    assert res.new_id == "NEW_FILE_ID"
    assert "OLD" in res.report()
    assert "delete it manually" in res.report()


def test_edit_then_write_runs_loop():
    client = _OkClient()
    res = edit_then_write(
        client,
        file_id="OLD",
        title="t.md",
        parent_id=PARENT,
        edit=lambda text: safe_replace(text, "KEEP", "REPLACED"),
    )
    assert res.old_id == "OLD"
    # markdown flags propagated into create_file kwargs
    assert client.calls[0]["disableConversionToGoogleType"] is True


def test_edit_noop_refuses_write():
    with pytest.raises(MatchCountError):
        edit_then_write(
            _OkClient(),
            file_id="OLD",
            title="t.md",
            parent_id=PARENT,
            edit=lambda text: text,  # no change
        )


def test_outage_raises_with_pending_capture():
    with pytest.raises(WriteOutage) as exc:
        write_new_version(
            _OutageClient(),
            title="t.md",
            new_content="payload",
            parent_id=PARENT,
            old_id="OLD",
        )
    pending = exc.value.pending
    assert isinstance(pending, PendingWrite)
    assert pending.content == "payload"
    assert pending.target_id == "OLD"
