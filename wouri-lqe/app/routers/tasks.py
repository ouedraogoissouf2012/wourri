from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.data.language_registry import is_known
from app.routers.session import current_user, require_role
from app.services import workflow
from app.services.auth import session_has

router = APIRouter(prefix="/tasks")


def _langue(user: dict, demandee: str | None) -> str:
    """Langue visée : celle de la session, ou celle qu'un **admin** nomme (ADR-0034).

    Un compte admin porte toujours la langue `*` (`users.create_user` l'impose) : sans
    ce paramètre il ne verrait aucune fiche et ne pourrait reposer aucune question, le
    dépôt filtrant en égalité stricte. Le paramètre ne perce pas l'isolation entre
    locuteurs — un compte sans le rôle `admin` est refusé, même pour sa propre langue.
    """
    if demandee is None:
        return user["lang"]
    if not session_has(user, "admin"):
        raise HTTPException(status_code=403, detail="forbidden")
    lang = demandee.strip().lower()
    if not is_known(lang):
        raise HTTPException(status_code=400, detail="unknown_language")
    return lang


class DecisionBody(BaseModel):
    id: str = Field(min_length=1)
    decision: str


class ReexamenBody(BaseModel):
    id: str = Field(min_length=1)
    motif: str = Field(min_length=1)
    # Admin seulement : la langue visée, puisque sa session porte `*` (voir `_langue`).
    language: str | None = None


class EditBody(BaseModel):
    id: str = Field(min_length=1)
    text_local: str = Field(min_length=1)
    text_fr: str = ""
    # paire question/reponse seulement : la reponse proposee corrigee (ADR-0045)
    reponse_bci: str | None = None
    reponse_fr: str | None = None


@router.get("")
def get_tasks(language: str | None = None, user: dict = Depends(current_user)):
    lang = _langue(user, language)
    return {
        "language": lang,
        "bronze": workflow.list_tasks(language=lang, status="bronze"),
        "accepted": workflow.list_tasks(language=lang, status="admin_accepted"),
        "decided": workflow.list_decided(language=lang),
    }


@router.get("/validations")
def get_validations(kind: str, user: dict = Depends(current_user)):
    """Mots-cles ou paires question/reponse de la langue du compte, tous statuts (ADR-0045).

    Sert a reconstruire le NLU depuis les seules decisions du locuteur."""
    lang = user["lang"]
    entries = workflow.list_validations(language=lang, kind=kind)
    return {"language": lang, "kind": kind, "entries": entries, "count": len(entries)}


@router.post("/decision")
def post_decision(body: DecisionBody, user: dict = Depends(require_role("review"))):
    result = workflow.decide(body.id, body.decision, language=user["lang"])
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("reason"))
    return result


class ReprendreBody(BaseModel):
    id: str = Field(min_length=1)


@router.post("/reprendre")
def post_reprendre(body: ReprendreBody, user: dict = Depends(require_role("review"))):
    """Le locuteur annule sa decision et sa correction : la fiche redevient « a valider »."""
    result = workflow.reprendre(body.id, language=user["lang"])
    if not result.get("ok"):
        code = 404 if result.get("reason") == "not_found" else 400
        raise HTTPException(status_code=code, detail=result.get("reason"))
    return result


@router.post("/reexamen")
def post_reexamen(body: ReexamenBody, user: dict = Depends(require_role("admin"))):
    """Repose une question au locuteur : la fiche redevient « a valider » avec le motif
    affiche (ADR-0047). Reserve a l'admin — c'est un relecteur qui repose la question.

    L'admin DOIT nommer la langue (`language`) : sa session porte `*`, qui ne vise
    aucune fiche. Sans ce champ l'appel ne peut que renvoyer 404 — voir `_langue`."""
    result = workflow.remettre_en_question(
        body.id, language=_langue(user, body.language), motif=body.motif,
    )
    if not result.get("ok"):
        code = 404 if result.get("reason") == "not_found" else 400
        raise HTTPException(status_code=code, detail=result.get("reason"))
    return result


@router.post("/edit")
def post_edit(body: EditBody, user: dict = Depends(require_role("review"))):
    result = workflow.edit_text(
        body.id, language=user["lang"],
        text_local=body.text_local, text_fr=body.text_fr,
        reponse_bci=body.reponse_bci, reponse_fr=body.reponse_fr,
    )
    if not result.get("ok"):
        code = 404 if result.get("reason") == "not_found" else 400
        raise HTTPException(status_code=code, detail=result.get("reason"))
    return result

