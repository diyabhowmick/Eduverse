"""Scanned page handling.

Text comes from the qwen model. Boxes come from computer vision.
The two are aligned by sequence. Nothing about position ever comes from the
model, because an OCR model returns text, not reliable coordinates.
"""

from __future__ import annotations

import difflib
import re
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from .config import Config
from .schema import Run
from .textclean import clean

MD_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
MD_ITAL = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
MD_BULLET = re.compile(r"^\s*[-*+\u2022]\s+(.*)$")
MD_NUM = re.compile(r"^\s*(\d{1,2})[.)]\s+(.*)$")
MD_TABLE_SEP = re.compile(r"^\s*\|?[\s:\-|]+\|[\s:\-|]*$")
FIGURE_TOKEN = re.compile(r"<<\s*FIGURE\s*>>", re.I)


# ---------------------------------------------------------------------------
# Markdown parsing
# ---------------------------------------------------------------------------

class MdLine:
    __slots__ = ("text", "kind", "level", "runs", "raw", "rows_data")

    def __init__(self, text: str, kind: str, level: Optional[int],
                 runs: List[Run], raw: str):
        self.text = text
        self.kind = kind        # heading|paragraph|list|figure|table|equation
        self.level = level
        self.runs = runs
        self.raw = raw
        self.rows_data = []


# Some OCR models answer in their own layout format rather than in markdown:
# "title [24, 432, 132, 521]UNIT text [48, 593, 112, 713]1". Left alone it is
# published as the page text, which is how the unit title pages came out as
# a string of coordinates.
LAYOUT_TAG_RE = re.compile(
    r"\b(?:title|text|image|image_caption|caption|table|figure|header|footer)"
    r"\s*\[\s*\d+(?:\s*,\s*\d+){1,3}\s*\]", re.I)


def looks_like_layout_markup(md: str) -> bool:
    """Two or more coordinate tags means the model answered in layout, not in
    markdown. One stray match could be real text."""
    return len(LAYOUT_TAG_RE.findall(md or "")) >= 2


def strip_layout_markup(md: str) -> str:
    """Keep the words, drop the tags, and start a new line where each tag was
    so the pieces do not run together."""
    out = LAYOUT_TAG_RE.sub("\n", md or "")
    out = re.sub(r"[ \t]{2,}", " ", out)
    return "\n".join(l.strip() for l in out.splitlines() if l.strip())


def parse_markdown(md: str, cfg=None) -> List[MdLine]:
    out: List[MdLine] = []
    if (cfg is None or getattr(cfg, "strip_ocr_layout_tags", True)) \
            and looks_like_layout_markup(md):
        md = strip_layout_markup(md)
    lines = clean(md or "").splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        if not line.strip():
            i += 1
            continue

        if FIGURE_TOKEN.search(line):
            out.append(MdLine("", "figure", None, [], raw))
            i += 1
            continue

        # table block
        if line.lstrip().startswith("|") and i + 1 < len(lines) \
                and MD_TABLE_SEP.match(lines[i + 1]):
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                if not MD_TABLE_SEP.match(lines[i]):
                    rows.append([c.strip() for c in
                                 lines[i].strip().strip("|").split("|")])
                i += 1
            ml = MdLine("\n".join("\t".join(r) for r in rows), "table", None, [], "")
            ml.rows_data = rows
            out.append(ml)
            continue

        m = MD_HEADING.match(line)
        if m:
            text, runs = _strip_inline(m.group(2))
            out.append(MdLine(text, "heading", min(4, len(m.group(1))), runs, raw))
            i += 1
            continue

        mb = MD_BULLET.match(line)
        if mb:
            text, runs = _strip_inline(mb.group(1))
            out.append(MdLine(text, "list", 0, runs, raw))
            i += 1
            continue

        mn = MD_NUM.match(line)
        if mn:
            text, runs = _strip_inline(line.strip())
            out.append(MdLine(text, "list", 0, runs, raw))
            i += 1
            continue

        if line.strip().startswith("$$"):
            buf = [line.strip()]
            i += 1
            while i < len(lines) and "$$" not in lines[i]:
                buf.append(lines[i])
                i += 1
            if i < len(lines):
                buf.append(lines[i])
                i += 1
            out.append(MdLine("\n".join(buf), "equation", None, [], ""))
            continue

        text, runs = _strip_inline(line.strip())
        out.append(MdLine(text, "paragraph", None, runs, raw))
        i += 1
    return _join_paragraphs(out)


def _strip_inline(s: str) -> Tuple[str, List[Run]]:
    """Remove ** and * markers, returning clean text plus runs by offset."""
    runs: List[Run] = []
    out = []
    i = 0
    while i < len(s):
        if s.startswith("**", i):
            end = s.find("**", i + 2)
            if end > 0:
                inner = s[i + 2:end]
                start = len("".join(out))
                out.append(inner)
                runs.append(Run(s=start, e=start + len(inner), bold=True))
                i = end + 2
                continue
        if s[i] == "*" and not s.startswith("**", i):
            end = s.find("*", i + 1)
            if end > 0:
                inner = s[i + 1:end]
                start = len("".join(out))
                out.append(inner)
                runs.append(Run(s=start, e=start + len(inner), italic=True))
                i = end + 1
                continue
        out.append(s[i])
        i += 1
    return "".join(out), runs


def _join_paragraphs(lines: List[MdLine]) -> List[MdLine]:
    """A wrapped paragraph arrives as several lines. Join them back."""
    out: List[MdLine] = []
    for ml in lines:
        if (out and ml.kind == "paragraph" and out[-1].kind == "paragraph"
                and not out[-1].text.rstrip().endswith((".", ":", "?", "!", ";"))):
            prev = out[-1]
            off = len(prev.text) + 1
            prev.text = prev.text + " " + ml.text
            prev.runs.extend([Run(s=r.s + off, e=r.e + off, bold=r.bold,
                                  italic=r.italic) for r in ml.runs])
        else:
            out.append(ml)
    return out


# ---------------------------------------------------------------------------
# CV line boxes
# ---------------------------------------------------------------------------

def line_boxes(img: Image.Image, exclude_px=None) -> List[Tuple[int, int, int, int]]:
    """Text line boxes by horizontal smearing. Boxes only, no text."""
    g = np.array(img.convert("L"))
    h, w = g.shape
    ink = (g < 190).astype(np.uint8)
    for (x0, y0, x1, y1) in (exclude_px or []):
        ink[max(0, y0):min(h, y1), max(0, x0):min(w, x1)] = 0
    if ink.sum() == 0:
        return []
    try:
        import cv2
        kern = cv2.getStructuringElement(cv2.MORPH_RECT, (max(9, w // 60), 3))
        smear = cv2.dilate(ink, kern, iterations=1)
        n, _, stats, _ = cv2.connectedComponentsWithStats(smear, 8)
        boxes = []
        for i in range(1, n):
            x, y, bw, bh, area = stats[i]
            if bh < 6 or bw < 12 or bh > h * 0.25:
                continue
            boxes.append((int(x), int(y), int(x + bw), int(y + bh)))
    except ImportError:
        boxes = _rows_fallback(ink)
    boxes.sort(key=lambda b: (b[1], b[0]))
    return boxes


def _rows_fallback(ink: np.ndarray):
    rows = ink.sum(axis=1)
    thresh = max(1, int(rows.max() * 0.02))
    boxes = []
    start = None
    for y, v in enumerate(rows):
        if v > thresh and start is None:
            start = y
        elif v <= thresh and start is not None:
            if y - start >= 6:
                cols = np.where(ink[start:y].sum(axis=0) > 0)[0]
                if len(cols):
                    boxes.append((int(cols[0]), start, int(cols[-1]) + 1, y))
            start = None
    return boxes


def word_boxes_in_line(img: Image.Image, line_box) -> List[Tuple[int, int, int, int]]:
    x0, y0, x1, y1 = line_box
    g = np.array(img.convert("L").crop((x0, y0, x1, y1)))
    ink = (g < 190).astype(np.uint8)
    if ink.size == 0:
        return []
    cols = ink.sum(axis=0)
    gap = max(3, int((y1 - y0) * 0.45))
    boxes = []
    start = None
    run0 = 0
    for i, v in enumerate(cols):
        if v > 0:
            if start is None:
                start = i
            run0 = 0
        else:
            if start is not None:
                run0 += 1
                if run0 >= gap:
                    boxes.append((x0 + start, y0, x0 + i - run0 + 1, y1))
                    start = None
                    run0 = 0
    if start is not None:
        boxes.append((x0 + start, y0, x1, y1))
    return boxes


# ---------------------------------------------------------------------------
# Bold on a scan: stroke thickness relative to the page median
# ---------------------------------------------------------------------------

def ink_ratio(img: Image.Image, box) -> float:
    x0, y0, x1, y1 = [int(v) for v in box]
    if x1 <= x0 or y1 <= y0:
        return 0.0
    g = np.array(img.convert("L").crop((x0, y0, x1, y1)))
    if g.size == 0:
        return 0.0
    return float((g < 190).mean())


def page_ink_median(img: Image.Image, boxes) -> float:
    vals = [ink_ratio(img, b) for b in boxes]
    vals = [v for v in vals if v > 0.01]
    return float(np.median(vals)) if vals else 0.0


def bold_runs_from_ink(img: Image.Image, line_box, text: str,
                       median: float, cfg: Config) -> List[Run]:
    """Map heavy words to character ranges by proportional width."""
    if median <= 0 or not text.strip():
        return []
    wboxes = word_boxes_in_line(img, line_box)
    words = text.split()
    if not wboxes or len(wboxes) != len(words):
        return []
    runs: List[Run] = []
    pos = 0
    for w, wb in zip(words, wboxes):
        if (wb[2] - wb[0]) >= cfg.bold_min_word_px // 4:
            if ink_ratio(img, wb) >= median * cfg.bold_ink_ratio:
                runs.append(Run(s=pos, e=pos + len(w), bold=True))
        pos += len(w) + 1
    return runs


# ---------------------------------------------------------------------------
# Alignment: OCR lines to CV boxes
# ---------------------------------------------------------------------------

def align(md_lines: List[MdLine], boxes: List[Tuple[int, int, int, int]]
          ) -> List[Tuple[MdLine, Optional[Tuple[int, int, int, int]]]]:
    """Pair each OCR line with a box, in sequence. Robust to a few misses."""
    text_lines = [m for m in md_lines if m.kind != "figure"]
    if not boxes:
        return [(m, None) for m in md_lines]

    # Rough proportional mapping, then refine by nearest unused box.
    out: List[Tuple[MdLine, Optional[Tuple]]] = []
    n_txt = max(1, len(text_lines))
    used = set()
    ti = 0
    for ml in md_lines:
        if ml.kind == "figure":
            out.append((ml, None))
            continue
        want = int(round(ti * (len(boxes) - 1) / max(1, n_txt - 1))) \
            if n_txt > 1 else 0
        pick = None
        for delta in range(0, len(boxes)):
            for cand in (want + delta, want - delta):
                if 0 <= cand < len(boxes) and cand not in used:
                    pick = cand
                    break
            if pick is not None:
                break
        if pick is not None:
            used.add(pick)
            out.append((ml, boxes[pick]))
        else:
            out.append((ml, None))
        ti += 1
    return out


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a or "", b or "").ratio()
