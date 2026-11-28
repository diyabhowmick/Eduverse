"""A solved drawing to SVG, in the look of the figures M2 redraws for the books.

The palette, font and text helper are svgdraw's (M1), imported, not copied. The output is inert so it can be
inlined into a page: shapes and text only, every attribute a number or a constant, every piece of text escaped.
No script, no links, no external references, no images. draw_check.py verifies that on the output.
"""
import math

from . import m1  # noqa: F401  puts M1 (svgdraw) on the path
from eduverse_book2docx.svgdraw import ACCENT, FONT, INK, MUT, _text  # noqa: E402

from .draw_solve import FONT_SIZE, layout_labels  # noqa: E402  one label estimator, shared with the fit and the gate

STROKE = 2
MARK = 14         # px: right-angle square side, angle arc radius (both shrink on short sides)


def compile_svg(spec, solved) -> str:
    """SVG text for a spec that passed validate() and solve()."""
    w, h, pts = solved["width"], solved["height"], solved["points"]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" font-family="{FONT}">',
           f'<rect width="{w}" height="{h}" fill="#ffffff"/>']
    line = f'fill="none" stroke="{INK}" stroke-width="{STROKE}" stroke-linejoin="round" stroke-linecap="round"'

    for c in solved["circles"]:
        out.append(f'<circle cx="{c["cx"]:.2f}" cy="{c["cy"]:.2f}" r="{c["r"]:.2f}" {line}/>')
    for poly in spec.get("polygons", []):
        coords = " ".join(f"{pts[n][0]:.2f},{pts[n][1]:.2f}" for n in poly["points"])
        tag = "polygon" if poly.get("closed", True) else "polyline"
        out.append(f'<{tag} points="{coords}" {line}/>')
    for s in spec.get("segments", []):
        (x1, y1), (x2, y2) = pts[s["from"]], pts[s["to"]]
        out.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" {line}/>')

    for a in spec.get("angles", []):
        p, v, q = (pts[n] for n in a["points"])
        u, t = _unit(v, p), _unit(v, q)
        if u is None or t is None:
            continue
        r = min(MARK, 0.3 * math.dist(v, p), 0.3 * math.dist(v, q))
        mark = f'fill="none" stroke="{ACCENT}" stroke-width="1.5"'
        if a.get("right"):
            c1 = (v[0] + u[0] * r, v[1] + u[1] * r)
            c2 = (c1[0] + t[0] * r, c1[1] + t[1] * r)
            c3 = (v[0] + t[0] * r, v[1] + t[1] * r)
            out.append(f'<polyline points="{c1[0]:.2f},{c1[1]:.2f} {c2[0]:.2f},{c2[1]:.2f} {c3[0]:.2f},{c3[1]:.2f}" {mark}/>')
        else:
            r = min(r * 1.6, 0.4 * math.dist(v, p), 0.4 * math.dist(v, q))
            sweep = 1 if u[0] * t[1] - u[1] * t[0] > 0 else 0     # y points down: a positive turn is clockwise on screen
            s0, s1 = (v[0] + u[0] * r, v[1] + u[1] * r), (v[0] + t[0] * r, v[1] + t[1] * r)
            out.append(f'<path d="M{s0[0]:.2f} {s0[1]:.2f} A{r:.2f} {r:.2f} 0 0 {sweep} {s1[0]:.2f} {s1[1]:.2f}" {mark}/>')

    for x, y in pts.values():
        out.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" fill="{INK}"/>')

    for lb in layout_labels(spec, solved):
        colour = MUT if lb["segment"] else INK
        out.append(_text(lb["cx"], lb["cy"] + FONT_SIZE * 0.35, lb["text"], FONT_SIZE, colour, "middle"))
    out.append("</svg>")
    return "".join(out)


def _unit(a, b):
    d = math.dist(a, b)
    return None if d < 1e-9 else ((b[0] - a[0]) / d, (b[1] - a[1]) / d)
