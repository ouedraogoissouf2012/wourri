"""Chargement unique des dictionnaires du normalizer post-ASR."""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_CORRECTIONS_PATH = _PROJECT_ROOT / "dictionnaires" / "asr_corrections.json"
_NLU_CONCEPTS_PATH = _PROJECT_ROOT / "dictionnaires" / "nlu_concepts.json"


def _load_exact_corrections() -> dict[str, str]:
    """Charge les corrections exactes depuis asr_corrections.json.

    Fusionne toutes les catégories en un dict plat {wrong: correct}.
    """
    corrections: dict[str, str] = {}
    try:
        with open(_CORRECTIONS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        for category, pairs in data.get("corrections", {}).items():
            if isinstance(pairs, dict):
                corrections.update(pairs)
        logger.info("[ASR-NORM] %d corrections exactes chargées depuis JSON", len(corrections))
    except FileNotFoundError:
        logger.warning("[ASR-NORM] Fichier %s non trouvé", _CORRECTIONS_PATH)
    except Exception as e:
        logger.error("[ASR-NORM] Erreur chargement corrections: %s", e)
    return corrections


def _load_nlu_vocabulary() -> set[str]:
    """Charge les mots-clés du NLU comme vocabulaire de référence pour le fuzzy matching."""
    vocab: set[str] = set()
    try:
        with open(_NLU_CONCEPTS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        concepts = data.get("concepts", {})
        for name, concept_data in concepts.items():
            if isinstance(concept_data, dict):
                for kw in concept_data.get("keywords", []):
                    vocab.add(kw.lower())
            elif isinstance(concept_data, list):
                for kw in concept_data:
                    vocab.add(kw.lower())
        logger.info("[ASR-NORM] %d mots-clés NLU chargés pour fuzzy matching", len(vocab))
    except Exception as e:
        logger.error("[ASR-NORM] Erreur chargement vocabulaire NLU: %s", e)
    return vocab


_EXACT_CORRECTIONS = _load_exact_corrections()
_NLU_VOCAB = _load_nlu_vocabulary()
_NLU_VOCAB_LIST = sorted(_NLU_VOCAB)
