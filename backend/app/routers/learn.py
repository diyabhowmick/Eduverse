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
from .. import content as C
from ..models import AiUsage, Book, Explanation, ExplainLink, ExplanationVote, Misconception, PrepJob, Question, QuestionPaper
from ..security import current_user, require
from ..audit import log
from .. import explain_store as X
from .. import hardening as H

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


class TextIn(BaseModel):
    text: str


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


def _links(db, e: Explanation | None) -> list[dict]:
    if not e or e.level != 1 or e.scope != "book":
        return []
    return [{"term": l.term} for l in db.query(ExplainLink).filter(ExplainLink.parent_id == e.id).order_by(ExplainLink.id)]


def _out(db, e: Explanation | None, me, credits: Credits, *, text=None, level=None, cached=False, live=False, term="", bridge="", **extra):
    mine = db.query(ExplanationVote).filter(ExplanationVote.explanation_id == e.id, ExplanationVote.user_id == me.id).order_by(ExplanationVote.id.desc()).first() if e else None
    lv = e.level if e else level
    return {"id": e.id if e else None, "text": e.text if e else text, "level": lv, "style": e.style if e else "",
            "term": e.term if e else term, "cached": cached, "live": live, "final": bool(e and e.status == "final"),
            "vote": mine.value if mine and mine.value != "report" else "", "credits_left": credits.left(), "free_deeper": lv < 2,
            "bridge": bridge, "links": _links(db, e), **extra}


def _who(scope, book) -> str:
    return f"a Class {book.grade} {book.subject} student ({book.board})" if scope == "book" else f"a student preparing for {book.exam or 'an exam'}"


def _find_link(db, parent: Explanation, phrase: str) -> ExplainLink | None:
    """The prepared level 2 word the student tapped, allowing for a selection a little wider or narrower than it."""
    links = db.query(ExplainLink).filter(ExplainLink.parent_id == parent.id).all()
    exact = next((l for l in links if l.key == phrase), None)
    if exact:
        return exact
    close = [l for l in links if len(l.key) >= 3 and (l.key in phrase or phrase in l.key)]
    return max(close, key=lambda l: len(l.key)) if close else None


@router.post("/explain")
def explain(body: ExplainIn, db: Session = Depends(get_db), me=Depends(current_user)):
    H.guard(f"explain:{me.id}", 40, 60, "Slow down a little: too many explanations in one minute.")
    ai = X.ai_conf(db)
    credits = Credits(db, me)
    style = body.style if body.style in (ai.get("depth_rules") or {}) else "concept_clarity"
    if me.role == "student":
        from .student import rules_for
        allowed = rules_for(db, me)["allowed_depths"]
        style = style if style in allowed else allowed[0]
    parent = root = q = None
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
    who = _who(scope, book)
    level = parent.level + 1 if parent else 1

    # A typed question: matched to what is saved first; the model only bridges or, failing that, answers.
    if body.doubt.strip():
        if not parent:
            raise HTTPException(422, "Ask about an explanation you have open")
        return _doubt(db, me, credits, ai, book, scope, root, parent, body.doubt.strip()[:400], who)

    # Where this explanation lives.
    bridge, link = "", None
    if parent:
        phrase = X.norm(body.term)
        if len(phrase) < 2:
            raise HTTPException(422, "Select the words you want explained")
        if H.unsafe(body.term):
            raise HTTPException(422, "Select words from the explanation")
        if level == 2 and scope == "book":
            # Level 2 in a textbook is one saved answer per word per book, whichever explanation it was tapped from.
            link = _find_link(db, parent, phrase)
            term = link.term if link else body.term.strip()[:200]
            anchor, bridge = X.l2_anchor(book, term), (link.bridge if link else "")
        else:
            anchor, term = f"x:{parent.id}:{phrase}", body.term.strip()[:200]
        where = root.term
    elif scope == "question":
        anchor, term, where = f"q:{q.id}", f"Question {q.number}", f"{book.title}, question {q.number}"
    else:
        place = f"kw:{body.keyword_id}" if body.keyword_id else f"blk:{body.block_id}:{X.norm(body.term)}"
        anchor, term, where = f"book:{book.id}:{C.reader_key(book)}:ch{body.chapter}:{place}", body.term.strip()[:200], f"{book.title}, unit {body.chapter}"

    def pool_for(a):
        return db.query(Explanation).filter(Explanation.anchor == a, Explanation.style == style, Explanation.level == level,
                                            Explanation.status.in_(X.LIVE)).order_by(Explanation.id).all()
    pool = pool_for(anchor)
    if not pool and parent and anchor.startswith("l2:"):
        pool = pool_for(f"x:{parent.id}:{phrase}")   # saved by an earlier build, one per explanation

    free = parent is not None and level == 2   # the first "go deeper" is free, as the panel promises

    def fresh():
        if not free:
            credits.check()
        if parent and anchor.startswith("l2:"):
            prompt = X.core_prompt(book, term, [parent.text[:600]], who, style, ai)
        elif parent:
            prompt = X.deeper_prompt(root, parent, term, who)
        elif scope == "question":
            prompt = X.question_prompt(book, q, style, ai)
        else:
            chapter_title = next((c.get("title", "") for c in _chapters(book) if c.get("number") == body.chapter), "")
            prompt = X.book_prompt(book, chapter_title, term, body.paragraph[:1500], body.definition[:800], body.figures[:3], style, ai)
        text, model = X.generate(db, prompt, kind="explain_deep" if level >= 3 else "explain", user_id=me.id, book_id=book.id, term=term, where=where)
        if not free:
            credits.spend(book.id, text)
        if H.unsafe(text):
            raise HTTPException(502, "That explanation did not come out right. Try again in a moment.")
        # Saved, even past level 2, so the next student who asks the same is served for free. A reviewer can check it later.
        e = Explanation(scope=scope, anchor=anchor, level=level, style=style, lang=book.medium or "English",
                        parent_id=parent.id if parent and not anchor.startswith("l2:") else None,
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
        try:
            e, cached = fresh(), False
        except HTTPException as ex:
            # The model is down. If the book itself defines the word, show that instead of an error.
            if ex.status_code in (502, 503) and not parent and body.definition.strip():
                db.rollback()
                return {**_out(db, None, me, credits, text=body.definition.strip(), level=level, live=True, term=term), "from_book": True,
                        "note": "Explanations are taking a break, so here is what your book says."}
            raise
    e.shown += 1
    if cached:
        X.record(db, "explain_deep" if level >= 3 else "explain", e.model, None, me.id, book.id, True, term, where)
    X.maybe_finalise(db, pool)
    if me.role == "student" and scope == "book" and level <= 2:
        _word_card(db, me, e, 3)
    db.commit()
    return _out(db, e, me, credits, cached=cached, bridge=bridge)


def _word_card(db, me, e: Explanation, after: int):
    """A word the learner keeps opening (or found unhelpful) becomes a revision card."""
    if after:
        n = db.query(func.count(AiUsage.id)).filter(AiUsage.user_id == me.id, AiUsage.term == e.term, AiUsage.book_id == e.book_id,
                                                     AiUsage.kind.in_(("explain",))).scalar() or 0
        if n + 1 < after:
            return
    from .. import study as S
    S.card_for(db, me.id, "word", e.id, e.term, e.text, "A word you opened often" if after else "Marked not helpful", e.book_id)


def _doubt(db, me, credits, ai, book, scope, root, parent, doubt, who):
    """Plan section 5. A close match to something saved is served as it is. A partial match gets two or three
    lines from the model that lead into the saved answer. Only a question nothing saved touches is answered in
    full. Every reply the model writes is kept with the student's words, so the next student is matched to it."""
    from ..explain_match import Matcher, best_misconception, best_explanation
    pc = X.pconf(ai)
    hi, lo = float(pc.get("match_high") or 0.6), float(pc.get("match_low") or 0.28)
    m = Matcher(ai)
    qv = m.vec(doubt)
    where = root.term

    # Nothing a student types is passed on to the model or kept for others if it carries instructions for the AI,
    # contact details or abuse. They get a gentle answer and no credit is spent.
    if H.unsafe(doubt):
        return _out(db, None, me, credits, text="I can only help with what you are studying here. Ask me about this topic in your own words.",
                    level=parent.level + 1, live=True, term=doubt, kind="refused")

    mc, ms = best_misconception(db, m, book.id, root.id, qv)
    # A saved reply written for one student reaches others only once a reviewer approved it, or three different
    # students asked the same thing. One student cannot plant an answer for everyone.
    shared_ok = bool(mc) and (mc.status == "final" or me.id in (mc.askers or []) or len(mc.askers or []) >= 3)
    if mc and ms >= hi and not shared_ok and mc.status != "held":
        mc.askers = list(dict.fromkeys([*(mc.askers or []), me.id]))[:50]
    if mc and ms >= hi and shared_ok and mc.status != "held":
        target = db.get(Explanation, mc.explanation_id) if mc.explanation_id else None
        mc.hits += 1
        X.record(db, "doubt", mc.model, None, me.id, book.id, True, doubt[:200], where)
        db.commit()
        return _out(db, None, me, credits, text=mc.reply, level=parent.level + 1, cached=True, term=doubt, kind="match", score=round(ms, 2),
                    see=_see(target, parent), misconception_id=mc.id)

    ex, es = best_explanation(db, m, book.id, qv)
    if ex and es >= hi and ex.id != parent.id:
        ex.shown += 1
        X.record(db, "doubt", ex.model, None, me.id, book.id, True, doubt[:200], where)
        db.commit()
        return {**_out(db, ex, me, credits, cached=True), "kind": "saved", "score": round(es, 2), "asked": doubt}

    credits.check()
    if ex and es >= lo:
        text, model = X.generate(db, X.bridge_prompt(ex, doubt, who), kind="doubt", user_id=me.id, book_id=book.id, term=doubt[:200], where=where)
        kind, target = "bridge", ex
    else:
        text, model = X.generate(db, X.doubt_prompt(root, parent, doubt, who), kind="explain_deep", user_id=me.id, book_id=book.id, term=doubt[:200], where=where)
        kind, target = "full", None
    credits.spend(book.id, text)
    if H.unsafe(text):
        db.commit()
        return _out(db, None, me, credits, text="I could not write a good answer to that. Try asking about the topic in a different way.",
                    level=parent.level + 1, live=True, term=doubt, kind="refused")
    if not (mc and ms >= hi):   # a close but unapproved reply already exists: it keeps counting askers instead of a duplicate being kept
        mc = Misconception(book_id=book.id, root_id=root.id, explanation_id=target.id if target else None, sample=doubt, reply=text, kind=kind,
                           vec=qv, vec_model=m.model, model=model, askers=[me.id])
        db.add(mc)
    db.commit()
    return _out(db, None, me, credits, text=text, level=parent.level + 1, live=True, term=doubt, kind=kind, see=_see(target, parent), misconception_id=mc.id)


def _see(target: Explanation | None, parent: Explanation):
    """The saved explanation a reply leads into, unless it is the one already on the student's screen."""
    if not target or target.id == parent.id:
        return {"id": target.id, "term": target.term, "same": True} if target else None
    return {"id": target.id, "term": target.term, "text": target.text, "level": target.level}


def _chapters(book: Book) -> list:
    from .. import content as C
    try:
        return C.load_ro(book, C.reader_key(book)).get("chapters", [])
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
        if body.value == "down" and me.role == "student" and e.scope == "book":
            _word_card(db, me, e, 0)
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
def list_explanations(question_id: int | None = None, book_id: int | None = None, status: str = "", level: int | None = None, source: str = "",
                      db: Session = Depends(get_db), _=Depends(staff)):
    q = db.query(Explanation)
    if question_id:
        roots = [e.id for e in db.query(Explanation).filter(Explanation.question_id == question_id)]
        q = q.filter((Explanation.question_id == question_id) | (Explanation.parent_id.in_(roots or [0])))
    if book_id:
        q = q.filter(Explanation.book_id == book_id)
    if status:
        q = q.filter(Explanation.status == status)
    if level:
        q = q.filter(Explanation.level == level)
    if source:
        q = q.filter(Explanation.source == source)
    rows = q.order_by(Explanation.level, Explanation.style, Explanation.id).limit(500).all()
    links = defaultdict(list)
    for l in db.query(ExplainLink).filter(ExplainLink.parent_id.in_([e.id for e in rows] or [0])):
        links[l.parent_id].append({"id": l.id, "term": l.term, "bridge": l.bridge})
    ctx = Context(db)
    return [{**ex_out(e), "links": links.get(e.id, []), "context": ctx.of(e)} for e in rows]


class Context:
    """Where an explanation is used, for the reviewer to read beside it: the book's own paragraph for level 1,
    the sentences that lead to it for level 2, and the explanation it came from for level 3."""
    def __init__(self, db):
        self.db, self.books = db, {}

    def chapters(self, bid, key):
        if (bid, key) not in self.books:
            b = self.db.get(Book, bid)
            try:
                self.books[(bid, key)] = C.load(b, key).get("chapters", []) if b else []
            except Exception:
                self.books[(bid, key)] = []
        return self.books[(bid, key)]

    def of(self, e: Explanation) -> dict | None:
        try:
            if e.scope == "book" and e.level == 1 and e.anchor.startswith("book:"):
                _b, bid, key, chn, kind, ref = e.anchor.split(":", 5)
                ch = next((c for c in self.chapters(int(bid), key) if f"ch{c.get('number')}" == chn), None)
                if not ch:
                    return None
                if kind == "kw":
                    text = passage_with(ch, ref)
                else:
                    blk = ref.split(":", 1)[0]
                    text = next((b.get("text", "") for b in walk(ch.get("blocks")) if b.get("id") == blk), "")
                return {"where": f"Unit {ch.get('number')}: {ch.get('title', '')}", "parts": [text] if text else []}
            if e.anchor.startswith("l2:"):
                from ..prepare import _sentence_with
                rows = self.db.query(ExplainLink, Explanation).join(Explanation, ExplainLink.parent_id == Explanation.id).filter(
                    ExplainLink.book_id == e.book_id, ExplainLink.key == X.norm(e.term)).limit(3).all()
                return {"where": "Inside " + ", ".join(sorted({p.term for _l, p in rows})) if rows else "Tapped by a student",
                        "parts": [_sentence_with(p.text, l.term) for l, p in rows]}
            if e.parent_id:
                p = self.db.get(Explanation, e.parent_id)
                return {"where": f"Inside the explanation of {p.term}", "parts": [p.text[:700]]} if p else None
        except Exception:
            return None
        return None


@router.get("/admin/explained_books")
def explained_books(db: Session = Depends(get_db), _=Depends(staff)):
    """Textbooks with saved explanations, and what is waiting for a reviewer in each."""
    counts = defaultdict(Counter)
    for bid, level, status, source in db.query(Explanation.book_id, Explanation.level, Explanation.status, Explanation.source).filter(Explanation.scope == "book"):
        c = counts[bid]
        c["total"] += 1; c[f"l{min(level, 3)}"] += 1
        if status == "flagged": c["flagged"] += 1
        if status == "candidate" and source == "live": c["unchecked"] += 1
    for bid, n in db.query(Misconception.book_id, func.count(Misconception.id)).group_by(Misconception.book_id):
        counts[bid]["replies"] += n
    books = db.query(Book).filter(Book.id.in_(list(counts) or [0])).order_by(Book.title)
    return [{"id": b.id, "title": b.title, "status": b.status, **dict(counts[b.id]), "waiting": _unapproved(db, b)[0]} for b in books]


def mc_out(m: Misconception, db):
    target = db.get(Explanation, m.explanation_id) if m.explanation_id else None
    root = db.get(Explanation, m.root_id) if m.root_id else None
    return {"id": m.id, "sample": m.sample, "reply": m.reply, "kind": m.kind, "hits": m.hits, "status": m.status, "model": m.model,
            "leads_to": target.term if target else "", "asked_in": root.term if root else "", "created_at": m.created_at}


@router.get("/admin/misconceptions")
def list_misconceptions(book_id: int, db: Session = Depends(get_db), _=Depends(staff)):
    rows = db.query(Misconception).filter(Misconception.book_id == book_id).order_by(Misconception.hits.desc(), Misconception.id.desc()).limit(500)
    return [mc_out(m, db) for m in rows]


@router.put("/admin/misconceptions/{mid}")
def edit_misconception(mid: int, body: TextIn, db: Session = Depends(get_db), me=Depends(staff)):
    m = db.get(Misconception, mid)
    if not m:
        raise HTTPException(404, "Not found")
    if len(body.text.strip()) < 10:
        raise HTTPException(422, "That is too short to help a student")
    m.reply, m.status = body.text.strip(), "final"
    log(db, me, "misconception.edit", "misconception", mid)
    db.commit()
    return mc_out(m, db)


@router.post("/admin/misconceptions/{mid}/{action}")
def misconception_action(mid: int, action: str, db: Session = Depends(get_db), me=Depends(staff)):
    m = db.get(Misconception, mid)
    if not m:
        raise HTTPException(404, "Not found")
    if action not in ("approve", "retire", "restore"):
        raise HTTPException(404, "Unknown action")
    m.status = {"approve": "final", "retire": "retired", "restore": "candidate"}[action]
    log(db, me, "misconception." + action, "misconception", mid)
    db.commit()
    return mc_out(m, db)


class LinkIn(BaseModel):
    term: str
    bridge: str = ""


@router.post("/admin/explanations/{eid}/links")
def add_link(eid: int, body: LinkIn, db: Session = Depends(get_db), me=Depends(staff)):
    e = db.get(Explanation, eid)
    if not e or e.level != 1:
        raise HTTPException(404, "Level 1 explanation not found")
    term = body.term.strip()
    if term.lower() not in e.text.lower():
        raise HTTPException(422, "Pick words that appear in the explanation")
    l = ExplainLink(parent_id=e.id, book_id=e.book_id, term=term[:200], key=X.norm(term), bridge=body.bridge.strip()[:300])
    db.add(l); log(db, me, "explanation.link_add", "explanation", eid, term=term); db.commit()
    return {"id": l.id, "term": l.term, "bridge": l.bridge}


@router.delete("/admin/links/{lid}")
def remove_link(lid: int, db: Session = Depends(get_db), me=Depends(staff)):
    l = db.get(ExplainLink, lid)
    if not l:
        raise HTTPException(404, "Not found")
    db.delete(l); log(db, me, "explanation.link_remove", "explanation", l.parent_id, term=l.term); db.commit()
    return {"ok": True}


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


def pending_level2(db, book: Book, styles: list[str], level1_new: int) -> int:
    """Level 1 answers whose hard words have not been picked yet, counting the ones this run is about to write."""
    if book.track == "exam" or not X.pconf(db).get("level2"):
        return 0
    have = db.query(Explanation).filter(Explanation.book_id == book.id, Explanation.scope == "book", Explanation.level == 1,
                                        Explanation.status.in_(X.LIVE), Explanation.marked.is_not(True), Explanation.style.in_(styles)).count()
    return have + level1_new


def plan_for(db, book: Book, styles: list[str]) -> dict:
    items = prep_items(db, book, styles)
    marks = pending_level2(db, book, styles, len(items))
    words = int(marks * min(int(X.pconf(db).get("terms_per_explanation") or 4), 8) * 0.6)   # about 40% of words repeat across a book
    tokens = sum(len(i["prompt"]) // 4 + 350 for i in items) + marks * 1100 + words * 450
    return {"items": items, "level1": len(items), "marks": marks, "level2": words, "requests": len(items) + marks + words, "tokens": tokens}


@router.get("/admin/prepare/{bid}/estimate")
def prepare_estimate(bid: int, styles: str = "concept_clarity", db: Session = Depends(get_db), _=Depends(sa)):
    book = db.get(Book, bid)
    if not book:
        raise HTTPException(404, "Not found")
    p = plan_for(db, book, _styles(db, styles))
    return {"requests": p["requests"], "level1": p["level1"], "marks": p["marks"], "level2": p["level2"], "tokens": p["tokens"],
            "budget_left": X.budget_left(db), "model": X.ai_conf(db)["providers"].get(X.ai_conf(db)["provider"], {}).get("model", ""),
            "note": "" if p["requests"] else ("Nothing to write: everything already has a saved explanation." if book.content_key or book.track == "exam" else "This book has no converted content yet.")}


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


def start_prep(db, book: Book, styles: list[str], by: str, me=None) -> PrepJob:
    if db.query(PrepJob).filter(PrepJob.book_id == book.id, PrepJob.status.in_(("queued", "running"))).count():
        raise HTTPException(409, "Explanations are already being written for this")
    p = plan_for(db, book, styles)
    if not p["requests"]:
        raise HTTPException(409, "Nothing to write: everything already has a saved explanation")
    left = X.budget_left(db)
    if left is not None and p["tokens"] > left:
        raise HTTPException(409, f"This needs about {p['tokens']:,} tokens but only {max(left, 0):,} are left in this month's budget")
    j = PrepJob(book_id=book.id, styles=styles, total=p["requests"], started_by=by)
    db.add(j)
    if me:
        log(db, me, "explanation.prepare", "book", book.id, styles=styles, requests=p["requests"])
    db.commit()
    from ..tasks import enqueue
    enqueue("prep", j.id)
    return j


def _unapproved(db, book: Book) -> tuple[int, int]:
    """Level 1 and 2 places with no approved (final) explanation, and reported ones, for one textbook."""
    rows = db.query(Explanation.anchor, Explanation.style, Explanation.level, Explanation.status).filter(
        Explanation.book_id == book.id, Explanation.scope == "book", Explanation.level <= 2, Explanation.status.in_(X.LIVE + ("flagged",))).all()
    final = {(a, s, l) for a, s, l, st in rows if st == "final"}
    places = {(a, s, l) for a, s, l, st in rows if st != "flagged"}
    return len(places - final), sum(1 for *_x, st in rows if st == "flagged")


def explain_gate(db, book: Book, me=None) -> str | None:
    """Why a textbook cannot go live yet, or None.

    Writing ahead (auto_on_live) starts here whether or not approval is required. When approval is required the
    book waits for the writing and then for a reviewer to approve every level 1 and level 2 explanation.

    It never starts a job it knows will fail: if the model cannot answer, or the last attempt for this book
    failed, it says why instead of starting another one. Before this, every Publish click started a job that
    failed in a second while the reviewer was told the explanations were "being written", so the book could
    never go live."""
    pc = X.pconf(db)
    if book.track == "exam":
        return None
    need = pc.get("require_approval")
    j = db.query(PrepJob).filter(PrepJob.book_id == book.id, PrepJob.status.in_(("queued", "running"))).first()
    if j:
        return (f"Explanations are still being written ({j.done} of {j.total}). Approve them under Explanations once done, "
                "then publish.") if need else None
    if pc.get("auto_on_live"):
        try:
            todo = plan_for(db, book, ["concept_clarity"])["requests"]
        except HTTPException:
            todo = 0
        if todo:
            last = db.query(PrepJob).filter(PrepJob.book_id == book.id).order_by(PrepJob.id.desc()).first()
            problem = X.provider_problem(X.ai_conf(db))
            recent = last and last.finished_at and datetime.utcnow() - last.finished_at < timedelta(minutes=10)
            if not problem and last and last.status == "failed" and recent:
                problem = (f"The last attempt to write them failed: {(last.error or 'no reason given')[:300]}. Fix the AI settings, "
                           "then press Write ahead under AI usage (or publish again in 10 minutes to retry)")
            if problem:
                if need:
                    return f"Explanations could not be written. {problem}"
                return None  # approval not required: the book may go live; students' taps are answered live when the model is back
            try:
                start_prep(db, book, ["concept_clarity"], getattr(me, "email", "") or "auto, on publish", me)
                if need:
                    # the same count the writing job shows, so the reviewer sees one number, not two
                    j = db.query(PrepJob).filter(PrepJob.book_id == book.id).order_by(PrepJob.id.desc()).first()
                    n = j.total if j and j.total else todo
                    return (f"Explanations are now being written for this book (0 of {n}). "
                            "Approve them under Explanations once done, then publish.")
            except HTTPException as e:
                db.rollback()
                if need and "Nothing to write" not in str(e.detail):
                    return f"Explanations could not be written: {e.detail}"
    if not need:
        return None
    waiting, reported = _unapproved(db, book)
    if waiting or reported:
        parts = ([f"{waiting} explanation{'s' if waiting != 1 else ''} still need approval"] if waiting else []) + \
                ([f"{reported} reported explanation{'s' if reported != 1 else ''} need a look"] if reported else [])
        return " and ".join(parts) + ". Open Explanations to approve them, then publish."
    return None


class ApproveAllIn(BaseModel):
    level: int | None = None


@router.post("/admin/books/{bid}/explanations/approve_all")
def approve_all(bid: int, body: ApproveAllIn, db: Session = Depends(get_db), me=Depends(staff)):
    """Approves the explanation in use at every level 1 or 2 place that has none approved yet. Reported ones are left alone."""
    q = db.query(Explanation).filter(Explanation.book_id == bid, Explanation.scope == "book", Explanation.level <= 2, Explanation.status.in_(X.LIVE))
    if body.level:
        q = q.filter(Explanation.level == body.level)
    groups = defaultdict(list)
    for e in q:
        groups[(e.anchor, e.style, e.level)].append(e)
    n = 0
    for pool in groups.values():
        if any(e.status == "final" for e in pool):
            continue
        best = max(pool, key=lambda e: (X.merit(e), -e.id))
        best.status, best.decided_by = "final", me.name
        n += 1
    log(db, me, "explanation.approve_all", "book", bid, level=body.level, approved=n)
    db.commit()
    return {"approved": n}


@router.post("/admin/prepare")
def prepare(body: PrepIn, db: Session = Depends(get_db), me=Depends(sa)):
    book = db.get(Book, body.book_id)
    if not book:
        raise HTTPException(404, "Not found")
    return job_out(start_prep(db, book, _styles(db, body.styles), me.email, me))


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
        if r.kind in ("explain", "explain_deep", "doubt"):
            daily[d]["generated"] += 1
    saved = sum(1 for r in rows if r.cached)
    gen = sum(1 for r in rows if not r.cached and r.kind in ("explain", "explain_deep", "doubt"))
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


# ---------------- Eddie, the study buddy on the student home page ----------------
class BuddyIn(BaseModel):
    question: str
    context: str = ""          # what Home already shows: name, class, books, today's plan
    history: list[dict] = []   # the last few turns, [{"who": "me"|"eddie", "text": ...}]


@router.post("/buddy")
def buddy(body: BuddyIn, db: Session = Depends(get_db), me=Depends(current_user)):
    q = body.question.strip()[:400]
    if not q:
        raise HTTPException(422, "Ask Eddie something")
    H.guard(f"buddy:{me.id}", 15, 60, "Eddie needs a moment. Try again in a minute.")
    if H.unsafe(q):
        return {"text": "I can only help with your studies here. What are you learning today?", "credits_left": Credits(db, me).left()}
    credits = Credits(db, me)
    credits.check()
    turns = "\n".join(f"{'Student' if t.get('who') == 'me' else 'Eddie'}: {str(t.get('text', ''))[:300]}" for t in body.history[-6:])
    prompt = f"""You are Eddie, a cheerful little robot study buddy inside EduVerse, talking out loud with a school student.
What you know about them and what is on their screen: {body.context[:3600]}
{('Conversation so far:' + chr(10) + turns) if turns else ''}
Student: {q}

Reply as Eddie in under 90 words, warm and encouraging, like a friendly older sibling who is good at studies.
Your reply is read aloud, so write plain spoken sentences: no lists, no markdown, no LaTeX, no emojis; say maths in words (\"x squared plus one\").
If they ask about \"this part\" or \"this unit\", use the text on their screen. You know each figure through its written description: explain it as if pointing at it (\"the dotted line in the middle is the normal\"), but only mention parts, labels and values the description gives. If it is a study doubt, explain it simply with one everyday example. If it is about what to study, use their plan above.
If it is not about studies, answer kindly in a line and steer back to learning. Never invent marks, dates or facts about the student."""
    text, _m = X.generate(db, prompt, kind="buddy", user_id=me.id, term=q[:200], where="Eddie on Home")
    credits.spend(None, text)
    db.commit()
    return {"text": text.replace("$", "").strip(), "credits_left": credits.left()}
