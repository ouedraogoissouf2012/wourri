from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.data.languages import known_languages
from app.data.roles import ALL_ROLES
from app.routers.session import require_role
from app.services import users as users_svc

router = APIRouter(prefix="/accounts")


class CreateBody(BaseModel):
    user: str = Field(min_length=1)
    password: str = Field(min_length=8)
    language: str = Field(min_length=1)
    roles: list[str] = Field(default_factory=lambda: ["review"])


class PatchBody(BaseModel):
    roles: list[str] | None = None
    language: str | None = None
    active: bool | None = None
    password: str | None = None


@router.get("")
def list_accounts(_: dict = Depends(require_role("admin"))):
    return {"accounts": users_svc.list_public(), "languages": known_languages(), "roles": list(ALL_ROLES)}


@router.post("")
def create_account(body: CreateBody, _: dict = Depends(require_role("admin"))):
    result = users_svc.create_user(
        user=body.user, password=body.password, language=body.language, roles=body.roles
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("reason"))
    return result


@router.patch("/{username}")
def patch_account(username: str, body: PatchBody, _: dict = Depends(require_role("admin"))):
    result = users_svc.update_user(
        username,
        roles=body.roles,
        language=body.language,
        active=body.active,
        password=body.password,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("reason"))
    return result
