"""Glossary / normalizer — expands Kent's shorthand on input.

Longest terms first so ``HOMA-IR`` wins over ``IR``, and word boundaries are
respected so we don't expand the ``ir`` inside ``stairs``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class Glossary:
    terms: dict[str, str]

    def _ordered(self) -> list[str]:
        # Longest first to avoid a short term shadowing a longer one.
        return sorted(self.terms, key=len, reverse=True)

    def find(self, text: str) -> list[tuple[str, str]]:
        """Return (term, expansion) pairs present in ``text``, in input order,
        without double-counting a span already claimed by a longer term."""
        claimed: list[tuple[int, int]] = []
        hits: list[tuple[int, str, str]] = []
        for term in self._ordered():
            pattern = r"(?<![\w-])" + re.escape(term) + r"(?![\w-])"
            for m in re.finditer(pattern, text, flags=re.IGNORECASE):
                span = (m.start(), m.end())
                if any(s < span[1] and span[0] < e for s, e in claimed):
                    continue
                claimed.append(span)
                hits.append((span[0], term, self.terms[term]))
        hits.sort(key=lambda h: h[0])
        # de-dup repeated terms, keep first occurrence
        seen: set[str] = set()
        out: list[tuple[str, str]] = []
        for _, term, exp in hits:
            if term in seen:
                continue
            seen.add(term)
            out.append((term, exp))
        return out

    def annotate(self, text: str) -> str:
        """Append a one-line expansion of every shorthand found, for grounding."""
        hits = self.find(text)
        if not hits:
            return text
        notes = "; ".join(f"{term} = {exp}" for term, exp in hits)
        return f"{text}\n\n[shorthand: {notes}]"


def load_glossary(path: Optional[os.PathLike | str] = None) -> Glossary:
    path = Path(path) if path else DATA_DIR / "glossary.yaml"
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Glossary(terms=dict(raw.get("terms") or {}))
