"""What a drawing script is, and whether one is valid.

A drawing is written as JSON. The schema is closed: a key it does not describe is an error, not ignored, so a
script cannot ask for anything this module has not agreed to draw. Pure Python, no I/O.

    {
      "kind": "geometry",                       optional, the only kind there is
      "width": 400, "height": 300,              optional, the canvas in px
      "points":   {"A": {"x": 0, "y": 0}, "B": {}, ...}
                    x and y together, or neither (the solver places it). Maths axes: y goes up.
      "segments": [{"from": "A", "to": "B", "length": 3, "label": "3 cm"}]
      "polygons": [{"points": ["A", "B", "C"], "closed": true, "shape": "triangle"}]
                    shape is optional: triangle | rectangle | square
      "circles":  [{"centre": "O", "r": 2}]  or  [{"through": ["A", "B", "C"]}]
      "angles":   [{"points": ["A", "B", "C"], "degrees": 60, "right": false}]   B is the vertex
      "labels":   [{"text": "A", "point": "A"}, {"text": "3 cm", "segment": ["A", "B"]},
                   {"text": "Not to scale", "x": 0.5, "y": 0.05}]   x and y are fractions of the canvas
    }

A length or an angle is a number, or {"value": number, "unit": "cm"}. Every length in one drawing shares one
unit. Angles are in degrees.
"""
import json
import math
import re

KINDS = ("geometry",)
SHAPES = {"triangle": 3, "rectangle": 4, "square": 4}
ANGLE_UNITS = ("", "°", "deg", "degree", "degrees")
DEFAULT_W, DEFAULT_H = 400, 300
MIN_SIDE, MAX_SIDE = 120, 2000
MAX_ITEMS = 200            # points, segments, polygons, circles, angles and labels together
MAX_TEXT = 60
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_']{0,15}$")

TOP_KEYS = {"kind", "width", "height", "points", "segments", "polygons", "circles", "angles", "labels"}
POINT_KEYS = {"x", "y"}
SEGMENT_KEYS = {"from", "to", "length", "label"}
POLYGON_KEYS = {"points", "closed", "shape"}
CIRCLE_KEYS = {"centre", "r", "through"}
ANGLE_KEYS = {"points", "degrees", "right"}
LABEL_KEYS = {"text", "point", "segment", "x", "y"}
QUANTITY_KEYS = {"value", "unit"}


def load(text: str):
    """JSON text to a spec. Returns (spec, errors); spec is None when there are errors."""
    try:
        spec = json.loads(text)
    except (TypeError, ValueError) as e:
        return None, [f"The drawing script is not valid JSON ({getattr(e, 'msg', 'unreadable')})."]
    errors = validate(spec)
    return (None, errors) if errors else (spec, [])


def is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def quantity(q):
    """(value, unit) of a length or angle: a number, or {"value": ..., "unit": ...}. Call after validate()."""
    if isinstance(q, dict):
        return float(q["value"]), str(q.get("unit") or "").strip()
    return float(q), ""


def size(spec) -> tuple:
    return int(spec.get("width", DEFAULT_W)), int(spec.get("height", DEFAULT_H))


def length_unit(spec) -> str:
    """The one unit the drawing's lengths are in, or "" when none is given."""
    for q in _lengths(spec):
        u = quantity(q)[1]
        if u:
            return u
    return ""


def validate(spec) -> list:
    """Every problem with the script, as plain sentences. An empty list means it can be drawn."""
    if not isinstance(spec, dict):
        return ["The drawing script must be a JSON object."]
    errs = []
    _unknown(spec, TOP_KEYS, "the drawing", errs)

    if "kind" in spec and spec["kind"] not in KINDS:
        errs.append(f"The kind {spec['kind']!r} is not supported. The only kind is geometry.")
    for k in ("width", "height"):
        if k in spec and not (is_number(spec[k]) and MIN_SIDE <= spec[k] <= MAX_SIDE):
            errs.append(f"The {k} must be a number from {MIN_SIDE} to {MAX_SIDE}.")

    for k in ("segments", "polygons", "circles", "angles", "labels"):
        if k in spec and not isinstance(spec[k], list):
            errs.append(f"{k.capitalize()} must be a list.")
    if "points" in spec and not isinstance(spec["points"], dict):
        errs.append("Points must be an object of named points.")
    if errs:
        return errs

    points = spec.get("points", {})
    total = len(points) + sum(len(spec.get(k, [])) for k in ("segments", "polygons", "circles", "angles", "labels"))
    if total > MAX_ITEMS:
        return [f"The drawing has {total} parts; the most allowed is {MAX_ITEMS}."]

    for name, p in points.items():
        where = f"point {name}"
        if not NAME.match(name):
            errs.append(f"The point name {name!r} is not allowed. Use a letter followed by up to 15 letters, digits, ' or _.")
        if not isinstance(p, dict):
            errs.append(f"The {where} must be an object, empty or with x and y.")
            continue
        _unknown(p, POINT_KEYS, f"the {where}", errs)
        if ("x" in p) != ("y" in p):
            errs.append(f"The {where} needs both x and y, or neither.")
        elif "x" in p and not (is_number(p["x"]) and is_number(p["y"])):
            errs.append(f"The {where} has an x or y that is not a number.")

    def ref(name, where):
        if not isinstance(name, str) or name not in points:
            errs.append(f"{where} refers to a point {name!r} that is not in points.")
            return False
        return True

    def refs(names, n, where):
        """A list of n distinct point names (n=None: at least 3)."""
        if not isinstance(names, list) or (n is not None and len(names) != n) or (n is None and len(names) < 3):
            errs.append(f"{where} needs {'exactly ' + str(n) if n else 'at least 3'} point names in a list.")
            return False
        ok = all([ref(x, where) for x in names])
        if ok and len(set(names)) != len(names):
            errs.append(f"{where} names the same point twice.")
            return False
        return ok

    for i, s in enumerate(spec.get("segments", [])):
        where = f"Segment {i + 1}"
        if not _obj(s, where, errs):
            continue
        _unknown(s, SEGMENT_KEYS, where.lower(), errs)
        if "from" not in s or "to" not in s:
            errs.append(f"{where} needs from and to.")
        elif ref(s["from"], where) and ref(s["to"], where) and s["from"] == s["to"]:
            errs.append(f"{where} starts and ends at the same point.")
        if "length" in s:
            _quantity(s["length"], f"The length of {where.lower()}", errs, positive=True)
        if "label" in s:
            _text(s["label"], f"The label of {where.lower()}", errs)

    for i, p in enumerate(spec.get("polygons", [])):
        where = f"Polygon {i + 1}"
        if not _obj(p, where, errs):
            continue
        _unknown(p, POLYGON_KEYS, where.lower(), errs)
        shape = p.get("shape")
        if shape is not None and shape not in SHAPES:
            errs.append(f"{where} has shape {shape!r}; the shapes are triangle, rectangle and square.")
            shape = None
        refs(p.get("points"), SHAPES.get(shape), where)
        if "closed" in p and not isinstance(p["closed"], bool):
            errs.append(f"{where}: closed must be true or false.")

    for i, c in enumerate(spec.get("circles", [])):
        where = f"Circle {i + 1}"
        if not _obj(c, where, errs):
            continue
        _unknown(c, CIRCLE_KEYS, where.lower(), errs)
        if "through" in c and ("centre" in c or "r" in c):
            errs.append(f"{where} has both a centre and points it passes through; give one or the other.")
        elif "through" in c:
            refs(c["through"], 3, where)
        elif "centre" in c and "r" in c:
            ref(c["centre"], where)
            _quantity(c["r"], f"The radius of {where.lower()}", errs, positive=True)
        else:
            errs.append(f"{where} needs a centre and r, or three points it passes through.")

    for i, a in enumerate(spec.get("angles", [])):
        where = f"Angle {i + 1}"
        if not _obj(a, where, errs):
            continue
        _unknown(a, ANGLE_KEYS, where.lower(), errs)
        refs(a.get("points"), 3, where)
        if "right" in a and not isinstance(a["right"], bool):
            errs.append(f"{where}: right must be true or false.")
        if "degrees" in a and _quantity(a["degrees"], f"The size of {where.lower()}", errs, positive=True):
            v, u = quantity(a["degrees"])
            if u.lower() not in ANGLE_UNITS:
                errs.append(f"The size of {where.lower()} is in {u!r}; angles are in degrees.")
            elif not v < 180:
                errs.append(f"The size of {where.lower()} must be less than 180 degrees.")
            elif a.get("right") is True and abs(v - 90) > 1e-9:
                errs.append(f"{where} is marked as a right angle but its size is {v:g} degrees.")

    for i, lb in enumerate(spec.get("labels", [])):
        where = f"Label {i + 1}"
        if not _obj(lb, where, errs):
            continue
        _unknown(lb, LABEL_KEYS, where.lower(), errs)
        if "text" not in lb:
            errs.append(f"{where} has no text.")
        else:
            _text(lb["text"], f"The text of {where.lower()}", errs)
        anchors = [k for k in ("point", "segment") if k in lb] + (["position"] if "x" in lb or "y" in lb else [])
        if len(anchors) != 1:
            errs.append(f"{where} needs exactly one place: a point, a segment, or x and y.")
        elif "point" in lb:
            ref(lb["point"], where)
        elif "segment" in lb:
            refs(lb["segment"], 2, where)
        elif not all(is_number(lb.get(k)) and 0 <= lb[k] <= 1 for k in ("x", "y")):
            errs.append(f"{where} needs x and y as fractions of the canvas, from 0 to 1.")

    if not any(spec.get(k) for k in ("segments", "polygons", "circles")):
        errs.append("The drawing has nothing to draw: it needs at least one segment, polygon or circle.")

    if not errs:
        units = {quantity(q)[1] for q in _lengths(spec)} - {""}
        if len(units) > 1:
            errs.append(f"The lengths are in more than one unit ({', '.join(sorted(units))}); use one unit for the whole drawing.")
    return errs


def _lengths(spec):
    for s in spec.get("segments", []):
        if "length" in s:
            yield s["length"]
    for c in spec.get("circles", []):
        if "r" in c:
            yield c["r"]


def _obj(v, where, errs) -> bool:
    if not isinstance(v, dict):
        errs.append(f"{where} must be an object.")
        return False
    return True


def _unknown(obj, allowed, where, errs):
    for k in obj:
        if k not in allowed:
            errs.append(f"Unknown key {k!r} in {where}. Allowed: {', '.join(sorted(allowed))}.")


def _text(v, where, errs):
    if not isinstance(v, str) or not v.strip():
        errs.append(f"{where} must be some text.")
    elif len(v) > MAX_TEXT:
        errs.append(f"{where} is longer than {MAX_TEXT} characters.")


def _quantity(q, where, errs, positive=False) -> bool:
    if isinstance(q, dict):
        bad = [k for k in q if k not in QUANTITY_KEYS]
        if bad:
            errs.append(f"Unknown key {bad[0]!r} in {where.lower()}. Allowed: unit, value.")
            return False
        if "unit" in q and not isinstance(q["unit"], str):
            errs.append(f"{where} has a unit that is not text.")
            return False
        q = q.get("value")
    if not is_number(q):
        errs.append(f"{where} must be a number, or an object with a number value and an optional unit.")
        return False
    if positive and q <= 0:
        errs.append(f"{where} must be more than zero.")
        return False
    return True
