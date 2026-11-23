"""Eddie's memory of each student: every chapter question they have answered, which mistakes are
still open, which are fixed, and when to bring each one back (spaced repetition: 1, 2, 4, 7, 14 days)."""
from datetime import date, datetime, timedelta
from .models import ChapterQuestion, QuestionMemory

GAPS = [1, 2, 4, 7, 14]


def _row(db, uid, q) -> QuestionMemory:
    m = db.get(QuestionMemory, (uid, q.id))
    if not m:
        m = QuestionMemory(user_id=uid, question_id=q.id, book_id=q.book_id, right=0, wrong=0, status="", box=0, due="")
        db.add(m)
    return m


def _due(box):
    return (date.today() + timedelta(days=GAPS[max(0, min(box, 4))])).isoformat()


def remember(db, uid, q, given: str, ok: bool) -> QuestionMemory:
    m = _row(db, uid, q)
    m.last_answer, m.last_at = (given or "")[:200], datetime.utcnow()
    if not ok:
        m.wrong = (m.wrong or 0) + 1
        m.status, m.box, m.fixed_at = "open", 0, None
        m.due = _due(0)
    else:
        m.right = (m.right or 0) + 1
        m.box = min(4, (m.box or 0) + 1)
        if m.status == "open" and m.box >= 2:
            m.status, m.fixed_at = "fixed", datetime.utcnow()
        m.due = _due(m.box)
    return m


def mark_fixed(db, uid, q):
    """The student explained back a mistake and got a similar question right: fixed, but it comes back once to be sure."""
    m = _row(db, uid, q)
    m.status, m.box, m.fixed_at, m.due = "fixed", max(m.box or 0, 1), datetime.utcnow(), _due(1)
    return m


def times_wrong(db, uid, qid) -> int:
    m = db.get(QuestionMemory, (uid, qid))
    return m.wrong if m else 0


def summary(db, uid, book_id=None, chapter=None) -> dict:
    qm = db.query(QuestionMemory, ChapterQuestion).join(ChapterQuestion, ChapterQuestion.id == QuestionMemory.question_id).filter(QuestionMemory.user_id == uid)
    if book_id:
        qm = qm.filter(QuestionMemory.book_id == book_id)
    if chapter is not None:
        qm = qm.filter(ChapterQuestion.chapter == chapter)
    rows = qm.all()
    topics = {}
    for m, q in rows:
        k = (q.book_id, q.chapter, q.section_title or f"Unit {q.chapter}")
        t = topics.setdefault(k, {"book_id": q.book_id, "chapter": q.chapter, "section": q.section, "title": k[2], "open": 0, "fixed": 0, "right": 0, "wrong": 0})
        t["open"] += m.status == "open"; t["fixed"] += m.status == "fixed"; t["right"] += m.right or 0; t["wrong"] += m.wrong or 0
    weak = sorted([t for t in topics.values() if t["open"] or t["wrong"] > t["right"]], key=lambda t: (-t["open"], t["right"] - t["wrong"]))
    today = date.today().isoformat()
    return {"weak": weak[:4], "open": sum(m.status == "open" for m, _ in rows), "fixed": sum(m.status == "fixed" for m, _ in rows),
            "due": sum(1 for m, _ in rows if m.status in ("open", "fixed") and m.due and m.due <= today), "answered": len(rows)}


def for_eddie(s: dict) -> str:
    """One line Eddie gets in his context, so he can say 'last time you found X tricky'."""
    if not s or not s.get("answered"):
        return ""
    parts = []
    if s["weak"]:
        parts.append("Topics they found tricky in tests: " + "; ".join(f"{t['title']} ({t['open']} mistake{'s' if t['open'] != 1 else ''} still open)" if t["open"] else t["title"] for t in s["weak"][:3]))
    parts.append(f"Mistakes fixed so far: {s['fixed']}. Still to fix: {s['open']}.")
    return " ".join(parts)
