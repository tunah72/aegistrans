from __future__ import annotations

import unittest

from pdfminer.pdfinterp import PDFResourceManager

from pdf2zh.converter import TranslateConverter
from pdf2zh.rules import (
    BULLET_CHARACTERS,
    classify_preserved_page,
    is_formula_font,
    is_scanned_page,
    line_height_for_language,
)


class PreservationRuleTests(unittest.TestCase):
    def test_formula_rule_covers_math_and_monospace_code_fonts(self):
        for font in (
            "CMMI10",
            "TeX-math-symbols",
            "STIXMath",
            "Consolas",
            "CourierNewPSMT",
            "SourceCodePro-Regular",
        ):
            with self.subTest(font=font):
                self.assertTrue(is_formula_font(font))
        self.assertFalse(is_formula_font("TimesNewRomanPSMT"))

    def test_vietnamese_line_height_and_extended_bullets_are_preserved(self):
        self.assertEqual(line_height_for_language("vi"), 1.2)
        self.assertTrue({"•", "■", "▸", "◆", "⬤"}.issubset(BULLET_CHARACTERS))

    def test_full_page_image_is_classified_as_scanned(self):
        self.assertTrue(
            is_scanned_page([{"type": 1, "bbox": (0, 0, 80, 80)}], 10_000)
        )
        self.assertFalse(
            is_scanned_page([{"type": 1, "bbox": (0, 0, 20, 20)}], 10_000)
        )

    def test_table_of_contents_page_keeps_number_alignment(self):
        text = "Table of Contents\n" + "\n".join(
            f"Chapter {index} .......... {index * 3}" for index in range(1, 6)
        )
        decision = classify_preserved_page(text)
        self.assertIsNotNone(decision)
        self.assertEqual(decision.kind, "TOC")

    def test_index_page_keeps_term_and_page_number_columns(self):
        text = "Index\nAlpha, 11\nBeta, 12\nGamma, 13"
        decision = classify_preserved_page(text)
        self.assertIsNotNone(decision)
        self.assertEqual(decision.kind, "INDEX")

    def test_nomenclature_page_keeps_symbol_definition_pairs(self):
        lines = ["Nomenclature"]
        for symbol, definition in (
            ("E", "Energy of the system"),
            ("m", "Mass of the particle"),
            ("c", "Speed of light"),
            ("F", "Applied force"),
            ("a", "Measured acceleration"),
        ):
            lines.extend((symbol, definition))
        decision = classify_preserved_page("\n".join(lines))
        self.assertIsNotNone(decision)
        self.assertEqual(decision.kind, "NOMENCLATURE")

    def test_reference_page_keeps_citation_numbering(self):
        text = "References\n" + "\n".join(
            f"[{index}] Author, A. ({2020 + index}). https://doi.org/10.1/{index}"
            for index in range(1, 6)
        )
        decision = classify_preserved_page(text)
        self.assertIsNotNone(decision)
        self.assertEqual(decision.kind, "REFERENCES")

    def test_normal_prose_is_not_misclassified(self):
        self.assertIsNone(
            classify_preserved_page(
                "A short introduction\nThis paragraph explains a translation system."
            )
        )

    def test_converter_rejects_an_unregistered_service(self):
        with self.assertRaisesRegex(ValueError, "Unsupported translation service"):
            TranslateConverter(PDFResourceManager(), service="bing")

    def test_converter_accepts_every_registered_engine(self):
        for service in ("google", "handoff"):
            with self.subTest(service=service):
                converter = TranslateConverter(PDFResourceManager(), service=service)
                self.assertEqual(converter.translator.name, service)


if __name__ == "__main__":
    unittest.main()
