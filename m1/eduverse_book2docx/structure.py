"""Book-wide structure decisions.

Heading levels come from a font-size histogram built across the WHOLE book,
never per page. Size alone never decides: weight, colour, length and position
all vote. Reading order comes from column detection, not from raw y order.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

from .config import Config
from .schema import Block, Page, Run
from .textclean import font_family, is_light

BULLET_RE = re.compile(r"^\s*([\u2022\u25cf\u25aa\u2023\u2043\-\*\u00b7])\s+")
NUMBER_RE = re.compile(r"^\s*(\d{1,2}|[ivxlIVXL]{1,5}|[a-zA-Z])[\.\)]\s+")
SECTION_RE = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){0,3})\s+\S")
FURNITURE_RE = re.compile(
    r"^\s*(?:page\s*)?\d{1,4}\s*$|^\s*[-\u2013]\s*\d{1,4}\s*[-\u2013]\s*$",
    re.I)
PRINTMARK_RE = re.compile(
    r"(indesign|cs\d|untitled-\d|\.indd|forms?\s*\d+|crop\s*mark)", re.I)
# A web address in the margin is furniture. The publisher's address printed on
# the imprint page is content, so the position decides, not the "www".
URL_RE = re.compile(r"^\s*(?:www\.|https?://)\S+\s*$", re.I)
# "First Edition  -  2019" is a row of an imprint table, not a bulleted list.
DASH_NUMBER_RE = re.compile(r"^\s*[-\u2013\u2022]\s*\d{1,4}\s*$")


# ---------------------------------------------------------------------------
# Font size profile
# ---------------------------------------------------------------------------

class SizeProfile:
    """Book-wide size histogram, weighted by characters not by line count.

    Rules 21 and 22: front matter is skipped, because a cover and a contents
    page use display type that has nothing to do with the heading scale, and a
    size that appears on only a page or two is a one-off, not a level.
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._hist: Counter = Counter()
        self._pages: Dict[float, set] = {}
        self.body_size: float = 11.0
        self.levels: List[float] = []
        self.skipped_pages: int = 0
        self._fonts: Counter = Counter()
        self.body_font: Optional[str] = None

    def observe(self, size: float, chars: int, page: int = 0) -> None:
        if not size or not chars:
            return
        key = round(size * 2) / 2
        self._hist[key] += chars
        self._pages.setdefault(key, set()).add(page)

    def observe_font(self, family: str, chars: int) -> None:
        if family and chars:
            self._fonts[family] += chars

    def finalise(self) -> None:
        if self._fonts:
            self.body_font = self._fonts.most_common(1)[0][0]
        if not self._hist:
            return
        self.body_size = self._hist.most_common(1)[0][0]
        bigger = sorted(
            {s for s, w in self._hist.items()
             if s > self.body_size * self.cfg.heading_min_size_ratio and w > 0
             and len(self._pages.get(s, ())) >= self.cfg.heading_min_pages},
            reverse=True)
        # merge sizes within the tolerance band
        merged: List[float] = []
        for s in bigger:
            if merged and abs(merged[-1] - s) <= self.cfg.body_size_tolerance:
                continue
            merged.append(s)
        self.levels = merged[: self.cfg.max_heading_levels]

    def level_for(self, size: float) -> Optional[int]:
        for idx, lv in enumerate(self.levels, start=1):
            if size >= lv - self.cfg.body_size_tolerance:
                return idx
        return None

    def is_body(self, size: float) -> bool:
        return abs(size - self.body_size) <= self.cfg.body_size_tolerance

    def summary(self) -> Dict:
        return {"body_size": self.body_size, "heading_sizes": self.levels,
                "body_font": self.body_font,
                "front_matter_pages_skipped": self.skipped_pages,
                "histogram": dict(sorted(self._hist.items()))}


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def is_furniture(text: str, block: Block, page: Page, cfg: Config) -> Optional[str]:
    t = (text or "").strip()
    if not t:
        return None
    band = max(28.0, page.height_pt * 0.065)
    top = block.y1 < min(page.margins_pt[1] + 12.0, band)
    bottom = block.y0 > page.height_pt - max(band, page.margins_pt[3] + 12.0)
    if FURNITURE_RE.match(t) and (top or bottom):
        return "furniture_pageno"
    if PRINTMARK_RE.search(t) and len(t) < 60:
        return "furniture_printmark"
    if URL_RE.match(t) and (top or bottom) and len(t) < 60:
        return "furniture_printmark"
    if (top or bottom) and len(t) < 70 and t.count(" ") <= 8 \
            and not t.endswith((".", ":", "?")):
        return "furniture_header"
    return None


def classify_text_block(block: Block, page: Page, profile: SizeProfile,
                        cfg: Config, max_size: float, is_bold: bool,
                        color: Optional[str]) -> None:
    """Set block.type, level, indent_level and align in place."""
    t = (block.text or "").strip()
    if not t:
        block.type = "page_furniture"
        return

    reason = is_furniture(t, block, page, cfg)
    if reason:
        block.type = "page_furniture"
        block.flags.append(reason)
        return

    if DASH_NUMBER_RE.match(t):
        block.type = "paragraph"
        return

    # A short bold line set in the book's display face, or knocked out white
    # on a coloured band, is a section label whatever its size. This book sets
    # "Learning Objectives", "Activity 1", "1.3 Clocks" and "1. Analog clocks"
    # in Verdana Bold at body size; size alone voted them down to body text.
    label_level = _display_label_level(block, t, profile, cfg, max_size,
                                       is_bold, color)
    if label_level is not None:
        block.type = "heading"
        if SECTION_RE.match(t) and _is_section_number(t):
            depth = SECTION_RE.match(t).group(1).count(".") + 1
            label_level = max(1, min(depth, cfg.max_heading_levels))
            block.block_kind = "numbered"
        else:
            block.block_kind = "label"
        block.level = label_level
        block.heading_size = max_size
        return

    if BULLET_RE.match(t):
        block.type = "list_item"
        block.block_kind = "bullet"
        block.indent_level = _indent_level(block, page)
        return
    if NUMBER_RE.match(t) and not SECTION_RE.match(t) and len(t) < 400:
        block.type = "list_item"
        block.block_kind = "number"
        block.indent_level = _indent_level(block, page)
        return

    lvl = profile.level_for(max_size)
    short = len(t) <= cfg.heading_max_chars
    no_stop = not t.rstrip().endswith((".", ",", ";"))
    numbered = bool(SECTION_RE.match(t))

    # A heading is words. A line of digits, degrees and compass points printed
    # large is a map label or the bottom half of a fraction, and calling it a
    # heading is what filled H1 with "36 N S PAKISTAN" and "2 x 108 = 1.5".
    #
    # And a heading is never SMALLER than the body text. The labels printed
    # across a map are two and a half point; nothing that size announces a
    # section.
    if not _reads_as_words(t) or max_size < profile.body_size * 0.95:
        block.type = "paragraph"
        block.align = _align(block, page)
        return

    # Rule 23: a numbered heading always wins. The number of dots gives the
    # level, whatever its size, because a book's own numbering is a stronger
    # statement of structure than its type scale.
    numbered = numbered and _is_section_number(t)

    if numbered and short and (is_bold or lvl is not None or color):
        block.type = "heading"
        depth = SECTION_RE.match(t).group(1).count(".") + 1
        block.level = max(1, min(depth, cfg.max_heading_levels))
        block.heading_size = max_size
        block.block_kind = "numbered"
        return

    votes = 0
    if lvl is not None:
        votes += 2
    if is_bold:
        votes += 1
    if color:
        votes += 1
    if numbered:
        votes += 1
    if short and no_stop:
        votes += 1

    if votes >= 3 and short:
        if lvl is None:
            # Body sized but bold or coloured. This is a run-in heading, and it
            # belongs at the deepest level the book actually uses. Inventing a
            # new level here is what turns every bold label in the book into an
            # H4 and flattens the real hierarchy.
            if not (is_bold or numbered) or votes < 4:
                block.type = "paragraph"
                block.align = _align(block, page)
                return
            lvl = max(1, min(len(profile.levels), cfg.max_heading_levels)) or 1
        block.type = "heading"
        block.level = lvl
        block.heading_size = max_size
        return

    block.type = "paragraph"
    block.align = _align(block, page)


def _dominant_family(block: Block) -> Optional[str]:
    weights: Dict[str, int] = {}
    for r in block.runs or []:
        fam = font_family(r.font or "")
        if fam:
            weights[fam] = weights.get(fam, 0) + max(0, r.e - r.s)
    if not weights:
        return None
    return max(weights, key=weights.get)


def _run_color(block: Block) -> Optional[str]:
    weights: Dict[str, int] = {}
    for r in block.runs or []:
        if r.color:
            weights[r.color] = weights.get(r.color, 0) + max(0, r.e - r.s)
    return max(weights, key=weights.get) if weights else None


def _display_label_level(block: Block, t: str, profile: "SizeProfile",
                         cfg: Config, max_size: float, is_bold: bool,
                         color: Optional[str]) -> Optional[int]:
    """Heading level for a styled section label, or None."""
    if not is_bold and block.runs:
        tot = sum(max(0, r.e - r.s) for r in block.runs)
        bold = sum(max(0, r.e - r.s) for r in block.runs if r.bold)
        is_bold = tot > 0 and bold >= tot * 0.6
    if not is_bold or len(t) > min(cfg.heading_max_chars, 64):
        return None
    if t.rstrip().endswith((".", ",", ";", ":")):
        return None
    if len(t.split()) > 8 or not _reads_as_words(t):
        return None
    if max_size and max_size < profile.body_size * 0.9:
        return None                    # map and diagram labels are smaller
    fam = _dominant_family(block)
    display = bool(fam and profile.body_font and fam != profile.body_font
                   and fam not in ("wingdings", "symbol", "zapfdingbats"))
    col = color or _run_color(block)
    knockout = bool(col and is_light(col))
    if not (display or knockout):
        return None
    deepest = max(1, min(cfg.max_heading_levels, 3))
    return min(2, deepest) if knockout else deepest


_WORD_RE = re.compile(r"[A-Za-z\u0b80-\u0bff]{3,}")


_SECTION_TITLE_RE = re.compile(
    r"^\s*\d{1,2}(?:\.\d{1,2}){0,3}[\.\)]?[\s\u2002\u2003\u00a0]+"
    r"([A-Z\u0b80-\u0bff].*)$")


def _is_section_number(t: str) -> bool:
    """`3.8.1 Refractive Index` is a section number. `4 radian = 180` starts
    with a digit and is a line of arithmetic.

    The title after the number has to look like a title: it opens with a
    capital, it carries no equals sign, and it does not run on the way a
    sentence broken across lines does.
    """
    m = _SECTION_TITLE_RE.match(t or "")
    if not m:
        return False
    title = m.group(1).strip()
    if not title or "=" in title:
        return False
    if title.endswith((",", "and", "of", "the", "for", "is", "are")):
        return False
    return True


def _reads_as_words(t: str) -> bool:
    """True when the line is language, not a scattering of figures.

    One real word is enough, because "Unit 1" and "3.4 Light" are headings.
    A line with no word in it at all is a label off a diagram or a fraction
    leg, never a heading.
    """
    t = (t or "").strip()
    if not t:
        return False
    if not _WORD_RE.search(t):
        return False
    letters = sum(1 for c in t if c.isalpha())
    digits = sum(1 for c in t if c.isdigit())
    # a numbered heading carries its number, so digits are only damning when
    # they outweigh the words
    return letters >= 3 and letters >= digits


def _indent_level(block: Block, page: Page) -> int:
    left = page.margins_pt[0]
    return max(0, min(4, int((block.x0 - left) // 18)))


def _align(block: Block, page: Page) -> str:
    if page.columns > 1 and block.column not in (-1,):
        return "left"        # column geometry, not alignment
    left = page.margins_pt[0]
    right = page.width_pt - page.margins_pt[2]
    lgap = block.x0 - left
    rgap = right - block.x1
    if lgap > 24 and rgap > 24 and abs(lgap - rgap) < 12:
        return "center"
    if lgap > 48 and rgap < 12:
        return "right"
    return "left"


# ---------------------------------------------------------------------------
# Columns and reading order
# ---------------------------------------------------------------------------

def detect_columns(blocks: List[Block], page: Page, cfg: Config) -> int:
    """Kept for pages the layout engine did not handle: DOCX input and OCR.
    A native page already carries its column count from layout.analyse."""
    if page.columns and page.columns > 1:
        return page.columns
    """Vertical projection profile to find gutters."""
    text_blocks = [b for b in blocks
                   if b.type not in ("page_furniture", "figure", "table")
                   and b.width > 4]
    if len(text_blocks) < 3:
        return 1
    w = int(page.width_pt)
    if w <= 0:
        return 1
    hist = [0] * (w + 1)
    for b in text_blocks:
        for x in range(max(0, int(b.x0)), min(w, int(b.x1))):
            hist[x] += 1
    left = int(page.margins_pt[0])
    right = int(page.width_pt - page.margins_pt[2])
    if right <= left:
        return 1
    inner = hist[left:right]
    if not inner:
        return 1
    gutters: List[Tuple[int, int]] = []
    run_start = None
    for i, v in enumerate(inner):
        if v == 0:
            if run_start is None:
                run_start = i
        else:
            if run_start is not None and i - run_start >= cfg.column_gutter_min_pt:
                gutters.append((run_start + left, i + left))
            run_start = None
    if run_start is not None and len(inner) - run_start >= cfg.column_gutter_min_pt:
        gutters.append((run_start + left, right))
    span = right - left
    middle = [g for g in gutters
              if 0.2 * span < (g[0] - left) < 0.8 * span]
    # A gutter is only real if blocks actually sit side by side across it.
    confirmed = [g for g in middle if _side_by_side(text_blocks, g)]
    return min(len(confirmed) + 1, 3)


def _side_by_side(blocks: List[Block], gutter) -> bool:
    gx = (gutter[0] + gutter[1]) / 2
    lefts = [b for b in blocks if b.x1 <= gx]
    rights = [b for b in blocks if b.x0 >= gx]
    for a in lefts:
        for b in rights:
            if min(a.y1, b.y1) - max(a.y0, b.y0) > 8:
                return True
    return False


def assign_columns(blocks: List[Block], page: Page, ncols: int) -> None:
    if ncols <= 1:
        for b in blocks:
            b.column = 0
        return
    left = page.margins_pt[0]
    usable = page.width_pt - page.margins_pt[0] - page.margins_pt[2]
    colw = usable / ncols
    for b in blocks:
        if b.width > usable * 0.75:      # full-width block spans the columns
            b.column = -1
            continue
        centre = (b.x0 + b.x1) / 2
        b.column = max(0, min(ncols - 1, int((centre - left) // colw)))


def reading_order(blocks: List[Block], page: Page, ncols: int) -> List[Block]:
    """Full-width blocks act as horizontal band separators."""
    if not blocks:
        return []
    if ncols <= 1:
        return sorted(blocks, key=lambda b: (round(b.y0, 1), round(b.x0, 1)))
    spanning = sorted([b for b in blocks if b.column == -1], key=lambda b: b.y0)
    bounds = [-1e9] + [b.y0 for b in spanning] + [1e9]
    out: List[Block] = []
    for i in range(len(bounds) - 1):
        lo, hi = bounds[i], bounds[i + 1]
        band = [b for b in blocks
                if b.column != -1 and lo <= b.y0 < hi]
        for col in range(ncols):
            out.extend(sorted([b for b in band if b.column == col],
                              key=lambda b: (round(b.y0, 1), round(b.x0, 1))))
        if i < len(spanning):
            out.append(spanning[i])
    seen = set()
    ordered = []
    for b in out:
        if b.id not in seen:
            seen.add(b.id)
            ordered.append(b)
    for b in blocks:
        if b.id not in seen:
            ordered.append(b)
    return ordered


# ---------------------------------------------------------------------------
# Captions
# ---------------------------------------------------------------------------

def bind_captions(page: Page, cfg: Config) -> None:
    figures = [b for b in page.blocks if b.type in ("figure", "table")]
    if not figures:
        return
    for b in page.blocks:
        if b.type not in ("paragraph", "heading", "caption"):
            continue
        if b.caption_of:
            continue
        t = (b.text or "").strip().lower()
        if not is_numbered_caption(t, cfg.caption_prefixes):
            continue
        best, best_d = None, 1e9
        for f in figures:
            below = b.y0 - f.y1
            above = f.y0 - b.y1
            d = below if below >= -2 else (above if above >= -2 else 1e9)
            overlap = min(b.x1, f.x1) - max(b.x0, f.x0)
            if overlap <= 0:
                continue
            if 0 <= d < best_d:
                best, best_d = f, d
        if best is not None and best_d <= cfg.caption_max_gap_pt:
            b.type = "caption"
            b.level = None
            b.caption_of = best.id
            # remember which side it was printed on. This book prints table
            # captions above the table and figure captions below it, and a
            # caption moved to the other side reads as the next table's title.
            b.block_kind = "caption_above" if b.y1 <= best.y0 + 2 \
                else "caption_below"


_CAP_NUM_RE = re.compile(r"^[\s:.\-\u2002\u00a0]*\d")


def is_numbered_caption(low: str, prefixes) -> bool:
    """A caption names a numbered thing: Figure 1.7, Table 1.2. The word
    alone is not enough, or "Table of Contents" becomes a table's caption."""
    for pfx in sorted(prefixes, key=len, reverse=True):
        if low.startswith(pfx) and _CAP_NUM_RE.match(low[len(pfx):]):
            return True
    return False


def bind_figure_labels(page: Page, cfg: Config) -> int:
    """A word or two printed straight under a picture names that picture:
    "E - book" under a QR code. Bound as its caption so the pair travels
    together instead of three labels reading on after three codes."""
    figs = [b for b in page.blocks if b.type == "figure"]
    if not figs:
        return 0
    captioned = {b.caption_of for b in page.blocks if b.caption_of}
    others = [b for b in page.blocks if b.type not in ("figure", "figure_note")]
    n = 0
    for f in figs:
        if f.id in captioned:
            continue
        best = None
        for b in page.blocks:
            if b.type not in ("paragraph", "heading") or b.caption_of:
                continue
            t = (b.text or "").strip()
            if not t or len(t) > 24 or len(t.split()) > 3:
                continue
            if t.endswith((".", ",", ";", ":")) or SECTION_RE.match(t):
                continue
            gap = b.y0 - f.y1
            if gap < -3 or gap > 14:
                continue
            cx = (b.x0 + b.x1) / 2
            if not (f.x0 - 4 <= cx <= f.x1 + 4):
                continue
            if b.width > f.width * 1.8:
                continue
            between = any(o is not b and o.y0 >= f.y1 - 1 and o.y1 <= b.y0 + 1
                          and min(o.x1, b.x1) > max(o.x0, b.x0)
                          for o in others)
            if between:
                continue
            if best is None or b.y0 < best.y0:
                best = b
        if best is not None:
            best.type = "caption"
            best.level = None
            best.caption_of = f.id
            best.block_kind = "caption_below"
            captioned.add(f.id)
            n += 1
    return n


def order_with_captions(blocks: List[Block], cfg: Optional[Config] = None
                        ) -> List[Block]:
    """Keep every caption and description box with the thing it describes.

    A caption printed ABOVE its table stays above it. A caption printed below
    a figure stays below. The description box always follows the object.
    """
    keep_side = cfg.caption_keep_printed_side if cfg else True
    by_id = {b.id: b for b in blocks}
    before: Dict[str, List[Block]] = {}
    after: Dict[str, List[Block]] = {}
    # the description box comes first among the trailing blocks, so the order
    # stays figure, box, printed caption
    for b in blocks:
        if b.type == "figure_note" and b.caption_of in by_id:
            after.setdefault(b.caption_of, []).append(b)
    for b in blocks:
        if b.type == "caption" and b.caption_of in by_id:
            if keep_side and b.block_kind == "caption_above":
                before.setdefault(b.caption_of, []).append(b)
            else:
                after.setdefault(b.caption_of, []).append(b)
    attached = ({c.id for lst in before.values() for c in lst}
                | {c.id for lst in after.values() for c in lst})
    out: List[Block] = []
    for b in blocks:
        if b.id in attached:
            continue
        for c in before.get(b.id, []):
            out.append(c)
        out.append(b)
        for c in after.get(b.id, []):
            out.append(c)
    return out


def _mostly_inside(inner: List[float], outer: List[float],
                   frac: float = 0.75) -> bool:
    ix = min(inner[2], outer[2]) - max(inner[0], outer[0])
    iy = min(inner[3], outer[3]) - max(inner[1], outer[1])
    if ix <= 0 or iy <= 0:
        return False
    area = max(1e-6, (inner[2] - inner[0]) * (inner[3] - inner[1]))
    return (ix * iy) / area >= frac


def normalise_headings(book, cfg: Config) -> Dict[str, int]:
    """Two corrections that can only be made once the whole book is read.

    1. Text sitting inside a picture is a label on the picture, never a
       heading, however large it is printed.
    2. Heading LEVEL comes from the book's own numbering. A heading with no
       number that is printed larger than every numbered heading is a unit
       title and belongs at level 1; everything else without a number sits
       below the numbered levels, never above them.
    """
    demoted = relevelled = 0
    for page in book.pages:
        figs = [b for b in page.blocks if b.type == "figure" and b.bbox_pt]
        if not (cfg.heading_block_in_figure and figs):
            continue
        for b in page.blocks:
            if b.type != "heading" or not b.bbox_pt:
                continue
            hosts = [f for f in figs if _mostly_inside(b.bbox_pt, f.bbox_pt)]
            # a lone title in a badge or on a band is the badge's title: only
            # a picture carrying several words is a labelled drawing
            if hosts and all(
                    sum(1 for o in page.blocks
                        if o is not b and o.type in ("paragraph", "heading",
                                                     "list_item")
                        and _mostly_inside(o.bbox_pt, f.bbox_pt)) == 0
                    for f in hosts):
                continue
            if hosts:
                b.type = "paragraph"
                b.level = None
                b.flags.append("heading_inside_figure")
                demoted += 1

    if not cfg.heading_from_numbering:
        return {"demoted": demoted, "relevelled": 0}

    numbered = [b.heading_size for p in book.pages for b in p.blocks
                if b.type == "heading" and b.block_kind == "numbered"
                and b.heading_size]
    top = max(numbered) if numbered else None
    for p in book.pages:
        for b in p.blocks:
            if b.type != "heading" or b.block_kind == "numbered":
                continue
            if b.heading_size is None:
                continue
            if top is not None and b.heading_size > top + 0.5:
                new = 1
            else:
                new = max(2, b.level or 2)
            if new != b.level:
                b.level = new
                relevelled += 1
    return {"demoted": demoted, "relevelled": relevelled}


PAGE_NO_RE = re.compile(r"^\s*[\[\(]?\s*(?:page\s*)?"
                        r"(\d{1,4}|[ivxlcdmIVXLCDM]{1,7})\s*[\]\)]?\s*$")


def _furniture_key(text: str) -> str:
    """Normalise a candidate so the same running head matches across pages
    even though the page number inside it changes."""
    t = re.sub(r"\d+", "#", (text or "").strip().lower())
    return re.sub(r"\s+", " ", t)


def find_repeating_furniture(book, cfg) -> Dict[str, int]:
    """A short line that appears in the same band on many pages is furniture.

    This is the only reliable way to catch a running head or a side tab: it is
    not in the margin, it is not styled differently, it is just repeated.
    """
    band = 0.14
    seen: Dict[str, set] = {}
    pos: Dict[str, set] = {}
    for page in book.pages:
        top = page.height_pt * band
        bottom = page.height_pt * (1 - band)
        for b in page.blocks:
            if b.type not in ("paragraph", "heading", "list_item", "caption"):
                continue
            t = (b.text or "").strip()
            if not t or len(t) > 60:
                continue
            edge = b.y1 <= top or b.y0 >= bottom
            narrow = b.width <= page.width_pt * 0.10
            if not (edge or narrow):
                continue
            seen.setdefault(_furniture_key(t), set()).add(page.page)
            if edge:
                pos.setdefault(_position_key(t, b), set()).add(page.page)
    npages = max(1, len(book.pages))
    if npages < 4:
        return {}
    threshold = max(3, int(npages * 0.30))
    out = {k: len(v) for k, v in seen.items() if len(v) >= threshold}
    # A running footer that names the unit repeats only for as long as the
    # unit lasts, far short of 30% of the book. The same words at the same
    # spot on three pages are furniture however few pages that is.
    out.update({k: len(v) for k, v in pos.items()
                if len(v) >= cfg.furniture_min_same_spot_pages})
    return out


def _position_key(text: str, b: Block) -> str:
    return (f"@{_furniture_key(text)}|{int(round(b.x0 / 6))}|"
            f"{int(round(b.y0 / 6))}")


def drop_furniture(book, ledger, cfg) -> int:
    """Remove page numbers and repeating heads. Returns how many went."""
    repeats = find_repeating_furniture(book, cfg)
    removed = 0
    for page in book.pages:
        top = page.height_pt * 0.14
        bottom = page.height_pt * (1 - 0.14)
        keep = []
        for b in page.blocks:
            t = (b.text or "").strip()
            if b.type in ("paragraph", "heading", "list_item", "caption") and t:
                edge = b.y1 <= top or b.y0 >= bottom
                narrow = b.width <= page.width_pt * 0.10
                if edge and PAGE_NO_RE.match(t) and len(t) <= 7:
                    ledger.drop(b.id, page.page, "furniture_pageno", t, b.bbox_pt)
                    removed += 1
                    continue
                key = _furniture_key(t)
                if not ((edge or narrow) and key in repeats) and edge:
                    key = _position_key(t, b)
                if (edge or narrow) and key in repeats:
                    ledger.drop(b.id, page.page, "furniture_header",
                                f"{t[:40]} (on {repeats[key]} pages)",
                                b.bbox_pt)
                    removed += 1
                    continue
            keep.append(b)
        page.blocks = keep
    ledger.emitted -= removed
    return removed


def dedupe_text(page: Page, ledger, cfg: Config) -> int:
    """Remove a text block that repeats one already on the page.

    A PDF can hold the same string twice at nearly the same spot: a shadow
    layer under coloured text, a transparency fallback, or a block returned by
    two overlapping extraction paths. It reads as a stutter in the output and
    there is no way to tell from the text alone which copy is real, so the
    first one wins.
    """
    if not cfg.dedupe_text:
        return 0
    seen: List[Block] = []
    keep: List[Block] = []
    removed = 0
    for b in page.blocks:
        if b.type not in ("paragraph", "heading", "list_item", "caption"):
            keep.append(b)
            continue
        collapsed = _collapse_doubled(b.text)
        if collapsed is not None:
            cut = len(b.text) - len(collapsed)
            b.text = collapsed
            b.runs = [r for r in b.runs if r.e <= len(collapsed)]
            b.flags.append("doubled_text_collapsed")
        key = _dedupe_key(b.text)
        if len(key) < cfg.dedupe_text_min_chars:
            keep.append(b)
            continue
        twin = next((o for o in seen
                     if _dedupe_key(o.text) == key and _overlaps_or_near(o, b, cfg)),
                    None)
        if twin is not None:
            ledger.drop(b.id, page.page, "duplicate",
                        f"same text as {twin.id}: {b.text[:40]}", b.bbox_pt)
            removed += 1
            continue
        seen.append(b)
        keep.append(b)
    page.blocks = keep
    ledger.emitted -= removed
    return removed


def _collapse_doubled(text: str) -> Optional[str]:
    """One string printed twice inside a single block, from a shadow layer the
    extractor merged into one line group."""
    t = (text or "").strip()
    if len(t) < 8:
        return None
    for sep in (" ", ""):
        half = len(t) // 2
        a, b = t[:half].strip(), t[half:].strip()
        if a and _dedupe_key(a) == _dedupe_key(b):
            return a
    words = t.split()
    if len(words) >= 4 and len(words) % 2 == 0:
        h = len(words) // 2
        if [w.lower() for w in words[:h]] == [w.lower() for w in words[h:]]:
            return " ".join(words[:h])
    return None


def _dedupe_key(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _overlaps_or_near(a: Block, b: Block, cfg: Config) -> bool:
    """Two copies of one string are the same block only if they sit on top of
    each other. The same words genuinely repeated elsewhere on the page stay."""
    ix = min(a.x1, b.x1) - max(a.x0, b.x0)
    iy = min(a.y1, b.y1) - max(a.y0, b.y0)
    if ix > 1 and iy > 1:
        small = min(a.width * a.height, b.width * b.height)
        if small > 0 and (ix * iy) / small > 0.5:
            return True
    return (abs(a.x0 - b.x0) <= cfg.dedupe_text_shift_pt
            and abs(a.y0 - b.y0) <= cfg.dedupe_text_shift_pt)


def join_split_math(page: Page, cfg: Config) -> int:
    """One printed expression arriving as two or three blocks.

    A stacked fraction is rebuilt from its legs, and the leg that carried the
    rest of the line comes back as a block of its own sitting on the same
    baseline: "60 deg =", "x 60 = pi", "3 radian". Left alone they are written
    out one under the other, they overlap each other on the page, and the sum
    reads wrong. Blocks that share a baseline and touch are put back together.
    """
    if not getattr(cfg, "join_split_math", True) or len(page.blocks) < 2:
        return 0
    joined = 0
    out: List[Block] = []
    for b in page.blocks:
        prev = out[-1] if out else None
        if prev is not None and _same_expression(prev, b):
            prev.text = f"{prev.text} {(b.text or '').strip()}".strip()
            prev.type = "equation"
            prev.bbox_pt = [min(prev.x0, b.x0), min(prev.y0, b.y0),
                            max(prev.x1, b.x1), max(prev.y1, b.y1)]
            prev.runs = []
            joined += 1
            continue
        out.append(b)
    page.blocks = out
    return joined


def _same_expression(a: Block, b: Block) -> bool:
    if "equation" not in (a.type, b.type):
        return False
    if a.type not in ("equation", "paragraph") or b.type not in ("equation",
                                                                 "paragraph"):
        return False
    if a.column != b.column:
        return False
    if len((a.text or "")) + len((b.text or "")) > 90:
        return False
    if (b.text or "").strip().startswith(("Solution", "Problem")):
        return False
    overlap = min(a.y1, b.y1) - max(a.y0, b.y0)
    if overlap < 0.45 * min(a.height, b.height):
        return False
    gap = max(a.x0, b.x0) - min(a.x1, b.x1)
    return gap < 8.0


def join_fragments(page: Page, cfg: Config) -> int:
    """Stitch a sentence back together when the layout split it across blocks.

    A boxed activity or a narrow column arrives as one PyMuPDF block per line,
    so the text comes out as "Measure / length / breadth of your science /
    book". Two blocks join only when the first does not end a sentence and the
    second continues one, which leaves a genuine list of short terms alone.
    """
    if len(page.blocks) < 2:
        return 0
    out: List[Block] = []
    joined = 0
    for b in page.blocks:
        if not out:
            out.append(b)
            continue
        prev = out[-1]
        if _joinable(prev, b, page, cfg):
            btext = (b.text or "").lstrip()
            marker = _repeated_marker(prev, b)
            if marker:
                btext = btext[len(marker):].lstrip()
            shift = len(b.text or "") - len(btext)
            off = len(prev.text) + 1 - shift
            prev.text = prev.text + " " + btext
            prev.runs.extend([Run(s=r.s + off, e=r.e + off, bold=r.bold,
                                  italic=r.italic, underline=r.underline,
                                  superscript=r.superscript,
                                  subscript=r.subscript, color=r.color)
                              for r in b.runs])
            prev.bbox_pt = [min(prev.x0, b.x0), min(prev.y0, b.y0),
                            max(prev.x1, b.x1), max(prev.y1, b.y1)]
            prev.runs = merge_runs(prev.runs)
            joined += 1
            continue
        out.append(b)
    page.blocks = out
    return joined


_LONE_BULLET_RE = re.compile(r"^[\u2022\u25cf\u25aa\u00b7\u2023\u2043\u2219\-\u2013]\s*$")


def merge_lone_bullets(page: Page, cfg: Config) -> int:
    """A bullet mark and its sentence are two spans, so they arrive as two
    blocks and the document ends up with a paragraph that is just a dot.

    The dot joins the nearest block to its right on the same line and the
    pair becomes one list item.
    """
    if not cfg.merge_lone_bullets:
        return 0
    out: List[Block] = []
    merged = 0
    pending: List[Block] = []
    for b in page.blocks:
        if b.type in ("paragraph", "list_item") and \
                _LONE_BULLET_RE.match((b.text or "").strip()):
            pending.append(b)
            continue
        if pending:
            mate = pending[-1]
            same_line = (min(b.y1, mate.y1) - max(b.y0, mate.y0)) > 1
            if b.type in ("paragraph", "list_item") and same_line \
                    and b.x0 >= mate.x0 - 1 and b.text.strip():
                off = len((mate.text or "").strip()) + 1
                b.text = (mate.text or "").strip() + " " + (b.text or "").lstrip()
                b.runs = [Run(s=r.s + off, e=r.e + off, bold=r.bold,
                              italic=r.italic, underline=r.underline,
                              superscript=r.superscript, subscript=r.subscript,
                              color=r.color) for r in b.runs]
                b.bbox_pt = [min(mate.x0, b.x0), min(mate.y0, b.y0),
                             max(mate.x1, b.x1), max(mate.y1, b.y1)]
                b.type = "list_item"
                b.block_kind = "bullet"
                pending.pop()
                merged += 1
            out.extend(pending)
            pending = []
        out.append(b)
    out.extend(pending)
    page.blocks = out
    return merged


def _repeated_marker(a: Block, b: Block) -> str:
    """A bullet glyph printed once per LINE rather than once per item.

    The reader hands back "* The need of standard units for physical" and
    "* quantities was recognised...", two halves of one sentence each wearing
    the same mark, with boxes that overlap. The mark on the second half is an
    artefact of the line, not a new bullet.
    """
    at = (a.text or "").lstrip()
    bt = (b.text or "").lstrip()
    if not at or not bt:
        return ""
    ch = bt[0]
    # not isalnum: the Wingdings bullet in this book arrives as the vulgar
    # fraction three quarters, which counts as numeric and would be let past
    if ch.isalpha() or ch.isdigit() or ch.isspace():
        return ""
    if at[0] != ch:
        return ""
    if min(a.y1, b.y1) - max(a.y0, b.y0) <= 2:
        return ""
    return ch


def _joinable(a: Block, b: Block, page: Page, cfg: Config) -> bool:
    if a.type != "paragraph" or b.type != "paragraph":
        return False
    if a.column != b.column or a.caption_of or b.caption_of:
        return False
    at = (a.text or "").rstrip()
    bt = (b.text or "").lstrip()
    if not at or not bt:
        return False
    if len(at) + len(bt) > 1800:
        return False
    if at.endswith((".", "!", "?", ":", ";")):
        return False
    marker = _repeated_marker(a, b)
    if marker:
        bt = bt[len(marker):].lstrip()
        if not bt:
            return False

    # the second block has to look like a continuation, not a new item
    first = bt[0]
    if not (first.islower() or first in ",)-\u2019'" or at.endswith("-")):
        return False
    if BULLET_RE.match(bt) or NUMBER_RE.match(bt) or SECTION_RE.match(bt):
        return False
    if marker:
        return True          # the boxes overlap by definition, so the gap
                             # tests below do not apply
    gap = b.y0 - a.y1
    line_h = max(8.0, a.height if a.height < 40 else 12.0)
    if gap > line_h * 1.8 or gap < -line_h:
        return False
    # side by side rather than stacked
    if b.y0 >= a.y1 - 1 and abs(b.x0 - a.x0) > max(36.0, a.width * 0.5):
        return False
    return True


def recompute_alignment(page: Page) -> None:
    """Alignment can only be judged once the column layout is known: a block in
    the right column is not right aligned, it is just in the right column."""
    for b in page.blocks:
        if b.type in ("paragraph", "heading", "list_item") and not b.caption_of:
            b.align = _align(b, page)


def renumber(page: Page) -> None:
    for i, b in enumerate(page.blocks):
        b.order = i


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

def merge_runs(runs: List[Run]) -> List[Run]:
    """Collapse adjacent identical runs. Keeps the docx small."""
    if not runs:
        return []
    runs = sorted(runs, key=lambda r: r.s)
    out = [runs[0]]
    for r in runs[1:]:
        p = out[-1]
        same = (p.bold == r.bold and p.italic == r.italic
                and p.underline == r.underline and p.color == r.color
                and p.superscript == r.superscript and p.subscript == r.subscript)
        if same and r.s <= p.e + 1:
            p.e = max(p.e, r.e)
        else:
            out.append(r)
    return [r for r in out if r.e > r.s and r.styled()]
