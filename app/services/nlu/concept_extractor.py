"""
WOURI - NLU Extracteur de Concepts
Scanne le texte bambara/dioula et retourne les concepts agricoles trouvés.

Stratégie de matching (ordre de priorité):
1. Phrases multi-mots exactes (ex: "i ni sɔgɔma", "ji boli")
2. Mots seuls exacts (ex: "malo", "kaba", "sɛnɛ")
3. Correspondance partielle/préfixe (ex: "kabaforo" contient "kaba")

Homographes (ADR-0041, section « homographes » de nlu_concepts.json, voir
homographes.py) : une occurrence d'un mot-clé de culture qui est aussi un mot
français courant (« mais », « fini »…) hors de ses contextes sûrs est douteuse.
Une culture vue seulement par des occurrences douteuses est retirée si la phrase
cite une autre culture par un mot entier ou un multi-mots, gardée sinon :
« mais comment faire pour mon manioc » ne parle pas du maïs, mais « mes jeunes
mais jaunissent » reste une question sur le maïs, jamais un refus hors-sujet.
Un partiel ne suffit pas à la retirer : il est souvent faux (« organique » donne
le gombo).

Ordre du résultat (ADR-0041) : d'abord les concepts vus par un mot entier ou un
multi-mots, puis les cultures vues seulement par des homographes douteux, puis
les concepts vus seulement par un partiel ; dans chaque groupe, ordre de
première apparition dans le texte, puis ordre de nlu_concepts.json. Le premier
CULTURE_ est la culture retenue pour la phrase française, le préfixe DeepSeek et
l'IVR, et le résultat ne dépend pas de PYTHONHASHSEED.

L'intent se calcule sur tous les concepts, homographes douteux compris
(`extraire`) : la règle choisit la culture, elle ne change pas l'intent.

Robustesse NeMo TDT: les tons sont strippés avant comparaison
(NeMo transcrit souvent sans tons: sɛnɛ → sene, kɔrɔ → koro, etc.)
"""
import logging
import re
import unicodedata
from bisect import bisect_left
from typing import Dict, List, NamedTuple, Set, Tuple

from .homographes import RegleHomographe, SectionHomographesInvalide, charger_regles, graphie

logger = logging.getLogger(__name__)

# Nature d'une occurrence ; c'est aussi son rang dans l'ordre du résultat. Un
# homographe douteux gardé passe avant une culture vue seulement par un
# partiel : « mes jeunes mais ont besoin d'engrais organique » parle du maïs,
# pas du gombo que le partiel « gan » trouve dans « organique ».
MOT = 0  # mot entier ou multi-mots (homographe compris s'il est en contexte sûr)
DOUTEUX = 1  # homographe hors de ses contextes sûrs
PARTIEL = 2  # correspondance partielle

# Une culture vue par une de ces natures est « citée de façon sûre » : elle fait
# retirer les cultures vues seulement en douteux. Le partiel n'en fait pas partie
# (ADR-0041) : un faux partiel (« organique », « automatique », « Kabadougou »)
# retirait sinon la vraie culture écrite sans contexte sûr.
_NATURES_SURES = frozenset((MOT,))


class Extraction(NamedTuple):
    """Résultat de ConceptExtractor.extraire."""

    concepts: Dict[str, float]  # concepts retenus (homographes douteux retirés)
    concepts_intent: Dict[str, float]  # tous les concepts, pour calculer l'intent


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


def _normaliser(mot: str) -> str:
    """Normalisation des mots-clés et du texte : minuscules, tons retirés."""
    return strip_tones(mot.lower().strip())


def _est_un_mot(jeton: str) -> bool:
    """Vrai si le jeton contient une lettre ou un chiffre.

    Une ponctuation détachée (« semer mais ? ») n'est ni le mot précédent ni le
    mot suivant d'un homographe ; un nombre l'est : dans « le 12 mais », le mot
    avant « mais » est « 12 », pas le déterminant « le ».
    """
    return any(c.isalnum() for c in jeton)


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
        # Rang de chaque concept dans nlu_concepts.json : départage deux concepts
        # de même nature qui apparaissent à la même position du texte.
        self._rang: Dict[str, int] = {name: i for i, name in enumerate(self._concepts)}
        self._build_indexes()
        self._homographes = self._charger_homographes(concepts_config.get("homographes"))

    def _build_indexes(self):
        """Construit les index de recherche depuis la config."""
        for concept_name, concept_data in self._concepts.items():
            keywords = concept_data.get("keywords", [])
            for kw in keywords:
                kw_norm = _normaliser(kw)
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
                pk_norm = _normaliser(partial_kw)
                if pk_norm not in self._partial_index:
                    self._partial_index[pk_norm] = []
                if concept_name not in self._partial_index[pk_norm]:
                    self._partial_index[pk_norm].append(concept_name)

    def _charger_homographes(self, section) -> Dict[str, RegleHomographe]:
        """Règles des homographes ; section invalide → règle désactivée, NLU conservé.

        Une section mal formée ne doit ni désactiver tout le NLU (get_nlu_service
        renverrait None) ni passer inaperçue : elle est signalée en ERROR, et
        chaque occurrence d'un homographe compte alors comme culture, comme avant
        la section. Le fichier livré est vérifié par les tests unitaires.
        """
        try:
            return charger_regles(section, self._word_index, self._partial_index, _normaliser)
        except SectionHomographesInvalide as erreur:
            logger.error(
                "[NLU] Section « homographes » de nlu_concepts.json invalide (%s) : règle "
                "désactivée, chaque occurrence d'un homographe compte comme culture.",
                erreur,
            )
            return {}

    def _occurrences_brutes(self, text: str) -> List[Tuple[int, str, int]]:
        """Toutes les occurrences de concepts : [(position, concept, nature)].

        La position est l'indice (en caractères) du début de l'occurrence dans
        le texte normalisé ; la nature vaut MOT, PARTIEL ou DOUTEUX.
        """
        text_norm = _normaliser(text)
        # Normaliser les apostrophes (b'a fɛ → b a fɛ pour le matching de mots).
        # Même longueur que text_norm : les positions des deux textes coïncident.
        text_for_words = text_norm.replace("'", " ").replace("-", " ")
        occurrences: List[Tuple[int, str, int]] = []

        # ---- Étape 1: Phrases multi-mots (priorité haute) ----
        # Trier par longueur décroissante pour matcher les plus longues en premier
        fins_multi_mots: Set[int] = set()
        for kw_norm, concept_names in sorted(
            self._multiword_index.items(),
            key=lambda x: len(x[0]),
            reverse=True
        ):
            # Limites de mots obligatoires : `mana su` (hévéa) ne doit pas
            # matcher le marqueur temporel courant dans `mana surunya`.
            pattern = rf"(?<!\w){re.escape(kw_norm)}(?!\w)"
            for match in re.finditer(pattern, text_norm):
                fins_multi_mots.add(match.end())
                occurrences.extend((match.start(), cn, MOT) for cn in concept_names)

        # ---- Étape 2: Mots seuls exacts, dans l'ordre du texte ----
        mots = list(re.finditer(r"\S+", text_for_words))
        # Graphie de chaque mot (accents et tréma conservés) pour les contextes
        # d'homographes. Garde-fou : si le découpage diffère (mot fait seulement
        # de diacritiques), on compare les mots normalisés.
        graphies = [m.group() for m in re.finditer(r"\S+", graphie(text).replace("'", " ").replace("-", " "))]
        if len(graphies) != len(mots):
            graphies = [m.group() for m in mots]
        # Seuls les vrais mots (lettre ou chiffre) servent de mot précédent ou suivant.
        vrais_mots = [i for i, m in enumerate(mots) if _est_un_mot(m.group())]
        for i, match in enumerate(mots):
            for cn in self._word_index.get(match.group(), []):
                nature = MOT
                regle = self._homographes.get(match.group())
                if regle is not None and regle.concept == cn:
                    # Vrais mots qui encadrent le mot i (recherche dichotomique)
                    k = bisect_left(vrais_mots, i)
                    j_avant = vrais_mots[k - 1] if k > 0 else None
                    k_apres = k + 1 if k < len(vrais_mots) and vrais_mots[k] == i else k
                    j_apres = vrais_mots[k_apres] if k_apres < len(vrais_mots) else None
                    precedent = ""
                    if j_avant is not None:
                        mot_avant = mots[j_avant]
                        # « arrose-le mais » : pronom accolé, pas un déterminant ;
                        # « i ni ce mais » : « ce » termine une salutation reconnue.
                        accole = mot_avant.start() > 0 and text_norm[mot_avant.start() - 1] == "-"
                        if not accole and mot_avant.end() not in fins_multi_mots:
                            precedent = graphies[j_avant]
                    suivant = graphies[j_apres] if j_apres is not None else ""
                    if not regle.occurrence_sure(graphies[i], precedent, suivant):
                        nature = DOUTEUX
                occurrences.append((match.start(), cn, nature))

        # ---- Étape 3: Matching partiel (ex: "kabaforo" contient "kaba") ----
        for partial_kw, concept_names in self._partial_index.items():
            # Sous-chaîne de mot, comme avant : on relève en plus la position
            for match in re.finditer(re.escape(partial_kw), text_norm):
                occurrences.extend((match.start(), cn, PARTIEL) for cn in concept_names)

        return occurrences

    @staticmethod
    def _retenir(brutes: List[Tuple[int, str, int]]) -> List[Tuple[int, str, int]]:
        """Occurrences retenues parmi les occurrences brutes.

        Une occurrence douteuse ne compte que pour une culture vue seulement en
        douteux, et seulement si aucune autre culture n'est citée de façon sûre.
        """
        natures: Dict[str, Set[int]] = {}
        for _, cn, nature in brutes:
            natures.setdefault(cn, set()).add(nature)
        culture_sure = any(
            cn.startswith("CULTURE_") and ns & _NATURES_SURES for cn, ns in natures.items()
        )
        return [
            (position, cn, nature) for position, cn, nature in brutes
            if nature != DOUTEUX or (natures[cn] == {DOUTEUX} and not culture_sure)
        ]

    def _ordonner(self, occurrences: List[Tuple[int, str, int]]) -> Dict[str, float]:
        """Concepts des occurrences, dans l'ordre du résultat (voir l'en-tête)."""
        # Concept → (sa meilleure nature, première position de cette nature)
        meilleure: Dict[str, Tuple[int, int]] = {}
        for position, cn, nature in occurrences:
            if cn not in meilleure or (nature, position) < meilleure[cn]:
                meilleure[cn] = (nature, position)

        ordre = sorted(meilleure, key=lambda cn: (*meilleure[cn], self._rang[cn]))
        return {cn: (0.7 if meilleure[cn][0] == PARTIEL else 1.0) for cn in ordre}

    def extraire(self, text: str) -> Extraction:
        """Concepts retenus, et tous les concepts pour calculer l'intent.

        L'intent se calcule sur tous les concepts, homographes douteux compris
        (classés après les mots entiers) : il reste celui que donnerait le texte
        sans la règle des homographes. Sinon, retirer une culture changeait le
        barème de l'intent (10 points par culture) : « ani sogoma mais comment
        faire pour mon manioc » recevait une salutation au lieu d'un conseil.
        Le premier CULTURE_ est le même dans les deux vues.
        """
        if not text or not text.strip():
            return Extraction({}, {})
        brutes = self._occurrences_brutes(text)
        return Extraction(self._ordonner(self._retenir(brutes)), self._ordonner(brutes))

    def extract(self, text: str) -> Dict[str, float]:
        """Extrait les concepts du texte.

        Args:
            text: Texte bambara/dioula (transcription ASR ou texte brut)

        Returns:
            Dict {concept_name: score_confiance} où score ∈ [0.0, 1.0]
            1.0 = match exact, 0.7 = match partiel.
            Ordre : mots entiers et multi-mots, puis homographes douteux gardés,
            puis partiels seuls ; dans chaque groupe, première apparition dans le
            texte (égalité : ordre de nlu_concepts.json).
        """
        return self.extraire(text).concepts

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
