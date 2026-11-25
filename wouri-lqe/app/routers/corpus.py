import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.routers.session import current_user, langue_du_locuteur, langue_visee, require_role
from app.services import assignments, workflow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/corpus")


class PromoteBody(BaseModel):
    id: str = Field(min_length=1)


@router.get("")
def get_corpus(language: str | None = None, user: dict = Depends(current_user)):
    """Corpus servi de la langue de session.

    `language` lit celui d'une AUTRE langue et est reserve aux admins, comme
    `/dictation/export` et `/assignments/missing`. Sans ce parametre le
    comportement ne change pas : un locuteur reste enferme dans sa langue
    (isolation inter-locuteurs, ADR-0034). C'est ce que `adc.admin` (langue `*`)
    doit passer pour construire les messages systeme d'une langue (ADR-0049) :
    sans lui il ne verrait rien, sa session n'etant liee a aucune langue : l'appel est
    alors refuse (400 `language_required`, #641) au lieu de repondre un corpus vide.
    Regle unique du service : `session.langue_visee`."""
    lang = langue_visee(user, language)
    rows = workflow.list_corpus(language=lang)
    return {
        "language": lang,
        "entries": rows,
        "count": len(rows),
        "with_audio": sum(1 for r in rows if r.get("audio_url")),
    }


@router.post("/promote")
def post_promote(body: PromoteBody, user: dict = Depends(require_role("promote"))):
    lang = langue_du_locuteur(user)
    result = workflow.promote(body.id, language=lang, actor=user["u"])
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("reason"))
    # ferme la boucle : si la production promue repond a une assignation, la marquer 'done'
    concept_id = (result.get("entry") or {}).get("concept_id")
    if concept_id:
        try:
            assignments.mark_done(concept_id=concept_id, language=lang)
        except Exception as exc:  # la promotion est deja actee : ne jamais la faire echouer
            logger.warning("mark_done apres promote (%s/%s): %s", concept_id, lang, exc)
    return result

