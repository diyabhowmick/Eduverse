"""What a class teacher sees: their own classes, and nothing else.

A teacher cannot add, remove or suspend a student — that is the school admin's
job, and it is exactly why a teacher could not simply be given an admin
account. The only thing a teacher can do here is record that they nudged a
student who has fallen behind.

The numbers come from the same helpers the school admin screens use, so a class
reads the same on both sides.
"""
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..audit import log
from ..db import get_db
from ..models import Book, ClassBook, ClassRoom, User, UsageEvent
from ..security import require
from .school import progress_map, student_out

router = APIRouter(prefix="/api/teacher", tags=["teacher"])
teacher = require("teacher")


def my_classes(db: Session, me: User):
    return db.query(ClassRoom).filter(ClassRoom.teacher_id == me.id).order_by(
        ClassRoom.grade, ClassRoom.section).all()


def class_name(c: ClassRoom) -> str:
    return f"{c.grade}{(' ' + c.section) if c.section else ''}"


def class_row(db: Session, c: ClassRoom) -> dict:
    studs = db.query(User).filter(User.class_id == c.id,
                                  User.role == "student").all()
    pm = progress_map(db, [u.id for u in studs])
    week = datetime.utcnow() - timedelta(days=7)

    read_week = sum(1 for u in studs
                    if (pm.get(u.id) or {}).get("last_read")
                    and pm[u.id]["last_read"] >= week)
    pcts = [pm[u.id]["percent"] for u in studs if u.id in pm]
    books = db.query(Book).join(ClassBook, ClassBook.book_id == Book.id).filter(
        ClassBook.class_id == c.id).all()

    return {
        "id": c.id,
        "name": class_name(c),
        "students": len(studs),
        "books": [{"id": b.id, "title": b.title} for b in books],
        "avg_progress": round(sum(pcts) / len(pcts)) if pcts else 0,
        "active_week": read_week,
        "behind": len(studs) - read_week,
        "hours": round(sum((pm.get(u.id) or {}).get("minutes", 0)
                           for u in studs) / 60),
    }


@router.get("/overview")
def overview(db: Session = Depends(get_db), me=Depends(teacher)):
    classes = [class_row(db, c) for c in my_classes(db, me)]
    students = sum(c["students"] for c in classes)
    weighted = sum(c["avg_progress"] * c["students"] for c in classes)
    return {
        "teacher": me.name,
        "school": me.school.name if me.school else "",
        "classes": classes,
        "students": students,
        "behind": sum(c["behind"] for c in classes),
        "hours": sum(c["hours"] for c in classes),
        "avg_progress": round(weighted / students) if students else 0,
    }


@router.get("/classes")
def classes(db: Session = Depends(get_db), me=Depends(teacher)):
    return [class_row(db, c) for c in my_classes(db, me)]


@router.get("/classes/{cid}")
def one_class(cid: int, db: Session = Depends(get_db), me=Depends(teacher)):
    c = db.get(ClassRoom, cid)
    if not c or c.teacher_id != me.id:
        raise HTTPException(404, "That is not one of your classes")
    studs = db.query(User).filter(User.class_id == cid,
                                  User.role == "student").order_by(User.name).all()
    pm = progress_map(db, [u.id for u in studs])
    week = datetime.utcnow() - timedelta(days=7)
    rows = []
    for u in studs:
        d = student_out(u, pm.get(u.id))
        d["behind"] = not d["last_read"] or d["last_read"] < week
        rows.append(d)
    return {"class": class_row(db, c), "students": rows}


@router.get("/analytics")
def analytics(days: int = 30, db: Session = Depends(get_db), me=Depends(teacher)):
    """The same shape the school admin's analytics returns, but only this
    teacher's classes, so the chart component is shared."""
    mine = my_classes(db, me)
    since = datetime.utcnow() - timedelta(days=days)
    ids = [u.id for u in db.query(User).filter(
        User.class_id.in_([c.id for c in mine]), User.role == "student")] if mine else []

    daily = defaultdict(lambda: {"active": 0, "minutes": 0, "explanations": 0})
    if me.school_id:
        for e in db.query(UsageEvent).filter(UsageEvent.school_id == me.school_id,
                                             UsageEvent.day >= since):
            d = daily[e.day.date().isoformat()]
            d["active"] += e.active_students
            d["minutes"] += e.reading_minutes
            d["explanations"] += e.explanations

    pm = progress_map(db, ids)
    ranked = sorted(
        [student_out(u, pm.get(u.id)) for u in db.query(User).filter(User.id.in_(ids))],
        key=lambda x: -x["progress"]) if ids else []

    return {
        "daily": [{"day": k, **v} for k, v in sorted(daily.items())],
        "classes": [class_row(db, c) for c in mine],
        "top": ranked[:8],
        "needs_help": [r for r in ranked if r["status"] == "active"][-8:][::-1],
    }


@router.post("/students/{sid}/nudge")
def nudge(sid: int, db: Session = Depends(get_db), me=Depends(teacher)):
    """The one action a teacher has. It records the nudge and changes nothing
    else — a teacher's job here is to notice, not to administer."""
    s = db.get(User, sid)
    if not s or s.role != "student":
        raise HTTPException(404, "Student not found")
    c = db.get(ClassRoom, s.class_id) if s.class_id else None
    if not c or c.teacher_id != me.id:
        raise HTTPException(403, "That student is not in your class")
    log(db, me, "student.nudge", "user", s.id, name=s.name, klass=class_name(c))
    db.commit()
    return {"ok": True, "student": s.name}
