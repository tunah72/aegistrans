"""Checkpoint system for resumable book translation."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SegmentRecord:
    """State of one translation segment."""
    segment_id: int
    source_text: str
    source_hash: str
    status: str = "pending"  # pending, completed, failed
    translation: str = ""
    model: str = ""
    timestamp: float = 0.0
    retry_count: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    error: str = ""


class TranslationCheckpoint:
    """SQLite-backed checkpoint for tracking translation progress.

    Each segment gets a unique ID and a hash of its source text.
    On resume, only segments that are 'pending' or 'failed' are retried.
    If the source text changed (different hash), the segment is re-translated.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS segments (
                segment_id INTEGER PRIMARY KEY,
                source_text TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                translation TEXT DEFAULT '',
                model TEXT DEFAULT '',
                timestamp REAL DEFAULT 0,
                retry_count INTEGER DEFAULT 0,
                tokens_in INTEGER DEFAULT 0,
                tokens_out INTEGER DEFAULT 0,
                error TEXT DEFAULT ''
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        self._conn.commit()

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def set_metadata(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            (key, value),
        )
        self._conn.commit()

    def get_metadata(self, key: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT value FROM metadata WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def load_segments(self, segments: list[str]) -> None:
        """Initialize checkpoint with source segments.

        New segments are added as 'pending'. Existing segments with the
        same hash keep their status. Segments with changed source text
        are reset to 'pending'.
        """
        for idx, text in enumerate(segments):
            h = self._hash(text)
            existing = self._conn.execute(
                "SELECT source_hash, status FROM segments WHERE segment_id = ?",
                (idx,),
            ).fetchone()
            if existing is None:
                self._conn.execute(
                    "INSERT INTO segments (segment_id, source_text, source_hash) VALUES (?, ?, ?)",
                    (idx, text, h),
                )
            elif existing[0] != h:
                # Source changed, re-translate
                self._conn.execute(
                    "UPDATE segments SET source_text=?, source_hash=?, status='pending', "
                    "translation='', error='' WHERE segment_id=?",
                    (text, h, idx),
                )
        self._conn.commit()

    def get_pending(self, max_retries: int = 3) -> list[SegmentRecord]:
        """Return segments that need translation (pending or retriable failures)."""
        rows = self._conn.execute(
            "SELECT segment_id, source_text, source_hash, status, translation, "
            "model, timestamp, retry_count, tokens_in, tokens_out, error "
            "FROM segments WHERE status='pending' OR (status='failed' AND retry_count < ?) "
            "ORDER BY segment_id",
            (max_retries,),
        ).fetchall()
        return [SegmentRecord(*row) for row in rows]

    def mark_completed(
        self,
        segment_id: int,
        translation: str,
        model: str = "",
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        self._conn.execute(
            "UPDATE segments SET status='completed', translation=?, model=?, "
            "timestamp=?, tokens_in=?, tokens_out=? WHERE segment_id=?",
            (translation, model, time.time(), tokens_in, tokens_out, segment_id),
        )
        self._conn.commit()

    def mark_failed(self, segment_id: int, error: str) -> None:
        self._conn.execute(
            "UPDATE segments SET status='failed', error=?, retry_count=retry_count+1, "
            "timestamp=? WHERE segment_id=?",
            (error, time.time(), segment_id),
        )
        self._conn.commit()

    def get_stats(self) -> dict:
        """Return translation progress statistics."""
        rows = self._conn.execute(
            "SELECT status, COUNT(*) FROM segments GROUP BY status"
        ).fetchall()
        stats = {row[0]: row[1] for row in rows}
        stats["total"] = sum(stats.values())
        return stats

    def export_translations(self, output_path: str | Path) -> int:
        """Export completed translations to JSONL for handoff rebuild.

        Returns the number of exported translations.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        rows = self._conn.execute(
            "SELECT source_text, translation FROM segments WHERE status='completed' "
            "ORDER BY segment_id"
        ).fetchall()
        with open(output_path, "w", encoding="utf-8") as f:
            for src, dst in rows:
                f.write(json.dumps({"src": src, "dst": dst}, ensure_ascii=False) + "\n")
        return len(rows)

    def is_complete(self) -> bool:
        """Check if all segments have been translated."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM segments WHERE status != 'completed'"
        ).fetchone()
        return row[0] == 0

    def close(self) -> None:
        self._conn.close()
