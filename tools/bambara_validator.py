"""
Pipeline DÉCOUVERTE bambara/dioula — Wourri (v3)
=================================================
Pour un concept français → chercher dans les sources →
collecter TOUS les termes bambara/dioula trouvés →
le terme qui revient le plus = le meilleur terme.

Sources actives (10) :
  Source 0 : agri_dict.json — dictionnaire agricole validé multi-sources (×5)
  Dioula CI: Koumankan4Dyula TF-IDF (×3), Findora TF-IDF (×3)
  Bambara  : Bayelemabaga TF-IDF (×2), jeli-asr (confirmation), UD Bambara (confirmation)
  En ligne : Bamadaba CNRS (×2), VOA Bambara, Bambara.org, Bamanankan.org

Sources écartées (raison) :
  An ka Taa   → app React/JS, lexicon.php statique utilisé pour alimenter agri_dict
  Lexilogos   → page de liens, pas un dictionnaire
  Live Lingua → téléchargement manuel requis

v3 changements (2026-04-17) :
  - Ajout Koumankan4Dyula (10 929 paires dioula CI, UVCI) poids ×3
  - Ajout Findora (20 513 paires dioula CI) poids ×3
  - Bayelemabaga réduit de ×3 à ×2 (bambara Mali, pas CI)
  - Score max = 5 + 3 + 3 + 2 + 2 + 1 + 1 + 1 + 1 + 1 = 20

Score max = 20
Seuil auto-validation = 8/20
Seuil décision manuelle = 5-7/20


Organisation du code
--------------------
Ce fichier est la **façade** : il expose l'API publique et ne contient aucune
logique. L'implémentation est répartie en six modules au graphe acyclique,
chacun sous la barre projet des 300 lignes :

    _bv_text      constantes lexicales et tokenizers          (aucune dépendance)
    _bv_sources   Source ABC, TfidfSource, HttpScraperSource, LookupSource
    _bv_registry  DATA_DIR, corpus chargés, fabriques de sources
    _bv_http      constructeurs d'URL et instances HTTP
    _bv_lookups   wrappers de lookup et de confirmation
    _bv_discover  registre pondéré, vote, découverte du meilleur terme

Chaque module dépend uniquement de ceux qui le précèdent. Aucune dépendance
remontante, aucune résolution par nom à l'exécution.

Substitution en test
--------------------
Les modules sont accessibles en attributs de cette façade
(`bambara_validator._bv_registry`, etc.). Un test qui doit substituer un état
patche **le module qui le possède**, pas la façade :

    monkeypatch.setattr(bambara_validator._bv_registry, "DATA_DIR", tmp_path)
    monkeypatch.setattr(bambara_validator._bv_discover, "SOURCES_PRINCIPALES", [...])
    monkeypatch.setattr(bambara_validator._bv_sources.requests, "get", fake_get)
"""
import sys
from pathlib import Path

# `tools/` n'est pas un package : on l'ajoute au chemin d'import pour que les
# modules `_bv_*` soient résolvables, que ce module soit importé normalement
# ou chargé par `importlib.util.spec_from_file_location` (cas des tests).
_TOOLS_DIR = str(Path(__file__).resolve().parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import _bv_discover  # noqa: E402
import _bv_http  # noqa: E402
import _bv_lookups  # noqa: E402
import _bv_registry  # noqa: E402
import _bv_sources  # noqa: E402
import _bv_text  # noqa: E402

# ── API publique ────────────────────────────────────────────────────────────
from _bv_discover import trouver_meilleur_terme, valider_terme_existant  # noqa: E402,F401

# ── Classes Source — réexportées pour les outils tiers et les tests ─────────
from _bv_sources import (  # noqa: E402,F401
    HttpScraperSource,
    LookupSource,
    Source,
    TfidfSource,
)

__all__ = [
    "trouver_meilleur_terme",
    "valider_terme_existant",
    "Source",
    "TfidfSource",
    "HttpScraperSource",
    "LookupSource",
]

# ── Compatibilité de signature ──────────────────────────────────────────────
# Ces trois helpers existaient ici avant la décomposition. Dans `_bv_text` ils
# prennent désormais le prédicat de langue en paramètre ; ce sont les formes
# *liées* du registre qui conservent la signature historique. Sans ces alias,
# la délégation ci-dessous résoudrait vers `_bv_text`, dont le 3ᵉ argument
# positionnel a changé de sens — un appel legacy passerait une fenêtre entière
# là où une fonction est attendue.
_extraire_fenetre = _bv_registry.extraire_fenetre    # (texte, concept, fenetre=250)
_tokeniser_bambara = _bv_registry.tokeniser_bambara  # (texte)
_est_bambara = _bv_registry.est_bambara              # (mot) -> bool
_tokeniser_simple = _bv_text._tokeniser_simple       # (texte) — inchangé

# Ordre de résolution des attributs délégués (voir `__getattr__`).
_MODULES_DELEGUES = (_bv_registry, _bv_discover, _bv_lookups, _bv_http, _bv_text)


def __getattr__(name):
    """Délègue les attributs restants au module qui les possède (PEP 562).

    Pourquoi une délégation plutôt que des réexports `from ... import` : un
    réexport copie la *liaison* au moment de l'import. Pour un état mutable
    — `DATA_DIR`, `_AGRI_DICT_SRC`, `_ud_mots`, les singletons `_*_SRC` — la
    copie diverge dès que le module propriétaire réassigne sa variable, et la
    façade servirait alors une valeur périmée sans le signaler.

    La délégation garantit que `bambara_validator.DATA_DIR` reflète toujours
    `_bv_registry.DATA_DIR`. Les classes et fonctions, elles, ne sont jamais
    réassignées : elles restent importées explicitement ci-dessus, ce qui les
    garde visibles à l'analyse statique.
    """
    for module in _MODULES_DELEGUES:
        try:
            return getattr(module, name)
        except AttributeError:
            continue
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    noms = set(globals())
    for module in _MODULES_DELEGUES:
        noms.update(n for n in dir(module) if not n.startswith("__"))
    return sorted(noms)
