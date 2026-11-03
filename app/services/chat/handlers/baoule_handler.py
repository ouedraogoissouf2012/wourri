"""
WOURI — BaouleHandler : NLU baoulé → réponse native validée → repli honnête (ADR-0045).

Même idée que la cascade du dioula, sans le dernier recours au LLM : en baoulé, aucun
texte n'est généré (docs/constraints.md §3.3). Le NLU baoulé (concepts → intention,
`preprocess_nlu`) cadre la culture ; la réponse servie est celle du corpus de la dictée
(`baoule_ivr`), écrite et lue par le locuteur natif, avec sa traduction française.

Sans réponse assez proche : repli qui le dit, liste les sujets connus (tirés du corpus
lui-même) et remonte la question au sas de validation (ADR-0031), comme le dioula le
fait avant le LLM. Ce repli est servi dans la langue dès qu'un message système y a été
validé (ADR-0049) ; en français tant qu'il n'y en a pas.
"""
from __future__ import annotations

import logging
from pathlib import PurePosixPath
from typing import Optional

from app.models.schemas import Language
from app.services.chat._types import ChatResult
from app.services.chat.nlu_preprocessor import NLUResult

logger = logging.getLogger(__name__)

SOURCE_IVR_BCI = "ivr_bci"
SOURCE_HORS_CORPUS_BCI = "bci_hors_corpus"


def _audio_url(entry: dict) -> Optional[str]:
    """Enregistrement de la réponse par le locuteur natif (ogg/opus), si la base est configurée."""
    from app.config import settings

    base = (settings.bci_audio_base_url or "").rstrip("/")
    fichier = entry.get("audio_reponse")
    if not base or not fichier:
        return None
    return f"{base}/{PurePosixPath(fichier).stem}.ogg"


def _sujets(corpus) -> str:
    filieres = sorted({(e.get("filiere") or "").split("(")[0].strip().lower() for e in corpus} - {""})
    return ", ".join(filieres)


class BaouleHandler:
    """Handler pour `Language.BAOULE`."""

    async def process(
        self,
        nlu: NLUResult,
        weather_data: dict | None,
        city: str,
        include_audio: bool,
        language: Language,
        user_id: Optional[str],
    ) -> ChatResult:
        from app.services import baoule_ivr

        texte = nlu.message_original or nlu.message_for_deepseek
        trouvaille = baoule_ivr.chercher(texte, nlu.intent, nlu.concepts)
        cultures = [k for k in (nlu.concepts or {}) if k.startswith("CULTURE_")]
        if trouvaille is not None:
            e = trouvaille.entry
            logger.info("[BCI] réponse %s (sim=%.2f, intent=%s)", e.get("id"), trouvaille.similarite, nlu.intent)
            audio_url = _audio_url(e) if include_audio else None
            return ChatResult(
                response=e.get("reponse_fr") or e["reponse_bci"],
                response_local=e["reponse_bci"],
                audio_url=audio_url,
                audio_language="Baoulé" if audio_url else None,
                city=city,
                language=language.value,
                meta={
                    "intent": nlu.intent,
                    "cultures": cultures,
                    "source": SOURCE_IVR_BCI,
                    "corpus_id": e.get("id"),
                    "question_bci": e.get("question_bci"),
                    "similarite": round(trouvaille.similarite, 3),
                },
            )

        from app.services.chat.llm_guard import escalate

        escalate(nlu, city, user_id, SOURCE_HORS_CORPUS_BCI, excerpt=texte)
        sujets = _sujets(baoule_ivr.entrees())
        # Dire que la QUESTION n'est pas comprise, jamais que le baoulé manque :
        # « pas de réponse validée en baoulé » faisait croire au paysan que la
        # langue ne marche pas, alors que seule sa question n'a pas été reconnue.
        message = "Je n'ai pas compris ta question."
        if sujets:
            message += f" Je peux t'aider sur : {sujets}."

        # Le repli dans la langue, s'il a ete valide par le locuteur (ADR-0049).
        # Le francais garde la liste des sujets, qui est calculee ; le natif s'ajoute
        # en texte et en voix. Sans message valide : le francais seul, comme avant.
        # Jamais une phrase inventee ni une tournure d'une autre langue (ADR-0031/0046).
        from app.config import settings
        from app.data.lqe_languages import BAOULE_CODE
        from app.services import messages_systeme

        # BAOULE_CODE (« bci »), pas `language.value` (« baoule ») : les fichiers de
        # langue, la dictee et l'atelier sont tous nommes par le code ISO.
        natif = messages_systeme.message(BAOULE_CODE, messages_systeme.REPLI)
        audio_url = (
            messages_systeme.url_audio(natif, settings.bci_audio_base_url)
            if natif and include_audio
            else None
        )
        return ChatResult(
            response=message,
            response_local=natif.texte if natif else None,
            audio_url=audio_url,
            audio_language="Baoulé" if audio_url else None,
            city=city,
            language=language.value,
            meta={"intent": nlu.intent, "cultures": cultures, "source": SOURCE_HORS_CORPUS_BCI},
        )
