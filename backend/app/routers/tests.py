"""Chapter tests: reviewers generate and approve questions; students take tests; Eddie teaches back."""
import os, random
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Book, ChapterAttempt, ChapterQuestion
from ..security import require
from ..audit import log
from .. import content as C
from .. import chapter_tests as T
from .. import explain_store as X
from .. import memory as M
from datetime import date, timedelta

reviewer = require("reviewer", "super_admin")
student = require("student")
router = APIRouter(prefix="/api/review/tests", tags=["chapter-tests"])
srouter = APIRouter(prefix="/api/student", tags=["chapter-tests"])
LEVELS = {"quick": 5, "chapter": 15}


def q_out(q: ChapterQuestion, answers=True) -> dict:
    d = {"id": q.id, "chapter": q.chapter, "section": q.section, "section_title": q.section_title, "qtype": q.qtype, "level": q.level,
         "text": q.text, "options": q.options or [], "figure": q.figure or {}}
    if answers:
        d.update(answer=q.answer, explanation=q.explanation, source=q.source, status=q.status, origin=q.origin, reviewed_by=q.reviewed_by)
    return d


def _book(db, bid) -> Book:
    b = db.get(Book, bid)
    if not b or not (b.content_key or b.live_key):
        raise HTTPException(404, "Book not found")
    return b


def _content(b: Book):
    return C.load(b, b.content_key or b.live_key)


# ---------------- reviewer ----------------
@router.get("")
def books(db: Session = Depends(get_db), me=Depends(reviewer)):
    out = []
    for b in db.query(Book).filter(Book.track != "exam").order_by(Book.id.desc()):
        if not (b.content_key or b.live_key):
            continue
        qs = db.query(ChapterQuestion.status).filter(ChapterQuestion.book_id == b.id).all()
        out.append({"id": b.id, "title": b.title, "board": b.board, "grade": b.grade, "subject": b.subject, "status": b.status,
                    "approved": sum(1 for (s,) in qs if s == "approved"), "draft": sum(1 for (s,) in qs if s == "draft")})
    return out


@router.get("/{bid}")
def book_tests(bid: int, db: Session = Depends(get_db), me=Depends(reviewer)):
    b = _book(db, bid); data = _content(b)
    qs = db.query(ChapterQuestion).filter(ChapterQuestion.book_id == bid, ChapterQuestion.status != "rejected").order_by(ChapterQuestion.chapter, ChapterQuestion.id).all()
    chs = [{"number": c["number"], "title": c["title"], "questions": [q_out(q) for q in qs if q.chapter == c["number"]]} for c in data["chapters"]]
    return {"id": b.id, "title": b.title, "board": b.board, "grade": b.grade, "subject": b.subject, "chapters": chs,
            "ai": (os.getenv("AI_PROVIDER_OVERRIDE") or X.ai_conf(db)["provider"]) != "mock"}


class GenIn(BaseModel):
    chapter: int | None = None
    use_ai: bool = True


@router.post("/{bid}/generate")
def generate(bid: int, body: GenIn, db: Session = Depends(get_db), me=Depends(reviewer)):
    """Write draft questions for one chapter or the whole book. Drafts are replaced; approved questions are kept."""
    b = _book(db, bid); data = _content(b)
    chs = [c for c in data["chapters"] if body.chapter is None or c["number"] == body.chapter]
    if not chs:
        raise HTTPException(404, "No such chapter")
    ai = X.ai_conf(db); provider = os.getenv("AI_PROVIDER_OVERRIDE") or ai["provider"]
    made, method, note = 0, "rules", ""
    for ch in chs:
        qs = []
        if body.use_ai and provider != "mock":
            try:
                from ..llm_client import call
                pv = ai["providers"].get(provider, {})
                usage = {}
                raw = call(provider, pv["model"], T.ai_prompt(b, ch), base_url=pv.get("base_url"), api_key=pv.get("api_key") or None, timeout=180, json_mode=True, usage=usage, max_tokens=4000)
                X.record(db, "chapter_test", pv["model"], usage, me.id, b.id, False, f"Unit {ch['number']}", b.title)
                qs = T.from_ai(raw, ch); method = "ai"
            except Exception as e:  # the rules still give the chapter a test
                note = "The AI did not answer, so questions were written from the book's highlighted words and figures."
                import logging; logging.getLogger("eduverse.ai").warning("chapter test AI failed: %s", str(e)[:300])
        if not qs:
            qs = T.rules(data, ch["number"])
        db.query(ChapterQuestion).filter(ChapterQuestion.book_id == bid, ChapterQuestion.chapter == ch["number"], ChapterQuestion.status == "draft").delete()
        known = {T._norm(t) for (t,) in db.query(ChapterQuestion.text).filter(ChapterQuestion.book_id == bid, ChapterQuestion.chapter == ch["number"])}
        for q in qs:
            if T._norm(q["text"]) in known:
                continue
            db.add(ChapterQuestion(book_id=bid, chapter=ch["number"], origin="ai" if method == "ai" else "rules", status="draft",
                                   **{k: q.get(k, d) for k, d in (("section", ""), ("section_title", ""), ("qtype", "mcq"), ("level", "easy"), ("text", ""),
                                                                  ("options", []), ("answer", ""), ("explanation", ""), ("source", ""), ("figure", {}))}))
            made += 1
    log(db, me, "tests.generate", "book", bid, chapter=body.chapter, made=made, method=method)
    db.commit()
    return {"made": made, "method": method, "note": note}


class QIn(BaseModel):
    text: str
    options: list[dict] = []
    answer: str
    explanation: str = ""
    level: str = "easy"


class NewQ(QIn):
    chapter: int
    qtype: str = "mcq"


@router.post("/{bid}/questions")
def add(bid: int, body: NewQ, db: Session = Depends(get_db), me=Depends(reviewer)):
    """A reviewer writes a question of their own. It goes straight in as approved."""
    b = _book(db, bid); data = _content(b)
    if not any(c["number"] == body.chapter for c in data["chapters"]):
        raise HTTPException(404, "No such chapter")
    qtype = "fill" if body.qtype == "fill" or not body.options else "mcq"
    if not body.text.strip() or not body.answer.strip():
        raise HTTPException(422, "A question needs its text and an answer")
    if qtype == "mcq" and body.answer not in [o.get("key") for o in body.options]:
        raise HTTPException(422, "Pick which option is right")
    chap = next(c for c in data["chapters"] if c["number"] == body.chapter)
    first_sec = next((x["id"] for x in chap.get("sections", [])), "")
    q = ChapterQuestion(book_id=bid, chapter=body.chapter, section=first_sec, section_title=chap["title"].strip(), qtype=qtype, level=body.level if body.level in ("easy", "medium", "hard") else "medium",
                        text=body.text.strip(), options=body.options if qtype == "mcq" else [], answer=body.answer.strip(), explanation=body.explanation.strip(),
                        source=body.explanation.strip(), status="approved", origin="human", reviewed_by=me.email)
    db.add(q); log(db, me, "tests.add", "book", bid, chapter=body.chapter); db.commit()
    return q_out(q)


@router.put("/q/{qid}")
def edit(qid: int, body: QIn, db: Session = Depends(get_db), me=Depends(reviewer)):
    q = db.get(ChapterQuestion, qid)
    if not q:
        raise HTTPException(404, "Question not found")
    if not body.text.strip() or not body.answer.strip():
        raise HTTPException(422, "A question needs its text and an answer")
    if q.qtype in ("mcq", "figure") and body.answer not in [o.get("key") for o in body.options]:
        raise HTTPException(422, "Pick which option is right")
    q.text, q.options, q.answer, q.explanation = body.text.strip(), body.options, body.answer.strip(), body.explanation.strip()
    q.level = body.level if body.level in ("easy", "medium", "hard") else q.level
    q.origin = "human" if q.origin == "rules" else q.origin
    log(db, me, "tests.edit", "book", q.book_id, question=qid)
    db.commit()
    return q_out(q)


@router.post("/q/{qid}/{action}")
def act(qid: int, action: str, db: Session = Depends(get_db), me=Depends(reviewer)):
    q = db.get(ChapterQuestion, qid)
    if not q:
        raise HTTPException(404, "Question not found")
    st = {"approve": "approved", "reject": "rejected", "undo": "draft"}.get(action)
    if not st:
        raise HTTPException(422, "approve, reject or undo")
    q.status, q.reviewed_by = st, me.email
    log(db, me, "tests." + action, "book", q.book_id, question=qid)
    db.commit()
    return q_out(q)


@router.post("/{bid}/chapters/{ch}/approve-all")
def approve_all(bid: int, ch: int, db: Session = Depends(get_db), me=Depends(reviewer)):
    n = 0
    for q in db.query(ChapterQuestion).filter(ChapterQuestion.book_id == bid, ChapterQuestion.chapter == ch, ChapterQuestion.status == "draft"):
        q.status, q.reviewed_by = "approved", me.email; n += 1
    log(db, me, "tests.approve_all", "book", bid, chapter=ch, n=n)
    db.commit()
    return {"approved": n}


# ---------------- student ----------------
def counts(db, bid) -> dict:
    out = {}
    for (ch,) in db.query(ChapterQuestion.chapter).filter(ChapterQuestion.book_id == bid, ChapterQuestion.status == "approved"):
        out[ch] = out.get(ch, 0) + 1
    return out


def _mine(db, me, aid) -> ChapterAttempt:
    a = db.get(ChapterAttempt, aid)
    if not a or a.user_id != me.id:
        raise HTTPException(404, "Test not found")
    return a


@srouter.get("/books/{bid}/tests")
def my_tests(bid: int, db: Session = Depends(get_db), me=Depends(student)):
    from .student import readable_book
    readable_book(db, me, bid)
    att = db.query(ChapterAttempt).filter(ChapterAttempt.user_id == me.id, ChapterAttempt.book_id == bid, ChapterAttempt.finished_at.isnot(None)).all()
    out = {}
    for ch, n in counts(db, bid).items():
        mine = [a for a in att if a.chapter == ch]
        best = max(mine, key=lambda a: a.score / max(1, a.total), default=None)
        out[ch] = {"count": n, "best": round(best.score / max(1, best.total) * 100) if best else None, "tries": len(mine)}
    return out


class StartIn(BaseModel):
    level: str = "quick"
    ids: list[int] = []      # retry: exactly these questions


@srouter.post("/books/{bid}/tests/{ch}/start")
def start(bid: int, ch: int, body: StartIn, db: Session = Depends(get_db), me=Depends(student)):
    from .student import readable_book
    b = readable_book(db, me, bid)
    if body.ids:
        pool = db.query(ChapterQuestion).filter(ChapterQuestion.book_id == bid, ChapterQuestion.id.in_(body.ids), ChapterQuestion.status == "approved").all()
        pool.sort(key=lambda q: body.ids.index(q.id))
        level = "retry"
    else:
        pool = db.query(ChapterQuestion).filter(ChapterQuestion.book_id == bid, ChapterQuestion.chapter == ch, ChapterQuestion.status == "approved").all()
        level = body.level if body.level in LEVELS else "quick"
        rng = random.Random()
        rng.shuffle(pool)
        order = {"easy": 0, "medium": 1, "hard": 2}
        pool = sorted(pool[:LEVELS[level]], key=lambda q: order.get(q.level, 1))   # easy first, to warm up
    if not pool:
        raise HTTPException(404, "This chapter has no test yet")
    data = C.load(b, C.reader_key(b))
    title = next((c["title"] for c in data["chapters"] if c["number"] == ch), "")
    a = ChapterAttempt(user_id=me.id, book_id=bid, chapter=ch, level=level, question_ids=[q.id for q in pool], total=len(pool))
    db.add(a); db.commit()
    return {"id": a.id, "book_id": bid, "book_title": b.title, "chapter": ch, "chapter_title": title, "level": level,
            "questions": [q_out(q, answers=False) for q in pool]}


class SubmitIn(BaseModel):
    answers: dict[str, str] = {}
    seconds: int = 0


def result(db, a: ChapterAttempt) -> dict:
    b = db.get(Book, a.book_id)
    qs = {q.id: q for q in db.query(ChapterQuestion).filter(ChapterQuestion.id.in_(a.question_ids))}
    rows, secs = [], {}
    for qid in a.question_ids:
        q = qs.get(qid)
        if not q:
            continue
        given = (a.answers or {}).get(str(qid), "")
        ok = T.is_right(q, given)
        rows.append({**q_out(q), "your": given, "your_text": T.option_text(q, given) if given else "", "right_text": T.correct_text(q), "correct": ok})
        k = q.section_title or "This unit"
        s = secs.setdefault(k, {"title": k, "section": q.section, "right": 0, "total": 0}); s["total"] += 1; s["right"] += ok
    try:
        title = "Daily 5" if a.level == "daily" else next((c["title"] for c in C.load(b, C.reader_key(b))["chapters"] if c["number"] == a.chapter), "")
    except Exception:
        title = ""
    for r in rows:
        r["why"] = (a.reasons or {}).get(str(r["id"]), "")
    return {"id": a.id, "book_id": a.book_id, "book_title": b.title if b else "", "chapter": a.chapter, "chapter_title": title, "level": a.level,
            "score": a.score, "total": a.total, "seconds": a.seconds, "finished": bool(a.finished_at), "taught": a.taught or [], "fixed": a.fixed or [],
            "questions": rows, "by_section": list(secs.values())}


@srouter.post("/tests/{aid}/submit")
def submit(aid: int, body: SubmitIn, db: Session = Depends(get_db), me=Depends(student)):
    a = _mine(db, me, aid)
    if a.finished_at:
        return result(db, a)
    qs = {q.id: q for q in db.query(ChapterQuestion).filter(ChapterQuestion.id.in_(a.question_ids))}
    a.answers = {str(k): str(v)[:200] for k, v in body.answers.items() if int(k) in qs}
    a.wrong = [qid for qid in a.question_ids if qid in qs and not T.is_right(qs[qid], a.answers.get(str(qid), ""))]
    a.score = len(a.question_ids) - len(a.wrong)
    for qid in a.question_ids:
        if qid in qs:
            M.remember(db, me.id, qs[qid], a.answers.get(str(qid), ""), qid not in a.wrong)
    a.seconds = max(0, min(body.seconds, 6 * 3600))
    a.finished_at = datetime.utcnow()
    from .student import day_row
    day_row(db, me.id)  # the attempt counts as study today
    db.commit()
    return result(db, a)


@srouter.get("/tests/{aid}")
def get_attempt(aid: int, db: Session = Depends(get_db), me=Depends(student)):
    a = _mine(db, me, aid)
    if not a.finished_at:
        qs = {q.id: q for q in db.query(ChapterQuestion).filter(ChapterQuestion.id.in_(a.question_ids))}
        r = result(db, a)
        r["questions"] = [q_out(qs[i], answers=False) for i in a.question_ids if i in qs]
        return r
    return result(db, a)


class TeachIn(BaseModel):
    question_id: int
    reason: str = ""


@srouter.post("/tests/{aid}/teach")
def teach(aid: int, body: TeachIn, db: Session = Depends(get_db), me=Depends(student)):
    """Eddie goes through one wrong answer: why the student chose it, the exact mistake, and the book's own words."""
    a = _mine(db, me, aid)
    if not a.finished_at or body.question_id not in (a.question_ids or []):
        raise HTTPException(404, "Question not in this test")
    q = db.get(ChapterQuestion, body.question_id)
    given = (a.answers or {}).get(str(q.id), "")
    b = db.get(Book, a.book_id)
    provider = os.getenv("AI_PROVIDER_OVERRIDE") or X.ai_conf(db)["provider"]
    before = M.times_wrong(db, me.id, q.id) > 1
    text, ai = T.teach_rules(q, given, body.reason), False
    if before:
        text = "This one tripped you up before too, so let's really nail it this time. " + text
    if provider != "mock":
        from .learn import Credits
        credits = Credits(db, me)
        if credits.left() is None or credits.left() > 0:
            try:
                who = f"a Class {b.grade} {b.subject} student" if b else "a student"
                prompt = T.teach_prompt(q, given, body.reason, who) + ("\nThe student has got this same question wrong before, so mention that gently." if before else "")
                text, _m = X.generate(db, prompt, kind="teach", user_id=me.id, book_id=a.book_id, term=q.text[:120], where="Chapter test")
                credits.spend(a.book_id, text); ai = True
            except HTTPException:
                pass   # the book's own words still teach it
    if q.id not in (a.taught or []):
        a.taught = [*(a.taught or []), q.id]
    db.commit()
    return {"text": text.replace("$", ""), "ai": ai, "section": q.section, "chapter": a.chapter}


# ---------------- check the fix ----------------
def similar(db, a: ChapterAttempt, q: ChapterQuestion):
    """A different approved question on the same idea, so the student shows they have really learned it.
    Same section first (one they have not just seen, then any), then a new one from the same unit; else the same question again."""
    near = db.query(ChapterQuestion).filter(ChapterQuestion.book_id == q.book_id, ChapterQuestion.chapter == q.chapter,
                                            ChapterQuestion.status == "approved", ChapterQuestion.id != q.id).all()
    seen = set(a.question_ids or [])
    for tier in ([x for x in near if q.section and x.section == q.section and x.id not in seen],
                 [x for x in near if q.section and x.section == q.section],
                 [x for x in near if x.id not in seen]):
        if tier:
            return random.choice(tier), False
    return q, True


@srouter.get("/tests/{aid}/check/{qid}")
def check_question(aid: int, qid: int, db: Session = Depends(get_db), me=Depends(student)):
    a = _mine(db, me, aid)
    if qid not in (a.wrong or []):
        raise HTTPException(404, "Not one of this test's mistakes")
    q = db.get(ChapterQuestion, qid)
    x, same = similar(db, a, q)
    return {"question": q_out(x, answers=False), "same": same, "original_id": qid}


class CheckIn(BaseModel):
    original_id: int
    question_id: int
    answer: str = ""


@srouter.post("/tests/{aid}/check")
def check_answer(aid: int, body: CheckIn, db: Session = Depends(get_db), me=Depends(student)):
    a = _mine(db, me, aid)
    if body.original_id not in (a.wrong or []):
        raise HTTPException(404, "Not one of this test's mistakes")
    orig, x = db.get(ChapterQuestion, body.original_id), db.get(ChapterQuestion, body.question_id)
    if not x or x.book_id != orig.book_id or x.status != "approved":
        raise HTTPException(404, "Question not found")
    ok = T.is_right(x, body.answer)
    if x.id != orig.id:
        M.remember(db, me.id, x, body.answer, ok)
    if ok:
        M.mark_fixed(db, me.id, orig)
        if orig.id not in (a.fixed or []):
            a.fixed = [*(a.fixed or []), orig.id]
    else:
        M.remember(db, me.id, orig, "", False)   # still open: it comes back tomorrow
    db.commit()
    return {"correct": ok, "your_text": T.option_text(x, body.answer) if body.answer else "", "right_text": T.correct_text(x),
            "explanation": x.explanation or x.source, "source": x.source, "fixed": ok}


# ---------------- memory ----------------
@srouter.get("/memory")
def my_memory(book_id: int | None = None, chapter: int | None = None, db: Session = Depends(get_db), me=Depends(student)):
    s = M.summary(db, me.id, book_id, chapter)
    return {**s, "for_eddie": M.for_eddie(s)}


# ---------------- Daily 5 ----------------
def daily_book(db, me):
    """The textbook the student read most recently that has approved questions."""
    from ..models import StudentProgress
    from .student import owned_ids
    ids = set(owned_ids(db, me))
    have = {b for (b,) in db.query(ChapterQuestion.book_id).filter(ChapterQuestion.status == "approved").distinct() if b in ids}
    if not have:
        return None
    prog = db.query(StudentProgress).filter(StudentProgress.user_id == me.id, StudentProgress.book_id.in_(list(have))).order_by(StudentProgress.last_read.desc()).first()
    return db.get(Book, prog.book_id if prog else sorted(have)[0])


def daily_pick(db, me, b: Book):
    """Up to 5: mistakes that are due first, then questions on what they read, then something new."""
    from ..models import QuestionMemory, StudentProgress
    today = date.today().isoformat()
    approved = {q.id: q for q in db.query(ChapterQuestion).filter(ChapterQuestion.book_id == b.id, ChapterQuestion.status == "approved")}
    mem = {m.question_id: m for m in db.query(QuestionMemory).filter(QuestionMemory.user_id == me.id, QuestionMemory.book_id == b.id)}
    out, used = [], set()
    due = sorted([m for m in mem.values() if m.question_id in approved and m.status in ("open", "fixed") and m.due and m.due <= today],
                 key=lambda m: (m.status != "open", m.due))
    for m in due[:3]:
        out.append((approved[m.question_id], "mistake")); used.add(m.question_id)
    p = db.get(StudentProgress, (me.id, b.id))
    read = set((p.sections or []) if p else []); chap = ((p.position or {}).get("chapter") if p else None)
    rng = random.Random(f"{me.id}-{today}")
    fresh = [q for q in approved.values() if q.id not in used and (q.id not in mem or (mem[q.id].box or 0) < 2)]
    rng.shuffle(fresh)
    reading = [q for q in fresh if q.section in read or q.chapter == chap]
    for q in reading:
        if len(out) >= 4: break
        out.append((q, "reading")); used.add(q.id)
    for q in fresh + list(approved.values()):
        if len(out) >= 5: break
        if q.id not in used:
            out.append((q, "new")); used.add(q.id)
    return out


def daily_today(db, me, bid):
    start_ = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return db.query(ChapterAttempt).filter(ChapterAttempt.user_id == me.id, ChapterAttempt.book_id == bid, ChapterAttempt.level == "daily",
                                           ChapterAttempt.finished_at >= start_).first()


def daily_status(db, me):
    b = daily_book(db, me)
    if not b:
        return None
    done = daily_today(db, me, b.id)
    picks = [] if done else daily_pick(db, me, b)
    return {"book_id": b.id, "book_title": b.title, "count": len(picks), "mistakes": sum(r == "mistake" for _, r in picks),
            "reading": sum(r == "reading" for _, r in picks), "done": bool(done), "attempt_id": done.id if done else None,
            "score": done.score if done else None, "total": done.total if done else None}


@srouter.post("/books/{bid}/daily/start")
def daily_start(bid: int, db: Session = Depends(get_db), me=Depends(student)):
    from .student import readable_book
    b = readable_book(db, me, bid)
    done = daily_today(db, me, bid)
    if done:
        raise HTTPException(409, f"done:{done.id}")
    picks = daily_pick(db, me, b)
    if not picks:
        raise HTTPException(404, "No questions for this book yet")
    order = {"mistake": 0, "reading": 1, "new": 2}
    picks.sort(key=lambda x: order[x[1]])
    a = ChapterAttempt(user_id=me.id, book_id=bid, chapter=-1, level="daily", question_ids=[q.id for q, _ in picks], total=len(picks),
                       reasons={str(q.id): r for q, r in picks})
    db.add(a); db.commit()
    return {"id": a.id, "book_id": bid, "book_title": b.title, "chapter": -1, "chapter_title": "Daily 5", "level": "daily",
            "questions": [{**q_out(q, answers=False), "why": r} for q, r in picks],
            "mix": {"mistake": sum(r == "mistake" for _, r in picks), "reading": sum(r == "reading" for _, r in picks), "new": sum(r == "new" for _, r in picks)}}
