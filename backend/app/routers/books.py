from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Book
from ..schemas import BookIn, BookPatch
from ..security import platform_admin
from ..audit import log

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


def out(b: Book):
    d = {c: getattr(b, c) for c in ("id", "title", "subject", "board", "grade", "medium", "edition",
                                    "pages", "price", "status", "created_at", "live_at", "assigned_reviewer_id", "review_note", "reviewed_by")}
    return d


@router.get("")
def list_books(status: str = "", board: str = "", db: Session = Depends(get_db), _=Depends(platform_admin)):
    q = db.query(Book)
    if status:
        q = q.filter(Book.status == status)
    if board:
        q = q.filter(Book.board == board)
    return [out(b) for b in q.order_by(Book.board, Book.grade, Book.subject).all()]


@router.post("")
def create_book(body: BookIn, db: Session = Depends(get_db), me=Depends(platform_admin)):
    if body.status not in ("upcoming",):
        raise HTTPException(422, "New catalogue entries start as upcoming. Upload the book in Processing to digitise it.")
    b = Book(**body.model_dump()); db.add(b); db.flush()
    log(db, me, "book.create", "book", b.id, title=b.title)
    db.commit()
    return out(b)


@router.patch("/{bid}")
def update_book(bid: int, body: BookPatch, db: Session = Depends(get_db), me=Depends(platform_admin)):
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
def transition(bid: int, action: str, db: Session = Depends(get_db), me=Depends(platform_admin)):
    if action not in TRANSITIONS:
        raise HTTPException(404, "Unknown action")
    b = db.get(Book, bid)
    if not b:
        raise HTTPException(404, "Book not found")
    src, dst = TRANSITIONS[action]
    if b.status != src:
        msg = ("Only reviewer approved books can go live" if action == "go_live"
               else "Only a live book can be pulled back" if action == "pull_back"
               else f"Book must be {src} first")
        raise HTTPException(409, msg)
    b.status = dst
    if dst == "live":
        b.live_at = datetime.utcnow()
    if action == "pull_back":
        b.assigned_at = datetime.utcnow()     # the clock restarts
        b.last_opened_at = None
    log(db, me, f"book.{action}", "book", bid, title=b.title)
    db.commit()
    return out(b)
