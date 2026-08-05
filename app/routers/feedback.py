"""
WOURI - Router Feedback

Reçoit les retours 👍/👎 depuis WhatsApp. Le feedback est un SIGNAL, pas une
validation linguistique (ADR-0019).

POST /api/feedback/positif  → log analytics + file de candidats à revue native
                              (si source = fallback), JAMAIS d'ajout direct au corpus
POST /api/feedback/negatif  → log pour priorisation des réécritures (C5)

ADR-0019 : le feedback n'enrichit JAMAIS le corpus automatiquement. Un 👍 sur une
réponse DeepSeek fallback dépose un CANDIDAT dans feedback_candidates.jsonl ;
ce candidat n'entre au corpus qu'après validation par un locuteur natif dioula CI
(processus formulaire → natif → promotion). Le corpus servi ne contient que du
dioula validé nativement (règle d'or, ADR-0014).
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
# File de candidats à revue native (ADR-0019) : un 👍 sur une réponse fallback
# dépose ici un candidat. Il n'entre au corpus qu'après validation d'un natif —
# jamais automatiquement. Lu par tools/review_feedback_candidates.py.
FEEDBACK_CANDIDATES_LOG = os.path.join(os.path.dirname(__file__), "..", "..", "data", "feedback_candidates.jsonl")


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

    ADR-0019 : le feedback n'enrichit JAMAIS le corpus automatiquement.
    - source = fallback (ivr_fallback/fallback_generic) : dépose un CANDIDAT dans
      feedback_candidates.jsonl → sera proposé à un locuteur natif pour validation.
    - source = ivr_exact : déjà dans le corpus validé, rien à faire.
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

    # ADR-0019 : un 👍 sur une réponse de fallback (dioula IA non validé) NE l'ajoute
    # PAS au corpus. Il dépose un candidat dans une file de revue native persistante.
    # Le candidat n'entre au corpus qu'après validation d'un locuteur natif dioula CI.
    if req.source in ("ivr_fallback", "fallback_generic") and req.reponse_bambara:
        candidate = {
            "ts": datetime.utcnow().isoformat(),
            "user": anonymize_user_id(req.user_id),
            "intent": req.intent or "CONSEIL_PRODUCTION",
            "cultures": req.cultures or ["*"],
            "reponse_bambara": req.reponse_bambara,
            "reponse_fr": req.reponse_fr or "",
            "source": req.source,
            "status": "pending_native_review",
        }
        try:
            os.makedirs(os.path.dirname(FEEDBACK_CANDIDATES_LOG), exist_ok=True)
            with open(FEEDBACK_CANDIDATES_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(candidate, ensure_ascii=False) + "\n")
            logger.info(
                f"[Feedback] Candidat déposé pour revue native (intent={req.intent}, "
                f"source={req.source})"
            )
            return {
                "status": "ok",
                "action": "candidate_queued",
                "message": "Merci ! Cette réponse sera proposée à un validateur.",
            }
        except Exception as e:
            logger.error(f"[Feedback] Erreur écriture candidat: {e}")

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
            # Façade ADR-0008 §Phase C : route vers Chroma (défaut) / dual / pgvector.
            from app.services.corpus_facade import chercher_reponse_ivr
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
