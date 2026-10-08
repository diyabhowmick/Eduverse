"""Money and renewals.

Nothing in the product answered "what we earn, from whom, and what renews
next month". A plan simply existed, with no end date, which makes a renewal
something you notice after it has passed.

Two kinds of number live here and they are guarded differently:

  revenue   what a school pays       /overview, /needs-attention   Super Admin
  cost      what a book cost to make /books, /estimate             Platform Admin

That split is the whole point of the Platform Admin role. The factory needs to
see what processing costs or it cannot be asked to spend less. It must never
see what a school was charged.
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Book, ClassBook, School, User
from ..security import super_admin, platform_admin
from .. import costing

router = APIRouter(prefix="/api/money", tags=["money"])


def paying(db: Session):
    """Real schools only. A test school must never move a revenue number."""
    return db.query(School).filter(School.status == "active",
                                   School.is_test == False).all()   # noqa: E712


def school_row(db: Session, s: School) -> dict:
    students = db.query(User).filter(User.school_id == s.id,
                                     User.role == "student").count()
    days = (s.plan_end - datetime.utcnow()).days if s.plan_end else None
    last = db.query(User.last_login).filter(User.school_id == s.id).order_by(
        User.last_login.desc()).first()
    quiet = (datetime.utcnow() - last[0]).days if last and last[0] else None
    return {
        "id": s.id, "name": s.name, "plan": s.plan.name if s.plan else "",
        "seats": s.seats, "used": students,
        "free": max(0, s.seats - students),
        "price_per_seat": s.price_per_seat,
        "value": round(s.seats * s.price_per_seat, 2),
        "plan_start": s.plan_start, "plan_end": s.plan_end,
        "days_to_renewal": days,
        "quiet_days": quiet,
        "contact": s.contact_name, "phone": s.contact_phone,
        # the four things worth a decision
        "nearly_full": students >= s.seats * 0.9,
        "renewing_soon": days is not None and days <= 45,
        "gone_quiet": quiet is not None and quiet > 14,
        "never_onboarded": s.seats > 0 and students < s.seats * 0.2,
    }


@router.get("/overview")
def overview(db: Session = Depends(get_db), _=Depends(super_admin)):
    rows = [school_row(db, s) for s in paying(db)]
    books = db.query(Book).all()
    return {
        "billed": round(sum(r["value"] for r in rows), 2),
        "used": round(sum(r["used"] * r["price_per_seat"] for r in rows), 2),
        "idle": round(sum(r["free"] * r["price_per_seat"] for r in rows), 2),
        "renewing_45d": round(sum(r["value"] for r in rows if r["renewing_soon"]), 2),
        "at_risk": round(sum(r["value"] for r in rows
                             if r["gone_quiet"] or r["never_onboarded"]), 2),
        "schools": len(rows),
        # what it costs to serve all of it — a one-time catalogue cost, not
        # something that grows when a school reads more
        "catalogue_cost_usd": round(sum(b.cost_usd for b in books), 2),
        "books": len(books),
        "renewals": sorted([r for r in rows if r["days_to_renewal"] is not None],
                           key=lambda r: r["days_to_renewal"]),
    }


@router.get("/needs-attention")
def needs_attention(db: Session = Depends(get_db), _=Depends(super_admin)):
    """The home screen. Not statistics — a list of decisions, each one money
    arriving or leaving. Empty is a good day."""
    rows = [school_row(db, s) for s in paying(db)]
    stuck = db.query(Book).filter(Book.status == "in_review").all()
    now = datetime.utcnow()
    return {
        "nearly_full": [r for r in rows if r["nearly_full"]],
        "renewing": [r for r in rows if r["renewing_soon"]],
        "gone_quiet": [r for r in rows if r["gone_quiet"]],
        "never_onboarded": [r for r in rows if r["never_onboarded"]],
        "stuck_in_review": [
            {"id": b.id, "title": b.title,
             "days": (now - (b.assigned_at or b.created_at)).days,
             "reviewer_id": b.assigned_reviewer_id}
            for b in stuck
            if (now - (b.assigned_at or b.created_at)).days > 14],
        "poor_conversions": [
            {"id": b.id, "title": b.title, "split_by": b.split_by,
             "headings": b.headings_n}
            for b in db.query(Book).filter(Book.split_by == "pages").all()],
    }


@router.get("/books")
def books_by_demand(db: Session = Depends(get_db), _=Depends(platform_admin)):
    """What each book cost, and how many schools it serves.

    This is the whole business model on one list: a book is paid for once and
    read by everyone on that syllabus, so the cost per school falls as the
    catalogue is used more.
    """
    out = []
    for b in db.query(Book).all():
        schools = db.query(ClassBook.class_id).join(
            Book, Book.id == ClassBook.book_id).filter(
            ClassBook.book_id == b.id).count()
        out.append({
            "id": b.id, "title": b.title, "status": b.status,
            "pages": b.pages, "figures": b.figures_n,
            "route": "scanned" if b.route_scanned > b.route_native else "native",
            "cost_usd": round(b.cost_usd, 4),
            "classes": schools,
            "cost_per_class": costing.per_school(b.cost_usd, schools),
            "split_by": b.split_by, "headings": b.headings_n,
        })
    return sorted(out, key=lambda r: -(r["classes"] or 0))


@router.get("/estimate")
def estimate(pages: int = 288, route: str = "native", figures: int = 330,
             keywords: int = 2000, _=Depends(platform_admin)):
    """What a book would cost, before anybody spends it."""
    return costing.estimate(pages, route, figures, keywords)
