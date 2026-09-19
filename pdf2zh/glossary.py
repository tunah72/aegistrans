"""Persistent terminology glossary for consistent translation across a book."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class TerminologyGlossary:
    """Manages a persistent glossary of English→Vietnamese medical terms.

    Loads a base glossary (shipped with the skill) and maintains a
    per-project glossary that grows as new terms are encountered.
    """

    def __init__(
        self,
        base_path: str | Path | None = None,
        project_path: str | Path | None = None,
    ) -> None:
        self._terms: dict[str, dict] = {}  # en_lower -> {en, vi, notes}
        if base_path:
            self._load_jsonl(base_path)
        if project_path:
            self._load_jsonl(project_path)
        self._project_path = Path(project_path) if project_path else None

    def _load_jsonl(self, path: str | Path) -> None:
        """Load terms from a JSONL glossary file."""
        path = Path(path)
        if not path.is_file():
            return
        try:
            with open(path, encoding="utf-8") as f:
                for lineno, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        en = record.get("en", "").strip()
                        vi = record.get("vi", "").strip()
                        notes = record.get("notes", "").strip()
                        if en and vi:
                            self._terms[en.lower()] = {
                                "en": en,
                                "vi": vi,
                                "notes": notes,
                            }
                    except (json.JSONDecodeError, AttributeError) as e:
                        logger.warning("Glossary %s line %d: %s", path, lineno, e)
        except OSError as e:
            logger.warning("Failed to load glossary %s: %s", path, e)

    def lookup(self, term: str) -> Optional[str]:
        """Look up the Vietnamese translation for an English term."""
        entry = self._terms.get(term.lower())
        return entry["vi"] if entry else None

    def add(self, en: str, vi: str, notes: str = "") -> None:
        """Add or update a term in the glossary."""
        self._terms[en.lower()] = {"en": en, "vi": vi, "notes": notes}
        self._persist()

    def get_all(self) -> list[dict]:
        """Return all glossary entries sorted by English term."""
        return sorted(self._terms.values(), key=lambda t: t["en"].lower())

    def to_prompt_context(self, max_terms: int = 100) -> str:
        """Generate a terminology context string for LLM prompts."""
        entries = self.get_all()[:max_terms]
        if not entries:
            return ""
        lines = ["Terminology glossary (use these translations consistently):"]
        for entry in entries:
            line = f"  {entry['en']} = {entry['vi']}"
            if entry.get("notes"):
                line += f" ({entry['notes']})"
            lines.append(line)
        return "\n".join(lines)

    def _persist(self) -> None:
        """Save the glossary to the project file."""
        if not self._project_path:
            return
        try:
            self._project_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._project_path, "w", encoding="utf-8") as f:
                for entry in self.get_all():
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("Failed to persist glossary to %s: %s", self._project_path, e)

    def __len__(self) -> int:
        return len(self._terms)

    def __contains__(self, term: str) -> bool:
        return term.lower() in self._terms
