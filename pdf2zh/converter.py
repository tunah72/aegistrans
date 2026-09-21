import concurrent.futures
import logging
import re
import unicodedata
from enum import Enum
from string import Template
from typing import Dict

import numpy as np
from pdfminer.converter import PDFConverter
from pdfminer.layout import LTChar, LTFigure, LTLine, LTPage
from pdfminer.pdffont import PDFCIDFont, PDFUnicodeNotDefined
from pdfminer.pdfinterp import PDFGraphicState, PDFResourceManager
from pdfminer.utils import apply_matrix_pt, mult_matrix
from pymupdf import Font
from tenacity import retry, stop_after_attempt, wait_exponential

from pdf2zh.rules import BULLET_CHARACTERS, is_formula_font, line_height_for_language
from pdf2zh.translator import ENGINES, BaseTranslator

log = logging.getLogger(__name__)


class PDFConverterEx(PDFConverter):
    def __init__(
        self,
        rsrcmgr: PDFResourceManager,
    ) -> None:
        PDFConverter.__init__(self, rsrcmgr, None, "utf-8", 1, None)

    def begin_page(self, page, ctm) -> None:
        x0, y0, x1, y1 = page.cropbox
        x0, y0 = apply_matrix_pt(ctm, (x0, y0))
        x1, y1 = apply_matrix_pt(ctm, (x1, y1))
        mediabox = (0, 0, abs(x0 - x1), abs(y0 - y1))
        self.cur_item = LTPage(page.pageno, mediabox)

    def end_page(self, page):
        return self.receive_layout(self.cur_item)

    def begin_figure(self, name, bbox, matrix) -> None:
        self._stack.append(self.cur_item)
        self.cur_item = LTFigure(name, bbox, mult_matrix(matrix, self.ctm))
        self.cur_item.pageid = self._stack[-1].pageid

    def end_figure(self, _: str) -> None:
        fig = self.cur_item
        assert isinstance(self.cur_item, LTFigure), str(type(self.cur_item))
        self.cur_item = self._stack.pop()
        self.cur_item.add(fig)
        return self.receive_layout(fig)

    def render_char(
        self,
        matrix,
        font,
        fontsize: float,
        scaling: float,
        rise: float,
        cid: int,
        ncs,
        graphicstate: PDFGraphicState,
    ) -> float:
        try:
            text = font.to_unichr(cid)
            assert isinstance(text, str), str(type(text))
        except PDFUnicodeNotDefined:
            text = self.handle_undefined_char(font, cid)
        textwidth = font.char_width(cid)
        textdisp = font.char_disp(cid)
        item = LTChar(
            matrix,
            font,
            fontsize,
            scaling,
            rise,
            text,
            textwidth,
            textdisp,
            ncs,
            graphicstate,
        )
        self.cur_item.add(item)
        item.cid = cid
        item.font = font
        return item.adv


def detect_font_style(fontname: str, size: float):
    fn = str(fontname).lower()
    is_bold = bool(re.search(r"bold|heavy|black|semibold|demi", fn) or size >= 13.5)
    is_italic = bool(re.search(r"italic|oblique", fn))
    return is_bold, is_italic


def is_heading_font(fontname: str) -> bool:
    """Detect if font is typically used for headings."""
    fn = str(fontname).lower()
    return bool(re.search(r"gotham|myriad|bold|semibold|demi|heavy|black", fn))


def font_family_clean(fontname: str) -> str:
    """Extract general font family name (myriad, garamond, gotham, helvetica, etc.)."""
    fn = str(fontname).lower()
    for fam in ["myriad", "garamond", "gotham", "helvetica", "times"]:
        if fam in fn:
            return fam
    return fn.split("+")[-1].split("-")[0]


def detect_color_op(child) -> str:
    """Extract non-stroking (fill) color operator for a character or element."""
    gs = getattr(child, "graphicstate", None)
    ncolor = getattr(gs, "ncolor", None) if gs else None
    if ncolor is not None:
        if isinstance(ncolor, (list, tuple)):
            if len(ncolor) == 4:
                return f"{ncolor[0]:.4f} {ncolor[1]:.4f} {ncolor[2]:.4f} {ncolor[3]:.4f} k "
            elif len(ncolor) == 3:
                return f"{ncolor[0]:.4f} {ncolor[1]:.4f} {ncolor[2]:.4f} rg "
            elif len(ncolor) == 1:
                return f"{ncolor[0]:.4f} g "
        elif isinstance(ncolor, (int, float)):
            return f"{float(ncolor):.4f} g "
    return "0 g "


class Paragraph:
    def __init__(
        self,
        y,
        x,
        x0,
        x1,
        y0,
        y1,
        size,
        brk,
        is_bold=False,
        is_italic=False,
        fontname="",
        color_op="0 g ",
        cls=0,
    ):
        self.y: float = y
        self.x: float = x
        self.x0: float = x0
        self.x1: float = x1
        self.y0: float = y0
        self.y1: float = y1
        self.size: float = size
        self.brk: bool = brk
        self.is_bold: bool = is_bold
        self.is_italic: bool = is_italic
        self.fontname: str = fontname
        self.color_op: str = color_op
        self.cls: int = cls


# fmt: off
class TranslateConverter(PDFConverterEx):
    def __init__(
        self,
        rsrcmgr,
        vfont: str = None,
        vchar: str = None,
        thread: int = 0,
        layout={},
        lang_in: str = "",
        lang_out: str = "",
        service: str = "",
        noto_name: str = "",
        noto: Font = None,
        envs: Dict = None,
        prompt: Template = None,
        ignore_cache: bool = False,
        noto_fonts: dict = None,
    ) -> None:
        super().__init__(rsrcmgr)
        self.vfont = vfont
        self.vchar = vchar
        self.thread = thread
        self.layout = layout
        self.noto_name = noto_name
        self.noto = noto
        self.noto_fonts = noto_fonts or ({noto_name: noto} if noto else {})
        self.translator: BaseTranslator = None
        self.scanned_pages: set = set()
        # Segments whose retries ran out; reported as a partial translation.
        self.translation_failures: list[str] = []
        # e.g. "handoff:model" -> ["handoff", "model"]; model is unused by both engines
        param = service.split(":", 1)
        service_name = param[0]
        service_model = param[1] if len(param) > 1 else None
        if not envs:
            envs = {}
        if service_name not in ENGINES:
            supported = ", ".join(sorted(ENGINES))
            raise ValueError(
                f"Unsupported translation service {service_name!r}; supported: {supported}"
            )
        self.translator = ENGINES[service_name](
            lang_in,
            lang_out,
            service_model,
            envs=envs,
            prompt=prompt,
            ignore_cache=ignore_cache,
        )

    def receive_layout(self, ltpage: LTPage):
        sstk: list[str] = []
        pstk: list[Paragraph] = []
        vbkt: int = 0
        vstk: list[LTChar] = []
        vlstk: list[LTLine] = []
        vfix: float = 0
        var: list[list[LTChar]] = []
        varl: list[list[LTLine]] = []
        varf: list[float] = []
        vlen: list[float] = []
        lstk: list[LTLine] = []
        xt: LTChar = None
        xt_cls: int = -1
        vmax: float = ltpage.width / 4
        ops: str = ""

        def vflag(font: str, char: str):
            if isinstance(font, bytes):
                try:
                    font = font.decode('utf-8')
                except UnicodeDecodeError:
                    font = ""
            font = font.split("+")[-1]
            if re.match(r"\(cid:", char):
                return True
            if self.vfont:
                if re.match(self.vfont, font):
                    return True
            else:
                if is_formula_font(font):
                    return True
            if self.vchar:
                if re.match(self.vchar, char):
                    return True
            else:
                if (
                    char
                    and char != " "
                    and (
                        unicodedata.category(char[0])
                        in ["Lm", "Mn", "Sk", "Sm", "Zl", "Zp", "Zs"]
                        or ord(char[0]) in range(0x370, 0x400)
                    )
                ):
                    return True
            return False

        ############################################################
        for child in ltpage:
            if isinstance(child, LTChar):
                cur_v = False
                layout = self.layout[ltpage.pageid]
                h, w = layout.shape
                cx, cy = np.clip(int(child.x0), 0, w - 1), np.clip(int(child.y0), 0, h - 1)
                cls = layout[cy, cx]
                if child.get_text() in BULLET_CHARACTERS:
                    cls = 0
                is_sub_or_super = (
                    cls == xt_cls
                    and len(sstk) > 0
                    and len(sstk[-1].strip()) > 1
                    and child.size < pstk[-1].size * 0.79
                    and not child.get_text().isalpha()
                )
                if (
                    cls == 0
                    or is_sub_or_super
                    or vflag(child.fontname, child.get_text())
                    or (child.matrix[0] == 0 and child.matrix[3] == 0)
                ):
                    cur_v = True
                if not cur_v:
                    if vstk and child.get_text() == "(":
                        cur_v = True
                        vbkt += 1
                    if vbkt and child.get_text() == ")":
                        cur_v = True
                        vbkt -= 1
                if (
                    not cur_v
                    or cls != xt_cls
                    or (sstk[-1] != "" and abs(child.x0 - xt.x0) > vmax)
                ):
                    if vstk:
                        if (
                            not cur_v
                            and cls == xt_cls
                            and child.x0 > max([vch.x0 for vch in vstk])
                        ):
                            vfix = vstk[0].y0 - child.y0
                        if sstk[-1] == "":
                            xt_cls = -1
                        sstk[-1] += f"{{v{len(var)}}}"
                        var.append(vstk)
                        varl.append(vlstk)
                        varf.append(vfix)
                        vstk = []
                        vlstk = []
                        vfix = 0
                if not vstk:
                    is_b, is_i = detect_font_style(child.fontname, child.size)
                    target_cls = pstk[-1].cls if pstk else cls
                    effective_cls = cls if cls > 0 else target_cls
                    is_same_line = (
                        xt is not None
                        and len(pstk) > 0
                        and (cls == xt_cls or (effective_cls > 0 and target_cls > 0 and abs(child.size - pstk[-1].size) <= 1.5))
                        and abs(child.y0 - xt.y0) <= max(pstk[-1].size, child.size) * 0.45
                        and child.x0 >= xt.x0 - 2.0
                        and abs(child.size - pstk[-1].size) <= 3.0
                    )
                    is_wrap_cand = (
                        xt is not None
                        and len(pstk) > 0
                        and child.x1 < xt.x0
                        and 0.3 * pstk[-1].size <= abs(child.y0 - xt.y0) <= pstk[-1].size * 1.6
                        and (cls > 0 or xt_cls > 0 or target_cls > 0)
                    )
                    continue_wrap = False
                    if is_wrap_cand:
                        prev_is_h = pstk[-1].is_bold or is_heading_font(pstk[-1].fontname) or pstk[-1].size >= 11.5
                        curr_is_h = is_b or is_heading_font(child.fontname) or child.size >= 11.5
                        diff_size = abs(child.size - pstk[-1].size) > 1.2
                        diff_fam = font_family_clean(pstk[-1].fontname) != font_family_clean(child.fontname)
                        is_indent = (
                            child.x0 > pstk[-1].x0 + 7.0
                            and sstk[-1].rstrip().endswith((".", ":", "!", "?", "”", '"', "—", "–"))
                        )
                        prev_is_caption = bool(re.match(r"^(•\s*)?(Fig|Figure|Table)\b", sstk[-1].strip(), re.IGNORECASE))
                        h_mismatch = (prev_is_h != curr_is_h) and not prev_is_caption
                        if prev_is_caption:
                            diff_fam = False
                        same_col = abs(child.x0 - pstk[-1].x0) <= 25.0 or abs(child.x0 - pstk[-1].x) <= 25.0
                        if not h_mismatch and not diff_size and not diff_fam and not is_indent:
                            if cls == xt_cls or cls == target_cls or xt_cls == target_cls:
                                continue_wrap = True
                            elif same_col:
                                prev_ended = sstk[-1].rstrip().endswith((".", ":", "!", "?", "”", '"'))
                                if not prev_ended:
                                    continue_wrap = True

                    if is_same_line or continue_wrap:
                        if child.x1 < xt.x0:
                            sstk[-1] += " "
                            pstk[-1].brk = True
                        elif child.x0 > xt.x1 + 1:
                            sstk[-1] += " "
                        if child.get_text().strip() and cls > 0:
                            pstk[-1].cls = cls
                    else:
                        c_op = detect_color_op(child)
                        sstk.append("")
                        pstk.append(Paragraph(child.y0, child.x0, child.x0, child.x0, child.y0, child.y1, child.size, False, is_b, is_i, child.fontname, c_op, cls=cls))
                if not cur_v:
                    if len(sstk[-1].strip()) == 0 and child.get_text().strip():
                        pstk[-1].x = child.x0
                        pstk[-1].y = child.y0
                        pstk[-1].x0 = child.x0
                        pstk[-1].y0 = child.y0
                    if (
                        child.size > pstk[-1].size
                        or len(sstk[-1].strip()) == 1
                    ) and child.get_text() != " ":
                        pstk[-1].y -= child.size - pstk[-1].size
                        pstk[-1].size = child.size
                    c_op = detect_color_op(child)
                    if pstk[-1].color_op == "0 g " and c_op != "0 g ":
                        pstk[-1].color_op = c_op
                    sstk[-1] += child.get_text()
                else:
                    if (
                        not vstk
                        and cls == xt_cls
                        and child.x0 > xt.x0
                    ):
                        vfix = child.y0 - xt.y0
                    vstk.append(child)
                pstk[-1].x0 = min(pstk[-1].x0, child.x0)
                pstk[-1].x1 = max(pstk[-1].x1, child.x1)
                pstk[-1].y0 = min(pstk[-1].y0, child.y0)
                pstk[-1].y1 = max(pstk[-1].y1, child.y1)
                xt = child
                if child.get_text().strip() and cls > 0:
                    xt_cls = cls
            elif isinstance(child, LTFigure):
                pass
            elif isinstance(child, LTLine):
                layout = self.layout[ltpage.pageid]
                h, w = layout.shape
                cx, cy = np.clip(int(child.x0), 0, w - 1), np.clip(int(child.y0), 0, h - 1)
                cls = layout[cy, cx]
                if vstk and cls == xt_cls:
                    vlstk.append(child)
                else:
                    lstk.append(child)
            else:
                pass
        if vstk:
            sstk[-1] += f"{{v{len(var)}}}"
            var.append(vstk)
            varl.append(vlstk)
            varf.append(vfix)
        log.debug("\n==========[VSTACK]==========\n")
        for id, v in enumerate(var):
            l = max([vch.x1 for vch in v]) - v[0].x0
            log.debug(f'< {l:.1f} {v[0].x0:.1f} {v[0].y0:.1f} {v[0].cid} {v[0].fontname} {len(varl[id])} > v{id} = {"".join([ch.get_text() for ch in v])}')
            vlen.append(l)

        ############################################################
        log.debug("\n==========[SSTACK]==========\n")

        # Google throttles a long document, so back off instead of hammering it.
        # Roughly two minutes of patience per segment, then give up rather than
        # hang the run forever the way an unbounded retry used to.
        @retry(
            wait=wait_exponential(multiplier=1, min=1, max=60),
            stop=stop_after_attempt(8),
            reraise=True,
        )
        def translate_segment(s: str) -> str:
            return self.translator.translate(s)

        def worker(s: str) -> str:
            if not s.strip() or re.match(r"^\{v\d+\}$", s):
                return s
            try:
                return translate_segment(s)
            except BaseException as e:
                # A book is thousands of segments over tens of minutes, so one
                # dead connection must not throw the whole document away. Keep
                # the source text and let the caller report how much is missing.
                if log.isEnabledFor(logging.DEBUG):
                    log.exception(e)
                else:
                    log.exception(e, exc_info=False)
                self.translation_failures.append(s)
                return s
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.thread
        ) as executor:
            news = list(executor.map(worker, sstk))

        ############################################################
        def raw_string(fcur: str, cstk: str):
            if fcur in self.noto_fonts:
                return "".join(["%04x" % self.noto_fonts[fcur].has_glyph(ord(c)) for c in cstk])
            elif fcur == self.noto_name:
                return "".join(["%04x" % self.noto.has_glyph(ord(c)) for c in cstk])
            elif isinstance(self.fontmap[fcur], PDFCIDFont):
                return "".join(["%04x" % ord(c) for c in cstk])
            else:
                return "".join(["%02x" % ord(c) for c in cstk])

        default_line_height = line_height_for_language(self.translator.lang_out)
        _x, _y = 0, 0
        ops_list = []

        # Draw white rectangles to cover original text in background image (scanned PDFs only)
        white_rects = ""
        if ltpage.pageid in self.scanned_pages:
            pad = 3  # padding to fully cover original text with descenders/ascenders
            for id, new in enumerate(news):
                if new != sstk[id]:  # Only cover areas that were translated
                    rx0 = pstk[id].x0 - pad
                    ry0 = pstk[id].y0 - pad
                    rw = pstk[id].x1 - pstk[id].x0 + pad * 2
                    rh = pstk[id].y1 - pstk[id].y0 + pad * 2
                    white_rects += f"q 1 1 1 rg {rx0:f} {ry0:f} {rw:f} {rh:f} re f Q "
            # Also cover formula areas
            for v in var:
                if v:
                    fx0 = min(ch.x0 for ch in v) - pad
                    fy0 = min(ch.y0 for ch in v) - pad
                    fx1 = max(ch.x1 for ch in v) + pad
                    fy1 = max(ch.y1 for ch in v) + pad
                    white_rects += f"q 1 1 1 rg {fx0:f} {fy0:f} {fx1-fx0:f} {fy1-fy0:f} re f Q "

        def gen_op_txt(font, size, x, y, rtxt, color_op="0 g "):
            return f"{color_op}/{font} {size:f} Tf 1 0 0 1 {x:f} {y:f} Tm [<{rtxt}>] TJ "

        def gen_op_line(x, y, xlen, ylen, linewidth):
            return f"ET q 1 0 0 1 {x:f} {y:f} cm [] 0 d 0 J {linewidth:f} w 0 0 m {xlen:f} {ylen:f} l S Q BT "

        # Compute column right boundaries to allow headings and single-line paragraphs
        # to expand naturally up to the column boundary without false wrapping.
        for p in pstk:
            if not p.brk:
                col_candidates = [
                    q.x1 for q in pstk
                    if abs(q.x0 - p.x0) <= 5.0 and (q.brk or q.x1 > p.x1 + 30.0)
                ]
                col_x1 = max(col_candidates) if col_candidates else p.x1
                obstacles = [
                    q.x0 for q in pstk
                    if q is not p and q.x0 > p.x0 + 10.0
                    and not (q.y1 < p.y0 - 2.0 or q.y0 > p.y1 + 2.0)
                ]
                max_right = min(obstacles) - 5.0 if obstacles else col_x1
                p.x1 = max(p.x1, min(col_x1, max_right))

        for id, new in enumerate(news):
            # Select target font variant based on paragraph style
            target_font_name = self.noto_name
            if pstk[id].is_bold and "noto_b" in self.noto_fonts:
                target_font_name = "noto_b"
            elif pstk[id].is_italic and "noto_i" in self.noto_fonts:
                target_font_name = "noto_i"

            active_noto = self.noto_fonts.get(target_font_name, self.noto)
            new = unicodedata.normalize("NFC", new)

            x: float = pstk[id].x
            if x > pstk[id].x0 + 30.0 and pstk[id].x1 > pstk[id].x0 + 50.0:
                x = pstk[id].x0
            y: float = pstk[id].y
            x0: float = pstk[id].x0
            x1: float = pstk[id].x1
            height: float = pstk[id].y1 - pstk[id].y0
            size: float = pstk[id].size
            brk: bool = pstk[id].brk

            # Auto-scale font size if translation is longer than original
            # Calculate actual rendered width of translated text at current size
            if new != sstk[id]:
                line_width = x1 - x0
                # Count how many lines the original text occupied
                orig_lines = max(1, round(height / (pstk[id].size * default_line_height))) if brk else 1
                total_avail = line_width * orig_lines
                # Measure actual width of translated text (excluding formula tags)
                total_new_width = 0
                tmp_ptr = 0
                plain_new = new
                while tmp_ptr < len(plain_new):
                    vm = re.match(r"\{\s*v([\d\s]+)\}", plain_new[tmp_ptr:], re.IGNORECASE)
                    if vm:
                        try:
                            vid_tmp = int(vm.group(1).replace(" ", ""))
                            total_new_width += vlen[vid_tmp]
                        except Exception:
                            pass
                        tmp_ptr += len(vm.group(0))
                    else:
                        ch = plain_new[tmp_ptr]
                        try:
                            if self.translator.lang_out != "vi" and self.fontmap.get("tiro") and self.fontmap["tiro"].to_unichr(ord(ch)) == ch:
                                total_new_width += self.fontmap["tiro"].char_width(ord(ch)) * pstk[id].size
                            else:
                                total_new_width += active_noto.char_lengths(ch, pstk[id].size)[0]
                        except Exception:
                            total_new_width += pstk[id].size * 0.5
                        tmp_ptr += 1
                if total_avail > 0 and total_new_width > total_avail * 1.05:
                    ratio = total_avail / total_new_width
                    size = pstk[id].size * max(ratio, 0.5)  # don't go below 50%

            # Pre-compute word-boundary line breaks to avoid mid-word splits
            if brk or (x1 - x0 > 0 and " " in new):
                def _measure_char(c):
                    try:
                        if self.translator.lang_out != "vi" and self.fontmap.get("tiro") and self.fontmap["tiro"].to_unichr(ord(c)) == c:
                            return self.fontmap["tiro"].char_width(ord(c)) * size
                    except Exception:
                        pass
                    try:
                        return active_noto.char_lengths(c, size)[0]
                    except Exception:
                        return size * 0.5

                break_positions = set()
                cur_x = x
                last_space_ptr = -1
                last_space_x_after = cur_x
                p2 = 0
                while p2 < len(new):
                    vr2 = re.match(r"\{\s*v([\d\s]+)\}", new[p2:], re.IGNORECASE)
                    if vr2:
                        try:
                            vid_t = int(vr2.group(1).replace(" ", ""))
                            cw = vlen[vid_t]
                        except Exception:
                            cw = 0
                        if cur_x + cw > x1 + 0.1 * size and cur_x > x0 + 0.1 * size:
                            if last_space_ptr >= 0:
                                break_positions.add(last_space_ptr + 1)
                                cur_x = x0 + (cur_x - last_space_x_after)
                                last_space_ptr = -1
                                last_space_x_after = x0
                        cur_x += cw
                        p2 += len(vr2.group(0))
                    else:
                        ch2 = new[p2]
                        cw = _measure_char(ch2)
                        if ch2 == ' ':
                            last_space_ptr = p2
                            last_space_x_after = cur_x + cw
                        if cur_x + cw > x1 + 0.1 * size and cur_x > x0 + 0.1 * size:
                            if last_space_ptr >= 0:
                                break_positions.add(last_space_ptr + 1)
                                cur_x = x0 + (cur_x - last_space_x_after)
                                last_space_ptr = -1
                                last_space_x_after = x0
                        cur_x += cw
                        p2 += 1
                # Replace spaces at break positions with newlines (process in reverse)
                for bp in sorted(break_positions, reverse=True):
                    new = new[:bp - 1] + '\n' + new[bp:]

            cstk: str = ""
            fcur: str = None
            lidx = 0
            tx = x
            fcur_ = fcur
            ptr = 0
            log.debug(f"< {y} {x} {x0} {x1} {size} {brk} > {sstk[id]} | {new}")

            ops_vals: list[dict] = []

            while ptr < len(new):
                vy_regex = re.match(
                    r"\{\s*v([\d\s]+)\}", new[ptr:], re.IGNORECASE
                )
                mod = 0
                if vy_regex:
                    ptr += len(vy_regex.group(0))
                    try:
                        vid = int(vy_regex.group(1).replace(" ", ""))
                        adv = vlen[vid]
                    except Exception:
                        continue
                    if var[vid][-1].get_text() and unicodedata.category(var[vid][-1].get_text()[0]) in ["Lm", "Mn", "Sk"]:
                        mod = var[vid][-1].width
                else:
                    ch = new[ptr]
                    if ch == '\n':  # Forced line break from word-wrap pre-computation
                        if cstk:
                            ops_vals.append({
                                "type": OpType.TEXT,
                                "font": fcur,
                                "size": size,
                                "x": tx,
                                "dy": 0,
                                "rtxt": raw_string(fcur, cstk),
                                "lidx": lidx,
                                "color_op": pstk[id].color_op,
                            })
                            cstk = ""
                        x = x0
                        lidx += 1
                        ptr += 1
                        continue
                    fcur_ = None
                    if self.translator.lang_out != "vi":
                        try:
                            if fcur_ is None and self.fontmap["tiro"].to_unichr(ord(ch)) == ch:
                                fcur_ = "tiro"
                        except Exception:
                            pass
                    if fcur_ is None:
                        fcur_ = target_font_name
                    if fcur_ in self.noto_fonts:
                        adv = self.noto_fonts[fcur_].char_lengths(ch, size)[0]
                    elif fcur_ == self.noto_name:
                        adv = self.noto.char_lengths(ch, size)[0]
                    else:
                        adv = self.fontmap[fcur_].char_width(ord(ch)) * size
                    ptr += 1
                if (
                    fcur_ != fcur
                    or vy_regex
                    or x + adv > x1 + 0.1 * size
                ):
                    if cstk:
                        # Word-wrap: if hitting right boundary, break at last space
                        if x + adv > x1 + 0.1 * size and ' ' in cstk and x1 > x0:
                            last_space = cstk.rfind(' ')
                            before = cstk[:last_space]
                            after = cstk[last_space + 1:]
                            if before:
                                ops_vals.append({
                                    "type": OpType.TEXT,
                                    "font": fcur,
                                    "size": size,
                                    "x": tx,
                                    "dy": 0,
                                    "rtxt": raw_string(fcur, before),
                                    "lidx": lidx,
                                    "color_op": pstk[id].color_op,
                                })
                            # Move remainder to new line
                            lidx += 1
                            x = x0
                            tx = x
                            # Recalculate x for the remaining text
                            for rc in after:
                                if fcur == self.noto_name:
                                    x += self.noto.char_lengths(rc, size)[0]
                                else:
                                    x += self.fontmap[fcur].char_width(ord(rc)) * size
                            cstk = after
                        else:
                            ops_vals.append({
                                "type": OpType.TEXT,
                                "font": fcur,
                                "size": size,
                                "x": tx,
                                "dy": 0,
                                "rtxt": raw_string(fcur, cstk),
                                "lidx": lidx,
                                "color_op": pstk[id].color_op,
                            })
                            cstk = ""
                if x + adv > x1 + 0.1 * size and x1 > x0 and (" " in new.strip()):
                    x = x0
                    lidx += 1
                if vy_regex:
                    fix = 0
                    if fcur is not None:
                        fix = varf[vid]
                    for vch in var[vid]:
                        vc = chr(vch.cid)
                        ops_vals.append({
                            "type": OpType.TEXT,
                            "font": self.fontid[vch.font],
                            "size": vch.size,
                            "x": x + vch.x0 - var[vid][0].x0,
                            "dy": fix + vch.y0 - var[vid][0].y0,
                            "rtxt": raw_string(self.fontid[vch.font], vc),
                            "lidx": lidx,
                            "color_op": pstk[id].color_op,
                        })
                        if log.isEnabledFor(logging.DEBUG):
                            lstk.append(LTLine(0.1, (_x, _y), (x + vch.x0 - var[vid][0].x0, fix + y + vch.y0 - var[vid][0].y0)))
                            _x, _y = x + vch.x0 - var[vid][0].x0, fix + y + vch.y0 - var[vid][0].y0
                    for l in varl[vid]:
                        if l.linewidth < 5:
                            ops_vals.append({
                                "type": OpType.LINE,
                                "x": l.pts[0][0] + x - var[vid][0].x0,
                                "dy": l.pts[0][1] + fix - var[vid][0].y0,
                                "linewidth": l.linewidth,
                                "xlen": l.pts[1][0] - l.pts[0][0],
                                "ylen": l.pts[1][1] - l.pts[0][1],
                                "lidx": lidx
                            })
                else:
                    if not cstk:
                        tx = x
                        if x == x0 and ch == " ":
                            adv = 0
                        else:
                            cstk += ch
                    else:
                        cstk += ch
                adv -= mod
                fcur = fcur_
                x += adv
                if log.isEnabledFor(logging.DEBUG):
                    lstk.append(LTLine(0.1, (_x, _y), (x, y)))
                    _x, _y = x, y
            if cstk:
                ops_vals.append({
                    "type": OpType.TEXT,
                    "font": fcur,
                    "size": size,
                    "x": tx,
                    "dy": 0,
                    "rtxt": raw_string(fcur, cstk),
                    "lidx": lidx,
                    "color_op": pstk[id].color_op,
                })

            # An inline formula keeps the vertical offsets it had in the source,
            # so a fraction reaches far below its baseline while the prose around
            # it does not. Uniform leading therefore let the next line print
            # straight through the denominator. Measure what each line actually
            # occupies above and below its own baseline, and open up only the
            # gaps that need it.
            ink: dict[int, tuple[float, float]] = {}
            for vals in ops_vals:
                s_ = vals["size"] if vals["type"] == OpType.TEXT else 0.0
                lo = vals["dy"] + min(0.0, vals.get("ylen", 0.0)) - 0.22 * s_
                hi = vals["dy"] + max(0.0, vals.get("ylen", 0.0)) + 0.78 * s_
                plo, phi = ink.get(vals["lidx"], (lo, hi))
                ink[vals["lidx"]] = (min(plo, lo), max(phi, hi))

            line_height = default_line_height

            # Fit the prose to the box on its own. Charging the formula's extra
            # room to this loop drops the leading for every line in the
            # paragraph, until they collide with each other instead.
            while (lidx + 1) * size * line_height > height and line_height >= 0.8:
                line_height -= 0.05

            # If still overflowing after reducing line_height, shrink font to fit
            if lidx > 0 and (lidx + 1) * size * line_height > height:
                shrink = height / ((lidx + 1) * size * line_height)
                shrink = max(shrink, 0.5)  # Don't go below 50%
                size *= shrink
                for vals in ops_vals:
                    if vals["type"] == OpType.TEXT:
                        vals["size"] *= shrink

            # ponytail: the paragraph's own box is the whole budget, so a
            # formula in an already tight paragraph stays somewhat cramped.
            # Measuring the gap down to the next paragraph would buy the rest.
            offsets = line_offsets(ink, lidx, size, line_height,
                                   budget=height - (lidx + 1) * size * line_height)

            for vals in ops_vals:
                if vals["type"] == OpType.TEXT:
                    ops_list.append(gen_op_txt(vals["font"], vals["size"], vals["x"], vals["dy"] + y - offsets[vals["lidx"]], vals["rtxt"], vals.get("color_op", "0 g ")))
                elif vals["type"] == OpType.LINE:
                    ops_list.append(gen_op_line(vals["x"], vals["dy"] + y - offsets[vals["lidx"]], vals["xlen"], vals["ylen"], vals["linewidth"]))

        for l in lstk:
            if l.linewidth < 5:
                ops_list.append(gen_op_line(l.pts[0][0], l.pts[0][1], l.pts[1][0] - l.pts[0][0], l.pts[1][1] - l.pts[0][1], l.linewidth))

        ops = f"{white_rects}BT {''.join(ops_list)}ET "
        return ops


def line_offsets(
    ink: dict[int, tuple[float, float]],
    lines: int,
    size: float,
    line_height: float,
    budget: float | None = None,
) -> list[float]:
    """Distance from a paragraph's first baseline down to each later baseline.

    `ink[i]` is how far line i's glyphs reach below and above its own baseline.
    Prose lines get the usual leading; a line holding a tall inline formula gets
    the extra room its glyphs and its neighbour's need, so a fraction's
    denominator no longer lands on the line underneath. `budget` caps that extra
    at the space the paragraph has left, because spilling onto the paragraph
    below looks worse than a formula that is still a little tight.
    """
    base = size * line_height
    want = [
        max(0.0, (ink.get(i + 1, (0.0, 0.0))[1] - ink.get(i, (0.0, 0.0))[0]) - base)
        for i in range(lines)
    ]
    total = sum(want)
    if budget is not None and total > budget:
        # Not enough slack for every tall formula. Share out what there is
        # rather than growing the paragraph down over the text below it.
        scale = max(0.0, budget) / total
        want = [w * scale for w in want]
    offsets = [0.0]
    for extra in want:
        offsets.append(offsets[-1] + base + extra)
    return offsets


class OpType(Enum):
    TEXT = "text"
    LINE = "line"
