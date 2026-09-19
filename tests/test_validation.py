"""Tests for translation validation."""

from __future__ import annotations

import unittest
from pdf2zh.validation import validate_translation, validate_batch


class ValidationTests(unittest.TestCase):
    def test_empty_translation(self):
        res = validate_translation(1, "Some source text", "")
        self.assertFalse(res.is_valid)
        self.assertIn("Translation is empty", res.errors)

    def test_placeholder_integrity(self):
        # Match
        res = validate_translation(1, "Source with <b0></b0> formula", "Bản dịch có <b0></b0> công thức")
        self.assertTrue(res.is_valid)
        self.assertEqual(len(res.errors), 0)

        # Mismatch
        res_mismatch = validate_translation(1, "Source with <b0></b0> formula", "Bản dịch không có công thức")
        self.assertFalse(res_mismatch.is_valid)
        self.assertTrue(any("Placeholder mismatch" in err for err in res_mismatch.errors))

    def test_length_ratio(self):
        # Normal
        res = validate_translation(1, "This is normal English text.", "Đây là đoạn văn bản tiếng Việt bình thường.")
        self.assertEqual(len(res.warnings), 0)

        # Too short
        res_short = validate_translation(1, "This is a rather long sentence with details that should not be dropped.", "Ngắn.")
        self.assertTrue(any("unusually short" in w for w in res_short.warnings))

        # Too long
        res_long = validate_translation(1, "Hi", "Đây là một đoạn dịch rất dài, dài bất thường so với bản gốc ban đầu.")
        self.assertTrue(any("unusually long" in w for w in res_long.warnings))

    def test_number_preservation(self):
        # Number preserved
        res = validate_translation(1, "The distance is 15 mm and angle is 45.5%.", "Khoảng cách là 15 mm và góc là 45.5%.")
        num_warnings = [w for w in res.warnings if "Numbers missing" in w]
        self.assertEqual(len(num_warnings), 0)

        # Number missing
        res_missing = validate_translation(1, "The distance is 15 mm and angle is 45.5%.", "Khoảng cách và góc đo được.")
        num_warnings = [w for w in res_missing.warnings if "Numbers missing" in w]
        self.assertEqual(len(num_warnings), 1)
        self.assertIn("15", num_warnings[0])

    def test_figure_table_reference(self):
        res = validate_translation(1, "As shown in Figure 3-2 and Table 1", "Như thể hiện trong Hình 3-2 và Bảng 1")
        fig_warnings = [w for w in res.warnings if "Figure/table" in w]
        self.assertEqual(len(fig_warnings), 0)

    def test_validate_batch(self):
        batch = [
            (1, "Hello", "Xin chào"),
            (2, "Test <b0></b0>", "Test"),
        ]
        results = validate_batch(batch)
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0].is_valid)
        self.assertFalse(results[1].is_valid)


if __name__ == "__main__":
    unittest.main()
