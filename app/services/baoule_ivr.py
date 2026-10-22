"""Réponses baoulé validées (ADR-0045) : le corpus question → réponse de la dictée.

Chaque entrée de `dictionnaires/corpus_ivr_bci.json` relie une question baoulé à sa
réponse baoulé, toutes deux écrites et lues par le locuteur natif, avec leur traduction
française, l'intention et les cultures (étiquetées depuis le français, sans table écrite
à la main). Rien n'est généré : on sert la réponse native la plus proche, ou rien.

Recherche : parmi les entrées de la culture comprise par le NLU baoulé, la question la
plus proche de ce que le paysan a dit, comparée par trigrammes de caractères (robuste
aux erreurs d'orthographe de l'ASR), avec un bonus si l'intention concorde. Sans
culture comprise, toute la base est comparée, avec un seuil plus exigeant.
"""
from __future__ import annotations

import json
import logging
import math
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple, Optional

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


@lru_cache(maxsize=1)
def _charger(path: str) -> tuple:
    p = Path(path)
    if not p.is_file():
        logger.warning("[BCI-IVR] Corpus absent: %s — réponses baoulé désactivées", p)
        return ()
    data = json.loads(p.read_text(encoding="utf-8"))
    return tuple(e for e in data.get("entries", []) if e.get("question_bci") and e.get("reponse_bci"))


def entrees(path: Optional[Path] = None) -> tuple:
    return _charger(str(path or CORPUS_PATH))


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
