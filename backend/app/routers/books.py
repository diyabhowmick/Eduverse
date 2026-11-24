from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Book, QuestionPaper
from ..schemas import BookIn, BookPatch
from ..security import super_admin
from ..audit import log
from ..storage import get_storage

router = APIRouter(prefix="/api/books", tags=["catalogue"])

# Super Admin may only move a book along these edges. in_review -> approved is the Reviewer's job.
TRANSITIONS = {
    "go_live": ("approved", "live"),
    "retire":  ("live", "retired"),
    "restore": ("retired", "live"),
    # A mistake found after publishing used to leave only one option: retire
    # the book and process it again. This sends it back with every approved
    # page intact, so only what changed is checked and nothing is reprocessed.
    "pull_back": ("live", "in_review"),
}


COVER_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def save_cover(b: Book, name: str, data: bytes):
    ext = Path(name).suffix.lower()
    if ext not in COVER_TYPES:
        raise HTTPException(422, "The cover must be a PNG, JPG or WEBP picture")
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(422, "The cover must be under 5 MB")
    from .. import hardening as H
    H.check_upload(name, data[:64], len(data), tuple(COVER_TYPES))
    b.cover_key = f"covers/{b.id}/cover{ext}"
    get_storage().put(b.cover_key, data)


def out(b: Book):
    d = {c: getattr(b, c) for c in ("id", "title", "subject", "board", "grade", "medium", "edition",
                                    "pages", "price", "status", "created_at", "live_at", "assigned_reviewer_id", "review_note", "reviewed_by",
                                    "track", "level", "exam", "university", "course", "semester", "content_type")}
    d["cover"] = f"/api/books/{b.id}/cover" if b.cover_key else ""
    d["linked_book_ids"] = b.linked_book_ids or []
    d["track"] = d["track"] or "textbook"
    d["live_for_students"] = b.status == "live" or (bool(b.live_key) and b.status in ("processing", "in_review", "rejected"))
    return d


@router.get("")
def list_books(status: str = "", board: str = "", track: str = "", db: Session = Depends(get_db), _=Depends(super_admin)):
    q = db.query(Book)
    if track:
        q = q.filter(Book.track == track)
    if status:
        q = q.filter(Book.status == status)
    if board:
        q = q.filter(Book.board == board)
    return [out(b) for b in q.order_by(Book.board, Book.grade, Book.subject).all()]


@router.post("")
def create_book(body: BookIn, db: Session = Depends(get_db), me=Depends(super_admin)):
    if body.status not in ("upcoming",):
        raise HTTPException(422, "New catalogue entries start as upcoming. Upload the book in Processing to digitise it.")
    if not body.title.strip():
        raise HTTPException(422, "Give it a title")
    if body.track == "exam" and not body.exam.strip():
        raise HTTPException(422, "Choose which exam this pack is for")
    b = Book(**body.model_dump()); db.add(b); db.flush()
    log(db, me, "book.create", "book", b.id, title=b.title)
    db.commit()
    return out(b)


@router.get("/{bid}/cover")
def cover(bid: int, db: Session = Depends(get_db)):
    """Public: covers show in the store."""
    b = db.get(Book, bid)
    if not b or not b.cover_key:
        raise HTTPException(404, "No cover")
    return Response(get_storage().get(b.cover_key), media_type=COVER_TYPES.get(Path(b.cover_key).suffix, "image/png"))


@router.patch("/{bid}")
def update_book(bid: int, body: BookPatch, db: Session = Depends(get_db), me=Depends(super_admin)):
    b = db.get(Book, bid)
    if not b:
        raise HTTPException(404, "Book not found")
    ch = body.model_dump(exclude_none=True)
    for k, v in ch.items():
        setattr(b, k, v)
    log(db, me, "book.update", "book", bid, **ch)
    db.commit()
    return out(b)


@router.post("/{bid}/{action}")
def transition(bid: int, action: str, db: Session = Depends(get_db), me=Depends(super_admin)):
    if action not in TRANSITIONS:
        raise HTTPException(404, "Unknown action")
    b = db.get(Book, bid)
    if not b:
        raise HTTPException(404, "Book not found")
    src, dst = TRANSITIONS[action]
    if b.track == "exam" and action == "go_live":
        # An exam pack is not page-reviewed as a whole. Each paper is approved on its own,
        # and the pack can go live once at least one approved paper is in it.
        if not db.query(QuestionPaper).filter(QuestionPaper.book_id == bid, QuestionPaper.status == "approved").count():
            raise HTTPException(409, "Approve at least one question paper before this exam pack goes live")
        src = b.status if b.status in ("upcoming", "approved", "in_review", "processing") else src
    if action == "go_live" and b.track != "exam" and b.status == src:
        from .learn import explain_gate
        block = explain_gate(db, b, me)
        if block:
            raise HTTPException(409, block)
    if b.status != src:
        msg = ("Only reviewer approved books can go live" if action == "go_live"
               else "Only a live book can be pulled back" if action == "pull_back"
               else f"Book must be {src} first")
        raise HTTPException(409, msg)
    b.status = dst
    if dst == "live":
        b.live_at = datetime.utcnow()
        b.live_key = b.content_key or b.live_key
    if action == "pull_back":
        b.live_key = ""                       # pulled back on purpose: students stop seeing it
        b.assigned_at = datetime.utcnow()     # the clock restarts
        b.last_opened_at = None
    log(db, me, f"book.{action}", "book", bid, title=b.title)
    db.commit()
    return out(b)

