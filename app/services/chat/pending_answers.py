"""WOURI — Boucle de retour : délivrer la réponse validée au prochain échange (ADR-0040).

L'ADR-0039 fait dire au bot « je la transmets à un expert, **tu auras une réponse** »
quand il refuse d'inventer. Ce module tient cette promesse — **sans jamais
ré-identifier l'agriculteur**.

Le verrou de confidentialité (ADR-0031 / ADR-0025, conformité ARTCI) est délibéré et
reste intact : `anonymize_user_id` est un SHA-256 salé **irréversible**, et la file
d'amélioration refuse toute PII. On n'emprunte donc **que le sens autorisé** :

    identifiant détenu à l'instant où l'agriculteur écrit  ──►  empreinte  ──►  ses questions

Le sens interdit (empreinte → personne) n'est **jamais** parcouru, et **aucune donnée
personnelle supplémentaire n'est stockée**.

Une fois validée, la question est entrée au **corpus** (ADR-0031) : le moteur sait donc
déjà y répondre. Il ne manque pas « une réponse à livrer » — il manque un **rappel à la
bonne personne**. D'où le mécanisme : on **rejoue la question conservée** dans la
cascade et on préfixe le résultat d'un rappel.

Limite assumée (ADR-0040) : un agriculteur qui ne revient jamais ne recevra rien. C'est
le prix explicite du refus de constituer une base ré-identifiante.
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable, Optional

from app.services.chat._types import ChatResult

logger = logging.getLogger(__name__)

SOURCE_RAPPEL = "pending_answer"

# Rappel placé devant la réponse rejouée. En FRANÇAIS, comme l'accusé qui l'a promis
# (dette dioula tracée, ADR-0014 / ADR-0039) : la formulation dioula viendra d'une
# validation native.
PREFIXE_RAPPEL_FR = "Tu m'avais posé cette question : « {question} ». Voici la réponse :"


def enabled() -> bool:
    """Flag de rollback (`PENDING_ANSWERS_ENABLED`, défaut True), lu paresseusement."""
    try:
        from app.config import get_settings

        return bool(get_settings().pending_answers_enabled)
    except Exception:
        return True


async def build_pending_answer(
    user_id: Optional[str],
    city: str,
    include_audio: bool,
    resolve: Callable[[str], Awaitable[ChatResult]],
) -> Optional[ChatResult]:
    """Renvoie la réponse à une question escaladée désormais validée, ou None.

    `resolve` rejoue une question dans la cascade. L'appelant l'injecte en
    désactivant ce même contrôle, ce qui **exclut toute récursion**.

    Ne lève JAMAIS : la boucle de retour est un bonus, elle ne doit en aucun cas
    empêcher de répondre à la question que l'agriculteur vient de poser.
    """
    if not enabled() or not user_id:
        return None
    try:
        from app.core.pii_utils import anonymize_user_id
        from app.services.improvement_queue import list_deliverables, mark_delivered

        # SENS DIRECT uniquement : identifiant détenu → empreinte.
        empreinte = anonymize_user_id(user_id)
        taches = list_deliverables(empreinte)
        if not taches:
            return None  # cas de loin le plus fréquent : sortie immédiate

        tache = taches[0]  # une seule par échange, pour ne pas noyer l'agriculteur
        question = (tache.get("excerpt") or "").strip()
        if not question:
            return None

        # Drapeau de rejeu : la question est DÉJÀ dans la file. Sans lui, chaque
        # retour de l'agriculteur dont la question n'est pas encore servie par le
        # corpus créerait un doublon (constaté en démonstration du cycle complet).
        from app.services.chat.llm_guard import marquer_rejeu, restaurer_rejeu

        jeton = marquer_rejeu(True)
        try:
            resultat = await resolve(question)
        finally:
            restaurer_rejeu(jeton)

        if resultat is None or not (resultat.response or "").strip():
            logger.info("[RAPPEL] Rejeu sans réponse exploitable — tâche conservée")
            return None

        # Le moteur sait-il VRAIMENT répondre maintenant ? Si le rejeu retombe sur
        # l'accusé du garde (ADR-0039), la question a beau être validée dans
        # l'atelier, elle n'est pas servie par le moteur — c'est le cas en mode
        # français, qui ne consulte pas le corpus. On ne remet alors RIEN et on ne
        # marque PAS la tâche : sans ce garde, l'agriculteur recevrait « voici la
        # réponse : je préfère ne pas te répondre au hasard », et le rejeu créerait
        # une nouvelle tâche à chaque passage.
        from app.services.chat.llm_guard import SOURCE_ESCALATED

        if (resultat.meta or {}).get("source") == SOURCE_ESCALATED:
            logger.info(
                "[RAPPEL] Question validée mais toujours non servie par le moteur "
                "(tâche=%s) — conservée en attente", (tache.get("id") or "")[:8],
            )
            return None

        # Marquer APRÈS avoir obtenu une réponse : si le rejeu échoue, la tâche
        # reste en attente et sera retentée au prochain échange.
        mark_delivered(tache.get("id") or "")

        rappel = PREFIXE_RAPPEL_FR.format(question=question)
        texte = f"{rappel}\n\n{resultat.response}"
        logger.info(
            "[RAPPEL] Réponse validée remise (tâche=%s, intent=%s)",
            tache.get("id", "")[:8], tache.get("intent"),
        )
        return ChatResult(
            response=texte,
            response_dioula=resultat.response_dioula,
            city=city,
            language=resultat.language,
            audio_url=resultat.audio_url,
            audio_language=resultat.audio_language,
            meta={
                "intent": tache.get("intent"),
                "source": SOURCE_RAPPEL,
                "origine": (resultat.meta or {}).get("source"),
            },
        )
    except Exception as e:  # noqa: BLE001 — jamais au détriment de la question courante
        logger.error("[RAPPEL] Boucle de retour en échec : %s", e)
        return None
