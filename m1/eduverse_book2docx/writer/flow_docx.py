"""flow.docx, the editable output.

Everything in reading order, real Word styles, real tables, native OMML
equations, images at printed size with the VLM description in the alt text.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Emu, Pt, RGBColor

from .. import mathtools
from ..textclean import clean, readable_color
from ..config import Config
from ..ledger import Ledger
from ..omml import Unsupported, latex_to_omml
from ..schema import Block, Book, Page, Run, TableCell
from . import template
from .ooxml import (P_ORDER, PPR_ORDER, TBLPR_ORDER, TCPR_ORDER, TRPR_ORDER,
                    after_ppr, insert_ordered, replace_ordered)

ALIGN = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
         "right": WD_ALIGN_PARAGRAPH.RIGHT,
         "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}

STYLE_FOR = {
    "title": "EV Title",
    "heading": None,          # resolved by level
    "paragraph": "EV Body",
    "caption": "EV Caption",
    "equation": "EV Equation",
    "box": "EV Box",
}


class FlowWriter:
    def __init__(self, book: Book, out_dir: str, cfg: Config, ledger: Ledger):
        self.book = book
        self.out_dir = out_dir
        self.cfg = cfg
        self.ledger = ledger
        self.stats: Dict[str, int] = {"paragraphs": 0, "tables": 0,
                                      "pictures": 0, "equations": 0,
                                      "figure_notes": 0,
                                      "equation_images": 0, "bookmarks": 0}
        self._bm = 0

    # -- public ----------------------------------------------------------
    def write(self, path: str) -> str:
        tpl = template.ensure(self.out_dir, self.cfg)
        doc = Document(tpl)
        self._apply_page_setup(doc, self.book.pages[0])

        last_size: Optional[Tuple[float, float]] = None
        for pi, page in enumerate(self.book.pages):
            size = (round(page.width_pt, 1), round(page.height_pt, 1))
            if last_size is not None and size != last_size:
                doc.add_section(WD_SECTION.NEW_PAGE)
                self._apply_page_setup(doc, page)
            last_size = size

            if self.cfg.show_page_markers:
                p = doc.add_paragraph(style="EV Note")
                p.add_run(f"Page {page.page}")
                self._bookmark(p, f"p{page.page:03d}")

            for blk in page.blocks:
                self._write_block(doc, blk, page)

            if self.cfg.page_lock and pi < len(self.book.pages) - 1:
                doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

        doc.save(path)
        return path

    # -- page setup -------------------------------------------------------
    def _apply_page_setup(self, doc, page: Page) -> None:
        sec = doc.sections[-1]
        sec.page_width = Pt(page.width_pt)
        sec.page_height = Pt(page.height_pt)
        m = page.margins_pt
        sec.left_margin = Pt(max(18.0, min(m[0], page.width_pt / 3)))
        sec.top_margin = Pt(max(18.0, min(m[1], page.height_pt / 3)))
        sec.right_margin = Pt(max(18.0, min(m[2], page.width_pt / 3)))
        sec.bottom_margin = Pt(max(18.0, min(m[3], page.height_pt / 3)))

    # -- dispatch ---------------------------------------------------------
    def _write_block(self, doc, blk: Block, page: Page) -> None:
        if blk.type == "page_furniture":
            return
        body = doc.element.body
        mark = body[-2] if len(body) >= 2 else None
        self._write_block_inner(doc, blk, page)
        if blk.box >= 0 and self.cfg.box_panels_in_docx and \
                blk.type in ("paragraph", "heading", "list_item", "caption",
                             "equation"):
            node = mark.getnext() if mark is not None else body[0]
            while node is not None and node.tag != qn("w:sectPr"):
                if node.tag == qn("w:p"):
                    _panel_paragraph(node, self.cfg.box_shading,
                                     "B9A57E" if blk.box % 2 == 0 else "B9A57F")
                node = node.getnext()

    def _write_block_inner(self, doc, blk: Block, page: Page) -> None:
        try:
            if blk.type == "figure":
                self._figure(doc, blk)
            elif blk.type == "table":
                self._table(doc, blk, page)
            elif blk.type == "equation":
                self._equation(doc, blk)
            elif blk.type == "list_item":
                self._list_item(doc, blk)
            elif blk.type == "figure_note":
                self._figure_note(doc, blk, page)
            elif blk.type == "box":
                self._box(doc, blk, page)
            else:
                self._paragraph(doc, blk)
        except Exception as exc:                      # never lose the book
            self.ledger.drop(blk.id, blk.page, "unsupported",
                             f"{type(exc).__name__}: {exc}"[:150])
            if blk.text:
                p = doc.add_paragraph(style="EV Body")
                p.add_run(clean(blk.text))
                self.stats["paragraphs"] += 1

    # -- paragraphs -------------------------------------------------------
    def _style_name(self, blk: Block) -> str:
        if blk.type == "heading":
            lv = max(1, min(4, blk.level or 2))
            return f"EV H{lv}"
        return STYLE_FOR.get(blk.type, "EV Body")

    def _paragraph(self, doc, blk: Block):
        p = doc.add_paragraph(style=self._style_name(blk))
        if blk.align in ALIGN and blk.type != "caption":
            p.paragraph_format.alignment = ALIGN[blk.align]
        self._emit_runs(p, blk.text, blk.runs)
        self._bookmark(p, blk.id)
        if blk.caption_of:
            self._relation(p, "capof", blk.caption_of)
        self.stats["paragraphs"] += 1
        return p

    def _list_item(self, doc, blk: Block):
        style = ("EV List Number" if blk.block_kind == "number"
                 else "EV List Bullet")
        p = doc.add_paragraph(style=style)
        p.paragraph_format.left_indent = Pt(18 + 18 * max(0, blk.indent_level))
        text = blk.text
        runs = blk.runs
        # strip the printed bullet, Word draws its own
        from ..structure import BULLET_RE
        m = BULLET_RE.match(text)
        if m and blk.block_kind == "bullet":
            cut = m.end()
            text = text[cut:]
            runs = [Run(s=max(0, r.s - cut), e=max(0, r.e - cut), bold=r.bold,
                        italic=r.italic, underline=r.underline, color=r.color)
                    for r in runs if r.e > cut]
        self._emit_runs(p, text, runs)
        self._bookmark(p, blk.id)
        self.stats["paragraphs"] += 1
        return p

    def _box(self, doc, blk: Block, page: Page):
        """Activity / do-you-know panels keep their visual grouping."""
        tbl = doc.add_table(rows=1, cols=1)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        cell = tbl.cell(0, 0)
        usable = page.width_pt - page.margins_pt[0] - page.margins_pt[2]
        _set_cell_width(cell, usable)
        _set_table_width(tbl, usable)
        _shade(cell, self.cfg.box_shading)
        _no_borders(tbl)
        cell.paragraphs[0].style = doc.styles["EV Box"]
        self._emit_runs(cell.paragraphs[0], blk.text, blk.runs)
        self._bookmark(cell.paragraphs[0], blk.id)
        self.stats["tables"] += 1
        doc.add_paragraph(style="EV Body")

    def _figure_note(self, doc, blk: Block, page: Page):
        """A shaded box under the figure holding the description that was read
        off the real image. Visible in the document, not only in the alt text."""
        tbl = doc.add_table(rows=1, cols=1)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        cell = tbl.cell(0, 0)
        width = max(120.0, min(blk.width or 0,
                               page.width_pt - page.margins_pt[0]
                               - page.margins_pt[2]))
        if width < 200:
            width = page.width_pt - page.margins_pt[0] - page.margins_pt[2]
        _set_table_width(tbl, width)
        _set_grid(tbl, [width])
        _set_cell_width(cell, width)
        _shade(cell, self.cfg.figure_note_shading)
        _no_borders(tbl)

        head = cell.paragraphs[0]
        head.style = doc.styles["EV Figure Note Head"]
        kind = (blk.block_kind or "figure").replace("_", " ")
        label = {"equation": "Equation description",
                 "table": "Table description"}.get(kind, "Image description")
        head.add_run(f"{label}  ({kind})")

        for line in clean(blk.text).split("\n"):
            if not line.strip():
                continue
            p = cell.add_paragraph(style="EV Figure Note")
            p.add_run(line.strip())
        self._bookmark(head, blk.id)
        self._relation(head, "desc", blk.caption_of or "")
        self.stats["tables"] += 1
        self.stats["figure_notes"] = self.stats.get("figure_notes", 0) + 1
        doc.add_paragraph(style="EV Body")

    # -- runs -------------------------------------------------------------
    def _emit_runs(self, p, text: str, runs: List[Run]) -> None:
        """One add_run per formatting span. Never collapse to a single run,
        that is exactly where bold gets lost."""
        text = clean(text or "")
        if not runs:
            if text:
                p.add_run(text)
            return
        spans = sorted([r for r in runs if r.e > r.s], key=lambda r: r.s)
        pos = 0
        for r in spans:
            s, e = max(0, min(r.s, len(text))), max(0, min(r.e, len(text)))
            if s > pos:
                p.add_run(text[pos:s])
            if e > s:
                run = p.add_run(text[s:e])
                run.bold = r.bold or None
                run.italic = r.italic or None
                run.underline = r.underline or None
                if r.superscript:
                    run.font.superscript = True
                if r.subscript:
                    run.font.subscript = True
                col = readable_color(r.color)
                if col:
                    try:
                        run.font.color.rgb = RGBColor.from_string(col)
                    except ValueError:
                        pass
                pos = e
        if pos < len(text):
            p.add_run(text[pos:])

    # -- equations --------------------------------------------------------
    def _equation(self, doc, blk: Block):
        p = doc.add_paragraph(style="EV Equation")
        self._bookmark(p, blk.id)

        if blk.omml_xml:
            try:
                p._p.append(_parse(blk.omml_xml))
                self.stats["equations"] += 1
                return p
            except Exception:
                blk.flags.append("omml_reuse_failed")

        if blk.latex and not blk.math_unreadable:
            try:
                # a standalone equation paragraph is display maths, and display
                # maths must be wrapped in oMathPara or it renders as nothing
                xml = latex_to_omml(blk.latex, display=not blk.eq_number)
                p._p.append(_parse(xml))
                if blk.eq_number:
                    r = p.add_run("\t" + blk.eq_number)
                    r.font.size = Pt(10)
                self.stats["equations"] += 1
                # the reconstruction is what Word edits; the cut out of the
                # page is what proves it
                if (self.cfg.equation_images_in_docx == "always"
                        and blk.image_ref):
                    pic = doc.add_paragraph(style="EV Equation")
                    self._add_picture(doc, pic, blk, note="as printed")
                    self.stats["equation_images"] += 1
                self._equation_note(doc, blk)
                return p
            except (Unsupported, Exception):
                blk.math_unreadable = True
                blk.flags.append("omml_failed")

        # never publish a wrong formula: fall back to the printed image
        if blk.image_ref and self.cfg.equation_images_in_docx != "never":
            self._add_picture(doc, p, blk, note="equation not verified")
            self.stats["equation_images"] += 1
            self._equation_note(doc, blk)
            return p
        if mathtools.is_chemistry(blk.text):
            for chunk, kind in mathtools.split_chem_runs(clean(blk.text)):
                r = p.add_run(chunk)
                if kind == "sub":
                    r.font.subscript = True
                elif kind == "sup":
                    r.font.superscript = True
            self.stats["paragraphs"] += 1
            return p
        r = p.add_run(clean(blk.text))
        r.italic = True
        self._hidden(p, "[equation not verified]")
        self.stats["paragraphs"] += 1
        return p

    def _equation_note(self, doc, blk: Block) -> None:
        """The formula in words, for a reader who cannot see the symbols."""
        if not (self.cfg.equation_description_box and blk.math_desc):
            return
        note = doc.add_paragraph(style="EV Figure Note")
        r = note.add_run(clean(blk.math_desc))
        r.italic = True
        self.stats["figure_notes"] += 1

    # -- figures ----------------------------------------------------------
    def _figure(self, doc, blk: Block):
        p = doc.add_paragraph()
        p.paragraph_format.alignment = ALIGN.get(
            blk.align, WD_ALIGN_PARAGRAPH.CENTER)
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(2)
        self._bookmark(p, blk.id)
        self._add_picture(doc, p, blk)
        return p

    def _add_picture(self, doc, p, blk: Block, note: str = "") -> None:
        ref = blk.redraw_ref if (self.cfg.redraw and blk.redraw_ref) else blk.image_ref
        if not ref:
            self.ledger.drop(blk.id, blk.page, "empty", "figure with no image file")
            return
        path = ref if os.path.isabs(ref) else os.path.join(self.out_dir, ref)
        if not os.path.exists(path):
            self.ledger.drop(blk.id, blk.page, "empty", f"missing {ref}")
            return
        w = max(8.0, blk.width)
        h = max(8.0, blk.height)
        run = p.add_run()
        try:
            run.add_picture(path, width=Pt(w), height=Pt(h))
        except Exception:
            run.add_picture(path, width=Pt(w))
        self.stats["pictures"] += 1
        if self.cfg.embed_alt_text:
            self._alt_text(run, blk, note)

    def _alt_text(self, run, blk: Block, note: str = "") -> None:
        """The VLM description rides in the picture alt text: invisible to the
        reader, readable by any tool, survives a round trip through Word."""
        parts = []
        if blk.figure:
            if blk.figure.label:
                parts.append(blk.figure.label)
            if blk.figure.desc:
                parts.append(blk.figure.desc)
            if blk.figure.entities:
                parts.append("Parts: " + ", ".join(blk.figure.entities))
            if blk.figure.relationships:
                parts.append("Relations: " + "; ".join(blk.figure.relationships))
            if blk.figure.data_points:
                parts.append("Data: " + "; ".join(blk.figure.data_points))
            if blk.figure.text_in_image:
                parts.append("Text in figure: " + " | ".join(blk.figure.text_in_image))
        if blk.math_desc:
            parts.append(blk.math_desc)
        if blk.latex:
            parts.append(f"LaTeX: {blk.latex}")
        if note:
            parts.append(note)
        parts.append(f"[eduverse:{blk.id}]")
        descr = clean("\n".join(parts))[:8000]
        for docpr in run._r.findall(
                ".//" + qn("wp:inline") + "/" + qn("wp:docPr")):
            docpr.set("descr", descr)
            docpr.set("title", blk.figure.label if blk.figure else blk.id)
        for docpr in run._r.iter():
            if docpr.tag.endswith("}docPr"):
                docpr.set("descr", descr)

    # -- tables -----------------------------------------------------------
    def _table(self, doc, blk: Block, page: Page):
        td = blk.table
        if td is None or td.rows == 0 or td.cols == 0:
            return
        tbl = doc.add_table(rows=td.rows, cols=td.cols)
        tbl.style = "Table Grid"
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        _cell_margins(tbl, 4.0, 3.0)

        usable = page.width_pt - page.margins_pt[0] - page.margins_pt[2]
        widths = _scale_widths(td.col_widths_pt, td.cols, usable)
        _set_table_width(tbl, sum(widths))
        _set_grid(tbl, widths)

        for c in td.cells:
            if c.row >= td.rows or c.col >= td.cols:
                continue
            cell = tbl.cell(c.row, c.col)
            para = cell.paragraphs[0]
            para.style = doc.styles["EV Table Header" if c.is_header
                                    else "EV Table Cell"]
            # a numeric column reads right aligned, everything else left
            if _is_number(c.text) and not c.is_header:
                para.paragraph_format.alignment = ALIGN["right"]
            self._emit_runs(para, c.text, c.runs)
            for nested in c.blocks:                # a figure or equation in a cell
                self._write_block_in_cell(doc, cell, nested)
            _set_cell_width(cell, widths[c.col])
            _valign(cell, "center")
            if c.is_header:
                _shade(cell, self.cfg.table_header_shading)

        # merges
        for c in td.cells:
            if c.row_span <= 1 and c.col_span <= 1:
                continue
            r2 = min(td.rows - 1, c.row + c.row_span - 1)
            c2 = min(td.cols - 1, c.col + c.col_span - 1)
            try:
                tbl.cell(c.row, c.col).merge(tbl.cell(r2, c2))
            except Exception:
                pass

        for ri in range(min(td.header_rows, td.rows)):
            _repeat_header(tbl.rows[ri])

        # draw what the printed table drew, no more
        if not td.has_v_rules and td.has_h_rules:
            _horizontal_only(tbl)
        elif not td.has_v_rules and not td.has_h_rules:
            _no_borders(tbl)
        self._bookmark(tbl.rows[0].cells[0].paragraphs[0], blk.id)
        self.stats["tables"] += 1
        doc.add_paragraph(style="EV Body")

    def _write_block_in_cell(self, doc, cell, blk: Block) -> None:
        p = cell.add_paragraph()
        if blk.type == "figure":
            self._add_picture(doc, p, blk)
        elif blk.type == "equation" and blk.latex and not blk.math_unreadable:
            try:
                p._p.append(_parse(latex_to_omml(blk.latex)))
                self.stats["equations"] += 1
            except Exception:
                p.add_run(clean(blk.text))
        else:
            self._emit_runs(p, blk.text, blk.runs)

    # -- helpers ----------------------------------------------------------
    def _bookmark(self, p, name: str) -> None:
        self._bm += 1
        start = OxmlElement("w:bookmarkStart")
        start.set(qn("w:id"), str(self._bm))
        start.set(qn("w:name"), _bm_name(name))
        end = OxmlElement("w:bookmarkEnd")
        end.set(qn("w:id"), str(self._bm))
        after_ppr(p._p, start)
        p._p.append(end)
        self.stats["bookmarks"] += 1

    def _relation(self, p, kind: str, target: str) -> None:
        """Record which figure this paragraph belongs to.

        As a BOOKMARK, not as text. A hidden run is still in the text stream,
        so it turns up in every copy, every export and every reading tool, and
        the document reads "Figure 1.1 Hot and Cold Objects[caption_of:...]".
        The bookmark says the same thing and cannot be read as words.
        """
        if not target:
            return
        if self.cfg.inline_bind_tokens:
            self._hidden(p, f"[{'caption_of' if kind == 'capof' else 'describes'}"
                            f":{target}]")
            return
        self._bookmark(p, f"{kind}__{target}")

    def _hidden(self, p, text: str) -> None:
        r = p.add_run(text)
        r.font.hidden = True
        r.font.size = Pt(1)


# ---------------------------------------------------------------------------
# low level XML helpers
# ---------------------------------------------------------------------------

NS_M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _parse(xml: str):
    """OMML runs carry w:rPr, so both namespaces must be declared on the root."""
    from lxml import etree
    root_tag = "<m:oMathPara" if xml.startswith("<m:oMathPara") else "<m:oMath"
    add = ""
    if f'xmlns:m="{NS_M}"' not in xml:
        add += f' xmlns:m="{NS_M}"'
    if f'xmlns:w="{NS_W}"' not in xml:
        add += f' xmlns:w="{NS_W}"'
    if add:
        xml = xml.replace(root_tag, root_tag + add, 1)
    return etree.fromstring(xml)


def _bm_name(name: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)
    return ("ev_" + safe)[:40]


def _scale_widths(widths: List[float], ncols: int, usable: float) -> List[float]:
    w = list(widths or [])
    if len(w) < ncols:
        w += [0.0] * (ncols - len(w))
    w = w[:ncols]
    total = sum(x for x in w if x > 0)
    if total <= 0:
        return [usable / ncols] * ncols
    for i, x in enumerate(w):
        if x <= 0:
            w[i] = total / max(1, len([y for y in w if y > 0]))
    total = sum(w)
    scale = usable / total if total > usable else 1.0
    return [max(18.0, x * scale) for x in w]


def _set_table_width(tbl, pts: float) -> None:
    el = OxmlElement("w:tblW")
    el.set(qn("w:w"), str(int(pts * 20)))
    el.set(qn("w:type"), "dxa")
    replace_ordered(tbl._tbl.tblPr, el, TBLPR_ORDER)
    tbl.autofit = False


def _set_grid(tbl, widths: List[float]) -> None:
    grid = tbl._tbl.find(qn("w:tblGrid"))
    if grid is None:
        grid = OxmlElement("w:tblGrid")
        tbl._tbl.insert(1, grid)
    for gc in list(grid):
        grid.remove(gc)
    for w in widths:
        gc = OxmlElement("w:gridCol")
        gc.set(qn("w:w"), str(int(w * 20)))
        grid.append(gc)


def _set_cell_width(cell, pts: float) -> None:
    """Word ignores a width set only on the column, so set it on every cell."""
    el = OxmlElement("w:tcW")
    el.set(qn("w:w"), str(int(pts * 20)))
    el.set(qn("w:type"), "dxa")
    replace_ordered(cell._tc.get_or_add_tcPr(), el, TCPR_ORDER)


def _panel_paragraph(p_el, fill: str, border: str) -> None:
    """Shade a paragraph and rule it on all four sides. Consecutive
    paragraphs with the same rule merge into one box in Word, so an Activity
    panel reads as one set apart block. Neighbouring panels alternate the rule
    colour by one step so Word keeps them as two boxes."""
    ppr = p_el.get_or_add_pPr()
    for old in ppr.findall(qn("w:pBdr")) + ppr.findall(qn("w:shd")):
        ppr.remove(old)
    bdr = OxmlElement("w:pBdr")
    for side in ("top", "left", "bottom", "right"):
        e = OxmlElement(f"w:{side}")
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), "6")
        e.set(qn("w:space"), "4")
        e.set(qn("w:color"), border)
        bdr.append(e)
    insert_ordered(ppr, bdr, PPR_ORDER)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    insert_ordered(ppr, shd, PPR_ORDER)


def _shade(cell, hex_fill: str) -> None:
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")          # never "solid", it renders black
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    replace_ordered(cell._tc.get_or_add_tcPr(), shd, TCPR_ORDER)


def _no_borders(tbl) -> None:
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "none")
        el.set(qn("w:sz"), "0")
        borders.append(el)
    replace_ordered(tbl._tbl.tblPr, borders, TBLPR_ORDER)


def _horizontal_only(tbl) -> None:
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "bottom", "insideH"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:color"), "808080")
        borders.append(el)
    for edge in ("left", "right", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "none")
        borders.append(el)
    replace_ordered(tbl._tbl.tblPr, borders, TBLPR_ORDER)


NUMERIC = re.compile(r"^[\s]*[-\u2212+]?[\d][\d,. ]*%?[\s]*$")


def _is_number(text: str) -> bool:
    return bool(text) and bool(NUMERIC.match(text))


def _valign(cell, where: str) -> None:
    el = OxmlElement("w:vAlign")
    el.set(qn("w:val"), where)
    replace_ordered(cell._tc.get_or_add_tcPr(), el, TCPR_ORDER)


def _cell_margins(tbl, side_pt: float, vert_pt: float) -> None:
    """Without margins a ruled table looks cramped against its borders."""
    mar = OxmlElement("w:tblCellMar")
    for edge, pts in (("top", vert_pt), ("start", side_pt), ("left", side_pt),
                      ("bottom", vert_pt), ("end", side_pt), ("right", side_pt)):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:w"), str(int(pts * 20)))
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    replace_ordered(tbl._tbl.tblPr, mar, TBLPR_ORDER)


def _repeat_header(row) -> None:
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    replace_ordered(row._tr.get_or_add_trPr(), el, TRPR_ORDER)


def write(book: Book, out_dir: str, cfg: Config, ledger: Ledger,
          filename: str = "flow.docx") -> Tuple[str, Dict[str, int]]:
    w = FlowWriter(book, out_dir, cfg, ledger)
    path = os.path.join(out_dir, filename)
    w.write(path)
    return path, w.stats
