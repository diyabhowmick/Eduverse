"""Explanations for students, served from saved copies, plus the reviewer and cost controls around them.
How saving and choosing work is described in explain_store.py."""
import os, subprocess, sys, threading
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from ..config import BASE
from ..db import get_db, SessionLocal
from ..models import AiUsage, Book, Explanation, ExplanationVote, PrepJob, Question, QuestionPaper
from ..security import current_user, require
from ..audit import log
from .. import explain_store as X

router = APIRouter(prefix="/api/learn", tags=["learn"])
staff = require("super_admin", "reviewer")
sa = require("super_admin")
STAFF = ("super_admin", "reviewer")


class ExplainIn(BaseModel):
    scope: str = "book"                 # book | question
    book_id: int | None = None
    chapter: int | None = None
    keyword_id: str | None = None       # a highlighted word in the book
    block_id: str | None = None         # the passage, for words the student selected themselves
    question_id: int | None = None
    term: str = ""
    paragraph: str = ""
    definition: str = ""
    figures: list[str] = []
    style: str = "concept_clarity"
    parent_id: int | None = None        # set when the student goes one level deeper
    doubt: str = ""                     # a question typed by the student; always answered live
    different_from: int | None = None   # "Explain differently"


def _book_for(db, me, bid) -> Book:
    if me.role in STAFF:
        b = db.get(Book, bid)
        if not b:
            raise HTTPException(404, "Book not found")
        return b
    from .student import readable_book
    return readable_book(db, me, bid)


def _question_for(db, me, qid) -> tuple[Book, Question]:
    q = db.get(Question, qid)
    paper = db.get(QuestionPaper, q.paper_id) if q else None
    if not paper:
        raise HTTPException(404, "Question not found")
    if me.role in STAFF:
        return db.get(Book, paper.book_id), q
    from .exams import owned_pack
    pack = owned_pack(db, me, paper.book_id)
    if paper.status != "approved":
        raise HTTPException(404, "Question not found")
    return pack, q


def _root(db, e: Explanation) -> Explanation:
    while e.parent_id:
        e = db.get(Explanation, e.parent_id)
    return e


class Credits:
    """A student spends one credit each time the model is actually asked. Saved answers are free."""
    def __init__(self, db, me):
        self.db, self.me, self.limit = db, me, None
        if me.role == "student":
            from .student import rules_for
            self.limit = rules_for(db, me)["daily_limit"]

    def used(self):
        from .student import day_row
        return day_row(self.db, self.me.id).explanations if self.limit is not None else 0

    def check(self):
        if self.limit is not None and self.used() >= self.limit:
            raise HTTPException(429, f"You have used today's {self.limit} AI credits. Saved explanations are still free, and credits reset tomorrow.")

    def spend(self, book_id, text):
        if self.limit is not None:
            from .student import count_explanation
            count_explanation(self.db, self.me, None, tokens=len(text) // 4)

    def left(self):
        return None if self.limit is None else max(0, self.limit - self.used())


def _out(db, e: Explanation | None, me, credits: Credits, *, text=None, level=None, cached=False, live=False, term=""):
    mine = db.query(ExplanationVote).filter(ExplanationVote.explanation_id == e.id, ExplanationVote.user_id == me.id).order_by(ExplanationVote.id.desc()).first() if e else None
    return {"id": e.id if e else None, "text": e.text if e else text, "level": e.level if e else level, "style": e.style if e else "",
            "term": e.term if e else term, "cached": cached, "live": live, "final": bool(e and e.status == "final"),
            "vote": mine.value if mine and mine.value != "report" else "", "credits_left": credits.left(), "free_deeper": (e.level if e else level) < 2}


@router.post("/explain")
def explain(body: ExplainIn, db: Session = Depends(get_db), me=Depends(current_user)):
    ai = X.ai_conf(db)
    credits = Credits(db, me)
    style = body.style if body.style in (ai.get("depth_rules") or {}) else "concept_clarity"
    if me.role == "student":
        from .student import rules_for
        allowed = rules_for(db, me)["allowed_depths"]
        style = style if style in allowed else allowed[0]
    parent = root = None
    if body.parent_id:
        parent = db.get(Explanation, body.parent_id)
        if not parent:
            raise HTTPException(404, "Explanation not found")
        root = _root(db, parent)
        scope, style = parent.scope, parent.style
        if scope == "book":
            book = _book_for(db, me, parent.book_id)
        else:
            book, _q = _question_for(db, me, root.question_id)
    else:
        scope = body.scope
        if scope == "question":
            if not body.question_id:
                raise HTTPException(422, "Which question?")
            book, q = _question_for(db, me, body.question_id)
        elif scope == "book":
            if not body.book_id or not (body.keyword_id or (body.block_id and body.term.strip())):
                raise HTTPException(422, "Which word, and where in the book?")
            book = _book_for(db, me, body.book_id)
        else:
            raise HTTPException(422, "scope must be book or question")
    who = (f"a Class {book.grade} {book.subject} student ({book.board})" if scope == "book" else f"a student preparing for {book.exam or 'an exam'}")
    level = parent.level + 1 if parent else 1

    # A typed question, or anything past level 2, is answered for this student alone and not saved.
    if body.doubt.strip() or level >= 3:
        if not parent:
            raise HTTPException(422, "Ask about an explanation you have open")
        credits.check()
        prompt = X.doubt_prompt(root, parent, body.doubt.strip(), who) if body.doubt.strip() else X.deeper_prompt(root, parent, body.term.strip()[:120], who)
        text, _m = X.generate(db, prompt, kind="explain_deep", user_id=me.id, book_id=book.id, term=body.doubt.strip()[:200] or body.term, where=root.term)
        credits.spend(book.id, text)
        db.commit()
        return _out(db, None, me, credits, text=text, level=level, live=True, term=body.term or body.doubt)

    # Where this explanation lives.
    if parent:
        phrase = X.norm(body.term)
        if len(phrase) < 2:
            raise HTTPException(422, "Select the words you want explained")
        anchor, term, where = f"x:{parent.id}:{phrase}", body.term.strip()[:200], root.term
    elif scope == "question":
        anchor, term, where = f"q:{q.id}", f"Question {q.number}", f"{book.title}, question {q.number}"
    else:
        place = f"kw:{body.keyword_id}" if body.keyword_id else f"blk:{body.block_id}:{X.norm(body.term)}"
        anchor, term, where = f"book:{book.id}:{book.content_key}:ch{body.chapter}:{place}", body.term.strip()[:200], f"{book.title}, unit {body.chapter}"
    pool = db.query(Explanation).filter(Explanation.anchor == anchor, Explanation.style == style, Explanation.level == level,
                                        Explanation.status.in_(X.LIVE)).order_by(Explanation.id).all()

    def fresh():
        credits.check()
        if parent:
            prompt = X.deeper_prompt(root, parent, term, who)
        elif scope == "question":
            prompt = X.question_prompt(book, q, style, ai)
        else:
            chapter_title = next((c.get("title", "") for c in _chapters(book) if c.get("number") == body.chapter), "")
            prompt = X.book_prompt(book, chapter_title, term, body.paragraph[:1500], body.definition[:800], body.figures[:3], style, ai)
        text, model = X.generate(db, prompt, kind="explain", user_id=me.id, book_id=book.id, term=term, where=where)
        credits.spend(book.id, text)
        e = Explanation(scope=scope, anchor=anchor, level=level, style=style, lang=book.medium or "English", parent_id=parent.id if parent else None,
                        book_id=book.id, question_id=(q.id if scope == "question" and not parent else None), term=term, text=text, model=model)
        db.add(e); db.flush(); pool.append(e)
        return e

    cached = True
    if body.different_from:
        current = next((e for e in pool if e.id == body.different_from), None)
        if current:
            current.retries += 1
        others = [e for e in pool if e.id != body.different_from]
        if len(pool) < X.MAX_CANDIDATES:
            e, cached = fresh(), False
        else:
            e = X.choose(others) if others else (current or X.choose(pool))
    elif pool:
        e = X.choose(pool)
    else:
        e, cached = fresh(), False
    e.shown += 1
    if cached:
        X.record(db, "explain", e.model, None, me.id, book.id, True, term, where)
    X.maybe_finalise(db, pool)
    db.commit()
    return _out(db, e, me, credits, cached=cached)


def _chapters(book: Book) -> list:
    from .. import content as C
    try:
        return C.load(book).get("chapters", [])
    except Exception:
        return []


class VoteIn(BaseModel):
    value: str
    note: str = ""


@router.post("/explanations/{eid}/vote")
def vote(eid: int, body: VoteIn, db: Session = Depends(get_db), me=Depends(current_user)):
    if body.value not in ("up", "down", "report", "clear"):
        raise HTTPException(422, "value must be up, down, report or clear")
    e = db.get(Explanation, eid)
    if not e:
        raise HTTPException(404, "Explanation not found")
    if body.value == "report":
        if not db.query(ExplanationVote).filter_by(explanation_id=eid, user_id=me.id, value="report").first():
            db.add(ExplanationVote(explanation_id=eid, user_id=me.id, value="report", note=body.note[:500]))
            e.reports += 1
            # One report pulls an exam explanation for review; a textbook one needs three.
            if e.status != "retired" and (e.reports >= (1 if e.scope == "question" else 3)):
                e.status = "flagged"
        db.commit()
        return {"ok": True, "status": e.status}
    old = db.query(ExplanationVote).filter(ExplanationVote.explanation_id == eid, ExplanationVote.user_id == me.id, ExplanationVote.value.in_(("up", "down"))).first()
    if old:
        if old.value == "up": e.helpful -= 1
        else: e.unhelpful -= 1
        db.delete(old)
    if body.value in ("up", "down"):
        db.add(ExplanationVote(explanation_id=eid, user_id=me.id, value=body.value))
        if body.value == "up": e.helpful += 1
        else: e.unhelpful += 1
    db.flush()
    X.maybe_finalise(db, db.query(Explanation).filter(Explanation.anchor == e.anchor, Explanation.style == e.style, Explanation.level == e.level,
                                                      Explanation.status.in_(X.LIVE)).all())
    db.commit()
    return {"ok": True, "vote": body.value if body.value != "clear" else "", "status": e.status}


# ---------------- reviewer: look after the saved explanations ----------------
def ex_out(e: Explanation):
    return {"id": e.id, "scope": e.scope, "level": e.level, "style": e.style, "term": e.term, "text": e.text, "status": e.status, "source": e.source,
            "shown": e.shown, "helpful": e.helpful, "unhelpful": e.unhelpful, "retries": e.retries, "reports": e.reports, "model": e.model,
            "decided_by": e.decided_by, "parent_id": e.parent_id, "question_id": e.question_id, "book_id": e.book_id, "created_at": e.created_at}


@router.get("/admin/explanations")
def list_explanations(question_id: int | None = None, book_id: int | None = None, status: str = "", db: Session = Depends(get_db), _=Depends(staff)):
    q = db.query(Explanation)
    if question_id:
        roots = [e.id for e in db.query(Explanation).filter(Explanation.question_id == question_id)]
        q = q.filter((Explanation.question_id == question_id) | (Explanation.parent_id.in_(roots or [0])))
    if book_id:
        q = q.filter(Explanation.book_id == book_id)
    if status:
        q = q.filter(Explanation.status == status)
    return [ex_out(e) for e in q.order_by(Explanation.level, Explanation.style, Explanation.id).limit(500)]


class TextIn(BaseModel):
    text: str


@router.put("/admin/explanations/{eid}")
def edit_explanation(eid: int, body: TextIn, db: Session = Depends(get_db), me=Depends(staff)):
    e = db.get(Explanation, eid)
    if not e:
        raise HTTPException(404, "Explanation not found")
    if len(body.text.strip()) < 20:
        raise HTTPException(422, "That is too short to help a student")
    e.text, e.source = body.text.strip(), "edited"
    log(db, me, "explanation.edit", "explanation", eid)
    db.commit()
    return ex_out(e)


@router.post("/admin/explanations/{eid}/{action}")
def explanation_action(eid: int, action: str, db: Session = Depends(get_db), me=Depends(staff)):
    e = db.get(Explanation, eid)
    if not e:
        raise HTTPException(404, "Explanation not found")
    if action == "pin":
        for other in db.query(Explanation).filter(Explanation.anchor == e.anchor, Explanation.style == e.style, Explanation.level == e.level, Explanation.status == "final"):
            other.status = "candidate"
        e.status, e.decided_by = "final", me.name
    elif action == "retire":
        e.status = "retired"
    elif action == "restore":
        e.status, e.reports = "candidate", 0
    else:
        raise HTTPException(404, "Unknown action")
    log(db, me, "explanation." + action, "explanation", eid)
    db.commit()
    return ex_out(e)


# ---------------- writing explanations ahead of students ----------------
def walk(blocks):
    for b in blocks or []:
        yield b
        yield from walk(b.get("children"))


def passage_with(chapter, kid):
    for b in walk(chapter.get("blocks")):
        if any(str(m[2]) == str(kid) for m in b.get("marks") or []):
            return b.get("text", "")
        for it in b.get("items") or []:
            if any(str(m[2]) == str(kid) for m in it.get("marks") or []):
                return it.get("text", "")
    return ""


def prep_items(db, book: Book, styles: list[str]) -> list[dict]:
    """Everything a student could tap at level 1 that has no saved explanation yet, with the prompt for it."""
    ai = X.ai_conf(db)
    have = {(a, s) for a, s in db.query(Explanation.anchor, Explanation.style).filter(Explanation.level == 1, Explanation.status.in_(X.LIVE))}
    items = []
    if book.track == "exam":
        qs = db.query(Question).join(QuestionPaper, Question.paper_id == QuestionPaper.id).filter(QuestionPaper.book_id == book.id, QuestionPaper.status == "approved")
        for q in qs.order_by(Question.paper_id, Question.position):
            for st in styles:
                if (f"q:{q.id}", st) not in have:
                    items.append({"scope": "question", "anchor": f"q:{q.id}", "style": st, "question_id": q.id, "term": f"Question {q.number}",
                                  "where": f"{book.title}, question {q.number}", "prompt": X.question_prompt(book, q, st, ai)})
    else:
        for ch in _chapters(book):
            for k in ch.get("keywords") or []:
                anchor = f"book:{book.id}:{book.content_key}:ch{ch.get('number')}:kw:{k.get('id')}"
                for st in styles:
                    if (anchor, st) not in have:
                        items.append({"scope": "book", "anchor": anchor, "style": st, "question_id": None, "term": k.get("term", ""),
                                      "where": f"{book.title}, unit {ch.get('number')}",
                                      "prompt": X.book_prompt(book, ch.get("title", ""), k.get("term", ""), passage_with(ch, k.get("id")), k.get("definition", ""), [], st, ai)})
    return items


def _styles(db, raw: str | list) -> list[str]:
    known = list((X.ai_conf(db).get("depth_rules") or {}).keys())
    styles = [s for s in (raw.split(",") if isinstance(raw, str) else raw) if s in known]
    if not styles:
        raise HTTPException(422, "Pick at least one explanation style")
    return styles


@router.get("/admin/prepare/{bid}/estimate")
def prepare_estimate(bid: int, styles: str = "concept_clarity", db: Session = Depends(get_db), _=Depends(sa)):
    book = db.get(Book, bid)
    if not book:
        raise HTTPException(404, "Not found")
    items = prep_items(db, book, _styles(db, styles))
    tokens = sum(len(i["prompt"]) // 4 + 350 for i in items)
    return {"requests": len(items), "tokens": tokens, "budget_left": X.budget_left(db), "model": X.ai_conf(db)["providers"].get(X.ai_conf(db)["provider"], {}).get("model", ""),
            "note": "" if items else ("Nothing to write: everything already has a saved explanation." if book.content_key or book.track == "exam" else "This book has no converted content yet.")}


class PrepIn(BaseModel):
    book_id: int
    styles: list[str] = ["concept_clarity"]


def supervise_prep(job_id: int):
    r = subprocess.run([sys.executable, "-m", "app.prepare", str(job_id)], capture_output=True, text=True, errors="replace",
                       env={**os.environ, "PYTHONPATH": str(BASE)})
    if r.returncode:
        with SessionLocal() as db:
            j = db.get(PrepJob, job_id)
            if j and j.status in ("queued", "running"):
                j.status, j.error, j.finished_at = "failed", f"Stopped unexpectedly (code {r.returncode}). {r.stderr[-400:]}", datetime.utcnow()
                db.commit()


@router.post("/admin/prepare")
def prepare(body: PrepIn, db: Session = Depends(get_db), me=Depends(sa)):
    book = db.get(Book, body.book_id)
    if not book:
        raise HTTPException(404, "Not found")
    if db.query(PrepJob).filter(PrepJob.book_id == book.id, PrepJob.status.in_(("queued", "running"))).count():
        raise HTTPException(409, "Explanations are already being written for this")
    styles = _styles(db, body.styles)
    items = prep_items(db, book, styles)
    if not items:
        raise HTTPException(409, "Nothing to write: everything already has a saved explanation")
    left = X.budget_left(db)
    need = sum(len(i["prompt"]) // 4 + 350 for i in items)
    if left is not None and need > left:
        raise HTTPException(409, f"This needs about {need:,} tokens but only {max(left, 0):,} are left in this month's budget")
    j = PrepJob(book_id=book.id, styles=styles, total=len(items), started_by=me.email)
    db.add(j); log(db, me, "explanation.prepare", "book", book.id, styles=styles, requests=len(items)); db.commit()
    threading.Thread(target=supervise_prep, args=(j.id,), daemon=True).start()
    return job_out(j)


def job_out(j: PrepJob):
    return {"id": j.id, "book_id": j.book_id, "styles": j.styles, "status": j.status, "total": j.total, "done": j.done, "failed": j.failed,
            "tokens": j.tokens, "error": j.error, "created_at": j.created_at, "finished_at": j.finished_at}


@router.get("/admin/prepare/jobs")
def prepare_jobs(db: Session = Depends(get_db), _=Depends(sa)):
    return [job_out(j) for j in db.query(PrepJob).order_by(PrepJob.id.desc()).limit(50)]


# ---------------- cost dashboard and confusion map ----------------
@router.get("/admin/usage")
def usage(days: int = 30, db: Session = Depends(get_db), _=Depends(sa)):
    ai = X.ai_conf(db)
    since = datetime.utcnow() - timedelta(days=max(1, min(days, 365)))
    rows = db.query(AiUsage).filter(AiUsage.at >= since).all()
    prices, cur = ai.get("prices") or {}, ai.get("currency") or "USD"

    def cost(model, p, c):
        pr = prices.get(model) or {}
        if not pr:
            return None
        return (p * float(pr.get("in") or 0) + c * float(pr.get("out") or 0)) / 1_000_000

    by_kind, by_model, daily = defaultdict(lambda: [0, 0, 0]), defaultdict(lambda: [0, 0, 0]), defaultdict(lambda: {"tokens": 0, "saved": 0, "generated": 0})
    for r in rows:
        tok = r.prompt_tokens + r.completion_tokens
        d = r.at.strftime("%Y-%m-%d")
        if r.cached:
            daily[d]["saved"] += 1; by_kind[r.kind][2] += 1
            continue
        by_kind[r.kind][0] += 1; by_kind[r.kind][1] += tok
        by_model[r.model][0] += r.prompt_tokens; by_model[r.model][1] += r.completion_tokens; by_model[r.model][2] += 1
        daily[d]["tokens"] += tok
        if r.kind in ("explain", "explain_deep"):
            daily[d]["generated"] += 1
    saved = sum(1 for r in rows if r.cached)
    gen = sum(1 for r in rows if not r.cached and r.kind in ("explain", "explain_deep"))
    models = [{"model": m, "prompt": v[0], "completion": v[1], "requests": v[2], "cost": cost(m, v[0], v[1])} for m, v in sorted(by_model.items(), key=lambda kv: -(kv[1][0] + kv[1][1]))]
    known = [m["cost"] for m in models if m["cost"] is not None]
    taps = Counter((r.term, r.where, r.book_id) for r in rows if r.kind == "explain" and r.term)
    books = {b.id: b.title for b in db.query(Book).filter(Book.id.in_({k[2] for k in taps} or {0}))}
    ex = Counter(s for (s,) in db.query(Explanation.status))
    start = datetime.utcnow().date() - timedelta(days=max(1, min(days, 365)) - 1)
    return {"days": days, "month_tokens": X.month_tokens(db), "budget": int(ai.get("monthly_token_budget") or 0), "budget_left": X.budget_left(db),
            "requests": sum(v[0] for v in by_kind.values()), "tokens": sum(v[1] for v in by_kind.values()),
            "saved": saved, "generated": gen, "hit_rate": round(saved / (saved + gen) * 100) if saved + gen else None,
            "cost": sum(known) if known else None, "cost_partial": len(known) < len(models), "currency": cur, "prices": prices,
            "by_kind": [{"kind": k, "requests": v[0], "tokens": v[1], "saved": v[2]} for k, v in sorted(by_kind.items())],
            "by_model": models,
            "daily": [{"day": (start + timedelta(days=i)).isoformat(), **daily.get((start + timedelta(days=i)).isoformat(), {"tokens": 0, "saved": 0, "generated": 0})} for i in range((datetime.utcnow().date() - start).days + 1)],
            "confusion": [{"term": t, "where": w, "book": books.get(b, ""), "taps": n} for (t, w, b), n in taps.most_common(25)],
            "explanations": {"total": sum(ex.values()), **ex},
            "flagged": [ex_out(e) for e in db.query(Explanation).filter(Explanation.status == "flagged").order_by(Explanation.id.desc()).limit(50)]}
