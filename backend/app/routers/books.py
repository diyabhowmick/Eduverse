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
    b.cover_key = f"covers/{b.id}/cover{ext}"
    get_storage().put(b.cover_key, data)


def out(b: Book):
    d = {c: getattr(b, c) for c in ("id", "title", "subject", "board", "grade", "medium", "edition",
                                    "pages", "price", "status", "created_at", "live_at", "assigned_reviewer_id", "review_note", "reviewed_by",
                                    "track", "level", "exam", "university", "course", "semester", "content_type")}
    d["cover"] = f"/api/books/{b.id}/cover" if b.cover_key else ""
    d["linked_book_ids"] = b.linked_book_ids or []
    d["track"] = d["track"] or "textbook"
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


# ---------- flags and issues ----------
# Every rejected page is an open issue. It already carries the book, the page,
# the reviewer, what they wrote and (since the flag change) what kind of
# problem it is and what would fix it. So this reads review_pages rather than
# inventing a second table that could disagree with the page's own status.
#
#   rejected  an open issue
#   pending   somebody fixed it, waiting to be looked at again
#   approved  closed
from ..models import ReviewPage
from .review import FLAGS, RERUNS

STATE = {"rejected": "open", "pending": "to_recheck", "approved": "fixed"}


@router.get("/issues")
def issues(status: str = "open", category: str = "", book_id: int | None = None,
           db: Session = Depends(get_db), _=Depends(super_admin)):
    """Flags across the whole catalogue, newest first."""
    q = db.query(ReviewPage, Book).join(Book, Book.id == ReviewPage.book_id)
    q = q.filter(ReviewPage.category != "")
    if book_id:
        q = q.filter(ReviewPage.book_id == book_id)
    if category:
        q = q.filter(ReviewPage.category == category)
    rows = []
    labels = {k: l for k, l, _ in FLAGS}
    fixes = dict(RERUNS)
    for r, b in q.order_by(ReviewPage.updated_at.desc().nullslast()).all():
        state = STATE.get(r.status, "open")
        if status and status != "all" and state != status:
            continue
        rows.append({
            "book_id": b.id, "book": b.title, "book_status": b.status,
            "page": r.page, "state": state,
            "category": r.category, "category_label": labels.get(r.category, r.category),
            "rerun": r.rerun, "rerun_label": fixes.get(r.rerun, r.rerun),
            "comment": r.comment, "reviewer": r.reviewer,
            "at": r.updated_at, "fixed_by": r.fixed_by, "fixed_at": r.fixed_at,
        })
    return rows


@router.get("/issues/summary")
def issues_summary(db: Session = Depends(get_db), _=Depends(super_admin)):
    """Counts for the screen's heading, and per book so the catalogue can show
    a number on each row. One number per book is worth more than a dashboard."""
    labels = {k: l for k, l, _ in FLAGS}
    by_cat, by_book, by_state = {}, {}, {"open": 0, "to_recheck": 0, "fixed": 0}
    for r in db.query(ReviewPage).filter(ReviewPage.category != "").all():
        state = STATE.get(r.status, "open")
        by_state[state] = by_state.get(state, 0) + 1
        if state == "open":
            by_cat[r.category] = by_cat.get(r.category, 0) + 1
            by_book[r.book_id] = by_book.get(r.book_id, 0) + 1
    return {"by_state": by_state,
            "by_category": sorted(({"key": k, "label": labels.get(k, k), "n": n}
                                   for k, n in by_cat.items()), key=lambda x: -x["n"]),
            "open_by_book": by_book}


class Fixed(BaseModel):
    note: str = ""


@router.post("/{bid}/issues/{page}/fixed")
def mark_fixed(bid: int, page: int, body: Fixed, db: Session = Depends(get_db), me=Depends(super_admin)):
    """Somebody has corrected this page. It goes back to 'needs checking'
    rather than straight to approved — a fix nobody looked at is not a fix.

    Only this page moves. The other 300 approved pages stay approved, which is
    the whole point: a 350 page re-review becomes a 1 page one.
    """
    b = db.get(Book, bid)
    if not b:
        raise HTTPException(404, "Book not found")
    r = db.get(ReviewPage, (bid, page))
    if not r or not r.category:
        raise HTTPException(404, "No flag on that page")
    if r.status != "rejected":
        raise HTTPException(409, "That flag is not open")
    r.status = "pending"
    r.fixed_at, r.fixed_by = datetime.utcnow(), me.email
    if body.note.strip():
        r.comment = (r.comment + "\n\nFix: " + body.note.strip())[:4000]
    log(db, me, "issue.fixed", "book", bid, page=page, category=r.category)
    db.commit()
    return {"page": page, "state": "to_recheck", "book_status": b.status}
