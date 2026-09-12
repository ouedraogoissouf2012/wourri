"""Vote pondere multi-sources et decouverte du meilleur terme."""
import logging
import time
from collections import defaultdict

import _bv_http
import _bv_lookups

logger = logging.getLogger(__name__)

# Registre des sources. Ajouter une source = 1 entree ici, zero modification
# de `trouver_meilleur_terme` (OCP). Les fonctions sont referencees
# directement — plus d'indirection par nom au travers de `sys.modules`.
SOURCES_PRINCIPALES = [
    ("agri_dict",    _bv_lookups._agri_dict_lookup, 5),
    ("koumankan",    _bv_lookups._koumankan,        3),
    ("findora",      _bv_lookups._findora,          3),
    ("bayelemabaga", _bv_lookups._bayelemabaga,     2),
    ("bamadaba",     _bv_http._bamadaba,            2),
    ("voa_bambara",  _bv_http._voa_bambara,         1),
    ("bambara_org",  _bv_http._bambara_org,         1),
    ("bamanankan",   _bv_http._bamanankan_org,      1),
]

SOURCES_CONFIRMATION = [
    ("jeli_asr",   _bv_lookups._jeli_confirme, 1),
    ("ud_bambara", _bv_lookups._ud_confirme,   1),
]

# Score maximum possible (utilisé pour normaliser en 0.0–1.0)
SCORE_MAX = (
    sum(p for _, _, p in SOURCES_PRINCIPALES) +
    sum(p for _, _, p in SOURCES_CONFIRMATION)
)
# = 5 + 3 + 3 + 2 + 2 + 1 + 1 + 1 + 1 + 1 = 20


# ─────────────────────────────────────────────
# Fonction principale : DÉCOUVERTE du meilleur terme
# ─────────────────────────────────────────────

def trouver_meilleur_terme(concept_fr: str, verbose: bool = True) -> dict:
    """
    Pour un concept français, cherche dans toutes les sources et retourne
    le terme bambara le plus spécifique = le meilleur terme validé.

    Exemple :
        result = trouver_meilleur_terme("igname")
        result["meilleur_terme"]  # → "danburu"
        result["score"]           # → 0.7 (7/10 points)
        result["classement"]      # → top 5 termes avec scores
    """
    votes: dict = defaultdict(lambda: {"count": 0, "sources": []})

    if verbose:
        print(f"\n{'='*60}")
        print(f"  Recherche : '{concept_fr}'")
        print(f"{'='*60}")

    # ── Etape 1 : Collecter les termes depuis chaque source ──
    #
    # Issue #233 PR 4 : dispatcher 100% uniforme. Toutes les sources retournent
    # desormais Counter (TfidfSource depuis PR 1+2, HttpScraperSource depuis
    # PR 3, LookupSource depuis cette PR pour agri_dict). Plus de branche
    # `else` legacy, plus de `if isinstance(result, list)`. Pattern OCP 100%
    # atteint : ajouter une nouvelle source = creer 1 instance + 1 ligne dans
    # SOURCES_PRINCIPALES (zero modification de cette fonction).
    for nom, fn, poids in SOURCES_PRINCIPALES:
        try:
            compteur = fn(concept_fr)
            # top10 pour capturer les bases de composes (cas TF-IDF ou la
            # racine et un derive peuvent tous deux apparaitre dans le top).
            top10 = compteur.most_common(10)
            for terme, score in top10:
                votes[terme]["count"] += poids
                votes[terme]["sources"].append(f"{nom}(~{score})")
            if verbose:
                top_str = ", ".join([f"{t}(~{s})" for t, s in top10[:3]])
                print(f"  [{nom:15s}] -> {top_str if top10 else 'rien trouve'}")

            time.sleep(0.3)

        except Exception as e:
            logger.warning(f"[VAL] Erreur source {nom}: {e}")
            if verbose:
                print(f"  [{nom:15s}] -> ERREUR: {e}")

    # ── Étape 2 : Confirmation dans corpus locaux ──
    if verbose:
        print(f"\n  Confirmation corpus locaux (jeli-asr, UD)...")

    for terme in list(votes.keys()):
        for nom, fn, poids in SOURCES_CONFIRMATION:
            if fn(terme):
                votes[terme]["count"] += poids
                votes[terme]["sources"].append(f"✓{nom}")

    # ── Étape 3 : Classement final ──
    if not votes:
        return {
            "concept_fr":     concept_fr,
            "meilleur_terme": None,
            "score":          0.0,
            "classement":     [],
            "message":        "Aucun terme bambara trouvé dans les sources",
        }

    classement = sorted(
        votes.items(),
        key=lambda x: x[1]["count"],
        reverse=True,
    )

    meilleur_terme, meilleur_info = classement[0]
    score = round(meilleur_info["count"] / SCORE_MAX, 2)

    if verbose:
        print(f"\n  Classement final :")
        for i, (terme, info) in enumerate(classement[:5]):
            s = round(info["count"] / SCORE_MAX, 2)
            print(f"    {i+1}. '{terme}' — score={s} — {info['sources']}")
        print(f"\n  MEILLEUR TERME : '{meilleur_terme}' (score={score})")

    return {
        "concept_fr":     concept_fr,
        "meilleur_terme": meilleur_terme,
        "score":          score,
        "sources":        meilleur_info["sources"],
        "classement": [
            {
                "terme":   t,
                "score":   round(info["count"] / SCORE_MAX, 2),
                "sources": info["sources"],
            }
            for t, info in classement[:5]
        ],
    }


# ─────────────────────────────────────────────
# Validation d'un terme existant
# ─────────────────────────────────────────────

def valider_terme_existant(terme_bam: str, concept_fr: str, verbose: bool = True) -> dict:
    """
    Vérifie si un terme bambara existant est bien le meilleur pour un concept.
    Utile pour re-valider les entrées du corpus_ivr.json.

    Retourne :
        {
          "terme_teste":    str,
          "valide":         bool,
          "meilleur_terme": str,
          "score":          float,
          "action":         "garder" | "remplacer" | "verifier_manuellement"
        }
    """
    result = trouver_meilleur_terme(concept_fr, verbose=verbose)
    meilleur = result.get("meilleur_terme")

    if meilleur is None:
        action, valide = "verifier_manuellement", False
    elif meilleur == terme_bam.lower():
        action, valide = "garder", True
    elif result["score"] > 0.5:
        action, valide = "remplacer", False
    else:
        action, valide = "verifier_manuellement", False

    return {
        "terme_teste":    terme_bam,
        "valide":         valide,
        "meilleur_terme": meilleur,
        "score":          result["score"],
        "action":         action,
        "classement":     result.get("classement", []),
    }
