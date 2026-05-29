"""
Tests pour `app/services/vdb_service.py::_get_collection` embedding fallback
(followup #246).

Le module hesite entre 2 cas pour creer la fonction d'embedding :
    - Chemin local `modeles_manuels/paraphrase-multilingual-MiniLM-L12-v2/` existe
      → `SentenceTransformerEmbeddingFunction(model_name=str(local_path))`
    - Sinon → `SentenceTransformerEmbeddingFunction(model_name=_HF_MODEL_ID)`

Avant ce followup, le 2e cas tombait sur `DefaultEmbeddingFunction()` de
chromadb (modele 384-dim generique DIFFERENT) → divergence silencieuse
d'embeddings entre l'import (`import_corpus_ivr.py`) et la recherche
(`vdb_service.py`).

On mock `embedding_functions` ET `chromadb.PersistentClient` pour eviter
le download reel et la creation effective de Chroma collection. On verifie
QUEL `model_name` est passe a `SentenceTransformerEmbeddingFunction`.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services import vdb_service


def _make_chromadb_mocks(captured_ef_kwargs: list):
    """Construit un mock de `chromadb` + `embedding_functions` qui capture les
    kwargs passes a `SentenceTransformerEmbeddingFunction`."""

    def _st_ef_init(*args, **kwargs):
        captured_ef_kwargs.append({"args": args, "kwargs": kwargs})
        return MagicMock(name="ST_EF")

    mock_ef_module = MagicMock()
    mock_ef_module.SentenceTransformerEmbeddingFunction = _st_ef_init
    mock_ef_module.DefaultEmbeddingFunction = MagicMock(name="DEFAULT_EF")

    mock_chromadb = MagicMock(name="chromadb")
    mock_chromadb.PersistentClient = MagicMock(
        return_value=MagicMock(
            get_or_create_collection=MagicMock(return_value=MagicMock(name="collection"))
        )
    )

    return mock_chromadb, mock_ef_module


def test_get_collection_utilise_chemin_local_si_existe(monkeypatch, tmp_path):
    """Si `modeles_manuels/paraphrase-multilingual-MiniLM-L12-v2/` existe,
    `SentenceTransformerEmbeddingFunction` recoit le PATH LOCAL."""
    # Reset le singleton pour forcer la creation
    vdb_service._chroma_collection = None

    fake_model_dir = tmp_path / "modeles_manuels" / "paraphrase-multilingual-MiniLM-L12-v2"
    fake_model_dir.mkdir(parents=True)

    # On override le chemin parent racine pour pointer vers tmp_path
    # En l'occurrence, vdb_service calcule:
    #   model_path = Path(__file__).parent.parent.parent / "modeles_manuels" / ...
    # On mock juste Path.exists() pour qu'il retourne True sur model_path
    real_exists = Path.exists

    def fake_exists(self):
        # Toute Path pointant sur "modeles_manuels/paraphrase-multilingual-MiniLM-L12-v2"
        # est consideree comme existante.
        if "paraphrase-multilingual-MiniLM-L12-v2" in str(self):
            return True
        return real_exists(self)

    monkeypatch.setattr(Path, "exists", fake_exists)

    captured = []
    mock_chromadb, mock_ef_module = _make_chromadb_mocks(captured)

    import sys
    with patch.dict(
        sys.modules,
        {
            "chromadb": mock_chromadb,
            "chromadb.utils": MagicMock(embedding_functions=mock_ef_module),
        },
    ):
        # On doit aussi mocker chromadb.utils dans le scope import du module
        mock_utils = MagicMock()
        mock_utils.embedding_functions = mock_ef_module
        sys.modules["chromadb.utils"] = mock_utils
        vdb_service._get_collection()

    assert len(captured) == 1, "SentenceTransformerEmbeddingFunction doit etre appele 1 fois"
    model_name = captured[0]["kwargs"].get("model_name") or captured[0]["args"][0]
    assert "modeles_manuels" in model_name, (
        f"Doit utiliser le chemin LOCAL, got: {model_name}"
    )


def test_get_collection_fallback_hf_si_chemin_local_absent(monkeypatch):
    """Si modeles_manuels/ absent, fallback vers _HF_MODEL_ID
    (pas vers DefaultEmbeddingFunction comme avant)."""
    vdb_service._chroma_collection = None

    real_exists = Path.exists

    def fake_exists(self):
        # Le path modeles_manuels/paraphrase-multilingual-MiniLM-L12-v2 N'EXISTE PAS
        if "paraphrase-multilingual-MiniLM-L12-v2" in str(self):
            return False
        return real_exists(self)

    monkeypatch.setattr(Path, "exists", fake_exists)

    captured = []
    mock_chromadb, mock_ef_module = _make_chromadb_mocks(captured)

    import sys
    mock_utils = MagicMock()
    mock_utils.embedding_functions = mock_ef_module
    with patch.dict(
        sys.modules,
        {"chromadb": mock_chromadb, "chromadb.utils": mock_utils},
    ):
        vdb_service._get_collection()

    # On doit avoir appele SentenceTransformerEmbeddingFunction (PAS DefaultEmbeddingFunction)
    assert len(captured) == 1, (
        "SentenceTransformerEmbeddingFunction doit etre appele 1 fois "
        "(fallback HF, PAS DefaultEmbeddingFunction)"
    )
    # ET on doit l'avoir appele avec _HF_MODEL_ID
    model_name = captured[0]["kwargs"].get("model_name") or captured[0]["args"][0]
    assert model_name == vdb_service._HF_MODEL_ID, (
        f"Doit utiliser _HF_MODEL_ID, got: {model_name}"
    )
    # Et DefaultEmbeddingFunction n'a PAS ete appele
    mock_ef_module.DefaultEmbeddingFunction.assert_not_called()


def test_hf_model_id_coherent_avec_import_corpus_ivr():
    """Garde-fou : `_HF_MODEL_ID` dans vdb_service.py DOIT etre strictement
    identique a celui de scripts/import_corpus_ivr.py (followup #246).
    Sans cette identite, on aurait des embeddings differents entre import
    et search → bug silencieux."""
    assert vdb_service._HF_MODEL_ID == (
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
