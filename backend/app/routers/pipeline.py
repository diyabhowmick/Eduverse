"""Settings for the book pipeline: M1 (extraction) and M2 (figure regeneration). Super Admin only."""
import base64, copy
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Setting
from ..security import platform_admin
from ..audit import log
from .. import m1, m2
from ..defaults import M2

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


def _save(db, key, value, me, **detail):
    s = db.get(Setting, key)
    if s:
        s.value = value
    else:
        db.add(Setting(key=key, value=value))
    log(db, me, f"settings.{key}", "setting", key, **detail)
    db.commit()


# ---------- M1 ----------
def m1_view(db):
    ov = m1.stored(db)
    return {"fields": m1.fields(), "groups": m1.GROUPS, "values": m1.masked(m1.effective(db)),
            "changed": sorted(ov.keys())}


def _unmask(db, values: dict) -> dict:
    cur = m1.effective(db)
    for k in m1.SECRETS:
        if values.get(k) == "saved":
            values[k] = cur.get(k, "")
    return values


@router.get("/m1")
def get_m1(db: Session = Depends(get_db), _=Depends(platform_admin)):
    return m1_view(db)


@router.put("/m1")
def put_m1(values: dict, db: Session = Depends(get_db), me=Depends(platform_admin)):
    try:
        ov = m1.clean_overrides(_unmask(db, dict(values)))
    except ValueError as e:
        raise HTTPException(422, str(e))
    if ov.get("provider") == "openai" and not ov.get("openai_api_key") and not ov.get("offline"):
        raise HTTPException(422, "OpenAI is selected: add the OpenAI API key")
    _save(db, "m1", {"overrides": ov}, me, changed=sorted(k for k in ov if k not in m1.SECRETS))
    return m1_view(db)


@router.post("/m1/reset")
def reset_m1(body: dict | None = None, db: Session = Depends(get_db), me=Depends(platform_admin)):
    """Reset one field (body {"field": name}) or everything to M1's own defaults."""
    ov = m1.stored(db)
    name = (body or {}).get("field")
    if name:
        ov.pop(name, None)
    else:
        ov = {}
    _save(db, "m1", {"overrides": ov}, me, reset=name or "all")
    return m1_view(db)


@router.post("/m1/check")
def check_m1(values: dict | None = None, db: Session = Depends(get_db), _=Depends(platform_admin)):
    """Is the model reachable and can it see an image? Uses the values on screen, saved or not."""
    vals = m1.effective(db)
    if values:
        try:
            vals = {**m1.defaults(), **m1.clean_overrides(_unmask(db, dict(values)))}
        except ValueError as e:
            raise HTTPException(422, str(e))
    try:
        return m1.check_models(vals)
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


# ---------- M2 ----------
@router.get("/m2")
def get_m2(db: Session = Depends(get_db), _=Depends(platform_admin)):
    return {"values": m2.masked(m2.settings_of(db)), "defaults": m2.masked(M2)}


@router.put("/m2")
def put_m2(value: dict, db: Session = Depends(get_db), me=Depends(platform_admin)):
    cur = m2.settings_of(db)
    v = copy.deepcopy(value)
    for name, p in (v.get("providers") or {}).items():
        if p.get("api_key") == "saved":
            p["api_key"] = cur["providers"].get(name, {}).get("api_key", "")
    if v.get("provider") not in ("openai", "gemini", "local"):
        raise HTTPException(422, "Image provider must be openai, gemini or local")
    try:
        v["max_images_per_book"] = max(0, int(v.get("max_images_per_book", 100)))
        v["timeout_s"] = max(10, int(v.get("timeout_s", 180)))
    except (TypeError, ValueError):
        raise HTTPException(422, "Limits must be whole numbers")
    size = str(v.get("size", "auto")).lower()
    if size != "auto":
        try:
            w, h = (int(x) for x in size.split("x"))
            assert 256 <= w <= 4096 and 256 <= h <= 4096
        except Exception:
            raise HTTPException(422, "Size must be auto or like 1024x1024")
    v["size"] = size
    _save(db, "m2", v, me, provider=v["provider"], enabled=bool(v.get("enabled")))
    return get_m2(db)


@router.post("/m2/reset")
def reset_m2(db: Session = Depends(get_db), me=Depends(platform_admin)):
    cur = m2.settings_of(db)
    v = copy.deepcopy(M2)
    for n, p in v["providers"].items():  # keep saved keys
        p["api_key"] = cur["providers"].get(n, {}).get("api_key", "")
    _save(db, "m2", v, me, reset="all")
    return get_m2(db)


@router.post("/m2/test")
def test_m2(db: Session = Depends(get_db), _=Depends(platform_admin)):
    """Generate one small test picture with the saved settings (this uses one image from the provider)."""
    cfg = m2.settings_of(db)
    ok, why = m2.ready(cfg)
    if not ok:
        return {"ok": False, "error": why}
    try:
        png = m2._png(m2.generate(cfg["style_prompt"] + "\nDraw a simple labelled diagram of a lit candle. Label: \"flame\".",
                                  1024, 1024, cfg), cap=512)
        return {"ok": True, "image": "data:image/png;base64," + base64.b64encode(png).decode()}
    except Exception as e:
        return {"ok": False, "error": str(e)[:400]}
