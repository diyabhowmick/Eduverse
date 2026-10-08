from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Plan, Discount, School
from ..schemas import PlanIn, DiscountIn
from ..security import super_admin
from ..audit import log

router = APIRouter(prefix="/api/pricing", tags=["pricing"])


def plan_out(p: Plan, db: Session):
    return {"id": p.id, "name": p.name, "price_per_seat": p.price_per_seat, "billing_cycle": p.billing_cycle,
            "credits_per_seat": p.credits_per_seat, "max_books": p.max_books, "features": p.features or {},
            "active": p.active, "schools": db.query(School).filter(School.plan_id == p.id).count()}


@router.get("/plans")
def plans(db: Session = Depends(get_db), _=Depends(super_admin)):
    return [plan_out(p, db) for p in db.query(Plan).order_by(Plan.price_per_seat).all()]


@router.post("/plans")
def create_plan(body: PlanIn, db: Session = Depends(get_db), me=Depends(super_admin)):
    if db.query(Plan).filter(Plan.name == body.name).first():
        raise HTTPException(409, "A plan with this name exists")
    p = Plan(**body.model_dump()); db.add(p); db.flush()
    log(db, me, "plan.create", "plan", p.id, name=p.name, price=p.price_per_seat)
    db.commit()
    return plan_out(p, db)


@router.put("/plans/{pid}")
def update_plan(pid: int, body: PlanIn, db: Session = Depends(get_db), me=Depends(super_admin)):
    p = db.get(Plan, pid)
    if not p:
        raise HTTPException(404, "Plan not found")
    old = p.price_per_seat
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    log(db, me, "plan.update", "plan", pid, name=p.name, price_from=old, price_to=p.price_per_seat)
    db.commit()
    return plan_out(p, db)


@router.delete("/plans/{pid}")
def delete_plan(pid: int, db: Session = Depends(get_db), me=Depends(super_admin)):
    p = db.get(Plan, pid)
    if not p:
        raise HTTPException(404, "Plan not found")
    if db.query(School).filter(School.plan_id == pid).count():
        raise HTTPException(409, "Schools are on this plan. Move them or mark the plan inactive.")
    log(db, me, "plan.delete", "plan", pid, name=p.name)
    db.delete(p); db.commit()
    return {"ok": True}


def disc_out(d: Discount):
    return {"id": d.id, "code": d.code, "percent": d.percent, "max_uses": d.max_uses, "used": d.used,
            "valid_until": d.valid_until, "active": d.active}


@router.get("/discounts")
def discounts(db: Session = Depends(get_db), _=Depends(super_admin)):
    return [disc_out(d) for d in db.query(Discount).order_by(Discount.code).all()]


@router.post("/discounts")
def create_discount(body: DiscountIn, db: Session = Depends(get_db), me=Depends(super_admin)):
    code = body.code.upper().strip()
    if db.query(Discount).filter(Discount.code == code).first():
        raise HTTPException(409, "This code exists")
    d = Discount(**{**body.model_dump(), "code": code}); db.add(d); db.flush()
    log(db, me, "discount.create", "discount", d.id, code=code, percent=d.percent)
    db.commit()
    return disc_out(d)


@router.put("/discounts/{did}")
def update_discount(did: int, body: DiscountIn, db: Session = Depends(get_db), me=Depends(super_admin)):
    d = db.get(Discount, did)
    if not d:
        raise HTTPException(404, "Discount not found")
    for k, v in body.model_dump().items():
        setattr(d, k, v.upper().strip() if k == "code" else v)
    log(db, me, "discount.update", "discount", did, code=d.code, percent=d.percent, active=d.active)
    db.commit()
    return disc_out(d)


@router.delete("/discounts/{did}")
def delete_discount(did: int, db: Session = Depends(get_db), me=Depends(super_admin)):
    d = db.get(Discount, did)
    if not d:
        raise HTTPException(404, "Discount not found")
    db.query(School).filter(School.discount_id == did).update({School.discount_id: None})
    log(db, me, "discount.delete", "discount", did, code=d.code)
    db.delete(d); db.commit()
    return {"ok": True}
