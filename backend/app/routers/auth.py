from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User
from ..schemas import LoginIn
from ..security import check_pw, make_token, current_user
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
    if user.role in ("admin", "student", "teacher") and (not user.school or user.school.status != "active"):
        raise HTTPException(403, "Your school's access is paused. Contact EduVerse support.")
    user.last_login = datetime.utcnow()
    log(db, user, "login", "user", user.id)
    db.commit()
    return {"token": make_token(user), "user": {"id": user.id, "name": user.name, "email": user.email, "role": user.role, "school": user.school.name if user.school else ""}}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role}
