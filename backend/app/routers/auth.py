from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User, Setting
from ..schemas import LoginIn, SignupIn
from ..security import check_pw, make_token, current_user, hash_pw
from ..defaults import FEATURES
from ..audit import log

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower().strip()).first()
    if not user or not check_pw(body.password, user.password_hash):
        raise HTTPException(401, "Email or password is wrong")
    if user.role != body.portal:
        raise HTTPException(403, "This account cannot sign in here. Use your own login page.")
    if user.status != "active":
        raise HTTPException(403, "This account is suspended")
    # Organisation accounts need an active organisation. An individual learner (B2C) has none, and needs none.
    if user.role in ("admin", "teacher") or (user.role == "student" and user.school_id):
        if not user.school or user.school.status != "active":
            raise HTTPException(403, "Your organisation's access is paused. Contact EduVerse support.")
    user.last_login = datetime.utcnow()
    log(db, user, "login", "user", user.id)
    db.commit()
    return {"token": make_token(user), "user": {"id": user.id, "name": user.name, "email": user.email, "role": user.role, "school": user.school.name if user.school else ""}}


@router.post("/signup")
def signup(body: SignupIn, db: Session = Depends(get_db)):
    """An individual learner creates their own student account (B2C). Organisation students are still added by their admin."""
    f = db.get(Setting, "features")
    if not {**FEATURES, **(f.value if f else {})}.get("public_signup", True):
        raise HTTPException(403, "Sign up is closed. Ask your school or college for an account.")
    email = body.email.lower().strip()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(422, "Enter a valid email")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")
    if body.track not in ("textbook", "exam") or body.level not in ("school", "degree", "competitive"):
        raise HTTPException(422, "Pick what you are studying")
    prof = {k: (getattr(body, k) or "").strip() for k in ("track", "level", "board", "grade", "exam", "university", "course")}
    u = User(email=email, name=body.name.strip(), role="student", phone=body.phone.strip(), password_hash=hash_pw(body.password),
             profile=prof, signup="self", last_login=datetime.utcnow())
    db.add(u); db.flush()
    log(db, u, "student.signup", "user", u.id, **prof)
    db.commit()
    return {"token": make_token(u), "user": {"id": u.id, "name": u.name, "email": u.email, "role": u.role, "school": ""}}


@router.post("/refresh")
def refresh(user: User = Depends(current_user)):
    """A fresh token for someone still working, so an active session never runs out."""
    return {"token": make_token(user)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role}
