from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pdf2zh.cache import clean_test_db, init_test_db
from pdf2zh.translator import HandoffTranslator, load_segment_table, placeholders


def _jsonl(path: Path, records: list[dict]) -> Path:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    return path


class SegmentTableTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def test_a_missing_path_yields_an_empty_table(self):
        self.assertEqual(load_segment_table(None), {})

    def test_loads_records_and_skips_blank_translations(self):
        path = _jsonl(
            self.root / "table.jsonl",
            [{"src": "Hello", "dst": "Xin chào"}, {"src": "Unfilled", "dst": ""}],
        )
        self.assertEqual(load_segment_table(str(path)), {"Hello": "Xin chào"})

    def test_skips_entries_that_lost_or_reordered_a_formula_placeholder(self):
        path = _jsonl(
            self.root / "table.jsonl",
            [
                {"src": "where <b0></b0> holds", "dst": "trong đó đúng"},
                {"src": "and <b1></b1> too", "dst": "và <b1></b1> nữa"},
            ],
        )
        table = load_segment_table(str(path))
        self.assertNotIn("where <b0></b0> holds", table)
        self.assertIn("and <b1></b1> too", table)

    def test_rejects_a_malformed_record_and_names_the_line(self):
        path = self.root / "table.jsonl"
        path.write_text('{"src": "a", "dst": "b"}\n{"src": "no dst here"}\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "line 2"):
            load_segment_table(str(path))

    def test_placeholders_are_returned_in_order(self):
        self.assertEqual(
            placeholders("a <b0></b0> b <b1></b1>"),
            ["<b0>", "</b0>", "<b1>", "</b1>"],
        )


class HandoffTranslatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.test_db = init_test_db()
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        self.misses = self.root / "missing.jsonl"

    def tearDown(self) -> None:
        self.temp_directory.cleanup()
        clean_test_db(self.test_db)

    def _translator(self, table: list[dict] | None = None) -> HandoffTranslator:
        envs = {"segments_out": str(self.misses)}
        if table is not None:
            envs["segments_in"] = str(_jsonl(self.root / "table.jsonl", table))
        return HandoffTranslator("auto", "vi", envs=envs)

    def _recorded_misses(self) -> list[str]:
        lines = self.misses.read_text(encoding="utf-8").splitlines()
        return [json.loads(line)["src"] for line in lines if line.strip()]

    def test_returns_the_supplied_translation(self):
        translator = self._translator([{"src": "Hello", "dst": "Xin chào"}])
        self.assertEqual(translator.translate("Hello"), "Xin chào")
        self.assertEqual(self._recorded_misses(), [])

    def test_records_each_miss_once_and_passes_the_text_through(self):
        translator = self._translator()
        self.assertEqual(translator.translate("Hello"), "Hello")
        self.assertEqual(translator.translate("Hello"), "Hello")
        self.assertEqual(translator.translate("Goodbye"), "Goodbye")
        self.assertEqual(self._recorded_misses(), ["Hello", "Goodbye"])

    def test_never_caches_an_untranslated_passthrough(self):
        translator = self._translator()
        translator.translate("Hello")
        self.assertTrue(translator.ignore_cache)
        self.assertIsNone(translator.cache.get("Hello"))

    def test_truncates_a_stale_miss_file_on_construction(self):
        self.misses.write_text('{"src": "from an older run"}\n', encoding="utf-8")
        self._translator()
        self.assertEqual(self._recorded_misses(), [])


if __name__ == "__main__":
    unittest.main()
