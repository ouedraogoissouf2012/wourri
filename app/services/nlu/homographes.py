"""
WOURI - NLU : homographes de culture (ADR-0041)

Un homographe est un mot-clé de culture qui est aussi un mot français courant :
« mais » (conjonction), « fini » (participe de « finir »), « beni » (« béni »),
« mil » (numéral, « mille » mal écrit), « caoutchouc » (la matière, le sachet).
Ils sont déclarés dans la section « homographes » de nlu_concepts.json, chacun
avec ses propres contextes sûrs.

Une occurrence d'homographe est SÛRE si elle est :
- écrite sous une de ses « formes_sures » (« maïs » avec tréma) ;
- juste avant un de ses « mots_apres_surs » (« mais et arachide ») ;
- juste après un de ses « mots_avant_surs » (« le maïs », « pour mais »), sauf
  si le mot suivant est un de ses « mots_apres_douteux » (« traite le mais pas
  en plein soleil »).
Les mots sont comparés tels qu'écrits, en minuscules (accents compris).
Hors de ces contextes, l'occurrence est DOUTEUSE ; ce que devient une culture
vue seulement par des occurrences douteuses est décidé par ConceptExtractor.

Ce module ne contient aucun mot : tout vient de la configuration.
"""
import unicodedata
from dataclasses import dataclass
from typing import Callable, Dict, FrozenSet, List, Mapping

# Champs reconnus d'une déclaration d'homographe. Un champ inconnu est refusé :
# une faute de frappe dans un nom de champ ne doit pas passer inaperçue.
_CHAMPS_LISTES = ("formes_sures", "mots_avant_surs", "mots_apres_douteux", "mots_apres_surs")
_CHAMPS_TEXTE = ("sens_courant", "note")
_CHAMPS_CONNUS = frozenset(("concept",) + _CHAMPS_LISTES + _CHAMPS_TEXTE)


class SectionHomographesInvalide(ValueError):
    """La section « homographes » de nlu_concepts.json est mal formée."""


def graphie(texte: str) -> str:
    """Minuscules en NFC, accents et tréma conservés (« maïs » ≠ « mais »)."""
    return unicodedata.normalize("NFC", texte.lower().strip())


@dataclass(frozen=True)
class RegleHomographe:
    """Contextes sûrs d'un homographe (mots en graphie, voir `graphie`)."""

    concept: str
    formes_sures: FrozenSet[str]
    mots_avant_surs: FrozenSet[str]
    mots_apres_douteux: FrozenSet[str]
    mots_apres_surs: FrozenSet[str]

    def occurrence_sure(self, forme: str, precedent: str, suivant: str) -> bool:
        """Vrai si l'occurrence est dans un contexte sûr.

        Args:
            forme: le mot tel qu'écrit
            precedent: mot qui le précède ; "" s'il n'y en a pas ou s'il ne peut
                pas compter (pronom accolé « arrose-le », fin d'un mot-clé
                multi-mots comme la salutation « i ni ce »)
            suivant: mot qui le suit ("" en fin de texte)
        """
        if forme in self.formes_sures or suivant in self.mots_apres_surs:
            return True
        return precedent in self.mots_avant_surs and suivant not in self.mots_apres_douteux


def _liste_de_mots(mot: str, champ: str, valeur) -> FrozenSet[str]:
    """Liste de mots d'un seul mot chacun : un mot avant ou après est comparé à
    un seul mot du texte, une entrée de deux mots ne correspondrait jamais."""
    if not isinstance(valeur, list) or not all(
        isinstance(v, str) and len(v.split()) == 1 for v in valeur
    ):
        raise SectionHomographesInvalide(
            f"« {mot} » : « {champ} » doit être une liste de mots d'un seul mot"
        )
    return frozenset(graphie(v) for v in valeur)


def charger_regles(
    section,
    mots_cles: Mapping[str, List[str]],
    partiels: Mapping[str, List[str]],
    normaliser: Callable[[str], str],
) -> Dict[str, RegleHomographe]:
    """Valide la section « homographes » et indexe ses règles par mot normalisé.

    Args:
        section: la section telle que lue dans nlu_concepts.json (absente : None)
        mots_cles: index des mots-clés d'un seul mot (mot normalisé → concepts)
        partiels: index des partiels (partiel normalisé → concepts)
        normaliser: normalisation des mots-clés (minuscules, tons retirés)

    Raises:
        SectionHomographesInvalide: section mal formée ; homographe qui n'est pas
            un mot-clé d'un seul mot d'une culture ; homographe qui contient un
            partiel de sa culture (l'étape des partiels le trouverait quand même) ;
            homographe déclaré deux fois sous la même forme normalisée (« mais »
            et « maïs ») ; champ inconnu ou de mauvais type.
    """
    if section is None:
        return {}
    if not isinstance(section, dict) or not isinstance(section.get("mots"), dict):
        raise SectionHomographesInvalide("la section doit contenir un objet « mots »")

    regles: Dict[str, RegleHomographe] = {}
    for mot, declaration in section["mots"].items():
        if not isinstance(declaration, dict):
            raise SectionHomographesInvalide(f"« {mot} » : la déclaration doit être un objet")
        inconnus = sorted(set(declaration) - _CHAMPS_CONNUS)
        if inconnus:
            raise SectionHomographesInvalide(f"« {mot} » : champ(s) inconnu(s) {inconnus}")
        mal_types = [champ for champ in _CHAMPS_TEXTE if not isinstance(declaration.get(champ, ""), str)]
        if mal_types:
            raise SectionHomographesInvalide(f"« {mot} » : {mal_types} doit être un texte")
        mot_norm = normaliser(mot)
        if mot_norm in regles:
            # Une seconde déclaration remplacerait la première sans le dire
            raise SectionHomographesInvalide(f"« {mot} » : déclaré deux fois (forme normalisée « {mot_norm} »)")
        concept = declaration.get("concept")
        if not (isinstance(concept, str) and concept.startswith("CULTURE_")
                and concept in mots_cles.get(mot_norm, [])):
            raise SectionHomographesInvalide(
                f"« {mot} » : pas un mot-clé (d'un seul mot) de la culture {concept!r}"
            )
        contournants = sorted(p for p, concepts in partiels.items() if concept in concepts and p in mot_norm)
        if contournants:
            raise SectionHomographesInvalide(
                f"« {mot} » : contient le partiel {contournants} de {concept}, qui le trouverait quand même"
            )
        listes = {champ: _liste_de_mots(mot, champ, declaration.get(champ, [])) for champ in _CHAMPS_LISTES}
        regles[mot_norm] = RegleHomographe(concept=concept, **listes)
    return regles
