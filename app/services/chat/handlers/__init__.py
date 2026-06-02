"""
WOURI — Registre des language handlers (ADR-0015 PR 2/4).

Strategy Pattern : chaque langue a son propre handler implementant le Protocol
`LanguageHandler`. Le dispatcher `chat_service.process()` (refactore en PR 3/4)
lit ce registre :

    handler = HANDLERS[language]
    return await handler.process(...)

Ajout d'une langue future = nouvelle classe + 1 entree dans ce dict. **Zero
modification** du dispatcher.

Etat actuel (PR 2/4) : FRENCH, DIOULA, BOTH enregistres. La cascade legacy
dans `chat_service.process()` reste active jusqu'en PR 3/4 — les handlers ici
sont utilises uniquement via les wrappers retrocompat (deepseek_router,
ChatService._try_*). La PR 3/4 fera de `process()` un thin dispatcher pur
qui delegue a ces handlers.

Ref : ADR-0015 docs/adr/0015-strategy-pattern-cascade-chat-et-anglais.md
Issue parent : #275 (Epic)
"""
from __future__ import annotations

from app.models.schemas import Language
from app.services.chat.handlers._protocol import LanguageHandler
from app.services.chat.handlers.both_handler import BothHandler
from app.services.chat.handlers.dioula_handler import DioulaHandler
from app.services.chat.handlers.english_handler import EnglishHandler
from app.services.chat.handlers.french_handler import FrenchHandler


HANDLERS: dict[Language, LanguageHandler] = {
    Language.FRENCH:  FrenchHandler(),
    Language.DIOULA:  DioulaHandler(),
    Language.BOTH:    BothHandler(),
    # ADR-0015 PR 4/4 : EnglishHandler — pure extension du pattern Strategy
    Language.ENGLISH: EnglishHandler(),
}


__all__ = [
    "HANDLERS",
    "LanguageHandler",
    "FrenchHandler",
    "DioulaHandler",
    "BothHandler",
    "EnglishHandler",
]
