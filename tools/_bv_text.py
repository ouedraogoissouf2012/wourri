"""Constantes lexicales et tokenizers du validateur bambara.

Socle de la decomposition : ce module ne depend d'aucun autre. Les fonctions
qui ont besoin de savoir si un mot est du bambara recoivent le predicat en
parametre (`est_bambara`) plutot que d'aller le chercher dans un module
appelant — la dependance remonte vers l'appelant, jamais l'inverse.
"""
import re

# Caractères phonétiques spécifiques au bambara (absents de l'anglais et du HTML)
BAMBARA_CHARS = frozenset("ɛɔɲŋɓɗɪʊ")

# Mots bambara courts connus (≤ 2 chars) — exceptions au filtre longueur
# Ex: ku=igname, ɲɔ=mil — confirmés par An ka Taa, mandenkan, coastsystems
SHORT_AGRI_TERMS = {"ku", "ɲɔ"}

# Mots grammaticaux bambara à ignorer
STOPWORDS_BAM = {
    "ye", "bɛ", "be", "ka", "ko", "la", "ni", "o", "a", "i", "n", "u",
    "an", "aw", "le", "de", "nan", "ma", "do", "kɔ", "fɔ", "fo", "si",
    "so", "da", "wo", "wa", "di", "ke", "se", "to", "bi", "na", "ta",
    "min", "don", "jan", "bɔ", "bo", "in", "tun", "nɔ", "no", "sun",
    "san", "kan", "den", "ten", "kelen", "fila", "saba",
}

_MOT_RE = re.compile(r"[a-zA-Zɛɔɲŋɪʊɓɗ'-]+")


def _retenu(mot: str) -> bool:
    """Filtre commun aux deux tokenizers : ni stopword, ni trop court."""
    return mot not in STOPWORDS_BAM and (len(mot) > 2 or mot in SHORT_AGRI_TERMS)


def _tokeniser_simple(texte: str) -> list:
    """
    Tokenizer léger — pour les lignes BAM du corpus Bayelemabaga.
    On SAIT que ces lignes sont en bambara : pas besoin de filtre de langue.
    Rejette les stopwords et les mots trop courts (sauf SHORT_AGRI_TERMS).
    """
    return [m for m in _MOT_RE.findall(texte.lower()) if _retenu(m)]


def _tokeniser_bambara(texte: str, est_bambara) -> list:
    """Tokenizer strict : ajoute le filtre de langue au filtre de `_tokeniser_simple`.

    `est_bambara` est un predicat `(mot) -> bool` fourni par l'appelant, qui
    seul connait le lexique de reference (cf. `_bv_registry.est_bambara`).
    """
    return [
        m for m in _MOT_RE.findall(texte.lower())
        if _retenu(m) and est_bambara(m)
    ]


def _extraire_fenetre(texte: str, concept: str, est_bambara, fenetre: int = 250) -> list:
    """Collecte les termes bambara dans une fenetre autour de chaque occurrence.

    Le chargement du lexique de reference releve de l'appelant : ce module ne
    connait pas les corpus. Cf. `_bv_registry.extraire_fenetre`, qui garantit
    que le lexique est charge avant d'appeler ici.
    """
    texte_lower = texte.lower()
    concept_lower = concept.lower()
    termes = []
    pos = 0
    while True:
        idx = texte_lower.find(concept_lower, pos)
        if idx == -1:
            break
        debut = max(0, idx - fenetre)
        fin = min(len(texte), idx + len(concept) + fenetre)
        termes.extend(_tokeniser_bambara(texte[debut:fin], est_bambara))
        pos = idx + 1
    return termes
