from sqlalchemy.orm import Session
from .models import AuditLog, User


def log(db: Session, actor: User, action: str, target_type: str, target_id="", **detail):
    db.add(AuditLog(actor_email=actor.email, actor_role=actor.role, action=action,
                    target_type=target_type, target_id=str(target_id), detail=detail))
