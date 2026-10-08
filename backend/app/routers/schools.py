from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import School, User
from ..schemas import SchoolIn
from ..security import super_admin
from ..audit import log

router = APIRouter(prefix="/api/schools", tags=["schools"])


def annual_value(s: School) -> float:
    if not s.plan or s.status != "active":
        return 0.0
    price = s.plan.price_per_seat * (12 if s.plan.billing_cycle == "monthly" else 1)
    disc = (s.discount.percent / 100) if s.discount and s.discount.active else 0
    return round(s.seats * price * (1 - disc), 2)


def out(s: School, students: int = 0, admins: int = 0):
    return {"id": s.id, "name": s.name, "board": s.board, "medium": s.medium, "city": s.city,
            "contact_name": s.contact_name, "contact_email": s.contact_email, "academic_year": s.academic_year,
            "plan_id": s.plan_id, "plan": s.plan.name if s.plan else "", "seats": s.seats,
            "discount_id": s.discount_id, "discount": s.discount.code if s.discount else "",
            "status": s.status, "students": students, "admins": admins,
            "annual_value": annual_value(s), "created_at": s.created_at}


def counts(db: Session):
    rows = db.query(User.school_id, User.role, func.count()).filter(User.school_id.isnot(None)).group_by(User.school_id, User.role).all()
    c = {}
    for sid, role, n in rows:
        c.setdefault(sid, {})[role] = n
    return c


@router.get("")
def list_schools(db: Session = Depends(get_db), _=Depends(super_admin)):
    c = counts(db)
    return [out(s, c.get(s.id, {}).get("student", 0), c.get(s.id, {}).get("admin", 0))
            for s in db.query(School).order_by(School.name).all()]


@router.post("")
def create_school(body: SchoolIn, db: Session = Depends(get_db), me=Depends(super_admin)):
    s = School(**body.model_dump())
    db.add(s); db.flush()
    log(db, me, "school.create", "school", s.id, name=s.name)
    db.commit(); db.refresh(s)
    return out(s)


@router.put("/{sid}")
def update_school(sid: int, body: SchoolIn, db: Session = Depends(get_db), me=Depends(super_admin)):
    s = db.get(School, sid)
    if not s:
        raise HTTPException(404, "School not found")
    data = body.model_dump()
    students = db.query(User).filter(User.school_id == sid, User.role == "student").count()
    if data["seats"] < students:
        raise HTTPException(422, f"Seats cannot be below the {students} students already enrolled")
    for k, v in data.items():
        setattr(s, k, v)
    log(db, me, "school.update", "school", sid, **{k: v for k, v in data.items() if k in ("plan_id", "seats", "status", "discount_id")})
    db.commit(); db.refresh(s)
    c = counts(db).get(sid, {})
    return out(s, c.get("student", 0), c.get("admin", 0))


@router.delete("/{sid}")
def delete_school(sid: int, db: Session = Depends(get_db), me=Depends(super_admin)):
    s = db.get(School, sid)
    if not s:
        raise HTTPException(404, "School not found")
    if db.query(User).filter(User.school_id == sid).count():
        raise HTTPException(409, "Remove this school's admins and students first, or suspend the school instead")
    log(db, me, "school.delete", "school", sid, name=s.name)
    db.delete(s); db.commit()
    return {"ok": True}
