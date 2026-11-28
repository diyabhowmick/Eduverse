"""Place a drawing's points so its measurements are true, then fit it to the canvas.

A triangle labelled 3-4-5 must measure 3-4-5: a student will put a ruler on it. So points the script leaves
unplaced are computed from its stated lengths and angles, in closed form, and only for cases that have one
answer:

  triangle   from three sides (SSS), from two sides and the angle between them (SAS, which covers a right
             triangle from its two legs). A triangle is a polygon of three points, or three segments with
             lengths that close one (see _loose_triangles); both go through the same _triangle().
  rectangle  from two adjacent sides; square from one side (polygon "shape": "rectangle" | "square")
  circle     a centre and radius, or three placed points it passes through
  points     given with x and y

Anything else is refused with the names of the points that could not be placed. There is no iterative
solver and no approximation.

Placement rules that pick between two mirror images: the first side of a shape runs along +x, and the rest of
the shape goes counter-clockwise in the order its points are listed. A shape not touching anything already
placed goes to the right of what is.

Then normalise: one uniform scale (px per unit) fits the drawing into the canvas, centred, with y flipped so
it increases downwards as SVG expects. "The drawing" includes the labels on its points and sides: their size
does not change with the scale, so a fit to the points alone could push a long label off the edge. Labels are
placed by layout_labels() below, which the compiler draws from and the gate measures, so all three agree. The
scale is returned, so the gate can turn pixels back into the script's units.
"""
import math

from . import draw_spec as S

PAD = 12             # px kept clear inside the canvas edge, round the shapes and their labels
EPS = 1e-9

# Label size, estimated: there is no font engine here. Used for fitting, drawing and checking alike.
FONT_SIZE = 14
CHAR_W = 0.6         # average Arial glyph width as a share of the font size (digits 0.56, capitals about 0.67)
LINE_H = 1.2         # text box height as a share of the font size
GAP = 8              # px between a label and the point or side it names
ANGLE_GAP = 31       # px from an angle's vertex to its label: past the arc draw_compile draws (22.4 px at most), plus GAP
ARM_GAP = 4          # px kept between an angle's label and the two lines that make the angle


def solve(spec):
    """Returns (solved, errors). solved is None when there are errors. Expects a spec that passed validate()."""
    world = {n: (float(p["x"]), float(p["y"])) for n, p in spec.get("points", {}).items() if "x" in p}
    lengths = {}
    for s in spec.get("segments", []):
        if "length" in s:
            lengths[frozenset((s["from"], s["to"]))] = S.quantity(s["length"])[0]
    angles = {}
    for a in spec.get("angles", []):
        p, v, q = a["points"]
        deg = 90.0 if a.get("right") else S.quantity(a["degrees"])[0] if "degrees" in a else None
        if deg is not None:
            angles[(v, frozenset((p, q)))] = deg

    def length(a, b):
        """A side's length: stated in the script, or measured between two points already placed."""
        k = frozenset((a, b))
        if k in lengths:
            return lengths[k]
        if a in world and b in world:
            return math.dist(world[a], world[b])
        return None

    errors = []
    shapes = [p for p in spec.get("polygons", []) if p.get("shape") in ("triangle", "rectangle", "square")
              or (p.get("shape") is None and len(p["points"]) == 3)]
    loose, why = _loose_triangles(spec, shapes)
    shapes = shapes + [{"points": names} for names in loose]     # after the polygons, so those place first
    done = set()
    progress = True
    while progress and not errors:
        progress = False
        for i, poly in enumerate(shapes):
            names = poly["points"]
            if i in done:
                continue
            if all(n in world for n in names):
                done.add(i)
                continue
            if len(names) == 3:
                placed = _triangle(names, length, angles, world, errors)
            else:
                placed = _rectangle(names, poly.get("shape"), lengths, world, errors)
            if placed:
                world.update(placed)
                done.add(i)
                progress = True

    circles = []
    for i, c in enumerate(spec.get("circles", [])):
        if errors:
            break
        if "centre" in c:
            if c["centre"] not in world and not world:
                world[c["centre"]] = (0.0, 0.0)       # a circle on its own: its centre is the origin
            if c["centre"] in world:
                circles.append((world[c["centre"]], S.quantity(c["r"])[0]))
        elif all(n in world for n in c["through"]):
            cc = _circumcircle(*(world[n] for n in c["through"]))
            if cc is None:
                errors.append(f"Circle {i + 1} cannot pass through {', '.join(c['through'])}: the three points are on one line.")
            else:
                circles.append(cc)

    if errors:
        return None, errors
    missing = [n for n in spec.get("points", {}) if n not in world]
    if missing:
        reasons = "".join(" " + r for r in why(set(missing)))
        return None, [f"Cannot place these points: {', '.join(missing)}.{reasons} A point is placed when it has x and "
                      "y, or belongs to a triangle with three sides, or two sides and the angle between them, stated; "
                      "three segments with lengths that close a triangle; a rectangle with two adjacent sides "
                      "stated; a square with one side stated; or is the centre of a circle drawn on its own."]
    return _normalise(spec, world, circles)


def _loose_triangles(spec, polygons):
    """Triangles written as three segments rather than a polygon: three segments joining three points, each
    point the end of exactly two, all three with a length. The corners are named in the order the segments are
    listed (a mirror image has the same measurements). Refused rather than guessed:
      - a side with no length;
      - a triangle sharing a side with one already found, or with a triangle polygon: which side of the shared
        side it lies on is not stated, and a folded drawing would pass every measurement;
      - any triangle at points where a side is listed twice.
    Returns (triangles, why): why(missing points) gives a sentence for each refusal that left points unplaced."""
    segs = spec.get("segments", [])
    pair = [frozenset((s["from"], s["to"])) for s in segs]
    first, twice = {}, set()                       # each side's first listing; sides listed more than once
    for i, k in enumerate(pair):
        if k in first:
            twice.add(k)
        else:
            first[k] = i
    at_twice = set().union(*twice) if twice else set()
    adj = {}
    for k in first:
        a, b = tuple(k)
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    cycles = {frozenset((*k, c)) for k in first for c in adj[tuple(k)[0]] & adj[tuple(k)[1]]}

    def sides(t):
        return sorted((first[frozenset(e)] for e in ((a, b) for a in t for b in t if a < b)))

    def name(i):
        return segs[i]["from"] + segs[i]["to"]

    taken = {frozenset(e) for p in polygons if len(p["points"]) == 3
             for e in zip(p["points"], p["points"][1:] + p["points"][:1])}
    polys = {frozenset(p["points"]) for p in polygons if len(p["points"]) == 3}
    found, refused = [], []
    for t in sorted(cycles, key=sides):
        idx = sides(t)
        if t in polys:
            continue
        if t & at_twice:
            continue                                                     # explained below, by the duplicate
        no_length = [name(i) for i in idx if "length" not in segs[i]]
        shared = [pair[i] for i in idx if pair[i] in taken]
        if no_length:
            refused.append((t, f"{_and([name(i) for i in idx])} close a triangle but {_and(no_length)} "
                               f"{'has' if len(no_length) == 1 else 'have'} no length."))
        elif shared:
            s = "".join(sorted(shared[0]))
            refused.append((t, f"{_and([name(i) for i in idx])} close a triangle that shares the side {s} with "
                               f"another triangle, so which side of {s} it lies on is not stated."))
        else:
            a, b = segs[idx[0]]["from"], segs[idx[0]]["to"]
            found.append([a, b, next(iter(t - {a, b}))])
            taken |= {pair[i] for i in idx}

    def why(missing):
        out = [r for t, r in refused if t & missing]
        for k in twice:
            if k & missing or any(adj.get(p, set()) & missing for p in k):
                a, b = sorted(k)
                out.append(f"The side {a}{b} is listed more than once, so no triangle is read from the segments at {a} and {b}.")
        in_cycle = {k for t in cycles for k in (frozenset(e) for e in ((a, b) for a in t for b in t if a < b))}
        loose = [i for k, i in first.items() if k not in in_cycle and k not in twice and k & missing]
        if loose:
            names = sorted({p for i in loose for p in pair[i]})
            out.append(f"{_and([name(i) for i in sorted(loose)])} "
                       f"join{'s' if len(loose) == 1 else ''} {_and(names)} without closing a triangle: a triangle "
                       "from loose segments is three segments joining three points.")
        return out

    return found, why


def _and(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _triangle(names, length, angles, world, errors):
    """Places the unplaced corners of one triangle. Returns {name: (x, y)}, or None if it cannot yet."""
    a_, b_, c_ = names
    side = {frozenset((a_, b_)): length(a_, b_), frozenset((b_, c_)): length(b_, c_), frozenset((c_, a_)): length(c_, a_)}
    if any(v is None for v in side.values()):
        # SAS: two sides and the angle at the corner they share gives the third (law of cosines)
        for v, (p, q) in ((a_, (b_, c_)), (b_, (c_, a_)), (c_, (a_, b_))):
            deg = angles.get((v, frozenset((p, q))))
            l1, l2 = side[frozenset((v, p))], side[frozenset((v, q))]
            if deg is not None and l1 is not None and l2 is not None:
                t = math.radians(deg)
                side[frozenset((p, q))] = math.sqrt(max(0.0, l1 * l1 + l2 * l2 - 2 * l1 * l2 * math.cos(t)))
                break
        else:
            return None
    ab, bc, ca = side[frozenset((a_, b_))], side[frozenset((b_, c_))], side[frozenset((c_, a_))]
    for s1, n1, s2, n2, s3, n3 in ((ab, a_ + b_, bc, b_ + c_, ca, c_ + a_), (bc, b_ + c_, ca, c_ + a_, ab, a_ + b_),
                                   (ca, c_ + a_, ab, a_ + b_, bc, b_ + c_)):
        if s1 >= (s2 + s3) * (1 - EPS):
            errors.append(f"Triangle {a_}{b_}{c_} cannot exist: side {n1} = {s1:g} is not shorter than "
                          f"{n2} + {n3} = {s2 + s3:g}.")
            return None

    have = [n for n in names if n in world]
    if len(have) == 2:
        # the third corner is where circles round the two placed ones meet, on the side that keeps the listed
        # order counter-clockwise
        z = [n for n in names if n not in world][0]
        p, q = have
        cands = _meet(world[p], side[frozenset((p, z))], world[q], side[frozenset((q, z))])
        if not cands:
            errors.append(f"Triangle {a_}{b_}{c_} cannot exist with {p} and {q} where they are.")
            return None
        ccw = [c for c in cands if _area(*({**world, z: c}[n] for n in names)) > 0]
        return {z: (ccw or cands)[0]}

    # none or one placed: build it with the first side along +x, then move it into place
    cx = (ca * ca + ab * ab - bc * bc) / (2 * ab)
    shape = {a_: (0.0, 0.0), b_: (ab, 0.0), c_: (cx, math.sqrt(max(0.0, ca * ca - cx * cx)))}
    return _move(shape, have, world)


def _rectangle(names, shape, lengths, world, errors):
    p0, p1, p2, p3 = names
    if any(n in world for n in names):
        return None          # partly placed rectangles are not solved; all four must then be given

    def stated(*pairs):
        vals = [lengths[frozenset(pr)] for pr in pairs if frozenset(pr) in lengths]
        if any(abs(v - vals[0]) > EPS * max(1.0, vals[0]) for v in vals):
            errors.append(f"The {shape} {''.join(names)} has sides that should be equal but are stated as "
                          f"{' and '.join(f'{v:g}' for v in vals)}.")
            return None
        return vals[0] if vals else None

    if shape == "square":
        w = h = stated((p0, p1), (p1, p2), (p2, p3), (p3, p0))
    else:
        w, h = stated((p0, p1), (p2, p3)), stated((p1, p2), (p3, p0))
    if errors or w is None or h is None:
        return None
    return _move({p0: (0.0, 0.0), p1: (w, 0.0), p2: (w, h), p3: (0.0, h)}, [], world)


def _move(shape, have, world):
    """Translate a shape built at the origin: onto its one placed corner, or beside everything already placed."""
    if have:
        ox, oy = shape[have[0]]
        tx, ty = world[have[0]][0] - ox, world[have[0]][1] - oy
    elif world:
        xs = [p[0] for p in world.values()]
        ys = [p[1] for p in world.values()]
        span = max(max(p[0] for p in shape.values()) - min(p[0] for p in shape.values()), 1e-6)
        tx, ty = max(xs) + span * 0.3 - min(p[0] for p in shape.values()), min(ys) - min(p[1] for p in shape.values())
    else:
        tx = ty = 0.0
    return {n: (x + tx, y + ty) for n, (x, y) in shape.items() if n not in world}


def _meet(p, r1, q, r2):
    d = math.dist(p, q)
    if d < EPS or d > r1 + r2 + EPS or d < abs(r1 - r2) - EPS:
        return []
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h = math.sqrt(max(0.0, r1 * r1 - a * a))
    mx, my = p[0] + a * (q[0] - p[0]) / d, p[1] + a * (q[1] - p[1]) / d
    ux, uy = -(q[1] - p[1]) / d, (q[0] - p[0]) / d
    return [(mx + h * ux, my + h * uy), (mx - h * ux, my - h * uy)]


def _area(a, b, c):
    return ((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) / 2


def _circumcircle(a, b, c):
    d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    scale = max(math.dist(a, b), math.dist(b, c), math.dist(c, a), 1e-12)
    if abs(d) < EPS * scale * scale:
        return None
    ux = ((a[0] ** 2 + a[1] ** 2) * (b[1] - c[1]) + (b[0] ** 2 + b[1] ** 2) * (c[1] - a[1]) + (c[0] ** 2 + c[1] ** 2) * (a[1] - b[1])) / d
    uy = ((a[0] ** 2 + a[1] ** 2) * (c[0] - b[0]) + (b[0] ** 2 + b[1] ** 2) * (a[0] - c[0]) + (c[0] ** 2 + c[1] ** 2) * (b[0] - a[0])) / d
    return (ux, uy), math.dist((ux, uy), a)


def label_size(text: str) -> tuple:
    return len(text) * FONT_SIZE * CHAR_W, FONT_SIZE * LINE_H


def _labels(spec, pts):
    """Each label's text, size, and where it sits relative to its anchor, given points in any y-down frame.
    The offset is in px and the same at every scale: it points away from the middle of the drawing (a point's
    label), across the side to its outside (a side's label), or into the angle along its bisector, clear of the
    vertex's own name outside (an angle's label). Uniform scaling keeps those directions."""
    cx0 = sum(p[0] for p in pts.values()) / len(pts)
    cy0 = sum(p[1] for p in pts.values()) / len(pts)
    wanted = [(s["label"], "segment", (s["from"], s["to"])) for s in spec.get("segments", []) if s.get("label")]
    for lb in spec.get("labels", []):
        if "point" in lb:
            wanted.append((lb["text"], "point", lb["point"]))
        elif "segment" in lb:
            wanted.append((lb["text"], "segment", tuple(lb["segment"])))
        elif "angle" in lb:
            wanted.append((lb["text"], "angle", tuple(lb["angle"])))
        else:
            wanted.append((lb["text"], "free", (lb["x"], lb["y"])))
    out = []
    for text, kind, at in wanted:
        text = " ".join(str(text).split())
        bw, bh = label_size(text)
        item = {"text": text, "w": bw, "h": bh, "kind": kind, "at": at, "off": (0.0, 0.0)}
        if kind != "free":
            if kind == "angle":
                item["off"] = _into_angle(*(pts[n] for n in at), bw, bh)
                out.append(item)
                continue
            if kind == "point":
                ax, ay = pts[at]
                dx, dy = ax - cx0, ay - cy0
            else:
                (x1, y1), (x2, y2) = pts[at[0]], pts[at[1]]
                ax, ay = (x1 + x2) / 2, (y1 + y2) / 2
                dx, dy = -(y2 - y1), x2 - x1
                if dx * (ax - cx0) + dy * (ay - cy0) < 0:
                    dx, dy = -dx, -dy
            n = math.hypot(dx, dy)
            dx, dy = (dx / n, dy / n) if n > 1e-9 else (0.0, -1.0)
            item["off"] = (dx * (GAP + bw / 2), dy * (GAP + bh / 2))
        out.append(item)
    return out


def _into_angle(p, v, q, bw, bh):
    """Offset from the vertex v to the centre of a bw x bh label inside the angle p-v-q, along its bisector: past
    the arc, and far enough that the box clears both arm lines by ARM_GAP. Closed form: for an arm at half-angle
    h from the bisector, the centre's distance from the arm grows as t*sin(h), and the box reaches toward the arm
    by its half-extent across it. The sharper the angle, the further out the label sits."""
    d1, d2 = math.hypot(p[0] - v[0], p[1] - v[1]) or 1.0, math.hypot(q[0] - v[0], q[1] - v[1]) or 1.0
    arms = [((p[0] - v[0]) / d1, (p[1] - v[1]) / d1), ((q[0] - v[0]) / d2, (q[1] - v[1]) / d2)]
    ux, uy = arms[0][0] + arms[1][0], arms[0][1] + arms[1][1]
    n = math.hypot(ux, uy)
    ux, uy = (ux / n, uy / n) if n > 1e-9 else (0.0, -1.0)
    t = ANGLE_GAP + bw / 2 * abs(ux) + bh / 2 * abs(uy)
    for ax, ay in arms:
        sin_h = abs(ax * uy - ay * ux)
        if sin_h > 1e-9:
            reach = bw / 2 * abs(ay) + bh / 2 * abs(ax)          # the box's half-extent across this arm
            t = max(t, (reach + ARM_GAP) / sin_h)
    return (ux * t, uy * t)


def _anchor(item, pts):
    if item["kind"] == "point":
        return pts[item["at"]]
    if item["kind"] == "angle":
        return pts[item["at"][1]]
    a, b = pts[item["at"][0]], pts[item["at"][1]]
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def layout_labels(spec, solved) -> list:
    """Where each label goes, as a box: {text, cx, cy, w, h, segment, angle}. segment is the pair of point names
    for a label on a side, angle the three for a label on an angle, else None. The fit, the compiler and the gate
    all use these same boxes."""
    pts, out = solved["points"], []
    for it in _labels(spec, pts):
        if it["kind"] == "free":
            cx, cy = it["at"][0] * solved["width"], it["at"][1] * solved["height"]
        else:
            ax, ay = _anchor(it, pts)
            cx, cy = ax + it["off"][0], ay + it["off"][1]
        out.append({"text": it["text"], "cx": cx, "cy": cy, "w": it["w"], "h": it["h"],
                    "segment": it["at"] if it["kind"] == "segment" else None,
                    "angle": it["at"] if it["kind"] == "angle" else None})
    return out


def _extent(spec, world, circles):
    """Everything the fit must keep on the canvas, per axis, as (c, lo, hi): at scale s it covers
    c * s + lo to c * s + hi px, before the shift that centres it. y is flipped here (c = -y)."""
    frame = {n: (x, -y) for n, (x, y) in world.items()}
    xs = [(p[0], 0.0, 0.0) for p in frame.values()]
    ys = [(p[1], 0.0, 0.0) for p in frame.values()]
    for (cx, cy), r in circles:
        xs += [(cx - r, 0.0, 0.0), (cx + r, 0.0, 0.0)]
        ys += [(-cy - r, 0.0, 0.0), (-cy + r, 0.0, 0.0)]
    for it in _labels(spec, frame):
        if it["kind"] == "free":
            continue     # placed on the canvas by the script, not with the drawing; the gate checks those
        (ax, ay), (ox, oy) = _anchor(it, frame), it["off"]
        xs.append((ax, ox - it["w"] / 2, ox + it["w"] / 2))
        ys.append((ay, oy - it["h"] / 2, oy + it["h"] / 2))
    return xs, ys


def _largest_scale(items, room):
    """The largest s for which max(c*s + hi) - min(c*s + lo) <= room, in closed form: every pair of items
    bounds s, from above when the first lies further along than the second, from below when it lies behind."""
    top, bottom = math.inf, 0.0
    for ci, _, hi in items:
        for cj, lo, _ in items:
            fixed, grow = hi - lo, ci - cj
            if grow > EPS:
                top = min(top, (room - fixed) / grow)
            elif grow < -EPS:
                bottom = max(bottom, (fixed - room) / -grow)
            elif fixed > room + 1e-9:
                return None
    return top if top >= bottom else None


def _normalise(spec, world, circles):
    w, h = S.size(spec)
    xs = [p[0] for p in world.values()] + [c[0][0] + k * c[1] for c in circles for k in (-1, 1)]
    ys = [p[1] for p in world.values()] + [c[0][1] + k * c[1] for c in circles for k in (-1, 1)]
    if max(xs) - min(xs) < EPS and max(ys) - min(ys) < EPS:
        return None, ["The drawing has no size: every point is in the same place."]
    room_w, room_h = w - 2 * PAD, h - 2 * PAD
    ex, ey = _extent(spec, world, circles)
    sx, sy = _largest_scale(ex, room_w), _largest_scale(ey, room_h)
    scale = None if sx is None or sy is None else min(sx, sy)
    if scale is None or scale <= EPS or math.isinf(scale):
        return None, [f"The drawing and its labels do not fit a {w}x{h} canvas. Shorten the labels or make the canvas larger."]

    def span(items):
        return min(c * scale + lo for c, lo, _ in items), max(c * scale + hi for c, _, hi in items)

    (x0, x1), (y0, y1) = span(ex), span(ey)
    ox = PAD + (room_w - (x1 - x0)) / 2 - x0
    oy = PAD + (room_h - (y1 - y0)) / 2 - y0

    def px(p):
        return (ox + p[0] * scale, oy - p[1] * scale)

    return {
        "width": w, "height": h, "scale": scale, "unit": S.length_unit(spec),
        "points": {n: px(p) for n, p in world.items()},
        "world": dict(world),
        "circles": [{"cx": px(c)[0], "cy": px(c)[1], "r": r * scale} for c, r in circles],
    }, []
