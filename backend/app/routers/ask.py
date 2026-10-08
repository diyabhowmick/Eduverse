"""A student's own question — the only place a model runs while anybody waits.

Tapping a word is free, because that answer was written during review and the
reviewer approved it. This is different: nobody could have predicted the
question, so it costs something every time.

Four things keep that under control, cheapest first:

  the page goes with the question   the model answers from this passage only
  a word check before spending      no overlap with the page, no API call
  a cap per student per day         one keen student cannot drain the class
  a refusal costs nothing           or students spend the quota testing it

The cap is per student rather than per school on purpose. A shared pool sounds
fairer and is not: the best reader in the class finishes it by Tuesday and
thirty others get nothing.
"""
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..defaults import AI
from ..explain_prompt import explain
from ..models import AskLog, Book, School, Setting, User
from ..security import require

router = APIRouter(prefix="/api/ask", tags=["ask"])
student = require("student")

WORD = re.compile(r"[a-z]{4,}")


def ai_settings(db: Session) -> dict:
    """The same provider, model and key the tappable explanations use."""
    row = db.get(Setting, "ai")
    return {**AI, **((row.value if row else None) or {})}


def quota(db: Session, me: User) -> dict:
    since = datetime.utcnow() - timedelta(days=1)
    used_today = db.query(AskLog).filter(
        AskLog.user_id == me.id, AskLog.answered == True,     # noqa: E712
        AskLog.at >= since).count()
    s = db.get(School, me.school_id) if me.school_id else None
    cap = s.ask_per_student_day if s else 10
    return {"used_today": used_today, "cap": cap,
            "left": max(0, cap - used_today),
            "pool_left": max(0, (s.ask_pool - s.ask_pool_used)) if s else None,
            "pool_total": s.ask_pool if s else None}


@router.get("/quota")
def my_quota(db: Session = Depends(get_db), me=Depends(student)):
    return quota(db, me)


class AskIn(BaseModel):
    book_id: int
    section: str = ""
    passage: str = ""          # the text the student is looking at
    question: str


def on_topic(question: str, passage: str) -> bool:
    """Does the question have anything to do with this page?

    A local check — no model, no cost. It will not catch everything, and it
    does not need to: it catches the obvious cases before any money is spent,
    and the model is told to answer only from the passage anyway.
    """
    q = set(WORD.findall(question.lower()))
    p = set(WORD.findall((passage or "").lower()))
    if not q:
        return False
    return bool(q & p)


@router.post("")
def ask(body: AskIn, db: Session = Depends(get_db), me=Depends(student)):
    q = (body.question or "").strip()
    if not q:
        raise HTTPException(422, "Type a question")
    book = db.get(Book, body.book_id)
    if not book or book.status != "live":
        raise HTTPException(404, "Book not found")

    def log(answered, why="", tokens=0):
        db.add(AskLog(user_id=me.id, school_id=me.school_id, book_id=book.id,
                      section=body.section, question=q[:500],
                      answered=answered, refused_why=why, tokens=tokens))
        db.commit()

    # 1 · nothing to do with this page. Refused, and it costs them nothing —
    #     otherwise the quota gets spent finding out where the edges are.
    if not on_topic(q, body.passage):
        log(False, "off_topic")
        return {"answered": False, "counted": False,
                "answer": "That is not something this page is about, so I cannot "
                          "answer it from here. Try asking about what you are "
                          "reading. This did not use one of your questions.",
                **quota(db, me)}

    qu = quota(db, me)
    if qu["left"] <= 0:
        log(False, "over_cap")
        return {"answered": False, "counted": False,
                "answer": f"You have used all {qu['cap']} questions for today. "
                          "They come back tomorrow. Tapping a highlighted word "
                          "still works as much as you like.",
                **qu}

    school = db.get(School, me.school_id) if me.school_id else None
    if school and school.ask_pool_used >= school.ask_pool:
        log(False, "pool_empty")
        return {"answered": False, "counted": False,
                "answer": "Your school has used all its questions for this month. "
                          "Your teacher can ask EduVerse for more. Tapping a "
                          "highlighted word still works.",
                **qu}

    # 2 · a real answer, from this passage only. The model is given the
    #     paragraph the student is looking at and told to answer from it — so
    #     an answer can never wander off into something the book never said.
    try:
        cfg = ai_settings(db)
        text = explain(cfg["provider"], cfg["model"],
                       term=q, book={"title": book.title},
                       chapter=body.section,
                       paragraph=body.passage[:2000],
                       depth="question",
                       rules={"answer_only_from_passage": True},
                       api_key=cfg.get("api_key"), base_url=cfg.get("endpoint"))
        tokens = len(body.passage) // 4 + len(text) // 4
    except Exception:
        log(False, "error")
        return {"answered": False, "counted": False,
                "answer": "Something went wrong asking that. Try again in a "
                          "moment — this did not use one of your questions.",
                **qu}

    if school:
        school.ask_pool_used += 1
    log(True, "", tokens)
    return {"answered": True, "counted": True, "answer": text, **quota(db, me)}


@router.get("/log")
def my_log(db: Session = Depends(get_db), me=Depends(student)):
    """A student can see what they asked. So can their teacher — knowing the
    questions are visible is itself part of what keeps them sensible."""
    rows = db.query(AskLog).filter(AskLog.user_id == me.id).order_by(
        AskLog.at.desc()).limit(50).all()
    return [{"question": r.question, "answered": r.answered,
             "why": r.refused_why, "at": r.at} for r in rows]
