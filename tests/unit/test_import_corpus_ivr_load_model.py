"""
Tests pour `scripts/import_corpus_ivr.py::_load_model` (issue #223).

Couvre :
    - Branche local : si `_MODEL_PATH` existe → `SentenceTransformer(str(_MODEL_PATH))`
    - Branche HF fallback : si absent → `SentenceTransformer(_HF_MODEL_ID)`

On mock `SentenceTransformer` pour ne PAS télécharger le modèle réel
(le but du test est de vérifier QUEL argument est passé, pas de tester
la lib upstream).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Charger le script en tant que module (pas un package "scripts")
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "import_corpus_ivr.py"


@pytest.fixture
def import_module():
    """Charge le module sans déclencher l'exécution de `main()`."""
    spec = importlib.util.spec_from_file_location("import_corpus_ivr", _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_load_model_branche_locale_si_chemin_existe(import_module, tmp_path):
    """Si _MODEL_PATH existe (cas dev historique), charge depuis le chemin local.

    On mock _MODEL_PATH vers un tmp_path qui existe, et on mock
    SentenceTransformer pour capturer l'argument.
    """
    fake_model_dir = tmp_path / "paraphrase-multilingual-MiniLM-L12-v2"
    fake_model_dir.mkdir()  # le path EXISTE

    with patch.object(import_module, "_MODEL_PATH", fake_model_dir):
        mock_st_class = MagicMock(return_value=MagicMock(name="loaded_model"))
        # Patch le module sentence_transformers AVANT l'import dans la fonction
        with patch.dict(
            sys.modules,
            {"sentence_transformers": MagicMock(SentenceTransformer=mock_st_class)},
        ):
            result = import_module._load_model()

    mock_st_class.assert_called_once_with(str(fake_model_dir))
    assert result is not None


def test_load_model_branche_hf_si_chemin_absent(import_module, tmp_path):
    """Si _MODEL_PATH n'existe pas (cas CI / container prod sans cache), charge
    depuis HuggingFace via l'identifiant `_HF_MODEL_ID`."""
    nonexistent_path = tmp_path / "definitely_not_existing"
    # NOTE : on ne crée PAS le dossier — le path n'existe pas

    with patch.object(import_module, "_MODEL_PATH", nonexistent_path):
        mock_st_class = MagicMock(return_value=MagicMock(name="loaded_from_hf"))
        with patch.dict(
            sys.modules,
            {"sentence_transformers": MagicMock(SentenceTransformer=mock_st_class)},
        ):
            result = import_module._load_model()

    mock_st_class.assert_called_once_with(import_module._HF_MODEL_ID)
    assert result is not None


def test_hf_model_id_est_celui_de_vdb_service(import_module):
    """Garde-fou : l'identifiant HF utilisé par le script doit etre
    paraphrase-multilingual-MiniLM-L12-v2 (cohérent avec vdb_service.py
    et ADR-0008 §Phase B). Sans ca, l'import et la recherche n'auraient
    pas les memes embeddings → bug silencieux."""
    assert import_module._HF_MODEL_ID == (
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
