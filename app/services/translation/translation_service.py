"""
WOURI - Service de traduction (Orchestrateur)
Principe: Strategy Pattern + Chain of Responsibility
Essaie chaque stratégie par priorité jusqu'à obtenir un résultat satisfaisant.
"""
import os
from typing import Optional
from .interfaces import ITranslator, TranslationResult, Direction
from .dictionary_repository import DictionaryRepository
from .word_translator import WordTranslator
from .nllb_translator import NLLBTranslator


class TranslationService:
    """
    Orchestrateur de traduction.
    Chaîne de stratégies triées par priorité :
      1. Dictionnaire (rapide, précis, limité)
      2. NLLB (lent, large couverture)
    """

    _instance: Optional["TranslationService"] = None

    def __init__(self, dictionnaires_dir: str):
        self._repository = DictionaryRepository(dictionnaires_dir)
        self._strategies: list[ITranslator] = []
        self._nllb: Optional[NLLBTranslator] = None
        self._setup_strategies()

    @classmethod
    def get_instance(cls) -> "TranslationService":
        """Singleton - une seule instance du service"""
        if cls._instance is None:
            # Remonter de app/services/translation/ vers wouri-api/
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            dict_dir = os.path.join(base_dir, "dictionnaires")
            cls._instance = cls(dict_dir)
        return cls._instance

    def _setup_strategies(self):
        """Configure la chaîne de stratégies"""
        # Stratégie 1 : Dictionnaire (priorité haute)
        word_translator = WordTranslator(self._repository)
        self._strategies.append(word_translator)

        # Stratégie 2 : NLLB (fallback)
        self._nllb = NLLBTranslator()
        self._strategies.append(self._nllb)

        # Trier par priorité
        self._strategies.sort(key=lambda s: s.priority)
        names = [s.name for s in self._strategies]
        print(f"[TranslationService] Stratégies: {' -> '.join(names)}")

    def translate(self, text: str, direction: Direction) -> TranslationResult:
        """
        Traduit en essayant chaque stratégie par priorité.
        Retourne le meilleur résultat trouvé.
        """
        if not text or not text.strip():
            return TranslationResult(
                text=text or "",
                source_text=text or "",
                direction=direction,
                strategy_used="none",
                confidence=0.0,
            )

        best_result: Optional[TranslationResult] = None

        for strategy in self._strategies:
            try:
                result = strategy.translate(text, direction)

                if result is None:
                    continue

                log_text = result.text[:60] + "..." if len(result.text) > 60 else result.text
                print(f"[{strategy.name}] '{text[:40]}' -> '{log_text}' (conf: {result.confidence:.1%})")

                # Si confiance haute, on prend directement
                if result.confidence >= 0.7:
                    return result

                # Sinon on garde le meilleur
                if best_result is None or result.confidence > best_result.confidence:
                    best_result = result

            except Exception as e:
                print(f"[{strategy.name}] Erreur: {e}")
                continue

        # Retourner le meilleur résultat ou le texte original
        if best_result:
            return best_result

        return TranslationResult(
            text=text,
            source_text=text,
            direction=direction,
            strategy_used="passthrough",
            confidence=0.0,
        )

    def translate_to_french(self, bambara_text: str) -> str:
        """Raccourci : Bambara -> Français"""
        result = self.translate(bambara_text, Direction.BAM_TO_FR)
        return result.text

    def translate_to_bambara(self, french_text: str) -> str:
        """Raccourci : Français -> Bambara"""
        result = self.translate(french_text, Direction.FR_TO_BAM)
        return result.text

    def get_nllb_model_and_tokenizer(self):
        """Accès NLLB pour compatibilité avec tts_bambara"""
        if self._nllb:
            return self._nllb.get_model_and_tokenizer()
        return None, None

    def get_repository(self) -> DictionaryRepository:
        """Accès au repository (pour stats, debug)"""
        return self._repository

    def get_stats(self) -> dict:
        """Statistiques complètes du service"""
        repo_stats = self._repository.get_stats()
        return {
            "dictionnaire": repo_stats,
            "strategies": [
                {"nom": s.name, "priorite": s.priority}
                for s in self._strategies
            ],
        }
