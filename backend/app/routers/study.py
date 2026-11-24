"""Notebook, saved explanations, Mistake book and Revise for a learner. Everything here is private:
every query is filtered by the signed-in learner, and nothing is shared with anyone else."""
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session
from ..db import get_db, SessionLocal
from ..models import Book, ChapterQuestion, Explanation, Mistake, Note, Question, ReviewCard, SavedExplanation
from ..storage import get_storage
from .. import hardening as H
from .. import study as S
from .student import student, owned_ids

router = APIRouter(prefix="/api/student/study", tags=["study"])
COLORS = ("yellow", "red", "green", "blue")
AUDIO = {b"\x1aE\xdf\xa3": "audio/webm", b"OggS": "audio/ogg", b"RIFF": "audio/wav", b"ID3": "audio/mpeg", b"\xff\xfb": "audio/mpeg"}
MAX_AUDIO = 8 * 1048576


def _owned_book(db, me, book_id):
    if book_id and book_id not in owned_ids(db, me):
        raise HTTPException(403, "That book is not in your library")


def _book_titles(db, ids) -> dict:
    return {b.id: b.title for b in db.query(Book).filter(Book.id.in_([i for i in ids if i] or [0]))}


# ---------------- notes, highlights, voice ----------------
def note_out(n: Note, titles=None):
    return {"id": n.id, "kind": n.kind, "book_id": n.book_id, "book": (titles or {}).get(n.book_id, ""), "chapter": n.chapter, "section": n.section,
            "block_id": n.block_id, "quote": n.quote, "body": n.body, "color": n.color, "tags": n.tags or [], "audio": bool(n.audio_key),
            "audio_secs": n.audio_secs, "transcript": n.transcript, "created_at": n.created_at, "updated_at": n.updated_at}


class NoteIn(BaseModel):
    kind: str = "note"
    book_id: int | None = None
    chapter: int | None = None
    section: str = Field("", max_length=80)
    block_id: str = Field("", max_length=80)
    quote: str = Field("", max_length=1200)
    body: str = Field("", max_length=8000)
    color: str = "yellow"
    tags: list[str] = []


def _clean_tags(tags):
    out = []
    for t in tags[:8]:
        t = "".join(c for c in str(t).lower().lstrip("#") if c.isalnum() or c in "-_")[:24]
        if t and t not in out:
            out.append(t)
    return out


@router.get("/notes")
def list_notes(book_id: int | None = None, chapter: int | None = None, kind: str = "", tag: str = "", q: str = "", limit: int = 300,
               db: Session = Depends(get_db), me=Depends(student)):
    qry = db.query(Note).filter(Note.user_id == me.id)
    if book_id: qry = qry.filter(Note.book_id == book_id)
    if chapter is not None: qry = qry.filter(Note.chapter == chapter)
    if kind in ("note", "highlight", "voice"): qry = qry.filter(Note.kind == kind)
    if q.strip():
        like = f"%{q.strip()[:80]}%"
        qry = qry.filter(or_(Note.body.ilike(like), Note.quote.ilike(like), Note.transcript.ilike(like)))
    rows = qry.order_by(Note.created_at.desc()).limit(min(limit, 500)).all()
    if tag:
        rows = [n for n in rows if tag.lower().lstrip("#") in (n.tags or [])]
    titles = _book_titles(db, {n.book_id for n in rows})
    tags = sorted({t for (ts,) in db.query(Note.tags).filter(Note.user_id == me.id) for t in (ts or [])})
    return {"notes": [note_out(n, titles) for n in rows], "tags": tags,
            "books": [{"id": k, "title": v} for k, v in _book_titles(db, {b for (b,) in db.query(Note.book_id).filter(Note.user_id == me.id).distinct()}).items()]}


@router.post("/notes")
def add_note(body: NoteIn, db: Session = Depends(get_db), me=Depends(student)):
    H.guard(f"notes:{me.id}", 60, 60, "Too many notes in one minute.")
    if body.kind not in ("note", "highlight"):
        raise HTTPException(422, "kind must be note or highlight")
    if body.kind == "note" and not body.body.strip():
        raise HTTPException(422, "Write something first")
    if body.kind == "highlight" and not body.quote.strip():
        raise HTTPException(422, "Select the words to highlight")
    _owned_book(db, me, body.book_id)
    n = Note(user_id=me.id, kind=body.kind, book_id=body.book_id, chapter=body.chapter, section=body.section, block_id=body.block_id,
             quote=body.quote.strip(), body=body.body.strip(), color=body.color if body.color in COLORS else "yellow", tags=_clean_tags(body.tags))
    db.add(n); db.commit()
    return note_out(n)


class NotePatch(BaseModel):
    body: str | None = Field(None, max_length=8000)
    color: str | None = None
    tags: list[str] | None = None


def _mine(db, me, nid) -> Note:
    n = db.get(Note, nid)
    if not n or n.user_id != me.id:
        raise HTTPException(404, "Note not found")
    return n


@router.put("/notes/{nid}")
def edit_note(nid: int, body: NotePatch, db: Session = Depends(get_db), me=Depends(student)):
    n = _mine(db, me, nid)
    if body.body is not None: n.body = body.body.strip()
    if body.color in COLORS: n.color = body.color
    if body.tags is not None: n.tags = _clean_tags(body.tags)
    db.commit()
    return note_out(n)


@router.delete("/notes/{nid}")
def delete_note(nid: int, db: Session = Depends(get_db), me=Depends(student)):
    n = _mine(db, me, nid)
    if n.audio_key:
        try:
            get_storage().delete(n.audio_key)
        except Exception:
            pass
    for c in db.query(ReviewCard).filter_by(user_id=me.id, kind="note", ref_id=n.id):
        db.delete(c)
    db.delete(n); db.commit()
    return {"ok": True}


@router.post("/notes/voice")
async def add_voice(audio: UploadFile = File(...), seconds: int = Form(0), book_id: int | None = Form(None), chapter: int | None = Form(None),
                    section: str = Form(""), block_id: str = Form(""), quote: str = Form(""), body: str = Form(""),
                    db: Session = Depends(get_db), me=Depends(student)):
    H.guard(f"voice:{me.id}", 20, 600, "Too many voice notes in a few minutes.")
    _owned_book(db, me, book_id)
    data = await audio.read()
    if not data or len(data) > MAX_AUDIO:
        raise HTTPException(413, "A voice note can be up to 3 minutes")
    head = data[:12]
    kind = next((t for sig, t in AUDIO.items() if head.startswith(sig)), None) or ("audio/mp4" if head[4:8] == b"ftyp" else None)
    if not kind:
        raise HTTPException(422, "That recording could not be read. Try again.")
    ext = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/wav": "wav", "audio/mpeg": "mp3", "audio/mp4": "m4a"}[kind]
    key = f"voice/{me.id}/{uuid.uuid4().hex}.{ext}"
    get_storage().put(key, data)
    n = Note(user_id=me.id, kind="voice", book_id=book_id, chapter=chapter, section=section[:80], block_id=block_id[:80], quote=quote[:1200],
             body=body[:2000], audio_key=key, audio_type=kind, audio_secs=max(0, min(int(seconds or 0), 180)))
    db.add(n); db.commit()
    from ..tasks import enqueue
    enqueue("transcribe", n.id)
    return note_out(n)


@router.get("/notes/{nid}/audio")
def note_audio(nid: int, db: Session = Depends(get_db), me=Depends(student)):
    n = _mine(db, me, nid)
    if not n.audio_key:
        raise HTTPException(404, "No recording")
    return Response(get_storage().get(n.audio_key), media_type=n.audio_type or "audio/webm", headers={"Cache-Control": "private, max-age=3600"})


def transcribe(note_id: int):
    """Writes a transcript for a voice note, so it can be searched. Uses the OpenAI key from AI settings when
    one is saved; without one the note simply has no transcript. Never spends the learner's AI credits."""
    import json, urllib.request
    with SessionLocal() as db:
        n = db.get(Note, note_id)
        if not n or not n.audio_key or n.transcript:
            return
        from ..explain_store import ai_conf
        key = ((ai_conf(db).get("providers") or {}).get("openai") or {}).get("api_key") or ""
        import os
        key = key or os.getenv("OPENAI_API_KEY", "")
        if not key:
            return
        data = get_storage().get(n.audio_key)
        boundary = uuid.uuid4().hex
        ext = n.audio_key.rsplit(".", 1)[-1]
        parts = [f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\nwhisper-1\r\n".encode(),
                 f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"note.{ext}\"\r\nContent-Type: {n.audio_type}\r\n\r\n".encode(),
                 data, f"\r\n--{boundary}--\r\n".encode()]
        req = urllib.request.Request("https://api.openai.com/v1/audio/transcriptions", b"".join(parts),
                                     {"Authorization": "Bearer " + key, "Content-Type": f"multipart/form-data; boundary={boundary}"})
        text = json.loads(urllib.request.urlopen(req, timeout=120).read()).get("text", "")
        n.transcript = text.strip()[:6000]
        db.commit()


# ---------------- saved explanations ----------------
class SaveIn(BaseModel):
    explanation_id: int
    book_id: int | None = None
    chapter: int | None = None
    path: list[str] = []


def saved_out(s: SavedExplanation, e: Explanation | None, titles=None):
    return {"id": s.id, "explanation_id": s.explanation_id, "book_id": s.book_id, "book": (titles or {}).get(s.book_id, ""), "chapter": s.chapter,
            "path": s.path or [], "term": e.term if e else "", "text": e.text if e else "", "level": e.level if e else 1, "created_at": s.created_at}


@router.get("/saved")
def list_saved(book_id: int | None = None, chapter: int | None = None, db: Session = Depends(get_db), me=Depends(student)):
    q = db.query(SavedExplanation).filter(SavedExplanation.user_id == me.id)
    if book_id: q = q.filter(SavedExplanation.book_id == book_id)
    if chapter is not None: q = q.filter(SavedExplanation.chapter == chapter)
    rows = q.order_by(SavedExplanation.created_at.desc()).limit(500).all()
    ex = {e.id: e for e in db.query(Explanation).filter(Explanation.id.in_([r.explanation_id for r in rows] or [0]))}
    titles = _book_titles(db, {r.book_id for r in rows})
    return [saved_out(r, ex.get(r.explanation_id), titles) for r in rows]


@router.post("/saved")
def save(body: SaveIn, db: Session = Depends(get_db), me=Depends(student)):
    e = db.get(Explanation, body.explanation_id)
    if not e:
        raise HTTPException(404, "Explanation not found")
    bid = body.book_id or e.book_id
    _owned_book(db, me, bid)
    s = db.query(SavedExplanation).filter_by(user_id=me.id, explanation_id=e.id).first()
    if not s:
        s = SavedExplanation(user_id=me.id, explanation_id=e.id, book_id=bid, chapter=body.chapter, path=[p[:80] for p in body.path[:8]])
        db.add(s); db.flush()
        S.card_for(db, me.id, "saved", s.id, e.term or "This explanation", e.text, " › ".join(s.path), bid)
    db.commit()
    return saved_out(s, e)


@router.delete("/saved/{sid}")
def unsave(sid: int, db: Session = Depends(get_db), me=Depends(student)):
    s = db.get(SavedExplanation, sid)
    if not s or s.user_id != me.id:
        raise HTTPException(404, "Not found")
    for c in db.query(ReviewCard).filter_by(user_id=me.id, kind="saved", ref_id=s.id):
        db.delete(c)
    db.delete(s); db.commit()
    return {"ok": True}


@router.delete("/saved/by-explanation/{eid}")
def unsave_by_explanation(eid: int, db: Session = Depends(get_db), me=Depends(student)):
    s = db.query(SavedExplanation).filter_by(user_id=me.id, explanation_id=eid).first()
    return unsave(s.id, db, me) if s else {"ok": True}


# ---------------- mistakes ----------------
def mistake_out(m: Mistake, q, titles=None):
    d = S.describe(m.qsource, q) if q else {"text": "This question was removed", "options": [], "right": "", "solution": "", "figure": {}}
    mine = m.my_answer
    if q and q.options and mine:
        mine = S._opt_text(q, mine)
    return {"id": m.id, "qsource": m.qsource, "question_id": m.question_id, "origin": m.origin, "book_id": m.book_id, "book": (titles or {}).get(m.book_id, ""),
            "chapter": m.chapter, "topic": m.topic, "text": d["text"], "options": d["options"], "my_answer": mine, "right": d["right"],
            "solution": d["solution"], "figure": d.get("figure") or {}, "section": d.get("section", ""), "wrong_count": m.wrong_count,
            "not_sure": m.not_sure, "right_days": len(m.right_days or []), "status": m.status, "updated_at": m.updated_at}


def _questions(db, rows):
    cq = {q.id: q for q in db.query(ChapterQuestion).filter(ChapterQuestion.id.in_([m.question_id for m in rows if m.qsource == "chapter"] or [0]))}
    eq = {q.id: q for q in db.query(Question).filter(Question.id.in_([m.question_id for m in rows if m.qsource == "exam"] or [0]))}
    return lambda m: (cq if m.qsource == "chapter" else eq).get(m.question_id)


@router.get("/mistakes")
def list_mistakes(show: str = "open", book_id: int | None = None, chapter: str = "", origin: str = "", db: Session = Depends(get_db), me=Depends(student)):
    q = db.query(Mistake).filter(Mistake.user_id == me.id)
    if show == "open": q = q.filter(Mistake.status == "open", Mistake.wrong_count > 0)
    elif show == "not_sure": q = q.filter(Mistake.status == "open", Mistake.not_sure.is_(True))
    elif show == "cleared": q = q.filter(Mistake.status == "cleared")
    if book_id: q = q.filter(Mistake.book_id == book_id)
    if chapter: q = q.filter(Mistake.chapter == chapter)
    if origin: q = q.filter(Mistake.origin == origin)
    rows = q.order_by(Mistake.updated_at.desc()).limit(400).all()
    get = _questions(db, rows)
    titles = _book_titles(db, {m.book_id for m in rows})
    base = db.query(Mistake).filter(Mistake.user_id == me.id, Mistake.status == "open")
    return {"items": [mistake_out(m, get(m), titles) for m in rows],
            "counts": {"open": base.filter(Mistake.wrong_count > 0).count(), "not_sure": base.filter(Mistake.not_sure.is_(True)).count(),
                       "cleared": db.query(Mistake).filter(Mistake.user_id == me.id, Mistake.status == "cleared").count()},
            "origins": sorted({o for (o,) in db.query(Mistake.origin).filter(Mistake.user_id == me.id).distinct() if o})}


@router.post("/mistakes/{mid}/dismiss")
def dismiss(mid: int, db: Session = Depends(get_db), me=Depends(student)):
    m = db.get(Mistake, mid)
    if not m or m.user_id != me.id:
        raise HTTPException(404, "Not found")
    m.status = "dismissed"
    for c in db.query(ReviewCard).filter_by(user_id=me.id, kind="mistake", ref_id=m.id):
        c.status = "done"
    db.commit()
    return {"ok": True}


# ---------------- revise ----------------
def card_out(c: ReviewCard):
    return {"id": c.id, "kind": c.kind, "ref_id": c.ref_id, "book_id": c.book_id, "front": c.front, "back": c.back, "where": c.where,
            "due": c.due, "step": c.step, "reps": c.reps}


@router.get("/revise")
def revise(db: Session = Depends(get_db), me=Depends(student)):
    t = S.today()
    due = db.query(ReviewCard).filter(ReviewCard.user_id == me.id, ReviewCard.status == "active", ReviewCard.due <= t).order_by(ReviewCard.due, ReviewCard.id).limit(40).all()
    order = {"mistake": 0, "word": 1, "saved": 2, "note": 3}
    due.sort(key=lambda c: (order.get(c.kind, 9), c.due))
    mix = {}
    for c in due[:20]:
        k = "not_sure" if c.kind == "mistake" and (db.get(Mistake, c.ref_id) or Mistake()).not_sure and not (db.get(Mistake, c.ref_id) or Mistake()).wrong_count else c.kind
        mix[k] = mix.get(k, 0) + 1
    tomorrow = db.query(ReviewCard).filter(ReviewCard.user_id == me.id, ReviewCard.status == "active", ReviewCard.due == S.in_days(1)).count()
    st, week = S.streak(db, me.id)
    titles = _book_titles(db, {w["book_id"] for w in S.weak_topics(db, me.id)})
    weak = [{**w, "book": titles.get(w["book_id"], "")} for w in S.weak_topics(db, me.id)]
    counts = list_mistakes("open", None, "", "", db, me)["counts"]
    return {"due": [card_out(c) for c in due[:20]], "due_total": len(due), "mix": mix, "tomorrow": tomorrow, "streak": st, "week": week,
            "weak": weak, "counts": {**counts, "cards": db.query(ReviewCard).filter(ReviewCard.user_id == me.id, ReviewCard.status == "active").count()}}


@router.get("/cards")
def cards(kind: str = "", db: Session = Depends(get_db), me=Depends(student)):
    q = db.query(ReviewCard).filter(ReviewCard.user_id == me.id, ReviewCard.status == "active")
    if kind: q = q.filter(ReviewCard.kind == kind)
    return [card_out(c) for c in q.order_by(ReviewCard.due).limit(500)]


class RateIn(BaseModel):
    grade: str


@router.post("/cards/{cid}/rate")
def rate(cid: int, body: RateIn, db: Session = Depends(get_db), me=Depends(student)):
    c = db.get(ReviewCard, cid)
    if not c or c.user_id != me.id:
        raise HTTPException(404, "Card not found")
    try:
        S.rate(db, c, body.grade)
    except ValueError:
        raise HTTPException(422, "grade must be again, hard, good or easy")
    db.commit()
    return card_out(c)


class CardIn(BaseModel):
    note_id: int
    front: str = Field("", max_length=300)


@router.post("/cards/from-note")
def card_from_note(body: CardIn, db: Session = Depends(get_db), me=Depends(student)):
    n = _mine(db, me, body.note_id)
    front = body.front.strip() or n.quote[:200] or "Your note"
    c = S.card_for(db, me.id, "note", n.id, front, n.body or n.transcript or n.quote, "Your note", n.book_id)
    db.commit()
    return card_out(c)


# ---------------- quick fix: five questions on one weak topic ----------------
@router.get("/quickfix")
def quickfix(book_id: int, topic: str, db: Session = Depends(get_db), me=Depends(student)):
    _owned_book(db, me, book_id)
    src, qs = S.quickfix_questions(db, me.id, book_id, topic)
    if not qs:
        raise HTTPException(404, "No questions on this topic yet")
    return {"qsource": src, "topic": topic, "questions": [{"id": q.id, "text": q.text, "options": q.options or [],
            "figure": (q.figure or {}) if src == "chapter" else {}, "qtype": q.qtype} for q in qs]}


class FixIn(BaseModel):
    qsource: str
    question_id: int
    given: str = Field("", max_length=300)
    not_sure: bool = False


@router.post("/answer")
def answer(body: FixIn, db: Session = Depends(get_db), me=Depends(student)):
    """One answer from Quick fix or from a mistake card: checked, recorded, and the right answer shown."""
    if body.qsource == "chapter":
        from .. import chapter_tests as T
        q = db.get(ChapterQuestion, body.question_id)
        if not q or q.status != "approved":
            raise HTTPException(404, "Question not found")
        _owned_book(db, me, q.book_id)
        ok, bid = T.is_right(q, body.given), q.book_id
    elif body.qsource == "exam":
        from .exams import judge
        from ..models import QuestionPaper
        q = db.get(Question, body.question_id)
        p = db.get(QuestionPaper, q.paper_id) if q else None
        if not p or p.status != "approved":
            raise HTTPException(404, "Question not found")
        _owned_book(db, me, p.book_id)
        ok, bid = judge(q, body.given.strip().lower()), p.book_id
    else:
        raise HTTPException(422, "qsource must be chapter or exam")
    S.record(db, me.id, body.qsource, q, body.given, ok, book_id=bid, origin="Quick fix", not_sure=body.not_sure)
    db.commit()
    d = S.describe(body.qsource, q)
    return {"correct": ok, "right": d["right"], "solution": d["solution"]}


# ---------------- what the reader's side panel shows for one chapter ----------------
@router.get("/chapter")
def chapter_view(book_id: int, chapter: int, db: Session = Depends(get_db), me=Depends(student)):
    _owned_book(db, me, book_id)
    notes = db.query(Note).filter(Note.user_id == me.id, Note.book_id == book_id, Note.chapter == chapter).order_by(Note.created_at.desc()).all()
    saved = list_saved(book_id, chapter, db, me)
    ms = db.query(Mistake).filter(Mistake.user_id == me.id, Mistake.book_id == book_id, Mistake.status == "open", Mistake.chapter == str(chapter)).all()
    get = _questions(db, ms)
    return {"notes": [note_out(n) for n in notes], "saved": saved, "mistakes": [mistake_out(m, get(m)) for m in ms]}


@router.get("/due")
def due(db: Session = Depends(get_db), me=Depends(student)):
    return summary(db, me.id)


def summary(db, uid) -> dict:
    """For Home: cards due today."""
    return {"due": db.query(ReviewCard).filter(ReviewCard.user_id == uid, ReviewCard.status == "active", ReviewCard.due <= S.today()).count()}
