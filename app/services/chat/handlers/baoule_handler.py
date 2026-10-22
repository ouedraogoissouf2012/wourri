"""
WOURI — BaouleHandler : NLU baoulé → réponse native validée → repli honnête (ADR-0045).

Même idée que la cascade du dioula, sans le dernier recours au LLM : en baoulé, aucun
texte n'est généré (docs/constraints.md §3.3). Le NLU baoulé (concepts → intention,
`preprocess_nlu`) cadre la culture ; la réponse servie est celle du corpus de la dictée
(`baoule_ivr`), écrite et lue par le locuteur natif, avec sa traduction française.

Sans réponse assez proche : repli en français qui le dit, liste les sujets connus (tirés
du corpus lui-même) et remonte la question au sas de validation (ADR-0031), comme le
dioula le fait avant le LLM.
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
        message = "Je n'ai pas encore de réponse validée en baoulé pour cette question."
        if sujets:
            message += f" Je peux déjà t'aider sur : {sujets}."
        return ChatResult(
            response=message,
            city=city,
            language=language.value,
            meta={"intent": nlu.intent, "cultures": cultures, "source": SOURCE_HORS_CORPUS_BCI},
        )
