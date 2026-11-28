"""draw_ai: a model writes the script, the gate judges it. No real model and no cost: the mock provider or a
scripted stand-in that counts its calls. A throwaway in-memory database holds the rows.

Run either way, from the repository root or from backend/:
    python backend/tests/test_draw_ai.py
    python -m pytest backend/tests/test_draw_ai.py
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # backend/, so "app" imports

from sqlalchemy import create_engine                       # noqa: E402
from sqlalchemy.orm import sessionmaker                    # noqa: E402
from sqlalchemy.pool import StaticPool                     # noqa: E402

from app import draw_ai, draw_check, draw_compile, draw_solve, draw_spec  # noqa: E402
from app.models import AiUsage, Base, Drawing               # noqa: E402

MOCK = {"provider": "mock", "providers": {}}
STUB = {"provider": "stub", "providers": {"stub": {"model": "stub-model"}}}


def fresh_db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class Model:
    """Answers from a script, in order, and counts the calls. A call beyond the script fails the test."""
    def __init__(self, *answers):
        self.answers, self.prompts = list(answers), []

    def __call__(self, ai, prompt, *, json_mode=False, usage=None, max_tokens=0):
        assert json_mode, "drawings must ask for JSON"
        self.prompts.append(prompt)
        assert self.answers, f"the model was called {len(self.prompts)} times; the script allows {len(self.prompts) - 1}"
        usage.update(prompt=100, completion=50)
        return self.answers.pop(0)

    @property
    def calls(self):
        return len(self.prompts)


def lying(label="5 cm"):
    """A 3-4-5 written as loose segments, with AB (really 3) labelled as something else."""
    return json.dumps({"points": {"A": {}, "B": {}, "C": {}},
                       "segments": [{"from": "A", "to": "B", "length": 3, "label": label},
                                    {"from": "B", "to": "C", "length": 4}, {"from": "C", "to": "A", "length": 5}]})


def usage_rows(db):
    return db.query(AiUsage).all()


def test_mock_script_goes_end_to_end_to_a_final_drawing():
    db = fresh_db()
    r = draw_ai.draw(db, "right-angled triangle", subject="Maths", grade="8", ai=MOCK)
    assert r.verdict == "final" and r.attempts == 1, (r.verdict, r.findings)
    row = db.query(Drawing).one()
    assert (row.status, row.source, row.model, row.term) == ("final", "generated", "test", "right-angled triangle")
    assert row.svg.startswith("<svg") and "TEST DRAWING (mock model)" in row.svg
    assert [u.kind for u in usage_rows(db)] == ["drawing"]


def test_skip_is_a_skip_not_a_failure_and_makes_no_drawing():
    db, model = fresh_db(), Model('{"skip": "Photosynthesis is a process, not a shape."}')
    r = draw_ai.draw(db, "photosynthesis", ai=STUB, ask=model)
    assert r.verdict == "skipped" and r.skip_reason == "Photosynthesis is a process, not a shape."
    assert not r.skipped_after_failure and model.calls == 1
    assert db.query(Drawing).count() == 0


def test_malformed_json_fails_cleanly_with_a_sentence():
    db, model = fresh_db(), Model("Sure! Here is a drawing of a triangle.", "{not json at all")
    r = draw_ai.draw(db, "triangle", ai=STUB, ask=model)        # no exception reaches us
    assert r.verdict == "rejected" and model.calls == 2
    assert r.findings == [{"severity": "error", "code": "parse", "message": "The reply is not a JSON object."}]
    row = db.query(Drawing).one()
    assert row.status == "rejected" and row.script == "{not json at all" and row.checks == r.findings


def test_lying_label_twice_is_rejected_after_exactly_one_retry_and_kept():
    db, model = fresh_db(), Model(lying("5 cm"), lying("6 cm"))
    r = draw_ai.draw(db, "right-angled triangle", ai=STUB, ask=model)
    assert model.calls == 2, model.calls                     # one retry, not two
    assert r.verdict == "rejected" and r.attempts == 2
    assert [f["code"] for f in r.first_findings if f["severity"] == "error"] == ["label_length"]
    row = db.query(Drawing).one()
    assert row.status == "rejected" and row.source == "generated" and row.model == "stub-model"
    assert [c["code"] for c in row.checks if c["severity"] == "error"] == ["label_length"]
    assert "'6 cm'" in row.checks[0]["message"]              # the second answer is the one kept
    # the retry carried the first reply and what was wrong with it
    assert "Your previous answer was" in model.prompts[1] and "'5 cm'" in model.prompts[1]


def test_failure_then_a_good_retry_is_final_after_two_calls():
    db, model = fresh_db(), Model(lying("5 cm"), lying("3 cm"))
    r = draw_ai.draw(db, "right-angled triangle", ai=STUB, ask=model)
    assert model.calls == 2 and r.verdict == "final" and r.attempts == 2
    assert db.query(Drawing).one().status == "final"


def test_every_call_is_recorded_as_drawing_retries_included():
    db = fresh_db()
    draw_ai.draw(db, "t1", ai=STUB, ask=Model(lying("5 cm"), lying("6 cm")))     # 2 calls
    draw_ai.draw(db, "t2", ai=STUB, ask=Model(lying("5 cm"), lying("3 cm")))     # 2 calls
    draw_ai.draw(db, "t3", ai=STUB, ask=Model('{"skip": "not a shape"}'))        # 1 call
    rows = usage_rows(db)
    assert [(u.kind, u.term, u.model, u.prompt_tokens, u.completion_tokens) for u in rows] == \
        [("drawing", t, "stub-model", 100, 50) for t in ("t1", "t1", "t2", "t2", "t3")]


def test_skip_after_a_failed_attempt_is_counted_apart():
    db, model = fresh_db(), Model(lying("5 cm"), '{"skip": "cannot label it honestly"}')
    r = draw_ai.draw(db, "triangle", ai=STUB, ask=model)
    assert r.verdict == "skipped" and r.skipped_after_failure and model.calls == 2
    assert db.query(Drawing).count() == 0


def test_a_provider_that_raises_is_crashed_not_recorded():
    def down(*a, **k):
        raise TimeoutError("timed out")
    db = fresh_db()
    r = draw_ai.draw(db, "triangle", ai=STUB, ask=down)
    assert r.verdict == "crashed" and "timed out" in r.error
    assert usage_rows(db) == [] and db.query(Drawing).count() == 0


def test_no_budget_means_no_call():
    from app.models import Setting
    db = fresh_db()
    db.add(Setting(key="ai", value={**STUB, "monthly_token_budget": 10}))
    db.add(AiUsage(kind="explain", prompt_tokens=10, completion_tokens=5))
    db.flush()
    model = Model()
    r = draw_ai.draw(db, "triangle", ai=STUB, ask=model)
    assert r.verdict == "budget" and model.calls == 0


# ---- the prompt cannot drift from the schema

SCHEMA_KEYS = (draw_spec.TOP_KEYS | draw_spec.POINT_KEYS | draw_spec.SEGMENT_KEYS | draw_spec.POLYGON_KEYS
               | draw_spec.CIRCLE_KEYS | draw_spec.ANGLE_KEYS | draw_spec.LABEL_KEYS | draw_spec.QUANTITY_KEYS)


def test_prompt_and_schema_agree_both_ways():
    text = draw_ai.prompt("area of a rectangle", subject="Maths", grade="7", paragraph="p", definition="d")
    missing = sorted(k for k in SCHEMA_KEYS if f'"{k}"' not in text)
    assert missing == [], f"the schema accepts these but the prompt never mentions them: {missing}"
    used = set(re.findall(r'"(\w+)"\s*:', text))
    # point names inside "points" ("P": {}) are the script's own names, not schema keys
    unknown = sorted(used - SCHEMA_KEYS - {"skip"} - set(draw_ai.EXAMPLE["points"]))
    assert unknown == [], f"the prompt uses these as keys but the schema rejects them: {unknown}"


def test_prompt_example_and_mock_script_pass_the_gate():
    for spec in (draw_ai.EXAMPLE, draw_ai.CANNED):
        assert draw_spec.validate(spec) == []
        solved, errs = draw_solve.solve(spec)
        assert errs == []
        svg = draw_compile.compile_svg(spec, solved)
        assert [f for f in draw_check.check(spec, solved, svg) if f["severity"] == "error"] == []


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
