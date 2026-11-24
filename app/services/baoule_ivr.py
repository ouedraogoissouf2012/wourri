"""Réponses baoulé validées (ADR-0045) : le corpus question → réponse de la dictée.

Chaque entrée de `dictionnaires/corpus_ivr_bci.json` relie une question baoulé à sa
réponse baoulé, toutes deux écrites et lues par le locuteur natif, avec leur traduction
française, l'intention et les cultures (étiquetées depuis le français, sans table écrite
à la main). Rien n'est généré : on sert la réponse native la plus proche, ou rien.

Recherche : parmi les entrées de la culture comprise par le NLU baoulé, la question la
plus proche de ce que le paysan a dit, comparée par trigrammes de caractères (robuste
aux erreurs d'orthographe de l'ASR), avec un bonus si l'intention concorde. Sans
culture comprise, toute la base est comparée, avec un seuil plus exigeant.

Servi depuis PostgreSQL (ADR-0050 amendé, #623) : le fichier reste la source relue en PR,
la base en est la copie servie, que le moteur met à jour lui-même quand l'empreinte du
fichier change (`corpus_bci_base`). L'algorithme de recherche, lui, ne change pas.
"""
from __future__ import annotations

import json
import logging
import math
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple, Optional

from app.db import engine as db
from app.services import corpus_bci_base
from app.services.nlu.baoule_text import tokens_bci

logger = logging.getLogger(__name__)

CORPUS_PATH = Path(__file__).resolve().parents[2] / "dictionnaires" / "corpus_ivr_bci.json"

# Seuils de similarité (cosinus des trigrammes, 0 à 1). Avec une culture comprise,
# la question est déjà cadrée : un seuil bas suffit. Sans culture, il faut une
# ressemblance nette, sinon le repli honnête vaut mieux qu'une réponse à côté.
MIN_SIM_AVEC_CULTURE = 0.25
MIN_SIM_SANS_CULTURE = 0.45
BONUS_INTENTION = 0.15
# Écart minimal entre la meilleure question et la suivante : deux questions trop proches
# = réponse ambiguë, le repli honnête est préférable. Mesure du 2026-10-22 (questions de
# la dictée bruitées à 19 %, 3 tirages) : sans écart 84 % bonnes / 16 % mauvaises ; avec
# 0,03 → 77 % bonnes / 6 % mauvaises / 17 % replis.
MARGE_MIN = 0.03


class Trouvaille(NamedTuple):
    entry: dict
    similarite: float
    score: float


def _trigrammes(text: str) -> Counter:
    mots = tokens_bci(text)
    t = f" {' '.join(mots)} "
    return Counter(t[i:i + 3] for i in range(len(t) - 2))


def similarite(a: str, b: str) -> float:
    """Cosinus des trigrammes de caractères (0 à 1) entre deux textes baoulé."""
    ta, tb = _trigrammes(a), _trigrammes(b)
    if not ta or not tb:
        return 0.0
    dot = sum(ta[g] * tb[g] for g in ta.keys() & tb.keys())
    return dot / (math.sqrt(sum(v * v for v in ta.values())) * math.sqrt(sum(v * v for v in tb.values())))


class _Lot(NamedTuple):
    empreinte: str
    entrees: tuple


@lru_cache(maxsize=1)
def _lot_fichier(path: str) -> Optional[_Lot]:
    """Le fichier relu en PR, tel que déployé : il ne change pas pendant la vie du processus."""
    p = Path(path)
    if not p.is_file():
        logger.warning("[BCI-DB] Fichier source absent : %s — la base sert son dernier lot", p)
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    servies = tuple(e for e in data.get("entries", []) if e.get("question_bci") and e.get("reponse_bci"))
    return _Lot(corpus_bci_base.empreinte(data), servies)


# Lots dont ce processus a déjà vérifié qu'ils sont appliqués : une seule vérification par lot.
_synchronises: set[str] = set()


def _synchroniser_si_besoin(engine) -> None:
    """ADR-0050 amendé : le moteur applique lui-même le fichier relu quand son empreinte
    diffère du dernier lot en base — à la première requête, jamais au démarrage."""
    lot = _lot_fichier(str(CORPUS_PATH))
    if lot is None or lot.empreinte in _synchronises:
        return
    try:
        with engine.begin() as conn:
            bilan = corpus_bci_base.synchroniser(conn, lot.entrees, lot.empreinte,
                                                 auteur=f"moteur, lot {lot.empreinte[:12]}")
    except ValueError as exc:
        # Lot refusé (vide) : la base garde son dernier lot ET continue d'être servie. Refus
        # définitif pour ce fichier : ne pas le retenter à chaque requête. Une erreur de base,
        # elle, remonte (repli) et sera retentée.
        logger.error("[BCI-DB] Lot %s refusé (%s) — la base continue de servir son dernier lot",
                     lot.empreinte[:12], exc)
        _synchronises.add(lot.empreinte)
        return
    if bilan.applique:
        logger.info("[BCI-DB] Lot %s appliqué : %d ajoutée(s), %d modifiée(s), %d supprimée(s)",
                    lot.empreinte[:12], bilan.ajoutees, bilan.modifiees, bilan.supprimees)
    _synchronises.add(lot.empreinte)


def _base_tombee(exc: Exception) -> None:
    # D4 (#623) : le texte servi reste le repli habituel, mais le journal dit la vraie cause.
    logger.error("[BCI-DB] Corpus baoulé indisponible en base (%s) — repli servi : ce n'est pas "
                 "la question qui est en cause", db.message_sur(exc))


class _Cache(NamedTuple):
    empreinte: Optional[str]
    entrees: tuple


# Le corpus servi, gardé tant que le lot en base ne change pas (décision B, #623). Rempli
# depuis un fil : deux premières requêtes concurrentes peuvent le remplir deux fois — même
# contenu, une seule affectation gagne ; bénin, mesuré dans la PR, sans verrou.
_cache: Optional[_Cache] = None


def entrees() -> tuple:
    """Les entrées servies : la base, mise à jour d'abord depuis le fichier s'il a changé.

    L'empreinte du lot est relue à CHAQUE requête (une requête légère) : c'est elle, et non
    une durée, qui dit si la copie en mémoire est périmée — y compris quand un autre
    processus a synchronisé. Le corpus n'est relu que si elle a changé. L'empreinte est lue
    AVANT le corpus : une copie peut être plus récente que son étiquette (relue la fois
    suivante), jamais plus ancienne."""
    global _cache
    try:
        engine = db.get_engine()
        _synchroniser_si_besoin(engine)  # garde SA transaction : le verrou consultatif en dépend
        # Lecture seule en autocommit : pas de BEGIN/ROLLBACK autour de la vérification
        # d'empreinte (−0,7 ms mesuré). Jamais sur la synchronisation, dont le verrou
        # pg_advisory_xact_lock ne tient que le temps d'une transaction.
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            lot = corpus_bci_base.lot_courant(conn)
            cache = _cache
            if cache is None or cache.empreinte != lot:
                cache = _cache = _Cache(lot, corpus_bci_base.charger(conn))
            return cache.entrees
    except Exception as exc:  # base injoignable ou synchronisation refusée : repli, jamais une 500
        _base_tombee(exc)
        return ()


def filieres() -> list[str]:
    """Les filières du corpus servi : tout ce dont le repli a besoin."""
    try:
        with db.get_engine().connect() as conn:
            return corpus_bci_base.filieres(conn)
    except Exception as exc:
        _base_tombee(exc)
        return []


def chercher(text: str, intent: Optional[str], concepts, corpus=None) -> Optional[Trouvaille]:
    """La réponse native la plus proche de `text`, ou None si rien n'est assez proche."""
    corpus = entrees() if corpus is None else corpus
    if not text or not corpus:
        return None
    cultures = [c for c in (concepts or {}) if c.startswith("CULTURE_")]
    if cultures:
        candidats = [e for e in corpus if set(e.get("cultures") or []) & set(cultures)]
        seuil = MIN_SIM_AVEC_CULTURE
    else:
        candidats = list(corpus)
        seuil = MIN_SIM_SANS_CULTURE
    classees = sorted(
        (
            Trouvaille(e, sim, sim + (BONUS_INTENTION if intent and e.get("intent") == intent else 0.0))
            for e, sim in ((e, similarite(text, e["question_bci"])) for e in candidats)
        ),
        key=lambda t: t.score,
        reverse=True,
    )
    if not classees or classees[0].similarite < seuil:
        return None
    if len(classees) > 1 and classees[0].score - classees[1].score < MARGE_MIN:
        return None  # deux questions trop proches : ambigu
    return classees[0]
