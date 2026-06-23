"""Open-loops tracker — surfaces the consolidated loops and closes them.

Backed by ``data/open_loops.yaml``. Closing a loop is append-only in spirit:
status flips to ``closed`` and a dated note is attached; the loop is not deleted.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass
class Loop:
    id: str
    summary: str
    status: str = "open"
    owner: Optional[str] = None
    medical: bool = False
    blocked_by: Optional[str] = None
    closed_on: Optional[str] = None
    note: Optional[str] = None

    @property
    def is_open(self) -> bool:
        return self.status == "open"


@dataclass
class OpenLoops:
    loops: list[Loop] = field(default_factory=list)
    path: Optional[Path] = None

    def open(self) -> list[Loop]:
        return [l for l in self.loops if l.is_open]

    def get(self, loop_id: str) -> Loop:
        for l in self.loops:
            if l.id == loop_id:
                return l
        raise KeyError(f"unknown loop: {loop_id!r}")

    def close(self, loop_id: str, *, on: str, note: str) -> Loop:
        loop = self.get(loop_id)
        loop.status = "closed"
        loop.closed_on = on
        loop.note = note
        return loop

    def summary(self) -> str:
        lines = []
        for l in self.open():
            tag = " (medical → physician)" if l.medical else ""
            blocked = f" [blocked: {l.blocked_by}]" if l.blocked_by else ""
            lines.append(f"- [ ] {l.summary}{tag}{blocked}")
        return "\n".join(lines) if lines else "No open loops."

    def save(self, path: Optional[os.PathLike | str] = None) -> None:
        target = Path(path) if path else self.path
        if target is None:
            raise ValueError("no path to save to")
        payload = {"loops": []}
        for l in self.loops:
            d = {"id": l.id, "status": l.status, "summary": l.summary}
            if l.owner:
                d["owner"] = l.owner
            if l.medical:
                d["medical"] = True
            if l.blocked_by:
                d["blocked_by"] = l.blocked_by
            if l.closed_on:
                d["closed_on"] = l.closed_on
            if l.note:
                d["note"] = l.note
            payload["loops"].append(d)
        Path(target).write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )


def load_open_loops(path: Optional[os.PathLike | str] = None) -> OpenLoops:
    p = Path(path) if path else DATA_DIR / "open_loops.yaml"
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    loops = []
    for d in raw.get("loops") or []:
        loops.append(
            Loop(
                id=d["id"],
                summary=d["summary"],
                status=d.get("status", "open"),
                owner=d.get("owner"),
                medical=bool(d.get("medical", False)),
                blocked_by=d.get("blocked_by"),
                closed_on=d.get("closed_on"),
                note=d.get("note"),
            )
        )
    return OpenLoops(loops=loops, path=p)
