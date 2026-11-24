import copy, os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Setting
from ..security import super_admin
from ..audit import log
from ..defaults import ALL
from ..llm_client import openai_json

router = APIRouter(prefix="/api/settings", tags=["settings"])
SECRET_FIELDS = ("api_key",)


def mask(v):
    v = copy.deepcopy(v)
    for p in (v.get("providers") or {}).values():
        if p.get("api_key"):
            p["api_key"] = "saved"
    return v


def openai_conf(db):
    s = db.get(Setting, "ai")
    ai = s.value if s else ALL["ai"]
    p = ai["providers"]["openai"]
    source = "saved" if p.get("api_key") else "env" if os.getenv("OPENAI_API_KEY") else ""
    return p, ai.get("exam_model") or ALL["ai"]["exam_model"], source


@router.get("/openai/status")
def openai_status(db: Session = Depends(get_db), _=Depends(super_admin)):
    _p, model, source = openai_conf(db)
    return {"has_key": bool(source), "source": source, "exam_model": model}


@router.post("/openai/test")
def openai_test(db: Session = Depends(get_db), _=Depends(super_admin)):
    """Sends one tiny request, so a wrong key, model or blocked connection shows up here and not halfway through a paper."""
    p, model, source = openai_conf(db)
    if not source:
        raise HTTPException(422, "No OpenAI key yet. Paste one here and save, or set OPENAI_API_KEY in backend/.env and restart.")
    try:
        openai_json(model, 'Reply with the JSON object {"ok": true}', base_url=p.get("base_url"), api_key=p.get("api_key") or None, timeout=45)
    except Exception as e:
        raise HTTPException(502, f"The test failed. {str(e)[:300]}")
    return {"ok": True, "model": model, "source": source}


@router.get("/{key}")
def get_setting(key: str, db: Session = Depends(get_db), _=Depends(super_admin)):
    if key not in ALL:
        raise HTTPException(404, "Unknown setting")
    s = db.get(Setting, key)
    val = s.value if s else ALL[key]
    if key == "ai":   # settings saved before a new section existed still show it, with its defaults
        val = {**ALL["ai"], **val, "prestore": {**ALL["ai"]["prestore"], **(val.get("prestore") or {})}}
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
