from datetime import datetime, timedelta
import bcrypt, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db
from .models import User

bearer = HTTPBearer(auto_error=False)


def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def check_pw(pw: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), h.encode())
    except ValueError:
        return False


def make_token(user: User) -> str:
    exp = datetime.utcnow() + timedelta(hours=settings.jwt_hours)
    return jwt.encode({"sub": str(user.id), "role": user.role, "tv": user.token_version or 0, "exp": exp, "iat": datetime.utcnow()},
                      settings.jwt_secret, algorithm="HS256")


def end_sessions(user: User):
    """Every token issued before this stops working: password reset, suspension, removal."""
    user.token_version = (user.token_version or 0) + 1


COOKIE = "ev_session"


def set_session_cookie(response, token: str, request=None):
    """The same token as an HttpOnly cookie that only goes to book images, so a plain <img> can load them
    while a script on the page can never read it."""
    secure = bool(request and (request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"))
    # Path /api: plain <img> tags for book pictures (/api/content) and original pages (/api/review/.../original.png)
    # carry it. Every other endpoint ignores the cookie and needs the Authorization header, so it adds no CSRF risk.
    response.set_cookie(COOKIE, token, max_age=settings.jwt_hours * 3600, httponly=True, samesite="strict", secure=secure, path="/api")


def current_user(cred: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not cred:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required")
    return user_from_token(cred.credentials, db)


def user_from_token(token: str, db: Session) -> User:
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired, sign in again")
    user = db.get(User, int(data["sub"]))
    if not user or user.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not active")
    if data.get("tv", 0) != (user.token_version or 0) or data.get("role") != user.role:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session ended, sign in again")
    if user.role in ("admin", "teacher") or (user.role == "student" and user.school_id):
        if not user.school or user.school.status != "active":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your organisation's access is paused")
    return user


def require(*roles):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed for your role")
        return user
    return dep


super_admin = require("super_admin")
