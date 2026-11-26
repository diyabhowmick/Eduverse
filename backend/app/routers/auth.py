import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User, Setting
from ..schemas import LoginIn, SignupIn
from ..security import check_pw, make_token, current_user, hash_pw, set_session_cookie, COOKIE
from ..defaults import FEATURES
from ..audit import log
from .. import hardening as H

router = APIRouter(prefix="/api/auth", tags=["auth"])


_DUMMY = hash_pw("not-a-real-password-just-for-timing")
LOCK_AFTER, LOCK_MIN = 8, 15
WRONG = "Email or password is wrong, or this is not the sign-in page for your account"


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    ip = H.client_ip(request)
    # A whole school signs in from one address (one internet connection). 30 an address per 10 minutes let 30 of a
    # school's students in and locked the rest out for the period. Guessing is stopped per account instead
    # (12 tries an email per 15 minutes, and 8 wrong passwords lock the account).
    H.guard("login-ip:" + ip, int(os.getenv("LOGIN_PER_IP_10MIN", "600")), 600)
    H.guard("login-email:" + email, 12, 900)
    user = db.query(User).filter(User.email == email).first()
    if not user:
        check_pw(body.password, _DUMMY)   # same time as a real check, so timing does not reveal which emails exist
        raise HTTPException(401, WRONG)
    if user.locked_until and user.locked_until > datetime.utcnow():
        raise HTTPException(429, "Too many wrong passwords. This account is locked for a few minutes.")
    if not check_pw(body.password, user.password_hash):
        user.failed_logins = (user.failed_logins or 0) + 1
        if user.failed_logins >= LOCK_AFTER:
            user.locked_until, user.failed_logins = datetime.utcnow() + timedelta(minutes=LOCK_MIN), 0
            log(db, user, "login.locked", "user", user.id, ip=ip)
        db.commit()
        raise HTTPException(401, WRONG)
    if user.role != body.portal:
        # Same answer as a wrong password. A different answer told anyone guessing that the password was right.
        raise HTTPException(401, WRONG)
    if user.status != "active":
        raise HTTPException(403, "This account is suspended")
    # Organisation accounts need an active organisation. An individual learner (B2C) has none, and needs none.
    if user.role in ("admin", "teacher") or (user.role == "student" and user.school_id):
        if not user.school or user.school.status != "active":
            raise HTTPException(403, "Your organisation's access is paused. Contact EduVerse support.")
    user.last_login, user.failed_logins, user.locked_until = datetime.utcnow(), 0, None
    H.limiter.clear("login-email:" + email)
    log(db, user, "login", "user", user.id, ip=ip)
    db.commit()
    tok = make_token(user); set_session_cookie(response, tok, request)
    return {"token": tok, "user": {"id": user.id, "name": user.name, "email": user.email, "role": user.role, "school": user.school.name if user.school else "",
                                                "nickname": (user.profile or {}).get("nickname", "") if hasattr(user, "profile") else ""}}


@router.post("/signup")
def signup(body: SignupIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """An individual learner creates their own student account (B2C). Organisation students are still added by their admin."""
    f = db.get(Setting, "features")
    if not {**FEATURES, **(f.value if f else {})}.get("public_signup", True):
        raise HTTPException(403, "Sign up is closed. Ask your school or college for an account.")
    ip = H.client_ip(request)
    H.guard("signup-ip:" + ip, 6, 3600, "Too many sign ups from this network. Try again later.")
    email = body.email.lower().strip()
    if not (any(c.isalpha() for c in body.password) and any(c.isdigit() for c in body.password)):
        raise HTTPException(422, "Use at least 8 characters with letters and numbers")
    if not body.consent:
        raise HTTPException(422, "Please agree to the terms and privacy notice")
    if body.age_group not in ("adult", "minor"):
        raise HTTPException(422, "Tell us whether you are 18 or older")
    g_email = body.guardian_email.lower().strip()
    if body.age_group == "minor" and (len(body.guardian_name.strip()) < 2 or "@" not in g_email or g_email == body.email.lower().strip()):
        raise HTTPException(422, "Under 18: a parent or guardian must agree, with their own name and email")
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(422, "Enter a valid email")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")
    if body.track not in ("textbook", "exam") or body.level not in ("school", "degree", "competitive"):
        raise HTTPException(422, "Pick what you are studying")
    prof = {k: (getattr(body, k) or "").strip() for k in ("track", "level", "board", "grade", "exam", "university", "course")}
    # A record of consent: who agreed, when, from where. A minor's account carries their guardian's consent.
    prof["consent"] = {"by": "guardian" if body.age_group == "minor" else "self", "guardian_name": body.guardian_name.strip()[:120] if body.age_group == "minor" else "",
                       "guardian_email": g_email if body.age_group == "minor" else "", "at": datetime.utcnow().isoformat(timespec="seconds"), "ip": ip, "version": "2026-11"}
    u = User(email=email, name=body.name.strip(), role="student", phone=body.phone.strip(), password_hash=hash_pw(body.password),
             profile=prof, signup="self", last_login=datetime.utcnow())
    db.add(u); db.flush()
    log(db, u, "student.signup", "user", u.id, **{k: v for k, v in prof.items() if k != "consent"}, consent_by=prof["consent"]["by"])
    db.commit()
    tok = make_token(u); set_session_cookie(response, tok, request)
    return {"token": tok, "user": {"id": u.id, "name": u.name, "email": u.email, "role": u.role, "school": ""}}


@router.post("/refresh")
def refresh(request: Request, response: Response, user: User = Depends(current_user)):
    """A fresh token for someone still working, so an active session never runs out."""
    tok = make_token(user); set_session_cookie(response, tok, request)
    return {"token": tok}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/api")
    response.delete_cookie(COOKIE, path="/api/content")   # set by builds before v48
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role}
