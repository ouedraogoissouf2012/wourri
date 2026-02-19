"""
WOURI - Interfaces de traduction (Contrats abstraits)
Principe: Interface Segregation + Dependency Inversion
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Direction(Enum):
    BAM_TO_FR = "bam_fr"
    FR_TO_BAM = "fr_bam"


@dataclass
class TranslationResult:
    """Résultat d'une traduction avec métadonnées"""
    text: str
    source_text: str
    direction: Direction
    strategy_used: str  # Quelle stratégie a produit ce résultat
    confidence: float = 0.0  # 0.0 à 1.0
    words_matched: int = 0
    words_total: int = 0


@dataclass
class DictionaryEntry:
    """Une entrée du dictionnaire"""
    word: str
    translations: list[str] = field(default_factory=list)
    category: str = ""
    source: str = ""
    variants: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    part_of_speech: str = ""  # nom, verbe, adjectif...


class ITranslator(ABC):
    """Interface pour toute stratégie de traduction"""

    @abstractmethod
    def translate(self, text: str, direction: Direction) -> Optional[TranslationResult]:
        """Traduit un texte. Retourne None si incapable de traduire."""
        pass

    @abstractmethod
    def can_handle(self, text: str, direction: Direction) -> bool:
        """Indique si cette stratégie peut gérer cette traduction."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Nom de la stratégie (pour les logs)"""
        pass

    @property
    @abstractmethod
    def priority(self) -> int:
        """Priorité (plus bas = essayé en premier). Ex: 1=dico, 2=pattern, 3=NLLB"""
        pass


class IDictionaryRepository(ABC):
    """Interface pour l'accès aux données du dictionnaire"""

    @abstractmethod
    def lookup_word(self, word: str, direction: Direction) -> Optional[DictionaryEntry]:
        """Cherche un mot dans le dictionnaire"""
        pass

    @abstractmethod
    def lookup_phrase(self, phrase: str, direction: Direction) -> Optional[str]:
        """Cherche une phrase complète"""
        pass

    @abstractmethod
    def get_patterns(self, direction: Direction) -> dict[str, str]:
        """Récupère les patterns grammaticaux"""
        pass

    @abstractmethod
    def get_stats(self) -> dict:
        """Statistiques du dictionnaire"""
        pass


class ICollector(ABC):
    """Interface pour les collecteurs de données"""

    @abstractmethod
    def fetch(self) -> list[DictionaryEntry]:
        """Collecte les entrées depuis la source"""
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Nom de la source"""
        pass
