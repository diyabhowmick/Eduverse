"""Audit log. Entries are chained: each carries a hash of its own content and of the entry before it,
so editing or deleting a past entry is detectable (GET /api/platform/audit/verify)."""
import hashlib, json, threading
from datetime import datetime
from sqlalchemy.orm import Session
from .models import AuditLog, User

_lock = threading.Lock()


def _digest(prev: str, e: AuditLog) -> str:
    body = json.dumps([prev, e.at.isoformat(timespec="seconds") if e.at else "", e.actor_email, e.actor_role, e.action, e.target_type,
                       e.target_id, e.detail], sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(body.encode()).hexdigest()


def log(db: Session, actor: User, action: str, target_type: str, target_id="", **detail):
    with _lock:
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            from sqlalchemy import text
            db.execute(text("SELECT pg_advisory_xact_lock(7342001)"))   # one writer at a time across every API copy
        last = db.query(AuditLog.hash).filter(AuditLog.hash != "").order_by(AuditLog.id.desc()).first()
        prev = last[0] if last else ""
        e = AuditLog(at=datetime.utcnow().replace(microsecond=0), actor_email=actor.email, actor_role=actor.role, action=action,
                     target_type=target_type, target_id=str(target_id), detail=detail, prev_hash=prev)
        e.hash = _digest(prev, e)
        db.add(e)
        db.flush()


def verify(db: Session, limit: int = 200000) -> dict:
    """Walks the chain. Entries written before chaining existed (no hash) are skipped."""
    prev, n, broken = "", 0, None
    for e in db.query(AuditLog).filter(AuditLog.hash != "").order_by(AuditLog.id).limit(limit).yield_per(2000):
        if e.prev_hash != prev or _digest(e.prev_hash, e) != e.hash:
            broken = {"id": e.id, "at": e.at, "action": e.action}
            break
        prev, n = e.hash, n + 1
    return {"checked": n, "intact": broken is None, "first_break": broken}
