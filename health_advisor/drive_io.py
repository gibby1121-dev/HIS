"""Drive I/O layer — implements the quirky connector contract.

Hard facts about the connector this encodes:

* No in-place overwrite. Every write CREATES A NEW FILE with a new id. Pattern:
  download -> base64-decode -> edit -> re-encode -> create_file -> report new id
  -> surface the old id for manual deletion.
* On create_file always set ``disableConversionToGoogleType=True`` and
  ``contentMimeType='text/markdown'`` so a .md stays markdown, not a Google Doc.
* Base64 from the connector can carry stray non-ASCII (transcription noise);
  filter to ``[A-Za-z0-9+/=]`` before decoding.
* Edits assert the match count before replacing (no silent no-ops / over-writes).
* Known write outage (2026-06-22): create_file rejected ALL payloads (even a
  5-byte probe). That is a write-authorization failure, not a content problem —
  do not retry encodings; capture the change as pending and tell Kent to recheck
  the connector's write scope.

The actual connector is reached through a ``DriveClient`` the caller supplies
(in an agent session that is the Google Drive MCP). Everything that does NOT
need the network — sanitising base64, safe edits, building create params,
running the write loop, classifying an outage — lives here and is unit-tested.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Optional, Protocol

from .config import CREATE_FILE_DEFAULTS

_B64_VALID = re.compile(rb"[^A-Za-z0-9+/=]")


class WriteOutage(RuntimeError):
    """Raised when create_file rejects every payload — a write-auth failure.

    The change is preserved on ``.pending`` so the caller can stash it.
    """

    def __init__(self, message: str, pending: "PendingWrite"):
        super().__init__(message)
        self.pending = pending


class MatchCountError(ValueError):
    """A string replacement did not match the asserted number of times."""


@dataclass(frozen=True)
class PendingWrite:
    """A write that could not be committed (e.g. during the write outage)."""

    target_id: Optional[str]
    title: str
    content: str
    reason: str


@dataclass(frozen=True)
class WriteResult:
    new_id: str
    old_id: Optional[str]
    title: str

    def report(self) -> str:
        line = f"Wrote new file '{self.title}' -> {self.new_id}."
        if self.old_id:
            line += f" Old id {self.old_id} is now stale — delete it manually."
        return line


class DriveClient(Protocol):
    """The slice of the Drive connector the write loop needs.

    In an agent session, wire these to the Google Drive MCP tools:
      download_b64 -> download_file_content / read_file_content
      create_file  -> create_file (pass **CREATE_FILE_DEFAULTS)
      search       -> search_files (scoped by parentId + title contains)
    """

    def download_b64(self, file_id: str) -> str: ...

    def create_file(
        self,
        *,
        title: str,
        content_b64: str,
        parent_id: str,
        **kwargs,
    ) -> str: ...


# --- base64 -----------------------------------------------------------------

def sanitize_b64(data: str | bytes) -> bytes:
    """Strip anything outside the base64 alphabet, then fix padding."""
    if isinstance(data, str):
        data = data.encode("ascii", "ignore")
    cleaned = _B64_VALID.sub(b"", data)
    cleaned = cleaned.rstrip(b"=")
    pad = (-len(cleaned)) % 4
    return cleaned + b"=" * pad


def decode_b64(data: str | bytes, encoding: str = "utf-8") -> str:
    """Decode connector base64 to text, tolerating transcription noise."""
    return base64.b64decode(sanitize_b64(data)).decode(encoding)


def encode_b64(text: str, encoding: str = "utf-8") -> str:
    return base64.b64encode(text.encode(encoding)).decode("ascii")


# --- safe editing -----------------------------------------------------------

def safe_replace(text: str, old: str, new: str, *, expected: int = 1) -> str:
    """Replace ``old`` with ``new`` only if it occurs exactly ``expected`` times."""
    count = text.count(old)
    if count != expected:
        raise MatchCountError(
            f"expected {expected} match(es) of {old!r}, found {count}"
        )
    return text.replace(old, new)


def prepend_entry(text: str, entry: str, *, anchor: Optional[str] = None) -> str:
    """Newest-on-top insert. With ``anchor`` (e.g. a section heading) the entry
    goes directly under that heading; otherwise it goes at the top of the doc."""
    entry = entry.rstrip("\n") + "\n"
    if anchor is None:
        return entry + "\n" + text
    idx = text.find(anchor)
    if idx == -1:
        raise MatchCountError(f"anchor not found: {anchor!r}")
    end = text.find("\n", idx)
    if end == -1:
        end = len(text)
    head, tail = text[: end + 1], text[end + 1 :]
    return f"{head}\n{entry}{tail}"


# --- create-params + write loop --------------------------------------------

def build_create_params(title: str, content: str, parent_id: str) -> dict:
    """Params for create_file with the markdown-preserving flags applied."""
    return {
        "title": title,
        "content_b64": encode_b64(content),
        "parent_id": parent_id,
        **CREATE_FILE_DEFAULTS,
    }


def write_new_version(
    client: DriveClient,
    *,
    title: str,
    new_content: str,
    parent_id: str,
    old_id: Optional[str] = None,
) -> WriteResult:
    """Run the create-new-file loop. On total write failure raise WriteOutage
    carrying the change as a PendingWrite (do NOT retry encodings)."""
    params = build_create_params(title, new_content, parent_id)
    try:
        new_id = client.create_file(**params)
    except Exception as exc:  # connector rejected the write
        pending = PendingWrite(
            target_id=old_id,
            title=title,
            content=new_content,
            reason=f"create_file rejected: {exc}",
        )
        raise WriteOutage(
            "create_file rejected the payload — likely a connector write-auth "
            "outage, not a content problem. Captured as pending; recheck the "
            "connector's write scope before retrying.",
            pending,
        ) from exc
    return WriteResult(new_id=new_id, old_id=old_id, title=title)


def edit_then_write(
    client: DriveClient,
    *,
    file_id: str,
    title: str,
    parent_id: str,
    edit,
) -> WriteResult:
    """download -> decode -> ``edit(text)->text`` -> encode -> create -> report.

    ``edit`` is a callable taking the current text and returning the new text
    (use safe_replace / prepend_entry inside it so the match-count assert fires).
    """
    current = decode_b64(client.download_b64(file_id))
    updated = edit(current)
    if updated == current:
        raise MatchCountError("edit produced no change — refusing to write a copy")
    return write_new_version(
        client,
        title=title,
        new_content=updated,
        parent_id=parent_id,
        old_id=file_id,
    )
