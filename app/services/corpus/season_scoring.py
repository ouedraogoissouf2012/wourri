"""Saison agricole CI + scoring métier des candidats IVR (logique partagée).

Ce module centralise deux règles métier qui étaient auparavant DUPLIQUÉES
verbatim entre le backend Chroma (`vdb_service._best_result`) et pgvector
(`corpus_service._best_result_pg`) :

  1. `get_current_season()` — saison agricole selon le mois (calendrier CI) ;
  2. `score_entry()` — score métier d'un candidat (base + bonus/pénalité saison
     + bonus par condition explicite matchée).

Les backends restent responsables de la seule PERSISTANCE : ils désérialisent
leurs conditions (Chroma en CSV, pgvector en array) puis délèguent le calcul
ici. Aucun accès store dans ce module (fonctions pures, testables isolément).

Les valeurs (mois de pluie, poids) sont les valeurs HISTORIQUES exactes des deux
backends : ce module ne change aucun comportement, il supprime la duplication.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

# --- Calendrier agricole CI ------------------------------------------------
# Grande saison des pluies (mars-juin) + petite saison des pluies (sep-oct).
# Le reste (nov-fév, jul-août) = saison sèche. Valeurs identiques à l'origine
# (vdb_service.py / corpus_service.py, fonctions `_get_current_season`).
RAINY_MONTHS: frozenset[int] = frozenset({3, 4, 5, 6, 9, 10})
SEASON_RAINY = "saison_pluie"
SEASON_DRY = "saison_seche"

# Ensemble des étiquettes de saison reconnues (pour distinguer une condition
# saisonnière d'une condition « métier » quelconque).
_SEASON_LABELS: frozenset[str] = frozenset({SEASON_RAINY, SEASON_DRY})

# --- Poids du scoring (valeurs historiques figées) -------------------------
SEASON_MATCH_BONUS = 0.15       # saison courante présente dans les conditions
SEASON_MISMATCH_PENALTY = 0.05  # l'entrée a une saison, mais ce n'est pas la bonne
EXPLICIT_CONDITION_BONUS = 0.05  # par condition explicite de la requête matchée
DEFAULT_VALIDATION_SCORE = 0.5   # score de base par défaut si absent en base


def get_current_season(now: Optional[datetime] = None) -> str:
    """Retourne la saison agricole CI pour la date donnée (défaut : maintenant).

    Args:
        now: date/heure de référence. Injectable pour la testabilité ; par
            défaut `datetime.now()`.

    Returns:
        `SEASON_RAINY` (mars-juin, sep-oct) ou `SEASON_DRY` (sinon).
    """
    month = (now or datetime.now()).month
    return SEASON_RAINY if month in RAINY_MONTHS else SEASON_DRY


def score_entry(
    base_score: float,
    entry_conditions: Iterable[str],
    query_conditions: Iterable[str],
    season: str,
) -> float:
    """Calcule le score métier d'un candidat IVR (logique historique exacte).

    Règles (identiques aux deux backends d'origine) :
      - départ = `base_score` (le `score_validation` de l'entrée) ;
      - si `season` figure dans `entry_conditions` → +`SEASON_MATCH_BONUS` ;
      - sinon, si l'entrée ne porte AUCUNE étiquette de saison → neutre (+0) ;
      - sinon (l'entrée a une saison, mais pas la bonne) → −`SEASON_MISMATCH_PENALTY` ;
      - +`EXPLICIT_CONDITION_BONUS` pour chaque condition non vide de la requête
        présente dans `entry_conditions`.

    Les chaînes vides sont ignorées (le backend Chroma produit `[""]` pour une
    entrée sans condition ; ça ne doit jamais déclencher la pénalité ni un bonus).

    Args:
        base_score: score de validation de base de l'entrée.
        entry_conditions: conditions de l'entrée (déjà désérialisées par le backend).
        query_conditions: conditions issues de la requête (contexte utilisateur).
        season: saison courante (cf. `get_current_season`).

    Returns:
        Le score ajusté (non borné, non arrondi — cohérent avec l'origine).
    """
    entry_conditions = list(entry_conditions)
    score = base_score

    if season in entry_conditions:
        score += SEASON_MATCH_BONUS
    elif not any(c in _SEASON_LABELS for c in entry_conditions if c):
        # Aucune contrainte saisonnière sur l'entrée → neutre.
        pass
    else:
        # L'entrée impose une saison, mais ce n'est pas la saison courante.
        score -= SEASON_MISMATCH_PENALTY

    for cond in query_conditions:
        if cond and cond in entry_conditions:
            score += EXPLICIT_CONDITION_BONUS

    return score
