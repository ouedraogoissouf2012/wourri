"""
WOURI — BothHandler : mode bilingue dioula + francais (ADR-0015 PR 2/4).

Mode `Language.BOTH` = "le meilleur des deux" :
  - Texte FR pour les utilisateurs alphabetises qui veulent lire
  - Audio dioula pour les utilisateurs peu alphabetises qui veulent ecouter
  - Meme cascade IVR exact → concept → DeepSeek que `DioulaHandler`

La logique de cascade est **strictement identique** a DioulaHandler — seule
la valeur `ChatResult.language = "both"` change. Cette valeur est portee
automatiquement par les fonctions de cascade (`try_ivr_exact`, `try_ivr_concept`,
`try_deepseek_dioula`) qui relayent `language.value` du parametre d'entree.

Implementation : herite de `DioulaHandler` sans override. La distinction est
purement semantique (entree dans `HANDLERS` avec cle `Language.BOTH`). Si un
futur besoin imposait un comportement different pour BOTH (ex: format ChatResult
specifique pour le mode bilingue WhatsApp), le override irait ici sans toucher
DioulaHandler — OCP respecte.

Ref : ADR-0015 docs/adr/0015-strategy-pattern-cascade-chat-et-anglais.md
Issue : #277 (PR 2/4)
"""
from __future__ import annotations

from app.services.chat.handlers.dioula_handler import DioulaHandler


class BothHandler(DioulaHandler):
    """Mode `Language.BOTH` : meme cascade que `DioulaHandler`.

    Le mode bilingue produit texte FR + audio dioula. La cascade etant
    identique, on herite sans override. La valeur `ChatResult.language = "both"`
    est portee par le parametre `language` transmis aux fonctions de cascade.

    Si un futur ADR impose un comportement different (ex: rendu particulier
    cote whatsapp-server), override `process()` ici — sans toucher DioulaHandler.
    """
    pass
