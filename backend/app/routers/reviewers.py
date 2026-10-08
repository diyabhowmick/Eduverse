"""Super Admin manages reviewer accounts and who reviews which book."""
import secrets
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User, Book
from ..security import hash_pw, platform_admin
from ..audit import log

router = APIRouter(prefix="/api/reviewers", tags=["reviewers"])


def out(db, u: User):
    q = db.query(Book).filter(Book.assigned_reviewer_id == u.id)
    waiting = q.filter(Book.status == "in_review").all()

    # "Waiting three weeks" and "opened three weeks ago" are different
    # problems: one reviewer has not started, the other is stuck part way.
    # Both dates are reported so the tag can say which.
    now = datetime.utcnow()
    oldest_days, oldest_title, never_opened = 0, "", 0
    for b in waiting:
        since = b.assigned_at or b.created_at
        days = (now - since).days if since else 0
        if days > oldest_days:
            oldest_days, oldest_title = days, b.title
        if not b.last_opened_at:
            never_opened += 1

    return {"id": u.id, "name": u.name, "email": u.email, "status": u.status,
            "last_login": u.last_login, "created_at": u.created_at,
            "in_review": len(waiting),
            "published": db.query(Book).filter(Book.reviewed_by == u.email,
                                               Book.status == "live").count(),
            "oldest_days": oldest_days, "oldest_title": oldest_title,
            "never_opened": never_opened,
            "tag": ("Never opened" if never_opened and oldest_days >= 7
                    else "Oldest waiting" if oldest_days >= 14
                    else "Newly sent" if waiting and oldest_days <= 2
                    else "")}



class ReviewerIn(BaseModel):
    name: str = Field(min_length=2)
    email: str


@router.get("")
def list_reviewers(db: Session = Depends(get_db), _=Depends(platform_admin)):
    return [out(db, u) for u in db.query(User).filter(User.role == "reviewer").order_by(User.name)]


@router.post("")
def create(body: ReviewerIn, db: Session = Depends(get_db), me=Depends(platform_admin)):
    email = body.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "An account with this email already exists")
    pw = secrets.token_urlsafe(9)
    u = User(name=body.name.strip(), email=email, role="reviewer", password_hash=hash_pw(pw))
    db.add(u); db.flush()
    log(db, me, "reviewer.create", "user", u.id, email=email)
    db.commit()
    return {**out(db, u), "temp_password": pw}


class Patch(BaseModel):
    status: str


@router.patch("/{uid}")
def patch(uid: int, body: Patch, db: Session = Depends(get_db), me=Depends(platform_admin)):
    u = db.get(User, uid)
    if not u or u.role != "reviewer":
        raise HTTPException(404, "Reviewer not found")
    if body.status not in ("active", "suspended"):
        raise HTTPException(422, "Status must be active or suspended")
    u.status = body.status
    log(db, me, "reviewer.update", "user", uid, status=body.status)
    db.commit()
    return out(db, u)


@router.post("/{uid}/reset-password")
def reset(uid: int, db: Session = Depends(get_db), me=Depends(platform_admin)):
    u = db.get(User, uid)
    if not u or u.role != "reviewer":
        raise HTTPException(404, "Reviewer not found")
    pw = secrets.token_urlsafe(9); u.password_hash = hash_pw(pw)
    log(db, me, "reviewer.reset_password", "user", uid)
    db.commit()
    return {"email": u.email, "temp_password": pw}


class Assign(BaseModel):
    reviewer_id: int | None = None


@router.put("/books/{bid}")
def assign(bid: int, body: Assign, db: Session = Depends(get_db), me=Depends(platform_admin)):
    b = db.get(Book, bid)
    if not b:
        raise HTTPException(404, "Book not found")
    if body.reviewer_id:
        u = db.get(User, body.reviewer_id)
        if not u or u.role != "reviewer" or u.status != "active":
            raise HTTPException(422, "Choose an active reviewer")
    b.assigned_reviewer_id = body.reviewer_id
    b.assigned_at = datetime.utcnow()
    b.last_opened_at = None          # a new reviewer has not opened it
    log(db, me, "book.assign_reviewer", "book", bid, title=b.title, reviewer_id=body.reviewer_id)
    db.commit()
    return {"ok": True}


class HandoverIn(BaseModel):
    to_reviewer_id: int | None = None


@router.post("/{uid}/handover")
def handover(uid: int, body: HandoverIn, db: Session = Depends(get_db), me=Depends(platform_admin)):
    """Give every book this reviewer holds to somebody else.

    Work already done is kept. If they approved 8 of 20 pages, the next
    reviewer starts at page 9 — handing a book over should not punish the
    person receiving it. The audit log records both names, so "who approved
    page 5" stays answerable.
    """
    leaving = db.get(User, uid)
    if not leaving or leaving.role != "reviewer":
        raise HTTPException(404, "Reviewer not found")
    if not body.to_reviewer_id:
        raise HTTPException(400, "Choose who should take these books")
    taking = db.get(User, body.to_reviewer_id)
    if not taking or taking.role != "reviewer" or taking.status != "active":
        raise HTTPException(400, "That reviewer cannot take books")
    if taking.id == leaving.id:
        raise HTTPException(400, "Choose a different reviewer")

    books = db.query(Book).filter(Book.assigned_reviewer_id == leaving.id,
                                  Book.status == "in_review").all()
    for b in books:
        b.assigned_reviewer_id = taking.id
        b.assigned_at = datetime.utcnow()
        b.last_opened_at = None
        log(db, me, "book.handover", "book", b.id,
            title=b.title, frm=leaving.name, to=taking.name)
    db.commit()
    return {"moved": len(books), "to": taking.name}


@router.delete("/{uid}")
def remove_reviewer(uid: int, db: Session = Depends(get_db), me=Depends(platform_admin)):
    """Remove a reviewer who has left. Blocked while they still hold books —
    deleting them silently would leave those books with nobody to review."""
    u = db.get(User, uid)
    if not u or u.role != "reviewer":
        raise HTTPException(404, "Reviewer not found")
    held = db.query(Book).filter(Book.assigned_reviewer_id == u.id,
                                 Book.status == "in_review").count()
    if held:
        raise HTTPException(400,
            f"{u.name} still has {held} book{'s' if held > 1 else ''} to review. "
            f"Hand them to another reviewer first.")
    log(db, me, "reviewer.remove", "user", u.id, name=u.name)
    db.delete(u)
    db.commit()
    return {"ok": True}
