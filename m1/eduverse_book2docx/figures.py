"""Figures.

Position and size ALWAYS come from geometry, never from a model. The model is
only ever asked what the picture shows. That separation is what keeps images
landing in the right place at the right size.
"""

from __future__ import annotations

import io
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from . import svgdraw
from .config import Config
from .ledger import Ledger
from .ollama_client import OllamaClient
from .schema import Block, FigureMeta, Page


# ---------------------------------------------------------------------------
# Region detection on a rasterised page (scanned and hybrid pages)
# ---------------------------------------------------------------------------

def detect_regions(page_img: Image.Image, text_boxes_px: List[Tuple[int, int, int, int]],
                   cfg: Config) -> List[Tuple[int, int, int, int]]:
    """Find picture areas by removing known text boxes then grouping ink."""
    g = np.array(page_img.convert("L"))
    h, w = g.shape
    ink = (g < 200).astype(np.uint8)

    for (x0, y0, x1, y1) in text_boxes_px:
        x0 = max(0, min(w - 1, int(x0) - 2))
        x1 = max(0, min(w, int(x1) + 2))
        y0 = max(0, min(h - 1, int(y0) - 2))
        y1 = max(0, min(h, int(y1) + 2))
        if x1 > x0 and y1 > y0:
            ink[y0:y1, x0:x1] = 0

    if ink.sum() == 0:
        return []

    k = max(3, cfg.figure_merge_gap_px)
    dil = _dilate(ink, k)
    boxes = _components(dil, min_area=int(cfg.figure_min_area_frac * w * h))
    merged = _merge_close(boxes, cfg.figure_merge_gap_px * 2)
    out = []
    for (x0, y0, x1, y1) in merged:
        if (x1 - x0) < 24 or (y1 - y0) < 24:
            continue
        sub = ink[y0:y1, x0:x1]
        if sub.size == 0 or sub.mean() < 0.004:      # near-empty region
            continue
        out.append((x0, y0, x1, y1))
    return out


def _dilate(mask: np.ndarray, k: int) -> np.ndarray:
    try:
        import cv2
        kern = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
        return cv2.dilate(mask, kern, iterations=1)
    except ImportError:
        pad = k // 2
        p = np.pad(mask, pad)
        out = np.zeros_like(mask)
        for dy in range(k):
            for dx in range(k):
                out |= p[dy:dy + mask.shape[0], dx:dx + mask.shape[1]]
        return out


def _components(mask: np.ndarray, min_area: int) -> List[Tuple[int, int, int, int]]:
    try:
        import cv2
        n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        out = []
        for i in range(1, n):
            x, y, w, h, area = stats[i]
            if area >= min_area:
                out.append((int(x), int(y), int(x + w), int(y + h)))
        return out
    except ImportError:
        return _components_slow(mask, min_area)


def _components_slow(mask, min_area):
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    out = []
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            if mask[y, x] and not seen[y, x]:
                stack = [(y, x)]
                seen[y, x] = True
                x0 = x1 = x
                y0 = y1 = y
                area = 0
                while stack:
                    cy, cx = stack.pop()
                    area += 1
                    x0, x1 = min(x0, cx), max(x1, cx)
                    y0, y1 = min(y0, cy), max(y1, cy)
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] \
                                and not seen[ny, nx]:
                            seen[ny, nx] = True
                            stack.append((ny, nx))
                if area >= min_area:
                    out.append((x0, y0, x1 + 1, y1 + 1))
    return out


def _merge_close(boxes, gap: int):
    boxes = list(boxes)
    changed = True
    while changed:
        changed = False
        out = []
        while boxes:
            b = boxes.pop()
            merged = False
            for i, o in enumerate(out):
                if _near(b, o, gap):
                    out[i] = (min(b[0], o[0]), min(b[1], o[1]),
                              max(b[2], o[2]), max(b[3], o[3]))
                    merged = True
                    changed = True
                    break
            if not merged:
                out.append(b)
        boxes = out
    return boxes


def _near(a, b, gap: int) -> bool:
    return not (a[2] + gap < b[0] or b[2] + gap < a[0]
                or a[3] + gap < b[1] or b[3] + gap < a[1])


# ---------------------------------------------------------------------------
# Clustering fragments into whole figures
# ---------------------------------------------------------------------------

def cluster(rects: List[Tuple[float, float, float, float]],
            text_boxes: List[Tuple[float, float, float, float]],
            page_area: float, cfg: Config,
            captions: Optional[List[Tuple[float, float, float, float]]] = None,
            gutters: Optional[List[Tuple[float, float]]] = None,
            box_edges: Optional[List[Tuple[float, float, float, float]]] = None,
            ) -> List[Tuple[Tuple[float, float, float, float], List[int]]]:
    """Group fragments of one illustration into a single region.

    A PDF is free to store a clock face as one image and its hands, numerals and
    tick marks as five more. Each is a real object, none of them is a figure on
    its own. Two candidates join when they touch, nearly touch, or one sits
    inside the other, and when no line of text runs between them.

    Returns the merged rectangle plus the indexes of the fragments it swallowed,
    so the ledger can account for every one of them.
    """
    if not rects:
        return []
    if not cfg.fragment_merge:
        return [(r, [i]) for i, r in enumerate(rects)]

    groups = [[i] for i in range(len(rects))]
    boxes = [list(r) for r in rects]
    gap = cfg.fragment_gap_pt

    changed = True
    while changed:
        changed = False
        for i in range(len(boxes)):
            if boxes[i] is None:
                continue
            for j in range(i + 1, len(boxes)):
                if boxes[j] is None:
                    continue
                if not _joins(boxes[i], boxes[j], gap):
                    continue
                if _text_between(boxes[i], boxes[j], text_boxes):
                    continue
                if _caption_between(boxes[i], boxes[j], captions or []):
                    continue                       # rules 27 and 29
                if _gutter_between(boxes[i], boxes[j], gutters or []):
                    continue                       # rule 27
                if _box_edge_between(boxes[i], boxes[j], box_edges or []):
                    continue                       # rule 27
                merged = _union(boxes[i], boxes[j])
                if _too_much_growth(boxes[i], boxes[j], merged, cfg):
                    continue
                if _area(merged) > page_area * 0.92:
                    continue
                boxes[i] = merged
                groups[i] = groups[i] + groups[j]
                boxes[j] = None
                groups[j] = []
                changed = True

    return [(tuple(b), sorted(groups[i]))
            for i, b in enumerate(boxes) if b is not None]


def _joins(a, b, gap: float) -> bool:
    if _contains(a, b) or _contains(b, a):
        return True
    return not (a[2] + gap < b[0] or b[2] + gap < a[0]
                or a[3] + gap < b[1] or b[3] + gap < a[1])


def _contains(outer, inner, tol: float = 2.0) -> bool:
    return (inner[0] >= outer[0] - tol and inner[1] >= outer[1] - tol
            and inner[2] <= outer[2] + tol and inner[3] <= outer[3] + tol)


def _union(a, b):
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def _area(r) -> float:
    return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])


def _too_much_growth(a, b, merged, cfg: Config) -> bool:
    """Never let a caption sized speck drag a big figure into a much larger
    box, which is how two separate figures get glued together."""
    big = max(_area(a), _area(b))
    if big <= 0:
        return False
    return _area(merged) / big > cfg.fragment_max_growth


def _text_between(a, b, text_boxes) -> bool:
    """A line of text running between two candidates means they are two
    figures, not one broken into pieces."""
    gap_box = _gap_rect(a, b)
    if gap_box is None:
        return False
    for t in text_boxes:
        ix = min(gap_box[2], t[2]) - max(gap_box[0], t[0])
        iy = min(gap_box[3], t[3]) - max(gap_box[1], t[1])
        if ix > 2 and iy > 2:
            return True
    return False


def _caption_between(a, b, captions) -> bool:
    """Two pictures with a caption between them are two figures. A grid of
    photos under ONE caption stays together, because nothing separates them."""
    gap = _gap_rect(a, b)
    if gap is None:
        return False
    for c in captions:
        ix = min(gap[2], c[2]) - max(gap[0], c[0])
        iy = min(gap[3], c[3]) - max(gap[1], c[1])
        if ix > 2 and iy > 2:
            return True
    return False


def _gutter_between(a, b, gutters) -> bool:
    for g0, g1 in gutters:
        gx = (g0 + g1) / 2
        if (a[2] <= gx <= b[0]) or (b[2] <= gx <= a[0]):
            return True
    return False


def _box_edge_between(a, b, boxes) -> bool:
    """One piece inside a panel and one outside it are not one picture."""
    for box in boxes:
        ina = _contains(box, a)
        inb = _contains(box, b)
        if ina != inb:
            return True
    return False


def is_grid(rects: List[Tuple[float, float, float, float]],
            cfg: Config) -> bool:
    """Rule 28: several similar pictures in a tidy grid under one caption are
    one figure. Judged by shape, not by content."""
    if len(rects) < cfg.grid_min_parts:
        return False
    ws = [r[2] - r[0] for r in rects]
    hs = [r[3] - r[1] for r in rects]
    if min(ws) <= 0 or min(hs) <= 0:
        return False
    if max(ws) / min(ws) > cfg.grid_size_tolerance:
        return False
    if max(hs) / min(hs) > cfg.grid_size_tolerance:
        return False
    xs = sorted({round(r[0], 0) for r in rects})
    ys = sorted({round(r[1], 0) for r in rects})
    return len(xs) <= 4 and len(ys) <= 4 and (len(xs) > 1 or len(ys) > 1)


def _gap_rect(a, b):
    if a[2] < b[0]:
        x0, x1 = a[2], b[0]
    elif b[2] < a[0]:
        x0, x1 = b[2], a[0]
    else:
        x0, x1 = max(a[0], b[0]), min(a[2], b[2])
    if a[3] < b[1]:
        y0, y1 = a[3], b[1]
    elif b[3] < a[1]:
        y0, y1 = b[3], a[1]
    else:
        y0, y1 = max(a[1], b[1]), min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return None
    return [x0, y0, x1, y1]


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def phash(img: Image.Image, bits: int = 8) -> int:
    """Average hash. Small, fast, and stable against rescaling and requantising,
    which is exactly how the same picture comes back looking slightly different
    the second time a PDF places it."""
    g = img.convert("L").resize((bits, bits), Image.LANCZOS)
    a = np.asarray(g, dtype=np.float32)
    mean = float(a.mean())
    bitsv = (a > mean).flatten()
    out = 0
    for b in bitsv:
        out = (out << 1) | int(b)
    return out


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def near_duplicate(a: int, b: int, cfg: Config) -> bool:
    return hamming(a, b) <= cfg.dup_max_distance


def is_code_like(img: Image.Image) -> bool:
    """A QR code, a barcode or any dense machine code.

    Every one of them is fine grained black and white noise, so every hash puts
    them within a hair of each other and the dedupe reads four different codes
    as one picture printed four times. They are content and are never a
    watermark, so they are kept out of the comparison altogether.
    """
    w, h = img.size
    if w < 8 or h < 8:
        return False
    ar = w / float(h)
    if ar < 0.55 or ar > 1.8:              # codes are square or nearly so
        return False
    g = np.asarray(img.convert("L").resize((64, 64), Image.LANCZOS),
                   dtype=np.float32)
    mid = (g.min() + g.max()) / 2.0
    if g.max() - g.min() < 60:             # flat, not a code
        return False
    bw = g > mid
    ink = float(bw.mean())
    if ink < 0.25 or ink > 0.75:           # a code is roughly half dark
        return False
    flips = float((bw[:, 1:] != bw[:, :-1]).mean()
                  + (bw[1:, :] != bw[:-1, :]).mean()) / 2.0
    return flips > 0.22                    # cell to cell switching, not shapes


def drop_repeating(book, ledger, cfg, out_dir: str) -> int:
    """A picture that appears on most pages is a logo, a watermark or a border,
    not content. Same principle as a running head, applied to images.

    Hashes are read back from the saved crops, so this runs once at the end and
    needs nothing kept in memory during extraction.
    """
    if not cfg.dedupe_images or len(book.pages) < 4:
        return 0

    seen: Dict[int, List] = {}
    for page in book.pages:
        for b in page.blocks:
            if b.type != "figure" or not b.image_ref:
                continue
            path = os.path.join(out_dir, b.image_ref)
            if not os.path.exists(path):
                continue
            try:
                with Image.open(path) as im:
                    if cfg.skip_code_like_dedupe and is_code_like(im):
                        continue
                    h = phash(im, cfg.dup_hash_bits)
            except Exception:
                continue
            key = next((k for k in seen if near_duplicate(k, h, cfg)), h)
            seen.setdefault(key, []).append((page.page, b.id))

    threshold = max(3, int(len(book.pages) * cfg.repeat_image_page_frac))
    doomed: Dict[str, int] = {}
    for _key, hits in seen.items():
        pages = {p for p, _ in hits}
        if len(pages) >= threshold:
            for _p, bid in hits:
                doomed[bid] = len(pages)

    if not doomed:
        return 0
    removed = 0
    for page in book.pages:
        keep = []
        for b in page.blocks:
            if b.id in doomed:
                ledger.drop(b.id, page.page, "watermark",
                            f"same picture on {doomed[b.id]} pages",
                            b.bbox_pt)
                removed += 1
                continue
            if b.type == "figure_note" and b.caption_of in doomed:
                removed += 1
                continue
            keep.append(b)
        page.blocks = keep
    ledger.emitted -= removed
    return removed


def is_flat(img: Image.Image) -> bool:
    """A crop with almost no variation is a rule, a background block or a blank
    patch, not a figure."""
    g = np.asarray(img.convert("L"), dtype=np.float32)
    return bool(g.size == 0 or g.std() < 3.0)


# ---------------------------------------------------------------------------
# Cropping and describing
# ---------------------------------------------------------------------------

def crop_and_save(page_img: Image.Image, box_px: Tuple[int, int, int, int],
                  out_path: str, cfg: Config) -> Tuple[int, int]:
    x0, y0, x1, y1 = box_px
    b = cfg.figure_bleed_px
    x0 = max(0, x0 - b)
    y0 = max(0, y0 - b)
    x1 = min(page_img.width, x1 + b)
    y1 = min(page_img.height, y1 + b)
    crop = page_img.crop((x0, y0, x1, y1))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    crop.save(out_path, "PNG", optimize=True)
    return crop.size


def to_png_bytes(img: Image.Image, max_edge: int = 1400) -> bytes:
    im = img
    if max(im.size) > max_edge:
        scale = max_edge / max(im.size)
        im = im.resize((max(1, int(im.width * scale)),
                        max(1, int(im.height * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "PNG", optimize=True)
    return buf.getvalue()


def split_composite(client: OllamaClient, crop: Image.Image,
                    cfg: Config) -> List[Tuple[float, float, float, float]]:
    """Ask the VLM how many figures are inside one region. Fractions only."""
    if not cfg.composite_split or cfg.offline:
        return [(0.0, 0.0, 1.0, 1.0)]
    if crop.width < 200 or crop.height < 200:
        return [(0.0, 0.0, 1.0, 1.0)]
    try:
        parts = client.split_composite(to_png_bytes(crop, 900))
    except Exception:
        return [(0.0, 0.0, 1.0, 1.0)]
    if len(parts) < cfg.composite_min_parts:
        return [(0.0, 0.0, 1.0, 1.0)]
    return [(p["x0"], p["y0"], p["x1"], p["y1"]) for p in parts]


# A mark like a seal or a logo carries the identity of the book and usually
# prints words inside itself. Models call these decorative because they sit in
# a margin and carry no lesson, and the region is then thrown away with its
# text still inside it. A decorative verdict has to survive this first.
_MARK_RE = re.compile(
    r"\b(emblem|seal|crest|coat[- ]of[- ]arms|logo|insignia|monogram|"
    r"masthead|badge|stamp|crown|qr[- ]?code|barcode|"
    r"letterhead|watermark)\b", re.I)


def decorative_stands(d: Dict[str, Any]) -> bool:
    """True only when the crop really is ornament: nothing printed in it,
    nothing named in it, and nothing that reads as a mark."""
    if any(str(x).strip() for x in (d.get("text_in_image") or [])):
        return False
    if any(str(x).strip() for x in (d.get("entities") or [])):
        return False
    blob = f"{d.get('desc') or ''} {d.get('label') or ''}"
    return not _MARK_RE.search(blob)


def describe(client: OllamaClient, crop: Image.Image, cfg: Config) -> FigureMeta:
    if not cfg.describe_figures:
        return FigureMeta(error="description pass switched off")
    if cfg.offline:
        return FigureMeta(error="running offline, no model was called")
    try:
        d = client.describe_figure(to_png_bytes(crop))
    except Exception as exc:
        # A failed call must never look like a figure that simply had nothing
        # to say. The reason is carried through to the box and the report.
        return FigureMeta(error=f"{type(exc).__name__}: {exc}"[:200])
    kind = str(d.get("fig_kind", "photo")).lower().strip()
    if kind not in ("photo", "diagram", "chart", "map", "text_banner", "decorative"):
        kind = "photo"
    if kind == "decorative" and not decorative_stands(d):
        # the verdict would have discarded a seal, a logo or a region with
        # printed text in it, so it is overruled here rather than at the drop
        kind = "photo"
    if not str(d.get("desc") or "").strip():
        return FigureMeta(fig_kind=kind,
                          error="the model returned no description")
    return FigureMeta(
        fig_kind=kind,
        text_only=bool(d.get("text_only")) or kind == "text_banner",
        label=str(d.get("label") or "")[:120],
        desc=str(d.get("desc") or "").strip(),
        entities=[str(x)[:80] for x in (d.get("entities") or [])][:40],
        relationships=[str(x)[:160] for x in (d.get("relationships") or [])][:40],
        data_points=[str(x)[:80] for x in (d.get("data_points") or [])][:80],
        text_in_image=[str(x)[:120] for x in (d.get("text_in_image") or [])][:60],
    )


def enrich(client: OllamaClient, crop: Image.Image, meta: FigureMeta,
           cfg: Config, out_dir: str, fig_id: str,
           w_pt: float, h_pt: float) -> None:
    """Turn a described figure into a regenerable one.

    A prose description tells a reader what the picture shows. A spec lets the
    picture be rebuilt without the pixels, which is the whole point: once a
    diagram is nodes and edges it can be restyled, resized, translated, read
    aloud, or handed to a model as data.
    """
    if not cfg.figure_spec or cfg.offline:
        return
    if meta.fig_kind not in cfg.spec_kinds:
        return
    try:
        spec = client.figure_spec(to_png_bytes(crop), meta.fig_kind)
    except Exception:
        return
    if not spec:
        return
    spec.setdefault("kind", "chart" if spec.get("chart_type") else "diagram")
    meta.spec = spec
    meta.regenerable = svgdraw.is_regenerable(spec)

    if meta.regenerable and cfg.emit_svg:
        path = os.path.join(out_dir, "figures", f"{fig_id}.svg")
        if svgdraw.save(spec, path, w_pt, h_pt):
            meta.svg_ref = f"figures/{fig_id}.svg"


def as_table(client: OllamaClient, crop: Image.Image, cfg: Config
             ) -> Optional[dict]:
    """A picture of a table is still a table. Pull the cells out of it."""
    if not cfg.vlm_tables or cfg.offline:
        return None
    try:
        d = client.read_table(to_png_bytes(crop))
    except Exception:
        return None
    if not d.get("is_table"):
        return None
    header = [str(x) for x in (d.get("header") or [])]
    rows = [[str(x) for x in r] for r in (d.get("rows") or [])
            if isinstance(r, list)]
    if not rows or len(rows) < 2 or max(len(r) for r in rows) < 2:
        return None
    return {"header": header, "rows": rows, "caption": str(d.get("caption") or "")}


def read_math(client: OllamaClient, crop: Image.Image, cfg: Config
              ) -> Optional[str]:
    """Read a formula the text layer could not give us. Validated before use,
    so an unreadable one still falls back to the image rather than to a wrong
    formula typed out confidently."""
    if not cfg.vlm_math or cfg.offline:
        return None
    from .mathtools import prepare
    try:
        d = client.read_math(to_png_bytes(crop))
    except Exception:
        return None
    raw = str(d.get("latex") or "").strip()
    if not raw or not d.get("confident"):
        return None
    latex, _why = prepare(raw)
    return latex


def save_meta(meta: FigureMeta, path: str) -> None:
    import json
    from dataclasses import asdict
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(asdict(meta), fh, ensure_ascii=False, indent=2)


def post_filter(block: Block, ledger: Ledger) -> bool:
    """text_banner and decorative are not figures. Returns True to keep."""
    if block.figure is None:
        return True
    if block.figure.fig_kind == "decorative":
        if not decorative_stands({
                "text_in_image": block.figure.text_in_image,
                "entities": block.figure.entities,
                "desc": block.figure.desc,
                "label": block.figure.label}):
            # second net, for figures described by a path that did not go
            # through describe(): a mark is never ornament
            block.figure.fig_kind = "photo"
            return True
        ledger.drop(block.id, block.page, "decorative",
                    "VLM classified the region as decorative", block.bbox_pt)
        return False
    return True
