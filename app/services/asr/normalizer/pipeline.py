"""Pipeline principal de normalisation post-ASR."""
import logging

from app.services.asr.normalizer.culture import _try_culture_reconstruction
from app.services.asr.normalizer.exact import _apply_exact_corrections, _apply_nemo_fusions
from app.services.asr.normalizer.fuzzy import _apply_fuzzy_matching

logger = logging.getLogger(__name__)


def normalize_asr_output(text: str) -> str:
    """Pipeline complet de normalisation post-ASR.

    Ordre :
    1. Corrections exactes multi-mots (JSON) — salutations, particules
    2. Corrections fusions NeMo — fusions syllabiques
    3. Fuzzy matching Levenshtein — mots isolés vs vocabulaire NLU
    4. Reconstruction contextuelle de cultures — fusion de fragments

    Args:
        text: transcription brute de l'ASR.

    Returns:
        texte corrigé, prêt pour le NLU et la traduction.
    """
    if not text:
        return text

    original = text

    text = _apply_exact_corrections(text)
    text = _apply_nemo_fusions(text)
    text = _apply_fuzzy_matching(text)
    text = _try_culture_reconstruction(text)

    if text != original:
        logger.info("[ASR-NORM] '%s' → '%s'", original, text)

    return text
