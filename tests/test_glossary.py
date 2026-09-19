"""Tests for TerminologyGlossary."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pdf2zh.glossary import TerminologyGlossary


class GlossaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.base_file = Path(self.tmpdir) / "base.jsonl"
        self.proj_file = Path(self.tmpdir) / "proj.jsonl"

        with open(self.base_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({"en": "mandible", "vi": "xương hàm dưới", "notes": ""}) + "\n")
            f.write(json.dumps({"en": "maxilla", "vi": "xương hàm trên", "notes": ""}) + "\n")

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_load_and_lookup(self):
        glossary = TerminologyGlossary(base_path=self.base_file)
        self.assertEqual(glossary.lookup("mandible"), "xương hàm dưới")
        self.assertEqual(glossary.lookup("Mandible"), "xương hàm dưới")
        self.assertEqual(glossary.lookup("MAXILLA"), "xương hàm trên")
        self.assertIsNone(glossary.lookup("unknown_term"))

    def test_contains_and_len(self):
        glossary = TerminologyGlossary(base_path=self.base_file)
        self.assertEqual(len(glossary), 2)
        self.assertIn("mandible", glossary)
        self.assertIn("MANDIBLE", glossary)
        self.assertNotIn("tooth", glossary)

    def test_add_and_persist(self):
        glossary = TerminologyGlossary(base_path=self.base_file, project_path=self.proj_file)
        glossary.add("tooth", "răng", "dental")
        self.assertEqual(glossary.lookup("tooth"), "răng")

        # Verify persisted file
        self.assertTrue(self.proj_file.exists())
        reloaded = TerminologyGlossary(project_path=self.proj_file)
        self.assertEqual(reloaded.lookup("tooth"), "răng")
        self.assertEqual(reloaded.lookup("mandible"), "xương hàm dưới")

    def test_to_prompt_context(self):
        glossary = TerminologyGlossary(base_path=self.base_file)
        ctx = glossary.to_prompt_context(max_terms=10)
        self.assertIn("Terminology glossary", ctx)
        self.assertIn("mandible = xương hàm dưới", ctx)
        self.assertIn("maxilla = xương hàm trên", ctx)

    def test_empty_glossary(self):
        glossary = TerminologyGlossary()
        self.assertEqual(len(glossary), 0)
        self.assertEqual(glossary.to_prompt_context(), "")


if __name__ == "__main__":
    unittest.main()
