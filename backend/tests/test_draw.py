"""Drawings: script, solver, compiler and gate, with hand-written scripts and no model anywhere.

Run either way, from the repository root or from backend/:
    python backend/tests/test_draw.py
    python -m pytest backend/tests/test_draw.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # backend/, so "app" imports

from app import draw_check, draw_compile, draw_solve, draw_spec  # noqa: E402


def build(spec):
    """validate -> solve -> compile -> check, failing loudly at the first stage that refuses."""
    errs = draw_spec.validate(spec)
    assert errs == [], errs
    solved, errs = draw_solve.solve(spec)
    assert errs == [], errs
    svg = draw_compile.compile_svg(spec, solved)
    return solved, svg, draw_check.check(spec, solved, svg)


def errors(findings, code=None):
    return [f for f in findings if f["severity"] == "error" and (code is None or f["code"] == code)]


def units_apart(solved, a, b):
    return math.dist(solved["points"][a], solved["points"][b]) / solved["scale"]


def angle_at(solved, p, v, q):
    return draw_check._angle(solved["points"][p], solved["points"][v], solved["points"][q])


TRIANGLE_345 = {
    "kind": "geometry", "width": 400, "height": 300,
    "points": {"A": {}, "B": {}, "C": {}},
    "polygons": [{"points": ["A", "B", "C"], "closed": True}],
    "segments": [
        {"from": "A", "to": "B", "length": {"value": 4, "unit": "cm"}, "label": "4 cm"},
        {"from": "B", "to": "C", "length": {"value": 3, "unit": "cm"}, "label": "3 cm"},
        {"from": "C", "to": "A", "length": {"value": 5, "unit": "cm"}, "label": "5 cm"},
    ],
    "angles": [{"points": ["A", "B", "C"], "right": True}],
    "labels": [{"text": "A", "point": "A"}, {"text": "B", "point": "B"}, {"text": "C", "point": "C"}],
}


def test_345_right_triangle_measures_345():
    solved, svg, found = build(TRIANGLE_345)
    assert abs(units_apart(solved, "A", "B") - 4) < 1e-9
    assert abs(units_apart(solved, "B", "C") - 3) < 1e-9
    assert abs(units_apart(solved, "C", "A") - 5) < 1e-9
    assert abs(angle_at(solved, "A", "B", "C") - 90) < 1e-9
    assert errors(found) == [], found


def test_345_from_two_legs_and_the_right_angle():
    # SAS: the hypotenuse is not stated; the solver must find it is 5
    spec = {**TRIANGLE_345, "segments": [
        {"from": "A", "to": "B", "length": 4}, {"from": "B", "to": "C", "length": 3}], "labels": []}
    solved, svg, found = build(spec)
    assert abs(units_apart(solved, "C", "A") - 5) < 1e-9
    assert errors(found) == [], found


def test_equilateral_has_three_60_degree_angles():
    spec = {"points": {"P": {}, "Q": {}, "R": {}},
            "polygons": [{"points": ["P", "Q", "R"]}],
            "segments": [{"from": "P", "to": "Q", "length": 6}, {"from": "Q", "to": "R", "length": 6},
                         {"from": "R", "to": "P", "length": 6}]}
    solved, svg, found = build(spec)
    for p, v, q in (("R", "P", "Q"), ("P", "Q", "R"), ("Q", "R", "P")):
        assert abs(angle_at(solved, p, v, q) - 60) < 1e-9
    assert errors(found) == [], found


def test_impossible_triangle_1_2_10_is_refused():
    spec = {"points": {"A": {}, "B": {}, "C": {}},
            "polygons": [{"points": ["A", "B", "C"]}],
            "segments": [{"from": "A", "to": "B", "length": 1}, {"from": "B", "to": "C", "length": 2},
                         {"from": "C", "to": "A", "length": 10}]}
    assert draw_spec.validate(spec) == []
    solved, errs = draw_solve.solve(spec)
    assert solved is None
    assert len(errs) == 1 and "cannot exist" in errs[0] and "10" in errs[0], errs


def test_label_says_5_but_side_measures_6_is_an_error():
    # The points are given, so nothing can quietly fix the drawing: AB really is 6 long and its label says 5.
    spec = {"points": {"A": {"x": 0, "y": 0}, "B": {"x": 6, "y": 0}, "C": {"x": 0, "y": 8}},
            "polygons": [{"points": ["A", "B", "C"]}],
            "segments": [{"from": "A", "to": "B", "label": "5"}, {"from": "B", "to": "C", "label": "10"},
                         {"from": "C", "to": "A", "label": "8"}]}
    solved, svg, found = build(spec)
    assert abs(units_apart(solved, "A", "B") - 6) < 1e-9          # the geometry is what we think it is
    bad = errors(found)
    # exactly one error, it is the label check, it names AB, and it says both 5 and 6
    assert len(bad) == 1, found
    assert bad[0]["code"] == "label_length", bad
    assert "AB" in bad[0]["message"] and "'5'" in bad[0]["message"] and "6" in bad[0]["message"], bad
    # the control: the same drawing labelled truthfully passes, so the error above came from the 5
    spec["segments"][0]["label"] = "6"
    assert errors(build(spec)[2]) == []


def test_stated_length_5_but_side_measures_6_is_an_error():
    spec = {"points": {"A": {"x": 0, "y": 0}, "B": {"x": 6, "y": 0}, "C": {"x": 0, "y": 8}},
            "polygons": [{"points": ["A", "B", "C"]}],
            "segments": [{"from": "A", "to": "B", "length": 5}]}
    bad = errors(build(spec)[2])
    assert [f["code"] for f in bad] == ["length"], bad
    assert "AB" in bad[0]["message"] and "5" in bad[0]["message"] and "6" in bad[0]["message"]


def test_label_in_another_unit_is_converted_before_comparing():
    # the drawing is in cm (from the stated length); AB measures 5 cm
    spec = {"points": {"A": {"x": 0, "y": 0}, "B": {"x": 5, "y": 0}, "C": {"x": 0, "y": 4}},
            "polygons": [{"points": ["A", "B", "C"]}],
            "segments": [{"from": "A", "to": "B", "length": {"value": 5, "unit": "cm"}, "label": "60 mm"}]}
    bad = errors(build(spec)[2])
    assert [f["code"] for f in bad] == ["label_length"], bad
    assert "'60 mm'" in bad[0]["message"] and "50 mm" in bad[0]["message"], bad
    spec["segments"][0]["label"] = "50 mm"
    assert errors(build(spec)[2]) == []


def test_rounded_label_must_also_be_within_5_percent():
    # "1" rounds to anything from 0.5 to 1.5, but a side of 1.4 labelled "1" is 40% off
    spec = {"points": {"A": {"x": 0, "y": 0}, "B": {"x": 1.4, "y": 0}, "C": {"x": 0, "y": 1}},
            "polygons": [{"points": ["A", "B", "C"]}],
            "segments": [{"from": "A", "to": "B", "label": "1"}]}
    assert [f["code"] for f in errors(build(spec)[2])] == ["label_length"]
    # agreed to pass: the hypotenuse of a 5-5 right triangle, 7.07, labelled "7" (1% off)
    spec = {"points": {"A": {"x": 0, "y": 0}, "B": {"x": 5, "y": 0}, "C": {"x": 0, "y": 5}},
            "polygons": [{"points": ["A", "B", "C"]}],
            "segments": [{"from": "B", "to": "C", "label": "7"}]}
    assert errors(build(spec)[2]) == []


def test_rounded_label_in_inches_must_also_be_within_5_percent():
    # a side of 3.9 cm is 1.54 in: "2 in" is inside the rounding band but 30% off
    spec = {"points": {"A": {"x": 0, "y": 0}, "B": {"x": 3.9, "y": 0}, "C": {"x": 0, "y": 3}},
            "polygons": [{"points": ["A", "B", "C"]}],
            "segments": [{"from": "C", "to": "A", "length": {"value": 3, "unit": "cm"}},
                         {"from": "A", "to": "B", "label": "2 in"}]}
    assert [f["code"] for f in errors(build(spec)[2])] == ["label_length"]
    # agreed to pass: a side of 5 cm (1.97 in) labelled "2 in" (1.6% off)
    spec["points"]["B"] = {"x": 5, "y": 0}
    assert errors(build(spec)[2]) == []


def test_long_label_on_an_outer_side_stays_on_the_canvas():
    # BC is the right-hand side of the 3-4-5, so its label sits to the right of everything else. The fit must
    # make room for it, not just for the points.
    segments = [dict(s) for s in TRIANGLE_345["segments"]]
    segments[1]["label"] = "the shorter leg, opposite A"
    solved, svg, found = build({**TRIANGLE_345, "segments": segments})
    assert [f for f in found if f["code"] == "outside"] == [], found
    assert errors(found) == [], found
    for b in draw_solve.layout_labels(TRIANGLE_345 | {"segments": segments}, solved):
        assert b["cx"] - b["w"] / 2 >= 0 and b["cx"] + b["w"] / 2 <= solved["width"], b
    assert abs(units_apart(solved, "B", "C") - 3) < 1e-9          # making room did not distort the triangle


def test_labels_that_are_not_a_plain_quantity_are_ignored():
    # "about 5 cm" on a 6 cm side is prose, not a measurement: no finding at all
    spec = {"points": {"A": {"x": 0, "y": 0}, "B": {"x": 6, "y": 0}, "C": {"x": 0, "y": 8}},
            "polygons": [{"points": ["A", "B", "C"]}],
            "segments": [{"from": "A", "to": "B", "label": "about 5 cm"}],
            "labels": [{"text": "Figure 5", "x": 0.8, "y": 0.1}]}
    assert [f for f in build(spec)[2] if f["code"] == "label_length"] == []


def test_labels_on_top_of_each_other_are_reported():
    spec = {"points": {"A": {"x": 0, "y": 0}, "B": {"x": 4, "y": 0}},
            "segments": [{"from": "A", "to": "B"}],
            "labels": [{"text": "first", "x": 0.5, "y": 0.2}, {"text": "second", "x": 0.5, "y": 0.2}]}
    found = build(spec)[2]
    overlaps = [f for f in found if f["code"] == "overlap"]
    assert len(overlaps) == 1 and overlaps[0]["severity"] == "error", found


def test_unknown_key_is_rejected():
    spec = {**TRIANGLE_345, "colour": "red"}
    errs = draw_spec.validate(spec)
    assert any("'colour'" in e for e in errs), errs
    nested = {**TRIANGLE_345, "segments": [{"from": "A", "to": "B", "style": "dashed"}]}
    assert any("'style'" in e for e in draw_spec.validate(nested))


def test_reference_to_missing_point_and_empty_drawing_are_rejected():
    assert any("'Z'" in e for e in draw_spec.validate({"points": {"A": {}}, "segments": [{"from": "A", "to": "Z"}]}))
    assert any("nothing to draw" in e for e in draw_spec.validate({"points": {"A": {"x": 0, "y": 0}}}))


def test_script_tag_in_a_label_is_escaped_and_the_gate_is_happy():
    spec = {**TRIANGLE_345, "labels": [{"text": "<script>alert(1)</script>", "x": 0.5, "y": 0.06}]}
    solved, svg, found = build(spec)
    assert "<script" not in svg.lower()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in svg
    assert errors(found) == [], found


def test_unsafe_svg_is_caught():
    solved, svg, _ = build(TRIANGLE_345)
    for bad in ('<script>alert(1)</script>', '<image href="http://x/y.png"/>', '<a href="javascript:alert(1)"><text>x</text></a>'):
        tampered = svg.replace("</svg>", bad + "</svg>")
        assert any(f["code"] == "unsafe" for f in errors(draw_check.check(TRIANGLE_345, solved, tampered))), bad


def test_rectangle_square_and_circle():
    rect = {"points": {"P": {}, "Q": {}, "R": {}, "S": {}},
            "polygons": [{"points": ["P", "Q", "R", "S"], "shape": "rectangle"}],
            "segments": [{"from": "P", "to": "Q", "length": 8}, {"from": "Q", "to": "R", "length": 3}]}
    solved, _, found = build(rect)
    assert abs(units_apart(solved, "R", "S") - 8) < 1e-9 and abs(units_apart(solved, "P", "R") - math.hypot(8, 3)) < 1e-9
    assert errors(found) == []
    square = {"points": {"P": {}, "Q": {}, "R": {}, "S": {}},
              "polygons": [{"points": ["P", "Q", "R", "S"], "shape": "square"}],
              "segments": [{"from": "Q", "to": "R", "length": 2}]}
    solved, _, _ = build(square)
    assert abs(units_apart(solved, "P", "Q") - 2) < 1e-9
    circle = {"points": {"O": {}}, "circles": [{"centre": "O", "r": {"value": 3, "unit": "cm"}}]}
    solved, _, found = build(circle)
    assert abs(solved["circles"][0]["r"] / solved["scale"] - 3) < 1e-9 and errors(found) == []


def test_underdetermined_points_are_refused_not_guessed():
    spec = {"points": {"A": {}, "B": {}, "C": {}, "D": {}},
            "polygons": [{"points": ["A", "B", "C", "D"]}],
            "segments": [{"from": "A", "to": "B", "length": 3}]}
    solved, errs = draw_solve.solve(spec)
    assert solved is None and errs[0].startswith("Cannot place these points: A, B, C, D"), errs


# ---- triangles from three loose segments

def loose(*sides, points="ABC"):
    """Segments only, no polygon. sides: (from, to, length or None)."""
    return {"points": {p: {} for p in points},
            "segments": [{"from": a, "to": b, **({"length": n} if n is not None else {})} for a, b, n in sides]}


def test_loose_segments_3_4_5_make_a_triangle():
    solved, svg, found = build(loose(("A", "B", 3), ("B", "C", 4), ("C", "A", 5)))
    assert abs(units_apart(solved, "A", "B") - 3) < 1e-9
    assert abs(units_apart(solved, "B", "C") - 4) < 1e-9
    assert abs(units_apart(solved, "C", "A") - 5) < 1e-9
    assert errors(found) == [], found


def test_loose_segments_in_another_order_give_the_same_measurements():
    solved, svg, found = build(loose(("C", "A", 5), ("B", "C", 4), ("A", "B", 3)))
    for (a, b), n in ((("A", "B"), 3), (("B", "C"), 4), (("C", "A"), 5)):
        assert abs(units_apart(solved, a, b) - n) < 1e-9
    assert errors(found) == [], found


def test_loose_segments_1_2_10_meet_the_same_triangle_inequality_as_a_polygon():
    spec = loose(("A", "B", 1), ("B", "C", 2), ("C", "A", 10))
    solved, errs = draw_solve.solve(spec)
    assert solved is None and len(errs) == 1, errs
    assert errs[0] == "Triangle ABC cannot exist: side CA = 10 is not shorter than AB + BC = 3.", errs
    # the same sentence, word for word, as the polygon route: one check, reached from both
    as_polygon = {**spec, "polygons": [{"points": ["A", "B", "C"]}]}
    assert draw_solve.solve(as_polygon)[1] == errs


def test_loose_segments_with_a_side_missing_its_length_are_refused():
    solved, errs = draw_solve.solve(loose(("A", "B", 3), ("B", "C", 4), ("C", "A", None)))
    assert solved is None and errs[0].startswith("Cannot place these points: A, B, C."), errs
    assert "AB, BC and CA close a triangle but CA has no length." in errs[0], errs


def test_open_path_of_three_segments_is_not_a_triangle():
    solved, errs = draw_solve.solve(loose(("A", "B", 3), ("B", "C", 4), ("C", "D", 5), points="ABCD"))
    assert solved is None and errs[0].startswith("Cannot place these points: A, B, C, D."), errs
    assert "AB, BC and CD join A, B, C and D without closing a triangle" in errs[0], errs


def test_duplicated_side_and_shared_side_are_refused():
    solved, errs = draw_solve.solve(loose(("A", "B", 3), ("A", "B", 3), ("A", "C", 4)))
    assert solved is None and "The side AB is listed more than once" in errs[0], errs
    # ABC is a triangle; ACD shares AC with it, and which side of AC D falls on is not stated
    spec = loose(("A", "B", 3), ("B", "C", 4), ("C", "A", 5), ("C", "D", 4), ("D", "A", 3), points="ABCD")
    solved, errs = draw_solve.solve(spec)
    assert solved is None and errs[0].startswith("Cannot place these points: D."), errs
    assert "shares the side AC with another triangle" in errs[0], errs


def test_triangle_polygon_is_unchanged():
    # segments listed in an order that, read as loose segments, would start from C: the polygon still decides
    spec = {"points": {"A": {}, "B": {}, "C": {}},
            "polygons": [{"points": ["A", "B", "C"], "shape": "triangle"}],
            "segments": [{"from": "C", "to": "A", "length": 5}, {"from": "B", "to": "C", "length": 3},
                         {"from": "A", "to": "B", "length": 4}]}
    solved, svg, found = build(spec)
    w = solved["world"]
    assert w["A"] == (0.0, 0.0) and w["B"] == (4.0, 0.0), w
    assert abs(w["C"][0] - 4) < 1e-9 and abs(w["C"][1] - 3) < 1e-9, w
    assert errors(found) == [], found


# ---- angle labels checked against the measured angle

def test_right_angle_labelled_90_passes():
    spec = {**TRIANGLE_345, "labels": TRIANGLE_345["labels"] + [{"text": "90°", "angle": ["A", "B", "C"]}]}
    assert errors(build(spec)[2]) == []


def test_equilateral_angles_labelled_60_pass():
    spec = loose(("P", "Q", 6), ("Q", "R", 6), ("R", "P", 6), points="PQR")
    spec["angles"] = [{"points": ["R", "P", "Q"]}, {"points": ["P", "Q", "R"]}, {"points": ["Q", "R", "P"]}]
    spec["labels"] = [{"text": "60", "angle": a["points"]} for a in spec["angles"]]
    found = build(spec)[2]
    assert errors(found) == [], found


def test_right_angle_labelled_60_is_an_error():
    spec = {**TRIANGLE_345, "labels": [{"text": "60°", "angle": ["A", "B", "C"]}]}
    bad = errors(build(spec)[2])
    assert len(bad) == 1, bad
    assert bad[0]["code"] == "label_angle", bad
    assert bad[0]["message"] == "Angle ABC is labelled '60°' but the drawing makes it 90.0°.", bad


def test_angle_labels_that_are_not_a_plain_size_in_degrees_are_ignored():
    for text in ("roughly 60", "angle A", "60 cm"):
        spec = {**TRIANGLE_345, "labels": [{"text": text, "angle": ["A", "B", "C"]}]}
        assert build(spec)[2] == [], text


def test_label_on_an_angle_that_does_not_exist_is_rejected():
    spec = {**TRIANGLE_345, "labels": [{"text": "60°", "angle": ["B", "A", "C"]}]}
    errs = draw_spec.validate(spec)
    assert errs == ["Label 1 is on the angle BAC, which is not in angles."], errs


if __name__ == "__main__":
    failed = 0
    for name, fn in [(k, v) for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)]:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as e:                      # noqa: BLE001  report every failure, then exit non-zero
            failed += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{'all passed' if not failed else f'{failed} failed'}")
    sys.exit(1 if failed else 0)
