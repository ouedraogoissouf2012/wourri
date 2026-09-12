"""Etat des corpus et fabriques de sources du validateur bambara.

Ce module concentre tout ce qui touche au disque : le repertoire de donnees,
les corpus charges en memoire (jeli-asr, UD) et les instances de `Source`.

Il existe pour casser le cycle qui apparaissait sinon : les wrappers de lookup
ont besoin des instances de source, et les instances de source ont besoin du
lexique de reference. En isolant l'etat ici, le graphe de dependances reste
acyclique :

    _bv_text  ->  _bv_sources  ->  _bv_registry  ->  _bv_http  ->  _bv_lookups
                                                                        |
                                                                  _bv_discover

Les globals de ce module sont le point de substitution des tests : ils sont
lus a chaque appel (jamais capturés dans une closure ou importés par valeur),
de sorte qu'un `monkeypatch.setattr(_bv_registry, "DATA_DIR", tmp_path)` soit
effectivement pris en compte.
"""
import logging
from pathlib import Path

import _bv_text
from _bv_sources import LookupSource, TfidfSource

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "validation_sources"


# ─────────────────────────────────────────────
# État interne — chargé une seule fois
# ─────────────────────────────────────────────
#
# Note: les globals `_agri_dict`, `_agri_loaded` ont ete remplaces par
# l'attribut d'instance de `LookupSource` (cf. `_AGRI_DICT_SRC` plus bas,
# issue #233 PR 4). Les globals `_baye_*`, `_kouman_*` et `_findora_*` ont
# ete remplaces par `TfidfSource` (PR 1 et PR 2).

_jeli_phrases: list = []
_jeli_loaded = False

_ud_mots: set = set()
_ud_loaded = False


def _charger_jeli():
    global _jeli_phrases, _jeli_loaded
    if _jeli_loaded:
        return
    f = DATA_DIR / "jeli_asr_bam.txt"
    if f.exists():
        with open(f, encoding="utf-8") as fp:
            _jeli_phrases = [l.strip().lower() for l in fp if l.strip()]
    _jeli_loaded = True
    logger.info(f"[VAL] jeli-asr: {len(_jeli_phrases)} phrases")


def _charger_ud():
    global _ud_mots, _ud_loaded
    if _ud_loaded:
        return
    f = DATA_DIR / "ud_bambara_words.txt"
    if f.exists():
        with open(f, encoding="utf-8") as fp:
            _ud_mots = {l.strip().lower() for l in fp if l.strip()}
    _ud_loaded = True


# ─────────────────────────────────────────────
# Lexique de reference — predicat et extraction
# ─────────────────────────────────────────────


def est_bambara(mot: str) -> bool:
    """Un mot est bambara s'il porte un caractere specifique, ou s'il est au lexique UD.

    Lit `_ud_mots` comme global du module (et non via une copie capturee) pour
    rester substituable en test.
    """
    if any(c in _bv_text.BAMBARA_CHARS for c in mot):
        return True
    return mot in _ud_mots


def extraire_fenetre(texte: str, concept: str, fenetre: int = 250) -> list:
    """Extraction de termes autour d'un concept, lexique UD garanti charge.

    C'est la forme liee de `_bv_text._extraire_fenetre` : elle fournit le
    predicat de langue et assure le chargement du corpus UD au prealable —
    comportement de l'implementation d'origine, preserve tel quel.
    """
    _charger_ud()
    return _bv_text._extraire_fenetre(texte, concept, est_bambara, fenetre=fenetre)


def tokeniser_bambara(texte: str) -> list:
    """Forme liee de `_bv_text._tokeniser_bambara` : predicat de langue fourni."""
    _charger_ud()
    return _bv_text._tokeniser_bambara(texte, est_bambara)


# ─────────────────────────────────────────────
# Fabriques de sources — instanciation paresseuse
# ─────────────────────────────────────────────
#
# Volontairement initialisees a None et instanciees lazy pour conserver le
# comportement "charge a la 1ere utilisation" du module (DATA_DIR resolu une
# seule fois mais fichiers lus sur demande).

_BAYELEMABAGA_SRC: "TfidfSource | None" = None
_KOUMAN_SRC: "TfidfSource | None" = None
_FINDORA_SRC: "TfidfSource | None" = None


def _bayelemabaga_src() -> TfidfSource:
    global _BAYELEMABAGA_SRC
    if _BAYELEMABAGA_SRC is None:
        for split in ("train", "test", "valid"):
            # Bayelemabaga est splitte en 3 dossiers. On garde la 1ere paire
            # existante comme initialisation primaire ; les autres splits sont
            # concatenes ci-dessous pour reproduire le comportement legacy.
            base = DATA_DIR / "bayelemabaga" / split
            if (base / f"{split}.fr").exists():
                _BAYELEMABAGA_SRC = TfidfSource(
                    name="bayelemabaga",
                    fr_path=base / f"{split}.fr",
                    dyu_path=base / f"{split}.bam",
                    weight=2,
                    min_global=3,
                    min_match_lignes=3,
                )
                break
        if _BAYELEMABAGA_SRC is None:
            # Aucun split present : TfidfSource avec paths vides → load() sera
            # un no-op, find() renverra Counter() vide. Comportement equivalent
            # a l'ancien code (qui ne chargait rien si fichiers absents).
            _BAYELEMABAGA_SRC = TfidfSource(
                name="bayelemabaga",
                fr_path=DATA_DIR / "bayelemabaga" / "train" / "train.fr",
                dyu_path=DATA_DIR / "bayelemabaga" / "train" / "train.bam",
                weight=2,
                min_global=3,
                min_match_lignes=3,
            )
    return _BAYELEMABAGA_SRC


def _bayelemabaga_load_all_splits() -> None:
    """Concatene les 3 splits (train/test/valid) de Bayelemabaga dans la source.

    Comportement legacy : le module original chargeait les 3 splits en boucle
    avant l'introduction de l'abstraction `TfidfSource`. On preserve ce
    comportement en chargeant les splits additionnels apres `load()`.

    Idempotent (fix review #233 PR 1 MAJOR-1) : le flag `_all_splits_loaded`
    sur l'instance empeche une 2e concatenation qui doublerait le corpus.
    Utilise `append_split()` (fix MAJOR-2) plutot qu'un acces direct aux
    attributs prives pour preserver l'encapsulation.
    """
    src = _bayelemabaga_src()
    if src._all_splits_loaded:
        return
    src.load()
    if src._loaded and len(src._fr) > 0:
        # 1er split deja charge par load(). Concatener les autres si dispo.
        deja_charge = src.fr_path.parent.name  # ex: "train"
        for split in ("train", "test", "valid"):
            if split == deja_charge:
                continue
            fr_f = DATA_DIR / "bayelemabaga" / split / f"{split}.fr"
            bam_f = DATA_DIR / "bayelemabaga" / split / f"{split}.bam"
            src.append_split(fr_f, bam_f)
    src._all_splits_loaded = True


def _kouman_src() -> TfidfSource:
    global _KOUMAN_SRC
    if _KOUMAN_SRC is None:
        _KOUMAN_SRC = TfidfSource(
            name="koumankan",
            fr_path=DATA_DIR / "koumankan" / "koumankan.fr",
            dyu_path=DATA_DIR / "koumankan" / "koumankan.dyu",
            weight=3,
            min_global=2,
            min_match_lignes=2,
        )
    return _KOUMAN_SRC


def _findora_src() -> TfidfSource:
    global _FINDORA_SRC
    if _FINDORA_SRC is None:
        _FINDORA_SRC = TfidfSource(
            name="findora",
            fr_path=DATA_DIR / "findora" / "findora.fr",
            dyu_path=DATA_DIR / "findora" / "findora.dyu",
            weight=3,
            min_global=2,
            min_match_lignes=2,
        )
    return _FINDORA_SRC


# Instance LookupSource pour agri_dict (issue #233 PR 4 — finalise OCP).
_AGRI_DICT_SRC = LookupSource(
    name="agri_dict",
    json_path=DATA_DIR / "agri_dict.json",
    weight=5,                # poids maximum (dico valide multi-sources)
    entries_root="cultures",
    key_field="bambara",
    variante_field="variante",
)


# ─────────────────────────────────────────────
# Wrappers de chargement (compatibilite)
# ─────────────────────────────────────────────


def _charger_bayelemabaga():
    """Wrapper de compatibilite (issue #233 PR 1) : delegue a `TfidfSource`.

    L'ancien code chargeait les 3 splits (train/test/valid) en boucle. On
    reproduit ce comportement via `_bayelemabaga_load_all_splits()` qui
    concatene les splits dans l'instance.
    """
    _bayelemabaga_load_all_splits()


def _charger_koumankan():
    """Wrapper de compatibilite (issue #233 PR 2) : delegue a TfidfSource."""
    _kouman_src().load()


def _charger_findora():
    """Wrapper de compatibilite (issue #233 PR 2) : delegue a TfidfSource."""
    _findora_src().load()


def _charger_agri_dict():
    """Wrapper de compatibilite (issue #233 PR 4) : delegue a LookupSource."""
    _AGRI_DICT_SRC.load()
