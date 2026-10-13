"""Étape 4 : reconstruction contextuelle de cultures par fusion de fragments."""
import json
import logging
import unicodedata
from typing import Optional

from app.services.asr.normalizer.data import _NLU_CONCEPTS_PATH, _NLU_VOCAB, _REGLES
from app.services.asr.normalizer.ecart import (
    CONFUSIONS_RECONSTRUCTION,
    ecart_admis,
    est_voyelle,
    paires_de_lettres,
)

logger = logging.getLogger(__name__)

_AGRI_VERBS: frozenset[str] = frozenset({
    "sɛnɛ", "sene", "tigɛ", "tige", "bɔ", "bo",
    "fere", "feere", "dumu", "mara", "filɛ", "file",
})

_GRAMMAR_WORDS: frozenset[str] = frozenset({
    "n", "ne", "i", "a", "an", "aw", "u", "o",
    "bɛ", "be", "tɛ", "te", "ye", "ma", "bɛna", "tɛna",
    "fɛ", "fe", "ka", "la", "na", "ni", "wa",
    "se", "kɛ", "ke", "don", "min",
})

_NEVER_FUSE: frozenset[str] = frozenset({
    "n", "ne", "i", "a", "an", "ni", "u", "o", "aw",
    "bɛ", "be", "tɛ", "te", "fɛ", "fe", "ye", "ma",
    "bɛna", "tɛna", "se", "kɛ", "ke", "don", "min",
    "wa", "la", "na",
})

# Paramètres de l'étape, lus dans asr_normalizer_regles.json (constraints.md §1.2).
# Sans ce fichier, aucune valeur de repli n'est codée en dur : l'étape ne fait rien.
_REGLES_ETAPE: dict = _REGLES.get("reconstruction_cultures", {})
_MOT_SEUL: dict = _REGLES_ETAPE.get("mot_seul", {})
_GROUPE_DE_CONSONNES: dict = _REGLES_ETAPE.get("groupe_de_consonnes", {})
_MOT_COURT: dict = _REGLES_ETAPE.get("mot_court_du_vocabulaire", {})
_MOT_OUTIL_FINAL: dict = _REGLES_ETAPE.get("mot_outil_final", {})
_DETECTION: dict = _REGLES_ETAPE.get("detection", {})
# « Exactement un nom de culture » s'entend à la graphie près (e/ɛ, o/ɔ).
_CONFUSIONS_GRAPHIE: frozenset[tuple[str, ...]] = paires_de_lettres(
    _REGLES_ETAPE.get("confusions_graphie", [])
)

_CULTURE_VOCAB: dict[str, str] = {}
_CULTURE_DETECTION: set[str] = set()


def _load_culture_vocab() -> dict[str, str]:
    """Charge les noms de cultures depuis nlu_concepts.json.

    Ne garde que les mots dioula/bambara (pas les mots français/anglais).
    """
    vocab: dict[str, str] = {}
    try:
        with open(_NLU_CONCEPTS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        exclude = {
            "riz", "riziere", "rizière", "rice", "maïs", "mais", "corn", "maize",
            "mil", "sorgho", "millet", "fonio", "arachide", "cacahuete", "cacahuète",
            "groundnut", "peanut", "yam", "igname", "ignames", "cassava", "manioc",
            "gari", "haricot", "haricots", "cowpea", "niebe", "niébé", "coton",
            "cotton", "fibre", "sesame", "sésame", "banane", "bananes", "plantain",
            "banana", "tomate", "tomates", "tomato", "oignon", "oignons", "patate",
            "gombo", "okra", "cacao", "cacaoyer", "chocolat", "café", "cafe",
            "caféier", "ananas", "pineapple", "mangue", "mango", "citron", "lime",
            "agrume", "agrumes", "néré", "parkia", "sweet potato",
            "cacaoforo", "kafeforo", "gros mil", "petit mil", "patate douce",
        }
        for concept_name, concept_data in data.get("concepts", {}).items():
            if not concept_name.startswith("CULTURE_"):
                continue
            if not isinstance(concept_data, dict):
                continue
            for kw in concept_data.get("keywords", []):
                kw_clean = kw.lower().strip()
                if kw_clean in exclude or len(kw_clean) <= 2:
                    continue
                kw_norm = unicodedata.normalize('NFD', kw_clean)
                kw_norm = ''.join(c for c in kw_norm if unicodedata.category(c) != 'Mn')
                vocab[kw_norm] = kw_clean
        logger.info("[ASR-NORM] %d mots-clés cultures chargés pour reconstruction", len(vocab))
    except Exception as e:
        logger.error("[ASR-NORM] Erreur chargement vocab cultures: %s", e)
    return vocab


def _load_culture_detection() -> set[str]:
    """Charge les mots-clés CULTURE_* de nlu_concepts.json qui montrent qu'une
    culture est déjà nommée, noms français compris (« ananas », « banane »).

    Sont écartés, selon `detection` (asr_normalizer_regles.json), les mots-clés
    de moins de `longueur_min` lettres (« ku », « ɲɔ » : trop courts pour prouver
    qu'une culture est nommée, « ba nan ku » doit pouvoir redevenir « bananku »)
    et ceux de `mots_ignores`, homographes d'un mot courant (« mais », la
    conjonction française). Formes sans tons et ɲ → ny, comme dans
    _has_culture_word.
    """
    longueur_min = _DETECTION.get("longueur_min", 0)
    ignores = {
        _normalize_ny(_strip_tones_simple(mot.lower().strip()))
        for mot in _DETECTION.get("mots_ignores", [])
    }
    detection: set[str] = set()
    try:
        with open(_NLU_CONCEPTS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        for concept_name, concept_data in data.get("concepts", {}).items():
            if concept_name.startswith("CULTURE_") and isinstance(concept_data, dict):
                for kw in concept_data.get("keywords", []):
                    forme = _normalize_ny(_strip_tones_simple(kw.lower().strip()))
                    if len(forme) >= longueur_min and forme not in ignores:
                        detection.add(forme)
    except Exception as e:
        logger.error("[ASR-NORM] Erreur chargement détection cultures: %s", e)
    return detection


def _strip_tones_simple(text: str) -> str:
    """Retire les diacritiques de ton."""
    nfd = unicodedata.normalize('NFD', text)
    return ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')


def _normalize_ny(text: str) -> str:
    """Normalise ɲ → ny pour la comparaison (même phonème, deux écritures)."""
    return text.replace('ɲ', 'ny')


def _has_culture_word(text: str) -> bool:
    """Vérifie si le texte nomme déjà une culture (voir _load_culture_detection)."""
    text_norm = _normalize_ny(_strip_tones_simple(text.lower()))
    words = set(text_norm.replace("'", " ").replace("-", " ").split())
    for culture_check in _CULTURE_DETECTION:
        if culture_check in words:
            return True
        if ' ' in culture_check and culture_check in text_norm:
            return True
    return False


def _sans_consonne_parasite(mot: str) -> set[str]:
    """Lectures d'un mot où deux consonnes se suivent sans nasale en tête.

    Une consonne parasite peut s'insérer dans un nom de culture (« tigka » pour
    « tiga », asr_corrections.json). Renvoie le mot privé tour à tour de chacune
    des deux consonnes (« tika », « tiga »). Un groupe qui commence par une
    nasale (`groupe_de_consonnes.nasales` : « ntomati », « sanji ») n'est jamais
    lu ainsi. Une lecture ne sert que si elle donne exactement un nom de
    culture : un digramme (« gb », « sh ») ne crée donc pas de nom à lui seul.
    Vide si `groupe_de_consonnes` n'est pas configuré.
    """
    nasales = _GROUPE_DE_CONSONNES.get("nasales")
    if not nasales:
        return set()
    lectures: set[str] = set()
    for k in range(len(mot) - 1):
        premiere, seconde = mot[k], mot[k + 1]
        if (premiere.isalpha() and seconde.isalpha() and premiere not in nasales
                and not est_voyelle(premiere) and not est_voyelle(seconde)):
            lectures.add(mot[:k] + mot[k + 1:])
            lectures.add(mot[:k + 1] + mot[k + 2:])
    return lectures


def _lectures_fenetre(
    fragment_words: list[str], fused_norm: str, suivant: str, avec_verbe_agricole: bool = True
) -> list[tuple[str, frozenset, int]]:
    """Lectures d'une fenêtre à comparer aux noms de cultures : (graphie,
    confusions admises, longueur minimale du nom de culture). Liste vide si la
    fenêtre est exclue.

    - Une fenêtre qui contient un verbe agricole est exclue.
    - Mot seul (`mot_seul`), hors vocabulaire NLU : nom de culture d'au moins
      `longueur_min_culture` lettres, par une confusion documentée
      (« mangogo » → « mangoro ») ; ou, si deux consonnes s'y suivent, lecture
      sans la consonne parasite, qui doit donner exactement un nom de culture
      (`groupe_de_consonnes` : « tigka » → « tiga »).
    - Sans verbe agricole dans la phrase (`mot_seul.sans_verbe_agricole`), seule
      la première lecture du mot seul reste : la consonne parasite et les
      fusions de plusieurs mots exigent le verbe agricole.
    - Un mot-outil (_NEVER_FUSE) ne peut que finir la fenêtre, juste avant un
      verbe agricole, et la fusion doit donner exactement un nom de culture
      d'au moins `mot_outil_final.longueur_min_culture` lettres
      (« kɔrɔ ni sɛnɛ » → « kɔrɔni sɛnɛ »).
    - Un mot du vocabulaire NLU n'est jamais fondu, sauf un mot court (au plus
      `mot_court_du_vocabulaire.longueur_max` lettres : « sɔ », « ku ») quand la
      fusion donne exactement un nom de culture (« sɔ mɔ » → « sɔmɔ »).
    - Sinon, plusieurs mots fusionnés : confusions documentées
      (CONFUSIONS_RECONSTRUCTION : « man go ra » → « mangoro »).
    « Exactement » s'entend à la graphie près (`confusions_graphie` : e/ɛ, o/ɔ).
    """
    if any(w in _AGRI_VERBS for w in fragment_words):
        return []
    outils = [w for w in fragment_words if w in _NEVER_FUSE]
    connus = [w for w in fragment_words if w in _NLU_VOCAB]

    if len(fragment_words) == 1:
        if outils or connus or not _MOT_SEUL:
            return []
        lectures = [(fused_norm, CONFUSIONS_RECONSTRUCTION, _MOT_SEUL["longueur_min_culture"])]
        if _GROUPE_DE_CONSONNES and avec_verbe_agricole:
            lectures += [
                (lecture, _CONFUSIONS_GRAPHIE, _GROUPE_DE_CONSONNES["longueur_min_culture"])
                for lecture in sorted(_sans_consonne_parasite(fused_norm))
            ]
        return lectures

    if not avec_verbe_agricole:
        return []

    if outils:
        dernier_seul = outils == [fragment_words[-1]] and not connus
        if not _MOT_OUTIL_FINAL or not dernier_seul or suivant not in _AGRI_VERBS:
            return []
        return [(fused_norm, _CONFUSIONS_GRAPHIE, _MOT_OUTIL_FINAL["longueur_min_culture"])]

    if connus:
        longueur_max = _MOT_COURT.get("longueur_max")
        if longueur_max is None or any(len(_strip_tones_simple(w)) > longueur_max for w in connus):
            return []
        return [(fused_norm, _CONFUSIONS_GRAPHIE, 0)]

    return [(fused_norm, CONFUSIONS_RECONSTRUCTION, 0)]


def _find_best_culture_fragment(
    words: list[str], avec_verbe_agricole: bool = True
) -> tuple[Optional[str], int, int, int]:
    """Cherche la meilleure fusion de mots adjacents qui donne un nom de culture.

    Fenêtres de `taille_fenetre_min` à `taille_fenetre_max` mots, précédées du
    mot seul si `mot_seul` est configuré (asr_normalizer_regles.json). Sans verbe
    agricole, le mot seul est la seule fenêtre. Chaque
    fenêtre est lue selon _lectures_fenetre ; les fusions < 4 caractères sont
    ignorées. Une lecture rejoint un nom de culture si l'écart est admis
    (ecart_admis) et si la distance de Levenshtein de la fenêtre au nom reste
    ≤ min(3, len//2), et ≤ `mot_seul.distance_max` pour un mot seul. À
    distance égale, la première trouvée l'emporte. Retourne
    (culture|None, start, end, distance), ou (None, -1, -1, 999) si rapidfuzz
    est indisponible ou si les fenêtres ne sont pas configurées.
    """
    try:
        from rapidfuzz.distance import Levenshtein
    except ImportError:
        return None, -1, -1, 999

    taille_min = _REGLES_ETAPE.get("taille_fenetre_min")
    taille_max = _REGLES_ETAPE.get("taille_fenetre_max")
    if not taille_min or not taille_max:
        return None, -1, -1, 999

    best_match: Optional[str] = None
    best_distance = 999
    best_start = -1
    best_end = -1

    tailles = ([1] if _MOT_SEUL and taille_min > 1 else [])
    if avec_verbe_agricole:
        tailles += list(range(taille_min, taille_max + 1))
    for window_size in tailles:
        for i in range(len(words) - window_size + 1):
            fragment_words = words[i:i + window_size]
            fused_norm = _strip_tones_simple(''.join(fragment_words))
            if len(fused_norm) < 4:
                continue

            suivant = words[i + window_size] if i + window_size < len(words) else ""
            lectures = _lectures_fenetre(fragment_words, fused_norm, suivant, avec_verbe_agricole)
            if not lectures:
                continue

            max_dist = min(3, len(fused_norm) // 2)
            if window_size == 1:
                max_dist = min(max_dist, _MOT_SEUL["distance_max"])

            for culture_norm, culture_correct in _CULTURE_VOCAB.items():
                if abs(len(fused_norm) - len(culture_norm)) > max_dist:
                    continue

                dist = Levenshtein.distance(fused_norm, culture_norm, score_cutoff=max_dist)
                if dist > max_dist or dist >= best_distance:
                    continue
                if any(
                    len(culture_norm) >= longueur_min and ecart_admis(lecture, culture_norm, confusions)
                    for lecture, confusions, longueur_min in lectures
                ):
                    best_distance = dist
                    best_match = culture_correct
                    best_start = i
                    best_end = i + window_size

    return best_match, best_start, best_end, best_distance


def _try_culture_reconstruction(text: str) -> str:
    """Étape 4 : détection contextuelle de cultures par fusion de fragments.

    NeMo Soloni (retiré de la chaîne, ADR-0027) fragmentait les mots qu'il ne
    connaissait pas en petits mots bambara valides. Exemples réels, couverts par
    asr_corrections.json :
        kakawo → ka ka aw / ka ka o / ka o / ka aw
        kafe   → ka fɛ / ka fe
        mangoro → mangogo

    Cette étape :
    1. Vérifie qu'un verbe agricole est présent (sɛnɛ, tigɛ, etc.) ; sans lui,
       seul le mot seul est lu, si `mot_seul.sans_verbe_agricole` est vrai
    2. Vérifie qu'aucune culture n'est déjà nommée (noms français compris)
    3. Lit le mot seul et les fenêtres de mots adjacents (_lectures_fenetre)
    4. Compare chaque lecture aux noms de cultures, à confusions documentées près
    5. Remplace si match trouvé (tolérance : distance ≤ min(3, len//2))

    Un mot courant n'est plus réécrit en nom de culture : « foro », « bana » ou
    « sɔrɔ » ne deviennent plus « ɲɔforo », « kaba » ou « sɔsɔ ». ADR-0042
    (proposé).
    """
    if not _CULTURE_VOCAB:
        return text

    words = text.lower().split()

    has_agri_verb = any(w in _AGRI_VERBS for w in words)
    if not has_agri_verb and not _MOT_SEUL.get("sans_verbe_agricole"):
        return text

    if _has_culture_word(text):
        return text

    best_match, best_start, best_end, best_distance = _find_best_culture_fragment(words, has_agri_verb)

    if best_match and best_start >= 0:
        original_words = text.split()
        new_words = original_words[:best_start] + [best_match] + original_words[best_end:]
        result = ' '.join(new_words)
        logger.info(
            "[ASR-NORM] Culture reconstruite: '%s' → '%s' (culture=%s, distance=%d)",
            text, result, best_match, best_distance,
        )
        return result

    return text


_CULTURE_VOCAB.update(_load_culture_vocab())
_CULTURE_DETECTION.update(_load_culture_detection())
