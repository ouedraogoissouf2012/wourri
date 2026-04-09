"""
WOURI - Repository du dictionnaire (accès aux données)
Principe: Single Responsibility + Repository Pattern
Charge le JSON une seule fois, fournit des lookups rapides.
Gère la normalisation des tons pour le matching ASR.
"""
import json
import logging
import os
import unicodedata
from typing import Optional
from .interfaces import IDictionaryRepository, DictionaryEntry, Direction

logger = logging.getLogger(__name__)


def strip_tones(text: str) -> str:
    """Enlève les marques de ton (accents graves/aigus) du texte bambara.
    L'ASR transcrit sans tons, mais le dictionnaire Bamadaba a des tons.
    Ex: 'màlo' -> 'malo', 'sɛ̀nɛ' -> 'sɛnɛ', 'kàba' -> 'kaba'
    Garde les caractères spéciaux bambara (ɛ, ɔ, ŋ, ɲ).
    """
    result = []
    for char in unicodedata.normalize('NFD', text):
        cat = unicodedata.category(char)
        # Garder tout sauf les marques de ton (combining accents)
        # Mn = Mark, nonspacing (accents combinants)
        if cat != 'Mn':
            result.append(char)
    return ''.join(result)


class DictionaryRepository(IDictionaryRepository):
    """Accès au dictionnaire Bambara-Français depuis les fichiers JSON.
    Double indexation: avec tons (original) et sans tons (pour matching ASR).
    """

    def __init__(self, dictionnaires_dir: str):
        self._dir = dictionnaires_dir
        # Index avec tons (clés originales du dictionnaire)
        self._words_bam_fr: dict[str, DictionaryEntry] = {}
        self._words_fr_bam: dict[str, DictionaryEntry] = {}
        # Index SANS tons (pour matching avec sortie ASR)
        self._words_bam_fr_notone: dict[str, DictionaryEntry] = {}
        self._phrases_bam_fr: dict[str, str] = {}
        self._phrases_bam_fr_notone: dict[str, str] = {}
        self._phrases_fr_bam: dict[str, str] = {}
        self._patterns_bam_fr: dict[str, str] = {}
        self._patterns_fr_bam: dict[str, str] = {}
        self._loaded = False
        self._stats = {"total_mots": 0, "total_phrases": 0, "total_patterns": 0}

    def _ensure_loaded(self):
        """Lazy loading : charge les données au premier accès"""
        if self._loaded:
            return
        self._load_dictionary()
        self._load_phrases()
        self._loaded = True

    # Catégories agricoles à prioriser (WOURI = assistant agricole)
    _AGRI_CATEGORIES = {"agriculture", "agriculture.cereales", "agriculture.legumes",
                         "agriculture.elevage", "agriculture.outils", "meteo", "nature"}

    def _merge_notone_entry(self, key_notone: str, entry: DictionaryEntry):
        """Fusionne une entrée dans l'index sans tons.
        En cas de collision (ex: kàba/kába -> kaba), fusionne les traductions
        en mettant les traductions agricoles en premier.
        """
        existing = self._words_bam_fr_notone.get(key_notone)
        if existing is None:
            self._words_bam_fr_notone[key_notone] = entry
            return

        # Collision: fusionner les traductions
        new_is_agri = any(entry.category.startswith(c) for c in self._AGRI_CATEGORIES) if entry.category else False
        existing_is_agri = any(existing.category.startswith(c) for c in self._AGRI_CATEGORIES) if existing.category else False

        # Fusionner les listes de traductions (dédupliquées)
        merged_translations = list(existing.translations)
        for t in entry.translations:
            if t not in merged_translations:
                merged_translations.append(t)

        # Si la nouvelle entrée est agricole et l'existante ne l'est pas,
        # mettre les traductions agricoles en premier
        if new_is_agri and not existing_is_agri:
            merged_translations = list(entry.translations) + [t for t in existing.translations if t not in entry.translations]
            category = entry.category
        else:
            category = existing.category

        self._words_bam_fr_notone[key_notone] = DictionaryEntry(
            word=existing.word,
            translations=merged_translations,
            category=category,
            source=existing.source,
            variants=existing.variants,
            examples=existing.examples,
            part_of_speech=existing.part_of_speech,
        )

    def _load_dictionary(self):
        """Charge le dictionnaire de mots"""
        dict_path = os.path.join(self._dir, "bambara_francais.json")
        if not os.path.exists(dict_path):
            logger.warning(f"[DictRepo] Fichier dictionnaire non trouvé: {dict_path}")
            return

        with open(dict_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Charger les mots
        mots = data.get("mots", {})
        for bam_word, info in mots.items():
            entry = DictionaryEntry(
                word=bam_word,
                translations=info.get("fr", []) if isinstance(info.get("fr"), list) else [info.get("fr", "")],
                category=info.get("categorie", ""),
                source=info.get("source", ""),
                variants=info.get("variantes", []),
                examples=info.get("exemples", []),
                part_of_speech=info.get("pos", ""),
            )
            # Index Bambara -> Français (avec tons)
            key_toned = bam_word.lower()
            self._words_bam_fr[key_toned] = entry
            # Index sans tons (pour matching ASR)
            # En cas de collision (ex: kàba/kába -> kaba), fusionner les traductions
            # et prioriser les catégories agricoles
            key_notone = strip_tones(key_toned)
            self._merge_notone_entry(key_notone, entry)
            # Variantes aussi
            for var in entry.variants:
                self._words_bam_fr[var.lower()] = entry
                self._merge_notone_entry(strip_tones(var.lower()), entry)

            # Index inverse Français -> Bambara
            for fr_word in entry.translations:
                if fr_word:
                    fr_key = fr_word.lower().strip()
                    if fr_key not in self._words_fr_bam:
                        self._words_fr_bam[fr_key] = DictionaryEntry(
                            word=fr_key,
                            translations=[bam_word],
                            category=entry.category,
                            source=entry.source,
                            part_of_speech=entry.part_of_speech,
                        )
                    else:
                        if bam_word not in self._words_fr_bam[fr_key].translations:
                            self._words_fr_bam[fr_key].translations.append(bam_word)

        # Charger les patterns + générer les variantes sans tons
        self._patterns_bam_fr = data.get("patterns_bam_fr", {})
        # Auto-générer les patterns sans tons pour matching ASR
        notone_patterns = {}
        for pat, replacement in self._patterns_bam_fr.items():
            pat_notone = strip_tones(pat)
            if pat_notone != pat and pat_notone not in self._patterns_bam_fr:
                notone_patterns[pat_notone] = replacement
        self._patterns_bam_fr.update(notone_patterns)
        self._patterns_fr_bam = data.get("patterns_fr_bam", {})
        # Auto-générer les patterns FR->BAM sans accents (mais->maïs, riz->riz)
        notone_fr_patterns = {}
        for pat, replacement in self._patterns_fr_bam.items():
            pat_noaccent = strip_tones(pat)
            if pat_noaccent != pat and pat_noaccent not in self._patterns_fr_bam:
                notone_fr_patterns[pat_noaccent] = replacement
        self._patterns_fr_bam.update(notone_fr_patterns)

        self._stats["total_mots"] = len(self._words_bam_fr)
        self._stats["total_mots_notone"] = len(self._words_bam_fr_notone)
        self._stats["total_patterns"] = len(self._patterns_bam_fr) + len(self._patterns_fr_bam)
        logger.info(f"[DictRepo] {len(self._words_bam_fr)} mots BAM->FR ({len(self._words_bam_fr_notone)} sans tons), {len(self._words_fr_bam)} mots FR->BAM, {self._stats['total_patterns']} patterns")

    def _load_phrases(self):
        """Charge les phrases parallèles"""
        phrases_path = os.path.join(self._dir, "bambara_phrases.json")
        if not os.path.exists(phrases_path):
            return

        with open(phrases_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for entry in data.get("phrases", []):
            bam = entry.get("bam", "").lower().strip()
            fr = entry.get("fr", "").strip()
            if bam and fr:
                self._phrases_bam_fr[bam] = fr
                # Indexer aussi sans tons pour matching ASR
                bam_notone = strip_tones(bam)
                if bam_notone != bam:
                    self._phrases_bam_fr_notone[bam_notone] = fr
                self._phrases_fr_bam[fr.lower()] = entry.get("bam", "")

        self._stats["total_phrases"] = len(self._phrases_bam_fr)
        logger.info(f"[DictRepo] {len(self._phrases_bam_fr)} phrases parallèles chargées")

    def lookup_word(self, word: str, direction: Direction) -> Optional[DictionaryEntry]:
        self._ensure_loaded()
        key = word.lower().strip()
        if direction == Direction.BAM_TO_FR:
            # Chercher avec tons d'abord, puis sans tons
            result = self._words_bam_fr.get(key)
            if result is None:
                result = self._words_bam_fr_notone.get(strip_tones(key))
            return result
        else:
            return self._words_fr_bam.get(key)

    def lookup_phrase(self, phrase: str, direction: Direction) -> Optional[str]:
        self._ensure_loaded()
        key = phrase.lower().strip()
        if direction == Direction.BAM_TO_FR:
            result = self._phrases_bam_fr.get(key)
            if result is None:
                result = self._phrases_bam_fr_notone.get(strip_tones(key))
            return result
        else:
            return self._phrases_fr_bam.get(key)

    def get_all_words(self, direction: Direction) -> dict[str, DictionaryEntry]:
        """Accès direct à l'index complet (pour le WordTranslator)"""
        self._ensure_loaded()
        if direction == Direction.BAM_TO_FR:
            return self._words_bam_fr
        return self._words_fr_bam

    def get_patterns(self, direction: Direction) -> dict[str, str]:
        self._ensure_loaded()
        if direction == Direction.BAM_TO_FR:
            return self._patterns_bam_fr
        return self._patterns_fr_bam

    def get_stats(self) -> dict:
        self._ensure_loaded()
        return {
            **self._stats,
            "mots_bam_fr": len(self._words_bam_fr),
            "mots_fr_bam": len(self._words_fr_bam),
            "phrases_bam_fr": len(self._phrases_bam_fr),
        }
