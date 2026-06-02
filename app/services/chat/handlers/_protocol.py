"""
WOURI — Protocol pour les language handlers (ADR-0015 PR 1/4).

Definit l'interface `LanguageHandler` que tous les handlers de langue doivent
respecter. Le dispatcher `chat_service.process()` (refactore en PR 3/4) lit
le registre `HANDLERS[language]` et appelle `handler.process(...)` sans
connaitre l'implementation concrete (Strategy Pattern, OCP-compliant).

Ajout d'une nouvelle langue = nouvelle classe respectant ce Protocol + entree
dans `HANDLERS`. Aucune modification du dispatcher requise.

Ref : ADR-0015 docs/adr/0015-strategy-pattern-cascade-chat-et-anglais.md
Issue parent : #275 (Epic), Issue PR 1/4 : #276
"""
from __future__ import annotations

from typing import Optional, Protocol

from app.models.schemas import Language
from app.services.chat._types import ChatResult
from app.services.chat.nlu_preprocessor import NLUResult


class LanguageHandler(Protocol):
    """Interface pour un handler de langue dans la cascade chat.

    Chaque langue (FRENCH, DIOULA, BOTH, ENGLISH, ...) implemente ce Protocol
    avec sa propre logique : direct DeepSeek pour FR/EN, cascade IVR pour
    DIOULA/BOTH.

    Methodes :
      - `process(...)` : pipeline complet message -> reponse pour cette langue.
        Retourne un `ChatResult` pret a etre converti en `ChatResponse`.

    Parametres standardises (memes pour toutes les langues, certains ignores
    selon le handler) :
      - `nlu` : resultat preprocessing NLU (`message_for_deepseek`, `intent`,
        `concepts`)
      - `weather_data` : donnees meteo de la ville detectee (peut etre None)
      - `city` : ville detectee ou fallback "Abidjan"
      - `include_audio` : si True, genere un audio TTS dans la langue cible
      - `language` : enum Language demande (utilise pour le champ
        `ChatResult.language` et le routage TTS)
      - `user_id` : ID utilisateur anonymise pour l'historique conversation
        (transmis a DeepSeek)
    """

    async def process(
        self,
        nlu: NLUResult,
        weather_data: dict | None,
        city: str,
        include_audio: bool,
        language: Language,
        user_id: Optional[str],
    ) -> ChatResult:
        """Pipeline complet message -> reponse pour cette langue.

        Retourne un `ChatResult` avec :
          - `response` : texte de la reponse (en langue cible ou FR selon langue)
          - `response_dioula` : texte dioula si applicable (None pour FR/EN)
          - `audio_url` : URL relative TTS si `include_audio=True` et synthese OK
          - `city` / `language` / `audio_language` : metadonnees
          - `meta` : dict avec `intent`, `cultures`, `source` (`deepseek_open`,
            `ivr_exact`, `ivr_fallback`, `clarification_culture`, ...)
        """
        ...
