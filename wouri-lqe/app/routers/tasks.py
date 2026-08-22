from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.routers.session import current_user, require_role
from app.services import workflow

router = APIRouter(prefix="/tasks")


class DecisionBody(BaseModel):
    id: str = Field(min_length=1)
    decision: str


@router.get("")
def get_tasks(user: dict = Depends(current_user)):
    lang = user["lang"]
    return {
        "language": lang,
        "bronze": workflow.list_tasks(language=lang, status="bronze"),
        "accepted": workflow.list_tasks(language=lang, status="admin_accepted"),
    }


@router.post("/decision")
def post_decision(body: DecisionBody, user: dict = Depends(require_role("review"))):
    result = workflow.decide(body.id, body.decision, language=user["lang"])
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("reason"))
    return result

