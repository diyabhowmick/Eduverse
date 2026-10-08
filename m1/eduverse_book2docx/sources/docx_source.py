"""DOCX input. The most accurate path: styles, bold and image sizes are all
declared in the file, so nothing is inferred and OCR never runs.
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Dict, List, Optional

from docx import Document
from docx.shared import Emu
from docx.table import Table as DxTable
from docx.text.paragraph import Paragraph as DxPara

from ..config import Config
from ..ledger import Ledger
from ..mathtools import prepare, find_math_spans
from ..schema import (Block, Book, FigureMeta, Page, Run, TableCell, TableData)
from ..textclean import clean

EMU_PER_PT = 12700
HEADING_RE = re.compile(r"(?:heading|^ev h)\s*(\d)", re.I)
NS_M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
NS_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
NS_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def _pt(emu) -> float:
    return float(emu) / EMU_PER_PT if emu else 0.0


def _iter_body(doc):
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag == f"{NS_W}p":
            yield DxPara(child, doc)
        elif child.tag == f"{NS_W}tbl":
            yield DxTable(child, doc)


def extract(path: str, out_dir: str, cfg: Config, ledger: Ledger) -> Book:
    doc = Document(path)
    sec = doc.sections[0]
    pw, ph = _pt(sec.page_width), _pt(sec.page_height)
    margins = [_pt(sec.left_margin), _pt(sec.top_margin),
               _pt(sec.right_margin), _pt(sec.bottom_margin)]

    fig_dir = os.path.join(out_dir, "figures")
    os.makedirs(fig_dir, exist_ok=True)

    page = Page(page=1, width_pt=pw or 595.3, height_pt=ph or 841.9,
                route="docx", margins_pt=margins)
    book = Book(book_id=_file_id(path), source_file=os.path.basename(path),
                pages=[page])

    y = margins[1]
    n = 0
    image_parts = _image_parts(doc)

    for item in _iter_body(doc):
        if isinstance(item, DxTable):
            n += 1
            ledger.detect()
            blk = _note_block(item, n, y, pw, margins) \
                or _table_block(item, n, y, pw, margins)
            page.blocks.append(blk)
            ledger.emit()
            y += 14 * max(1, len(item.rows))
            continue

        n += 1
        ledger.detect()
        blk = _para_block(item, n, y, pw, margins, doc, fig_dir, image_parts, cfg)
        if blk is None:
            ledger.drop(f"d{n:04d}", 1, "empty", "empty paragraph")
            y += 12
            continue
        page.blocks.append(blk)
        ledger.emit()
        y += max(14.0, blk.height)

    # a docx has no printed page height, so the synthetic canvas grows to hold
    # every block: a bbox must never fall outside its page
    lowest = max((b.y1 for b in page.blocks), default=y)
    page.height_pt = max(page.height_pt, lowest + margins[3], y + margins[3])
    for i, b in enumerate(page.blocks):
        b.order = i
    book.detected = {"format": "docx", "pages": 1,
                     "language": _guess_lang(page.blocks)}
    return book


def _para_block(p, n, y, pw, margins, doc, fig_dir, image_parts, cfg):
    bid = f"d{n:04d}"
    x0, x1 = margins[0], pw - margins[2]
    text = clean(p.text or "", keep_breaks=False)

    # inline images
    blips = p._p.findall(f".//{NS_A}blip")
    if blips:
        drawing = p._p.find(f".//{NS_W}drawing")
        cx = cy = 0
        if drawing is not None:
            ext = drawing.find(f".//{NS_A}ext")
            if ext is not None:
                cx = int(ext.get("cx", 0))
                cy = int(ext.get("cy", 0))
        rid = blips[0].get(f"{{http://schemas.openxmlformats.org/"
                           f"officeDocument/2006/relationships}}embed")
        data = image_parts.get(rid)
        w_pt = _pt(cx) or 200.0
        h_pt = _pt(cy) or 150.0
        usable = max(72.0, (pw - margins[0] - margins[2]))
        if w_pt > usable:                 # never let a picture overflow the page
            h_pt *= usable / w_pt
            w_pt = usable
        ref = None
        px_w = px_h = None
        if data:
            ext_name = _sniff_ext(data)
            ref = os.path.join("figures", f"{bid}_fig.{ext_name}")
            with open(os.path.join(fig_dir, os.path.basename(ref)), "wb") as fh:
                fh.write(data)
            px_w, px_h = _png_size(data)
        alt = _alt_text(p._p)
        return Block(id=bid, page=1, type="figure",
                     bbox_pt=[x0, y, x0 + w_pt, y + h_pt],
                     image_ref=ref, px_w=px_w, px_h=px_h,
                     source="docx_style",
                     figure=FigureMeta(fig_kind="photo", desc=alt or "",
                                       label=""))

    # a Word equation already present in the input: keep the OMML verbatim
    omath = p._p.find(f".//{NS_M}oMath")
    if omath is not None:
        from lxml import etree
        raw = etree.tostring(omath, encoding="unicode")
        return Block(id=bid, page=1, type="equation",
                     bbox_pt=[x0, y, x1, y + 18], text=text,
                     omml_xml=raw, display_math=True, source="docx_style")

    if not text.strip():
        return None

    style = (p.style.name if p.style is not None else "") or ""
    if style == "EV Note":            # our own page marker, not book content
        return None
    runs = _runs_from_para(p)

    # maths
    spans = find_math_spans(text)
    if spans and len(spans) == 1 and spans[0][0] == 0 and spans[0][1] >= len(text.strip()):
        latex, why = prepare(spans[0][2])
        blk = Block(id=bid, page=1, type="equation",
                    bbox_pt=[x0, y, x1, y + 18], text=text,
                    latex=latex, math_unreadable=latex is None,
                    display_math=spans[0][3], source="docx_style")
        if latex is None:
            blk.flags.append(f"math:{why}")
        return blk

    blk = Block(id=bid, page=1, bbox_pt=[x0, y, x1, y + 14], text=text,
                runs=runs, source="docx_style", type="paragraph")

    m = HEADING_RE.search(style)
    outline = _outline_level(p)
    if style.lower().startswith(("title", "ev title")):
        blk.type, blk.level = "heading", 1
    elif m:
        blk.type, blk.level = "heading", max(1, min(4, int(m.group(1))))
    elif outline is not None and outline <= 4:
        blk.type, blk.level = "heading", max(1, min(4, outline + 1))
    elif "caption" in style.lower():
        blk.type = "caption"
    elif "list" in style.lower():
        blk.type = "list_item"
        blk.block_kind = "number" if "number" in style.lower() else "bullet"
        blk.indent_level = _list_level(p)
    align = p.paragraph_format.alignment
    if align is not None:
        blk.align = {0: "left", 1: "center", 2: "right", 3: "justify"}.get(
            int(align), "left")
    ind = p.paragraph_format.left_indent
    if ind:
        blk.indent_level = max(blk.indent_level, int(_pt(ind) // 18))
    blk.bbox_pt[3] = y + 14 * max(1, len(text) // 90 + 1)
    return blk


def _runs_from_para(p) -> List[Run]:
    runs: List[Run] = []
    pos = 0
    for r in p.runs:
        t = r.text or ""
        if not t:
            continue
        color = None
        try:
            if r.font.color is not None and r.font.color.rgb is not None:
                color = str(r.font.color.rgb)
        except (AttributeError, ValueError):
            color = None
        runs.append(Run(s=pos, e=pos + len(t),
                        bold=bool(r.bold), italic=bool(r.italic),
                        underline=bool(r.underline),
                        superscript=bool(getattr(r.font, "superscript", False)),
                        subscript=bool(getattr(r.font, "subscript", False)),
                        color=color))
        pos += len(t)
    return [r for r in runs if r.styled()]


DESCRIBES_RE = re.compile(r"\[describes:([^\]]+)\]")
# the relation now travels as a bookmark rather than as hidden text, so the
# round trip reads it back from the XML instead of from the words
BM_DESC_RE = re.compile(r"ev_desc__(\w+)")
BM_CAPOF_RE = re.compile(r"ev_capof__(\w+)")


def _bookmark_target(el, rx) -> Optional[str]:
    try:
        xml = el.xml
    except Exception:
        return None
    m = rx.search(xml or "")
    return m.group(1) if m else None


def _note_block(tbl: DxTable, n: int, y: float, pw: float,
                margins: List[float]) -> Optional[Block]:
    """A description box we wrote earlier is a note, not a table. Without this
    a round trip turns every box into a one cell table."""
    if len(tbl.rows) != 1 or len(tbl.columns) != 1:
        return None
    cell = tbl.rows[0].cells[0]
    paras = cell.paragraphs
    if not paras:
        return None
    joined = "\n".join(p.text for p in paras)
    m = DESCRIBES_RE.search(joined)
    target = m.group(1) if m else _bookmark_target(tbl._tbl, BM_DESC_RE)
    if not target:
        return None
    head = paras[0].text
    kind = "figure"
    if "(" in head and ")" in head:
        kind = head[head.rfind("(") + 1: head.rfind(")")].strip() or "figure"
    body = "\n".join(p.text for p in paras[1:] if p.text.strip())
    body = DESCRIBES_RE.sub("", body).strip()
    return Block(id=f"d{n:04d}", page=1, type="figure_note",
                 bbox_pt=[margins[0], y, pw - margins[2], y + 12],
                 text=body, caption_of=target, block_kind=kind,
                 source="docx_style")


def _table_block(tbl: DxTable, n: int, y: float, pw: float,
                 margins: List[float]) -> Block:
    bid = f"d{n:04d}"
    nrows = len(tbl.rows)
    ncols = len(tbl.columns)
    cells: List[TableCell] = []
    seen = set()
    for ri, row in enumerate(tbl.rows):
        for ci, cell in enumerate(row.cells):
            key = id(cell._tc)
            if key in seen:
                continue
            seen.add(key)
            rs, cs = _span(cell, tbl, ri, ci)
            text = clean("\n".join(par.text for par in cell.paragraphs)).strip()
            runs: List[Run] = []
            off = 0
            for par in cell.paragraphs:
                for r in _runs_from_para(par):
                    runs.append(Run(s=r.s + off, e=r.e + off, bold=r.bold,
                                    italic=r.italic, underline=r.underline,
                                    color=r.color))
                off += len(par.text) + 1
            cells.append(TableCell(row=ri, col=ci, text=text, runs=runs,
                                   row_span=rs, col_span=cs,
                                   is_header=(ri == 0)))
    widths = []
    for col in tbl.columns:
        try:
            widths.append(_pt(col.width) or 0.0)
        except (AttributeError, TypeError):
            widths.append(0.0)
    if not any(widths):
        usable = pw - margins[0] - margins[2]
        widths = [usable / max(ncols, 1)] * max(ncols, 1)
    return Block(id=bid, page=1, type="table",
                 bbox_pt=[margins[0], y, pw - margins[2], y + 14 * nrows],
                 source="docx_style",
                 table=TableData(rows=nrows, cols=ncols, cells=cells,
                                 col_widths_pt=widths, header_rows=1))


def _span(cell, tbl, ri, ci):
    tc = cell._tc
    grid = tc.find(f"{NS_W}tcPr/{NS_W}gridSpan")
    cs = int(grid.get(f"{NS_W}val")) if grid is not None else 1
    vm = tc.find(f"{NS_W}tcPr/{NS_W}vMerge")
    rs = 1
    if vm is not None and vm.get(f"{NS_W}val") == "restart":
        rs = 1
        for r2 in range(ri + 1, len(tbl.rows)):
            try:
                nxt = tbl.rows[r2].cells[ci]._tc
            except IndexError:
                break
            v2 = nxt.find(f"{NS_W}tcPr/{NS_W}vMerge")
            if v2 is not None and v2.get(f"{NS_W}val") != "restart":
                rs += 1
            else:
                break
    return rs, cs


def _outline_level(p):
    """A custom heading style is still a heading if it declares an outline
    level, which is exactly how it reaches the table of contents."""
    style = p.style
    while style is not None:
        ppr = style.element.find(f"{NS_W}pPr")
        if ppr is not None:
            el = ppr.find(f"{NS_W}outlineLvl")
            if el is not None:
                try:
                    return int(el.get(f"{NS_W}val"))
                except (TypeError, ValueError):
                    return None
        style = getattr(style, "base_style", None)
    return None


def _list_level(p) -> int:
    numpr = p._p.find(f"{NS_W}pPr/{NS_W}numPr/{NS_W}ilvl")
    if numpr is not None:
        try:
            return int(numpr.get(f"{NS_W}val"))
        except (TypeError, ValueError):
            return 0
    return 0


def _alt_text(p_el) -> str:
    for tag in (f".//{{http://schemas.openxmlformats.org/drawingml/2006/"
                f"wordprocessingDrawing}}docPr",):
        el = p_el.find(tag)
        if el is not None:
            return el.get("descr") or el.get("name") or ""
    dp = p_el.find(".//{http://schemas.openxmlformats.org/drawingml/2006/"
                   "wordprocessingDrawing}docPr")
    if dp is not None:
        return dp.get("descr") or ""
    return ""


def _image_parts(doc) -> Dict[str, bytes]:
    out = {}
    for rid, rel in doc.part.rels.items():
        if "image" in rel.reltype:
            try:
                out[rid] = rel.target_part.blob
            except (AttributeError, ValueError):
                continue
    return out


def _sniff_ext(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:2] == b"\xff\xd8":
        return "jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return "png"


def _png_size(data: bytes):
    try:
        from PIL import Image
        import io
        with Image.open(io.BytesIO(data)) as im:
            return im.size
    except Exception:
        return None, None


def _file_id(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()[:24]


def _guess_lang(blocks) -> str:
    text = " ".join(b.text for b in blocks[:60])
    if re.search(r"[\u0b80-\u0bff]", text):
        return "ta"
    if re.search(r"[\u0900-\u097f]", text):
        return "hi"
    return "en"
