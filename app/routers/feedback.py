"""
WOURI - Router Feedback

Reçoit les retours 👍/👎 depuis WhatsApp. Le feedback est un SIGNAL, pas une
validation linguistique (ADR-0019).

POST /api/feedback/positif  → log analytics + file de candidats à revue native
                              (si source = deepseek_open, le dioula machine),
                              JAMAIS d'ajout direct au corpus
POST /api/feedback/negatif  → log pour priorisation des réécritures (C5)

ADR-0019 : le feedback n'enrichit JAMAIS le corpus automatiquement. Un 👍 sur une
réponse DeepSeek fallback dépose un CANDIDAT dans feedback_candidates.jsonl ;
ce candidat n'entre au corpus qu'après validation par un locuteur natif dioula CI
(processus formulaire → natif → promotion). Le corpus servi ne contient que du
dioula validé nativement (règle d'or, ADR-0014).

Fix #359 : la condition d'origine visait `ivr_fallback`/`fallback_generic` —
or `ivr_fallback` est déjà du corpus validé (rien à revoir) et `fallback_generic`
n'est produit nulle part. La SEULE source de dioula machine est `deepseek_open`
(traduction NLLB du fallback DeepSeek) : c'est elle, et elle seule, qui alimente
la file de revue native.
"""
import json
import logging
import os
from datetime import date, datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional, List
from app.security import require_api_key
from app.core.log_retention import DEFAULT_LOG_DIR, monthly_feedback_filename
from app.core.pii_utils import anonymize_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/feedback", tags=["Feedback"])

# Logs feedback — fichier MENSUEL feedback-YYYY-MM.jsonl (issue #215, ADR-0025) :
# la purge de rétention supprime des fichiers entiers (atomique), jamais de
# réécriture de lignes concurrente avec les appends des workers. LOG_DIR vient
# de la source unique ADR-0025 (même dossier que la purge et le handler).
LOG_DIR              = os.fspath(DEFAULT_LOG_DIR)
FEEDBACK_NEGATIF_LOG = os.path.join(os.path.dirname(__file__), "..", "..", "data", "feedback_negatif.jsonl")
# File de candidats à revue native (ADR-0019) : un 👍 sur une réponse DeepSeek
# (deepseek_open) dépose ici un candidat. Il n'entre au corpus qu'après
# validation d'un natif — jamais automatiquement. Revue : manuelle pour
# l'instant (lire le jsonl → formulaire PDF via generate_culture_validation_pdf) ;
# l'outil dédié tools/review_feedback_candidates.py, prévu « optionnel » par
# ADR-0019, n'a pas encore été écrit.
FEEDBACK_CANDIDATES_LOG = os.path.join(os.path.dirname(__file__), "..", "..", "data", "feedback_candidates.jsonl")

# Caractères propres à l'écriture dioula/bambara — même heuristique que
# nlu_preprocessor.py:120 (2 usages : sous le seuil de factorisation du projet).
# Sert de garde : si `reponse_bambara` n'en contient aucun, c'est très
# probablement le texte FRANÇAIS non traduit (cas include_audio=False où
# response_dioula = réponse FR brute) → ne pas polluer la file de revue native.
_BAMBARA_CHARS = set("ɛɔŋɲɛ̀ɛ́ɔ̀ɔ́")


class FeedbackRequest(BaseModel):
    user_id: str
    reponse_bambara: str
    reponse_fr: Optional[str] = ""
    intent: Optional[str] = ""
    cultures: Optional[List[str]] = []
    source: Optional[str] = "unknown"  # ivr_exact | ivr_fallback | fallback_generic


def _feedback_log_path() -> str:
    """Chemin du fichier feedback du mois courant (ADR-0025).

    date.today() (date locale du process, UTC en prod via TZ compose) — même
    horloge que le handler de logs et la purge, pour que « fichier du mois
    courant jamais purgé » reste vrai.
    """
    return os.path.join(LOG_DIR, monthly_feedback_filename(date.today()))


def _log_feedback(entry: dict):
    """Écrit une ligne JSONL dans le fichier de log feedback du mois."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(_feedback_log_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"[Feedback] Erreur log: {e}")


@router.post("/positif", dependencies=[Depends(require_api_key)])
async def feedback_positif(req: FeedbackRequest):
    """
    Feedback 👍 — l'utilisateur a apprécié la réponse.

    ADR-0019 (condition corrigée #359) : le feedback n'enrichit JAMAIS le corpus
    automatiquement.
    - source = deepseek_open (dioula machine, NLLB) : dépose un CANDIDAT dans
      feedback_candidates.jsonl → sera proposé à un locuteur natif pour validation.
    - source = ivr_exact / ivr_fallback : texte déjà issu du corpus validé,
      log analytics seulement.
    - deepseek_english / deepseek_french : pas du dioula, log seulement.
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
    # Fix #359 : cible = deepseek_open, la seule source de dioula machine
    # (l'ancienne condition ivr_fallback/fallback_generic ne pouvait jamais
    # capturer de dioula IA). Garde : le texte doit contenir des caractères
    # dioula — sinon c'est la réponse FR non traduite (include_audio=False).
    if (
        req.source == "deepseek_open"
        and req.reponse_bambara
        and any(c in req.reponse_bambara for c in _BAMBARA_CHARS)
    ):
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
async def feedback_negatif(req: FeedbackRequest):
    """
    Feedback 👎 — l'utilisateur n'a pas apprécié la réponse.
    Logue dans feedback-YYYY-MM.jsonl (général) + feedback_negatif.jsonl (dédié corpus).
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
            from app.services.corpus_service import chercher_reponse_ivr
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

    # ADR-0031 / #431 : 👎 → tâche Bronze (file équivalente). Jamais de corpus.
    from app.services.improvement_queue import enqueue_improvement_task

    enqueue_improvement_task(
        intent=req.intent,
        source=req.source,
        cultures=req.cultures,
        excerpt=req.reponse_bambara,
        user_anon=anonymize_user_id(req.user_id),
    )

    return {"status": "ok", "action": "logged", "message": "Feedback enregistré pour amélioration"}
