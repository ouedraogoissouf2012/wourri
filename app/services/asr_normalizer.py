"""
WOURI — Normalizer post-ASR unifié pour le bambara/dioula.

Placé entre l'ASR et le reste du pipeline (NLU, traduction, TTS).
Tout le pipeline profite des corrections.

Architecture (validée par la littérature ASR error correction 2025-2026) :
    1. Corrections exactes multi-mots depuis JSON (fusions, fragmentations, particules)
    2. Corrections exactes mono-mot depuis le normalizer bambara existant (NeMo fusions)
    3. Fuzzy matching Levenshtein (distance adaptative) sur le vocabulaire NLU (645 mots)

Références :
    - Hybrid phonetic-neural model for ASR correction (arXiv:2102.06744)
    - Bambara phonology : 7 voyelles (a,e,ɛ,i,o,ɔ,u), paires proches e/ɛ o/ɔ
    - Nasalisation documentée (An Ka Taa, Vydrin 2020)
"""
import json
import logging
import unicodedata
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent  # wouri-api/
_CORRECTIONS_PATH = _PROJECT_ROOT / "dictionnaires" / "asr_corrections.json"
_NLU_CONCEPTS_PATH = _PROJECT_ROOT / "dictionnaires" / "nlu_concepts.json"


# ---------------------------------------------------------------------------
# Chargement des données (une seule fois au premier import)
# ---------------------------------------------------------------------------

def _load_exact_corrections() -> dict[str, str]:
    """Charge les corrections exactes depuis asr_corrections.json.

    Fusionne toutes les catégories en un dict plat {wrong: correct}.
    """
    corrections: dict[str, str] = {}
    try:
        with open(_CORRECTIONS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        for category, pairs in data.get("corrections", {}).items():
            if isinstance(pairs, dict):
                corrections.update(pairs)
        logger.info("[ASR-NORM] %d corrections exactes chargées depuis JSON", len(corrections))
    except FileNotFoundError:
        logger.warning("[ASR-NORM] Fichier %s non trouvé", _CORRECTIONS_PATH)
    except Exception as e:
        logger.error("[ASR-NORM] Erreur chargement corrections: %s", e)
    return corrections


def _load_nlu_vocabulary() -> set[str]:
    """Charge les mots-clés du NLU comme vocabulaire de référence pour le fuzzy matching."""
    vocab: set[str] = set()
    try:
        with open(_NLU_CONCEPTS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        concepts = data.get("concepts", {})
        for name, concept_data in concepts.items():
            if isinstance(concept_data, dict):
                for kw in concept_data.get("keywords", []):
                    vocab.add(kw.lower())
            elif isinstance(concept_data, list):
                for kw in concept_data:
                    vocab.add(kw.lower())
        logger.info("[ASR-NORM] %d mots-clés NLU chargés pour fuzzy matching", len(vocab))
    except Exception as e:
        logger.error("[ASR-NORM] Erreur chargement vocabulaire NLU: %s", e)
    return vocab


# Chargement au premier import
_EXACT_CORRECTIONS = _load_exact_corrections()
_NLU_VOCAB = _load_nlu_vocabulary()
_NLU_VOCAB_LIST = sorted(_NLU_VOCAB)  # Liste triée pour rapidfuzz


# ---------------------------------------------------------------------------
# Étape 1 : Corrections exactes multi-mots
# ---------------------------------------------------------------------------

def _apply_exact_corrections(text: str) -> str:
    """Applique les corrections exactes (JSON + normalizer bambara fusions).

    Les corrections multi-mots (espaces, particules) sont appliquées
    par remplacement de sous-chaîne, ordonnées par longueur décroissante
    pour éviter les conflits (ex: "ani sɔgɔma" avant "ani").
    """
    result = f" {text} "  # Pad pour matcher les frontières de mot
    for wrong in sorted(_EXACT_CORRECTIONS, key=len, reverse=True):
        if wrong in result:
            result = result.replace(wrong, _EXACT_CORRECTIONS[wrong])
    return result.strip()


# ---------------------------------------------------------------------------
# Étape 2 : Corrections fusions NeMo (normalizer bambara existant)
# ---------------------------------------------------------------------------

def _apply_nemo_fusions(text: str) -> str:
    """Applique les corrections de fusions syllabiques NeMo.

    Délègue au normalizer bambara existant (FUSIONS + PHRASE_SUBS).
    """
    from app.services.asr_bambara_normalizer import normalize_bambara_asr
    return normalize_bambara_asr(text) or text


# ---------------------------------------------------------------------------
# Étape 3 : Fuzzy matching Levenshtein sur vocabulaire NLU
# ---------------------------------------------------------------------------

def _max_distance_for_word(word: str) -> int:
    """Distance max adaptative selon la longueur du mot.

    - Mots ≤ 3 chars : pas de fuzzy (trop de faux positifs)
    - Mots 4 chars : distance ≤ 1
    - Mots ≥ 5 chars : distance ≤ 2

    Justification : les mots courts bambara (ku, ji, ba) ont trop de
    voisins à distance 1. Les mots longs (sɛnɛ, wagati) tolèrent
    plus de variation sans ambiguïté.
    """
    n = len(word)
    if n <= 3:
        return 0
    if n == 4:
        return 1
    return 2


def _consonant_changes(word_a: str, word_b: str) -> int:
    """Compte le nombre de consonnes différentes entre deux mots de même longueur.

    Sert à départager les candidats fuzzy : on préfère les corrections
    qui ne changent que les voyelles (confusions e/ɛ, o/ɔ, i/o documentées
    en bambara) plutôt que les consonnes.
    """
    _VOWELS = set("aeɛiouɔàáâèéêìíòóôùú")
    changes = 0
    for a, b in zip(word_a.lower(), word_b.lower()):
        if a != b and (a not in _VOWELS or b not in _VOWELS):
            changes += 1
    return changes


def _phonological_variant_in_vocab(word_lower: str) -> Optional[str]:
    """Cherche une variante phonologique dioula↔bambara présente dans le vocab NLU.

    ADR-0020 : applique les 5 règles phonologiques déterministes (gw↔g, l↔d,
    l↔j, r↔l intervoc, nin↔len) et retourne la première variante — autre que le
    mot lui-même — qui est un mot NLU connu. Aucune substitution lexicale n'est
    faite ici (celles-ci restent conditionnelles au sens, hors de ce module).

    Limite connue : cette étape n'est atteinte QUE pour un mot hors vocab (les
    mots déjà connus font early-return dans _fuzzy_correct_word). Deux mots NLU
    sont phonologiquement voisins (wolo=poulet ↔ woro=porc/cola) ; comme les deux
    sont dans le vocab, aucun n'est jamais réécrit vers l'autre par cette voie.
    Le risque résiduel (un mot ASR hors vocab dont une variante tombe sur l'un
    d'eux) est ≤ à celui du fuzzy Levenshtein existant, plus permissif.

    Retourne None si aucune variante n'est dans le vocabulaire.
    """
    try:
        from app.services.language import phonological_variants
    except ImportError:
        return None
    for variant in phonological_variants(word_lower):
        if variant != word_lower and variant in _NLU_VOCAB:
            return variant
    return None


def _fuzzy_correct_word(word: str) -> str:
    """Corrige un mot par fuzzy matching contre le vocabulaire NLU.

    Utilise rapidfuzz (C++ backend) pour des performances < 0.1ms.
    Départage : à distance égale, préfère le candidat avec moins de
    changements de consonnes (les confusions voyelles sont plus probables
    en bambara : e/ɛ, o/ɔ, i/o — sources : Wikipedia Bambara phonology, Vydrin 2020).
    """
    if not _NLU_VOCAB_LIST:
        return word

    max_dist = _max_distance_for_word(word)
    if max_dist == 0:
        return word

    word_lower = word.lower()
    if word_lower in _NLU_VOCAB:
        return word

    # ADR-0020 : avant le fuzzy approximatif, tenter les variantes phonologiques
    # dioula↔bambara (déterministes). Si UNE variante est exactement dans le
    # vocabulaire NLU, c'est un match sûr (le modèle ASR a produit la forme
    # malienne d'un mot dioula, ou l'inverse) — préférable au fuzzy.
    phon_match = _phonological_variant_in_vocab(word_lower)
    if phon_match:
        logger.info("[ASR-NORM] Variante phonologique: '%s' → '%s'", word, phon_match)
        return phon_match

    try:
        from rapidfuzz.distance import Levenshtein

        best_match: Optional[str] = None
        best_distance = max_dist + 1
        best_consonant_changes = 999

        for candidate in _NLU_VOCAB_LIST:
            if abs(len(candidate) - len(word_lower)) > max_dist:
                continue

            dist = Levenshtein.distance(word_lower, candidate, score_cutoff=max_dist)
            if dist <= max_dist:
                cons = _consonant_changes(word_lower, candidate)
                # Préférer : distance plus petite, puis moins de consonnes changées
                if (dist < best_distance) or (dist == best_distance and cons < best_consonant_changes):
                    best_distance = dist
                    best_consonant_changes = cons
                    best_match = candidate

        if best_match:
            # Sécurité : rejeter si des consonnes ont changé (risque de faux positif)
            # SAUF : ajout/suppression de 'n' final = nasalisation bambara (documenté)
            # Source : An Ka Taa, Vydrin 2020 — le 'n' final signale la nasalisation
            is_nasal_only = (
                abs(len(word_lower) - len(best_match)) == 1
                and (word_lower.endswith("n") or best_match.endswith("n"))
                and (word_lower.rstrip("n") == best_match or best_match.rstrip("n") == word_lower
                     or word_lower[:-1] == best_match or best_match[:-1] == word_lower)
            )

            if best_consonant_changes > 0 and not is_nasal_only:
                logger.debug(
                    "[ASR-NORM] Fuzzy rejeté: '%s' → '%s' (consonnes changées=%d)",
                    word, best_match, best_consonant_changes,
                )
                return word

            logger.info(
                "[ASR-NORM] Fuzzy: '%s' → '%s' (distance=%d)",
                word, best_match, best_distance,
            )
            return best_match

    except ImportError:
        logger.warning("[ASR-NORM] rapidfuzz non installé — fuzzy matching désactivé")
    except Exception as e:
        logger.error("[ASR-NORM] Erreur fuzzy: %s", e)

    return word


def _apply_fuzzy_matching(text: str) -> str:
    """Applique le fuzzy matching mot par mot sur le texte."""
    words = text.split()
    corrected = []
    for word in words:
        # Séparer la ponctuation
        clean = word.strip(".,!?;:\"'")
        suffix = word[len(clean):]
        corrected_word = _fuzzy_correct_word(clean)
        corrected.append(corrected_word + suffix)
    return " ".join(corrected)


# ---------------------------------------------------------------------------
# Étape 4 : Détection contextuelle de cultures par fusion de fragments
# ---------------------------------------------------------------------------

# Verbes agricoles qui signalent qu'un nom de culture est attendu
_AGRI_VERBS: frozenset[str] = frozenset({
    "sɛnɛ", "sene", "tigɛ", "tige", "bɔ", "bo",
    "fere", "feere", "dumu", "mara", "filɛ", "file",
})

# Mots grammaticaux à ignorer (ne font pas partie du nom de culture)
_GRAMMAR_WORDS: frozenset[str] = frozenset({
    "n", "ne", "i", "a", "an", "aw", "u", "o",
    "bɛ", "be", "tɛ", "te", "ye", "ma", "bɛna", "tɛna",
    "fɛ", "fe", "ka", "la", "na", "ni", "wa",
    "se", "kɛ", "ke", "don", "min",
})

# Mots qui ne doivent JAMAIS participer à une fusion culture
# (trop fréquents en bambara, produisent des faux positifs)
# Cas réel : an+ni → anni → matche fini (fonio) = faux positif
_NEVER_FUSE: frozenset[str] = frozenset({
    "n", "ne", "i", "a", "an", "ni", "u", "o", "aw",
    "bɛ", "be", "tɛ", "te", "fɛ", "fe", "ye", "ma",
    "bɛna", "tɛna", "se", "kɛ", "ke", "don", "min",
    "wa", "la", "na",
})

# Vocabulaire cultures — construit une fois depuis nlu_concepts.json
_CULTURE_VOCAB: dict[str, str] = {}  # {forme_normalisée: forme_correcte}


def _load_culture_vocab() -> dict[str, str]:
    """Charge les noms de cultures depuis nlu_concepts.json.

    Ne garde que les mots dioula/bambara (pas les mots français/anglais).
    """
    vocab: dict[str, str] = {}
    try:
        with open(_NLU_CONCEPTS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        # Mots français/anglais à exclure
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
                # Enlever les tons pour normaliser
                kw_norm = unicodedata.normalize('NFD', kw_clean)
                kw_norm = ''.join(c for c in kw_norm if unicodedata.category(c) != 'Mn')
                vocab[kw_norm] = kw_clean
        logger.info("[ASR-NORM] %d mots-clés cultures chargés pour reconstruction", len(vocab))
    except Exception as e:
        logger.error("[ASR-NORM] Erreur chargement vocab cultures: %s", e)
    return vocab


def _strip_tones_simple(text: str) -> str:
    """Retire les diacritiques de ton."""
    nfd = unicodedata.normalize('NFD', text)
    return ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')


def _normalize_ny(text: str) -> str:
    """Normalise ɲ → ny pour la comparaison (même phonème, deux écritures)."""
    return text.replace('ɲ', 'ny')


def _has_culture_word(text: str) -> bool:
    """Vérifie si le texte contient déjà un mot-clé de culture connu."""
    text_norm = _normalize_ny(_strip_tones_simple(text.lower()))
    words = set(text_norm.replace("'", " ").replace("-", " ").split())
    for culture_norm in _CULTURE_VOCAB:
        culture_check = _normalize_ny(culture_norm)
        # Match exact par mot (pas substring) pour éviter faux positifs
        if culture_check in words:
            return True
        # Match multi-mots
        if ' ' in culture_check and culture_check in text_norm:
            return True
    return False


def _try_culture_reconstruction(text: str) -> str:
    """Étape 4 : détection contextuelle de cultures par fusion de fragments.

    NeMo Soloni fragmente les mots qu'il ne connaît pas en petits mots
    bambara valides. Exemples réels :
        kakawo → ka ka aw / ka ka o / ka o / ka aw
        kafe   → ka fɛ / ka fe
        mangoro → mangogo

    Cette étape :
    1. Vérifie qu'un verbe agricole est présent (sɛnɛ, tigɛ, etc.)
    2. Vérifie qu'aucune culture n'est déjà reconnue
    3. Fusionne des fenêtres de 1, 2, 3 mots adjacents
    4. Compare chaque fusion aux noms de cultures par Levenshtein
    5. Remplace si match trouvé (tolérance : distance ≤ min(3, len//2))
    """
    if not _CULTURE_VOCAB:
        return text

    words = text.lower().split()

    # Condition 1 : verbe agricole présent ?
    has_agri_verb = any(w in _AGRI_VERBS for w in words)
    if not has_agri_verb:
        return text

    # Condition 2 : culture déjà reconnue ?
    if _has_culture_word(text):
        return text

    try:
        from rapidfuzz.distance import Levenshtein
    except ImportError:
        return text

    best_match: Optional[str] = None
    best_distance = 999
    best_start = -1
    best_end = -1

    # Fenêtre glissante : 1, 2, 3 mots adjacents
    for window_size in (1, 2, 3):
        for i in range(len(words) - window_size + 1):
            fragment_words = words[i:i + window_size]

            # Ne pas fusionner si ça inclut un verbe agricole
            if any(w in _AGRI_VERBS for w in fragment_words):
                continue

            # Ne pas fusionner si un des mots est dans _NEVER_FUSE
            # (bɛ, fɛ, te, ye, ma — trop fréquents, produisent des faux positifs)
            if any(w in _NEVER_FUSE for w in fragment_words):
                continue

            # Fusionner les mots
            fused = ''.join(fragment_words)
            fused_norm = _strip_tones_simple(fused)

            # Trop court → trop de faux positifs
            if len(fused_norm) < 4:
                continue

            max_dist = min(3, len(fused_norm) // 2)

            for culture_norm, culture_correct in _CULTURE_VOCAB.items():
                # Pré-filtre rapide : différence de longueur
                if abs(len(fused_norm) - len(culture_norm)) > max_dist:
                    continue

                dist = Levenshtein.distance(fused_norm, culture_norm, score_cutoff=max_dist)
                if dist <= max_dist and dist < best_distance:
                    best_distance = dist
                    best_match = culture_correct
                    best_start = i
                    best_end = i + window_size

    if best_match and best_start >= 0:
        # Reconstruire la phrase avec le mot de culture correct
        original_words = text.split()
        new_words = original_words[:best_start] + [best_match] + original_words[best_end:]
        result = ' '.join(new_words)
        logger.info(
            "[ASR-NORM] Culture reconstruite: '%s' → '%s' (culture=%s, distance=%d)",
            text, result, best_match, best_distance,
        )
        return result

    return text


# Charger le vocabulaire cultures au premier import
_CULTURE_VOCAB.update(_load_culture_vocab())


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def normalize_asr_output(text: str) -> str:
    """Pipeline complet de normalisation post-ASR.

    Ordre :
    1. Corrections exactes multi-mots (JSON) — salutations, particules
    2. Corrections fusions NeMo — fusions syllabiques
    3. Fuzzy matching Levenshtein — mots isolés vs vocabulaire NLU
    4. Reconstruction contextuelle de cultures — fusion de fragments

    Args:
        text: transcription brute de l'ASR.

    Returns:
        texte corrigé, prêt pour le NLU et la traduction.
    """
    if not text:
        return text

    original = text

    # Étape 1 : corrections exactes multi-mots
    text = _apply_exact_corrections(text)

    # Étape 2 : fusions NeMo
    text = _apply_nemo_fusions(text)

    # Étape 3 : fuzzy matching mot par mot
    text = _apply_fuzzy_matching(text)

    # Étape 4 : reconstruction contextuelle de cultures
    text = _try_culture_reconstruction(text)

    if text != original:
        logger.info("[ASR-NORM] '%s' → '%s'", original, text)

    return text
