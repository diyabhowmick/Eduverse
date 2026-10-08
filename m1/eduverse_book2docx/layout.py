"""Page layout.

Rules A and B: work out the layout before reading anything, and find the boxes
before reading the text.

Everything here operates on raw text LINES, not on paragraphs. Grouping lines
into paragraphs first is what hides the column gap, which is how a two column
page ends up read straight across.

The output is an assignment of every line to a band, a column and possibly a
box, plus a reading order over those units.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .config import Config

Rect = Tuple[float, float, float, float]


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class Box:
    """A bordered or tinted panel. Read start to finish, on its own."""
    rect: Rect
    kind: str = "panel"          # panel | badge
    filled: bool = False
    bordered: bool = False
    title_line: Optional[int] = None      # index of the line acting as its title

    @property
    def x0(self): return self.rect[0]

    @property
    def y0(self): return self.rect[1]

    @property
    def x1(self): return self.rect[2]

    @property
    def y1(self): return self.rect[3]

    @property
    def width(self): return self.rect[2] - self.rect[0]

    @property
    def height(self): return self.rect[3] - self.rect[1]

    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    def contains(self, r: Rect, tol: float = 2.0) -> bool:
        return (r[0] >= self.x0 - tol and r[2] <= self.x1 + tol
                and r[1] >= self.y0 - tol and r[3] <= self.y1 + tol)


@dataclass
class Band:
    """A horizontal slice of the page with a single column layout."""
    y0: float
    y1: float
    columns: List[Tuple[float, float]] = field(default_factory=list)

    @property
    def ncols(self) -> int:
        return max(1, len(self.columns))

    def column_of(self, r: Rect) -> int:
        if len(self.columns) <= 1:
            return 0
        cx = (r[0] + r[2]) / 2
        best, bd = 0, 1e9
        for i, (a, b) in enumerate(self.columns):
            if a <= cx <= b:
                return i
            d = min(abs(cx - a), abs(cx - b))
            if d < bd:
                best, bd = i, d
        return best


@dataclass
class Layout:
    bands: List[Band] = field(default_factory=list)
    boxes: List[Box] = field(default_factory=list)
    line_band: List[int] = field(default_factory=list)
    line_col: List[int] = field(default_factory=list)
    line_box: List[int] = field(default_factory=list)   # -1 when not in a box
    confidence: float = 1.0
    notes: List[str] = field(default_factory=list)

    def max_columns(self) -> int:
        return max((b.ncols for b in self.bands), default=1)


# ---------------------------------------------------------------------------
# Boxes  (rules 7 to 11)
# ---------------------------------------------------------------------------

def find_boxes(drawings: Sequence[dict], page_rect: Rect, lines: Sequence[Rect],
               cfg: Config) -> List[Box]:
    """A box is a bordered or tinted region that holds text."""
    pw = page_rect[2] - page_rect[0]
    ph = page_rect[3] - page_rect[1]
    page_area = max(1.0, pw * ph)
    out: List[Box] = []

    for d in drawings or []:
        r = d.get("rect")
        if r is None:
            continue
        rect = (float(r[0]), float(r[1]), float(r[2]), float(r[3]))
        w, h = rect[2] - rect[0], rect[3] - rect[1]
        if w < 24 or h < 18:
            continue
        area = w * h
        if area > page_area * cfg.box_max_area_frac:
            continue
        if area < page_area * cfg.box_min_area_frac:
            continue
        filled = bool(d.get("fill"))
        bordered = bool(d.get("color")) or bool(d.get("width"))
        if not (filled or bordered):
            continue
        inside = [l for l in lines if _inside(l, rect)]
        if not inside:
            continue
        out.append(Box(rect=rect, filled=filled, bordered=bordered))

    out = _merge_nested(out)
    _mark_badges(out, lines, cfg)
    return out


def _merge_nested(boxes: List[Box]) -> List[Box]:
    """A panel drawn as several stacked rectangles is one panel. A small shape
    fully inside a bigger one stays, because it may be a badge."""
    boxes = sorted(boxes, key=lambda b: -b.area())
    kept: List[Box] = []
    for b in boxes:
        dup = False
        for k in kept:
            if _iou(b.rect, k.rect) > 0.75:
                dup = True
                break
        if not dup:
            kept.append(b)
    return kept


def _mark_badges(boxes: List[Box], lines: Sequence[Rect], cfg: Config) -> None:
    """Rule 11: a small roughly square shape inside a panel, holding one short
    line, is the panel's title badge, like the circle around PREFACE."""
    for b in boxes:
        if b.width <= 0 or b.height <= 0:
            continue
        ratio = b.width / b.height
        if not (0.45 <= ratio <= 2.2):
            continue
        parent = next((p for p in boxes
                       if p is not b and p.contains(b.rect, tol=6.0)
                       and p.area() > b.area() * 1.6), None)
        if parent is None:
            continue
        inside = [i for i, l in enumerate(lines) if _inside(l, b.rect, tol=4.0)]
        if len(inside) > cfg.badge_max_lines or not inside:
            continue
        b.kind = "badge"
        parent.title_line = inside[0]


# ---------------------------------------------------------------------------
# Bands  (rules 4 and 5)
# ---------------------------------------------------------------------------

def find_bands(lines: Sequence[Rect], page_rect: Rect,
               gutters: Sequence[Tuple[float, float]], cfg: Config,
               boxes: Sequence["Box"] = ()) -> List[Band]:
    """A page can change layout halfway down, so a full width line splits it.

    Only ever called once the page is known to have columns. A line counts as
    full width when it CROSSES a gutter, not merely because it is long: a
    wrapped line in a wide single column is long too, and treating it as a
    band break shreds every paragraph into one band per line.
    """
    if not lines or not gutters:
        return [Band(page_rect[1], page_rect[3])]

    def crosses(l: Rect) -> bool:
        return any(l[0] < (a + b) / 2 < l[2] for a, b in gutters)

    wide = [l for l in lines if crosses(l)]
    # A panel drawn across both columns is a full width region even when the
    # text inside it is short. Its heading is not a left column line.
    for b in boxes:
        if getattr(b, "kind", "") == "badge":
            continue
        if crosses(b.rect):
            wide.append(tuple(b.rect))
    wide = sorted(wide, key=lambda l: l[1])
    if not wide:
        return [Band(page_rect[1], page_rect[3])]

    # merge neighbouring full width lines into one spanning region
    spans: List[List[float]] = []
    for l in wide:
        if spans and l[1] - spans[-1][1] <= max(6.0, (l[3] - l[1]) * 1.8):
            spans[-1][1] = max(spans[-1][1], l[3])
        else:
            spans.append([l[1], l[3]])

    bounds = [page_rect[1]]
    for a, b in spans:
        bounds.extend([a, b])
    bounds.append(page_rect[3])
    bounds = sorted(set(round(v, 1) for v in bounds))

    bands = [Band(a, b) for a, b in zip(bounds, bounds[1:]) if b - a >= 6]
    if len(bands) > cfg.max_bands:
        return [Band(page_rect[1], page_rect[3])]
    return bands or [Band(page_rect[1], page_rect[3])]


# ---------------------------------------------------------------------------
# Columns  (rules 2, 3, 6)
# ---------------------------------------------------------------------------

def columns_in(lines: Sequence[Rect], x0: float, x1: float, y0: float,
               y1: float, cfg: Config) -> List[Tuple[float, float]]:
    """Find columns from the gaps between LINES.

    A real gutter is a vertical strip with no text in it, tall enough to be
    deliberate, with text on both sides that actually sits side by side.
    """
    band_lines = [l for l in lines if l[1] >= y0 - 1 and l[3] <= y1 + 1
                  and (l[2] - l[0]) > 4]
    if len(band_lines) < cfg.column_min_lines:
        return [(x0, x1)]

    # Stray marks sit in the gutter of a real book: a registration cross, a
    # stray bullet, a one character fragment. Projecting them makes the gutter
    # look occupied and the page reads as one column, so short fragments are
    # left out and the gutter is judged by a low threshold, not by zero.
    solid = [l for l in band_lines
             if (l[2] - l[0]) >= cfg.min_line_width_pt]
    if len(solid) < cfg.column_min_lines:
        solid = band_lines

    width = int(max(1.0, x1 - x0))
    hist = [0] * (width + 2)
    for l in solid:
        a = max(0, int(l[0] - x0))
        b = min(width, int(l[2] - x0))
        for x in range(a, b):
            hist[x] += 1

    # A gutter is rarely completely empty on a real page. A full width heading
    # or a banner box crosses it, and demanding zero coverage there is what
    # makes a two column page read as one. But a single loose threshold is
    # worse: a threshold high enough to forgive a banner also swallows the
    # ragged right edge of the left column, and the "gutter" comes back 120pt
    # wide sitting in the middle of the text. So the search runs as a LADDER,
    # strictest first, and stops at the first rung that confirms a gutter.
    peak = max(hist) if hist else 0
    if peak == 0:
        return [(x0, x1)]

    span = x1 - x0
    max_gutter = span * cfg.gutter_max_width_frac
    rungs = [0,
             int(peak * cfg.gutter_noise_frac),
             max(int(peak * cfg.gutter_noise_frac),
                 int(len(solid) * cfg.gutter_max_cross_frac))]

    confirmed: List[Tuple[float, float]] = []
    for thresh in rungs:
        gaps: List[Tuple[float, float]] = []
        run: Optional[int] = None
        for i in range(width + 1):
            if hist[i] <= thresh:
                if run is None:
                    run = i
            else:
                if run is not None and i - run >= cfg.column_gutter_min_pt:
                    gaps.append((x0 + run, x0 + i))
                run = None
        if run is not None and width - run >= cfg.column_gutter_min_pt:
            gaps.append((x0 + run, x0 + width))

        # a gutter wider than a fair slice of the page is not a gutter, it is
        # the whole right hand side of a short column
        gaps = [g for g in gaps if (g[1] - g[0]) <= max_gutter]
        gaps = [g for g in gaps if _is_valley(hist, x0, g, cfg)]
        inner = [g for g in gaps
                 if (g[0] - x0) > span * 0.12 and (x1 - g[1]) > span * 0.12]
        confirmed = [g for g in inner if _side_by_side(band_lines, g, cfg)]
        confirmed = [g for g in confirmed
                     if _supported(band_lines, g, cfg)]
        if confirmed:
            break

    if not confirmed:
        centre = _centre_corridor(band_lines, x0, x1, cfg)
        if centre:
            confirmed = [centre]

    if not confirmed:
        return [(x0, x1)]

    confirmed.sort()
    if len(confirmed) > cfg.max_columns - 1:
        confirmed = sorted(confirmed,
                           key=lambda g: -(g[1] - g[0]))[: cfg.max_columns - 1]
        confirmed.sort()

    cols: List[Tuple[float, float]] = []
    cursor = x0
    for a, b in confirmed:
        cols.append((cursor, a))
        cursor = b
    cols.append((cursor, x1))
    return [c for c in cols if c[1] - c[0] > 20]


def _supported(lines: Sequence[Rect], gutter: Tuple[float, float],
               cfg: Config) -> bool:
    """Keep a gutter unless it is contested and only reads across locally.

    An uncontested gap, one no line crosses, is a plain column break and needs
    no further evidence. A contested gap has to earn it: if text crosses it
    and the rows that read across it only cover a slice of the page, it is a
    table's internal column gap, not the page gutter.
    """
    a, b = gutter
    crossing = sum(1 for l in lines if l[0] < a - 1 and l[2] > b + 1)
    if crossing < cfg.gutter_contested_lines:
        return True
    return _vertical_support(lines, gutter) >= cfg.gutter_min_support_frac


def _vertical_support(lines: Sequence[Rect], gutter: Tuple[float, float]) -> float:
    """How much of the text height actually reads across this gap.

    A page gutter runs the height of the text. The gap between a glossary's
    label column and its definitions only runs the height of the glossary, and
    treating it as a page gutter turns the page into three columns and
    scrambles the order.
    """
    if not lines:
        return 0.0
    a, b = gutter
    top = min(l[1] for l in lines)
    bot = max(l[3] for l in lines)
    height = bot - top
    if height <= 0:
        return 0.0
    users = [l for l in lines if l[2] <= a or l[0] >= b]
    rows = {}
    for l in users:
        rows.setdefault(round((l[1] + l[3]) / 6.0), []).append(l)
    ys = []
    for row in rows.values():
        if any(l[2] <= a for l in row) and any(l[0] >= b for l in row):
            ys.extend([min(l[1] for l in row), max(l[3] for l in row)])
    if len(ys) < 4:
        return 0.0
    return (max(ys) - min(ys)) / height


def _centre_corridor(lines: Sequence[Rect], x0: float, x1: float,
                     cfg: Config) -> Optional[Tuple[float, float]]:
    """Last rung: the narrow strip near the middle that fewest ROWS cross.

    Coverage thresholds fail on a page that mixes a two column body with one
    full width band, because the band's rows put ink right through the gutter.
    Counting rows instead of ink lets a handful of full width rows be outvoted
    by the forty that respect the columns.
    """
    span = x1 - x0
    if span <= 0:
        return None
    rows: List[List[Rect]] = []
    for l in sorted(lines, key=lambda r: (r[1] + r[3]) / 2):
        c = (l[1] + l[3]) / 2
        if rows and abs(c - (rows[-1][0][1] + rows[-1][0][3]) / 2) <= 3.0:
            rows[-1].append(l)
        else:
            rows.append([l])
    if len(rows) < cfg.centre_corridor_min_rows:
        return None
    best = None
    step = 2
    lo_x = x0 + span * cfg.centre_corridor_lo_frac
    hi_x = x0 + span * cfg.centre_corridor_hi_frac
    x = lo_x
    while x < hi_x:
        lo, hi = x - 4, x + 4
        cross = sum(1 for r in rows
                    if any(l[2] > lo and l[0] < hi for l in r))
        if best is None or cross < best[0]:
            best = (cross, x)
        x += step
    if best is None:
        return None
    cross, x = best
    if cross > len(rows) * cfg.centre_corridor_max_cross_frac:
        return None
    lo, hi = x - 4, x + 4
    left = sum(1 for r in rows if all(l[2] <= lo for l in r))
    right = sum(1 for r in rows if all(l[0] >= hi for l in r))
    if left < cfg.column_min_side_lines or right < cfg.column_min_side_lines:
        return None
    # widen to the real whitespace either side of the probe
    a, b = lo, hi
    for r in rows:
        if any(l[2] > lo and l[0] < hi for l in r):
            continue
        ls = [l[2] for l in r if l[2] <= lo]
        rs = [l[0] for l in r if l[0] >= hi]
        if ls and rs:
            a = max(a, max(ls))
            b = min(b, min(rs))
    if b - a < 4:
        a, b = lo, hi
    return (a, b)


def _is_valley(hist: List[int], x0: float, gutter: Tuple[float, float],
               cfg: Config) -> bool:
    """The gap must be a real dip, not just a thin patch of a sparse page."""
    a = int(gutter[0] - x0)
    b = int(gutter[1] - x0)
    inner = hist[max(0, a):max(1, b)]
    if not inner:
        return False
    low = sum(inner) / len(inner)
    left = hist[max(0, a - 40):max(1, a)]
    right = hist[b:b + 40]
    if not left or not right:
        return False
    lo_side = min(sum(left) / len(left), sum(right) / len(right))
    return lo_side >= max(1.0, low * cfg.gutter_valley_ratio)


def _side_by_side(lines: Sequence[Rect], gutter: Tuple[float, float],
                  cfg: Config) -> bool:
    """Text on both sides of the gap, overlapping vertically. Without this a
    ragged right margin reads as a column."""
    gx = (gutter[0] + gutter[1]) / 2
    lefts = [l for l in lines if l[2] <= gx]
    rights = [l for l in lines if l[0] >= gx]
    if len(lefts) < cfg.column_min_side_lines:
        return False
    if len(rights) < cfg.column_min_side_lines:
        return False
    pairs = 0
    for a in lefts:
        for b in rights:
            if min(a[3], b[3]) - max(a[1], b[1]) > 3:
                pairs += 1
                if pairs >= cfg.column_min_pairs:
                    return True
    return False


# ---------------------------------------------------------------------------
# Assignment and ordering
# ---------------------------------------------------------------------------

def analyse(lines: Sequence[Rect], page_rect: Rect, margins: Sequence[float],
            drawings: Sequence[dict], cfg: Config) -> Layout:
    boxes = find_boxes(drawings, page_rect, lines, cfg) if cfg.detect_boxes else []

    left = margins[0]
    right = page_rect[2] - margins[2]
    if right <= left:
        left, right = page_rect[0], page_rect[2]

    # Columns for the whole page first. Only a page that actually has columns
    # can have bands, so a single column page is never cut up.
    #
    # A full width heading sits across the gutter, so it has to be left out
    # while the gutter is being looked for. Otherwise one banner line hides
    # the columns of the whole page.
    usable = max(1.0, right - left)
    narrow = [l for l in lines
              if (l[2] - l[0]) <= usable * cfg.full_width_frac]
    probe = narrow if len(narrow) >= cfg.column_min_lines else lines
    page_cols = columns_in(probe, left, right, page_rect[1], page_rect[3], cfg)
    gutters = [(a[1], b[0]) for a, b in zip(page_cols, page_cols[1:])]

    if len(page_cols) <= 1:
        bands = [Band(page_rect[1], page_rect[3], columns=page_cols)]
    else:
        bands = find_bands(lines, page_rect, gutters, cfg, boxes)
        for band in bands:
            band.columns = columns_in(lines, left, right, band.y0, band.y1, cfg)

    lay = Layout(bands=bands, boxes=boxes)
    lay.line_band = [0] * len(lines)
    lay.line_col = [0] * len(lines)
    lay.line_box = [-1] * len(lines)

    for i, l in enumerate(lines):
        bi = _band_index(bands, l)
        lay.line_band[i] = bi
        lay.line_col[i] = bands[bi].column_of(l)
        lay.line_box[i] = _box_index(boxes, l)

    lay.confidence = _confidence(lay, lines, cfg)
    return lay


def gutters_of(lay: "Layout") -> List[Tuple[float, float]]:
    """Every column gap the layout found, across all bands."""
    out: List[Tuple[float, float]] = []
    for band in lay.bands:
        cols = sorted(band.columns)
        for a, b in zip(cols, cols[1:]):
            if b[0] - a[1] > 2:
                out.append((a[1], b[0]))
    merged: List[Tuple[float, float]] = []
    for g in sorted(out):
        if merged and g[0] <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], g[1]))
        else:
            merged.append(g)
    return merged


def _band_index(bands: List[Band], r: Rect) -> int:
    cy = (r[1] + r[3]) / 2
    for i, b in enumerate(bands):
        if b.y0 - 1 <= cy <= b.y1 + 1:
            return i
    return min(range(len(bands)),
               key=lambda i: abs(((bands[i].y0 + bands[i].y1) / 2) - cy))


def _box_index(boxes: List[Box], r: Rect) -> int:
    best, best_area = -1, 1e18
    for i, b in enumerate(boxes):
        if b.kind == "badge":
            continue
        if b.contains(r, tol=3.0) and b.area() < best_area:
            best, best_area = i, b.area()
    return best


def order_units(units: Sequence["Unitish"], lay: Layout, cfg: Config
                ) -> List[int]:
    """Reading order: band, then column, then top to bottom.

    A box is a single unit placed where it starts, and its own contents keep
    their internal order. Nothing outside a box may cut into it.
    """
    idx = list(range(len(units)))

    def key(i: int):
        u = units[i]
        return (u.band, u.box_order, u.column, round(u.y0, 1), round(u.x0, 1))

    return sorted(idx, key=key)


class Unitish:
    """Duck type for order_units: band, column, box_order, y0, x0."""
    band: int
    column: int
    box_order: float
    y0: float
    x0: float


# ---------------------------------------------------------------------------

def _confidence(lay: Layout, lines: Sequence[Rect], cfg: Config) -> float:
    """How sure we are about this page. Reported per page so you can go
    straight to the doubtful ones."""
    score = 1.0
    if not lines:
        return 1.0
    if lay.max_columns() > 1:
        score -= 0.05
    if len(lay.bands) > 4:
        score -= 0.1
        lay.notes.append(f"{len(lay.bands)} layout bands")
    if len(lay.boxes) > 6:
        score -= 0.05
        lay.notes.append(f"{len(lay.boxes)} boxes")
    unplaced = sum(1 for b in lay.line_box if b == -1)
    if lay.boxes and unplaced == len(lay.line_box):
        score -= 0.05
    return max(0.0, min(1.0, score))


def _inside(r: Rect, box: Rect, tol: float = 2.0) -> bool:
    return (r[0] >= box[0] - tol and r[2] <= box[2] + tol
            and r[1] >= box[1] - tol and r[3] <= box[3] + tol)


def _iou(a: Rect, b: Rect) -> float:
    ix = min(a[2], b[2]) - max(a[0], b[0])
    iy = min(a[3], b[3]) - max(a[1], b[1])
    if ix <= 0 or iy <= 0:
        return 0.0
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1])
    ub = (b[2] - b[0]) * (b[3] - b[1])
    return inter / max(1e-6, ua + ub - inter)


def crosses_gutter(a: Rect, b: Rect, lay: Layout) -> bool:
    """Rule 15 and 19: never join across a column gap."""
    for band in lay.bands:
        if len(band.columns) < 2:
            continue
        for (_, ax1), (bx0, _) in zip(band.columns, band.columns[1:]):
            gx = (ax1 + bx0) / 2
            if (a[2] <= gx <= b[0]) or (b[2] <= gx <= a[0]):
                return True
    return False


def same_box(i: int, j: int, lay: Layout) -> bool:
    return lay.line_box[i] == lay.line_box[j]
