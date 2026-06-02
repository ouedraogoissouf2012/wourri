"""
WOURI — Registre des language handlers (ADR-0015 PR 1/4).

Strategy Pattern : chaque langue a son propre handler implementant le Protocol
`LanguageHandler`. Le dispatcher `chat_service.process()` (refactore en PR 3/4)
lit ce registre :

    handler = HANDLERS[language]
    return await handler.process(...)

Ajout d'une langue future = nouvelle classe + 1 entree dans ce dict. **Zero
modification** du dispatcher.

Etat actuel (PR 1/4) : seul `FrenchHandler` est enregistre. Les autres langues
(DIOULA, BOTH) sont encore gerees par la cascade legacy dans `chat_service`
jusqu'a la PR 2/4 qui ajoutera `DioulaHandler` et `BothHandler`. La PR 3/4
finalisera le dispatcher pur.

Ref : ADR-0015 docs/adr/0015-strategy-pattern-cascade-chat-et-anglais.md
Issue parent : #275 (Epic)
"""
from __future__ import annotations

from app.models.schemas import Language
from app.services.chat.handlers._protocol import LanguageHandler
from app.services.chat.handlers.french_handler import FrenchHandler


HANDLERS: dict[Language, LanguageHandler] = {
    Language.FRENCH: FrenchHandler(),
}


__all__ = ["HANDLERS", "LanguageHandler", "FrenchHandler"]
