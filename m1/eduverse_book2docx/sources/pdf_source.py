"""PDF input. One of three routes per page: native, hybrid, scanned.

Geometry always comes from PyMuPDF or from CV. The OCR model supplies text and
nothing else.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF
from PIL import Image

from .. import fractions as fracmod
from .. import figures as figmod
from .. import layout as laymod
from .. import lines as linemod
from .. import ocr as ocrmod
from .. import tables as tablemod
from ..config import Config
from ..ledger import Ledger
from .. import mathtools
from ..mathtools import find_math_spans, looks_like_formula, prepare
from ..ollama_client import OllamaClient
from ..schema import (Block, Book, FigureMeta, Page, Run, TableCell, TableData)
from ..structure import SizeProfile, is_numbered_caption, merge_runs
from ..textclean import broken_ratio, clean, font_family

BOLD_FLAG = 1 << 4
ITALIC_FLAG = 1 << 1
SUPER_FLAG = 1
BOLD_NAME = re.compile(r"bold|black|heavy|semib|demi", re.I)
ITAL_NAME = re.compile(r"italic|oblique", re.I)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def extract(path: str, out_dir: str, cfg: Config, ledger: Ledger,
            client: OllamaClient, progress=None) -> Book:
    doc = fitz.open(path)
    fig_dir = os.path.join(out_dir, "figures")
    page_dir = os.path.join(out_dir, "pages")
    os.makedirs(fig_dir, exist_ok=True)
    os.makedirs(page_dir, exist_ok=True)

    book = Book(book_id=_file_id(path), source_file=os.path.basename(path))
    profile = SizeProfile(cfg)

    # pass 1: geometry and size histogram, no model calls
    raw_pages: List[Dict] = []
    for pno in range(doc.page_count):
        pg = doc[pno]
        info = _scan_page(pg, cfg)
        if _is_front_matter(info, pno, doc.page_count, cfg):
            info["front_matter"] = True
            profile.skipped_pages += 1
        else:
            for size, chars in info["sizes"]:
                profile.observe(size, chars, pno + 1)
            for fam, chars in info.get("fonts", {}).items():
                profile.observe_font(fam, chars)
        raw_pages.append(info)
        if progress:
            progress("scan", pno + 1, doc.page_count)
    profile.finalise()

    # pass 2: build blocks
    for pno in range(doc.page_count):
        pg = doc[pno]
        info = raw_pages[pno]
        page = Page(page=pno + 1, width_pt=pg.rect.width, height_pt=pg.rect.height,
                    route=info["route"], rotation=pg.rotation,
                    margins_pt=info["margins"])
        if info["route"] == "scanned" or cfg.page_dpi:
            raster = _raster(pg, cfg.page_dpi)
            rpath = os.path.join(page_dir, f"p{pno + 1:03d}.png")
            raster.save(rpath, "PNG", optimize=True)
            page.raster_ref = f"pages/p{pno + 1:03d}.png"
        else:
            raster = None

        if info["route"] in ("native", "hybrid"):
            _build_native(pg, page, info, cfg, ledger, profile)
        # The reviewer's compare view stays at full resolution — it is drawn on
        # a screen and costs nothing. The model gets a smaller page.
        _ocr_dpi = getattr(cfg, "ocr_dpi", 0) or cfg.page_dpi
        model_raster = raster if (raster is None or _ocr_dpi >= cfg.page_dpi) \
            else _raster(pg, _ocr_dpi)

        if info["route"] in ("hybrid", "scanned"):
            _build_scanned(pg, page, model_raster, cfg, ledger, client,
                           only_gaps=(info["route"] == "hybrid"))

        _rejoin_fractions(pg, page, cfg, ledger)
        _build_tables(pg, page, cfg, ledger, raster, client)
        _build_figures(pg, page, raster, info, cfg, ledger, client, fig_dir)
        book.stats.setdefault("furniture", []).extend(info.get("furniture", []))
        book.pages.append(page)
        if progress:
            progress("build", pno + 1, doc.page_count)

    book.detected = _detect(book, profile, doc)
    book.stats["size_profile"] = profile.summary()
    doc.close()
    return book


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def _scan_page(pg, cfg: Config) -> Dict:
    d = pg.get_text("rawdict")
    chars = 0
    sizes: List[Tuple[float, int]] = []
    fonts: Dict[str, int] = {}
    text_rects: List[fitz.Rect] = []
    raw_all = []
    for blk in d.get("blocks", []):
        if blk.get("type") != 0:
            continue
        for line in blk.get("lines", []):
            for span in line.get("spans", []):
                raw = (span.get("text") if "text" in span else
                       "".join(c.get("c", "") for c in span.get("chars", [])))
                raw_all.append(raw or "")
                n = len(_span_text(span))
                if n:
                    chars += n
                    sizes.append((float(span.get("size", 0)), n))
                    fam = font_family(span.get("font", ""))
                    if fam:
                        fonts[fam] = fonts.get(fam, 0) + n
                    text_rects.append(fitz.Rect(span["bbox"]))
    corrupt = broken_ratio("".join(raw_all))
    area = pg.rect.width * pg.rect.height
    text_area = sum(r.get_area() for r in text_rects)
    frac = (text_area / area) if area else 0.0

    if corrupt >= cfg.corrupt_text_ratio:
        # the text layer exists but is unusable, so read the page instead of
        # publishing garbage
        route = "scanned"
    elif chars >= cfg.native_min_chars and frac >= cfg.native_min_text_area:
        route = "native"
    elif chars >= cfg.hybrid_min_chars:
        route = "hybrid"
    else:
        route = "scanned"

    if text_rects:
        x0 = min(r.x0 for r in text_rects)
        y0 = min(r.y0 for r in text_rects)
        x1 = max(r.x1 for r in text_rects)
        y1 = max(r.y1 for r in text_rects)
        margins = [max(0.0, x0), max(0.0, y0),
                   max(0.0, pg.rect.width - x1), max(0.0, pg.rect.height - y1)]
    else:
        margins = [56.0, 56.0, 56.0, 56.0]

    return {"route": route, "chars": chars, "sizes": sizes, "fonts": fonts,
            "corrupt": round(corrupt, 3),
            "margins": margins,
            "text_rects": [tuple(r) for r in text_rects]}


def _is_front_matter(info: Dict, pno: int, total: int, cfg: Config) -> bool:
    """Rule 21: a cover, a copyright page and a contents page use display type
    that has nothing to do with the heading scale of the book."""
    if pno >= min(cfg.front_matter_max_pages, max(1, total // 4)):
        return False
    text = " ".join(t for t, _ in
                    [(str(x), 0) for x in info.get("furniture", [])]) or ""
    if info["chars"] < cfg.native_min_chars:
        return True                    # a title page carries almost no text
    sizes = [s for s, _c in info["sizes"]]
    if not sizes:
        return True
    big = sum(c for s, c in info["sizes"] if s >= 20)
    return big > info["chars"] * 0.25



    pix = pg.get_pixmap(dpi=dpi, alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


# ---------------------------------------------------------------------------
# Native text
# ---------------------------------------------------------------------------

def _span_text(span) -> str:
    """Length preserving clean: run offsets are indexes into this string."""
    if "text" in span:
        raw = span["text"]
    else:
        raw = "".join(c.get("c", "") for c in span.get("chars", []))
    return clean(raw, keep_breaks=False)


def _raster(pg, dpi: int) -> Image.Image:
    pix = pg.get_pixmap(dpi=dpi, alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def _build_native(pg, page: Page, info: Dict, cfg: Config, ledger: Ledger,
                  profile: SizeProfile) -> None:
    """Layout first, then read.

    Lines are placed into bands, columns and boxes before anything is grouped,
    so a two column page is never read straight across and a panel is never
    cut into by the text beside it.
    """
    from ..structure import classify_text_block

    raw = linemod.read_lines(pg.get_text("rawdict"))
    if not raw:
        return
    if cfg.fold_fractions_at_span_level and cfg.rejoin_stacked_fractions:
        try:
            h_rules, _v = tablemod.page_rules(pg, cfg)
        except Exception:
            h_rules = []
        raw, _folded = linemod.fold_fraction_lines(raw, h_rules, cfg)
    boxes = [l.bbox for l in raw]
    try:
        drawings = pg.get_drawings()
    except Exception:
        drawings = []
    lay = laymod.analyse(boxes, tuple(pg.rect), page.margins_pt, drawings, cfg)

    # A row that carries both columns arrives spliced. Cut it at the gutter the
    # layout just found, then read the layout again from the cut lines.
    gutters = laymod.gutters_of(lay)
    if gutters:
        split = linemod.split_at_gutters(raw, gutters)
        if len(split) != len(raw):
            raw = split
            boxes = [l.bbox for l in raw]
            lay = laymod.analyse(boxes, tuple(pg.rect), page.margins_pt,
                                 drawings, cfg)
    page.columns = lay.max_columns()
    page.layout_confidence = round(lay.confidence, 3)
    page.layout_notes = list(lay.notes)
    page.boxes_pt = [list(b.rect) for b in lay.boxes if b.kind != "badge"]

    groups = linemod.group_lines(raw, lay, pg.rect.width, cfg)
    if cfg.pair_label_rows:
        groups = linemod.pair_label_rows(groups)
    groups = linemod.order_groups(groups, lay)

    n = 0
    for g in groups:
        n += 1
        ledger.detect()
        text, runs, max_size, bold_frac, color = _group_text(g)
        bid = f"p{page.page:03d}_b{n:03d}"
        if not text.strip():
            ledger.drop(bid, page.page, "empty")
            continue
        bbox = list(g.bbox())
        b = Block(id=bid, page=page.page, type="paragraph", bbox_pt=bbox,
                  text=text, runs=merge_runs(runs), source="native_span")
        b.column = g.column
        b.font_size = round(max_size, 2) if max_size else None
        if g.box >= 0:
            b.block_kind = "panel"
            b.flags.append("in_panel")
        if g.is_title:
            b.flags.append("box_title")
        classify_text_block(b, page, profile, cfg, max_size,
                            bold_frac > 0.6, color)
        if g.is_title and b.type == "paragraph":
            b.type = "heading"
            b.level = min(3, len(profile.levels) or 3)
        if b.type == "page_furniture":
            # flags may already hold "in_panel" and the like, so pick the
            # furniture flag rather than whatever landed first
            why = next((f for f in b.flags if f.startswith("furniture_")),
                       "furniture_header")
            ledger.drop(b.id, page.page, why,
                        text[:60], b.bbox_pt)
            info.setdefault("furniture", []).append(text[:120])
            continue
        _maybe_equation(b, cfg)
        page.blocks.append(b)
        ledger.emit()


def _group_text(g) -> Tuple[str, List[Run], float, float, Optional[str]]:
    parts: List[str] = []
    runs: List[Run] = []
    pos = 0
    max_size = 0.0
    bold_chars = 0
    total = 0
    colors: Dict[str, int] = {}
    for li, line in enumerate(g.lines):
        if li:
            parts.append(" ")
            pos += 1
        for r in line.runs:
            runs.append(Run(s=r.s + pos, e=r.e + pos, bold=r.bold,
                            italic=r.italic, superscript=r.superscript,
                            color=r.color, font=r.font))
        parts.append(line.text)
        pos += len(line.text)
        total += len(line.text)
        max_size = max(max_size, line.max_size)
        bold_chars += int(line.bold_frac * len(line.text))
        if line.color:
            colors[line.color] = colors.get(line.color, 0) + len(line.text)
    text = "".join(parts).strip()
    lead = len("".join(parts)) - len("".join(parts).lstrip())
    if lead:
        runs = [Run(s=max(0, r.s - lead), e=max(0, r.e - lead), bold=r.bold,
                    italic=r.italic, superscript=r.superscript, color=r.color,
                    font=r.font) for r in runs]
    dominant = max(colors, key=colors.get) if colors else None
    if dominant and colors[dominant] < total * 0.6:
        dominant = None
    return (text, runs, max_size,
            (bold_chars / total) if total else 0.0, dominant)


def _union(boxes):
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)
    return (x0, y0, x1, y1)


def _maybe_equation(b: Block, cfg: Config) -> None:
    spans = find_math_spans(b.text)
    whole = spans and spans[0][0] == 0 and spans[0][1] >= len(b.text.strip())
    if whole:
        latex, why = prepare(spans[0][2])
        b.type = "equation"
        b.display_math = spans[0][3]
    elif b.type == "paragraph" and looks_like_formula(b.text):
        latex, why = prepare(b.text)
        b.type = "equation"
        b.display_math = True
    else:
        return
    b.level = None
    b.latex = latex
    b.latex_source = "text_layer" if latex else None
    b.math_unreadable = latex is None
    if latex is None:
        b.flags.append(f"math:{why}")


# ---------------------------------------------------------------------------
# Scanned text
# ---------------------------------------------------------------------------

def _build_scanned(pg, page: Page, raster: Optional[Image.Image], cfg: Config,
                   ledger: Ledger, client: OllamaClient,
                   only_gaps: bool = False) -> None:
    if raster is None:
        return
    scale = raster.width / page.width_pt if page.width_pt else 1.0

    exclude = []
    if only_gaps:
        for b in page.blocks:
            exclude.append(tuple(int(v * scale) for v in b.bbox_pt))

    boxes = ocrmod.line_boxes(raster, exclude_px=exclude)
    if not boxes:
        return

    try:
        md = client.ocr_page(figmod.to_png_bytes(raster, cfg.ocr_max_edge_px))
    except Exception as exc:
        ledger.detect()
        ledger.drop(f"p{page.page:03d}_ocr", page.page, "ocr_empty", str(exc)[:120])
        return
    md_lines = ocrmod.parse_markdown(md, cfg)
    if not md_lines:
        ledger.detect()
        ledger.drop(f"p{page.page:03d}_ocr", page.page, "ocr_empty",
                    "model returned nothing")
        return

    median = ocrmod.page_ink_median(raster, boxes)
    pairs = ocrmod.align(md_lines, boxes)
    n = len(page.blocks)
    for ml, box in pairs:
        if ml.kind == "figure":
            continue
        n += 1
        ledger.detect()
        bid = f"p{page.page:03d}_o{n:03d}"
        if box is None:
            ledger.drop(bid, page.page, "outside_page", "no box for OCR line")
            continue
        bbox = [box[0] / scale, box[1] / scale, box[2] / scale, box[3] / scale]
        if ml.kind == "table":
            blk = _md_table_block(ml, bid, page, bbox, cfg)
            if blk is None:
                ledger.drop(bid, page.page, "unsupported",
                            "markdown table too sparse")
                continue
        else:
            runs = list(ml.runs)
            if not runs:
                runs = ocrmod.bold_runs_from_ink(raster, box, ml.text, median, cfg)
            blk = Block(id=bid, page=page.page, type="paragraph", bbox_pt=bbox,
                        text=ml.text, runs=merge_runs(runs), source="ocr",
                        confidence=0.85)
            if ml.kind == "heading":
                blk.type, blk.level = "heading", ml.level or 2
            elif ml.kind == "list":
                blk.type = "list_item"
                blk.block_kind = "bullet"
            elif ml.kind == "equation":
                latex, why = prepare(ml.text)
                blk.type = "equation"
                blk.latex = latex
                blk.display_math = True
                blk.math_unreadable = latex is None
                if latex is None:
                    blk.flags.append(f"math:{why}")
            else:
                _maybe_equation(blk, cfg)
        page.blocks.append(blk)
        ledger.emit()


def _md_table_block(ml, bid: str, page: Page, bbox, cfg: Config) -> Optional[Block]:
    return tablemod.from_markdown(getattr(ml, "rows_data", []), bid, page.page,
                                  bbox, cfg)


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def _rejoin_fractions(pg, page: Page, cfg: Config, ledger: Ledger) -> None:
    """A display fraction arrives as two blocks with a rule between them."""
    if not cfg.rejoin_stacked_fractions:
        return
    try:
        h_rules, _ = tablemod.page_rules(pg, cfg)
    except Exception:
        return
    merged = fracmod.rejoin(page, h_rules, cfg)
    if merged:
        # the denominator was detected and emitted, and is now inside the
        # numerator's block. It moves from emitted to dropped, so the ledger
        # stays balanced rather than gaining a block from nowhere.
        ledger.emitted -= merged
        for _ in range(merged):
            ledger.drop(f"p{page.page:03d}_fraction", page.page, "duplicate",
                        "denominator merged into its numerator", None)


def _build_figures(pg, page: Page, raster: Optional[Image.Image], info: Dict,
                   cfg: Config, ledger: Ledger, client: OllamaClient,
                   fig_dir: str) -> None:
    """Gather every candidate first, then decide.

    Emitting as we find is what produced the two figure faults: one clock
    arriving as six pieces because each stored object was published on its own,
    and the same picture arriving twice because two detectors both found it.
    """
    table_rects = [fitz.Rect(b.bbox_pt) for b in page.blocks if b.type == "table"]
    claimed = [tuple(b.bbox_pt) for b in page.blocks if b.type == "table"]
    page_area = pg.rect.get_area()

    # ---- 1. gather ------------------------------------------------------
    cands: List[Tuple[float, float, float, float]] = []
    sources: List[str] = []

    seen_xref_rects: set = set()
    for img in pg.get_images(full=True):
        xref = img[0]
        try:
            rects = pg.get_image_rects(xref)
        except Exception:
            rects = []
        for rect in rects:
            key = (xref, round(rect.x0, 1), round(rect.y0, 1),
                   round(rect.x1, 1), round(rect.y1, 1))
            if key in seen_xref_rects:
                ledger.detect()
                ledger.drop(f"p{page.page:03d}_dup", page.page, "duplicate",
                            f"same image placed twice at one spot (xref {xref})",
                            list(rect))
                continue
            seen_xref_rects.add(key)
            cands.append(tuple(rect))
            sources.append("native_image")

    for rect in _vector_regions(pg, cfg, claimed):
        if any(_overlaps(rect, t, 0.25) for t in table_rects):
            # the region is a ruled grid, but a seal or a diagram is often
            # printed inside one, so look in before letting it go
            for inner in _regions_inside_panel(pg, rect, page, cfg):
                cands.append(tuple(inner))
                sources.append("panel_inner")
            continue
        if _is_panel(rect, page):
            ledger.detect()
            ledger.drop(f"p{page.page:03d}_panel", page.page, "decorative",
                        "ruled panel around text, not a figure", list(rect))
            _mark_panel(page, rect)
            # The panel border is not a figure, but artwork is regularly
            # printed inside one: an activity's circuit, a publisher's seal.
            # Merging by proximity had swallowed that artwork into the border,
            # so the inside is searched again now the border is set aside.
            for inner in _regions_inside_panel(pg, rect, page, cfg):
                if any(_overlaps(inner, fitz.Rect(t), 0.25) for t in table_rects):
                    continue
                cands.append(tuple(inner))
                sources.append("panel_inner")
            continue
        cands.append(tuple(rect))
        sources.append("vector")

    # A published table or a shaded box can have artwork printed inside it too,
    # and its rectangle is claimed before the vector search ever sees it. Look
    # inside each claimed region for the same reason.
    for t in list(table_rects) + [fitz.Rect(c) for c in claimed]:
        for inner in _regions_inside_panel(pg, fitz.Rect(t), page, cfg):
            if any(_overlaps(inner, fitz.Rect(c), 0.4) for c in cands):
                continue
            cands.append(tuple(inner))
            sources.append("panel_inner")

    if page.route in ("scanned", "hybrid") and raster is not None:
        scale = raster.width / page.width_pt if page.width_pt else 1.0
        exclude = [tuple(int(v * scale) for v in b.bbox_pt)
                   for b in page.blocks if b.type != "figure"]
        exclude += [tuple(int(v * scale) for v in r) for r in cands + claimed]
        for box in figmod.detect_regions(raster, exclude, cfg):
            rect = (box[0] / scale, box[1] / scale,
                    box[2] / scale, box[3] / scale)
            if any(_overlaps(fitz.Rect(rect), fitz.Rect(c), 0.35)
                   for c in cands + claimed):
                continue
            cands.append(rect)
            sources.append("scan_region")

    if not cands:
        if cfg.concept_maps:
            _concept_map(pg, page, cfg, ledger, client, fig_dir, raster)
        _absorb_labels_for(page, ledger, cfg)
        _recover_math(pg, page, cfg, ledger, client, fig_dir)
        _add_notes(page, cfg, ledger)
        return

    # ---- 2. cluster the fragments into whole figures ---------------------
    text_boxes = [tuple(b.bbox_pt) for b in page.blocks
                  if b.type in ("paragraph", "heading", "list_item",
                                "equation")]
    captions = [tuple(b.bbox_pt) for b in page.blocks
                if b.type == "caption"
                or (b.text or "").strip().lower().startswith(
                    tuple(cfg.caption_prefixes))]
    gutters = []
    for band_cols in [page.columns] if page.columns > 1 else []:
        pass
    if page.columns > 1:
        usable = page.width_pt - page.margins_pt[0] - page.margins_pt[2]
        step = usable / page.columns
        for i in range(1, page.columns):
            x = page.margins_pt[0] + step * i
            gutters.append((x - 6, x + 6))
    groups = figmod.cluster(cands, text_boxes, page_area, cfg,
                            captions=captions, gutters=gutters,
                            box_edges=[tuple(b) for b in page.boxes_pt])

    # ---- 3. emit, dropping duplicates -----------------------------------
    hashes: List[Tuple[int, str]] = []
    extra: List[Tuple[fitz.Rect, str]] = []
    n = 0
    for rect, members in groups:
        for _ in members:
            ledger.detect()          # every fragment is accounted for
        merged = fitz.Rect(*rect) & pg.rect
        n += 1
        bid = f"p{page.page:03d}_fig{n:02d}"

        if merged.get_area() > page_area * cfg.figure_max_area_frac:
            # A picture the size of the page is a background, a border, or the
            # scan of the page itself. Keep it only when the page yielded
            # nothing else, so a page that is genuinely one image is not lost.
            has_content = any(b.type != "figure" and (b.text or b.table)
                              for b in page.blocks)
            if has_content:
                for _ in members:
                    ledger.drop(bid, page.page, "decorative",
                                "covers the whole page, treated as background",
                                list(rect))
                # a full page tint is a background, but the seals and logos
                # printed on it are not: search what it covers
                for inner in _regions_inside_panel(pg, merged, page, cfg):
                    extra.append((inner, "panel_inner"))
                continue
        kinds = {sources[m] for m in members if m < len(sources)}
        floor = _area_floor(kinds, cfg) * page_area
        if merged.is_empty or merged.get_area() < floor:
            ledger.drop(bid, page.page, "below_min_area",
                        f"{len(members)} fragment(s)", list(rect))
            for _ in members[1:]:
                ledger.drop(bid, page.page, "below_min_area", "fragment")
            continue
        if any(_overlaps(merged, fitz.Rect(c), 0.55) for c in claimed):
            for _ in members:
                ledger.drop(bid, page.page, "duplicate",
                            "region already claimed", list(rect))
            continue

        src = sources[members[0]] if members[0] < len(sources) else "vector"
        if len(members) > 1:
            src = "merged_fragments"

        emitted = _emit_figure(pg, page, merged, bid, cfg, ledger, client,
                               fig_dir, raster, source=src,
                               hashes=hashes, fragments=len(members),
                               embedded="native_image" in kinds)
        # the fragments that were folded in are accounted for as merged
        for _ in members[1:]:
            ledger.drop(bid, page.page, "duplicate",
                        "fragment merged into one figure")
        if emitted is not None:
            claimed.append(tuple(merged))

    # artwork found inside a background or a panel after the main pass
    for inner, src in extra:
        if any(_overlaps(inner, fitz.Rect(c), 0.4) for c in claimed):
            continue
        if inner.get_area() < _area_floor({src}, cfg) * page_area:
            continue
        n += 1
        bid = f"p{page.page:03d}_fig{n:02d}"
        ledger.detect()
        emitted = _emit_figure(pg, page, inner, bid, cfg, ledger, client,
                               fig_dir, raster, source=src,
                               hashes=hashes, fragments=1)
        if emitted is not None:
            claimed.append(tuple(inner))

    if cfg.concept_maps:
        _concept_map(pg, page, cfg, ledger, client, fig_dir, raster)
    _absorb_labels_for(page, ledger, cfg)
    _recover_math(pg, page, cfg, ledger, client, fig_dir)
    _add_notes(page, cfg, ledger)


_ARROW_RE = re.compile(r"^[\s\u2190-\u21ff\u27f5-\u27ff\u2b05-\u2b07>|v]+$")


def _concept_map(pg, page: Page, cfg: Config, ledger: Ledger,
                 client: OllamaClient, fig_dir: str,
                 raster: Optional[Image.Image]) -> None:
    """A concept map is one diagram: boxes of words joined by arrows.

    Each box is a ruled panel with text inside, so B13 dropped every box as a
    panel, kept the words as loose lines and the arrows as stray paragraphs,
    and cut the rest into separate pictures. Three or more arrow glyphs on a
    page seed the map; it grows through the drawings and short labels that
    touch it, and is emitted once, whole."""
    arrows = [b for b in page.blocks
              if b.type in ("paragraph", "list_item", "heading")
              and b.text.strip() and _ARROW_RE.match(b.text)
              and any(0x2190 <= ord(c) <= 0x2bff for c in b.text)]
    if len(arrows) < cfg.concept_map_min_arrows:
        return
    page_area = pg.rect.get_area()
    try:
        drawings = [fitz.Rect(d["rect"]) for d in pg.get_drawings()]
    except Exception:
        drawings = []
    drawings = [r for r in drawings if not r.is_empty
                and r.get_area() < page_area * 0.25]
    region = fitz.Rect(arrows[0].bbox_pt)
    for a in arrows[1:]:
        region |= fitz.Rect(a.bbox_pt)
    shorts = [b for b in page.blocks
              if b.type in ("paragraph", "list_item", "heading")
              and len((b.text or "").split()) <= 6
              and not re.match(r"(?i)^\s*concept\s+map\s*$", b.text or "")]
    for _ in range(12):
        grown = fitz.Rect(region)
        for r in drawings:
            if _near_rect(r, grown, 14) and (grown | r).get_area() < page_area * 0.45:
                grown |= r
        for b in shorts:
            r = fitz.Rect(b.bbox_pt)
            if _near_rect(r, grown, 10) and (grown | r).get_area() < page_area * 0.45:
                grown |= r
        if grown == region:
            break
        region = grown
    region &= pg.rect
    if region.get_area() < page_area * 0.04:
        return
    # the loose pieces found earlier are parts of this one diagram
    keep = []
    for b in page.blocks:
        fr = fitz.Rect(b.bbox_pt)
        if b.type in ("figure", "figure_note") and fr.get_area() > 0 and \
                (fr & region).get_area() >= fr.get_area() * 0.5:
            ledger.drop(b.id, page.page, "duplicate",
                        "part of the concept map, published whole",
                        b.bbox_pt)
            ledger.emitted -= 1
            continue
        keep.append(b)
    page.blocks = keep
    ledger.detect()
    fig = _emit_figure(pg, page, region, f"p{page.page:03d}_map01", cfg, ledger,
                       client, fig_dir, raster, source="concept_map",
                       hashes=None, fragments=1)
    if fig is None:
        return
    if fig.figure is not None and fig.figure.fig_kind == "photo":
        fig.figure.fig_kind = "diagram"
    # every word on the map stays with it, so nothing is lost when the
    # model is not there to describe it
    keep = []
    removed = 0
    for b in page.blocks:
        if b.type in ("paragraph", "list_item", "heading") and \
                _inside(b.bbox_pt, region, tol=3.0):
            if fig.figure is not None and b.text.strip():
                fig.figure.text_in_image.append(b.text.strip())
            ledger.drop(b.id, page.page, "duplicate",
                        f"label inside concept map: {b.text[:30]}", b.bbox_pt)
            removed += 1
            continue
        keep.append(b)
    page.blocks = keep
    ledger.emitted -= removed


_CAP_NUM_RE = re.compile(r"^[\s:.\-\u2002\u00a0]*\d")


def _is_caption(low: str, prefixes) -> bool:
    """A caption names a numbered thing: Figure 1.7, Table 1.2. The word alone
    is not enough, or the Table of Contents becomes a caption."""
    # longest first: "fig" must not shadow "figure"
    for pfx in sorted(prefixes, key=len, reverse=True):
        if low.startswith(pfx) and _CAP_NUM_RE.match(low[len(pfx):]):
            return True
    return False


def cfg_big(cfg: Optional[Config]) -> float:
    return getattr(cfg, "label_max_font_pt", 14.0) if cfg else 14.0


def _absorb_labels_for(page: Page, ledger: Ledger,
                       cfg: Optional[Config] = None) -> None:
    """A label printed inside a diagram belongs to the diagram, not to the text
    flow. It is already captured in the figure's text_in_image."""
    figs = [b for b in page.blocks if b.type == "figure"]
    if not figs:
        return
    prefixes = tuple(cfg.caption_prefixes) if cfg else ("fig", "figure", "table")
    labels_on: Dict[str, int] = {}
    for b in page.blocks:
        if b.type in ("paragraph", "heading", "list_item") and \
                len((b.text or "").strip()) <= 24:
            for f in figs:
                if _inside(b.bbox_pt, fitz.Rect(f.bbox_pt), tol=2.0):
                    labels_on[f.id] = labels_on.get(f.id, 0) + 1
    keep = []
    removed = 0
    for b in page.blocks:
        # "Figure 1.7  Radian" is the figure's caption, not a label written on
        # it. Captions were being swallowed whole and never printed again, so
        # a caption keeps its place in the flow however it overlaps.
        low = (b.text or "").strip().lower()
        if b.type in ("paragraph", "heading", "caption") and \
                _is_caption(low, prefixes):
            b.type = "caption"
            keep.append(b)
            continue
        # An equation typed off a diagram (r = s printed on the arc) is a label
        # too, but it has to sit squarely inside the figure to count: a display
        # equation directly under one must stay in the flow.
        is_label = (b.type in ("paragraph", "list_item")
                    and len(b.text.strip()) <= 24)
        # map type runs together into long lines; at this size it is still
        # lettering on the drawing, whatever its length
        if (b.type in ("paragraph", "list_item") and b.font_size
                and b.font_size < 6.5
                and any(_inside(b.bbox_pt, fitz.Rect(f.bbox_pt), tol=4.0)
                        for f in figs)):
            is_label = True
        # A label set in the display face now reads as a heading. Printed
        # squarely on a picture it is still the picture's label.
        # Only on a labelled drawing, though: a lone word in a circle is the
        # badge's title and has to stay in the text.
        if (b.type == "heading" and len(b.text.strip()) <= 24
                and any(_inside(b.bbox_pt, fitz.Rect(f.bbox_pt), tol=2.0)
                        and labels_on.get(f.id, 0) >= 2 for f in figs)):
            is_label = True
        is_inline_math = (b.type == "equation" and len(b.text.strip()) <= 24
                          and any(_inside(b.bbox_pt, fitz.Rect(f.bbox_pt), tol=2.0)
                                  for f in figs))
        # Display type is a title printed on a band, never a diagram label:
        # absorbing it is how a chapter lost its name.
        host = next((f for f in figs
                     if _inside(b.bbox_pt, fitz.Rect(f.bbox_pt), tol=26.0)),
                    None)
        if (is_label and host is not None and b.font_size
                and b.font_size >= cfg_big(cfg)
                and host.width >= page.width_pt * 0.6):
            is_label = False    # the chapter title printed on its band
        if is_label or is_inline_math:
            if is_inline_math or host is not None:
                # the words stay with the picture they were printed on, so a
                # label is still readable when no description was made
                if host is not None and host.figure is not None:
                    txt = (b.text or "").strip()
                    if txt and txt not in host.figure.text_in_image:
                        host.figure.text_in_image.append(txt)
                ledger.drop(b.id, page.page, "duplicate",
                            f"label inside figure: {b.text[:30]}", b.bbox_pt)
                removed += 1
                continue
        keep.append(b)
    page.blocks = keep
    ledger.emitted -= removed


def _recover_math(pg, page: Page, cfg: Config, ledger: Ledger,
                  client: OllamaClient, fig_dir: str) -> None:
    """An equation the text layer mangled is read off the page by the VLM.

    This closes the last hole where maths would survive only as a picture. It
    is still validated, so an unreadable formula falls back to the image rather
    than to a wrong formula typed out confidently.
    """
    if not cfg.vlm_math or cfg.offline:
        return
    for b in page.blocks:
        if b.type != "equation" or not b.math_unreadable:
            continue
        clip = fitz.Rect(b.bbox_pt) & pg.rect
        if clip.is_empty or clip.width < 8 or clip.height < 6:
            continue
        clip = fitz.Rect(clip.x0 - 4, clip.y0 - 4, clip.x1 + 4, clip.y1 + 4) & pg.rect
        try:
            pix = pg.get_pixmap(clip=clip, dpi=cfg.figure_dpi, alpha=False)
            crop = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        except Exception:
            continue
        latex = figmod.read_math(client, crop, cfg)
        if latex:
            b.latex = latex
            b.latex_source = "vlm"
            b.math_unreadable = False
            # the earlier failure has been answered, so its flag goes with it.
            # Leaving it behind reports a good formula as unreadable.
            b.flags = [f for f in b.flags if not f.startswith("math:")]
            b.flags.append("math_read_by_vlm")
        else:
            # keep the printed formula so nothing is lost, but never type a
            # formula we could not verify
            ref = f"figures/{b.id}_eq.png"
            crop.save(os.path.join(fig_dir, os.path.basename(ref)), "PNG")
            b.image_ref = ref


def _vet_split(parts, crop, clip, page: Page, cfg: Config):
    """A split has to earn itself. One photograph of five children has white
    space between the children, and that is not a gap between five pictures.

    Two tests, both cheap and both refusing rather than repairing: the parts
    must be genuinely separated, and if the page prints one caption for the
    region then the region is one figure whatever the model said.
    """
    whole = [(0.0, 0.0, 1.0, 1.0)]
    if not parts or len(parts) < 2:
        return whole

    # 1. real separation, measured on the page and not on the crop
    gap_x = min(
        (parts[i + 1][0] - parts[i][2]) * clip.width
        for i in range(len(parts) - 1)) if len(parts) > 1 else 0.0
    gap_y = min(
        (parts[i + 1][1] - parts[i][3]) * clip.height
        for i in range(len(parts) - 1)) if len(parts) > 1 else 0.0
    if max(gap_x, gap_y) < cfg.composite_min_gap_pt:
        return whole

    # 2. one caption for the whole region means one figure
    if cfg.composite_require_caption:
        caps = 0
        for b in page.blocks:
            if b.type not in ("paragraph", "caption") or not b.bbox_pt:
                continue
            t = (b.text or "").strip().lower()
            if not any(t.startswith(pfx) for pfx in cfg.caption_prefixes):
                continue
            if b.x1 > clip.x0 - 8 and b.x0 < clip.x1 + 8 and \
                    abs(b.y0 - clip.y1) <= cfg.caption_max_gap_pt:
                caps += 1
        if caps < len(parts):
            return whole
    return parts


def _overlaps(a: fitz.Rect, b: fitz.Rect, frac: float = 0.5) -> bool:
    inter = a & b
    if inter.is_empty:
        return False
    return inter.get_area() > frac * min(a.get_area(), b.get_area())


def _vector_regions(pg, cfg: Config, placed) -> List[fitz.Rect]:
    try:
        drawings = pg.get_drawings()
    except Exception:
        return []
    rects = []
    for d in drawings:
        r = fitz.Rect(d["rect"])
        if r.is_empty or r.width < 1 or r.height < 1:
            continue
        if r.width > pg.rect.width * 0.95 and r.height < 4:
            continue                     # a rule, not a figure
        rects.append(r)
    merged: List[fitz.Rect] = []
    for r in rects:
        hit = False
        for i, m in enumerate(merged):
            if _near_rect(r, m, 8):
                merged[i] = m | r
                hit = True
                break
        if not hit:
            merged.append(r)
    out = []
    for r in merged:
        if r.get_area() < cfg.figure_min_area_frac * pg.rect.get_area():
            continue
        if any(_overlaps(r, fitz.Rect(p)) for p in placed):
            continue
        out.append(r)
    return out


def _area_floor(kinds, cfg: Config) -> float:
    """The smallest a region may be, by how it was found.

    A stray vector fragment needs to clear a real bar. An embedded image, or a
    cluster recovered from inside a panel, was put there on purpose: a seal is
    small and still content.
    """
    if "native_image" in kinds:
        return cfg.figure_min_area_frac_native
    if "panel_inner" in kinds:
        return cfg.panel_inner_min_area_frac
    return cfg.figure_min_area_frac


def _regions_inside_panel(pg, panel, page: Page, cfg: Config) -> List[fitz.Rect]:
    """Artwork drawn inside a ruled panel.

    Drawings are merged by proximity, so a panel border joins everything it
    encloses into one rectangle and the whole lot is discarded with the border.
    Here the border itself is excluded and what is left is clustered again,
    keeping only clusters that do not sit under the panel's text.
    """
    if not cfg.panel_inner_figures:
        return []
    try:
        drawings = pg.get_drawings()
    except Exception:
        return []
    panel_area = panel.get_area()
    if panel_area <= 0:
        return []
    inside_blocks = [b for b in page.blocks
                     if b.type in ("paragraph", "heading", "list_item",
                                   "equation", "caption")]
    # Type under six and a half points is labelling on a drawing (a map's
    # place names and graticule), never text a drawing sits behind, so it does
    # not count against the drawing's claim to be artwork.
    text = [fitz.Rect(b.bbox_pt) for b in inside_blocks
            if not (b.font_size and b.font_size < 6.5)]
    # A word or two printed on a diagram is a label and travels with it. A
    # sentence is prose, and a cluster that encloses prose is a block of text
    # with some rules drawn through it, not artwork.
    prose = [fitz.Rect(b.bbox_pt) for b in inside_blocks if _is_prose(b)]
    inner: List[fitz.Rect] = []
    for d in drawings:
        r = fitz.Rect(d["rect"])
        if r.is_empty or r.width < 1 or r.height < 1:
            continue
        if not _inside(list(r), panel, tol=2.0):
            continue
        if r.get_area() > panel_area * 0.88:      # the border itself
            continue
        if _mostly_text(r, text):
            continue                              # a rule or a box around text
        if any(not (r & t).is_empty for t in prose):
            continue    # a rule under a sentence: joining through it would
                        # chain half the page into one imaginary picture
        inner.append(r)
    merged: List[fitz.Rect] = []
    for r in inner:
        hit = False
        for i, m in enumerate(merged):
            if _near_rect(r, m, 8):
                merged[i] = m | r
                hit = True
                break
        if not hit:
            merged.append(r)
    floor = cfg.panel_inner_min_area_frac * pg.rect.get_area()
    out = []
    for r in merged:
        if r.get_area() < floor:
            continue
        if r.width < 14 or r.height < 14:
            continue                              # a hairline, not a picture
        ar = r.width / max(1e-6, r.height)
        if ar > 7.0 or ar < 1 / 7.0:
            continue                              # a bar, a rule, a colour strip
        if r.get_area() > panel_area * 0.7:       # the panel itself, again
            continue
        if _text_coverage(r, text) > 0.35:
            continue
        if any(_inside(list(t), r, tol=2.0) for t in prose):
            continue                              # it encloses a sentence
        for b in inside_blocks:
            if _is_prose(b):
                continue
            lab = fitz.Rect(b.bbox_pt)
            if _near_rect(lab, r, 6) and not lab.contains(r):
                r = r | lab                       # the label belongs to it
        out.append(r)
    return out


_TOKEN_RE = re.compile(r"[A-Za-z]+")


def _is_prose(b: Block) -> bool:
    """A sentence, as opposed to labels printed on a drawing.

    B13 called anything over three words prose, and the Indian Standard
    Meridian map, whose run together labels ("68 7' BANGLADESH 24 24 ...")
    are set in three point type, was thrown out as a paragraph with rules
    drawn through it. Text that small is a label whatever its word count.
    """
    if len((b.text or "").split()) <= 3:
        return False
    if b.font_size and b.font_size < 6.5:
        return False
    return True


def _text_coverage(rect, text) -> float:
    """How much of a rectangle is taken up by text sitting inside it."""
    area = rect.get_area()
    if area <= 0:
        return 1.0
    covered = 0.0
    for t in text:
        inter = rect & t
        if not inter.is_empty:
            covered += inter.get_area()
    return covered / area


def _mostly_text(rect, text) -> bool:
    """A drawing that a text block all but covers is an underline, a rule or a
    highlight. A drawing a label merely sits on top of is artwork."""
    return _text_coverage(rect, text) > 0.6


def _mark_panel(page: Page, rect) -> None:
    for b in page.blocks:
        if (b.x0 >= rect.x0 - 4 and b.x1 <= rect.x1 + 4
                and b.y0 >= rect.y0 - 4 and b.y1 <= rect.y1 + 4):
            if not b.block_kind:
                b.block_kind = "panel"
            if "in_panel" not in b.flags:
                b.flags.append("in_panel")


def _is_panel(rect, page: Page) -> bool:
    """A ruled panel around an activity or a note is a border, not a figure.

    The give away is that its inside is mostly text. Treating it as a figure
    swallows the panel's heading and turns its text into a picture.
    """
    inside = [b for b in page.blocks
              if b.type in ("paragraph", "heading", "list_item", "equation")
              and b.x0 >= rect.x0 - 4 and b.x1 <= rect.x1 + 4
              and b.y0 >= rect.y0 - 4 and b.y1 <= rect.y1 + 4]
    if not inside:
        return False
    covered = sum(b.width * b.height for b in inside)
    area = rect.get_area()
    return area > 0 and covered / area > 0.18


def _near_rect(a, b, gap) -> bool:
    return not (a.x1 + gap < b.x0 or b.x1 + gap < a.x0
                or a.y1 + gap < b.y0 or b.y1 + gap < a.y0)


def _named_figure(page: Page, box, cfg: Config) -> bool:
    """True when a "Figure N" caption sits on, just under or just over the
    region. The book's own label outranks a model's verdict."""
    x0, y0, x1, y1 = box
    fig_prefixes = tuple(p for p in cfg.caption_prefixes
                         if not p.startswith("tab"))
    for b in page.blocks:
        if b.type not in ("paragraph", "caption", "heading"):
            continue
        if not is_numbered_caption((b.text or "").strip().lower(), fig_prefixes):
            continue
        if min(b.x1, x1) - max(b.x0, x0) <= 0:
            continue
        if b.y0 >= y0 - 4 and b.y0 - y1 <= cfg.caption_max_gap_pt * 0.75:
            return True
        if b.y1 <= y1 + 4 and y0 - b.y1 <= cfg.caption_max_gap_pt * 0.75:
            return True
    return False


def _native_text_inside(page: Page, box) -> bool:
    for b in page.blocks:
        if b.type in ("paragraph", "heading") and b.source == "native_span" \
                and re.search(r"[A-Za-z]{3,}", b.text or "") \
                and _inside(b.bbox_pt, fitz.Rect(box), tol=3.0):
            return True
    return False


def _promote_banner_text(page: Page, box) -> None:
    """Words printed on a banner or in a badge are its title."""
    for b in page.blocks:
        if b.type == "paragraph" and b.source == "native_span" \
                and _inside(b.bbox_pt, fitz.Rect(box), tol=3.0) \
                and len((b.text or "").split()) <= 8:
            b.type = "heading"
            b.level = b.level or 3
            b.block_kind = b.block_kind or "label"


def _region_to_text(sub: Image.Image, page: Page, bbox, base_id: str,
                    cfg: Config, ledger: Ledger, client: OllamaClient,
                    embedded: bool = False) -> List[Block]:
    """A region that holds only printed text is read out line by line and
    published as real text. A picture of a paragraph is not a figure."""
    try:
        md = client.ocr_page(figmod.to_png_bytes(sub, cfg.ocr_max_edge_px))
    except Exception:
        return []
    md_lines = [m for m in ocrmod.parse_markdown(md, cfg) if m.kind != "figure"]
    if not md_lines:
        return []
    total = sum(len(m.text) for m in md_lines)
    if total < cfg.text_only_min_chars:
        return []

    boxes = ocrmod.line_boxes(sub)
    median = ocrmod.page_ink_median(sub, boxes) if boxes else 0.0
    pairs = ocrmod.align(md_lines, boxes)

    bx0, by0, bx1, by1 = bbox
    sx = (bx1 - bx0) / max(1, sub.width)
    sy = (by1 - by0) / max(1, sub.height)

    # Text this small is a screenshot of a web page, not a heading banner.
    # Publishing it as prose spilled a Wikipedia article into the ICT corner.
    heights = sorted((b[3] - b[1]) * sy for b in boxes) if boxes else []
    if (embedded and len(heights) >= 3
            and heights[len(heights) // 2] < cfg.text_only_min_line_pt):
        return []

    narrow = (bx1 - bx0) < page.width_pt * 0.4
    one_line = len([m for m in md_lines if (m.text or "").strip()]) == 1
    out: List[Block] = []
    for i, (ml, box) in enumerate(pairs, start=1):
        if not (ml.text or "").strip() and ml.kind != "table":
            continue
        if one_line:
            lb = [bx0, by0, bx1, by1]   # a badge: the whole region is its place
        elif box is not None:
            lb = [bx0 + box[0] * sx, by0 + box[1] * sy,
                  bx0 + box[2] * sx, by0 + box[3] * sy]
        else:                      # no box: stack it inside the region
            h = (by1 - by0) / max(1, len(pairs))
            lb = [bx0, by0 + (i - 1) * h, bx1, by0 + i * h]
        bid = f"{base_id}_t{i:02d}"
        if ml.kind == "table":
            tb = _md_table_block(ml, bid, page, lb, cfg)
            if tb is not None:
                out.append(tb)
            continue
        runs = list(ml.runs)
        if not runs and box is not None:
            runs = ocrmod.bold_runs_from_ink(sub, box, ml.text, median, cfg)
        blk = Block(id=bid, page=page.page, type="paragraph", bbox_pt=lb,
                    text=ml.text, runs=merge_runs(runs), source="figure_text",
                    confidence=0.85)
        if ml.kind == "heading" or (one_line and narrow
                                    and len(ml.text.split()) <= 6):
            # a small badge is a box title, not a chapter heading
            blk.type = "heading"
            blk.level = 3 if narrow else (ml.level or 2)
            blk.block_kind = "label"
        elif ml.kind == "list":
            blk.type, blk.block_kind = "list_item", "bullet"
        elif ml.kind == "equation":
            latex, why = prepare(ml.text)
            blk.type, blk.latex, blk.display_math = "equation", latex, True
            blk.math_unreadable = latex is None
            if latex is None:
                blk.flags.append(f"math:{why}")
        else:
            _maybe_equation(blk, cfg)
        blk.flags.append("from_text_only_region")
        out.append(blk)
    return out


def _note_block(fig: Block, cfg: Config, page: Page) -> Optional[Block]:
    """The description box printed under a real figure."""
    m = fig.figure
    if m is None:
        return None
    parts: List[str] = []
    if (m.desc or "").strip():
        parts.append(m.desc.strip())
    if m.entities:
        parts.append("Parts: " + ", ".join(m.entities))
    if m.relationships:
        parts.append("Relations: " + "; ".join(m.relationships))
    if m.data_points:
        parts.append("Data: " + "; ".join(m.data_points))
    if m.text_in_image:
        parts.append("Text in figure: " + " | ".join(m.text_in_image))
    if not parts:
        # Switching the pass off is a choice, so no box. But if the pass was
        # meant to run and produced nothing, say so: a silent gap reads like a
        # missing feature, while a stated failure reads like a failure.
        if cfg.offline or not cfg.describe_figures:
            return None
        parts = ["No description available: "
                 + (m.error or "the model returned nothing for this figure"),
                 f"Check that Ollama is running and that {cfg.vlm_model} is "
                 "pulled: python -m eduverse_book2docx --check"]
    # the box flows under the figure, so its bbox only has to order correctly
    # and stay on the page: a figure ending at the page edge must not push it off
    y0 = min(fig.y1, page.height_pt - 12.0)
    y1 = min(y0 + 12.0, page.height_pt)
    return Block(id=f"{fig.id}_note", page=fig.page, type="figure_note",
                 bbox_pt=[fig.x0, y0, fig.x1, y1],
                 text="\n".join(parts), caption_of=fig.id,
                 block_kind=m.fig_kind, source="vlm_crop")


def _note_for_equation(b: Block, cfg: Config, page: Page) -> Optional[Block]:
    """The description box under an equation.

    The LaTeX is the exact recipe for a replica, so it goes in verbatim. The
    reading underneath is what a person or a model uses without parsing it.
    """
    if not cfg.equation_description_box:
        return None
    parts: List[str] = []
    if b.latex and not b.math_unreadable:
        parts.append(mathtools.speak(b.latex))
        parts.append("LaTeX: " + b.latex)
        if b.latex_source:
            parts.append("Read from: " + {"text_layer": "the page text layer",
                                          "vlm": "the vision model",
                                          "docx": "the Word equation"}
                         .get(b.latex_source, b.latex_source))
    elif b.text.strip():
        parts.append("Printed as: " + b.text.strip())
        parts.append("Not verified, so the printed image is kept instead of a "
                     "typed formula.")
    if not parts:
        return None
    y0 = min(b.y1, page.height_pt - 12.0)
    return Block(id=f"{b.id}_note", page=b.page, type="figure_note",
                 bbox_pt=[b.x0, y0, b.x1, min(y0 + 12.0, page.height_pt)],
                 text="\n".join(parts), caption_of=b.id,
                 block_kind="equation", source=b.latex_source or "text_layer")


def _note_for_table(b: Block, cfg: Config, page: Page) -> Optional[Block]:
    """The description box under a table.

    The cells are the replica, so they are written out as a pipe table. A long
    table is summarised rather than retyped, since the table itself is already
    in the document directly above.
    """
    if not cfg.table_description_box or b.table is None:
        return None
    td = b.table
    grid = {(c.row, c.col): c.text.strip() for c in td.cells}
    header = [grid.get((r, c), "") for r in range(max(1, td.header_rows))
              for c in range(td.cols)] if td.header_rows else []
    parts = [f"A table of {td.rows} rows and {td.cols} columns"
             + (f", with {td.header_rows} header row"
                + ("s" if td.header_rows > 1 else "") if td.header_rows else "")
             + (", ruled" if td.has_v_rules and td.has_h_rules
                else ", with horizontal rules only" if td.has_h_rules
                else ", unruled") + "."]
    if header and any(header):
        parts.append("Columns: " + ", ".join(h for h in header if h) + ".")
    merged = [c for c in td.cells if c.row_span > 1 or c.col_span > 1]
    if merged:
        parts.append("Merged cells: " + "; ".join(
            f"{c.text.strip() or 'blank'} spans {c.col_span} columns"
            + (f" and {c.row_span} rows" if c.row_span > 1 else "")
            for c in merged[:6]) + ".")
    body_start = td.header_rows
    rows_out = []
    for r in range(body_start, min(td.rows, body_start + cfg.table_note_max_rows)):
        rows_out.append(" | ".join(grid.get((r, c), "") for c in range(td.cols)))
    if rows_out:
        parts.append("Rows:")
        parts.extend(rows_out)
    if td.rows - body_start > cfg.table_note_max_rows:
        parts.append(f"... and {td.rows - body_start - cfg.table_note_max_rows} "
                     f"more rows, as printed in the table above.")
    y0 = min(b.y1, page.height_pt - 12.0)
    return Block(id=f"{b.id}_note", page=b.page, type="figure_note",
                 bbox_pt=[b.x0, y0, b.x1, min(y0 + 12.0, page.height_pt)],
                 text="\n".join(parts), caption_of=b.id,
                 block_kind="table", source=b.source)


def _add_notes(page: Page, cfg: Config, ledger: Ledger) -> None:
    """Every equation and every table gets the same treatment as a figure."""
    extra: List[Block] = []
    for b in page.blocks:
        if b.type == "equation":
            n = _note_for_equation(b, cfg, page)
        elif b.type == "table":
            n = _note_for_table(b, cfg, page)
        else:
            continue
        if n is not None:
            extra.append(n)
    for n in extra:
        ledger.detect()
        page.blocks.append(n)
        ledger.emit()


def _emit_figure(pg, page: Page, rect, bid: str, cfg: Config, ledger: Ledger,
                 client: OllamaClient, fig_dir: str,
                 raster: Optional[Image.Image], source: str,
                 hashes: Optional[List] = None,
                 fragments: int = 1, embedded: bool = False) -> Optional[Block]:
    """Crop at figure dpi, split composites, describe, write one or more blocks."""
    clip = fitz.Rect(rect) & pg.rect
    if clip.is_empty or clip.width < 8 or clip.height < 8:
        ledger.drop(bid, page.page, "below_min_area", "", list(rect))
        return None
    try:
        pix = pg.get_pixmap(clip=clip, dpi=cfg.figure_dpi, alpha=False)
        crop = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    except Exception as exc:
        ledger.drop(bid, page.page, "empty", str(exc)[:100], list(rect))
        return None

    if figmod.is_flat(crop):
        ledger.drop(bid, page.page, "empty", "blank or flat region", list(rect))
        return None

    parts = figmod.split_composite(client, crop, cfg)
    if len(parts) > 1:
        parts = _vet_split(parts, crop, clip, page, cfg)
    emitted = None
    for pi, (fx0, fy0, fx1, fy1) in enumerate(parts):
        if pi > 0:
            # extra parts were not counted at detection time. Counted HERE, at
            # the top, so a part dropped further down still balances: counting
            # it at the bottom is what left the ledger short.
            ledger.detect()
        sub = crop.crop((int(fx0 * crop.width), int(fy0 * crop.height),
                         max(1, int(fx1 * crop.width)),
                         max(1, int(fy1 * crop.height))))
        sub_id = bid if len(parts) == 1 else f"{bid}_{pi + 1}"
        bx0 = clip.x0 + fx0 * clip.width
        bx1 = clip.x0 + fx1 * clip.width
        by0 = clip.y0 + fy0 * clip.height
        by1 = clip.y0 + fy1 * clip.height

        # the same picture found twice by two detectors, or placed twice by the
        # PDF, comes out looking identical: hash it and keep only the first
        if (cfg.dedupe_images and hashes is not None
                and not (cfg.skip_code_like_dedupe and figmod.is_code_like(sub))):
            h = figmod.phash(sub, cfg.dup_hash_bits)
            twin = next((oid for oh, oid in hashes
                         if figmod.near_duplicate(h, oh, cfg)), None)
            if twin is not None:
                ledger.drop(sub_id, page.page, "duplicate",
                            f"same picture as {twin}", [bx0, by0, bx1, by1])
                continue
            hashes.append((h, sub_id))
            meta_hash = h

        meta = figmod.describe(client, sub, cfg)
        if len(parts) > 1:
            meta.part_of = bid

        bx0 = clip.x0 + fx0 * clip.width
        bx1 = clip.x0 + fx1 * clip.width
        by0 = clip.y0 + fy0 * clip.height
        by1 = clip.y0 + fy1 * clip.height

        box = (bx0, by0, bx1, by1)
        named = _named_figure(page, box, cfg)
        code = figmod.is_code_like(sub)
        named_picture = named and meta.fig_kind != "text_banner"
        if meta.text_only and (named_picture or code):
            # The book calls it a figure, or it is a QR code with its label.
            # A clock face showing 12:30 is still a picture of a clock.
            meta.text_only = False
            if meta.fig_kind == "text_banner":
                meta.fig_kind = "photo"
            meta.error = (meta.error + " " if meta.error else "") + \
                ("text_only overruled: captioned as a figure" if named_picture
                 else "text_only overruled: machine code")

        # A banner whose words are already in the text layer: keep the words,
        # drop the picture of them. This is the PREFACE printed twice case.
        if meta.text_only and _native_text_inside(page, box):
            _promote_banner_text(page, box)
            ledger.drop(sub_id, page.page, "duplicate",
                        "text banner, its words are already in the text layer",
                        list(box))
            continue

        # text only: read it out and drop the picture entirely
        if cfg.text_only_to_text and meta.text_only:
            blocks = _region_to_text(sub, page, (bx0, by0, bx1, by1),
                                     sub_id, cfg, ledger, client,
                                     embedded=embedded or source == "native_image")
            if blocks:
                ledger.drop(sub_id, page.page, "duplicate",
                            "region held only text, published as text",
                            [bx0, by0, bx1, by1])
                for b in blocks:
                    ledger.detect()
                    page.blocks.append(b)
                    ledger.emit()
                continue

        # a picture of a table is still a table
        # A photograph is not a table however tidily its subjects are arranged.
        # Asking anyway is how a four picture composite and a photo of a clock
        # were both republished as tables, losing the pictures.
        # Only a region the model itself calls a table is offered, and never
        # one the book captions as a Figure: a circuit with three labels, the
        # accuracy targets and a digital clock all came back as tables.
        if (cfg.vlm_tables and meta.fig_kind in cfg.vlm_table_kinds
                and not named):
            td = figmod.as_table(client, sub, cfg)
            if td is not None:
                tb = tablemod.from_markdown(
                    ([td["header"]] if td["header"] else []) + td["rows"],
                    sub_id, page.page, [bx0, by0, bx1, by1], cfg)
                if tb is not None:
                    tb.source = "vlm_table"
                    tb.confidence = 0.75
                    ledger.drop(sub_id, page.page, "duplicate",
                                "region was a table, published as a table",
                                [bx0, by0, bx1, by1])
                    ledger.detect()
                    page.blocks.append(tb)
                    ledger.emit()
                    continue

        rel = f"figures/{sub_id}.png"
        sub.save(os.path.join(fig_dir, f"{sub_id}.png"), "PNG", optimize=True)
        out_dir = os.path.dirname(fig_dir)
        figmod.enrich(client, sub, meta, cfg, out_dir, sub_id,
                      bx1 - bx0, by1 - by0)
        figmod.save_meta(meta, os.path.join(fig_dir, f"{sub_id}.json"))

        blk = Block(id=sub_id, page=page.page, type="figure",
                    bbox_pt=[bx0, by0, bx1, by1], image_ref=rel,
                    px_w=sub.width, px_h=sub.height, source=source,
                    figure=meta)
        if fragments > 1:
            blk.flags.append(f"merged_from_{fragments}_fragments")
        if not figmod.post_filter(blk, ledger):
            continue
        page.blocks.append(blk)
        ledger.emit()
        emitted = blk

        if cfg.figure_description_box:
            note = _note_block(blk, cfg, page)
            if note is not None:
                ledger.detect()
                page.blocks.append(note)
                ledger.emit()
    return emitted


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def _build_tables(pg, page: Page, cfg: Config, ledger: Ledger,
                  raster=None, client=None) -> None:
    h_rules, v_rules = tablemod.page_rules(pg, cfg)
    claimed: List[fitz.Rect] = []

    # 1. native grids, with per-cell runs and real spans
    strategies = [{}, {"strategy": "lines_strict"}, {"strategy": "text"}]
    seen_boxes: List[fitz.Rect] = []
    ti = 0
    for kwargs in strategies:
        try:
            found = pg.find_tables(**kwargs)
        except Exception:
            continue
        for tb in list(getattr(found, "tables", []) or []):
            rect = fitz.Rect(tb.bbox)
            if any(_overlaps(rect, s, 0.3) for s in seen_boxes):
                continue
            if any(b.type == "figure" and _overlaps(fitz.Rect(b.bbox_pt), rect, 0.4)
                   for b in page.blocks):
                continue                     # a diagram already claimed
            ti += 1
            bid = f"p{page.page:03d}_tbl{ti:02d}"
            ledger.detect()
            blk = tablemod.build_native(pg, tb, rect, page.page, bid, cfg,
                                        h_rules, v_rules)
            if blk is None:
                ledger.drop(bid, page.page, "unsupported",
                            "grid found but too sparse to be a table",
                            list(rect))
                continue
            seen_boxes.append(rect)
            _absorb_into_table(page, rect, ledger, blk.table)
            page.blocks.append(blk)
            ledger.emit()
            claimed.append(rect)
        if seen_boxes and kwargs == {}:
            break                            # the default strategy did the job

    # 2. ruled grids on a page raster the text layer knew nothing about
    if page.route in ("scanned", "hybrid") and raster is not None and client:
        scale = raster.width / page.width_pt if page.width_pt else 1.0
        for box in tablemod.detect_grids(raster, cfg):
            rect = fitz.Rect(box[0] / scale, box[1] / scale,
                             box[2] / scale, box[3] / scale)
            if any(_overlaps(rect, c, 0.3) for c in claimed):
                continue
            ti += 1
            bid = f"p{page.page:03d}_tbl{ti:02d}"
            ledger.detect()
            crop = raster.crop((max(0, box[0] - 4), max(0, box[1] - 4),
                                min(raster.width, box[2] + 4),
                                min(raster.height, box[3] + 4)))
            blk = tablemod.read_grid(client, crop, bid, page.page,
                                     [rect.x0, rect.y0, rect.x1, rect.y1], cfg)
            if blk is None:
                ledger.drop(bid, page.page, "ocr_empty",
                            "ruled region returned no table", list(rect))
                continue
            _absorb_into_table(page, rect, ledger, blk.table)
            page.blocks.append(blk)
            ledger.emit()
            claimed.append(rect)


def _absorb_into_table(page: Page, rect, ledger: Ledger, td=None) -> None:
    ids = set(tablemod.absorbed_ids(page.blocks, rect, td))
    if not ids:
        return
    keep = []
    for b in page.blocks:
        if b.id in ids:
            ledger.drop(b.id, page.page, "duplicate", "absorbed into table",
                        b.bbox_pt)
            continue
        keep.append(b)
    ledger.emitted -= len(page.blocks) - len(keep)
    page.blocks = keep


def _inside(bbox, rect, tol: float = 3.0) -> bool:
    return (bbox[0] >= rect.x0 - tol and bbox[2] <= rect.x1 + tol
            and bbox[1] >= rect.y0 - tol and bbox[3] <= rect.y1 + tol)


# ---------------------------------------------------------------------------
# Detection, nothing declared
# ---------------------------------------------------------------------------

TAMIL = re.compile(r"[\u0b80-\u0bff]")
DEVANAGARI = re.compile(r"[\u0900-\u097f]")
GRADE_RE = re.compile(r"\b(?:class|std|standard|grade)\s*[-:]?\s*"
                      r"(\d{1,2}|[IVX]{1,4}|one|two|three|four|five|six|seven|"
                      r"eight|nine|ten|eleven|twelve)\b", re.I)
BOARD_RE = re.compile(r"(samacheer kalvi|tamil ?nadu|ncert|cbse|icse|"
                      r"state board|karnataka|maharashtra|kerala|telangana)", re.I)
# Rule 44: the most specific match wins, so a subject is only accepted when it
# is not sitting inside a board or state name.
SUBJECT_WORDS = [
    "social science", "computer science", "environmental science",
    "political science", "general science", "mathematics", "chemistry",
    "biology", "physics", "geography", "economics", "accountancy",
    "commerce", "history", "civics", "science", "english", "maths",
    "botany", "zoology",
]
WORDS_TO_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
                "eleven": 11, "twelve": 12}


def _find_subject(text: str, board: Optional[str]) -> Optional[str]:
    """Rule 45: a state or board name is never the subject."""
    low = text.lower()
    banned: List[Tuple[int, int]] = []
    for m in BOARD_RE.finditer(low):
        banned.append((m.start(), m.end()))
    for word in SUBJECT_WORDS:          # longest first, so specific wins
        for m in re.finditer(r"\b" + re.escape(word) + r"\b", low):
            if any(a <= m.start() < b for a, b in banned):
                continue                # inside "Tamil Nadu", so not a subject
            return word.title()
    return None


def _detect(book: Book, profile: SizeProfile, doc) -> Dict:
    meta = doc.metadata or {}
    # Rule 46: the running head repeats on every page, so it is the most
    # reliable source. Weigh it above the cover.
    furniture = " ".join(book.stats.get("furniture", []))
    head = " ".join(b.text for p in book.pages[:6] for b in p.blocks
                    if b.text)[:4000]
    meta_txt = " ".join(str(v) for v in meta.values() if v)
    name = os.path.basename(book.source_file).replace("_", " ")

    lang = "ta" if TAMIL.search(head) else (
        "hi" if DEVANAGARI.search(head) else "en")

    subject = None
    for source in (furniture, name, head, meta_txt):
        board_here = BOARD_RE.search(source)
        subject = _find_subject(source, board_here.group(1) if board_here else None)
        if subject:
            break

    board = None
    for source in (head, furniture, meta_txt, name):
        m = BOARD_RE.search(source)
        if m:
            board = m.group(1).title()
            break

    grade = None
    for source in (furniture, head, name, meta_txt):
        g = GRADE_RE.search(source)
        if g:
            raw = g.group(1)
            if raw.isdigit():
                grade = int(raw)
            elif raw.lower() in WORDS_TO_NUM:
                grade = WORDS_TO_NUM[raw.lower()]
            else:
                grade = _roman(raw)
            if grade:
                break
    if grade is None:
        m = re.search(r"\b(\d{1,2})\s*(?:th|st|nd|rd)\b", name, re.I)
        if m:
            grade = int(m.group(1))

    routes: Dict[str, int] = {}
    for p in book.pages:
        routes[p.route] = routes.get(p.route, 0) + 1
    layout: Dict[str, int] = {}
    for p in book.pages:
        layout[f"{p.columns}col"] = layout.get(f"{p.columns}col", 0) + 1

    return {
        "format": "pdf",
        "pages": len(book.pages),
        "language": lang,
        "grade": grade,
        "board": board,
        "subject": subject,
        "routes": routes,
        "layout": layout,
        "title": (meta.get("title") or "").strip() or None,
    }


def _roman(s: str) -> Optional[int]:
    vals = {"I": 1, "V": 5, "X": 10}
    s = s.upper()
    if not all(c in vals for c in s):
        return None
    total = 0
    prev = 0
    for c in reversed(s):
        v = vals[c]
        total += -v if v < prev else v
        prev = max(prev, v)
    return total


def _file_id(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()[:24]
