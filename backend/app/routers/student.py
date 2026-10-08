"""Student API: home, store, the book reader and reading progress. Only published (live) books with content can be opened."""
from datetime import datetime, timedelta, date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User, Book, ClassBook, Purchase, StudentProgress, StudentDay, UsageEvent, Setting, School
from ..security import require
from ..audit import log
from ..defaults import FEATURES, AI
from .. import content as C

router = APIRouter(prefix="/api/student", tags=["student"])
student = require("student")
DEPTHS = ["exam", "concept_clarity", "curiosity", "research"]


def owned_ids(db, me: User) -> dict:
    ids = {}
    if me.class_id:
        for cb in db.query(ClassBook).filter(ClassBook.class_id == me.class_id):
            ids[cb.book_id] = "school"
    for p in db.query(Purchase).filter(Purchase.user_id == me.id, Purchase.status.in_(("demo", "paid"))):
        ids.setdefault(p.book_id, "bought")
    return ids


def feature(db, key):
    s = db.get(Setting, "features")
    return (s.value if s else FEATURES).get(key, False)


def book_card(b: Book, prog=None, how=None):
    return {"id": b.id, "title": b.title, "subject": b.subject, "board": b.board, "grade": b.grade, "medium": b.medium,
            "edition": b.edition, "price": b.price, "status": b.status, "readable": b.status == "live" and bool(b.content_key),
            "owned": how, "progress": round(prog.percent) if prog else 0, "minutes": prog.minutes if prog else 0,
            "last_read": prog.last_read if prog else None, "position": prog.position if prog else {}}


def rules_for(db, me: User):
    ai = (db.get(Setting, "ai").value if db.get(Setting, "ai") else AI)
    school = db.get(School, me.school_id) if me.school_id else None
    r = (school.rules or {}) if school else {}
    allowed = r.get("allowed_depths") or DEPTHS
    cap = min(r.get("daily_explanations", ai.get("daily_explanations_per_student", 100)), ai.get("daily_explanations_per_student", 100))
    today = date.today().isoformat()
    exam = None
    for w in r.get("exam_windows", []):
        if w.get("start", "") <= today <= w.get("end", "") and (not w.get("class_ids") or me.class_id in w["class_ids"]):
            exam = w.get("name") or "Exam"
    return {"allowed_depths": ["exam"] if exam else allowed, "daily_limit": cap, "exam_mode": exam}


def day_row(db, uid):
    k = date.today().isoformat()
    r = db.get(StudentDay, (uid, k))
    if not r:
        r = StudentDay(user_id=uid, day=k, seconds=0, explanations=0); db.add(r); db.flush()
    return r


@router.get("/home")
def home(db: Session = Depends(get_db), me=Depends(student)):
    ids = owned_ids(db, me)
    prog = {p.book_id: p for p in db.query(StudentProgress).filter(StudentProgress.user_id == me.id)}
    books = db.query(Book).filter(Book.id.in_(list(ids))).all() if ids else []
    mine = [book_card(b, prog.get(b.id), ids[b.id]) for b in books if b.status == "live"]
    mine.sort(key=lambda x: (x["last_read"] is None, -(x["last_read"].timestamp() if x["last_read"] else 0), x["title"]))
    days = {r.day: r for r in db.query(StudentDay).filter(StudentDay.user_id == me.id, StudentDay.day >= (date.today() - timedelta(days=13)).isoformat())}
    week = [(date.today() - timedelta(days=6 - i)).isoformat() for i in range(7)]
    streak, d = 0, date.today()
    while days.get(d.isoformat()) and days[d.isoformat()].seconds > 0:
        streak += 1; d -= timedelta(days=1)
    upcoming = db.query(Book).filter(Book.status == "upcoming", Book.grade == (me.klass.grade if me.klass else Book.grade)).limit(6).all() if feature(db, "upcoming_books") else []
    return {"me": {"name": me.name, "school": me.school.name if me.school else "", "class": (f"Class {me.klass.grade}{(' ' + me.klass.section) if me.klass.section else ''}" if me.klass else ""),
                   "board": me.school.board if me.school else "", "grade": me.klass.grade if me.klass else ""},
            "books": mine, "continue": next((b for b in mine if b["last_read"] and b["readable"]), None),
            "week": [{"day": k, "minutes": round((days[k].seconds if k in days else 0) / 60), "explanations": days[k].explanations if k in days else 0} for k in week],
            "streak": streak, "total_minutes": sum(p.minutes for p in prog.values()),
            "upcoming": [book_card(b) for b in upcoming], "rules": rules_for(db, me), "store_on": feature(db, "student_store")}


@router.get("/store")
def store(board: str = "", grade: str = "", db: Session = Depends(get_db), me=Depends(student)):
    if not feature(db, "student_store"):
        raise HTTPException(403, "The store is turned off")
    ids = owned_ids(db, me)
    q = db.query(Book).filter(Book.status.in_(("live", "upcoming")))
    if board: q = q.filter(Book.board == board)
    if grade: q = q.filter(Book.grade == grade)
    boards = sorted({b for (b,) in db.query(Book.board).filter(Book.status.in_(("live", "upcoming"))).distinct() if b})
    grades = sorted({g for (g,) in db.query(Book.grade).filter(Book.status.in_(("live", "upcoming"))).distinct() if g}, key=lambda g: (not g.isdigit(), int(g) if g.isdigit() else 0, g))
    return {"boards": boards, "grades": grades,
            "books": [book_card(b, how=ids.get(b.id)) for b in q.order_by(Book.grade, Book.subject).all()]}


class BuyIn(BaseModel):
    book_id: int


@router.post("/purchase")
def purchase(body: BuyIn, db: Session = Depends(get_db), me=Depends(student)):
    b = db.get(Book, body.book_id)
    if not b or b.status != "live":
        raise HTTPException(409, "This book is not available to buy yet")
    if body.book_id in owned_ids(db, me):
        raise HTTPException(409, "You already have this book")
    db.add(Purchase(user_id=me.id, book_id=b.id, price=b.price, status="demo"))
    log(db, me, "student.purchase", "book", b.id, title=b.title, price=b.price, status="demo")
    db.commit()
    return {"ok": True, "note": "Recorded as a demo purchase. No payment was taken; the payment gateway is not connected yet."}


def readable_book(db, me, bid) -> Book:
    b = db.get(Book, bid)
    if not b or b.status != "live":
        raise HTTPException(404, "Book not available")
    if bid not in owned_ids(db, me):
        raise HTTPException(403, "Get this book from the store first")
    if not b.content_key:
        raise HTTPException(409, "This book is still being prepared")
    return b


@router.get("/books/{bid}")
def read_book(bid: int, db: Session = Depends(get_db), me=Depends(student)):
    b = readable_book(db, me, bid)
    data = C.load(b)
    p = db.get(StudentProgress, (me.id, bid))
    return {"id": b.id, "title": b.title, "board": b.board, "grade": b.grade, "subject": b.subject, "book": data["book"], "toc": data["toc"],
            "chapters": data["chapters"], "progress": {"percent": round(p.percent) if p else 0, "sections": p.sections if p else [], "position": p.position if p else {}},
            "rules": rules_for(db, me)}


class ProgressIn(BaseModel):
    chapter: int
    section: str
    seconds: int = 0


@router.post("/books/{bid}/progress")
def progress(bid: int, body: ProgressIn, db: Session = Depends(get_db), me=Depends(student)):
    b = readable_book(db, me, bid)
    secs = max(0, min(body.seconds, 300))  # at most 5 minutes per ping
    data = C.load(b)
    total = sum(1 for ch in data["chapters"] for s in ch["sections"] if s["number"])
    p = db.get(StudentProgress, (me.id, bid))
    first_today = not p or not p.last_read or p.last_read.date() != datetime.utcnow().date()
    if not p:
        p = StudentProgress(user_id=me.id, book_id=bid, percent=0, minutes=0, explanations=0, sections=[], position={}); db.add(p)
    seen = set(p.sections or [])
    if body.section and "-s" in body.section:
        seen.add(body.section)
    p.sections = sorted(seen)
    p.percent = min(100.0, len(seen) / max(1, total) * 100)
    d = day_row(db, me.id); d.seconds += secs
    total_secs = (p.position or {}).get("seconds", (p.minutes or 0) * 60) + secs
    p.minutes = total_secs // 60
    p.last_read, p.position = datetime.utcnow(), {"chapter": body.chapter, "section": body.section, "seconds": total_secs}
    # school analytics roll up
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    ev = db.query(UsageEvent).filter(UsageEvent.day == today, UsageEvent.school_id == me.school_id, UsageEvent.book_id == bid).first()
    if not ev:
        ev = UsageEvent(day=today, school_id=me.school_id, book_id=bid, active_students=0, reading_minutes=0, explanations=0, llm_tokens=0); db.add(ev)
    if first_today:
        ev.active_students += 1
    ev.reading_minutes += round(secs / 60)
    db.commit()
    return {"percent": round(p.percent), "sections": p.sections}


def count_explanation(db, me, book_id=None, tokens=0):
    d = day_row(db, me.id); d.explanations += 1
    if book_id:
        p = db.get(StudentProgress, (me.id, book_id))
        if p: p.explanations = (p.explanations or 0) + 1
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        ev = db.query(UsageEvent).filter(UsageEvent.day == today, UsageEvent.school_id == me.school_id, UsageEvent.book_id == book_id).first()
        if ev:
            ev.explanations += 1; ev.llm_tokens += tokens
