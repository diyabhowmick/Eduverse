"""Super Admin side of school requests."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import SchoolRequest, Plan
from ..security import super_admin
from ..audit import log
from .school import req_out

router = APIRouter(prefix="/api/requests", tags=["requests"])


class Decision(BaseModel):
    response: str = ""


@router.get("")
def all_requests(status: str = "", db: Session = Depends(get_db), _=Depends(super_admin)):
    q = db.query(SchoolRequest)
    if status:
        q = q.filter(SchoolRequest.status == status)
    return [req_out(r) for r in q.order_by(SchoolRequest.status != "open", SchoolRequest.created_at.desc())]


@router.post("/{rid}/{decision}")
def decide(rid: int, decision: str, body: Decision, db: Session = Depends(get_db), me=Depends(super_admin)):
    r = db.get(SchoolRequest, rid)
    if not r:
        raise HTTPException(404, "Request not found")
    if r.status != "open":
        raise HTTPException(409, "This request is already closed")
    if decision not in ("approve", "decline"):
        raise HTTPException(404, "Unknown decision")
    if decision == "approve":
        s = r.school
        if r.kind == "seats":
            s.seats += int(r.detail.get("seats", 0))
        elif r.kind == "plan":
            if not db.get(Plan, r.detail.get("plan_id", 0)):
                raise HTTPException(409, "That plan no longer exists")
            s.plan_id = r.detail["plan_id"]
    r.status = "approved" if decision == "approve" else "declined"
    r.response, r.resolved_at = body.response.strip(), datetime.utcnow()
    log(db, me, f"request.{decision}", "request", rid, school=r.school.name, kind=r.kind, **r.detail)
    db.commit()
    return req_out(r)
