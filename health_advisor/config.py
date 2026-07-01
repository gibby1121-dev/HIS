"""Config layer — the Vault file-ID table and Drive conventions as constants.

IDs live in ``data/vault_files.yaml`` (single source of truth, edited by hand or
by the write layer when a new file id is minted). This module loads and validates
them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# create_file flags that keep a .md as markdown instead of a Google Doc.
CREATE_FILE_DEFAULTS = {
    "disableConversionToGoogleType": True,
    "contentMimeType": "text/markdown",
}


@dataclass(frozen=True)
class VaultFile:
    key: str
    title: str
    id: Optional[str]
    purpose: str = ""
    load_priority: Optional[int] = None
    locked: bool = False
    stale_id_in_master: Optional[str] = None

    @property
    def resolvable(self) -> bool:
        """True if we have an id; otherwise it must be found by scoped search."""
        return self.id is not None


@dataclass(frozen=True)
class VaultConfig:
    vault_folder_id: str
    owner: str
    files: dict[str, VaultFile]
    topic_routing: dict[str, str] = field(default_factory=dict)

    def get(self, key: str) -> VaultFile:
        if key not in self.files:
            raise KeyError(f"unknown vault file key: {key!r}")
        return self.files[key]

    def scoped_search_query(self, title_fragment: str) -> str:
        """Drive query: confine search to the Vault folder by parent + title."""
        return (
            f"parentId = '{self.vault_folder_id}' "
            f"and title contains '{title_fragment}'"
        )

    def load_order(self, topic: Optional[str] = None) -> list[VaultFile]:
        """Files to load for a query: priority files first (MASTER, References),
        then the topic-specific detail file if the topic routes to one."""
        ordered = sorted(
            (f for f in self.files.values() if f.load_priority is not None),
            key=lambda f: f.load_priority,
        )
        if topic:
            key = self.route_topic(topic)
            if key:
                detail = self.files[key]
                if detail not in ordered:
                    ordered.append(detail)
        return ordered

    def route_topic(self, topic: str) -> Optional[str]:
        """Map a free-text topic word to a detail-file key, if any."""
        t = topic.strip().lower()
        if t in self.topic_routing:
            return self.topic_routing[t]
        for word, key in self.topic_routing.items():
            if word in t:
                return key
        return None

    @property
    def master(self) -> VaultFile:
        return self.files["master"]

    @property
    def references(self) -> VaultFile:
        return self.files["references"]


def load_config(path: Optional[os.PathLike | str] = None) -> VaultConfig:
    path = Path(path) if path else DATA_DIR / "vault_files.yaml"
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))

    files: dict[str, VaultFile] = {}
    for key, spec in (raw.get("files") or {}).items():
        files[key] = VaultFile(
            key=key,
            title=spec["title"],
            id=spec.get("id"),
            purpose=spec.get("purpose", ""),
            load_priority=spec.get("load_priority"),
            locked=bool(spec.get("locked", False)),
            stale_id_in_master=spec.get("stale_id_in_master"),
        )

    return VaultConfig(
        vault_folder_id=raw["vault_folder_id"],
        owner=raw["owner"],
        files=files,
        topic_routing=raw.get("topic_routing") or {},
    )
