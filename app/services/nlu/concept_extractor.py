"""
WOURI - NLU Extracteur de Concepts
Scanne le texte bambara/dioula et retourne les concepts agricoles trouvés.

Stratégie de matching (ordre de priorité):
1. Phrases multi-mots exactes (ex: "i ni sɔgɔma", "ji boli")
2. Mots seuls exacts (ex: "malo", "kaba", "sɛnɛ")
3. Correspondance partielle/préfixe (ex: "kabaforo" contient "kaba")

Robustesse NeMo TDT: les tons sont strippés avant comparaison
(NeMo transcrit souvent sans tons: sɛnɛ → sene, kɔrɔ → koro, etc.)
"""
import unicodedata
from typing import Dict, List, Tuple


def strip_tones(text: str) -> str:
    """Enlève les marques de ton (accents combinants) du bambara.
    Garde les caractères spéciaux bambara (ɛ, ɔ, ŋ, ɲ) car ce sont
    des caractères de base, pas des diacritiques.
    Ex: 'sɛ̀nɛ̀' → 'sɛnɛ', 'kàba' → 'kaba', 'bɛ́ɛ́' → 'bɛɛ'
    """
    result = []
    for char in unicodedata.normalize('NFD', text):
        if unicodedata.category(char) != 'Mn':
            result.append(char)
    return ''.join(result)


class ConceptExtractor:
    """Extrait les concepts agricoles d'un texte bambara/dioula."""

    def __init__(self, concepts_config: dict):
        self._concepts = concepts_config.get("concepts", {})
        # Index inversé: keyword_normalisé → [concept_name, ...]
        # Séparé en deux index: multi-mots et mono-mot
        self._multiword_index: Dict[str, List[str]] = {}
        self._word_index: Dict[str, List[str]] = {}
        # Index pour partial matching: partial_keyword → [concept_name, ...]
        self._partial_index: Dict[str, List[str]] = {}
        self._build_indexes()

    def _build_indexes(self):
        """Construit les index de recherche depuis la config."""
        for concept_name, concept_data in self._concepts.items():
            keywords = concept_data.get("keywords", [])
            for kw in keywords:
                kw_norm = strip_tones(kw.lower().strip())
                if not kw_norm:
                    continue
                if ' ' in kw_norm:
                    # Phrase multi-mots
                    if kw_norm not in self._multiword_index:
                        self._multiword_index[kw_norm] = []
                    if concept_name not in self._multiword_index[kw_norm]:
                        self._multiword_index[kw_norm].append(concept_name)
                else:
                    # Mot seul
                    if kw_norm not in self._word_index:
                        self._word_index[kw_norm] = []
                    if concept_name not in self._word_index[kw_norm]:
                        self._word_index[kw_norm].append(concept_name)

            # Index de matching partiel
            for partial_kw in concept_data.get("partial", []):
                pk_norm = strip_tones(partial_kw.lower().strip())
                if pk_norm not in self._partial_index:
                    self._partial_index[pk_norm] = []
                if concept_name not in self._partial_index[pk_norm]:
                    self._partial_index[pk_norm].append(concept_name)

    def extract(self, text: str) -> Dict[str, float]:
        """Extrait les concepts du texte.

        Args:
            text: Texte bambara/dioula (transcription ASR ou texte brut)

        Returns:
            Dict {concept_name: score_confiance} où score ∈ [0.0, 1.0]
            1.0 = match exact, 0.7 = match partiel
        """
        if not text or not text.strip():
            return {}

        text_norm = strip_tones(text.lower().strip())
        # Normaliser les apostrophes (b'a fɛ → b a fɛ pour le matching de mots)
        text_for_words = text_norm.replace("'", " ").replace("-", " ")
        text_words = set(text_for_words.split())

        found: Dict[str, float] = {}

        # ---- Étape 1: Phrases multi-mots (priorité haute) ----
        # Trier par longueur décroissante pour matcher les plus longues en premier
        for kw_norm, concept_names in sorted(
            self._multiword_index.items(),
            key=lambda x: len(x[0]),
            reverse=True
        ):
            if kw_norm in text_norm:
                for cn in concept_names:
                    if cn not in found:
                        found[cn] = 1.0

        # ---- Étape 2: Mots seuls exacts ----
        for word in text_words:
            if word in self._word_index:
                for cn in self._word_index[word]:
                    if cn not in found:
                        found[cn] = 1.0

        # ---- Étape 3: Matching partiel (ex: "kabaforo" contient "kaba") ----
        for partial_kw, concept_names in self._partial_index.items():
            for cn in concept_names:
                if cn not in found:
                    # Vérifier si partial_kw apparaît dans le texte (en tant que sous-chaîne de mot)
                    if partial_kw in text_norm:
                        found[cn] = 0.7

        return found

    def get_concept_label(self, concept_name: str) -> str:
        """Retourne le label français d'un concept."""
        concept_data = self._concepts.get(concept_name, {})
        return concept_data.get("label_fr", concept_name)

    def has_agricultural_concepts(self, concepts: Dict[str, float]) -> bool:
        """Vérifie si au moins un concept agricole est présent."""
        agricultural_prefixes = (
            "CULTURE_", "ANIMAL_", "ACTION_PLANTER", "ACTION_RECOLTER",
            "ACTION_ARROSER", "ACTION_LABOURER", "ACTION_TRAITER",
            "PROBLEME_", "TEMPS_SAISON", "ENGRAIS_"
        )
        return any(
            any(k.startswith(p) for p in agricultural_prefixes)
            for k in concepts
        )

    def get_cultures(self, concepts: Dict[str, float]) -> List[Tuple[str, str]]:
        """Retourne les cultures trouvées: [(concept_name, label_fr), ...]"""
        cultures = []
        for cn in concepts:
            if cn.startswith("CULTURE_"):
                label = self.get_concept_label(cn)
                cultures.append((cn, label))
        return cultures

    def get_animals(self, concepts: Dict[str, float]) -> List[Tuple[str, str]]:
        """Retourne les animaux trouvés: [(concept_name, label_fr), ...]"""
        animals = []
        for cn in concepts:
            if cn.startswith("ANIMAL_"):
                label = self.get_concept_label(cn)
                animals.append((cn, label))
        return animals
