"""Test-sentinelle #189 — stabilité du double-load ML parent → subprocess.

Contexte (issue #189) : au smoke Phase D, quand un test parent avait déjà
chargé SentenceTransformer/torch en mémoire, un subprocess qui rechargeait la
même pile (ex. `scripts/import_corpus_ivr.py`) crashait sous Windows avec
ACCESS_VIOLATION `0xC0000005` (`returncode=3221225477`) — double-load du
runtime Intel OpenMP (`libiomp5md.dll`), même famille que le `mkl_malloc`
d'ADR-0011. Le contournement : env durci `KMP_DUPLICATE_LIB_OK=TRUE` +
`OMP_NUM_THREADS=1` (`tests/integration/_helpers.ml_subprocess_env`).

Ce module VERROUILLE l'acquis. Le crash n'est plus reproductible sur la config
dev actuelle (torch 2.13 / ST 5.6) — ces tests le PROUVENT et servent de
sentinelle : si un futur upgrade de torch/MKL/OpenMP réintroduit le crash,
`test_ml_double_load_without_guard_does_not_crash` échouera (returncode non nul
= régression #189), signalant qu'il faut réévaluer le garde.

Prérequis : le modèle d'embedding doit être résoluble (cache HF ou
`modeles_manuels/`). Sinon le module entier est skip — on ne peut pas tester le
double-load sans charger réellement la pile ML.

Note sur le critère « n'importe quel ordre » de #189 : l'ordre des tests n'a
d'effet sur ce crash QUE via l'état ML partagé du process parent (un module qui
charge ST avant un module qui spawn un subprocess ML). Ce test encode
directement ce pire cas causal (parent charge ST → enfant recharge), donc il
couvre l'invariance d'ordre sans recourir à un méta-test `pytest`-dans-`pytest`
(lent : recharge les subprocess corpus ~5 min ; fragile : chemins/env) qui
n'ajouterait aucune garantie au-delà de ce mécanisme.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

from app.services.corpus_service import _MODEL_PATH
from tests.integration._helpers import ml_subprocess_env

# Identifiant HuggingFace du modèle d'embedding — même modèle que la prod
# (`scripts/import_corpus_ivr.py:_HF_MODEL_ID`, `corpus_service._MODEL_PATH`).
# Non importé de ces modules pour éviter leurs effets de bord (import_corpus_ivr
# manipule sys.path + importe app.* au chargement). Source de vérité prod :
# import_corpus_ivr._HF_MODEL_ID.
_HF_MODEL_ID = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Dimension de l'embedding produit par ce modèle (preuve que l'inférence a
# abouti dans le subprocess enfant).
_EMBEDDING_DIM = 384

# ACCESS_VIOLATION Windows : 0xC0000005. Python l'expose en unsigned
# (3221225477) ou signé (-1073741819) selon le chemin.
_ACCESS_VIOLATION_CODES = frozenset({3221225477, -1073741819})

# Variables du garde OpenMP/MKL (#189/ADR-0011) — à retirer pour reconstituer
# l'env « nu » du scénario historique (cf. _run_child(with_guard=False)).
_GUARD_VARS = ("KMP_DUPLICATE_LIB_OK", "OMP_NUM_THREADS")


def _model_available() -> bool:
    """Le modèle est-il chargeable (local ou cache HF) ?

    On tente un import léger : si SentenceTransformer n'est pas installé ou si
    le modèle n'est ni en `modeles_manuels/` ni en cache HF, on skip.
    """
    if _MODEL_PATH.exists():
        return True
    # Cache HF : on cherche le snapshot sans déclencher de download réseau.
    try:
        from huggingface_hub import try_to_load_from_cache

        cached = try_to_load_from_cache(_HF_MODEL_ID, "config.json")
        return isinstance(cached, str)
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _model_available(),
    reason=(
        "Modèle d'embedding paraphrase-multilingual-MiniLM-L12-v2 introuvable "
        "(ni modeles_manuels/ ni cache HF). Le test-sentinelle #189 exige de "
        "charger réellement la pile ML pour exercer le double-load."
    ),
)


# Script exécuté dans le subprocess : recharge torch + SentenceTransformer.
# Reproduit ce que faisait `import_corpus_ivr.py` — charger la pile ML alors
# que le parent l'a déjà en mémoire.
_CHILD_SCRIPT = textwrap.dedent(
    """
    import sys
    import numpy as np
    import torch  # noqa: F401  (charge le runtime OpenMP/MKL)
    from sentence_transformers import SentenceTransformer

    model_path, expected_dim = sys.argv[1], int(sys.argv[2])
    model = SentenceTransformer(model_path)
    vec = np.asarray(model.encode("malo sene wagati"))
    # shape[-1] = dimension d'embedding (robuste à un retour 1-D ou 2-D batch) ;
    # preuve que l'inference a abouti.
    assert vec.shape[-1] == expected_dim, f"dim inattendue: {vec.shape}"
    print("CHILD_OK")
    """
)


def _resolve_model_arg() -> str:
    """Argument modèle passé au subprocess : chemin local si présent, sinon
    l'ID HF (le subprocess résout via le cache, comme import_corpus_ivr.py)."""
    if _MODEL_PATH.exists():
        return str(_MODEL_PATH)
    return _HF_MODEL_ID


@pytest.fixture(scope="module")
def parent_st_loaded():
    """Charge le vrai SentenceTransformer dans le PROCESS PARENT.

    C'est la moitié « parent » du scénario #189 : sans ce chargement préalable,
    le subprocess ne provoque aucun double-load et le test ne prouverait rien.
    """
    import numpy as np
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(_resolve_model_arg())
    vec = np.asarray(model.encode("test parent"))
    assert vec.shape[-1] == _EMBEDDING_DIM
    return model


def _naked_env() -> dict:
    """Env « nu » du scénario historique #189 : copie de os.environ SANS le
    garde OpenMP/MKL.

    On retire explicitement `_GUARD_VARS` de l'env hérité : si le shell/CI
    exporte déjà `KMP_DUPLICATE_LIB_OK=TRUE` (fréquent, à cause de ce même bug),
    un simple `env=None` ferait tourner l'enfant AVEC le garde par héritage — le
    test « sans garde » deviendrait faux-vert et ne détecterait plus la
    régression #189. On garantit donc un env réellement nu, quel que soit l'hôte.
    """
    env = os.environ.copy()
    for var in _GUARD_VARS:
        env.pop(var, None)
    # UTF-8 forcé côté enfant : évite qu'un byte non-ASCII émis par torch/tqdm
    # (barres de progression, warnings localisés) fasse échouer le décodage
    # UTF-8 du parent (stdout enfant = cp1252 par défaut sur Windows).
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run_child(*, with_guard: bool) -> subprocess.CompletedProcess:
    """Spawn le subprocess enfant qui recharge la pile ML.

    with_guard=True → env durci `ml_subprocess_env` (garde #189/ADR-0011).
    with_guard=False → env nu explicite (`_naked_env`, sans garde hérité).
    """
    env = ml_subprocess_env(PYTHONIOENCODING="utf-8") if with_guard else _naked_env()
    return subprocess.run(
        [sys.executable, "-c", _CHILD_SCRIPT, _resolve_model_arg(), str(_EMBEDDING_DIM)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        env=env,
    )


def _assert_no_crash(result: subprocess.CompletedProcess, label: str) -> None:
    assert result.returncode not in _ACCESS_VIOLATION_CODES, (
        f"[{label}] ACCESS_VIOLATION 0xC0000005 (returncode={result.returncode}) "
        f"— régression #189 : le double-load OpenMP/MKL crashe à nouveau.\n"
        f"stderr:\n{result.stderr[-500:]}"
    )
    assert result.returncode == 0, (
        f"[{label}] subprocess ML échoué (returncode={result.returncode}).\n"
        f"stdout:\n{result.stdout[-500:]}\nstderr:\n{result.stderr[-500:]}"
    )
    assert "CHILD_OK" in result.stdout, (
        f"[{label}] l'enfant n'a pas confirmé son succès (CHILD_OK absent).\n"
        f"stdout:\n{result.stdout[-500:]}"
    )


class TestMLDoubleLoadStability:
    """Sentinelle #189 : le double-load parent→subprocess ne doit pas crasher."""

    def test_ml_double_load_with_guard_does_not_crash(self, parent_st_loaded):
        """Avec le garde `ml_subprocess_env` : aucun crash (contrat nominal)."""
        result = _run_child(with_guard=True)
        _assert_no_crash(result, "avec garde")

    def test_ml_double_load_without_guard_does_not_crash(self, parent_st_loaded):
        """Sans le garde : le scénario NU historique de #189.

        Sur la config dev actuelle (torch 2.13 / ST 5.6) il ne crashe plus. Si
        ce test se met à échouer avec un returncode ACCESS_VIOLATION, c'est que
        le heisenbug #189 est revenu (upgrade torch/MKL/OpenMP) → le garde
        redevient indispensable partout, pas seulement conservé par prudence.
        """
        result = _run_child(with_guard=False)
        _assert_no_crash(result, "sans garde")
