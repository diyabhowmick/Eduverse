"""layout.docx, the positional output.

Every block sits in a frame anchored to its exact bbox, so the page looks like
the printed page. It is not comfortably editable, which is why flow.docx is the
default and this is opt in.
"""

from __future__ import annotations

import os
from typing import Dict, List, Tuple

from docx import Document
from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

from ..config import Config
from ..ledger import Ledger
from ..omml import latex_to_omml
from ..schema import Block, Book, Page
from . import template
from .flow_docx import FlowWriter, _parse, _set_cell_width, _set_table_width
from .ooxml import PPR_ORDER, insert_ordered

EMU_PER_PT = 12700


class LayoutWriter(FlowWriter):
    def write(self, path: str) -> str:
        tpl = template.ensure(self.out_dir, self.cfg)
        doc = Document(tpl)
        self._apply_page_setup(doc, self.book.pages[0])
        for pi, page in enumerate(self.book.pages):
            if pi:
                doc.add_section()
                self._apply_page_setup(doc, page)
            for blk in page.blocks:
                if blk.type == "page_furniture":
                    continue
                if blk.type == "figure":
                    self._anchored_picture(doc, blk, page)
                elif blk.type == "table":
                    self._table(doc, blk, page)
                else:
                    self._framed_text(doc, blk, page)
            if pi < len(self.book.pages) - 1:
                doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        doc.save(path)
        return path

    def _framed_text(self, doc, blk: Block, page: Page):
        p = doc.add_paragraph(style=self._style_name(blk))
        _frame(p, blk, page)
        if blk.type == "equation" and blk.latex and not blk.math_unreadable:
            try:
                p._p.append(_parse(latex_to_omml(blk.latex)))
                self.stats["equations"] += 1
                return p
            except Exception:
                pass
        self._emit_runs(p, blk.text, blk.runs)
        self.stats["paragraphs"] += 1
        return p

    def _anchored_picture(self, doc, blk: Block, page: Page):
        p = doc.add_paragraph()
        _frame(p, blk, page)
        self._add_picture(doc, p, blk)
        return p


def _frame(p, blk: Block, page: Page) -> None:
    """w:framePr places the paragraph at an absolute position on the page."""
    pPr = p._p.get_or_add_pPr()
    fr = OxmlElement("w:framePr")
    fr.set(qn("w:w"), str(int(max(20.0, blk.width) * 20)))
    fr.set(qn("w:h"), str(int(max(10.0, blk.height) * 20)))
    fr.set(qn("w:hRule"), "atLeast")
    fr.set(qn("w:x"), str(int(blk.x0 * 20)))
    fr.set(qn("w:y"), str(int(blk.y0 * 20)))
    fr.set(qn("w:hAnchor"), "page")
    fr.set(qn("w:vAnchor"), "page")
    fr.set(qn("w:wrap"), "none")
    fr.set(qn("w:xAlign"), "left")
    insert_ordered(pPr, fr, PPR_ORDER)


def write(book: Book, out_dir: str, cfg: Config, ledger: Ledger,
          filename: str = "layout.docx") -> Tuple[str, Dict[str, int]]:
    w = LayoutWriter(book, out_dir, cfg, ledger)
    path = os.path.join(out_dir, filename)
    w.write(path)
    return path, w.stats
