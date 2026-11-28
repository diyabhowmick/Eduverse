"""A model writes a drawing script for a term; the gate decides whether a student may see it.

    draw(db, term, ...) -> Result

The model is asked for a script in draw_spec's schema, or {"skip": "<why>"} when a drawing would not help. The
script is validated, solved, compiled and checked. If anything fails (unreadable JSON, a schema error, points
that cannot be placed, an error from the gate) the model gets its reply back with the findings and one chance
to fix it. Never more than one: MAX_ATTEMPTS is 2.

The gate's verdict is final. A drawing with an error finding is never final, whatever the model says about it,
and it is kept as status "rejected" with its findings, as evidence of what the model gets wrong. A skip is a
correct answer and creates no drawing. Every model call that answers is recorded as kind "drawing" for the cost
dashboard; a call that raised has no token count and is not. Nothing here commits: the caller does.

The model call is a parameter (ask), so tests can script the answers and count the calls. With the "mock"
provider no model is called: a canned, obviously labelled test triangle comes back instead.
"""
import json
import os
from dataclasses import dataclass, field

from . import draw_check as CK
from . import draw_compile as CP
from . import draw_solve as SV
from . import draw_spec as S
from . import explain_store as X
from .models import Drawing

KIND = "drawing"
MAX_ATTEMPTS = 2          # the first answer and exactly one retry
MAX_TOKENS = 2000

# The example in the prompt. A real script: the tests run it through the gate, so it cannot go stale.
EXAMPLE = {
    "points": {"P": {}, "Q": {}, "R": {}, "S": {}},
    "polygons": [{"points": ["P", "Q", "R", "S"], "shape": "rectangle"}],
    "segments": [
        {"from": "P", "to": "Q", "length": {"value": 6, "unit": "cm"}, "label": "6 cm"},
        {"from": "Q", "to": "R", "length": {"value": 4, "unit": "cm"}, "label": "4 cm"},
    ],
    "angles": [{"points": ["S", "P", "Q"], "right": True}],
    "labels": [{"text": "P", "point": "P"}, {"text": "Q", "point": "Q"}, {"text": "R", "point": "R"},
               {"text": "S", "point": "S"}],
}

# What the mock provider answers: plainly a test, never mistaken for a model's work.
CANNED = {
    "points": {"A": {}, "B": {}, "C": {}},
    "segments": [
        {"from": "A", "to": "B", "length": 4, "label": "4"},
        {"from": "B", "to": "C", "length": 3, "label": "3"},
        {"from": "C", "to": "A", "length": 5, "label": "5"},
    ],
    "angles": [{"points": ["A", "B", "C"], "right": True}],
    "labels": [{"text": "TEST DRAWING (mock model)", "x": 0.5, "y": 0.06}],
}


@dataclass
class Result:
    verdict: str                       # final | rejected | skipped | crashed | budget
    term: str
    attempts: int = 0                  # model answers judged
    model: str = ""
    script: str = ""                   # the last reply, as the model wrote it
    svg: str = ""
    findings: list = field(default_factory=list)
    first_findings: list = field(default_factory=list)   # what the first attempt failed on, when it did
    skip_reason: str = ""
    skipped_after_failure: bool = False
    error: str = ""
    drawing: Drawing | None = None


def provider(ai: dict) -> tuple:
    """(provider, model), resolved the way explain_store.ask() resolves them."""
    name = os.getenv("AI_PROVIDER_OVERRIDE") or ai["provider"]
    return name, ai["providers"].get(name, {"model": "test"})["model"]


def mock_ask(ai, prompt, *, json_mode=False, usage=None, max_tokens=MAX_TOKENS) -> str:
    text = json.dumps(CANNED)
    if usage is not None:
        usage.update(prompt=len(prompt) // 4, completion=len(text) // 4)
    return text


def _keys(keys) -> str:
    return ", ".join(f'"{k}"' for k in sorted(keys))


def prompt(term: str, *, subject="", grade="", paragraph="", definition="") -> str:
    who = " ".join(x for x in (f"Class {grade}" if grade else "", subject) if x) or "school"
    return f"""You draw precise geometry diagrams for a {who} textbook used in Tamil Nadu, India.
A student tapped the term "{term}".
{f'The paragraph it appeared in: """{paragraph[:1200]}"""' if paragraph else ''}
{f'The book defines it as: """{definition[:600]}"""' if definition else ''}

First decide whether a geometric drawing would genuinely help a student understand "{term}". Most terms have
none: processes, ideas, events, living things, places, grammar, history. For those answer exactly
{{"skip": "<one line saying why>"}}
Declining is a correct answer. Inventing a diagram for a term that has no geometric shape is the worst answer.

If a drawing helps, answer with one JSON object, a drawing script, and nothing else. The schema is closed: a key
not listed here is rejected.
Top level: {_keys(S.TOP_KEYS)}. Leave out "width" and "height" unless the default 400 x 300 canvas is wrong.
"kind", if given, must be "geometry".
"points": an object of named points; each is {{}} (placed for you) or has both of {_keys(S.POINT_KEYS)}. Names
start with a letter. Coordinates use maths axes: y goes up.
"segments": a list; each has {_keys(S.SEGMENT_KEYS)}; "from" and "to" are point names, "length" and "label" optional.
"polygons": a list; each has {_keys(S.POLYGON_KEYS)}; "shape" is optional, one of {_keys(S.SHAPES)}.
"circles": a list; each has "centre" and "r", or "through" with three point names. Keys: {_keys(S.CIRCLE_KEYS)}.
"angles": a list; each has {_keys(S.ANGLE_KEYS)}; "points" is three names with the vertex in the middle;
"degrees" (less than 180) and "right" are optional.
"labels": a list; each has "text" and exactly one place: "point", "segment" (two names), "angle" (three names,
matching an entry in "angles"), or "x" and "y" as fractions of the canvas. Keys: {_keys(S.LABEL_KEYS)}.
A length or an angle is a number, or an object with keys {_keys(S.QUANTITY_KEYS)}, like {{"value": 6, "unit": "cm"}}.

A point without x and y must be placed by one of these, or the drawing is refused:
- a triangle: a polygon of three points, or three segments joining three points, with all three lengths
  stated, or two lengths and the angle between them;
- a rectangle or square: a polygon with "shape" "rectangle" (two adjacent side lengths) or "square" (one side);
- a circle: "centre" with "r" (the centre is placed if nothing else is), or "through" three placed points.
Otherwise give the point x and y.

What cannot be expressed, so do not try:
- a point lying on a segment: no altitudes, medians or angle bisectors as constraints;
- function graphs, number lines or coordinate plots;
- more than one unit: every length in the drawing uses the same unit.

Every label on a side ("5 cm") and on an angle ("60°") is measured against the drawing, and one that disagrees
gets the drawing rejected. Leave a label out rather than guess it.

Example, a 6 cm by 4 cm rectangle:
{json.dumps(EXAMPLE)}"""


def retry_prompt(first: str, reply: str, errors: list) -> str:
    found = "\n".join(f"- {f['message']}" for f in errors)
    return f"""{first}

Your previous answer was:
{reply[:4000]}

It was checked and failed:
{found}

Answer again with the whole corrected script, fixing every problem listed. If the term cannot be drawn
honestly within these rules, answer {{"skip": "<one line saying why>"}} instead."""


def _error(code, message) -> dict:
    return {"severity": "error", "code": code, "message": message}


def judge(text: str):
    """A model reply to ("skip", reason, None, None, []) or ("script", spec, solved, svg, findings)."""
    try:
        data = X.parse_json(text)
    except ValueError:
        data = None
    if not isinstance(data, dict) or not data:
        return "script", None, None, "", [_error("parse", "The reply is not a JSON object.")]
    if set(data) == {"skip"} and isinstance(data["skip"], str):
        return "skip", data["skip"].strip()[:300], None, "", []
    errs = S.validate(data)
    if errs:
        return "script", data, None, "", [_error("invalid", e) for e in errs]
    solved, errs = SV.solve(data)
    if errs:
        return "script", data, None, "", [_error("unsolvable", e) for e in errs]
    svg = CP.compile_svg(data, solved)
    return "script", data, solved, svg, CK.check(data, solved, svg)


def draw(db, term: str, *, subject="", grade="", paragraph="", definition="", book_id=None, explanation_id=None,
         ai=None, ask=None) -> Result:
    ai = ai or X.ai_conf(db)
    name, model = provider(ai)
    ask = ask or (mock_ask if name == "mock" else X.ask)
    first = prompt(term, subject=subject, grade=grade, paragraph=paragraph, definition=definition)
    res = Result(verdict="rejected", term=term, model=model)
    p, last = first, None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        left = X.budget_left(db)
        if left is not None and left <= 0:
            res.verdict, res.error = "budget", "This month's AI budget is used up."
            break
        usage = {}
        try:
            text = ask(ai, p, json_mode=True, usage=usage, max_tokens=MAX_TOKENS)
        except Exception as e:                       # the provider did not answer: no tokens to record
            res.verdict, res.error = "crashed", f"The model did not answer: {str(e)[:300]}"
            break
        usage.setdefault("prompt", len(p) // 4)
        usage.setdefault("completion", len(text or "") // 4)
        X.record(db, KIND, model, usage, None, book_id, False, term, "drawing")
        res.attempts, res.script = attempt, text or ""

        kind, spec, solved, svg, findings = judge(text)
        if kind == "skip":
            res.verdict, res.skip_reason, res.skipped_after_failure = "skipped", spec, attempt > 1
            return res
        res.svg, res.findings = svg, findings
        errors = [f for f in findings if f["severity"] == "error"]
        if not errors:
            res.verdict = "final"
            res.drawing = _store(db, res, spec, solved, "final", explanation_id)
            return res
        last = (spec, solved)
        if attempt == 1:
            res.first_findings = findings
            p = retry_prompt(first, text or "", errors)

    if last is not None:                             # keep the failed script as evidence
        res.drawing = _store(db, res, last[0], last[1], "rejected", explanation_id)
    return res


def _store(db, res: Result, spec, solved, status, explanation_id) -> Drawing:
    w, h = (solved["width"], solved["height"]) if solved else (0, 0)      # a script that never solved has no canvas
    row = Drawing(explanation_id=explanation_id, term=res.term[:200], kind="geometry",
                  script=json.dumps(spec) if isinstance(spec, dict) else res.script, svg=res.svg or "",
                  width=w, height=h, status=status, checks=res.findings, model=res.model, source="generated")
    db.add(row)
    return row
