"""Redraw a figure from its spec.

The point of the spec is that the figure stops being pixels. Once it is a
structure, it can be redrawn at any size, restyled to the EduVerse look,
translated, read aloud, or handed to a model as data. This module does the
redraw for the two structures worth drawing programmatically: charts and
node-and-edge diagrams.

Nothing here invents content. If the spec does not say it, it is not drawn.
"""

from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

INK = "#1a1a1a"
MUT = "#6b6b6b"
LINE = "#c9c7c0"
ACCENT = "#E0212F"
SERIES = ["#E0212F", "#2E6FB7", "#1D7A4C", "#A5730A", "#6B4E9E", "#B7472E"]
FONT = "Arial, Helvetica, sans-serif"


def build(spec: Dict[str, Any], width: float, height: float) -> Optional[str]:
    """Return SVG text, or None when the spec cannot be drawn faithfully."""
    if not isinstance(spec, dict) or not spec:
        return None
    kind = str(spec.get("kind") or "").lower()
    if kind == "chart" or spec.get("chart_type"):
        return _chart(spec, width, height)
    if spec.get("nodes"):
        return _diagram(spec, width, height)
    return None


def is_regenerable(spec: Dict[str, Any]) -> bool:
    """A spec is regenerable when it holds enough to redraw without the image."""
    if not isinstance(spec, dict) or not spec:
        return False
    if spec.get("chart_type"):
        series = spec.get("series") or []
        if not series:
            return False
        vals = [v for s in series for v in (s.get("values") or [])]
        good = [v for v in vals if isinstance(v, (int, float))]
        return len(good) >= 2 and len(good) >= 0.6 * max(1, len(vals))
    nodes = spec.get("nodes") or []
    if len(nodes) >= 2 and all(n.get("label") for n in nodes):
        return True
    return False


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def _chart(spec: Dict[str, Any], width: float, height: float) -> Optional[str]:
    ctype = str(spec.get("chart_type") or "bar").lower()
    cats = [str(c) for c in (spec.get("categories") or [])]
    series = [s for s in (spec.get("series") or []) if s.get("values")]
    if not series:
        return None

    w = max(360.0, float(width) * 2)
    h = max(240.0, float(height) * 2)
    pad_l, pad_r, pad_t, pad_b = 58.0, 18.0, 34.0, 46.0
    if spec.get("title"):
        pad_t = 48.0
    pw = w - pad_l - pad_r
    ph = h - pad_t - pad_b
    if pw <= 20 or ph <= 20:
        return None

    nums = [v for s in series for v in s["values"] if isinstance(v, (int, float))]
    if not nums:
        return None
    vmax = max(nums + [0.0])
    vmin = min(nums + [0.0])
    if vmax == vmin:
        vmax = vmin + 1.0
    span = vmax - vmin

    parts: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" '
        f'width="100%" font-family="{FONT}">',
        f'<rect width="{w:.0f}" height="{h:.0f}" fill="#ffffff"/>',
    ]
    if spec.get("title"):
        parts.append(_text(w / 2, 24, str(spec["title"]), 13, INK, "middle", True))

    # axes and gridlines
    for i in range(5):
        y = pad_t + ph * i / 4
        val = vmax - span * i / 4
        parts.append(f'<line x1="{pad_l:.1f}" y1="{y:.1f}" x2="{pad_l + pw:.1f}" '
                     f'y2="{y:.1f}" stroke="{LINE}" stroke-width="1"/>')
        parts.append(_text(pad_l - 8, y + 4, _fmt(val), 10, MUT, "end"))
    parts.append(f'<line x1="{pad_l:.1f}" y1="{pad_t:.1f}" x2="{pad_l:.1f}" '
                 f'y2="{pad_t + ph:.1f}" stroke="{INK}" stroke-width="1.2"/>')

    n = max(len(cats), max(len(s["values"]) for s in series))
    if ctype in ("bar", "column"):
        group = pw / max(1, n)
        bw = group * 0.72 / max(1, len(series))
        for si, s in enumerate(series):
            col = SERIES[si % len(SERIES)]
            for i, v in enumerate(s["values"][:n]):
                if not isinstance(v, (int, float)):
                    continue
                x = pad_l + group * i + group * 0.14 + bw * si
                y = pad_t + ph * (vmax - v) / span
                bh = pad_t + ph * (vmax - max(vmin, 0)) / span - y
                if bh <= 0:
                    continue
                parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" '
                             f'height="{bh:.1f}" fill="{col}" rx="2"/>')
    else:
        step = pw / max(1, n - 1) if n > 1 else pw
        for si, s in enumerate(series):
            col = SERIES[si % len(SERIES)]
            pts = []
            for i, v in enumerate(s["values"][:n]):
                if not isinstance(v, (int, float)):
                    continue
                x = pad_l + step * i
                y = pad_t + ph * (vmax - v) / span
                pts.append((x, y))
            if len(pts) < 2:
                continue
            d = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f} {y:.1f}"
                         for i, (x, y) in enumerate(pts))
            parts.append(f'<path d="{d}" fill="none" stroke="{col}" '
                         f'stroke-width="2" stroke-linejoin="round"/>')
            for x, y in pts:
                parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{col}"/>')

    # category labels
    for i, c in enumerate(cats[:n]):
        if ctype in ("bar", "column"):
            x = pad_l + (pw / max(1, n)) * (i + 0.5)
        else:
            x = pad_l + (pw / max(1, n - 1) if n > 1 else pw) * i
        parts.append(_text(x, pad_t + ph + 16, _clip(c, 14), 10, MUT, "middle"))

    if spec.get("x_label"):
        parts.append(_text(pad_l + pw / 2, h - 8, str(spec["x_label"]), 11, INK,
                           "middle"))
    if spec.get("y_label"):
        parts.append(f'<text transform="translate(14 {pad_t + ph / 2}) rotate(-90)" '
                     f'text-anchor="middle" font-size="11" fill="{INK}">'
                     f'{escape(str(spec["y_label"]))}</text>')

    named = [s for s in series if s.get("name")]
    if len(named) > 1:
        lx = pad_l + 4
        for si, s in enumerate(named):
            col = SERIES[si % len(SERIES)]
            parts.append(f'<rect x="{lx:.1f}" y="{pad_t - 22:.1f}" width="10" '
                         f'height="10" fill="{col}" rx="2"/>')
            label = _clip(str(s["name"]), 18)
            parts.append(_text(lx + 15, pad_t - 13, label, 10, INK))
            lx += 26 + len(label) * 5.4

    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Diagrams
# ---------------------------------------------------------------------------

def _diagram(spec: Dict[str, Any], width: float, height: float) -> Optional[str]:
    nodes = [n for n in (spec.get("nodes") or []) if n.get("label")]
    if len(nodes) < 2:
        return None
    edges = spec.get("edges") or []
    layout = str(spec.get("layout") or "free").lower()

    w = max(400.0, float(width) * 2)
    h = max(260.0, float(height) * 2)
    placed = _place(nodes, layout, w, h)
    if not placed:
        return None

    parts: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" '
        f'width="100%" font-family="{FONT}">',
        f'<rect width="{w:.0f}" height="{h:.0f}" fill="#ffffff"/>',
        '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M1 1L9 5L1 9z" fill="{INK}"/></marker></defs>',
    ]

    by_id = {n["id"]: p for n, p in zip(nodes, placed) if n.get("id")}
    for e in edges:
        a = by_id.get(e.get("from"))
        b = by_id.get(e.get("to"))
        if not a or not b:
            continue
        x1, y1 = _edge_point(a, b)
        x2, y2 = _edge_point(b, a)
        dash = ' stroke-dasharray="5 4"' if str(e.get("style")) == "dashed" else ""
        parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" '
                     f'y2="{y2:.1f}" stroke="{INK}" stroke-width="1.4"'
                     f'{dash} marker-end="url(#ah)"/>')
        if e.get("label"):
            parts.append(_text((x1 + x2) / 2, (y1 + y2) / 2 - 5,
                               _clip(str(e["label"]), 18), 10, MUT, "middle"))

    for node, p in zip(nodes, placed):
        shape = str(node.get("shape") or "box").lower()
        label = _clip(str(node["label"]), 22)
        if shape == "label":
            parts.append(_text(p["cx"], p["cy"] + 4, label, 11, INK, "middle"))
            continue
        if shape in ("circle", "ellipse"):
            parts.append(f'<ellipse cx="{p["cx"]:.1f}" cy="{p["cy"]:.1f}" '
                         f'rx="{p["w"] / 2:.1f}" ry="{p["h"] / 2:.1f}" '
                         f'fill="#fbfaf7" stroke="{INK}" stroke-width="1.3"/>')
        else:
            parts.append(f'<rect x="{p["x"]:.1f}" y="{p["y"]:.1f}" '
                         f'width="{p["w"]:.1f}" height="{p["h"]:.1f}" rx="6" '
                         f'fill="#fbfaf7" stroke="{INK}" stroke-width="1.3"/>')
        parts.append(_text(p["cx"], p["cy"] + 4, label, 11, INK, "middle"))

    for a in (spec.get("annotations") or []):
        if not a.get("text"):
            continue
        x = _frac(a.get("x"), 0.5) * w
        y = _frac(a.get("y"), 0.5) * h
        parts.append(_text(x, y, _clip(str(a["text"]), 30), 10, MUT, "middle"))

    parts.append("</svg>")
    return "".join(parts)


def _place(nodes, layout: str, w: float, h: float) -> List[Dict[str, float]]:
    n = len(nodes)
    bw, bh = min(150.0, w / max(3, n) * 1.5), 44.0
    out: List[Dict[str, float]] = []

    have_coords = all(isinstance(nd.get("x"), (int, float))
                      and isinstance(nd.get("y"), (int, float)) for nd in nodes)
    for i, nd in enumerate(nodes):
        if have_coords:
            cx = _frac(nd.get("x"), 0.5) * w
            cy = _frac(nd.get("y"), 0.5) * h
            nw = (float(nd["w"]) * w if isinstance(nd.get("w"), (int, float))
                  and 0 < nd["w"] <= 1 else bw)
            nh = (float(nd["h"]) * h if isinstance(nd.get("h"), (int, float))
                  and 0 < nd["h"] <= 1 else bh)
        elif layout == "cycle":
            ang = 2 * math.pi * i / n - math.pi / 2
            r = min(w, h) * 0.34
            cx, cy = w / 2 + r * math.cos(ang), h / 2 + r * math.sin(ang)
            nw, nh = bw, bh
        elif layout == "hierarchy":
            rows = max(1, math.ceil(n / 3))
            row, col = divmod(i, 3)
            cx = w * (col + 1) / 4
            cy = h * (row + 1) / (rows + 1)
            nw, nh = bw, bh
        else:                                   # flow, parts, free
            cx = w * (i + 0.5) / n
            cy = h / 2
            nw, nh = min(bw, w / n - 16), bh
        nw = max(56.0, min(nw, w * 0.42))
        nh = max(30.0, min(nh, h * 0.4))
        out.append({"cx": cx, "cy": cy, "w": nw, "h": nh,
                    "x": cx - nw / 2, "y": cy - nh / 2})
    return out


def _edge_point(a: Dict[str, float], b: Dict[str, float]) -> Tuple[float, float]:
    dx, dy = b["cx"] - a["cx"], b["cy"] - a["cy"]
    if dx == 0 and dy == 0:
        return a["cx"], a["cy"]
    sx = (a["w"] / 2) / abs(dx) if dx else 1e9
    sy = (a["h"] / 2) / abs(dy) if dy else 1e9
    s = min(sx, sy)
    return a["cx"] + dx * s, a["cy"] + dy * s


# ---------------------------------------------------------------------------

def _text(x, y, s, size, fill, anchor="start", bold=False):
    weight = ' font-weight="600"' if bold else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" '
            f'text-anchor="{anchor}"{weight}>{escape(s)}</text>')


def _clip(s: str, n: int) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "\u2026"


def _fmt(v: float) -> str:
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    if abs(v) >= 10:
        return f"{v:.0f}"
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _frac(v, default: float) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return min(max(f, 0.0), 1.0)


def save(spec: Dict[str, Any], path: str, width: float, height: float
         ) -> Optional[str]:
    svg = build(spec, width, height)
    if not svg:
        return None
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(svg)
    return path
