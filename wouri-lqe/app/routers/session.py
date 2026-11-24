from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.config import get_settings
from app.data.language_registry import is_known
from app.services.auth import read_session, session_has, sign_session, verify

router = APIRouter(prefix="/auth")


class LoginBody(BaseModel):
    user: str = Field(min_length=1)
    password: str = Field(min_length=8)


def current_user(request: Request) -> dict:
    sess = read_session(request.cookies.get(get_settings().lqe_cookie_name))
    if not sess:
        raise HTTPException(status_code=401, detail="session")
    return sess


def require_role(role: str):
    def _inner(user: dict = Depends(current_user)) -> dict:
        if not session_has(user, role):
            raise HTTPException(status_code=403, detail="forbidden")
        return user
    return _inner


def langue_visee(user: dict, demandee: str | None) -> str:
    """Langue visée : celle de la session, ou celle qu'un **admin** nomme (ADR-0034).

    Un compte admin porte toujours la langue `*` (`users.create_user` l'impose) : sans
    ce paramètre il ne verrait aucune fiche et ne pourrait reposer aucune question, le
    dépôt filtrant en égalité stricte. Le paramètre ne perce pas l'isolation entre
    locuteurs — un compte sans le rôle `admin` est refusé, même pour sa propre langue.

    Ne renvoie jamais `*` (#637) : cette valeur ne vise aucune fiche, et la renvoyer
    faisait répondre « 200, rien » — on croyait le locuteur sans travail. La garde porte
    sur la VALEUR, pas sur le rôle : `users.update_user` garde la langue quand seuls les
    rôles changent, un admin rétrogradé porte donc encore `*`.
    """
    if demandee is None:
        if user["lang"] == "*":
            raise HTTPException(status_code=400, detail="language_required")
        return user["lang"]
    if not session_has(user, "admin"):
        raise HTTPException(status_code=403, detail="forbidden")
    lang = demandee.strip().lower()
    if not is_known(lang):
        raise HTTPException(status_code=400, detail="unknown_language")
    return lang


@router.post("/login")
def login(body: LoginBody, response: Response):
    acc = verify(body.user, body.password)
    if not acc:
        raise HTTPException(status_code=401, detail="invalid")
    token = sign_session(acc["user"], acc["language"], acc["roles"])
    settings = get_settings()
    response.set_cookie(
        settings.lqe_cookie_name,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.is_prod(),
        max_age=12 * 3600,
    )
    return {"user": acc["user"], "language": acc["language"], "roles": acc["roles"]}


@router.post("/logout")
def logout(response: Response):
    settings = get_settings()
    response.delete_cookie(
        settings.lqe_cookie_name, samesite="lax", secure=settings.is_prod()
    )
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return {"user": user["u"], "language": user["lang"], "roles": user.get("roles") or []}
