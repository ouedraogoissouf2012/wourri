from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.auth import read_session, sign_session, verify

router = APIRouter(prefix="/auth")


class LoginBody(BaseModel):
    user: str = Field(min_length=1)
    password: str = Field(min_length=8)

    model_config = {"json_schema_extra": {"examples": [{"user": "provider.bci", "password": "change-me-8chars"}]}}


def current_user(request: Request) -> dict:
    sess = read_session(request.cookies.get(get_settings().lqe_cookie_name))
    if not sess:
        raise HTTPException(status_code=401, detail="session")
    return sess


@router.post("/login")
def login(body: LoginBody, response: Response):
    acc = verify(body.user, body.password)
    if not acc:
        raise HTTPException(status_code=401, detail="invalid")
    token = sign_session(acc["user"], acc["language"])
    response.set_cookie(
        get_settings().lqe_cookie_name,
        token,
        httponly=True,
        samesite="lax",
        max_age=12 * 3600,
    )
    return {"user": acc["user"], "language": acc["language"]}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(get_settings().lqe_cookie_name)
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return {"user": user["u"], "language": user["lang"]}

