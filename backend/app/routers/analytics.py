from collections import defaultdict
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User, School, Book, Job, UsageEvent, AuditLog, SchoolRequest
from ..security import super_admin
from .schools import annual_value

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/analytics")
def analytics(days: int = 30, db: Session = Depends(get_db), _=Depends(super_admin)):
    since = datetime.utcnow() - timedelta(days=days)
    ev = db.query(UsageEvent).filter(UsageEvent.day >= since).all()
    daily = defaultdict(lambda: {"active": 0, "minutes": 0, "explanations": 0, "tokens": 0})
    per_book = defaultdict(lambda: {"minutes": 0, "explanations": 0})
    per_school = defaultdict(lambda: {"minutes": 0, "active": 0})
    for e in ev:
        d = daily[e.day.date().isoformat()]
        d["active"] += e.active_students; d["minutes"] += e.reading_minutes
        d["explanations"] += e.explanations; d["tokens"] += e.llm_tokens
        per_book[e.book_id]["minutes"] += e.reading_minutes; per_book[e.book_id]["explanations"] += e.explanations
        per_school[e.school_id]["minutes"] += e.reading_minutes
    books = {b.id: b.title + " (" + b.grade + ")" for b in db.query(Book).all()}
    schools = db.query(School).all()
    names = {s.id: s.name for s in schools}
    return {
        "daily": [{"day": k, **v} for k, v in sorted(daily.items())],
        "top_books": sorted([{"book": books.get(k, "Unknown"), **v} for k, v in per_book.items()], key=lambda x: -x["minutes"])[:6],
        "schools": sorted([{"school": names.get(k, "Unknown"), **v} for k, v in per_school.items()], key=lambda x: -x["minutes"]),
        "revenue": [{"school": s.name, "plan": s.plan.name if s.plan else "", "seats": s.seats, "annual_value": annual_value(s)}
                    for s in schools],
        "totals": {"minutes": sum(e.reading_minutes for e in ev), "explanations": sum(e.explanations for e in ev),
                   "tokens": sum(e.llm_tokens for e in ev)},
    }


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), _=Depends(super_admin)):
    role_counts = dict(db.query(User.role, func.count()).group_by(User.role).all())
    schools = db.query(School).all()
    book_counts = dict(db.query(Book.status, func.count()).group_by(Book.status).all())
    jobs = dict(db.query(Job.status, func.count()).group_by(Job.status).all())
    seats = sum(s.seats for s in schools if s.status == "active")
    week = datetime.utcnow() - timedelta(days=7)
    ev = db.query(UsageEvent).filter(UsageEvent.day >= week).all()
    return {
        "schools": len(schools), "active_schools": sum(1 for s in schools if s.status == "active"),
        "admins": role_counts.get("admin", 0), "students": role_counts.get("student", 0),
        "reviewers": role_counts.get("reviewer", 0), "seats": seats,
        "arr": round(sum(annual_value(s) for s in schools), 2),
        "books": book_counts, "jobs": jobs,
        "week_minutes": sum(e.reading_minutes for e in ev), "week_explanations": sum(e.explanations for e in ev),
        "needs_attention": {
            "approved_not_live": book_counts.get("approved", 0),
            "sent_back": book_counts.get("rejected", 0),
            "failed_jobs": jobs.get("failed", 0),
            "in_review": book_counts.get("in_review", 0),
            "suspended_schools": sum(1 for s in schools if s.status == "suspended"),
            "open_requests": db.query(SchoolRequest).filter(SchoolRequest.status == "open").count(),
        },
        "recent": [{"at": a.at, "actor": a.actor_email, "action": a.action, "target": f"{a.target_type} {a.target_id}", "detail": a.detail}
                   for a in db.query(AuditLog).order_by(AuditLog.at.desc()).limit(8).all()],
    }


@router.get("/audit")
def audit(q: str = "", action: str = "", limit: int = 200, db: Session = Depends(get_db), _=Depends(super_admin)):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action.startswith(action))
    if q:
        query = query.filter(AuditLog.actor_email.ilike(f"%{q}%"))
    return [{"id": a.id, "at": a.at, "actor": a.actor_email, "role": a.actor_role, "action": a.action,
             "target_type": a.target_type, "target_id": a.target_id, "detail": a.detail}
            for a in query.order_by(AuditLog.at.desc()).limit(min(limit, 1000)).all()]
