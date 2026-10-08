"""Tables.

Three ways a table arrives:

  native   PyMuPDF finds the grid, and the spans inside each cell give us the
           cell text with its bold and italic intact
  scanned  computer vision finds the ruling lines, the OCR model reads the
           region, and the markdown table it returns is mapped onto the grid
  markdown the OCR model returned a pipe table with no ruling lines to confirm

A table is never flattened to tab separated text. Merged cells are detected
from cell geometry, not guessed, and column widths come from the real grid.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .config import Config
from .schema import Block, Run, TableCell, TableData
from .structure import merge_runs
from .textclean import clean

BOLD_FLAG = 1 << 4
ITALIC_FLAG = 1 << 1
BOLD_NAME = re.compile(r"bold|black|heavy|semib|demi", re.I)
ITAL_NAME = re.compile(r"italic|oblique", re.I)


# ---------------------------------------------------------------------------
# Ruling lines
# ---------------------------------------------------------------------------

def page_rules(pg, cfg: Config) -> Tuple[List[Tuple[float, float, float]],
                                         List[Tuple[float, float, float]]]:
    """Return (horizontals, verticals) as (position, start, end) in points.

    A drawn line, a thin filled rectangle and a table border all count.
    """
    h: List[Tuple[float, float, float]] = []
    v: List[Tuple[float, float, float]] = []
    try:
        drawings = pg.get_drawings()
    except Exception:
        return h, v
    for d in drawings:
        r = d.get("rect")
        if r is None:
            continue
        w, ht = r.x1 - r.x0, r.y1 - r.y0
        if ht <= 2.5 and w >= 8:
            h.append(((r.y0 + r.y1) / 2, r.x0, r.x1))
        elif w <= 2.5 and ht >= 8:
            v.append(((r.x0 + r.x1) / 2, r.y0, r.y1))
    return _dedupe(h), _dedupe(v)


def _dedupe(lines, tol: float = 1.5):
    out: List[Tuple[float, float, float]] = []
    for pos, a, b in sorted(lines):
        if out and abs(out[-1][0] - pos) <= tol:
            p, oa, ob = out[-1]
            out[-1] = (p, min(oa, a), max(ob, b))
        else:
            out.append((pos, a, b))
    return out


def rules_in(rect, h_rules, v_rules, cfg: Config) -> Tuple[bool, bool]:
    """Does this region actually have horizontal and vertical rules drawn?"""
    w = rect.x1 - rect.x0
    ht = rect.y1 - rect.y0
    hs = [p for p, a, b in h_rules
          if rect.y0 - 2 <= p <= rect.y1 + 2
          and min(b, rect.x1) - max(a, rect.x0) > w * cfg.table_rule_min_len_frac]
    vs = [p for p, a, b in v_rules
          if rect.x0 - 2 <= p <= rect.x1 + 2
          and min(b, rect.y1) - max(a, rect.y0) > ht * cfg.table_rule_min_len_frac]
    return len(hs) >= 2, len(vs) >= 2


# ---------------------------------------------------------------------------
# Native extraction
# ---------------------------------------------------------------------------

def _spans_of(pg) -> List[Dict]:
    out: List[Dict] = []
    d = pg.get_text("rawdict")
    for blk in d.get("blocks", []):
        if blk.get("type") != 0:
            continue
        for line in blk.get("lines", []):
            for span in line.get("spans", []):
                raw = (span.get("text") if "text" in span else
                       "".join(c.get("c", "") for c in span.get("chars", [])))
                txt = clean(raw or "", keep_breaks=False)
                if not txt.strip():
                    continue
                flags = int(span.get("flags", 0))
                font = span.get("font", "") or ""
                out.append({
                    "text": txt,
                    "bbox": tuple(span["bbox"]),
                    "bold": bool(flags & BOLD_FLAG) or bool(BOLD_NAME.search(font)),
                    "italic": bool(flags & ITALIC_FLAG) or bool(ITAL_NAME.search(font)),
                    "line_y": round(span["bbox"][1], 1),
                })
    return out


def cell_content(spans: Sequence[Dict], box) -> Tuple[str, List[Run]]:
    """Text and formatting runs for one cell, built from the spans inside it.

    This is why a native table keeps its bold: tb.extract() hands back plain
    strings and throws the weight away.
    """
    x0, y0, x1, y1 = box
    # Assign by the span's centre, not by strict containment. A cell value
    # printed a hair wider than its ruled box is normal, and requiring
    # containment silently empties the whole column: the table then reads
    # "metre" as the unit of nothing while the labels leak into the prose.
    inside = [s for s in spans
              if x0 - 1.0 <= (s["bbox"][0] + s["bbox"][2]) / 2 <= x1 + 1.0
              and y0 - 1.0 <= (s["bbox"][1] + s["bbox"][3]) / 2 <= y1 + 1.0]
    if not inside:
        inside = [s for s in spans
                  if _overlap_frac(s["bbox"], box) > 0.55]
    if not inside:
        return "", []
    inside.sort(key=lambda s: (round(s["bbox"][1], 1), s["bbox"][0]))

    parts: List[str] = []
    runs: List[Run] = []
    pos = 0
    last_y: Optional[float] = None
    for s in inside:
        y = round(s["bbox"][1], 1)
        if last_y is not None and abs(y - last_y) > 1.5:
            parts.append(" ")            # a wrapped cell is one value
            pos += 1
        elif parts and not parts[-1].endswith(" ") and not s["text"].startswith(" "):
            parts.append(" ")
            pos += 1
        t = s["text"]
        runs.append(Run(s=pos, e=pos + len(t), bold=s["bold"], italic=s["italic"]))
        parts.append(t)
        pos += len(t)
        last_y = y

    text = "".join(parts).strip()
    trimmed = len("".join(parts)) - len("".join(parts).lstrip())
    if trimmed:
        runs = [Run(s=max(0, r.s - trimmed), e=max(0, r.e - trimmed),
                    bold=r.bold, italic=r.italic) for r in runs]
    return text, merge_runs([r for r in runs if r.e > r.s])


def _overlap_frac(a, b) -> float:
    ix = min(a[2], b[2]) - max(a[0], b[0])
    iy = min(a[3], b[3]) - max(a[1], b[1])
    if ix <= 0 or iy <= 0:
        return 0.0
    area = max(1e-6, (a[2] - a[0]) * (a[3] - a[1]))
    return (ix * iy) / area


def grid_from_cells(cells: Sequence) -> Tuple[List[float], List[float]]:
    """Column and row boundaries from the raw cell rectangles."""
    xs, ys = set(), set()
    for c in cells:
        if not c:
            continue
        xs.add(round(c[0], 1))
        xs.add(round(c[2], 1))
        ys.add(round(c[1], 1))
        ys.add(round(c[3], 1))
    return _cluster(sorted(xs)), _cluster(sorted(ys))


def _cluster(vals: List[float], tol: float = 2.5) -> List[float]:
    out: List[float] = []
    for v in vals:
        if out and v - out[-1] <= tol:
            out[-1] = (out[-1] + v) / 2
        else:
            out.append(v)
    return out


def _index_of(v: float, bounds: List[float], tol: float = 3.0) -> int:
    best, bd = 0, 1e9
    for i, b in enumerate(bounds):
        d = abs(b - v)
        if d < bd:
            best, bd = i, d
    return best if bd <= max(tol, 3.0) else best


def build_native(pg, tb, rect, page_no: int, bid: str, cfg: Config,
                 h_rules, v_rules) -> Optional[Block]:
    """One PyMuPDF table into a TableData with runs, spans and real widths."""
    raw_cells = [c for c in (getattr(tb, "cells", None) or []) if c]
    data = tb.extract() or []
    if not raw_cells and not data:
        return None

    spans = _spans_of(pg)

    if raw_cells:
        xs, ys = grid_from_cells(raw_cells)
        ncols = max(1, len(xs) - 1)
        nrows = max(1, len(ys) - 1)
        cells: List[TableCell] = []
        seen = set()
        for c in raw_cells:
            c0 = _index_of(c[0], xs)
            c1 = _index_of(c[2], xs)
            r0 = _index_of(c[1], ys)
            r1 = _index_of(c[3], ys)
            col_span = max(1, c1 - c0)
            row_span = max(1, r1 - r0)
            if (r0, c0) in seen or r0 >= nrows or c0 >= ncols:
                continue
            seen.add((r0, c0))
            text, runs = cell_content(spans, c)
            cells.append(TableCell(row=r0, col=c0, text=text, runs=runs,
                                   row_span=row_span, col_span=col_span,
                                   bbox_pt=[c[0], c[1], c[2], c[3]]))
        # fill the holes a merge leaves behind so the writer can index safely
        present = {(c.row, c.col) for c in cells}
        covered = set()
        for c in cells:
            for r in range(c.row, c.row + c.row_span):
                for cc in range(c.col, c.col + c.col_span):
                    covered.add((r, cc))
        for r in range(nrows):
            for cc in range(ncols):
                if (r, cc) not in covered and (r, cc) not in present:
                    cells.append(TableCell(row=r, col=cc, text=""))
        widths = [xs[i + 1] - xs[i] for i in range(ncols)]
    else:
        nrows = len(data)
        ncols = max(len(r) for r in data)
        cells = [TableCell(row=ri, col=ci,
                           text=clean("" if (ci >= len(row) or row[ci] is None)
                                      else str(row[ci])).strip())
                 for ri, row in enumerate(data) for ci in range(ncols)]
        widths = [(rect.x1 - rect.x0) / ncols] * ncols

    if raw_cells:
        _recover_empty_cells(cells, spans, xs, ys, cfg)
    cells.sort(key=lambda c: (c.row, c.col))
    filled = sum(1 for c in cells if c.text.strip())
    if filled < cfg.table_min_cells or nrows < 2 or ncols < 2:
        return None
    if filled / max(1, len(cells)) < 0.45:
        return None

    has_h, has_v = rules_in(rect, h_rules, v_rules, cfg)
    header_rows = _header_rows(cells, ncols, getattr(tb, "header", None))
    if raw_cells and (has_h or has_v):
        td_tmp = TableData(rows=nrows, cols=ncols, cells=cells)
        infer_spans(td_tmp, xs, ys, h_rules, v_rules, cfg)
    for c in cells:
        if c.row < header_rows:
            c.is_header = True

    td = TableData(rows=nrows, cols=ncols, cells=cells,
                   col_widths_pt=widths, has_h_rules=has_h, has_v_rules=has_v,
                   header_rows=header_rows)
    _prune(td)
    # pruning can collapse a grid to a single column, and a single column is a
    # sidebar or a list, never a table
    if td.rows < 2 or td.cols < 2:
        return None
    if sum(1 for c in td.cells if c.text.strip()) < cfg.table_min_cells:
        return None
    return Block(id=bid, page=page_no, type="table", bbox_pt=list(rect),
                 source="native_table", table=td)


def infer_spans(td: TableData, xs: List[float], ys: List[float],
                h_rules, v_rules, cfg: Config) -> None:
    """A merged cell is one with no rule drawn between it and its neighbour.

    PyMuPDF does not report merges, so they are read off the ruling lines:
    if the vertical rule that should separate two cells is not drawn and the
    right hand cell is empty, the pair is one cell.
    """
    if len(xs) < 2 or len(ys) < 2:
        return
    grid = {(c.row, c.col): c for c in td.cells}

    def v_rule_at(x: float, y0: float, y1: float) -> bool:
        span = y1 - y0
        return any(abs(p - x) <= 2.5
                   and min(b, y1) - max(a, y0) > span * 0.6
                   for p, a, b in v_rules)

    def h_rule_at(y: float, x0: float, x1: float) -> bool:
        span = x1 - x0
        return any(abs(p - y) <= 2.5
                   and min(b, x1) - max(a, x0) > span * 0.6
                   for p, a, b in h_rules)

    for r in range(td.rows):
        c = 0
        while c < td.cols:
            cell = grid.get((r, c))
            if cell is None or not cell.text.strip():
                c += 1
                continue
            span = 1
            while c + span < td.cols:
                boundary = xs[c + span] if c + span < len(xs) else None
                if boundary is None:
                    break
                nxt = grid.get((r, c + span))
                if nxt is None or nxt.text.strip():
                    break
                if v_rule_at(boundary, ys[r], ys[min(r + 1, len(ys) - 1)]):
                    break
                span += 1
            if span > 1:
                cell.col_span = span
            c += span

    for c in range(td.cols):
        r = 0
        while r < td.rows:
            cell = grid.get((r, c))
            if cell is None or not cell.text.strip():
                r += 1
                continue
            span = 1
            while r + span < td.rows:
                boundary = ys[r + span] if r + span < len(ys) else None
                if boundary is None:
                    break
                nxt = grid.get((r + span, c))
                if nxt is None or nxt.text.strip():
                    break
                if h_rule_at(boundary, xs[c], xs[min(c + 1, len(xs) - 1)]):
                    break
                span += 1
            if span > 1 and cell.col_span == 1:
                cell.row_span = span
            r += span


def _recover_empty_cells(cells, spans, xs, ys, cfg: Config) -> None:
    """Rules 35 and 36: an empty cell with unclaimed text in its column and row
    band is not empty. A table that says "kilogram" is the unit of nothing is
    worse than a table with a gap, because it reads as fact.
    """
    if len(xs) < 2 or len(ys) < 2:
        return
    claimed = set()
    for c in cells:
        for s_ in spans:
            if c.text and s_["text"].strip() and s_["text"] in c.text:
                claimed.add(id(s_))

    for c in cells:
        if c.text.strip():
            continue
        if c.col + 1 >= len(xs) or c.row + 1 >= len(ys):
            continue
        cx0, cx1 = xs[c.col], xs[c.col + 1]
        cy0, cy1 = ys[c.row], ys[c.row + 1]
        # widen sideways only, because a value never moves to another row
        pad = (cx1 - cx0) * cfg.cell_recover_pad_frac
        found = [s_ for s_ in spans if id(s_) not in claimed
                 and cy0 - 1 <= (s_["bbox"][1] + s_["bbox"][3]) / 2 <= cy1 + 1
                 and s_["bbox"][2] > cx0 - pad and s_["bbox"][0] < cx1 + pad
                 and _overlap_frac(s_["bbox"], (cx0 - pad, cy0, cx1 + pad, cy1))
                 > 0.5]
        if not found:
            continue
        found.sort(key=lambda s_: s_["bbox"][0])
        text = " ".join(s_["text"] for s_ in found).strip()
        text = re.sub(r"\s+", " ", text)
        if not text:
            continue
        c.text = text
        c.runs = merge_runs([Run(s=0, e=len(text),
                                 bold=all(s_["bold"] for s_ in found),
                                 italic=all(s_["italic"] for s_ in found))])
        for s_ in found:
            claimed.add(id(s_))


def row_gaps(td: TableData) -> List[int]:
    """Rule 36: rows with some columns filled and others blank."""
    grid = {(c.row, c.col): c.text.strip() for c in td.cells}
    out = []
    for r in range(td.header_rows, td.rows):
        vals = [grid.get((r, c), "") for c in range(td.cols)]
        if any(vals) and not all(vals):
            out.append(r)
    return out


def _header_rows(cells: List[TableCell], ncols: int, tb_header) -> int:
    """A header row is bold, or the extractor already said so. Never guess
    from position alone: plenty of tables start with data."""
    if tb_header is not None and getattr(tb_header, "external", False) is False:
        names = getattr(tb_header, "names", None)
        if names and any((n or "").strip() for n in names):
            return 1
    first = [c for c in cells if c.row == 0 and c.text.strip()]
    if not first:
        return 0
    bold = sum(1 for c in first if c.runs and all(r.bold for r in c.runs))
    return 1 if bold >= max(2, len(first) * 0.6) else 0


def _prune(td: TableData) -> None:
    """Drop rows and columns that are entirely empty, and renumber."""
    live_rows = sorted({c.row for c in td.cells if c.text.strip()}
                       | {c.row for c in td.cells if c.row_span > 1})
    live_cols = sorted({c.col for c in td.cells if c.text.strip()}
                       | {c.col for c in td.cells if c.col_span > 1})
    if not live_rows or not live_cols:
        return
    rmap = {r: i for i, r in enumerate(range(min(live_rows), max(live_rows) + 1))}
    cmap = {c: i for i, c in enumerate(range(min(live_cols), max(live_cols) + 1))}
    kept = []
    for c in td.cells:
        if c.row in rmap and c.col in cmap:
            c.row = rmap[c.row]
            c.col = cmap[c.col]
            kept.append(c)
    td.cells = kept
    td.rows = len(rmap)
    td.cols = len(cmap)
    lo, hi = min(live_cols), max(live_cols)
    if td.col_widths_pt and hi < len(td.col_widths_pt):
        td.col_widths_pt = td.col_widths_pt[lo:hi + 1]


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

def from_markdown(rows: List[List[str]], bid: str, page_no: int, bbox,
                  cfg: Config) -> Optional[Block]:
    rows = [[clean(c).strip() for c in r] for r in rows if any(x.strip() for x in r)]
    if len(rows) < 2:
        return None
    ncols = max(len(r) for r in rows)
    if ncols < 2:
        return None
    cells = [TableCell(row=ri, col=ci,
                       text=(row[ci] if ci < len(row) else ""),
                       is_header=(ri == 0))
             for ri, row in enumerate(rows) for ci in range(ncols)]
    if sum(1 for c in cells if c.text.strip()) < cfg.table_min_cells:
        return None
    width = bbox[2] - bbox[0]
    td = TableData(rows=len(rows), cols=ncols, cells=cells,
                   col_widths_pt=[width / ncols] * ncols,
                   header_rows=1, has_h_rules=True, has_v_rules=True)
    _prune(td)
    if td.rows < 2 or td.cols < 2:
        return None
    return Block(id=bid, page=page_no, type="table", bbox_pt=list(bbox),
                 source="ocr_table", confidence=0.8, table=td)


# ---------------------------------------------------------------------------
# Scanned grids
# ---------------------------------------------------------------------------

def detect_grids(img, cfg: Config) -> List[Tuple[int, int, int, int]]:
    """Find ruled table regions on a page raster by intersecting long
    horizontal and vertical runs of ink."""
    try:
        import cv2
    except ImportError:
        return []
    g = np.array(img.convert("L"))
    h, w = g.shape
    bw = (g < 190).astype(np.uint8)
    if bw.sum() == 0:
        return []

    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, w // 30), 1))
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, h // 40)))
    horiz = cv2.dilate(cv2.erode(bw, hk), hk)
    vert = cv2.dilate(cv2.erode(bw, vk), vk)
    grid = cv2.dilate(cv2.bitwise_and(horiz, vert),
                      cv2.getStructuringElement(cv2.MORPH_RECT, (12, 12)))
    n, _, stats, _ = cv2.connectedComponentsWithStats(
        cv2.bitwise_or(horiz, vert) & cv2.dilate(grid, np.ones((40, 40), np.uint8)),
        8)
    out = []
    for i in range(1, n):
        x, y, bw_, bh, area = stats[i]
        if bw_ < w * 0.2 or bh < 30:
            continue
        if area < 0.002 * w * h:
            continue
        out.append((int(x), int(y), int(x + bw_), int(y + bh)))
    return _merge_boxes(out, 14)


def _merge_boxes(boxes, gap: int):
    boxes = list(boxes)
    changed = True
    while changed:
        changed = False
        out = []
        while boxes:
            b = boxes.pop()
            hit = False
            for i, o in enumerate(out):
                if not (b[2] + gap < o[0] or o[2] + gap < b[0]
                        or b[3] + gap < o[1] or o[3] + gap < b[1]):
                    out[i] = (min(b[0], o[0]), min(b[1], o[1]),
                              max(b[2], o[2]), max(b[3], o[3]))
                    hit = True
                    changed = True
                    break
            if not hit:
                out.append(b)
        boxes = out
    return boxes


def read_grid(client, crop, bid: str, page_no: int, bbox,
              cfg: Config) -> Optional[Block]:
    """Send one ruled region to the OCR model and take the markdown table back."""
    from . import figures as figmod
    from .ocr import parse_markdown
    try:
        md = client.ocr_page(figmod.to_png_bytes(crop, cfg.ocr_max_edge_px))
    except Exception:
        return None
    for ml in parse_markdown(md):
        if ml.kind == "table" and ml.rows_data:
            return from_markdown(ml.rows_data, bid, page_no, bbox, cfg)
    return None


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

def absorbed_ids(page_blocks, rect, td: Optional[TableData] = None,
                 tol: float = 6.0) -> List[str]:
    """Rule 38: text now inside the table must be gone from the prose.

    Two ways in: the block sits inside the table's area, or its words are the
    words of a row. The second catches a row the extractor rebuilt from spans
    whose block bbox pokes a little outside the ruled box.
    """
    rows = set()
    if td is not None:
        grid: Dict[int, List[str]] = {}
        for c in td.cells:
            grid.setdefault(c.row, []).append(c.text.strip())
        for r, vals in grid.items():
            joined = " ".join(v for v in vals if v)
            if joined:
                rows.add(_key(joined))

    out = []
    for b in page_blocks:
        if b.type not in ("paragraph", "heading", "list_item", "equation"):
            continue
        inside = (b.bbox_pt[0] >= rect.x0 - tol and b.bbox_pt[2] <= rect.x1 + tol
                  and b.bbox_pt[1] >= rect.y0 - tol
                  and b.bbox_pt[3] <= rect.y1 + tol)
        overlap = _overlap_frac(tuple(b.bbox_pt),
                                (rect.x0, rect.y0, rect.x1, rect.y1)) > 0.7
        if inside or overlap or (_key(b.text) in rows and _key(b.text)):
            out.append(b.id)
    return out


def _key(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def summary(td: TableData) -> str:
    return (f"{td.rows}x{td.cols}, {sum(1 for c in td.cells if c.text.strip())} "
            f"filled, {'ruled' if td.has_v_rules else 'unruled'}, "
            f"{td.header_rows} header row(s)")
