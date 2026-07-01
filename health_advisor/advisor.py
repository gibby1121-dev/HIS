"""Advisor — composes the read / answer / write layers into one entry point.

This is the orchestration the agent drives. It does not itself generate prose:
the answering model (Jane, health-scoped) reads the assembled ``AnswerContext``
— loaded sources, expanded shorthand, triggered guardrails — and answers from
it. The contract this enforces in code:

  * grounded-first: load MASTER + References (then the topic detail) BEFORE
    answering; refuse to answer with zero loaded sources.
  * guardrails attach automatically when triggered.
  * writes go through the Drive loop (newest-on-top, surface the old id).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from .config import VaultConfig, VaultFile, load_config
from .drive_io import DriveClient, decode_b64, edit_then_write, prepend_entry
from .glossary import Glossary, load_glossary
from .guardrails import GuardrailFlag, guardrail_flags, BASE_DISCLAIMER
from .open_loops import OpenLoops, load_open_loops


@dataclass
class LoadedSource:
    file: VaultFile
    text: str


@dataclass
class AnswerContext:
    query: str
    normalized_query: str
    sources: list[LoadedSource]
    flags: list[GuardrailFlag]
    disclaimer: str = BASE_DISCLAIMER

    @property
    def grounded(self) -> bool:
        return bool(self.sources)

    def source_titles(self) -> list[str]:
        return [s.file.title for s in self.sources]


class ReadLayer:
    """Loads canonical files via the connector, cached per session."""

    def __init__(self, config: VaultConfig, client: DriveClient):
        self.config = config
        self.client = client
        self._cache: dict[str, str] = {}

    def load(self, file: VaultFile) -> LoadedSource:
        if not file.resolvable:
            raise ValueError(
                f"{file.title} has no id — resolve by scoped search first: "
                f"{self.config.scoped_search_query(file.title)}"
            )
        if file.id not in self._cache:
            self._cache[file.id] = decode_b64(self.client.download_b64(file.id))
        return LoadedSource(file=file, text=self._cache[file.id])

    def load_for(self, topic: Optional[str]) -> list[LoadedSource]:
        return [self.load(f) for f in self.config.load_order(topic)]


class Advisor:
    def __init__(
        self,
        client: DriveClient,
        *,
        config: Optional[VaultConfig] = None,
        glossary: Optional[Glossary] = None,
        open_loops: Optional[OpenLoops] = None,
    ):
        self.config = config or load_config()
        self.glossary = glossary or load_glossary()
        self.open_loops = open_loops or load_open_loops()
        self.reader = ReadLayer(self.config, client)

    def prepare(self, query: str, *, topic: Optional[str] = None) -> AnswerContext:
        """Read-then-answer scaffolding. Loads sources, expands shorthand, and
        collects guardrail flags. The model answers from the returned context;
        if ``grounded`` is False it must say so rather than invent."""
        normalized = self.glossary.annotate(query)
        sources = self.reader.load_for(topic)
        flags = guardrail_flags(normalized)
        return AnswerContext(
            query=query,
            normalized_query=normalized,
            sources=sources,
            flags=flags,
        )

    def file_reference(self, creator_block: str):
        """Append a standing source to Health_References.md, newest-on-top under
        its creator block (or at the top of the file)."""
        ref = self.config.references
        return edit_then_write(
            self.reader.client,
            file_id=ref.id,
            title=ref.title,
            parent_id=self.config.vault_folder_id,
            edit=lambda text: prepend_entry(text, creator_block),
        )

    def file_master_entry(self, entry: str, *, section_anchor: str):
        """Append a dated, newest-on-top entry under a MASTER section heading.
        Section 1's pointer line must be kept in sync separately."""
        master = self.config.master
        return edit_then_write(
            self.reader.client,
            file_id=master.id,
            title=master.title,
            parent_id=self.config.vault_folder_id,
            edit=lambda text: prepend_entry(text, entry, anchor=section_anchor),
        )
