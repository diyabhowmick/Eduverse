"""Eddie's server voice. Any signed-in user; short texts only."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from ..security import current_user
from .. import voice as V

router = APIRouter(prefix="/api/voice", tags=["voice"])


@router.get("/status")
def status(_=Depends(current_user)):
    return V.status()


class SayIn(BaseModel):
    text: str


@router.post("/say")
def say(body: SayIn, _=Depends(current_user)):
    if len(body.text) > 600:
        raise HTTPException(422, "Too long for one go; send a sentence at a time")
    try:
        data, mime = V.say(body.text)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return Response(data, media_type=mime, headers={"Cache-Control": "private, max-age=86400"})
