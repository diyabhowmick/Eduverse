"""Make each printed figure one picture.

Runs on every page after captions are bound. Three things it repairs:

1. Pieces of one figure. Sub-figures "(a)" and "(b)" side by side under one caption, a picture printed as two or
   more images, a diagram whose parts were found separately. Two figures are joined when they sit side by side or
   one above the other, close together, with nothing but short labels between them, and at most one of them has its
   own caption. Two figures that each have a caption stay apart: the book numbered them separately.
2. Labels around a diagram. "Petal", "Sepal", "(a)": short text printed beside or inside a figure, usually at the end
   of a leader line. It belongs to the picture. Before, it was read as body text ("Petal Centre (ovary) Sepal A
   flower is ...") and the picture lost its labels.
3. The joined figure is cropped again from the page image, as one rectangle, so the lines and labels between the
   pieces are in it.

Each join is written to the ledger, so the reviewer sees what happened.
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional

LABEL_RE = re.compile(r"^\(?\s*(?:[a-h]|[ivx]{1,4}|\d{1,2})\s*\)$|^[A-Za-z][A-Za-z ()'\-]{0,28}$")
SUBPART_RE = re.compile(r"^\(\s*(?:[a-h]|[ivx]{1,4})\s*\)$")


def _is_label(b, body_size: float) -> bool:
    """Short text that can only be a label: a few words, no sentence end, not bigger than body text."""
    if b.type not in ("paragraph", "list_item") or b.caption_of:
        return False
    t = (b.text or "").strip()
    if not t or len(t) > 30 or len(t.split()) > 4 or t.endswith((".", ":", "?", "!")):
        return False
    if b.font_size and body_size and b.font_size > body_size * 1.15:
        return False
    return bool(LABEL_RE.match(t))


def _overlap(a0, a1, b0, b1) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _gap_rect(a, b):
    """The space between two boxes, or None if they overlap on both axes."""
    x0, x1 = (a[2], b[0]) if a[2] <= b[0] else (b[2], a[0]) if b[2] <= a[0] else (max(a[0], b[0]), min(a[2], b[2]))
    y0, y1 = (a[3], b[1]) if a[3] <= b[1] else (b[3], a[1]) if b[3] <= a[1] else (max(a[1], b[1]), min(a[3], b[3]))
    return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]


def _inside(inner, outer, tol=2.0) -> bool:
    return inner[0] >= outer[0] - tol and inner[1] >= outer[1] - tol and inner[2] <= outer[2] + tol and inner[3] <= outer[3] + tol


def _hits(box, other) -> bool:
    return _overlap(box[0], box[2], other[0], other[2]) > 0.5 and _overlap(box[1], box[3], other[1], other[3]) > 0.5


def _body_size(page) -> float:
    sizes = sorted(b.font_size for b in page.blocks if b.type == "paragraph" and b.font_size and len(b.text or "") > 80)
    return sizes[len(sizes) // 2] if sizes else 0.0


def join_figures(page, out_dir: str, cfg, ledger) -> int:
    figs = [b for b in page.blocks if b.type == "figure" and b.image_ref]
    if not figs:
        return 0
    body = _body_size(page)
    captioned = {b.caption_of: b for b in page.blocks if b.type == "caption" and b.caption_of}
    captions = [b for b in page.blocks if b.type == "caption"]
    texts = [b for b in page.blocks if b.type in ("paragraph", "heading", "list_item", "caption", "table") and b not in figs]
    max_gap = getattr(cfg, "figure_join_gap_pt", 60.0)

    # --- 1. join pieces -------------------------------------------------
    parent = {f.id: f.id for f in figs}

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def group_has_caption(r):
        return any(captioned.get(f.id) for f in figs if root(f.id) == r)

    def caption_under_row(a, b):
        """One caption just below a row of figures, covering it: the row is one figure with sub-parts."""
        row_bottom = max(a.bbox_pt[3], b.bbox_pt[3])
        x0, x1 = min(a.bbox_pt[0], b.bbox_pt[0]), max(a.bbox_pt[2], b.bbox_pt[2])
        for c in captions:
            cb = c.bbox_pt
            if 0 <= cb[1] - row_bottom <= 45 and _overlap(cb[0], cb[2], x0, x1) > 0:
                return c
        return None

    def band_blocked(y0, y1, x0, x1):
        """Body text or a caption anywhere across the band between two stacked pieces separates them."""
        for t in texts:
            tb = t.bbox_pt
            if _overlap(tb[1], tb[3], y0, y1) > 0.5 and _overlap(tb[0], tb[2], x0 - 60, x1 + 60) > 0 and not _is_label(t, body):
                return True
        return False

    touch = getattr(cfg, "figure_touch_gap_pt", 12.0)
    for i, a in enumerate(figs):
        for b in figs[i + 1:]:
            ra, rb = root(a.id), root(b.id)
            if ra == rb or (group_has_caption(ra) and group_has_caption(rb)):
                continue
            A, Bx = a.bbox_pt, b.bbox_pt
            v_ov = _overlap(A[1], A[3], Bx[1], Bx[3])
            h_ov = _overlap(A[0], A[2], Bx[0], Bx[2])
            if v_ov >= 0.5 * min(A[3] - A[1], Bx[3] - Bx[1]):            # side by side
                gap = max(A[0], Bx[0]) - min(A[2], Bx[2])
                between = _gap_rect(A, Bx)
                if any(_hits(between, t.bbox_pt) and not _is_label(t, body) for t in texts):
                    continue
                cap = caption_under_row(a, b)
                own = [captioned.get(a.id), captioned.get(b.id)]
                shared = cap is not None and all(o in (None, cap) for o in own)
                if gap <= touch or (shared and gap <= max(max_gap, min(A[2] - A[0], Bx[2] - Bx[0]) * 1.2)):
                    parent[rb] = ra
            elif h_ov >= 0.4 * min(A[2] - A[0], Bx[2] - Bx[0]):          # one above the other
                y0, y1 = min(A[3], Bx[3]), max(A[1], Bx[1])
                if y1 - y0 <= touch and not band_blocked(y0, y1, min(A[0], Bx[0]), max(A[2], Bx[2])):
                    parent[rb] = ra

    groups: Dict[str, List] = {}
    for f in figs:
        groups.setdefault(root(f.id), []).append(f)

    # --- 2. labels -------------------------------------------------------
    joined = 0
    removed = set()
    for gid, members in groups.items():
        box = [min(f.bbox_pt[0] for f in members), min(f.bbox_pt[1] for f in members),
               max(f.bbox_pt[2] for f in members), max(f.bbox_pt[3] for f in members)]
        cap = next((captioned[f.id] for f in members if captioned.get(f.id)), None)
        labels = []
        for t in texts:
            if t.id in removed or not _is_label(t, body):
                continue
            tb = t.bbox_pt
            # beside the figure (left or right, within reach of a leader line), or just under a sub-figure
            beside = _overlap(tb[1], tb[3], box[1] - 20, box[3] + 20) > 0 and (
                0 <= tb[0] - box[2] <= 90 or 0 <= box[0] - tb[2] <= 90)
            within = _inside(tb, [box[0] - 4, box[1] - 4, box[2] + 4, box[3] + 4])
            under = (SUBPART_RE.match((t.text or "").strip()) and 0 <= tb[1] - box[3] <= 24
                     and _overlap(tb[0], tb[2], box[0], box[2]) > 0)
            # never past the caption: the caption ends the figure
            if cap and tb[1] >= cap.bbox_pt[1] - 1:
                continue
            if beside or within or under:
                labels.append(t)
        # Labels an earlier pass already dropped as "inside the figure" must really be inside the picture.
        # "(a)" and "(b)" printed just under sub-figures were dropped that way and then cut off by the crop.
        outside = []
        for e in getattr(ledger, "entries", []):
            eb = e.get("bbox")
            if e.get("page") != page.page or not eb or "label inside figure" not in (e.get("detail") or ""):
                continue
            near = _inside(eb, [box[0] - 30, box[1] - 30, box[2] + 30, box[3] + 30])
            if near and not _inside(eb, box) and not (cap and eb[1] >= cap.bbox_pt[1] - 1):
                outside.append(eb)
        if len(members) == 1 and not labels and not outside:
            continue
        for tb in [t.bbox_pt for t in labels] + outside:
            box = [min(box[0], tb[0]), min(box[1], tb[1]), max(box[2], tb[2]), max(box[3], tb[3])]
        keep = next((f for f in members if captioned.get(f.id)), members[0])
        if not _recrop(page, keep, box, out_dir):
            continue   # no page image to crop from (Word source): leave the pieces as they were
        for f in members:
            if f is not keep:
                removed.add(f.id)
                ledger.drop(f.id, page.page, "joined_into_figure", f"piece of figure {keep.id}", list(f.bbox_pt))
                for b in page.blocks:      # a description box or note bound to a removed piece now belongs to the whole
                    if b.caption_of == f.id:
                        b.caption_of = keep.id
        for t in labels:
            removed.add(t.id)
            ledger.drop(t.id, page.page, "joined_into_figure", f"label \"{(t.text or '').strip()}\" kept in figure {keep.id}", list(t.bbox_pt))
        keep.bbox_pt = box
        keep.flags.append("figure_joined" if len(members) > 1 else "figure_labels_absorbed")
        if outside:
            keep.flags.append("figure_crop_widened_for_labels")
        joined += len(members) - 1 + (1 if labels else 0)
    if removed:
        page.blocks = [b for b in page.blocks if b.id not in removed]
    return joined


def _recrop(page, fig, box, out_dir: str) -> bool:
    if not page.raster_ref:
        return False
    path = os.path.join(out_dir, page.raster_ref)
    if not os.path.exists(path):
        return False
    from PIL import Image
    with Image.open(path) as im:
        sx, sy = im.width / page.width_pt, im.height / page.height_pt
        pad = 4
        crop = im.crop((max(0, int((box[0] - pad) * sx)), max(0, int((box[1] - pad) * sy)),
                        min(im.width, int((box[2] + pad) * sx)), min(im.height, int((box[3] + pad) * sy)))).convert("RGB")
    dest = os.path.join(out_dir, fig.image_ref)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    crop.save(dest, "PNG", optimize=True)
    fig.px_w, fig.px_h = crop.size
    return True
