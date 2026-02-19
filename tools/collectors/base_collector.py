"""
WOURI - Collecteur de base (Template Method Pattern)
Chaque source hérite et implémente ses spécificités.
"""
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class CollectedEntry:
    """Entrée collectée depuis n'importe quelle source"""
    word: str
    translations_fr: list[str] = field(default_factory=list)
    category: str = ""
    part_of_speech: str = ""
    source: str = ""
    variants: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)


@dataclass
class CollectedPhrase:
    """Phrase parallèle collectée"""
    bam: str = ""
    fr: str = ""
    source: str = ""


class BaseCollector(ABC):
    """Template Method pour la collecte de données"""

    @property
    @abstractmethod
    def source_name(self) -> str:
        pass

    @abstractmethod
    def _fetch_raw(self) -> str:
        """Récupère les données brutes (texte, JSON, etc.)"""
        pass

    @abstractmethod
    def _parse_entries(self, raw_data: str) -> list[CollectedEntry]:
        """Parse les données brutes en entrées"""
        pass

    def _parse_phrases(self, raw_data: str) -> list[CollectedPhrase]:
        """Parse les phrases parallèles (optionnel)"""
        return []

    def _normalize_entry(self, entry: CollectedEntry) -> CollectedEntry:
        """Normalise une entrée (nettoyage commun)"""
        entry.word = entry.word.strip().lower()
        entry.translations_fr = [t.strip() for t in entry.translations_fr if t.strip()]
        entry.category = entry.category.strip().lower()
        entry.source = self.source_name
        entry.variants = [v.strip().lower() for v in entry.variants if v.strip()]
        return entry

    def collect(self) -> tuple[list[CollectedEntry], list[CollectedPhrase]]:
        """Template Method : fetch -> parse -> normalize"""
        print(f"[{self.source_name}] Début de la collecte...")

        try:
            raw = self._fetch_raw()
            print(f"[{self.source_name}] Données brutes récupérées ({len(raw)} chars)")
        except Exception as e:
            print(f"[{self.source_name}] Erreur fetch: {e}")
            return [], []

        entries = self._parse_entries(raw)
        print(f"[{self.source_name}] {len(entries)} entrées parsées")

        phrases = self._parse_phrases(raw)
        if phrases:
            print(f"[{self.source_name}] {len(phrases)} phrases parsées")

        # Normaliser
        entries = [self._normalize_entry(e) for e in entries if e.word and e.translations_fr]

        print(f"[{self.source_name}] {len(entries)} entrées après normalisation")
        return entries, phrases
