"""
Wouri - Heuristiques post-transcription Whisper.

Extraites de `stt_whisper.py` (refactor 2026-05-28) pour separer la
logique d'analyse de qualite/langue de la machinerie de chargement
modele. Comportement strictement identique a l'original.

NOTE DETTE TECHNIQUE :
    `is_likely_dioula_input` est une heuristique hardcodee (anti-pattern
    documente dans ADR-0005). Elle DOIT etre remplacee par AfroLID
    (detection ML 517 langues) lors de la Phase D de l'ADR. Voir
    `docs/adr/0005-afrolid-language-detection.md` pour le plan de
    suppression.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# Phrases generiques connues comme hallucinations de Whisper
_HALLUCINATION_PATTERNS: tuple[str, ...] = (
    "sous-titres réalisés",
    "sous-titrage",
    "merci d'avoir regardé",
    "thank you for watching",
    "subscribe",
    "abonnez-vous",
    "like and subscribe",
    "www.",
    "http",
    "copyright",
    "tous droits réservés",
)


# Indices de transcription incorrecte (Dioula parlé -> français charabia)
# Anti-pattern hardcoding documente dans ADR-0005, a remplacer par AfroLID
_INCOHERENT_DIOULA_PATTERNS: tuple[str, ...] = (
    # Questions qui n'ont pas de sens en français
    "est-ce que tu parles plus là",
    "tu parles plus là",
    "parles plus là",
    "est-ce que tu parles",
    # Phrases répétitives typiques des mauvaises transcriptions
    "dis-moi dis-moi",
    "oui oui oui",
    "non non non",
    # Sons/mots qui ressemblent au Dioula mal interprétés
    "ala", "allah", "wala", "walahi",
    "n'golo", "ngolo",
    "fola", "fo la",
    # Onomatopées fréquentes
    "hein hein",
    "eh eh",
    "mmh mmh",
)


def is_likely_hallucination(text: str) -> bool:
    """
    Detecte si un texte semble etre une hallucination de Whisper.

    Les hallucinations sont des textes generes par le modele qui ne
    correspondent pas a ce qui a ete dit dans l'audio.

    Criteres (dans l'ordre) :
        1. Texte vide ou < 2 mots
        2. Plus de 20 % de caracteres non-latins (au-dela de U+024F)
        3. Repetition excessive d'un meme mot (> 50 % des mots si > 4 mots)
        4. Presence d'un pattern connu (sous-titres, copyright, etc.)

    Args:
        text: Le texte transcrit

    Returns:
        True si le texte semble etre une hallucination
    """
    if not text:
        return True

    # Texte trop court (moins de 2 mots)
    words = text.split()
    if len(words) < 2:
        return True

    # Caracteres non-latins (signe d'hallucination)
    non_latin_chars = sum(1 for c in text if ord(c) > 0x024F and not c.isspace())
    if non_latin_chars > len(text) * 0.2:
        logger.warning("[Faster-Whisper] Trop de caracteres non-latins detectes")
        return True

    # Phrases repetitives (signe d'hallucination)
    if len(text) > 50 and len(words) > 4:
        word_counts: dict[str, int] = {}
        for word in words:
            word_lower = word.lower()
            word_counts[word_lower] = word_counts.get(word_lower, 0) + 1

        # Si un mot apparait plus de 50 % du temps, c'est suspect
        max_count = max(word_counts.values())
        if max_count > len(words) * 0.5:
            logger.warning("[Faster-Whisper] Repetition excessive detectee")
            return True

    # Patterns hallucination connus
    text_lower = text.lower()
    for pattern in _HALLUCINATION_PATTERNS:
        if pattern in text_lower:
            logger.warning(f"[Faster-Whisper] Pattern d'hallucination detecte: {pattern}")
            return True

    return False


def is_likely_dioula_input(text: str, language_probability: float = 0.0) -> bool:
    """
    Detecte si l'audio original etait probablement en Dioula/Bambara
    mais a ete mal transcrit en francais par Whisper.

    DETTE ADR-0005 : a remplacer par AfroLID (Phase D).

    Indices :
        - Phrases incoherentes en francais (cf. _INCOHERENT_DIOULA_PATTERNS)
        - Probabilite de langue francaise < 70 %
        - Mots repetes ou sons etranges

    Args:
        text: Le texte transcrit
        language_probability: Probabilite de la langue detectee par Whisper

    Returns:
        True si l'audio etait probablement en Dioula
    """
    if not text:
        return False

    text_lower = text.lower()

    for pattern in _INCOHERENT_DIOULA_PATTERNS:
        if pattern in text_lower:
            logger.info(f"[STT] Detection Dioula probable: pattern '{pattern}' trouve")
            return True

    # Si la probabilite de langue est basse (< 70 %), c'est suspect
    if 0 < language_probability < 0.7:
        logger.info(
            f"[STT] Detection Dioula probable: probabilite langue faible ({language_probability:.2f})"
        )
        return True

    return False
