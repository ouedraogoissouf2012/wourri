"""WOURI — Garde LLM : faits vérifiables + escalade préventive (ADR-0039).

Dernier maillon de la cascade, placé JUSTE AVANT l'appel au LLM. Deux régimes,
arbitrés par ADR-0039 (option B, acceptée le 2026-09-24) :

1. **Familles à réponse vérifiable** (météo, prix, date) — le LLM n'a aucun moyen
   de connaître la vérité : il est **interdit**. Si le répondeur déterministe de la
   famille n'a rien produit (donnée indisponible), on renvoie un **accusé explicite**
   et la question est **escaladée**, jamais une réponse inventée.
   C'est le défaut constaté le 23/09 (démo Bodokro) : une question météo localisée
   dont le répondeur a échoué retombait silencieusement sur le LLM, qui inventait
   une prévision.

2. **Conseil agronomique général hors corpus** — le LLM répond encore (sinon ~40 %
   des questions resteraient sans réponse, cf. mesure ADR-0039 §Contexte), mais la
   question est **escaladée systématiquement** vers le sas de validation
   (`improvement_queue`, ADR-0031) pour produire une réponse validée qui la
   remplacera au prochain passage. La remontée devient ainsi **préventive** et plus
   seulement réactive (elle n'était branchée que sur le 👎).

Dette tracée (ADR-0014, « ne jamais inventer de dioula ») : l'accusé est rendu en
FRANÇAIS même en dioula/both, comme `date_responder`. Arbitrage utilisateur du
2026-09-24. La formulation dioula viendra d'une validation native.

Réglages (externalisés, `constraints.md` §1.2 — aucune liste en dur) :
  - `LLM_GUARD_ENABLED` : rollback sans redéploiement de code ;
  - `LLM_FACTUAL_INTENTS` : familles interdites au LLM, ajustables sur mesure.

Pattern : fonctions module-level orchestrées par les handlers, à l'identique de
`meteo_responder` / `culture_zone_responder` / `date_responder`.
"""
from __future__ import annotations

import contextvars
import logging
from typing import Optional

from app.models.schemas import Language
from app.services.chat._types import ChatResult
from app.services.chat.nlu_preprocessor import NLUResult

logger = logging.getLogger(__name__)

# Message d'accusé — porte une PROMESSE de réponse d'expert (arbitrage Q1 de
# l'ADR-0039). La promesse est désormais TENUE par la boucle de retour (ADR-0040) :
# la réponse validée est remise à l'agriculteur **à son prochain échange**. D'où
# « reviens me voir » : on annonce exactement ce que le système fait, ni plus
# (aucune notification spontanée n'est envoyée) ni moins.
ESCALATION_MESSAGE_FR = (
    "Bonne question. Je préfère ne pas te répondre au hasard : "
    "je la fais étudier par un expert. Reviens me voir, je te donnerai la réponse."
)

SOURCE_ESCALATED = "escalated_factual"
SOURCE_LLM_ESCALATED = "llm_escalated"

# Vrai pendant le REJEU d'une question déjà escaladée (boucle de retour, ADR-0040).
# Sans ce drapeau, chaque retour de l'agriculteur dont la question n'est pas encore
# servie par le corpus recréerait une tâche : on escaladerait en boucle la même
# question. Un ContextVar (et non une variable globale) pour rester correct quand
# plusieurs conversations sont traitées en parallèle.
_REJEU_EN_COURS: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "wouri_rejeu_en_cours", default=False
)


def rejeu_en_cours() -> bool:
    """True si l'on rejoue une question archivée (→ ne pas ré-escalader)."""
    return _REJEU_EN_COURS.get()


def marquer_rejeu(actif: bool):
    """Pose le drapeau de rejeu ; renvoie le jeton de restauration."""
    return _REJEU_EN_COURS.set(actif)


def restaurer_rejeu(token) -> None:
    """Restaure l'état précédent du drapeau."""
    try:
        _REJEU_EN_COURS.reset(token)
    except ValueError:  # jeton d'un autre contexte : état déjà restauré
        pass


def guard_enabled() -> bool:
    """True si le garde est actif (flag `LLM_GUARD_ENABLED`, défaut True).

    Lecture paresseuse de la config : permet le monkeypatch en tests et un
    rollback en production sans redéploiement de code.
    """
    try:
        from app.config import get_settings

        return bool(get_settings().llm_guard_enabled)
    except Exception:  # config indisponible → ne jamais casser la réponse
        return True


def factual_intents() -> frozenset[str]:
    """Familles de questions interdites au LLM, lues depuis la configuration.

    `LLM_FACTUAL_INTENTS` est une liste d'intents séparés par des virgules. Une
    valeur vide désactive de fait le régime « faits vérifiables ».
    """
    try:
        from app.config import get_settings

        raw = get_settings().llm_factual_intents or ""
    except Exception:
        return frozenset()
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def is_factual_intent(nlu: NLUResult) -> bool:
    """True si l'intent relève d'une famille à réponse vérifiable (LLM interdit)."""
    return bool(nlu.intent) and nlu.intent in factual_intents()


def escalate(
    nlu: NLUResult,
    city: str,
    user_id: Optional[str],
    source: str,
    excerpt: Optional[str] = None,
) -> None:
    """Remonte la question au sas de validation (ADR-0031). Ne lève JAMAIS.

    L'escalade est un effet de bord : son échec ne doit en aucun cas priver
    l'agriculteur de sa réponse.

    N'escalade PAS pendant un rejeu (ADR-0040) : la question est déjà dans la file,
    la ré-enfiler créerait un doublon à chaque retour de l'agriculteur.
    """
    if rejeu_en_cours():
        logger.debug("[GARDE-LLM] Rejeu en cours — pas de nouvelle escalade")
        return
    try:
        from app.core.pii_utils import anonymize_user_id
        from app.services.improvement_queue import enqueue_improvement_task

        enqueue_improvement_task(
            intent=nlu.intent,
            source=source,
            cultures=sorted(nlu.concepts.keys()) if nlu.concepts else [],
            # La question TELLE QUE posée : c'est elle qu'on recitera a
            # l'agriculteur (ADR-0040). `message_for_deepseek` est la version
            # enrichie par le NLU, avec prefixe technique — a ne pas lui relire.
            excerpt=excerpt or nlu.message_original or nlu.message_for_deepseek,
            user_anon=anonymize_user_id(user_id),
            extra={"city": city, "reason": source},
            skip_if_duplicate=True,
        )
        logger.info("[GARDE-LLM] Question escaladée (source=%s, ville=%s)", source, city)
    except Exception as e:  # noqa: BLE001 — l'escalade ne doit jamais casser le chat
        logger.error("[GARDE-LLM] Échec de l'escalade (%s) : %s", source, e)


async def build_escalation_response(
    nlu: NLUResult,
    city: str,
    include_audio: bool,
    language: Language,
    user_id: Optional[str],
) -> ChatResult:
    """Accusé de réception pour une question FACTUELLE sans réponse fiable.

    Renvoie TOUJOURS un `ChatResult` (jamais None) : c'est précisément le point
    où l'on refuse de laisser le LLM inventer. Rendu en français (dette dioula).
    """
    escalate(nlu, city, user_id, SOURCE_ESCALATED)

    audio_url = None
    if include_audio:
        try:
            from app.services.tts_french import synthesize_french

            audio_url = await synthesize_french(ESCALATION_MESSAGE_FR)
        except Exception as e:  # noqa: BLE001 — le texte part même sans audio
            logger.error("[GARDE-LLM] TTS indisponible : %s", e)

    logger.info(
        "[GARDE-LLM] LLM bloqué sur un fait vérifiable (intent=%s, ville=%s)",
        nlu.intent, city,
    )
    return ChatResult(
        response=ESCALATION_MESSAGE_FR,
        city=city,
        language=language.value,
        audio_url=audio_url,
        audio_language="Français" if audio_url else None,
        meta={"intent": nlu.intent, "source": SOURCE_ESCALATED},
    )
