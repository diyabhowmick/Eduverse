"""Writes explanations ahead of students, for one book or exam pack, in its own process:
python -m app.prepare <job id>. Several requests run at once; one failing does not stop the rest.

Pass 1: a level 1 explanation for every highlighted word (or exam question).
Pass 2, textbooks only: the model picks the hard words inside each level 1 answer and writes one line tying
each back to it (one request per answer). Pass 3: each of those words is explained once for the whole book.
After this a student's taps are served from storage; the model is only asked for something nobody prepared."""
import re, sys
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from .db import SessionLocal
from .models import Book, Explanation, ExplainLink, PrepJob
from . import explain_store as X

WORKERS = 6


def _who(book) -> str:
    return f"a Class {book.grade} {book.subject} student ({book.board})"


def _budget_ok(db):
    left = X.budget_left(db)
    if left is not None and left <= 0:
        raise RuntimeError("Monthly AI budget used up")


def _run_pool(db, j, items, ask, save):
    """ask(item) runs in a worker and only talks to the model; save(item, result) writes, on this thread."""
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        jobs = {pool.submit(ask, it): it for it in items}
        for job in as_completed(jobs):
            it = jobs[job]
            try:
                _budget_ok(db)
                result, usage = job.result()
                save(it, result, usage)
                j.done += 1; j.tokens += usage.get("prompt", 0) + usage.get("completion", 0)
            except Exception as e:
                j.failed += 1; j.error = str(e)[:400]
            db.commit()


def _sentence_with(text: str, term: str) -> str:
    for s in re.split(r"(?<=[.!?])\s+", text):
        if term.lower() in s.lower():
            return s.strip()
    return text[:200]


def level1(db, j, book, ai, pv):
    from .routers.learn import prep_items
    items = prep_items(db, book, j.styles)
    j.total = len(items); db.commit()

    def ask(it):
        usage = {}
        return X.check(X.ask(ai, it["prompt"], usage=usage)), usage

    def save(it, text, usage):
        db.add(Explanation(scope=it["scope"], anchor=it["anchor"], level=1, style=it["style"], lang=book.medium or "English", book_id=book.id,
                           question_id=it["question_id"], term=it["term"][:200], text=text, model=pv["model"], source="prepared"))
        X.record(db, "prepare", pv["model"], usage, None, book.id, False, it["term"], it["where"])
    _run_pool(db, j, items, ask, save)


def mark_terms(db, j, book, ai, pv):
    pc = X.pconf(ai)
    n = max(1, min(int(pc.get("terms_per_explanation") or 4), 8))
    parents = db.query(Explanation).filter(Explanation.book_id == book.id, Explanation.scope == "book", Explanation.level == 1,
                                           Explanation.status.in_(X.LIVE), Explanation.marked.is_not(True), Explanation.style.in_(j.styles)).all()
    j.total += len(parents); db.commit()

    def ask(e):
        usage = {}
        return X.parse_json(X.ask(ai, X.mark_prompt(e, _who(book), n), json_mode=True, max_tokens=600, usage=usage)), usage

    def save(e, data, usage):
        own, seen = X.norm(e.term), set()
        for t in (data.get("terms") or [])[:n]:
            term = str((t or {}).get("term") or "").strip().strip(".,;:")
            key = X.norm(term)
            # Only words really in the text, so the reader can underline them, and never the word being explained.
            if not (2 <= len(term) <= 60) or key == own or key in seen or term.lower() not in e.text.lower():
                continue
            seen.add(key)
            db.add(ExplainLink(parent_id=e.id, book_id=book.id, term=term, key=key, bridge=str(t.get("bridge") or "").strip()[:300]))
        e.marked = True
        X.record(db, "prepare", pv["model"], usage, None, book.id, False, e.term, "level 2 words")
    _run_pool(db, j, parents, ask, save)


def level2(db, j, book, ai, pv):
    rows = db.query(ExplainLink, Explanation).join(Explanation, ExplainLink.parent_id == Explanation.id).filter(ExplainLink.book_id == book.id,
                                                                                                             Explanation.style.in_(j.styles)).all()
    groups: "OrderedDict[tuple, dict]" = OrderedDict()
    for link, parent in rows:
        g = groups.setdefault((link.key, parent.style), {"term": link.term, "style": parent.style, "uses": []})
        g["uses"].append(_sentence_with(parent.text, link.term))
    have = {(a, s) for a, s in db.query(Explanation.anchor, Explanation.style).filter(Explanation.book_id == book.id, Explanation.level == 2,
                                                                                    Explanation.status.in_(X.LIVE))}
    todo = [g | {"anchor": X.l2_anchor(book, g["term"])} for g in groups.values()]
    todo = [g for g in todo if (g["anchor"], g["style"]) not in have]
    j.total += len(todo); db.commit()

    def ask(g):
        usage = {}
        return X.check(X.ask(ai, X.core_prompt(book, g["term"], g["uses"], _who(book), g["style"], ai), usage=usage)), usage

    def save(g, text, usage):
        db.add(Explanation(scope="book", anchor=g["anchor"], level=2, style=g["style"], lang=book.medium or "English", book_id=book.id,
                           term=g["term"][:200], text=text, model=pv["model"], source="prepared"))
        X.record(db, "prepare", pv["model"], usage, None, book.id, False, g["term"], "level 2")
    _run_pool(db, j, todo, ask, save)


def run(job_id: int):
    db = SessionLocal()
    try:
        j = db.get(PrepJob, job_id)
        book = db.get(Book, j.book_id)
        ai = X.ai_conf(db)
        pv = ai["providers"].get(ai["provider"], {"model": "test"})
        j.status, j.total, j.done, j.failed = "running", 0, 0, 0; db.commit()
        level1(db, j, book, ai, pv)
        if book.track != "exam" and X.pconf(ai).get("level2"):
            mark_terms(db, j, book, ai, pv)
            level2(db, j, book, ai, pv)
        j.status = "failed" if j.total and j.failed == j.total else "done"
        j.finished_at = datetime.utcnow(); db.commit()
    except Exception as e:
        db.rollback(); j = db.get(PrepJob, job_id)
        j.status, j.error, j.finished_at = "failed", str(e)[:800], datetime.utcnow(); db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    run(int(sys.argv[1]))
