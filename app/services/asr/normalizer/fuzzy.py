"""Étape 3 : fuzzy matching Levenshtein sur le vocabulaire NLU."""
import logging
from typing import Optional

from app.services.asr.normalizer.data import _NLU_VOCAB, _NLU_VOCAB_LIST, _REGLES
from app.services.asr.normalizer.ecart import ecart_admis, sans_tons

logger = logging.getLogger(__name__)

# Suffixes ignorés en comparant deux mots (asr_normalizer_regles.json) : pluriels, et
# « e » final du français sur un radical assez long.
_SUFFIXES_PLURIEL: tuple[str, ...] = tuple(_REGLES.get("suffixes_pluriel", []))
_E_FINAL_FRANCAIS: dict = _REGLES.get("e_final_francais", {})


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


def _phonological_variant_in_vocab(word_lower: str) -> Optional[str]:
    """Cherche une variante phonologique dioula↔bambara présente dans le vocab NLU.

    ADR-0020 : applique les 5 règles phonologiques déterministes (gw↔g, l↔d,
    l↔j, r↔l intervoc, nin↔len) et retourne la variante — autre que le mot
    lui-même — qui est un mot NLU connu. Aucune substitution lexicale n'est
    faite ici (celles-ci restent conditionnelles au sens, hors de ce module).

    Limite connue : cette étape n'est atteinte QUE pour un mot hors vocab (les
    mots déjà connus font early-return dans _fuzzy_correct_word). Deux mots NLU
    sont phonologiquement voisins (wolo=poulet ↔ woro=porc/cola) ; comme les deux
    sont dans le vocab, aucun n'est jamais réécrit vers l'autre par cette voie.
    Le risque résiduel (un mot ASR hors vocab dont une variante tombe sur l'un
    d'eux) est ≤ à celui du fuzzy Levenshtein existant, plus permissif.

    Retourne None si aucune variante n'est dans le vocabulaire, ou si plusieurs
    le sont : choisir entre elles demanderait le sens de la phrase (« laba » →
    « daba », ACTION_LABOURER, ou « jaba », CULTURE_OIGNON). Prendre la première
    variante du set renvoyé par `phonological_variants` rendait ce choix
    dépendant de PYTHONHASHSEED.
    """
    try:
        from app.services.language import phonological_variants
    except ImportError:
        return None
    connues = [
        variant for variant in phonological_variants(word_lower)
        if variant != word_lower and variant in _NLU_VOCAB
    ]
    return connues[0] if len(connues) == 1 else None


def _is_nasalization_only(word_lower: str, candidate: str) -> bool:
    """Vrai si `word_lower` et `candidate` ne diffèrent que par un 'n' final.

    Le 'n' final signale la nasalisation en bambara — sources : An Ka Taa,
    Vydrin 2020. Le fuzzy n'en admet que le retrait (transcription plus longue
    d'un 'n' : « banan » → « bana ») : voir _ecart_admis.
    """
    return (
        abs(len(word_lower) - len(candidate)) == 1
        and (word_lower.endswith("n") or candidate.endswith("n"))
        and (word_lower.rstrip("n") == candidate or candidate.rstrip("n") == word_lower
             or word_lower[:-1] == candidate or candidate[:-1] == word_lower)
    )


def _differe_par_un_suffixe(word_lower: str, candidate: str) -> bool:
    """Vrai si les deux mots, tons et accents retirés, ne diffèrent que par un
    suffixe qui ne change pas le concept NLU (asr_normalizer_regles.json) :
    - un suffixe de pluriel (`suffixes_pluriel`) : « insectes » / « insecte »,
      « kabaw » / « kaba », « récoltés » / « récolte » ;
    - le « e » final du français (`e_final_francais`) : « cacaoyère » /
      « cacaoyer », « plant » / « plante », si le radical a au moins
      `longueur_min_radical` lettres (« Mile », la ville de Milet, ne devient
      pas « mil »).
    """
    court, long_ = sorted((sans_tons(word_lower), sans_tons(candidate)), key=len)
    if any(long_ == court + suffixe for suffixe in _SUFFIXES_PLURIEL):
        return True
    return (
        bool(_E_FINAL_FRANCAIS)
        and len(court) >= _E_FINAL_FRANCAIS["longueur_min_radical"]
        and any(long_ == court + suffixe for suffixe in _E_FINAL_FRANCAIS["suffixes"])
    )


def _ecart_admis(word_lower: str, candidate: str) -> bool:
    """Vrai si `candidate` peut remplacer le mot transcrit `word_lower`.

    L'écart doit porter sur des confusions courantes (ecart_admis : mêmes
    consonnes, e/ɛ, o/ɔ, i → o, allongement final), sur un 'n' final de trop
    dans la transcription (nasalisation), ou sur un suffixe sans effet sur le
    concept (_differe_par_un_suffixe : pluriel, « e » final du français). Toute
    autre consonne ajoutée, retirée ou changée est refusée : « mugan » ne
    devient plus « mugu », ni « bolisi » « boli ». L'ajout d'un 'n' final non
    plus : « kɔlɔ » ne devient plus « kɔlɔn ». Les confusions réservées à
    l'étape 4 (o → u, a → ɔ, g ↔ r) ne sont pas admises ici : appliquées à tout
    le vocabulaire, elles réécrivaient des mots courants (« fagali » →
    « farali »). ADR-0042 (proposé).
    """
    if ecart_admis(word_lower, candidate):
        return True
    if len(word_lower) == len(candidate) + 1 and _is_nasalization_only(word_lower, candidate):
        return True
    return _differe_par_un_suffixe(word_lower, candidate)


def _best_fuzzy_match(word_lower: str, max_dist: int) -> tuple[Optional[str], int]:
    """Meilleur candidat du vocabulaire NLU à distance de Levenshtein <= max_dist.

    Seuls les candidats dont l'écart est admis (_ecart_admis) sont considérés ;
    à distance égale, le premier dans l'ordre de _NLU_VOCAB_LIST (trié, donc
    déterministe). Retourne (match|None, distance).
    """
    from rapidfuzz.distance import Levenshtein

    best_match: Optional[str] = None
    best_distance = max_dist + 1

    for candidate in _NLU_VOCAB_LIST:
        if abs(len(candidate) - len(word_lower)) > max_dist:
            continue

        dist = Levenshtein.distance(word_lower, candidate, score_cutoff=max_dist)
        if dist < best_distance and _ecart_admis(word_lower, candidate):
            best_distance = dist
            best_match = candidate

    return best_match, best_distance


def _fuzzy_correct_word(word: str) -> str:
    """Corrige un mot par fuzzy matching contre le vocabulaire NLU.

    Utilise rapidfuzz (C++ backend) pour des performances < 0.1ms.
    Seuls les candidats dont l'écart est admis sont retenus (_ecart_admis) :
    les confusions de voyelles courantes (e/ɛ, o/ɔ, i → o) sont listées dans
    asr_normalizer_regles.json (sources : Wikipedia Bambara phonology,
    Vydrin 2020, erreur de production « mali » → « malo »).
    """
    if not _NLU_VOCAB_LIST:
        return word

    max_dist = _max_distance_for_word(word)
    if max_dist == 0:
        return word

    word_lower = word.lower()
    if word_lower in _NLU_VOCAB:
        return word

    phon_match = _phonological_variant_in_vocab(word_lower)
    if phon_match:
        logger.info("[ASR-NORM] Variante phonologique: '%s' → '%s'", word, phon_match)
        return phon_match

    try:
        best_match, best_distance = _best_fuzzy_match(word_lower, max_dist)

        if best_match:
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
        clean = word.strip(".,!?;:\"'")
        suffix = word[len(clean):]
        corrected_word = _fuzzy_correct_word(clean)
        corrected.append(corrected_word + suffix)
    return " ".join(corrected)
