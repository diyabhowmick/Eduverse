"""Where things sit on a page once every block exists.

Figures, tables and the text read out of pictures are found after the text
layer has been ordered. B13 slotted each one in front of the first text block
that sorted after it, so a single out of order block (a label inside a seal)
dragged every picture on the page to the top, and a full width table landed
above the page title. Here each late block goes AFTER the last block that
precedes it in reading order, with bands, columns and rows taken into account.
"""

from __future__ import annotations

from typing import List, Optional

from .schema import Block, Page

TEXT_TYPES = ("paragraph", "heading", "list_item", "caption", "equation",
              "box", "title")
LATE_SOURCES = ("figure_text",)
ROW_TOL = 6.0


def _is_late(b: Block) -> bool:
    return b.type not in TEXT_TYPES or b.source in LATE_SOURCES


def _geometry_column(b: Block, page: Page) -> int:
    if not page.columns or page.columns < 2:
        return 0
    left = page.margins_pt[0]
    usable = page.width_pt - page.margins_pt[0] - page.margins_pt[2]
    if b.width > usable * 0.75:
        return -1
    colw = usable / page.columns
    centre = (b.x0 + b.x1) / 2
    return max(0, min(page.columns - 1, int((centre - left) // colw)))


def _spanning_rows(late: List[Block]) -> None:
    """Pictures printed side by side in one row across both columns read as
    one row, left to right, not as a left column item and a right column
    item."""
    figs = sorted([b for b in late if b.type in ("figure", "table")],
                  key=lambda b: b.y0)
    rows: List[List[Block]] = []
    for f in figs:
        if rows and abs(f.y0 - rows[-1][0].y0) <= 10 and all(
                f.x0 >= o.x1 - 2 or f.x1 <= o.x0 + 2 for o in rows[-1]):
            rows[-1].append(f)
        else:
            rows.append([f])
    for row in rows:
        cols = {b.column for b in row}
        if len(row) >= 2 and len(cols) >= 2:
            for b in row:
                b.column = -1


def place_late_blocks(page: Page) -> None:
    late = [b for b in page.blocks if _is_late(b)]
    if not late:
        return
    text = [b for b in page.blocks if not _is_late(b)]
    if page.columns and page.columns > 1:
        for b in late:
            b.column = _geometry_column(b, page)
        _spanning_rows(late)
    else:
        for b in late:
            b.column = 0

    seps = [b for b in page.blocks if b.column == -1]

    def band(b: Block) -> int:
        return sum(1 for s in seps if s is not b and s.y0 < b.y0 - 2)

    def row_before(a: Block, b: Block) -> bool:
        if a.y0 < b.y0 - ROW_TOL:
            return True
        return abs(a.y0 - b.y0) <= ROW_TOL and a.x0 < b.x0

    def precedes(a: Block, b: Block) -> bool:
        ba, bb = band(a), band(b)
        if ba != bb:
            return ba < bb
        if a.column == b.column or a.column == -1 or b.column == -1:
            return row_before(a, b)
        return a.column < b.column

    out = list(text)
    order = sorted(late, key=lambda b: (band(b), b.column, round(b.y0 / 8),
                                        b.x0))
    for b in order:
        pos = 0
        for i, a in enumerate(out):
            if precedes(a, b):
                pos = i + 1
        out.insert(pos, b)
    page.blocks = out


def hoist_side_headings(page: Page) -> int:
    """A heading printed beside its text, in a badge or a side banner, comes
    before the first block it sits level with. This is the HOW TO USE THE
    BOOK and DO YOU KNOW? case: read by position it lands mid section or at
    the foot of the page."""
    moved = 0
    for h in [b for b in page.blocks if b.type == "heading"]:
        if len((h.text or "").split()) > 8:
            continue
        beside = [o for o in page.blocks
                  if o is not h
                  and o.type in ("paragraph", "list_item", "equation")
                  and (o.column == h.column or page.columns <= 1)
                  and min(o.y1, h.y1) - max(o.y0, h.y0) > 2
                  and (o.x0 >= h.x1 - 2 or o.x1 <= h.x0 + 2)]
        if not beside:
            continue
        first = min(page.blocks.index(o) for o in beside)
        cur = page.blocks.index(h)
        if cur <= first:
            continue
        page.blocks.remove(h)
        page.blocks.insert(first, h)
        if "side_heading" not in h.flags:
            h.flags.append("side_heading")
        moved += 1
    return moved


def content_frame(page: Page) -> Optional[List[float]]:
    body = [b for b in page.blocks
            if b.type in ("paragraph", "heading", "list_item", "caption",
                          "equation") and b.source == "native_span"]
    if len(body) < 3:
        return None
    return [min(b.x0 for b in body), min(b.y0 for b in body),
            max(b.x1 for b in body), max(b.y1 for b in body)]


def drop_bleed_decorations(page: Page, ledger) -> int:
    """A picture that sits wholly outside the text frame and runs into the
    page edge is a thumb tab or a colour bar, not content."""
    frame = content_frame(page)
    if frame is None:
        return 0
    fx0, fy0, fx1, fy1 = frame
    edge = 24.0
    gone = set()
    for b in page.blocks:
        if b.type != "figure":
            continue
        outside = (b.x0 >= fx1 + 6 or b.x1 <= fx0 - 6
                   or b.y1 <= fy0 - 6 or b.y0 >= fy1 + 6)
        touches = (b.x0 < edge or b.y0 < edge or b.x1 > page.width_pt - edge
                   or b.y1 > page.height_pt - edge)
        thin = min(b.width, b.height) < 60
        holds_text = bool(b.figure and b.figure.text_in_image)
        if outside and touches and thin and not holds_text:
            gone.add(b.id)
            ledger.drop(b.id, page.page, "decorative",
                        "outside the text frame at the page edge (tab or bar)",
                        b.bbox_pt)
    if not gone:
        return 0
    keep = []
    for b in page.blocks:
        if b.id in gone:
            continue
        if b.caption_of in gone and b.type == "figure_note":
            ledger.drop(b.id, page.page, "decorative",
                        "note for a dropped decoration", b.bbox_pt)
            ledger.emitted -= 1
            continue
        keep.append(b)
    page.blocks = keep
    ledger.emitted -= len(gone)
    return len(gone)


def _area(r) -> float:
    return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])


def _inter(a, b) -> float:
    return _area([max(a[0], b[0]), max(a[1], b[1]),
                  min(a[2], b[2]), min(a[3], b[3])])


def assign_boxes(page: Page) -> int:
    """Tie each block to the printed panel it sits in (Activity, Do you know,
    Problem), so the writers can keep a panel's contents set apart."""
    for b in page.blocks:
        b.box = -1
    page_area = page.width_pt * page.height_pt
    solids = [b.bbox_pt for b in page.blocks if b.type in ("table", "figure")]
    boxes = []
    for i, r in enumerate(page.boxes_pt or []):
        a = _area(r)
        if a <= 0 or a > page_area * 0.45:
            continue
        if (r[2] - r[0]) < 60 or (r[3] - r[1]) < 30:
            continue
        if any(_inter(r, s) > a * 0.5 for s in solids):
            continue             # a table grid or a figure frame
        boxes.append((a, i, r))
    boxes.sort()
    members = {}
    for b in page.blocks:
        ba = _area(b.bbox_pt)
        if ba <= 0:
            continue
        for a, i, r in boxes:
            if _inter(b.bbox_pt, r) >= ba * 0.85:
                members.setdefault(i, []).append(b)
                break
    kept = 0
    for i, lst in members.items():
        body = [b for b in lst
                if b.type in ("paragraph", "list_item", "equation")]
        if len(body) < 1 or len(lst) < 2:
            continue
        for b in lst:
            b.box = i
        kept += 1
    return kept
