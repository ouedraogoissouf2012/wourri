"""Compat : le normalizer post-ASR vit dans app.services.asr.normalizer."""
from app.services.asr.normalizer import (
    _apply_exact_corrections,
    _find_best_culture_fragment,
    _fuzzy_correct_word,
    _is_nasalization_only,
    _max_distance_for_word,
    normalize_asr_output,
)

__all__ = [
    "normalize_asr_output",
    "_apply_exact_corrections",
    "_fuzzy_correct_word",
    "_max_distance_for_word",
    "_is_nasalization_only",
    "_find_best_culture_fragment",
]
