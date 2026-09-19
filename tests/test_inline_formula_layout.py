"""Regression tests for inline fractions overlapping the reflowed text.

Two separate defects produced the same symptom. A fraction rule was left at its
source position, striking through whatever the translation happened to reflow
underneath it, and a fraction's denominator was printed on top of the next line
because every line in a paragraph got the same leading.
"""

from __future__ import annotations

import unittest

from pdf2zh.converter import line_offsets
from pdf2zh.pdfinterp import PDFPageInterpreterEx
from pdfminer.pdfinterp import PDFGraphicState, PDFResourceManager


class RecordingDevice:
    """Just enough of a PDFDevice to see what do_S hands over."""

    def __init__(self) -> None:
        self.painted: list = []
        self.ctm = None

    def paint_path(self, gstate, stroke, fill, evenodd, path) -> None:
        self.painted.append((gstate, path))

    def set_ctm(self, ctm) -> None:
        self.ctm = ctm


def _stroke(scolor, ctm=(1, 0, 0, 1, 0, 0), linewidth=1.0, path=None):
    device = RecordingDevice()
    interpreter = PDFPageInterpreterEx(PDFResourceManager(), device, {})
    interpreter.ctm = ctm
    interpreter.graphicstate = PDFGraphicState()
    interpreter.graphicstate.scolor = scolor
    interpreter.graphicstate.linewidth = linewidth
    interpreter.curpath = path or [("m", 0.0, 0.0), ("l", 100.0, 0.0)]
    result = interpreter.do_S()
    return result, device.painted


class FractionRuleTests(unittest.TestCase):
    def test_a_rule_drawn_in_the_default_colour_is_moved_with_its_formula(self):
        # TeX emits no stroking-colour operator, so scolor stays None. Treating
        # that as "not black" left every inline fraction bar behind.
        result, painted = _stroke(None)
        self.assertEqual(result, "n")  # the original operator is dropped
        self.assertEqual(len(painted), 1)

    def test_an_explicitly_black_rule_still_moves(self):
        for scolor in (0, (0, 0, 0)):
            with self.subTest(scolor=scolor):
                result, painted = _stroke(scolor)
                self.assertEqual(result, "n")
                self.assertEqual(len(painted), 1)

    def test_a_coloured_rule_is_left_alone(self):
        result, painted = _stroke((1, 0, 0))
        self.assertNotEqual(result, "n")  # keep the original operator in place
        self.assertEqual(painted, [])

    def test_the_line_width_is_scaled_by_the_ctm_it_was_drawn_under(self):
        # The redrawn rule carries no CTM, so a TeX `0.1 cm` scale has to be
        # baked in or a 4.05pt operand comes out as a 4pt slab.
        _, painted = _stroke(None, ctm=(0.1, 0, 0, 0.1, 0, 0), linewidth=4.05)
        self.assertAlmostEqual(painted[0][0].linewidth, 0.405, places=3)

    def test_scaling_does_not_leak_into_later_strokes(self):
        device = RecordingDevice()
        interpreter = PDFPageInterpreterEx(PDFResourceManager(), device, {})
        interpreter.ctm = (0.1, 0, 0, 0.1, 0, 0)
        interpreter.graphicstate = PDFGraphicState()
        interpreter.graphicstate.scolor = None
        interpreter.graphicstate.linewidth = 4.05
        interpreter.curpath = [("m", 0.0, 0.0), ("l", 100.0, 0.0)]
        interpreter.do_S()
        self.assertAlmostEqual(interpreter.graphicstate.linewidth, 4.05)

    def test_a_slanted_rule_is_left_alone(self):
        result, painted = _stroke(None, path=[("m", 0.0, 0.0), ("l", 100.0, 5.0)])
        self.assertNotEqual(result, "n")
        self.assertEqual(painted, [])


class LineOffsetTests(unittest.TestCase):
    SIZE = 10.0
    LEADING = 1.1

    def _offsets(self, ink, lines, budget=None):
        return line_offsets(ink, lines, self.SIZE, self.LEADING, budget)

    def test_prose_keeps_the_usual_even_leading(self):
        prose = (-0.22 * self.SIZE, 0.78 * self.SIZE)
        offsets = self._offsets({i: prose for i in range(4)}, 3)
        self.assertEqual([round(o, 4) for o in offsets], [0.0, 11.0, 22.0, 33.0])

    def test_a_deep_denominator_pushes_only_the_line_below_it(self):
        prose = (-2.2, 7.8)
        ink = {0: prose, 1: (-12.0, 7.8), 2: prose}  # line 1 holds the fraction
        offsets = self._offsets(ink, 2)
        self.assertEqual(round(offsets[1], 4), 11.0)   # gap above is unchanged
        self.assertEqual(round(offsets[2] - offsets[1], 4), 19.8)  # 7.8 - (-12.0)

    def test_a_tall_numerator_pushes_the_line_above_it(self):
        prose = (-2.2, 7.8)
        ink = {0: prose, 1: (-2.2, 16.0)}
        offsets = self._offsets(ink, 1)
        self.assertEqual(round(offsets[1], 4), 18.2)   # 16.0 - (-2.2)

    def test_extra_room_is_capped_at_the_paragraph_slack(self):
        # Growing the paragraph past its own box drops it onto the text below,
        # which looks worse than a formula that is still a little tight.
        ink = {0: (-2.2, 7.8), 1: (-12.0, 7.8), 2: (-2.2, 7.8)}
        offsets = self._offsets(ink, 2, budget=3.0)
        self.assertEqual(round(offsets[2], 4), 25.0)  # 11 + 11 + the 3.0 allowed

    def test_competing_formulas_share_the_slack(self):
        ink = {0: (-12.0, 7.8), 1: (-12.0, 7.8), 2: (-2.2, 7.8)}
        offsets = self._offsets(ink, 2, budget=4.0)
        self.assertEqual(round(offsets[1] - 0.0, 4), 13.0)   # half of 4.0 each
        self.assertEqual(round(offsets[2] - offsets[1], 4), 13.0)

    def test_a_paragraph_with_no_slack_keeps_the_plain_leading(self):
        ink = {0: (-2.2, 7.8), 1: (-12.0, 7.8)}
        self.assertEqual([round(o, 4) for o in self._offsets(ink, 1, budget=0.0)],
                         [0.0, 11.0])

    def test_a_single_line_paragraph_needs_no_gaps(self):
        self.assertEqual(self._offsets({0: (-2.2, 7.8)}, 0), [0.0])

    def test_lines_without_recorded_ink_fall_back_to_the_usual_leading(self):
        self.assertEqual([round(o, 4) for o in self._offsets({}, 2)], [0.0, 11.0, 22.0])


if __name__ == "__main__":
    unittest.main()
