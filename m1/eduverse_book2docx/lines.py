"""Turning lines into blocks, with the layout already known.

The old path grouped lines using PyMuPDF's own blocks, which straddle columns
and boxes. This module groups them only within one band, one column and one
box, which is what rules 13 to 20 require.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .config import Config
from .layout import Layout
from .schema import Run
from .textclean import clean

BOLD_FLAG = 1 << 4
ITALIC_FLAG = 1 << 1
SUPER_FLAG = 1
BOLD_NAME = re.compile(r"bold|black|heavy|semib|demi", re.I)
ITAL_NAME = re.compile(r"italic|oblique", re.I)

DINGBAT_FONTS = ("wingding", "zapf", "dingbat", "webding")
# A dingbat font read literally gives the glyph's byte, not the mark it prints.
# The Wingdings arrow in this book arrives as the vulgar fraction three quarters.
DINGBAT_MAP = {
    "\u00be": "\u27a2", "\u00d8": "\u27a2", "\u00a7": "\u25aa",
    "\u00b7": "\u2022", "l": "\u2022", "n": "\u25aa", "u": "\u25aa",
}


def dingbat_mark(ch: str) -> Optional[str]:
    """The bullet a dingbat byte stands for.

    The map covers the bytes seen so far. A byte outside it is still a mark
    printed in a symbol font, and the Learning Objectives of this book use two
    such bytes: unmapped they were dropped as control characters and seven
    objectives were published as three paragraphs. Anything that is not a
    letter or a digit is taken to be the bullet it looks like.
    """
    if not ch:
        return None
    if ch in DINGBAT_MAP:
        return DINGBAT_MAP[ch]
    if ch.isalnum() or ch.isspace():
        return None
    return "\u2022"

BULLET_START = re.compile(r"^\s*[\u2022\u25cf\u25aa\u2023\u2043\u25e6\-\*\u00b7\u25c6\u00be]\s+")
NUMBER_START = re.compile(r"^\s*(\d{1,2}|[ivxlIVXL]{1,5}|[a-zA-Z])[\.\)]\s+")
SECTION_START = re.compile(r"^\s*\d{1,2}(?:\.\d{1,2}){0,3}\s+\S")
SENTENCE_END = (".", "!", "?", ":", ";", "\u2026")


@dataclass
class Line:
    bbox: Tuple[float, float, float, float]
    text: str
    idx: int = -1
    runs: List[Run] = field(default_factory=list)
    max_size: float = 0.0
    bold_frac: float = 0.0
    color: Optional[str] = None
    band: int = 0
    column: int = 0
    box: int = -1
    is_title: bool = False
    spans: List[dict] = field(default_factory=list)
    is_fraction: bool = False

    @property
    def x0(self): return self.bbox[0]

    @property
    def y0(self): return self.bbox[1]

    @property
    def x1(self): return self.bbox[2]

    @property
    def y1(self): return self.bbox[3]

    @property
    def height(self): return self.bbox[3] - self.bbox[1]

    @property
    def width(self): return self.bbox[2] - self.bbox[0]


@dataclass
class Group:
    """A paragraph in the making: lines from one column, one box, one band."""
    lines: List[Line] = field(default_factory=list)
    box: int = -1
    band: int = 0
    column: int = 0
    is_title: bool = False

    def bbox(self):
        return (min(l.x0 for l in self.lines), min(l.y0 for l in self.lines),
                max(l.x1 for l in self.lines), max(l.y1 for l in self.lines))

    @property
    def y0(self): return min(l.y0 for l in self.lines)

    @property
    def x0(self): return min(l.x0 for l in self.lines)


# ---------------------------------------------------------------------------
# Reading the lines
# ---------------------------------------------------------------------------

def span_raw(span) -> str:
    """The span's characters before cleaning.

    clean() turns a byte like 0x8b into a space, which is right for corrupt
    text and wrong for a symbol font, where that byte is the bullet.
    """
    return (span.get("text") if "text" in span
            else "".join(c.get("c", "") for c in span.get("chars", []))) or ""


def span_text(span) -> str:
    raw = (span.get("text") if "text" in span
           else "".join(c.get("c", "") for c in span.get("chars", [])))
    return clean(raw or "", keep_breaks=False)


def _is_dingbat(font: str) -> bool:
    f = (font or "").lower()
    return any(k in f for k in DINGBAT_FONTS)


def _dingbat_marks(page_dict) -> List[Tuple[float, float, float, str]]:
    """Where a dingbat font actually printed a bullet."""
    marks: List[Tuple[float, float, float, str]] = []
    for blk in page_dict.get("blocks", []):
        if blk.get("type") != 0:
            continue
        for line in blk.get("lines", []):
            for span in line.get("spans", []):
                if not _is_dingbat(span.get("font", "")):
                    continue
                t = span_raw(span).strip()
                if t and dingbat_mark(t[0]):
                    bb = span.get("bbox") or (0, 0, 0, 0)
                    marks.append((bb[1], bb[2], bb[3], t[0]))
    return marks


def read_lines(page_dict) -> List[Line]:
    """Every text line on the page, in no particular order yet."""
    out: List[Line] = []
    marks = _dingbat_marks(page_dict)
    for blk in page_dict.get("blocks", []):
        if blk.get("type") != 0:
            continue
        for line in blk.get("lines", []):
            parts: List[str] = []
            runs: List[Run] = []
            spans: List[dict] = []
            pos = 0
            max_size = 0.0
            bold_chars = 0
            total = 0
            colors: Dict[str, int] = {}
            for span in line.get("spans", []):
                t = span_text(span)
                if not t:
                    continue
                font = span.get("font", "") or ""
                sbb = tuple(span.get("bbox") or (0, 0, 0, 0))
                if _is_dingbat(font):
                    t = "".join(dingbat_mark(c) or "" for c in span_raw(span))
                    if not t:
                        continue
                elif t.strip() and t.strip()[0] in DINGBAT_MAP \
                        and (sbb[2] - sbb[0]) < 5.0:
                    # a body font copy of the same glyph printed under the
                    # dingbat: one bullet, not two
                    if any(abs(my0 - sbb[1]) < 4 and abs(mx1 - sbb[0]) < 8
                           and mc == t.strip()[0] for my0, mx1, _my1, mc in marks):
                        continue
                flags = int(span.get("flags", 0))
                bold = bool(flags & BOLD_FLAG) or bool(BOLD_NAME.search(font))
                ital = bool(flags & ITALIC_FLAG) or bool(ITAL_NAME.search(font))
                size = float(span.get("size", 0))
                max_size = max(max_size, size)
                col = span.get("color", 0)
                hexcol = f"{col:06X}" if isinstance(col, int) else None
                if hexcol and hexcol != "000000":
                    colors[hexcol] = colors.get(hexcol, 0) + len(t)
                run = Run(s=pos, e=pos + len(t), bold=bold, italic=ital,
                          superscript=bool(flags & SUPER_FLAG),
                          color=hexcol if hexcol != "000000" else None,
                          font=font or None)
                runs.append(run)
                chars = []
                for ch in span.get("chars", []) or []:
                    c = clean(ch.get("c", ""), keep_breaks=False)
                    if not c:
                        continue
                    chars.append({"c": c, "bbox": tuple(ch.get("bbox") or sbb),
                                  "origin": tuple(ch.get("origin") or (sbb[0], sbb[3]))})
                spans.append({"bbox": sbb, "text": t, "chars": chars, "bold": bold,
                              "italic": ital,
                              "superscript": bool(flags & SUPER_FLAG),
                              "color": hexcol if hexcol != "000000" else None,
                              "font": font or None, "size": size})
                parts.append(t)
                pos += len(t)
                total += len(t)
                if bold:
                    bold_chars += len(t)
            text = "".join(parts)
            if not text.strip():
                continue
            dominant = max(colors, key=colors.get) if colors else None
            if dominant and colors[dominant] < total * 0.6:
                dominant = None
            out.append(Line(bbox=tuple(line["bbox"]), text=text, runs=runs,
                            max_size=max_size,
                            bold_frac=(bold_chars / total) if total else 0.0,
                            color=dominant, spans=spans))
    return _drop_shadow_lines(_reseat_bullets(out))


_BULLET_ONLY = re.compile(r"^[\u2022\u25aa\u27a2\u25c6]+$")


def _reseat_bullets(lines: List[Line]) -> List[Line]:
    """Put a bullet back on the line it was printed against.

    A symbol font sits lower than the text it marks, low enough that the
    extractor files the bullet on its own or with the NEXT line. The list then
    reads with every bullet one item late and the last item with none. Each
    stray bullet is given to the text line it was printed beside.
    """
    strays = [i for i, l in enumerate(lines)
              if l.spans and _BULLET_ONLY.match((l.text or "").strip())]
    if not strays:
        return lines
    taken = set()
    dropped = set()
    for i in strays:
        b = lines[i]
        bc = (b.y0 + b.y1) / 2.0
        best, best_d = None, 1e9
        for j, l in enumerate(lines):
            if j == i or j in taken or j in strays:
                continue
            if not l.spans or not (l.text or "").strip():
                continue
            if l.x1 <= b.x0 or l.x0 > b.x1 + 40:
                continue                   # the text it marks sits beside it
            d = abs(((l.y0 + l.y1) / 2.0) - bc)
            if d < best_d:
                best, best_d = j, d
        if best is None or best_d > 14.0:
            continue
        taken.add(best)
        mark = dict(lines[i].spans[0])
        lines[best] = _line_from_spans([mark] + list(lines[best].spans),
                                       lines[best])
        dropped.add(i)
    return [l for j, l in enumerate(lines) if j not in dropped]


def _line_from_spans(spans: List[dict], src: Line) -> Line:
    """Rebuild one line from a subset of its spans."""
    parts: List[str] = []
    runs: List[Run] = []
    pos = 0
    bold_chars = 0
    total = 0
    max_size = 0.0
    colors: Dict[str, int] = {}
    for sp in spans:
        t = sp["text"]
        runs.append(Run(s=pos, e=pos + len(t), bold=sp["bold"],
                        italic=sp["italic"], superscript=sp["superscript"],
                        color=sp["color"], font=sp["font"]))
        parts.append(t)
        pos += len(t)
        total += len(t)
        if sp["bold"]:
            bold_chars += len(t)
        max_size = max(max_size, float(sp.get("size") or 0.0))
        if sp["color"]:
            colors[sp["color"]] = colors.get(sp["color"], 0) + len(t)
    bb = (min(s["bbox"][0] for s in spans), min(s["bbox"][1] for s in spans),
          max(s["bbox"][2] for s in spans), max(s["bbox"][3] for s in spans))
    dominant = max(colors, key=colors.get) if colors else None
    if dominant and colors[dominant] < total * 0.6:
        dominant = None
    return Line(bbox=bb, text="".join(parts), runs=runs,
                max_size=max_size or src.max_size,
                bold_frac=(bold_chars / total) if total else 0.0,
                color=dominant, spans=list(spans))


def _span_chars(sp: dict) -> List[dict]:
    return sp.get("chars") or []


def _rebuild_span(sp: dict, keep: List[dict]) -> Optional[dict]:
    """The same span with some of its characters removed."""
    if not keep:
        return None
    out = dict(sp)
    out["chars"] = keep
    out["text"] = "".join(c["c"] for c in keep)
    out["bbox"] = (min(c["bbox"][0] for c in keep), min(c["bbox"][1] for c in keep),
                   max(c["bbox"][2] for c in keep), max(c["bbox"][3] for c in keep))
    return out if out["text"] else None


_LEG_BAD_START = ("=", "+", "\u00d7", "/", ")", "<", ">", "\u2212")


def _leg_ok(text: str) -> bool:
    """A leg is a term. A fragment that opens with an operator is the text
    beside the fraction, picked up by accident."""
    t = (text or "").strip()
    if not t or t.startswith(_LEG_BAD_START) or t.endswith(("=", "+")):
        return False
    return any(ch.isalnum() for ch in t)


def _chars_text(recs) -> str:
    """Characters back into text, with the spaces the gaps imply."""
    out: List[str] = []
    last = None
    for _l, _sp, ch in sorted(recs, key=lambda r: r[2]["bbox"][0]):
        if last is not None and ch["bbox"][0] - last > 1.4:
            out.append(" ")
        out.append(ch["c"])
        last = ch["bbox"][2]
    return "".join(out).strip()


def _run_over_rule(recs, rx0: float, rx1: float):
    """Only the unbroken run of glyphs that actually sits on the rule.

    Text beside the fraction shares the baseline and can fall inside the
    rule's x range. A leg is contiguous; its neighbours are separated by a
    word space, so the run that covers the rule best is the leg.
    """
    if not recs:
        return []
    ordered = sorted(recs, key=lambda r: r[2]["bbox"][0])
    runs: List[list] = [[ordered[0]]]
    for rec in ordered[1:]:
        prev = runs[-1][-1][2]["bbox"][2]
        if rec[2]["bbox"][0] - prev <= 4.0:
            runs[-1].append(rec)
        else:
            runs.append([rec])
    mid = (rx0 + rx1) / 2
    best, best_score = [], 0.0
    for run in runs:
        a = min(r[2]["bbox"][0] for r in run)
        b = max(r[2]["bbox"][2] for r in run)
        cov = max(0.0, min(b, rx1) - max(a, rx0))
        if cov <= 0:
            continue
        score = cov / max(1.0, min(b - a, rx1 - rx0))
        if a - 1 <= mid <= b + 1:
            score += 1.0          # the run the rule is actually drawn under
        if score > best_score:
            best, best_score = run, score
    if best_score < 0.5:
        return []
    return best


def fold_fraction_lines(lines: List[Line], rules, cfg=None) -> Tuple[List[Line], int]:
    """Rebuild a stacked fraction from the characters around its rule.

    The rule is real evidence, but the legs are not whole lines and not whole
    spans either: the extractor groups by baseline, so the denominator of one
    fraction arrives inside the same span as the words beside it
    (``4 radian = 180``). Characters carry their own baseline origin, so the
    glyphs sitting on the rule can be taken and nothing else moves.
    """
    if not rules:
        return lines, 0
    max_w = getattr(cfg, "fraction_rule_max_width_pt", 170.0) if cfg else 170.0
    up = getattr(cfg, "fraction_leg_max_rise_pt", 13.0) if cfg else 13.0
    down = getattr(cfg, "fraction_leg_max_drop_pt", 17.0) if cfg else 17.0
    max_chars = getattr(cfg, "fraction_leg_max_chars", 40) if cfg else 40

    index: List[Tuple[Line, dict, dict]] = []
    for l in lines:
        for sp in l.spans:
            for ch in _span_chars(sp):
                index.append((l, sp, ch))
    if not index:
        return lines, 0

    taken: set = set()
    made: List[Line] = []
    hosts: Dict[int, List[Line]] = {}
    folded = 0
    for y, rx0, rx1 in sorted(rules, key=lambda r: r[0]):
        width = rx1 - rx0
        if width <= 1 or width > max_w:
            continue
        above: List[Tuple[Line, dict, dict]] = []
        below: List[Tuple[Line, dict, dict]] = []
        for rec in index:
            _l, _sp, ch = rec
            if id(ch) in taken or not ch["c"].strip():
                continue
            cx = (ch["bbox"][0] + ch["bbox"][2]) / 2
            if cx < rx0 - 1.5 or cx > rx1 + 1.5:
                continue
            oy = ch["origin"][1]
            if 0 < y - oy <= up:
                above.append(rec)
            elif 0 < oy - y <= down:
                below.append(rec)
        if not above or not below:
            continue
        above = _run_over_rule(above, rx0, rx1)
        below = _run_over_rule(below, rx0, rx1)
        if not above or not below:
            continue
        num = _chars_text(above)
        den = _chars_text(below)
        if not num or not den or len(num) > max_chars or len(den) > max_chars:
            continue
        if not _leg_ok(num) or not _leg_ok(den):
            continue
        picked = above + below
        boxes = [c["bbox"] for _l, _s, c in picked]
        bb = (min(b[0] for b in boxes), min(b[1] for b in boxes),
              max(b[2] for b in boxes), max(b[3] for b in boxes))
        src = above[0][0]
        font = above[0][1].get("font")
        text = f"({num}) / ({den})"
        line = Line(bbox=bb, text=text,
                    runs=[Run(s=0, e=len(text), bold=False, italic=False,
                              superscript=False, color=None, font=font)],
                    max_size=src.max_size, bold_frac=0.0, color=None,
                    spans=[{"bbox": bb, "text": text, "chars": [],
                            "bold": False, "italic": False,
                            "superscript": False, "color": None,
                            "font": font, "size": above[0][1].get("size", 0.0)}])
        line.is_fraction = True
        hosts.setdefault(id(src), []).append(line)
        made.append(line)
        taken.update(id(c) for _l, _s, c in picked)
        folded += 1

    if not folded:
        return lines, 0

    out: List[Line] = []
    placed: set = set()
    for l in lines:
        changed = False
        spans: List[dict] = []
        for sp in l.spans:
            chars = _span_chars(sp)
            if not chars:
                spans.append(sp)
                continue
            keep = [c for c in chars if id(c) not in taken]
            if len(keep) == len(chars):
                spans.append(sp)
                continue
            changed = True
            rebuilt = _rebuild_span(sp, keep)
            if rebuilt is not None:
                spans.append(rebuilt)
        mine = hosts.get(id(l), [])
        if spans and mine:
            # the fraction belongs in the line it was printed in, at its own
            # x position, not as a block of its own
            for f in mine:
                spans.append(f.spans[0])
                placed.add(id(f))
            spans.sort(key=lambda sp: sp["bbox"][0])
            merged = _line_from_spans(spans, l)
            merged.is_fraction = True
            out.append(merged)
            continue
        if not changed:
            out.append(l)
        elif spans:
            out.append(_line_from_spans(spans, l))
    out.extend(f for f in made if id(f) not in placed)
    out.sort(key=lambda l: (round(l.y0, 1), l.x0))
    return out, folded


def split_at_gutters(lines: List[Line], gutters) -> List[Line]:
    """One printed row that carries both columns is two lines, not one.

    PyMuPDF groups by baseline, so a row of a two column page arrives as a
    single line holding the left column and the right column spliced together.
    Assigning that line to a column cannot undo the splice: it has to be cut,
    and it is only safe to cut where no glyph sits inside the gutter.
    """
    if not gutters:
        return lines
    out: List[Line] = []
    for l in lines:
        cut = None
        for a, b in gutters:
            if l.x0 >= a - 1 or l.x1 <= b + 1 or not l.spans:
                continue
            if any(s["bbox"][2] > a and s["bbox"][0] < b for s in l.spans):
                continue          # a glyph sits in the gutter: genuinely full width
            left = [s for s in l.spans if s["bbox"][2] <= a]
            right = [s for s in l.spans if s["bbox"][0] >= b]
            if left and right:
                cut = (left, right)
                break
        if cut:
            out.append(_line_from_spans(cut[0], l))
            out.append(_line_from_spans(cut[1], l))
        else:
            out.append(l)
    return out


def _drop_shadow_lines(lines: List[Line]) -> List[Line]:
    """A grey copy printed under coloured text is not a second line."""
    out: List[Line] = []
    for l in lines:
        twin = next((o for o in out
                     if abs(o.x0 - l.x0) <= 2.5 and abs(o.y0 - l.y0) <= 2.5
                     and _norm(o.text) == _norm(l.text) and _norm(l.text)),
                    None)
        if twin is not None:
            continue
        out.append(l)
    return out


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


# ---------------------------------------------------------------------------
# Grouping  (rules 12, 17 to 20)
# ---------------------------------------------------------------------------

def group_lines(lines: List[Line], lay: Layout, page_width: float,
                cfg: Config) -> List[Group]:
    """Join lines into paragraphs, never across a column, box or band."""
    titles = {b.title_line for b in lay.boxes if b.title_line is not None}
    for i, l in enumerate(lines):
        l.idx = i
        l.band = lay.line_band[i] if i < len(lay.line_band) else 0
        l.column = lay.line_col[i] if i < len(lay.line_col) else 0
        l.box = lay.line_box[i] if i < len(lay.line_box) else -1
        l.is_title = i in titles

    ordered = sorted(lines, key=lambda l: (l.band, l.box, l.column,
                                           round(l.y0, 1), round(l.x0, 1)))
    groups: List[Group] = []
    for l in ordered:
        if not l.is_title and groups and _joins(groups[-1], l, lay,
                                                page_width, cfg):
            groups[-1].lines.append(l)
            continue
        g = Group(lines=[l], box=l.box, band=l.band, column=l.column)
        g.is_title = l.is_title
        groups.append(g)
    return groups


def _joins(g: Group, l: Line, lay: Layout, page_width: float,
           cfg: Config) -> bool:
    prev = g.lines[-1]
    if g.is_title:
        return False
    if l.band != g.band or l.column != g.column or l.box != g.box:
        return False                       # rules 15 and 19
    if abs(l.max_size - prev.max_size) > cfg.body_size_tolerance * 2:
        return False                       # rule 19: size change
    # Rule 24 in spirit: a bold label followed by ordinary text is a run-in
    # heading, not the first line of that paragraph.
    if prev.bold_frac > 0.6 and l.bold_frac < 0.4:
        return False
    if l.bold_frac > 0.6 and prev.bold_frac < 0.4:
        return False
    gap = l.y0 - prev.y1
    lh = max(6.0, prev.height)
    if gap > lh * cfg.line_join_max_gap_pt or gap < -lh:
        return False
    if BULLET_START.match(l.text) or NUMBER_START.match(l.text):
        return False
    if SECTION_START.match(l.text):
        return False

    inside_narrow = _narrow_box(l.box, lay, page_width, cfg)
    if inside_narrow:
        return True                        # rule 12

    prev_text = prev.text.rstrip()
    if prev_text.endswith("-"):
        return True                        # rule 18
    if prev_text.endswith(SENTENCE_END):
        # a new sentence still continues the same paragraph when the line is
        # full width and the next one starts at the paragraph's left edge
        return (abs(l.x0 - g.x0) <= 4.0
                and prev.width > (g.bbox()[2] - g.bbox()[0]) * 0.75)
    nxt = l.text.lstrip()
    if not nxt:
        return False
    first = nxt[0]
    if first.islower() or first in ",);:\u2019'\u201d":
        return True                        # rule 17
    # capitalised continuation of an unfinished line, in the same block shape
    return abs(l.x0 - prev.x0) <= 4.0 and not _list_shaped(g, l, cfg)


def _list_shaped(g: Group, l: Line, cfg: Config) -> bool:
    """Rule 20: several short capitalised lines in a row are a list."""
    if len(l.text.strip()) > 34:
        return False
    recent = g.lines[-2:]
    short = sum(1 for r in recent if len(r.text.strip()) <= 34)
    return short >= len(recent) and len(recent) >= 1


def _narrow_box(box_idx: int, lay: Layout, page_width: float,
                cfg: Config) -> bool:
    if box_idx < 0 or box_idx >= len(lay.boxes):
        return False
    b = lay.boxes[box_idx]
    return b.width > 0 and b.width < page_width * cfg.narrow_box_frac


# ---------------------------------------------------------------------------
# Ordering the finished groups  (rules 13, 9, 11)
# ---------------------------------------------------------------------------

def order_groups(groups: List[Group], lay: Layout) -> List[Group]:
    """Bands top to bottom, boxes whole, then column by column."""
    box_start: Dict[int, Tuple[int, float, float]] = {}
    for g in groups:
        if g.box < 0:
            continue
        cur = box_start.get(g.box)
        key = (g.band, g.y0, g.x0)
        if cur is None or key < cur:
            box_start[g.box] = key

    def sort_key(g: Group):
        if g.box >= 0:
            band, y0, x0 = box_start[g.box]
            band_col = lay.bands[band].column_of(
                (x0, y0, x0 + 1, y0 + 1)) if band < len(lay.bands) else 0
            # a box is one unit placed where it starts, ordered internally
            return (band, band_col, y0, 0, g.y0, g.x0)
        return (g.band, g.column, g.y0, 1, g.y0, g.x0)

    ordered = sorted(groups, key=sort_key)
    return _promote_badge_titles(ordered, lay)


def _title_parent(g, lay):
    """The panel a title badge belongs to, found by geometry rather than by
    box index: the badge sits inside the panel, and the wrapped text around it
    often belongs to no box at all."""
    for b in lay.boxes:
        if b.title_line is None:
            continue
        if any(l.idx == b.title_line for l in g.lines):
            for parent in lay.boxes:
                if parent is b or parent.kind == "badge":
                    continue
                if parent.contains(b.rect, tol=8.0):
                    return parent.rect
            return b.rect
    return None


def _promote_badge_titles(groups: List[Group], lay: Layout) -> List[Group]:
    """Rule 11: the word inside the badge is the box title, so it comes first
    however far down the page it physically sits.

    This is the PREFACE case: the word is printed in a circle halfway down the
    panel and the paragraph wraps around it, so read positionally it lands in
    the middle of a sentence.
    """
    titles = [g for g in groups if g.is_title]
    if not titles:
        return groups
    out = list(groups)
    for t in titles:
        parent = _title_parent(t, lay)
        members = []
        if parent is not None:
            members = [g for g in out
                       if g is not t and _within(g.bbox(), parent, tol=6.0)]
        if not members:
            # The badge sits in its own little shape with nothing else inside
            # it, so there is no panel to be the title of. It is still the
            # heading of whatever it is printed beside: take the first group
            # its own height overlaps. This is the PREFACE and the HOW TO USE
            # THE BOOK case, where the badge is a circle to one side and the
            # text wraps around it.
            tb = t.bbox()
            members = [g for g in out
                       if g is not t and not g.is_title
                       and min(tb[3], g.bbox()[3]) - max(tb[1], g.bbox()[1]) > 2]
        if not members:
            continue
        first = min(out.index(m) for m in members)
        if out.index(t) > first:
            out.remove(t)
            out.insert(first, t)
    return out


def _within(r, box, tol: float = 2.0) -> bool:
    return (r[0] >= box[0] - tol and r[2] <= box[2] + tol
            and r[1] >= box[1] - tol and r[3] <= box[3] + tol)


def pair_label_rows(groups: List[Group], min_pairs: int = 3) -> List[Group]:
    """A glossary set as bold terms beside plain definitions.

    The layout reads the terms as one column and the definitions as another,
    and the definitions, printed one under the other with nothing between
    them, join into a single paragraph: five definitions read as one run-on
    sentence under "Calibration" and looked missing. Rows are rebuilt by
    baseline: each bold term takes the definition lines from its own baseline
    down to the next term's.
    """
    out = list(groups)
    for r in [g for g in groups if len(g.lines) >= min_pairs]:
        if r not in out:
            continue
        if sum(l.bold_frac for l in r.lines) / len(r.lines) > 0.4:
            continue
        terms = []
        for t in out:
            if t is r or len(t.lines) != 1:
                continue
            tl = t.lines[0]
            if tl.bold_frac < 0.6 or len(tl.text.split()) > 5:
                continue
            if not (0 <= min(l.x0 for l in r.lines) - tl.x1 <= 120):
                continue
            hit = next((i for i, l in enumerate(r.lines)
                        if abs(l.y1 - tl.y1) <= 3.0), None)
            if hit is not None:
                terms.append((hit, t))
        if len(terms) < min_pairs:
            continue
        xs = [t.lines[0].x0 for _, t in terms]
        if max(xs) - min(xs) > 4:
            continue
        terms.sort(key=lambda p: p[0])
        starts = [h for h, _ in terms]
        pieces: List[Group] = []
        if starts[0] > 0:
            pieces.append(Group(lines=r.lines[:starts[0]], box=r.box,
                                band=r.band, column=r.column))
        for k, (h, t) in enumerate(terms):
            end = starts[k + 1] if k + 1 < len(starts) else len(r.lines)
            g = Group(lines=[t.lines[0]] + r.lines[h:end], box=t.box,
                      band=t.band, column=t.column)
            pieces.append(g)
            out.remove(t)
        idx = out.index(r)
        out[idx:idx + 1] = pieces
    # a term whose definition fits on one line: the two single line groups
    # sitting on one baseline become one row
    singles = [g for g in out if len(g.lines) == 1]
    for t in singles:
        if t not in out:
            continue
        tl = t.lines[0]
        if tl.bold_frac < 0.6 or len(tl.text.split()) > 5:
            continue
        mate = next((d for d in singles if d is not t and d in out
                     and d.lines[0].bold_frac < 0.4
                     and abs(d.lines[0].y1 - tl.y1) <= 3.0
                     and 0 <= d.lines[0].x0 - tl.x1 <= 120), None)
        if mate is None:
            continue
        # only where the page already shows the glossary pattern
        rows = sum(1 for g in out if len(g.lines) >= 2
                   and g.lines[0].bold_frac >= 0.6
                   and abs(g.lines[0].x0 - tl.x0) <= 4)
        if rows < min_pairs:
            continue
        t.lines.append(mate.lines[0])
        out.remove(mate)
    return out
