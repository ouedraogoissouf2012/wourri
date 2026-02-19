"""
WOURI - Package de traduction
Interface publique unique pour tout le projet.
"""
from .interfaces import Direction, TranslationResult, DictionaryEntry
from .translation_service import TranslationService


def get_translation_service() -> TranslationService:
    """Point d'entrée unique pour obtenir le service de traduction"""
    return TranslationService.get_instance()


__all__ = [
    "Direction",
    "TranslationResult",
    "DictionaryEntry",
    "TranslationService",
    "get_translation_service",
]
