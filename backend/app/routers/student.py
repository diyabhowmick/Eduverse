"""Student API: home, store, the book reader and reading progress. Only published (live) books with content can be opened."""
from datetime import datetime, timedelta, date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User, Book, QuestionPaper, ClassBook, Purchase, StudentProgress, StudentDay, UsageEvent, Setting, School
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
    track = b.track or "textbook"
    return {"id": b.id, "title": b.title, "subject": b.subject, "board": b.board, "grade": b.grade, "medium": b.medium,
            "track": track, "level": b.level or "school", "exam": b.exam, "university": b.university, "course": b.course, "semester": b.semester,
            "edition": b.edition, "price": b.price, "status": "live" if C.serving(b) else b.status, "content_type": b.content_type or "book",
            "cover": f"/api/books/{b.id}/cover" if b.cover_key else "",
            "readable": C.serving(b) and (track == "exam" or bool(C.reader_key(b))),
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
    mine = [book_card(b, prog.get(b.id), ids[b.id]) for b in books if C.serving(b)]
    mine.sort(key=lambda x: (x["last_read"] is None, -(x["last_read"].timestamp() if x["last_read"] else 0), x["title"]))
    days = {r.day: r for r in db.query(StudentDay).filter(StudentDay.user_id == me.id, StudentDay.day >= (date.today() - timedelta(days=13)).isoformat())}
    week = [(date.today() - timedelta(days=6 - i)).isoformat() for i in range(7)]
    streak, d = 0, date.today()
    while days.get(d.isoformat()) and days[d.isoformat()].seconds > 0:
        streak += 1; d -= timedelta(days=1)
    prof = me.profile or {}
    grade = me.klass.grade if me.klass else prof.get("grade", "")
    uq = db.query(Book).filter(Book.status == "upcoming")
    if grade:
        uq = uq.filter(Book.grade == grade)
    upcoming = uq.limit(6).all() if feature(db, "upcoming_books") else []
    return {"me": {"name": me.name, "school": me.school.name if me.school else "", "individual": not me.school_id,
                   "class": (f"Class {me.klass.grade}{(' ' + me.klass.section) if me.klass.section else ''}" if me.klass else (f"Class {grade}" if grade else "")),
                   "board": (me.school.board if me.school else prof.get("board", "")), "grade": grade, "profile": prof},
            "books": mine, "continue": next((b for b in mine if b["last_read"] and b["readable"]), None),
            "week": [{"day": k, "minutes": round((days[k].seconds if k in days else 0) / 60), "explanations": days[k].explanations if k in days else 0} for k in week],
            "streak": streak, "total_minutes": sum(p.minutes for p in prog.values()),
            "upcoming": [book_card(b) for b in upcoming], "rules": rules_for(db, me), "store_on": feature(db, "student_store"),
            "goal_minutes": int(prof.get("goal_minutes") or 20), "exam_date": prof.get("exam_date") or "",
            "today_minutes": round((days[date.today().isoformat()].seconds if date.today().isoformat() in days else 0) / 60),
            "today_questions": _today_questions(db, me), "practice": weak_chapters(db, me), "last_exam": _last_exam(db, me, mine),
            **_tests_home(db, me, mine, prog)}


def _tests_home(db, me, mine, prog):
    """The chapter test Eddie suggests next, and the last one taken, for the Home plan."""
    from ..models import ChapterAttempt
    from .tests import counts
    last = db.query(ChapterAttempt).filter(ChapterAttempt.user_id == me.id, ChapterAttempt.finished_at.isnot(None), ChapterAttempt.level != "daily").order_by(ChapterAttempt.finished_at.desc()).first()
    nxt = None
    for b in mine:
        if b["track"] == "exam" or not b["readable"]:
            continue
        n = counts(db, b["id"])
        ch = ((prog.get(b["id"]).position or {}) if prog.get(b["id"]) else {}).get("chapter")
        ch = ch if ch in n else next(iter(sorted(n)), None)
        if ch is None:
            continue
        done = db.query(ChapterAttempt).filter(ChapterAttempt.user_id == me.id, ChapterAttempt.book_id == b["id"], ChapterAttempt.chapter == ch,
                                              ChapterAttempt.finished_at >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)).first()
        try:
            bk = db.get(Book, b["id"]); title = next((c["title"] for c in C.load(bk, C.reader_key(bk))["chapters"] if c["number"] == ch), "")
        except Exception:
            title = ""
        nxt = {"book_id": b["id"], "book_title": b["title"], "chapter": ch, "chapter_title": title, "count": n[ch], "done_today": bool(done)}
        break
    from .tests import daily_status
    from .. import memory as M
    mem = M.summary(db, me.id)
    from .study import summary as _rev
    return {"revise": _rev(db, me.id), "daily": daily_status(db, me), "memory": {**mem, "for_eddie": M.for_eddie(mem)}, "test_next": nxt, "last_test": {"id": last.id, "score": last.score, "total": last.total, "chapter": last.chapter, "book_id": last.book_id,
                                            "untaught": len([q for q in (last.wrong or []) if q not in (last.taught or [])])} if last else None}


def _today_questions(db, me):
    from ..models import QuestionProgress
    start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return db.query(QuestionProgress).filter(QuestionProgress.user_id == me.id, QuestionProgress.updated >= start, QuestionProgress.status != "").count()


def _last_exam(db, me, mine):
    """The exam pack the student worked on most recently, for the Continue card."""
    from ..models import QuestionProgress, MockAttempt
    packs = {b["id"]: b for b in mine if b["track"] == "exam"}
    if not packs:
        return None
    p = db.query(QuestionProgress).filter(QuestionProgress.user_id == me.id, QuestionProgress.book_id.in_(list(packs))).order_by(QuestionProgress.updated.desc()).first()
    a = db.query(MockAttempt).filter(MockAttempt.user_id == me.id, MockAttempt.book_id.in_(list(packs))).order_by(MockAttempt.started_at.desc()).first()
    when = [(x.updated, x.book_id) for x in [p] if x] + [(x.started_at, x.book_id) for x in [a] if x]
    bid = max(when)[1] if when else next(iter(packs))
    return {**packs[bid], "practised": db.query(QuestionProgress).filter(QuestionProgress.user_id == me.id, QuestionProgress.book_id == bid, QuestionProgress.status != "").count()}


@router.get("/progress")
def progress_page(db: Session = Depends(get_db), me=Depends(student)):
    """Everything the Progress page shows: reading time, books, tests, and strong and weak chapters."""
    from ..models import QuestionProgress, Question, MockAttempt
    days = {r.day: r for r in db.query(StudentDay).filter(StudentDay.user_id == me.id, StudentDay.day >= (date.today() - timedelta(days=29)).isoformat())}
    month = [(date.today() - timedelta(days=29 - i)).isoformat() for i in range(30)]
    ids = owned_ids(db, me)
    prog = {p.book_id: p for p in db.query(StudentProgress).filter(StudentProgress.user_id == me.id)}
    books = [book_card(b, prog.get(b.id), ids[b.id]) for b in db.query(Book).filter(Book.id.in_(list(ids) or [0]), C.serving_filter())]
    tests = db.query(MockAttempt).filter(MockAttempt.user_id == me.id, MockAttempt.submitted_at.isnot(None)).order_by(MockAttempt.submitted_at.desc()).limit(20).all()
    rows = db.query(QuestionProgress, Question).join(Question, Question.id == QuestionProgress.question_id).filter(QuestionProgress.user_id == me.id).all()
    from .exams import subject_of
    chap, subj = {}, {}
    for p, q in rows:
        if p.status not in ("correct", "wrong"):
            continue
        for agg, k in ((chap, (p.book_id, q.chapter or "Not tagged")), (subj, subject_of(q.section))):
            a = agg.setdefault(k, [0, 0]); a[0] += p.status == "correct"; a[1] += 1
    titles = {b["id"]: b["title"] for b in books}
    chapters = sorted([{"pack": titles.get(b, ""), "book_id": b, "chapter": c, "right": r, "tried": n, "accuracy": round(r / n * 100)} for (b, c), (r, n) in chap.items()],
                      key=lambda x: (x["accuracy"], -x["tried"]))
    streak, d = 0, date.today()
    while days.get(d.isoformat()) and days[d.isoformat()].seconds > 0:
        streak += 1; d -= timedelta(days=1)
    return {"days": [{"day": k, "minutes": round((days[k].seconds if k in days else 0) / 60)} for k in month], "streak": streak,
            "total_minutes": sum(p.minutes or 0 for p in prog.values()), "books": books,
            "tests": [{"id": a.id, "title": a.title, "when": a.submitted_at, "score": a.score, "total": a.total, "pct": round(max(0, a.score) / a.total * 100) if a.total else None,
                       "questions": len(a.question_ids), "time_taken": a.time_taken} for a in tests],
            "chapters": chapters, "subjects": [{"subject": s, "right": r, "tried": n, "accuracy": round(r / n * 100)} for s, (r, n) in sorted(subj.items())],
            "practised": sum(1 for p, _ in rows if p.status), "correct": sum(1 for p, _ in rows if p.status == "correct"), "saved": sum(1 for p, _ in rows if p.bookmarked)}


@router.get("/store")
def store(track: str = "textbook", level: str = "", board: str = "", grade: str = "", exam: str = "", university: str = "",
          db: Session = Depends(get_db), me=Depends(student)):
    """The store has two shelves. Textbooks: by board (CBSE, ICSE, each state) and class, or by university for degree.
    Exam preparation: board exams, degree exams and competitive exams such as JEE and NEET."""
    if not feature(db, "student_store"):
        raise HTTPException(403, "The store is turned off")
    if track == "exam" and not feature(db, "exam_track"):
        raise HTTPException(403, "Exam preparation is turned off")
    ids = owned_ids(db, me)
    from sqlalchemy import or_
    base = db.query(Book).filter(or_(C.serving_filter(), Book.status == "upcoming"))
    base = base.filter(Book.track == track) if track == "exam" else base.filter((Book.track == "textbook") | (Book.track.is_(None)))
    shelf = base.filter(Book.level == level) if level else base
    def vals(col, q=shelf):
        return sorted({v for (v,) in q.with_entities(col).distinct() if v})
    q = shelf
    if board: q = q.filter(Book.board == board)
    if grade: q = q.filter(Book.grade == grade)
    if exam: q = q.filter(Book.exam == exam)
    if university: q = q.filter(Book.university == university)
    grades = sorted(vals(Book.grade), key=lambda g: (not g.isdigit(), int(g) if g.isdigit() else 0, g))
    return {"track": track, "levels": vals(Book.level, base), "boards": vals(Book.board), "grades": grades, "exams": vals(Book.exam),
            "universities": vals(Book.university),
            "books": [book_card(b, how=ids.get(b.id)) for b in q.order_by(Book.level, Book.board, Book.grade, Book.subject).all()]}


@router.get("/store/segments")
def store_segments(db: Session = Depends(get_db), me=Depends(student)):
    """The store's first screen: every board, exam and university that has something on its shelf, with counts."""
    if not feature(db, "student_store"):
        raise HTTPException(403, "The store is turned off")
    from sqlalchemy import or_
    from collections import defaultdict
    rows = db.query(Book).filter(or_(C.serving_filter(), Book.status == "upcoming")).all()
    boards, exams, unis = defaultdict(lambda: {"books": 0, "grades": set(), "subjects": set(), "upcoming": 0}), defaultdict(lambda: {"packs": 0, "level": ""}), defaultdict(int)
    for b in rows:
        track, level = b.track or "textbook", b.level or "school"
        if track == "exam":
            if feature(db, "exam_track") and b.exam:
                exams[b.exam]["packs"] += 1; exams[b.exam]["level"] = level
        elif level == "degree" and b.university:
            unis[b.university] += 1
        elif b.board:
            g = boards[b.board]
            g["books"] += 1; g["upcoming"] += b.status == "upcoming"
            if b.grade: g["grades"].add(b.grade)
            if b.subject: g["subjects"].add(b.subject)
    key = lambda g: (not g.isdigit(), int(g) if g.isdigit() else 0, g)
    return {"boards": [{"board": k, "books": v["books"], "upcoming": v["upcoming"], "grades": sorted(v["grades"], key=key), "subjects": sorted(v["subjects"])[:6]}
                       for k, v in sorted(boards.items(), key=lambda kv: -kv[1]["books"])],
            "exams": [{"exam": k, **v} for k, v in sorted(exams.items(), key=lambda kv: -kv[1]["packs"])],
            "universities": [{"university": k, "books": n} for k, n in sorted(unis.items(), key=lambda kv: -kv[1])]}


@router.get("/store/books/{bid}")
def store_book(bid: int, db: Session = Depends(get_db), me=Depends(student)):
    """What the back of a book shows: its chapters, or for an exam pack the years of papers inside."""
    b = db.get(Book, bid)
    if not b or not (C.serving(b) or b.status == "upcoming"):
        raise HTTPException(404, "Book not found")
    out = book_card(b, how=owned_ids(db, me).get(b.id))
    out["pages"] = b.pages
    if (b.track or "textbook") == "exam":
        papers = db.query(QuestionPaper).filter(QuestionPaper.book_id == b.id, QuestionPaper.status == "approved").order_by(QuestionPaper.year.desc()).all()
        out["years"] = sorted({p.year for p in papers if p.year}, reverse=True)
        out["papers"] = len(papers)
    else:
        try:
            chs = C.load(b, C.reader_key(b)).get("chapters", []) if C.reader_key(b) else []
        except Exception:
            chs = []
        out["chapters"] = [{"number": c.get("number"), "title": c.get("title", "")} for c in chs][:40]
    return out


# ---------------- the learner's own data: a copy on request, and a way to ask for it to be deleted ----------------
@router.get("/me/data")
def my_data(db: Session = Depends(get_db), me=Depends(student)):
    """Everything EduVerse holds about this learner, as one file they can keep."""
    from ..models import ExplanationVote, StudentDay, Note, SavedExplanation, Mistake
    log(db, me, "student.data_export", "user", me.id); db.commit()
    return {"account": {"name": me.name, "email": me.email, "phone": me.phone, "created_at": me.created_at, "last_login": me.last_login,
                        "organisation": me.school.name if me.school else "", "profile": me.profile or {}},
            "purchases": [{"book_id": p.book_id, "price": p.price, "status": p.status, "at": p.created_at} for p in db.query(Purchase).filter(Purchase.user_id == me.id)],
            "progress": [{"book_id": p.book_id, "percent": p.percent, "minutes": p.minutes, "last_read": p.last_read} for p in db.query(StudentProgress).filter(StudentProgress.user_id == me.id)],
            "study_days": [{"day": d.day, "minutes": round((d.seconds or 0) / 60), "explanations": d.explanations} for d in db.query(StudentDay).filter(StudentDay.user_id == me.id)],
            "votes": [{"explanation_id": v.explanation_id, "value": v.value, "at": v.at} for v in db.query(ExplanationVote).filter(ExplanationVote.user_id == me.id)],
            "notes": [{"kind": n.kind, "book_id": n.book_id, "chapter": n.chapter, "quote": n.quote, "body": n.body, "tags": n.tags, "transcript": n.transcript,
                       "voice_note": bool(n.audio_key), "at": n.created_at} for n in db.query(Note).filter(Note.user_id == me.id)],
            "saved_explanations": [{"explanation_id": x.explanation_id, "path": x.path, "at": x.created_at} for x in db.query(SavedExplanation).filter(SavedExplanation.user_id == me.id)],
            "mistakes": [{"question": f"{m.qsource}:{m.question_id}", "topic": m.topic, "my_answer": m.my_answer, "wrong": m.wrong_count, "not_sure": m.not_sure,
                          "status": m.status} for m in db.query(Mistake).filter(Mistake.user_id == me.id)]}


@router.post("/me/delete-request")
def delete_request(db: Session = Depends(get_db), me=Depends(student)):
    """Records the request. The Super Admin completes it from the audit log; an organisation's student is
    handled with their organisation, which owns that account."""
    prof = dict(me.profile or {}); prof["deletion_requested_at"] = datetime.utcnow().isoformat(timespec="seconds")
    me.profile = prof
    log(db, me, "student.delete_request", "user", me.id, organisation=me.school.name if me.school else "")
    db.commit()
    return {"ok": True, "message": "Your request is recorded. Your account and data will be deleted within 30 days, and you will get an email when it is done."}


class ProfileIn(BaseModel):
    track: str | None = None
    level: str | None = None
    board: str | None = None
    grade: str | None = None
    exam: str | None = None
    university: str | None = None
    course: str | None = None
    goal_minutes: int | None = None   # daily reading or practice goal
    nickname: str | None = None       # what Eddie calls the student
    exam_date: str | None = None      # YYYY-MM-DD, for the countdown on Home


@router.put("/profile")
def set_profile(body: ProfileIn, db: Session = Depends(get_db), me=Depends(student)):
    """What an individual learner is studying, their daily goal and exam date. Only the fields sent are changed."""
    ch = body.model_dump(exclude_unset=True)
    if "goal_minutes" in ch and ch["goal_minutes"] is not None and not 5 <= ch["goal_minutes"] <= 600:
        raise HTTPException(422, "Pick a goal between 5 and 600 minutes")
    if ch.get("exam_date"):
        try:
            date.fromisoformat(ch["exam_date"])
        except ValueError:
            raise HTTPException(422, "Exam date must look like 2027-01-24")
    if ch.get("nickname") is not None:
        ch["nickname"] = " ".join(ch["nickname"].split())[:30]
    me.profile = {**(me.profile or {}), **{k: (v.strip() if isinstance(v, str) else v) for k, v in ch.items()}}
    db.commit()
    return me.profile


def weak_chapters(db, me, limit=3):
    """Chapters where this student's practice and test answers are weakest, from at least three tries."""
    from ..models import QuestionProgress, Question
    rows = db.query(QuestionProgress, Question).join(Question, Question.id == QuestionProgress.question_id) \
        .filter(QuestionProgress.user_id == me.id, QuestionProgress.status.in_(("correct", "wrong"))).all()
    agg = {}
    for p, q in rows:
        k = (p.book_id, q.chapter or "")
        a = agg.setdefault(k, [0, 0]); a[0] += p.status == "correct"; a[1] += 1
    titles = {b.id: b.title for b in db.query(Book).filter(Book.id.in_({k[0] for k in agg} or {0}))}
    out = [{"book_id": b, "pack": titles.get(b, ""), "chapter": ch, "right": r, "tried": n, "accuracy": round(r / n * 100)} for (b, ch), (r, n) in agg.items() if n >= 3 and ch]
    return sorted(out, key=lambda x: (x["accuracy"], -x["tried"]))[:limit]


class BuyIn(BaseModel):
    book_id: int


@router.post("/purchase")
def purchase(body: BuyIn, db: Session = Depends(get_db), me=Depends(student)):
    b = db.get(Book, body.book_id)
    if not b or not C.serving(b):
        raise HTTPException(409, "This book is not available to buy yet")
    if body.book_id in owned_ids(db, me):
        raise HTTPException(409, "You already have this book")
    db.add(Purchase(user_id=me.id, book_id=b.id, price=b.price, status="demo"))
    log(db, me, "student.purchase", "book", b.id, title=b.title, price=b.price, status="demo")
    db.commit()
    return {"ok": True, "note": "Recorded as a demo purchase. No payment was taken; the payment gateway is not connected yet."}


def test_counts(db, bid):
    from .tests import counts
    return counts(db, bid)


def readable_book(db, me, bid) -> Book:
    b = db.get(Book, bid)
    if not b or not C.serving(b):
        raise HTTPException(404, "Book not available")
    if b.track == "exam":
        raise HTTPException(409, "This is an exam pack. Open it from My books.")
    if bid not in owned_ids(db, me):
        raise HTTPException(403, "Get this book from the store first")
    if not C.reader_key(b):
        raise HTTPException(409, "This book is still being prepared")
    return b


@router.get("/books/{bid}")
def read_book(bid: int, db: Session = Depends(get_db), me=Depends(student)):
    b = readable_book(db, me, bid)
    data = C.load(b, C.reader_key(b))
    p = db.get(StudentProgress, (me.id, bid))
    packs = [x for x in db.query(Book).filter(Book.track == "exam", Book.status == "live") if bid in (x.linked_book_ids or [])]
    return {"practice_packs": [{"id": x.id, "title": x.title, "owned": x.id in owned_ids(db, me)} for x in packs],
            "id": b.id, "title": b.title, "board": b.board, "grade": b.grade, "subject": b.subject, "book": data["book"], "toc": data["toc"],
            "chapters": data["chapters"], "progress": {"percent": round(p.percent) if p else 0, "sections": p.sections if p else [], "position": p.position if p else {}},
            "rules": rules_for(db, me), "tests": test_counts(db, bid)}


class ProgressIn(BaseModel):
    chapter: int
    section: str
    seconds: int = 0


@router.post("/books/{bid}/progress")
def progress(bid: int, body: ProgressIn, db: Session = Depends(get_db), me=Depends(student)):
    b = readable_book(db, me, bid)
    secs = max(0, min(body.seconds, 300))  # at most 5 minutes per ping
    data = C.load(b, C.reader_key(b))
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
