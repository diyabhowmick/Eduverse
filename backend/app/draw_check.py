"""The gate. Nothing reaches a student unchecked.

check(spec, solved, svg) returns findings, each {"severity": "error" | "warning", "code", "message"}.
An error means the drawing must not be shown.

  length        a stated segment length disagrees with the drawing
  label_length  a side's label ("5 cm") disagrees with the drawing
  angle         a stated angle, or a right-angle mark, disagrees with the drawing
  overlap       two labels cover each other
  outside       something is drawn outside the canvas
  unsafe        the SVG holds something that could run, link or load: it must stay inert when inlined
"""
import math
import re
import xml.etree.ElementTree as ET

from . import draw_spec as S
from .draw_solve import layout_labels

# A correct solve is exact to about 1e-12. A student with a ruler reads to the nearest millimetre, which on a
# 5 cm side is 2%; 1% catches every disagreement they could measure and leaves float error far below it.
LENGTH_TOL = 0.01
# A side's label is rounded for print, so it gets more room than a stated length: within 5% of what is measured,
# and within the rounding of its last digit (see the label check below). 5% keeps "7" for 7.07 and "2 in" for
# 5 cm, and refuses "1" for 1.4.
LABEL_TOL = 0.05
# A protractor reads to the nearest degree; half a degree catches every disagreement one can show.
ANGLE_TOL = 0.5
# A label is checked only when the whole of it is a quantity: optional spaces, a number, an optional unit, and
# nothing else. "5", "5 cm" and "5cm" qualify; "about 5 cm", "side = 5" and "Figure 5" do not, and are ignored
# without a finding: a label that cannot be read is not evidence of a mistake.
QUANTITY = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([A-Za-z]{1,6})?\s*$")
# A label's unit may differ from the drawing's ("50 mm" on a drawing in cm). Lengths that convert are compared
# after conversion; a label in a unit not listed here, or on a drawing whose own unit is not listed, is skipped.
MM_PER = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "ft": 304.8}
# Overlap is measured as the share of the smaller label's box that the other covers. Any overlap is a warning.
# The boxes are estimates (average glyph width, 1.2x the font size tall), so a sliver of overlap is usually
# padding round the glyphs and the text still reads. Past a third, whole characters disappear under the other
# label, so that is an error.
OVERLAP_ERROR = 1 / 3
# The only elements and attributes a compiled drawing uses. Anything else is unsafe, whatever it is.
TAGS = {"svg", "rect", "circle", "line", "polygon", "polyline", "path", "text"}
ATTRS = {"xmlns", "viewBox", "width", "height", "font-family", "fill", "stroke", "stroke-width", "stroke-linejoin",
         "stroke-linecap", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "points", "d", "font-size",
         "font-weight", "text-anchor"}


def has_errors(findings) -> bool:
    return any(f["severity"] == "error" for f in findings)


def check(spec, solved, svg: str) -> list:
    found = []

    def add(severity, code, message):
        found.append({"severity": severity, "code": code, "message": message})

    pts, scale, unit = solved["points"], solved["scale"], solved["unit"]
    u = f" {unit}" if unit else ""

    # --- measurements against what is drawn
    for s in spec.get("segments", []):
        a, b = s["from"], s["to"]
        real = math.dist(pts[a], pts[b]) / scale
        if "length" in s:
            want = S.quantity(s["length"])[0]
            if abs(real - want) > LENGTH_TOL * want:
                add("error", "length", f"Side {a}{b} is stated as {want:g}{u} but the drawing makes it {real:.3g}{u}.")
    for lb in layout_labels(spec, solved):
        if not lb["segment"]:
            continue
        m = QUANTITY.match(lb["text"])
        if not m:
            continue
        said, said_unit = float(m.group(1)), (m.group(2) or "").lower()
        a, b = lb["segment"]
        real = math.dist(pts[a], pts[b]) / scale         # in the drawing's unit
        shown = f"{real:.3g}{u}"
        if said_unit and unit and said_unit != unit.lower():
            if said_unit not in MM_PER or unit.lower() not in MM_PER:
                continue    # a unit we cannot convert is not evidence of a mistake
            real = real * MM_PER[unit.lower()] / MM_PER[said_unit]
            shown = f"{real:.3g} {said_unit} ({shown.strip()})"
        # A label printed as "7" stands for anything that rounds to 7: half its last digit either way. That band
        # widens as the unit coarsens ("1 cm" would accept 0.5 to 1.5 cm), so the label must also be within
        # LABEL_TOL of what is measured. The tighter of the two wins. The 1e-9 only absorbs float noise.
        decimals = len(m.group(1).split(".")[1]) if "." in m.group(1) else 0
        allowed = min(0.5 * 10 ** -decimals, LABEL_TOL * real) + 1e-9 * max(1.0, real)
        if abs(real - said) > allowed:
            add("error", "label_length", f"Side {a}{b} is labelled {lb['text'].strip()!r} but the drawing makes it {shown}.")
    for a in spec.get("angles", []):
        want = 90.0 if a.get("right") else S.quantity(a["degrees"])[0] if "degrees" in a else None
        if want is None:
            continue
        p, v, q = a["points"]
        real = _angle(pts[p], pts[v], pts[q])
        if real is None or abs(real - want) > ANGLE_TOL:
            what = "marked as a right angle" if a.get("right") else f"stated as {want:g}°"
            add("error", "angle", f"Angle {p}{v}{q} is {what} but the drawing makes it "
                                  f"{'nothing' if real is None else f'{real:.1f}°'}.")

    # --- labels covering each other
    boxes = layout_labels(spec, solved)
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            ow = min(a["cx"] + a["w"] / 2, b["cx"] + b["w"] / 2) - max(a["cx"] - a["w"] / 2, b["cx"] - b["w"] / 2)
            oh = min(a["cy"] + a["h"] / 2, b["cy"] + b["h"] / 2) - max(a["cy"] - a["h"] / 2, b["cy"] - b["h"] / 2)
            if ow <= 0 or oh <= 0:
                continue
            share = ow * oh / min(a["w"] * a["h"], b["w"] * b["h"])
            add("error" if share > OVERLAP_ERROR else "warning", "overlap",
                f"The labels {a['text']!r} and {b['text']!r} overlap ({share:.0%} of the smaller one is covered).")

    # --- everything inside the canvas
    w, h = solved["width"], solved["height"]

    def inside(x0, y0, x1, y1, what):
        if x0 < -0.5 or y0 < -0.5 or x1 > w + 0.5 or y1 > h + 0.5:
            add("error", "outside", f"{what} is drawn outside the {w}x{h} canvas.")

    for n, (x, y) in pts.items():
        inside(x, y, x, y, f"Point {n}")
    for i, c in enumerate(solved["circles"]):
        inside(c["cx"] - c["r"], c["cy"] - c["r"], c["cx"] + c["r"], c["cy"] + c["r"], f"Circle {i + 1}")
    for lb in boxes:
        inside(lb["cx"] - lb["w"] / 2, lb["cy"] - lb["h"] / 2, lb["cx"] + lb["w"] / 2, lb["cy"] + lb["h"] / 2,
               f"The label {lb['text']!r}")

    # --- inert: parse what was actually produced, and allow only what the compiler writes
    if re.search(r"<!(DOCTYPE|ENTITY)|<\?xml-stylesheet", svg, re.I):
        add("error", "unsafe", "The SVG declares a document type, entity or stylesheet.")
        return found
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as e:
        add("error", "unsafe", f"The SVG is not well-formed XML ({e}).")
        return found
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag not in TAGS:
            add("error", "unsafe", f"The SVG contains a <{tag}> element, which a drawing never uses.")
        for k, v in el.attrib.items():
            name = k.split("}")[-1]
            if name not in ATTRS or "href" in name.lower() or name.lower().startswith("on"):
                add("error", "unsafe", f"The SVG has an attribute {name!r} on <{tag}>, which a drawing never uses.")
            elif re.search(r"url\(|javascript:|data:|expression\(", v, re.I):
                add("error", "unsafe", f"The SVG attribute {name!r} on <{tag}> refers to something outside the drawing.")
        for k in ("x", "y", "x1", "y1", "x2", "y2", "cx", "cy"):
            if k in el.attrib and tag != "rect":
                try:
                    val = float(el.attrib[k])
                except ValueError:
                    continue
                if not -0.5 <= val <= (w if k.startswith("x") or k == "cx" else h) + 0.5:
                    add("error", "outside", f"A <{tag}> is drawn at {k}={val:g}, outside the {w}x{h} canvas.")
    return found


def _angle(p, v, q):
    a, b = (p[0] - v[0], p[1] - v[1]), (q[0] - v[0], q[1] - v[1])
    na, nb = math.hypot(*a), math.hypot(*b)
    if na < 1e-9 or nb < 1e-9:
        return None
    c = max(-1.0, min(1.0, (a[0] * b[0] + a[1] * b[1]) / (na * nb)))
    return math.degrees(math.acos(c))
