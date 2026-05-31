"""
WOURI — Types partages du sous-package chat (refactor P2-09 PR 4/5).

Heberge la dataclass `ChatResult` consommee par plusieurs modules du
sous-package `app.services.chat` (notamment `ivr_searcher`, et plus tard
`deepseek_router` en PR 5/5). Sans ce module, on aurait un cycle d'import :

  chat_service.py imports app.services.chat.ivr_searcher
  app.services.chat.ivr_searcher needs ChatResult
  → si ChatResult est dans chat_service.py → CYCLE

Solution : ChatResult est defini ici, ChatService re-exporte pour back-compat.

Prefixe `_` car module privé du sous-package (pas un export public).

Note : `NLUResult` reste dans `nlu_preprocessor.py` (cf. PR 3/5) car c'est
le type de retour de `preprocess_nlu()` — convention "type de retour avec
sa fonction".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ChatResult:
    """Resultat final du ChatService, pret a etre converti en ChatResponse.

    Fields :
      response: Texte FR (par contrat — cf. issue #167). Fallback bambara
                uniquement si l'entree corpus n'a pas reponse_fr.
      response_dioula: Texte dioula (envoye par whatsapp-server en mode
                       dioula/both pour audio TTS).
      audio_url: URL relative vers l'audio TTS dioula genere (None si TTS
                 echoue ou include_audio=False).
      city: Ville detectee ou fallback "Abidjan".
      language: Mode langue choisi par l'utilisateur ("french"/"dioula"/"both").
      audio_language: "Dioula" si audio genere, None sinon.
      meta: Dict de metadonnees (intent, cultures, source, phrases_attestees).
    """
    response: str
    response_dioula: Optional[str] = None
    audio_url: Optional[str] = None
    city: str = "Abidjan"
    language: str = "both"
    audio_language: Optional[str] = None
    meta: Optional[dict] = None
