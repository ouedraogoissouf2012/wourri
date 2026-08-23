from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.data.language_registry import is_known
from app.routers.session import current_user, require_role
from app.services import assignments
from app.services.pg_catalog import PgCorpusCatalog

router = APIRouter(prefix="/assignments")


class AssignBody(BaseModel):
    target_language: str = Field(min_length=1)
    concept_ids: list[str] = Field(min_length=1)


@router.get("")
def get_my_assignments(user: dict = Depends(current_user)):
    """Assignations OUVERTES de la langue de session (isolation par langue)."""
    lang = user["lang"]
    rows = assignments.list_open(language=lang)
    return {"language": lang, "assignments": rows, "count": len(rows)}


@router.post("")
def post_assign(body: AssignBody, user: dict = Depends(require_role("admin"))):
    lang = body.target_language.strip().lower()
    if not is_known(lang):
        raise HTTPException(status_code=400, detail="unknown_language")
    return assignments.assign_batch(
        body.concept_ids, target_language=lang, assigned_by=user["u"],
        catalog=PgCorpusCatalog(),
    )


@router.get("/missing")
def get_missing(language: str, _: dict = Depends(require_role("admin"))):
    lang = language.strip().lower()
    if not is_known(lang):
        raise HTTPException(status_code=400, detail="unknown_language")
    rows = assignments.missing_to_assign(PgCorpusCatalog(), language=lang)
    return {"language": lang, "concepts": rows, "count": len(rows)}
