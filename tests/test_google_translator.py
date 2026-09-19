from __future__ import annotations

from unittest.mock import MagicMock, patch
import unittest

from pdf2zh.cache import clean_test_db, init_test_db
from pdf2zh.translator import GoogleTranslator, normalize_placeholders


class GoogleTranslatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.test_db = init_test_db()

    def tearDown(self) -> None:
        clean_test_db(self.test_db)

    def test_normalize_placeholders(self) -> None:
        self.assertEqual(normalize_placeholders("< b0 >test< / b0 >"), "<b0>test</b0>")
        self.assertEqual(normalize_placeholders("<b 1 >"), "<b1>")
        self.assertEqual(normalize_placeholders("</ b2 >"), "</b2>")
        self.assertEqual(normalize_placeholders("normal text"), "normal text")

    def test_empty_or_whitespace_returns_original(self) -> None:
        gt = GoogleTranslator(lang_in="en", lang_out="vi")
        self.assertEqual(gt.translate(""), "")
        self.assertEqual(gt.translate("   "), "   ")

    def test_primary_endpoint_success(self) -> None:
        gt = GoogleTranslator(lang_in="en", lang_out="vi", ignore_cache=True)
        with patch.object(gt, "_translate_clients5", return_value="Xin chào") as mock_clients5:
            result = gt.translate("Hello")
            self.assertEqual(result, "Xin chào")
            mock_clients5.assert_called_once()

    def test_fallback_to_secondary_when_primary_fails(self) -> None:
        gt = GoogleTranslator(lang_in="en", lang_out="vi", ignore_cache=True)
        with patch.object(gt, "_translate_clients5", side_effect=Exception("429 Too Many Requests")), \
             patch.object(gt, "_translate_googleapis", return_value="Xin chào từ secondary") as mock_second:
            result = gt.translate("Hello")
            self.assertEqual(result, "Xin chào từ secondary")
            mock_second.assert_called_once()

    def test_fallback_to_tertiary_when_both_fail(self) -> None:
        gt = GoogleTranslator(lang_in="en", lang_out="vi", ignore_cache=True)
        with patch.object(gt, "_translate_clients5", side_effect=Exception("Failed 1")), \
             patch.object(gt, "_translate_googleapis", side_effect=Exception("Failed 2")), \
             patch.object(gt, "_translate_mobile_web", return_value="Xin chào từ mobile web") as mock_third:
            result = gt.translate("Hello")
            self.assertEqual(result, "Xin chào từ mobile web")
            mock_third.assert_called_once()

    def test_raises_when_all_endpoints_fail(self) -> None:
        gt = GoogleTranslator(lang_in="en", lang_out="vi", ignore_cache=True)
        with patch.object(gt, "_translate_clients5", side_effect=Exception("Failed 1")), \
             patch.object(gt, "_translate_googleapis", side_effect=Exception("Failed 2")), \
             patch.object(gt, "_translate_mobile_web", side_effect=Exception("Failed 3")):
            with self.assertRaises(RuntimeError) as ctx:
                gt.translate("Hello")
            self.assertIn("All Google Translate endpoints failed", str(ctx.exception))
