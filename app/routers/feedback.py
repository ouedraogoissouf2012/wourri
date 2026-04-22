"""
WOURI - Router Feedback C4
Reçoit les retours 👍/👎 depuis WhatsApp et déclenche C3 auto-apprentissage.

POST /api/feedback/positif  → ajouter_reponse_validee() si source = ivr_fallback
POST /api/feedback/negatif  → log pour C5 reporting
"""
import json
import logging
import os
from datetime import datetime
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from typing import Optional, List
from app.security import require_api_key, limiter
from app.core.pii_utils import anonymize_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/feedback", tags=["Feedback"])

# Logs feedback
FEEDBACK_LOG         = os.path.join(os.path.dirname(__file__), "..", "..", "logs", "feedback.jsonl")
FEEDBACK_NEGATIF_LOG = os.path.join(os.path.dirname(__file__), "..", "..", "data", "feedback_negatif.jsonl")


class FeedbackRequest(BaseModel):
    user_id: str
    reponse_bambara: str
    reponse_fr: Optional[str] = ""
    intent: Optional[str] = ""
    cultures: Optional[List[str]] = []
    source: Optional[str] = "unknown"  # ivr_exact | ivr_fallback | fallback_generic


def _log_feedback(entry: dict):
    """Écrit une ligne JSONL dans le fichier de log feedback."""
    try:
        os.makedirs(os.path.dirname(FEEDBACK_LOG), exist_ok=True)
        with open(FEEDBACK_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"[Feedback] Erreur log: {e}")


@router.post("/positif", dependencies=[Depends(require_api_key)])
@limiter.limit("10/minute")
async def feedback_positif(request: Request, req: FeedbackRequest):
    """
    Feedback 👍 — l'utilisateur a apprécié la réponse.
    Si source = ivr_fallback : ajouter la réponse au corpus VDB (C3).
    Si source = ivr_exact    : déjà dans le corpus, rien à faire.
    """
    entry = {
        "ts": datetime.utcnow().isoformat(),
        "user": anonymize_user_id(req.user_id),
        "vote": "positif",
        "intent": req.intent,
        "cultures": req.cultures,
        "source": req.source,
        "reponse_bambara": req.reponse_bambara[:120],
    }
    _log_feedback(entry)

    # C3 : auto-apprentissage uniquement pour les réponses de fallback
    if req.source in ("ivr_fallback", "fallback_generic") and req.reponse_bambara:
        try:
            from app.services.vdb_service import ajouter_reponse_validee
            ok = ajouter_reponse_validee(
                intent=req.intent or "CONSEIL_PRODUCTION",
                cultures=req.cultures or ["*"],
                reponse_bambara=req.reponse_bambara,
                reponse_fr=req.reponse_fr or "",
                score_validation=0.80,
                tags=["feedback_positif", "auto_appris"],
            )
            if ok:
                logger.info(f"[C3] Nouvelle entrée validée depuis feedback 👍 (intent={req.intent})")
                return {"status": "ok", "action": "apprentissage", "message": "Réponse ajoutée au corpus"}
        except Exception as e:
            logger.error(f"[C3] Erreur auto-apprentissage: {e}")

    return {"status": "ok", "action": "logged", "message": "Merci pour votre retour"}


@router.post("/negatif", dependencies=[Depends(require_api_key)])
@limiter.limit("10/minute")
async def feedback_negatif(request: Request, req: FeedbackRequest):
    """
    Feedback 👎 — l'utilisateur n'a pas apprécié la réponse.
    Logue dans feedback.jsonl (général) + feedback_negatif.jsonl (dédié corpus).
    feedback_negatif.jsonl est lu par tools/analyze_feedback.py pour identifier
    les entrées corpus à réécrire en priorité.
    """
    ts = datetime.utcnow().isoformat()

    # Log général
    entry = {
        "ts": ts,
        "user": anonymize_user_id(req.user_id),
        "vote": "negatif",
        "intent": req.intent,
        "cultures": req.cultures,
        "source": req.source,
        "reponse_bambara": req.reponse_bambara[:120],
    }
    _log_feedback(entry)

    # Log dédié corpus — inclut l'id de l'entrée VDB pour traçabilité
    corpus_entry_id = None
    if req.intent and req.source == "ivr_exact":
        try:
            from app.services.vdb_service import chercher_reponse_ivr
            result = chercher_reponse_ivr(
                intent=req.intent,
                cultures=req.cultures or ["*"],
            )
            if result:
                corpus_entry_id = result.get("id")
        except Exception:
            pass

    negatif_entry = {
        "ts": ts,
        "user": anonymize_user_id(req.user_id),
        "intent": req.intent,
        "cultures": req.cultures,
        "source": req.source,
        "id_entree_corpus": corpus_entry_id,
        "reponse_bambara": req.reponse_bambara[:200],
    }
    try:
        os.makedirs(os.path.dirname(FEEDBACK_NEGATIF_LOG), exist_ok=True)
        with open(FEEDBACK_NEGATIF_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(negatif_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"[C5] Erreur log feedback_negatif: {e}")

    logger.warning(
        f"[C5] Réponse rejetée: id={corpus_entry_id} intent={req.intent} "
        f"cultures={req.cultures} source={req.source}"
    )
    return {"status": "ok", "action": "logged", "message": "Feedback enregistré pour amélioration"}
