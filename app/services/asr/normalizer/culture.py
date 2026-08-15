"""Étape 4 : reconstruction contextuelle de cultures par fusion de fragments."""
import json
import logging
import unicodedata
from typing import Optional

from app.services.asr.normalizer.data import _NLU_CONCEPTS_PATH

logger = logging.getLogger(__name__)

_AGRI_VERBS: frozenset[str] = frozenset({
    "sɛnɛ", "sene", "tigɛ", "tige", "bɔ", "bo",
    "fere", "feere", "dumu", "mara", "filɛ", "file",
})

_GRAMMAR_WORDS: frozenset[str] = frozenset({
    "n", "ne", "i", "a", "an", "aw", "u", "o",
    "bɛ", "be", "tɛ", "te", "ye", "ma", "bɛna", "tɛna",
    "fɛ", "fe", "ka", "la", "na", "ni", "wa",
    "se", "kɛ", "ke", "don", "min",
})

_NEVER_FUSE: frozenset[str] = frozenset({
    "n", "ne", "i", "a", "an", "ni", "u", "o", "aw",
    "bɛ", "be", "tɛ", "te", "fɛ", "fe", "ye", "ma",
    "bɛna", "tɛna", "se", "kɛ", "ke", "don", "min",
    "wa", "la", "na",
})

_CULTURE_VOCAB: dict[str, str] = {}


def _load_culture_vocab() -> dict[str, str]:
    """Charge les noms de cultures depuis nlu_concepts.json.

    Ne garde que les mots dioula/bambara (pas les mots français/anglais).
    """
    vocab: dict[str, str] = {}
    try:
        with open(_NLU_CONCEPTS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        exclude = {
            "riz", "riziere", "rizière", "rice", "maïs", "mais", "corn", "maize",
            "mil", "sorgho", "millet", "fonio", "arachide", "cacahuete", "cacahuète",
            "groundnut", "peanut", "yam", "igname", "ignames", "cassava", "manioc",
            "gari", "haricot", "haricots", "cowpea", "niebe", "niébé", "coton",
            "cotton", "fibre", "sesame", "sésame", "banane", "bananes", "plantain",
            "banana", "tomate", "tomates", "tomato", "oignon", "oignons", "patate",
            "gombo", "okra", "cacao", "cacaoyer", "chocolat", "café", "cafe",
            "caféier", "ananas", "pineapple", "mangue", "mango", "citron", "lime",
            "agrume", "agrumes", "néré", "parkia", "sweet potato",
            "cacaoforo", "kafeforo", "gros mil", "petit mil", "patate douce",
        }
        for concept_name, concept_data in data.get("concepts", {}).items():
            if not concept_name.startswith("CULTURE_"):
                continue
            if not isinstance(concept_data, dict):
                continue
            for kw in concept_data.get("keywords", []):
                kw_clean = kw.lower().strip()
                if kw_clean in exclude or len(kw_clean) <= 2:
                    continue
                kw_norm = unicodedata.normalize('NFD', kw_clean)
                kw_norm = ''.join(c for c in kw_norm if unicodedata.category(c) != 'Mn')
                vocab[kw_norm] = kw_clean
        logger.info("[ASR-NORM] %d mots-clés cultures chargés pour reconstruction", len(vocab))
    except Exception as e:
        logger.error("[ASR-NORM] Erreur chargement vocab cultures: %s", e)
    return vocab


def _strip_tones_simple(text: str) -> str:
    """Retire les diacritiques de ton."""
    nfd = unicodedata.normalize('NFD', text)
    return ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')


def _normalize_ny(text: str) -> str:
    """Normalise ɲ → ny pour la comparaison (même phonème, deux écritures)."""
    return text.replace('ɲ', 'ny')


def _has_culture_word(text: str) -> bool:
    """Vérifie si le texte contient déjà un mot-clé de culture connu."""
    text_norm = _normalize_ny(_strip_tones_simple(text.lower()))
    words = set(text_norm.replace("'", " ").replace("-", " ").split())
    for culture_norm in _CULTURE_VOCAB:
        culture_check = _normalize_ny(culture_norm)
        if culture_check in words:
            return True
        if ' ' in culture_check and culture_check in text_norm:
            return True
    return False


def _try_culture_reconstruction(text: str) -> str:
    """Étape 4 : détection contextuelle de cultures par fusion de fragments.

    NeMo Soloni fragmente les mots qu'il ne connaît pas en petits mots
    bambara valides. Exemples réels :
        kakawo → ka ka aw / ka ka o / ka o / ka aw
        kafe   → ka fɛ / ka fe
        mangoro → mangogo

    Cette étape :
    1. Vérifie qu'un verbe agricole est présent (sɛnɛ, tigɛ, etc.)
    2. Vérifie qu'aucune culture n'est déjà reconnue
    3. Fusionne des fenêtres de 1, 2, 3 mots adjacents
    4. Compare chaque fusion aux noms de cultures par Levenshtein
    5. Remplace si match trouvé (tolérance : distance ≤ min(3, len//2))
    """
    if not _CULTURE_VOCAB:
        return text

    words = text.lower().split()

    has_agri_verb = any(w in _AGRI_VERBS for w in words)
    if not has_agri_verb:
        return text

    if _has_culture_word(text):
        return text

    try:
        from rapidfuzz.distance import Levenshtein
    except ImportError:
        return text

    best_match: Optional[str] = None
    best_distance = 999
    best_start = -1
    best_end = -1

    for window_size in (1, 2, 3):
        for i in range(len(words) - window_size + 1):
            fragment_words = words[i:i + window_size]

            if any(w in _AGRI_VERBS for w in fragment_words):
                continue

            if any(w in _NEVER_FUSE for w in fragment_words):
                continue

            fused = ''.join(fragment_words)
            fused_norm = _strip_tones_simple(fused)

            if len(fused_norm) < 4:
                continue

            max_dist = min(3, len(fused_norm) // 2)

            for culture_norm, culture_correct in _CULTURE_VOCAB.items():
                if abs(len(fused_norm) - len(culture_norm)) > max_dist:
                    continue

                dist = Levenshtein.distance(fused_norm, culture_norm, score_cutoff=max_dist)
                if dist <= max_dist and dist < best_distance:
                    best_distance = dist
                    best_match = culture_correct
                    best_start = i
                    best_end = i + window_size

    if best_match and best_start >= 0:
        original_words = text.split()
        new_words = original_words[:best_start] + [best_match] + original_words[best_end:]
        result = ' '.join(new_words)
        logger.info(
            "[ASR-NORM] Culture reconstruite: '%s' → '%s' (culture=%s, distance=%d)",
            text, result, best_match, best_distance,
        )
        return result

    return text


_CULTURE_VOCAB.update(_load_culture_vocab())
