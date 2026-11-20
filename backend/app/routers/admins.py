import secrets
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User, School
from ..schemas import AdminIn, AdminPatch
from ..security import super_admin, hash_pw
from ..audit import log

router = APIRouter(prefix="/api/admins", tags=["admins"])


def out(u: User):
    return {"id": u.id, "name": u.name, "email": u.email, "phone": u.phone, "status": u.status,
            "school_id": u.school_id, "school": u.school.name if u.school else "",
            "created_at": u.created_at, "last_login": u.last_login}


@router.get("")
def list_admins(q: str = "", db: Session = Depends(get_db), _=Depends(super_admin)):
    query = db.query(User).filter(User.role == "admin")
    if q:
        like = f"%{q.lower()}%"
        query = query.filter((User.name.ilike(like)) | (User.email.ilike(like)))
    return [out(u) for u in query.order_by(User.created_at.desc()).all()]


@router.post("")
def create_admin(body: AdminIn, db: Session = Depends(get_db), me=Depends(super_admin)):
    email = body.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "An account with this email already exists")
    if not db.get(School, body.school_id):
        raise HTTPException(404, "School not found")
    pw = body.password or secrets.token_urlsafe(9)
    u = User(name=body.name, email=email, phone=body.phone, role="admin", school_id=body.school_id, password_hash=hash_pw(pw))
    db.add(u); db.flush()
    log(db, me, "admin.create", "user", u.id, email=email, school_id=body.school_id)
    db.commit(); db.refresh(u)
    return {**out(u), "temp_password": pw}


@router.patch("/{uid}")
def update_admin(uid: int, body: AdminPatch, db: Session = Depends(get_db), me=Depends(super_admin)):
    u = db.get(User, uid)
    if not u or u.role != "admin":
        raise HTTPException(404, "Admin not found")
    changes = body.model_dump(exclude_none=True)
    if "status" in changes and changes["status"] not in ("active", "suspended"):
        raise HTTPException(422, "Status must be active or suspended")
    for k, v in changes.items():
        setattr(u, k, v)
    log(db, me, "admin.update", "user", uid, **changes)
    db.commit(); db.refresh(u)
    return out(u)


@router.post("/{uid}/reset-password")
def reset_password(uid: int, db: Session = Depends(get_db), me=Depends(super_admin)):
    u = db.get(User, uid)
    if not u or u.role != "admin":
        raise HTTPException(404, "Admin not found")
    pw = secrets.token_urlsafe(9)
    u.password_hash = hash_pw(pw)
    log(db, me, "admin.reset_password", "user", uid)
    db.commit()
    return {"temp_password": pw}


@router.delete("/{uid}")
def delete_admin(uid: int, db: Session = Depends(get_db), me=Depends(super_admin)):
    u = db.get(User, uid)
    if not u or u.role != "admin":
        raise HTTPException(404, "Admin not found")
    log(db, me, "admin.delete", "user", uid, email=u.email)
    db.delete(u); db.commit()
    return {"ok": True}
