import copy
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Setting
from ..security import super_admin
from ..audit import log
from ..defaults import ALL

router = APIRouter(prefix="/api/settings", tags=["settings"])
SECRET_FIELDS = ("api_key",)


def mask(v):
    v = copy.deepcopy(v)
    for p in (v.get("providers") or {}).values():
        if p.get("api_key"):
            p["api_key"] = "saved"
    return v


@router.get("/{key}")
def get_setting(key: str, db: Session = Depends(get_db), _=Depends(super_admin)):
    if key not in ALL:
        raise HTTPException(404, "Unknown setting")
    s = db.get(Setting, key)
    val = s.value if s else ALL[key]
    return mask(val) if key == "ai" else val


@router.put("/{key}")
def put_setting(key: str, value: dict, db: Session = Depends(get_db), me=Depends(super_admin)):
    if key not in ALL:
        raise HTTPException(404, "Unknown setting")
    s = db.get(Setting, key)
    if key == "ai" and s:  # keep saved keys when the client sends the mask back
        for name, p in (value.get("providers") or {}).items():
            if p.get("api_key") == "saved":
                p["api_key"] = s.value["providers"][name].get("api_key", "")
        if value.get("provider") not in ("ollama", "anthropic", "openai"):
            raise HTTPException(422, "Provider must be ollama, anthropic or openai")
    if key == "permissions":
        for perm, roles in value.items():
            if "super_admin" not in roles and perm.startswith("manage_"):
                raise HTTPException(422, "Super Admin must keep every manage permission")
    if s:
        s.value = value
    else:
        db.add(Setting(key=key, value=value))
    log(db, me, f"settings.{key}", "setting", key)
    db.commit()
    return mask(value) if key == "ai" else value
