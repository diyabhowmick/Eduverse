"""The learner's study space: mistakes, "not sure" answers, weak topics and spaced revision cards.

Every answer from a chapter test, quick check, Daily 5, practice question, mock test or quick fix goes
through record(). A wrong or "not sure" answer opens a Mistake and a revision card. Two right answers on
different days clear it. Cards come back after 1, 3, 7, 14 and 30 days, sooner when the learner says Again."""
from datetime import date, timedelta
from .models import ChapterQuestion, Mistake, Question, ReviewCard, ReviewDay, TopicStat

STEPS = [1, 3, 7, 14, 30, 60]


def today() -> str:
    return date.today().isoformat()


def in_days(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


def _opt_text(q, key: str) -> str:
    for o in (q.options or []):
        if str(o.get("key")) == str(key):
            return f"({key}) {o.get('text', '')}"
    return key or ""


def describe(qsource: str, q) -> dict:
    """What the Mistake book and the revision card show for one question."""
    if qsource == "chapter":
        right = _opt_text(q, q.answer) if q.qtype in ("mcq", "figure") else (q.answer or "").split("|")[0]
        return {"text": q.text, "options": q.options or [], "right": right, "solution": q.explanation or "",
                "figure": q.figure or {}, "book_id": q.book_id, "chapter": str(q.chapter), "topic": q.section_title or f"Unit {q.chapter}",
                "section": q.section}
    right = _opt_text(q, q.answer) if q.options else (q.answer or "")
    return {"text": q.text, "options": q.options or [], "right": right, "solution": q.solution or "", "figure": {},
            "chapter": q.chapter or "", "topic": q.chapter or q.section or "General", "has_figure": bool(q.figure_key)}


def card_for(db, uid, kind, ref_id, front, back, where="", book_id=None) -> ReviewCard:
    c = db.query(ReviewCard).filter_by(user_id=uid, kind=kind, ref_id=ref_id).first()
    if c:
        if c.status == "done" and kind in ("mistake", "word"):
            c.status, c.step, c.due = "active", 0, today()
        return c
    c = ReviewCard(user_id=uid, kind=kind, ref_id=ref_id, book_id=book_id, front=front[:1500], back=back[:4000], where=where[:200], due=today())
    db.add(c)
    return c


def record(db, uid: int, qsource: str, q, given: str, ok, *, book_id=None, origin="", not_sure=False):
    """One answer. ok is True, False, or None for a written answer that cannot be checked (only "not sure" counts then)."""
    d = describe(qsource, q)
    bid = book_id or d.get("book_id")
    topic = (d["topic"] or "General")[:200]
    if ok is not None and bid:
        st = db.get(TopicStat, (uid, bid, topic))
        if not st:
            st = TopicStat(user_id=uid, book_id=bid, topic=topic, chapter=d["chapter"][:200], qsource=qsource, right=0, tries=0); db.add(st)
        st.tries += 1; st.right += bool(ok)
    m = db.query(Mistake).filter_by(user_id=uid, qsource=qsource, question_id=q.id).first()
    if ok is False or not_sure:
        if not m:
            m = Mistake(user_id=uid, qsource=qsource, question_id=q.id, book_id=bid, chapter=d["chapter"][:200], topic=topic, wrong_count=0, right_days=[])
            db.add(m)
        m.status, m.origin, m.my_answer = "open", origin[:20], (given or "")[:300]
        m.right_days = []
        if ok is False:
            m.wrong_count = (m.wrong_count or 0) + 1
        m.not_sure = bool(not_sure) or (m.not_sure and ok is not True)
        db.flush()
        front = d["text"] + ("\n" + "\n".join(f"({o.get('key')}) {o.get('text', '')}" for o in d["options"]) if d["options"] else "")
        card_for(db, uid, "mistake", m.id, front, f"{d['right']}\n\n{d['solution']}".strip(), f"{origin} · {topic}", bid)
    elif ok is True and m and m.status == "open":
        days = list(dict.fromkeys([*(m.right_days or []), today()]))
        m.right_days = days
        m.my_answer = (given or "")[:300]
        if len(days) >= 2:      # right on two different days: it has stuck
            m.status, m.not_sure = "cleared", False
            for c in db.query(ReviewCard).filter_by(user_id=uid, kind="mistake", ref_id=m.id):
                c.status = "done"
    return m


def rate(db, card: ReviewCard, grade: str):
    """again | hard | good | easy. Moves the card along the schedule and counts the day for the streak."""
    if grade == "again":
        card.step, card.lapses, card.due = 0, card.lapses + 1, in_days(0 if card.reps == 0 else 1)
    elif grade == "hard":
        card.due = in_days(max(1, STEPS[max(0, card.step - 1)]))
    elif grade == "good":
        card.step = min(card.step + 1, len(STEPS) - 1); card.due = in_days(STEPS[card.step])
    elif grade == "easy":
        card.step = min(card.step + 2, len(STEPS) - 1); card.due = in_days(STEPS[card.step])
    else:
        raise ValueError("grade")
    card.reps += 1
    if card.step >= len(STEPS) - 1 and grade in ("good", "easy"):
        card.status = "done"
    day = db.get(ReviewDay, (card.user_id, today()))
    if not day:
        day = ReviewDay(user_id=card.user_id, day=today(), cards=0); db.add(day)
    day.cards += 1


def streak(db, uid) -> tuple[int, list[bool]]:
    days = {d for (d,) in db.query(ReviewDay.day).filter(ReviewDay.user_id == uid, ReviewDay.day >= in_days(-60))}
    n, k = 0, 0 if today() in days else 1   # today not done yet does not break the streak
    while in_days(-k) in days:
        n += 1; k += 1
    week = [in_days(-i) in days for i in range(6, -1, -1)]
    return n, week


def weak_topics(db, uid, limit=8) -> list[dict]:
    rows = db.query(TopicStat).filter(TopicStat.user_id == uid, TopicStat.tries >= 2).all()
    opens = {}
    for m in db.query(Mistake).filter(Mistake.user_id == uid, Mistake.status == "open"):
        opens[(m.book_id, m.topic)] = opens.get((m.book_id, m.topic), 0) + 1
    out = [{"book_id": r.book_id, "topic": r.topic, "chapter": r.chapter, "qsource": r.qsource, "tries": r.tries,
            "accuracy": round(100 * r.right / r.tries), "open": opens.get((r.book_id, r.topic), 0)} for r in rows]
    out = [t for t in out if t["accuracy"] < 85 or t["open"]]
    return sorted(out, key=lambda t: (t["accuracy"] - 8 * t["open"]))[:limit]


def quickfix_questions(db, uid, book_id: int, topic: str, n=5):
    """Up to five questions on one weak topic: open mistakes first, then fresh ones."""
    from sqlalchemy import or_
    from .models import QuestionPaper
    opened = {m.question_id for m in db.query(Mistake).filter_by(user_id=uid, book_id=book_id, topic=topic, status="open")}
    cq = db.query(ChapterQuestion).filter(ChapterQuestion.book_id == book_id, ChapterQuestion.status == "approved",
                                          or_(ChapterQuestion.section_title == topic, ChapterQuestion.chapter == (int(topic[5:]) if topic.startswith("Unit ") and topic[5:].isdigit() else -99))).all()
    if cq:
        cq.sort(key=lambda q: (q.id not in opened, q.id))
        return "chapter", cq[:n]
    eq = db.query(Question).join(QuestionPaper, Question.paper_id == QuestionPaper.id).filter(
        QuestionPaper.book_id == book_id, QuestionPaper.status == "approved", or_(Question.chapter == topic, Question.section == topic)).all()
    eq = [q for q in eq if q.options and q.answer]
    eq.sort(key=lambda q: (q.id not in opened, q.id))
    return "exam", eq[:n]
