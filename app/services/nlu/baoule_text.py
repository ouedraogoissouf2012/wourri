"""Mise en forme du texte baoulé (bci) pour le NLU et la recherche dans le corpus (ADR-0045).

Une seule mise en forme, partagée par l'amorçage (scripts/baoule_nlu_bootstrap.py), le
NLU baoulé et la recherche de réponse : minuscules, tons retirés (comme le
ConceptExtractor), apostrophes et ponctuation → espace. Les déterminants accolés du
baoulé (fie’n, be’m, w’a) deviennent des mots séparés ; les lettres ɛ ɔ ɲ restent.
"""
from __future__ import annotations

import re
import unicodedata

from app.services.nlu.concept_extractor import strip_tones

# Apostrophes rencontrées dans la dictée et dans la sortie de l'ASR (’ ʼ ' ‘ `).
_APOSTROPHES = "’ʼ‘`'"
_NON_LETTRE = re.compile(r"[^\w\s]")


def tokens_bci(text: str | None) -> list[str]:
    """Mots baoulé comparables entre eux et avec les mots-clés du NLU."""
    t = strip_tones(unicodedata.normalize("NFC", text or "").lower())
    for a in _APOSTROPHES:
        t = t.replace(a, " ")
    return _NON_LETTRE.sub(" ", t).split()


def prepare_bci(text: str | None) -> str:
    """Texte baoulé prêt pour le ConceptExtractor (mêmes mots que tokens_bci)."""
    return " ".join(tokens_bci(text))
