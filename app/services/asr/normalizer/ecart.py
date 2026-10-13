"""Comparaison de deux graphies selon les confusions documentées (étapes 3 et 4).

Une transcription n'est rapprochée d'un mot du vocabulaire que si l'écart porte
sur des confusions documentées : autant de consonnes, dans le même ordre, égales
ou confondues selon une paire admise ; entre deux consonnes, des voyelles égales
ou confondues selon une paire admise. Le dernier groupe de voyelles peut aussi
être allongé (« sanjiii » / « sanji », « sɔ̀mɔɔ » / « sɔ̀mɔ ») ; une voyelle longue
à l'intérieur du mot (« feere », « dɔɔni ») n'est jamais raccourcie. Les tons
sont ignorés.

Deux jeux de confusions, lus dans dictionnaires/asr_normalizer_regles.json :
- `confusions_courantes` (e/ɛ, o/ɔ, i → o), admises aux étapes 3 et 4 ;
- `confusions_reconstruction` (o → u, a → ɔ, a → o, g ↔ r), admises en plus
  par l'étape 4 seulement, là où le risque est faible.
ADR-0042 (proposé).
"""
import re
import unicodedata
from collections.abc import Iterable

from app.services.asr.normalizer.data import _REGLES

_VOYELLES: frozenset[str] = frozenset(_REGLES.get("voyelles", ""))
_ALLONGEMENT = re.compile(r"(.)\1+")


def paires_de_lettres(paires: Iterable) -> frozenset[tuple[str, ...]]:
    """Paires [lettre de la transcription, lettre du vocabulaire] lues dans le JSON."""
    return frozenset(tuple(paire) for paire in paires)


CONFUSIONS_COURANTES: frozenset[tuple[str, ...]] = paires_de_lettres(
    _REGLES.get("confusions_courantes", [])
)
CONFUSIONS_RECONSTRUCTION: frozenset[tuple[str, ...]] = CONFUSIONS_COURANTES | paires_de_lettres(
    _REGLES.get("confusions_reconstruction", [])
)


def est_voyelle(lettre: str) -> bool:
    """Vrai si la lettre (sans ton) fait partie des `voyelles` du JSON."""
    return lettre in _VOYELLES


def sans_tons(mot: str) -> str:
    """Retire les diacritiques de ton et les accents (marques combinantes)."""
    nfd = unicodedata.normalize("NFD", mot)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def _decouper(mot: str) -> tuple[list[str], list[str]]:
    """Sépare un mot en consonnes et en groupes de voyelles : V0 C1 V1 … Cn Vn.

    Toute lettre absente de `voyelles` compte comme une consonne (espace et
    apostrophe compris) : un mot seul n'est jamais rapproché d'une expression.
    """
    consonnes: list[str] = []
    groupes: list[str] = []
    courant = ""
    for lettre in mot:
        if lettre in _VOYELLES:
            courant += lettre
        else:
            groupes.append(courant)
            consonnes.append(lettre)
            courant = ""
    groupes.append(courant)
    return consonnes, groupes


def _lettres_compatibles(lue: str, attendue: str, confusions: frozenset) -> bool:
    """Même lettre, ou confusion admise (lettre lue → lettre du vocabulaire)."""
    return lue == attendue or (lue, attendue) in confusions


def _voyelles_compatibles(lu: str, attendu: str, confusions: frozenset, final: bool) -> bool:
    """Deux groupes de voyelles de même longueur, lettre à lettre compatibles.

    Seul le groupe final peut être allongé : « iii » y vaut « i ».
    """
    if final:
        lu = _ALLONGEMENT.sub(r"\1", lu)
        attendu = _ALLONGEMENT.sub(r"\1", attendu)
    return len(lu) == len(attendu) and all(
        _lettres_compatibles(a, b, confusions) for a, b in zip(lu, attendu)
    )


def ecart_admis(lu: str, attendu: str, confusions: frozenset = CONFUSIONS_COURANTES) -> bool:
    """Vrai si la graphie `lu` (transcription) ne diffère de `attendu` (mot du
    vocabulaire) que par des confusions de `confusions`.

    Autant de consonnes, dans le même ordre, égales ou confondues ; voyelles
    égales ou confondues, le groupe final pouvant être allongé. Une consonne
    ajoutée ou retirée n'est jamais admise. Les tons sont ignorés.
    """
    consonnes_lues, groupes_lus = _decouper(sans_tons(lu.lower()))
    consonnes_attendues, groupes_attendus = _decouper(sans_tons(attendu.lower()))
    if len(consonnes_lues) != len(consonnes_attendues):
        return False
    if not all(
        _lettres_compatibles(a, b, confusions)
        for a, b in zip(consonnes_lues, consonnes_attendues)
    ):
        return False
    dernier = len(groupes_lus) - 1
    return all(
        _voyelles_compatibles(a, b, confusions, final=(rang == dernier))
        for rang, (a, b) in enumerate(zip(groupes_lus, groupes_attendus))
    )
