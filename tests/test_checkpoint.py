"""Tests for the checkpoint system."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pdf2zh.checkpoint import TranslationCheckpoint


class CheckpointTests(unittest.TestCase):
    """Test checkpoint create, resume, and idempotency."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = Path(self.tmpdir) / "test_checkpoint.db"

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_create_and_load_segments(self):
        cp = TranslationCheckpoint(self.db_path)
        segments = ["Hello world", "Good morning", "Test segment"]
        cp.load_segments(segments)
        stats = cp.get_stats()
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats.get("pending", 0), 3)
        cp.close()

    def test_mark_completed(self):
        cp = TranslationCheckpoint(self.db_path)
        cp.load_segments(["Hello", "World"])
        cp.mark_completed(0, "Xin chào", model="test")
        stats = cp.get_stats()
        self.assertEqual(stats.get("completed", 0), 1)
        self.assertEqual(stats.get("pending", 0), 1)
        cp.close()

    def test_mark_failed_and_retry(self):
        cp = TranslationCheckpoint(self.db_path)
        cp.load_segments(["Segment one", "Segment two"])
        cp.mark_failed(0, "API error")
        stats = cp.get_stats()
        self.assertEqual(stats.get("failed", 0), 1)
        # Failed segments should appear in pending with max_retries
        pending = cp.get_pending(max_retries=3)
        self.assertEqual(len(pending), 2)  # 1 pending + 1 failed (retriable)
        self.assertEqual(pending[0].retry_count, 1)
        cp.close()

    def test_resume_skips_completed(self):
        """The critical resume scenario: chunk 1 ✓, chunk 2 ✓, chunk 3 ✗."""
        cp = TranslationCheckpoint(self.db_path)
        cp.load_segments(["Seg A", "Seg B", "Seg C"])
        cp.mark_completed(0, "Dịch A", model="test")
        cp.mark_completed(1, "Dịch B", model="test")
        cp.mark_failed(2, "Error")
        cp.close()

        # Resume
        cp2 = TranslationCheckpoint(self.db_path)
        pending = cp2.get_pending(max_retries=3)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].segment_id, 2)
        self.assertEqual(pending[0].source_text, "Seg C")
        cp2.close()

    def test_source_change_resets_segment(self):
        cp = TranslationCheckpoint(self.db_path)
        cp.load_segments(["Original text"])
        cp.mark_completed(0, "Bản dịch", model="test")
        cp.close()

        cp2 = TranslationCheckpoint(self.db_path)
        cp2.load_segments(["Modified text"])  # Source changed
        pending = cp2.get_pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].source_text, "Modified text")
        cp2.close()

    def test_export_translations(self):
        cp = TranslationCheckpoint(self.db_path)
        cp.load_segments(["Hello", "World"])
        cp.mark_completed(0, "Xin chào")
        cp.mark_completed(1, "Thế giới")
        output = Path(self.tmpdir) / "translations.jsonl"
        count = cp.export_translations(output)
        self.assertEqual(count, 2)
        # Verify file content
        import json
        with open(output, encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["src"], "Hello")
        self.assertEqual(lines[0]["dst"], "Xin chào")
        cp.close()

    def test_is_complete(self):
        cp = TranslationCheckpoint(self.db_path)
        cp.load_segments(["A", "B"])
        self.assertFalse(cp.is_complete())
        cp.mark_completed(0, "X")
        self.assertFalse(cp.is_complete())
        cp.mark_completed(1, "Y")
        self.assertTrue(cp.is_complete())
        cp.close()

    def test_metadata(self):
        cp = TranslationCheckpoint(self.db_path)
        cp.set_metadata("source_file", "test.pdf")
        cp.set_metadata("model", "gpt-4")
        self.assertEqual(cp.get_metadata("source_file"), "test.pdf")
        self.assertEqual(cp.get_metadata("model"), "gpt-4")
        self.assertIsNone(cp.get_metadata("nonexistent"))
        cp.close()

    def test_max_retries_excludes_exhausted(self):
        cp = TranslationCheckpoint(self.db_path)
        cp.load_segments(["Fail me"])
        for _ in range(3):
            cp.mark_failed(0, "Error")
        pending = cp.get_pending(max_retries=3)
        self.assertEqual(len(pending), 0)  # Exhausted retries
        cp.close()

    def test_idempotent_load(self):
        """Loading the same segments twice should not change state."""
        cp = TranslationCheckpoint(self.db_path)
        cp.load_segments(["A", "B"])
        cp.mark_completed(0, "X")
        cp.load_segments(["A", "B"])  # Re-load
        stats = cp.get_stats()
        self.assertEqual(stats.get("completed", 0), 1)
        cp.close()


if __name__ == "__main__":
    unittest.main()
