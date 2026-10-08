"""Live explanations for the reader. Provider, model, keys and depth rules come from Super Admin AI settings."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Setting, School
from ..security import current_user
from ..defaults import AI
from ..explain_prompt import explain

router = APIRouter(prefix="/api", tags=["explain"])


class ExplainIn(BaseModel):
    term: str
    chapter: str = ""
    paragraph: str = ""
    definition: str = ""
    figures: list[str] = []
    depth: str = "concept_clarity"
    book: dict = {}
    book_id: int | None = None


@router.post("/explain")
def explain_term(body: ExplainIn, db: Session = Depends(get_db), user=Depends(current_user)):
    ai = (db.get(Setting, "ai").value if db.get(Setting, "ai") else AI)
    if user.role == "student":
        from .student import rules_for, day_row, count_explanation
        r = rules_for(db, user)
        if body.depth not in r["allowed_depths"]:
            body.depth = r["allowed_depths"][0]
        if day_row(db, user.id).explanations >= r["daily_limit"]:
            raise HTTPException(429, f"You have used today's {r['daily_limit']} explanations. They reset tomorrow.")
    import os
    provider = os.getenv("AI_PROVIDER_OVERRIDE") or ai["provider"]   # "mock" for offline testing only
    p = ai["providers"].get(provider, {"model": "test"})
    try:
        text = explain(provider, p["model"], body.term[:80], body.book, body.chapter, body.paragraph, body.definition,
                       body.figures[:3], body.depth, ai.get("depth_rules"), base_url=p.get("base_url"), api_key=p.get("api_key") or None)
    except Exception as e:
        raise HTTPException(502, f"The {ai['provider']} model did not answer: {str(e)[:160]}")
    if user.role == "student":
        count_explanation(db, user, body.book_id, tokens=len(text) // 4)
        db.commit()
    return {"text": text, "provider": provider, "model": p["model"], "depth": body.depth}
