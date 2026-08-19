from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.routers.session import current_user
from app.services import workflow

router = APIRouter(prefix="/corpus")


class PromoteBody(BaseModel):
    id: str = Field(min_length=1)


@router.get("")
def get_corpus(user: dict = Depends(current_user)):
    lang = user["lang"]
    rows = workflow.list_corpus(language=lang)
    return {
        "language": lang,
        "entries": rows,
        "count": len(rows),
        "with_audio": sum(1 for r in rows if r.get("audio_url")),
    }


@router.post("/promote")
def post_promote(body: PromoteBody, user: dict = Depends(current_user)):
    result = workflow.promote(body.id, language=user["lang"], actor=user["u"])
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("reason"))
    return result
