"""How well does a model write drawing scripts, and what do the failures look like?

Runs each term in drawing_terms.txt through draw_ai.draw() (model, then the gate) and reports the outcome:
passed first try, passed after retry, rejected, skipped first try, skipped after a failed attempt, crashed. It
then compares that with what each term was expected to do (hit rate, false enthusiasm) and groups the
rejections by the kind of finding that caused them.

    python backend/tools/eval_drawings.py --mock               free and instant: tests the plumbing only
    python backend/tools/eval_drawings.py --limit 10           the configured provider; asks before spending
    python backend/tools/eval_drawings.py --limit 30 --yes     no question asked

Every SVG, every script the model wrote and the summary go to backend/data/drawing_eval/<time>/, which git
already ignores. A real run uses DATABASE_URL, where the provider settings live: it needs the server's
SETTINGS_KEY or JWT_SECRET to read the API key, and it writes Drawing rows and "drawing" usage rows there, so
point it at staging, not production. --mock uses a throwaway in-memory database instead.
"""
import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

LABELS = {  # outcome -> (file name tag, summary line), in summary order
    "passed": ("passed", "passed first try"),
    "retried": ("passed-after-retry", "passed after retry"),
    "rejected": ("rejected", "rejected"),
    "skipped": ("skipped", "skipped first try"),
    "gave_up": ("skipped-after-failure", "skipped after a failed attempt"),
    "crashed": ("crashed", "crashed"),
    "budget": ("budget", "stopped: AI budget used up"),
}


def read_terms(path: Path) -> list:
    terms = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4 or parts[0] not in ("draw", "skip"):
            sys.exit(f"{path.name} line {n}: expected 'draw|skip | subject | grade | term | definition', got {line!r}")
        terms.append({"expect": parts[0], "subject": parts[1], "grade": parts[2], "term": parts[3],
                      "definition": parts[4] if len(parts) > 4 else ""})
    return terms


def outcome(r) -> str:
    if r.verdict == "final":
        return "passed" if r.attempts == 1 else "retried"
    if r.verdict == "skipped":
        return "gave_up" if r.skipped_after_failure else "skipped"
    return r.verdict                                  # rejected | crashed | budget


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "term"


def open_db(mock: bool):
    from app.models import Base
    if mock:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        return sessionmaker(bind=engine)(), {"provider": "mock", "providers": {}}
    from app import explain_store as X
    from app.db import SessionLocal, engine
    from app.main import _schema_lock, add_missing_columns
    _schema_lock(lambda: (Base.metadata.create_all(engine), add_missing_columns()))   # the drawings table, Drawing.term
    db = SessionLocal()
    return db, X.ai_conf(db)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--mock", action="store_true", help="no model, no cost: the canned test triangle for every term")
    ap.add_argument("--limit", type=int, default=5, help="how many terms, from the top of the file (default 5)")
    ap.add_argument("--terms", type=Path, default=Path(__file__).with_name("drawing_terms.txt"))
    ap.add_argument("--out", type=Path, default=None, help="default backend/data/drawing_eval/<time>/")
    ap.add_argument("--yes", action="store_true", help="do not ask before calling a real provider")
    args = ap.parse_args()

    terms = read_terms(args.terms)[: max(0, args.limit)]
    from app import draw_ai, explain_store as X
    from app.models import AiUsage
    db, ai = open_db(args.mock)
    name, model = draw_ai.provider(ai)
    mock = name == "mock"

    print(f"{len(terms)} terms with {name} / {model}: up to {len(terms) * draw_ai.MAX_ATTEMPTS} model calls.")
    if not mock:
        problem = X.provider_problem(ai)
        if problem:
            sys.exit(problem)
        left = X.budget_left(db)
        print(f"Monthly token budget left: {'no limit' if left is None else f'{left:,}'}.")
        if not args.yes and input("Call the model and spend money? [y/N] ").strip().lower() not in ("y", "yes"):
            sys.exit("Stopped; nothing was called.")

    out = args.out or BACKEND / "data" / "drawing_eval" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    # naive UTC, as models.now() writes AiUsage.at: an aware time would not compare cleanly with that column
    started = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = []
    for i, t in enumerate(terms, 1):
        t0 = time.time()
        try:
            r = draw_ai.draw(db, t["term"], subject=t["subject"], grade=t["grade"], definition=t["definition"], ai=ai)
            db.commit()
        except Exception as e:                         # a fault on our side, not the model's: report it and go on
            db.rollback()
            r = draw_ai.Result(verdict="crashed", term=t["term"], model=model, error=f"{type(e).__name__}: {e}")
        kind = outcome(r)
        stem = f"{i:02d}_{slug(t['term'])}_{LABELS[kind][0]}"
        files = []
        if r.svg:
            (out / f"{stem}.svg").write_text(r.svg + "\n", encoding="utf-8")
            files.append(f"{stem}.svg")
        if r.script:
            (out / f"{stem}.reply.txt").write_text(r.script + "\n", encoding="utf-8")
            files.append(f"{stem}.reply.txt")
        errors = [f for f in r.findings if f["severity"] == "error"]
        first_errors = [f for f in r.first_findings if f["severity"] == "error"]
        rows.append({**t, "outcome": kind, "attempts": r.attempts, "seconds": round(time.time() - t0, 1),
                     "skip_reason": r.skip_reason, "error": r.error, "files": files,
                     "errors": errors, "first_errors": first_errors})
        note = r.skip_reason or r.error or (errors[0]["message"] if errors else "")
        print(f"[{i:2d}/{len(terms)}] {t['term'][:34]:34s} {LABELS[kind][1]:30s} {note[:90]}")
        if kind == "budget":
            print("The monthly AI budget is used up; stopping.")
            break

    calls = db.query(AiUsage).filter(AiUsage.kind == draw_ai.KIND, AiUsage.at >= started).all()
    summary = report(rows, name, model, mock, len(calls), sum(u.prompt_tokens + u.completion_tokens for u in calls))
    (out / "summary.txt").write_text(summary, encoding="utf-8")
    (out / "results.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n" + summary)
    print(f"Written to {out}")


def report(rows, name, model, mock, calls, tokens) -> str:
    n = len(rows)
    count = Counter(r["outcome"] for r in rows)
    should = {e: [r for r in rows if r["expect"] == e] for e in ("draw", "skip")}
    pct = lambda a, b: f"{100 * a / b:.0f}%" if b else "n/a"          # noqa: E731
    lines = [f"Drawing eval, {datetime.now():%Y-%m-%d %H:%M}, {name} / {model}, {n} terms "
             f"({len(should['draw'])} expected to draw, {len(should['skip'])} expected to skip)"]
    if mock:
        lines.append("MOCK MODEL: the same canned triangle for every term. These numbers test the plumbing, not a model.")
    lines += ["", "Outcome"]
    lines += [f"  {LABELS[k][1]:32s} {count.get(k, 0):3d}" for k in LABELS if count.get(k) or k != "budget"]

    drawn = lambda rs: sum(r["outcome"] in ("passed", "retried") for r in rs)                       # noqa: E731
    tried = lambda rs: sum(r["outcome"] in ("passed", "retried", "rejected") for r in rs)         # noqa: E731
    honest = lambda rs: sum(r["outcome"] in ("skipped", "gave_up") for r in rs)                    # noqa: E731
    d, s = should["draw"], should["skip"]
    lines += ["", "Against expectation",
              f"  should draw ({len(d)}): a correct drawing for {drawn(d)}, hit rate {pct(drawn(d), len(d))}; "
              f"declined {honest(d)}, rejected {sum(r['outcome'] == 'rejected' for r in d)}",
              f"  should skip ({len(s)}): declined {honest(s)}; tried to draw {tried(s)}, false enthusiasm "
              f"{pct(tried(s), len(s))} (of those, {drawn(s)} passed the gate anyway)",
              f"  declined first try {count.get('skipped', 0)}, after a failed attempt {count.get('gave_up', 0)}"]

    def codes(key, which):
        c, example = Counter(), {}
        for r in rows:
            if r["outcome"] in which:
                for code in dict.fromkeys(f["code"] for f in r[key]):      # once per drawing
                    c[code] += 1
                    example.setdefault(code, next(f["message"] for f in r[key] if f["code"] == code))
        return [f"  {code:14s} {k:3d}   e.g. {example[code][:110]}" for code, k in c.most_common()] or ["  (none)"]

    lines += ["", "Why drawings were rejected (each rejected drawing counted once per kind of error)"]
    lines += codes("errors", ("rejected",))
    lines += ["", "What the one retry fixed (first-attempt errors in drawings that then passed)"]
    lines += codes("first_errors", ("retried",))
    lines += ["", f"Model calls {calls}, tokens {tokens:,}", "", "Each term"]
    lines += [f"  {i:2d} {r['expect']:4s} {r['term'][:34]:34s} {LABELS[r['outcome']][1]:30s} "
              f"{r['attempts']} answer{'s' if r['attempts'] != 1 else ''}" for i, r in enumerate(rows, 1)]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
