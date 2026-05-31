"""Tests unitaires — `app/services/corpus_service.py` (Sprint F Phase C, ADR-0008).

Reproduisent les cas couverts par les tests `vdb_service` existants (scoring,
cascade 3 essais, fallback). Aucune connexion Postgres réelle — les engines
SQLAlchemy et le modèle SentenceTransformer sont mockés via `unittest.mock`.

Pour les tests d'intégration avec vraie BDD, voir
`tests/integration/test_corpus_facade.py`.
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from app.services import corpus_service


# ─────────────────────────────────────────────────────────────────────────
# Fixture utilities
# ─────────────────────────────────────────────────────────────────────────


_SENTINEL = object()


def _make_row(
    id_: str,
    intent: str = "CONSEIL_PRODUCTION",
    cultures=_SENTINEL,
    conditions: list[str] | None = None,
    score: float = 0.8,
    reponse_bambara: str = "test ba",
    reponse_fr: str = "test fr",
) -> dict:
    # cultures peut être [] (distinct du défaut "CULTURE_RIZ") — sentinel pour
    # ne pas être piégé par le `or` truthy/falsy classique.
    return {
        "id": id_,
        "intent": intent,
        "cultures": ["CULTURE_RIZ"] if cultures is _SENTINEL else cultures,
        "conditions": conditions or [],
        "reponse_bambara": reponse_bambara,
        "reponse_fr": reponse_fr,
        "score_validation": score,
    }


@contextmanager
def _patch_engine_returning(*query_results):
    """Patch `_get_engine` pour retourner des résultats SQL séquentiels.

    `query_results` = liste de listes de dicts. Le n-ième `conn.execute(...)` retourne
    un objet itérable des dicts du n-ième élément.
    """
    iterator = iter(query_results)

    def execute(*args, **kwargs):
        try:
            rows = next(iterator)
        except StopIteration:
            rows = []
        # row._mapping -> dict pour _query_candidates ; first()/scalar() pour les autres
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter(
            [MagicMock(_mapping=r) for r in rows]
        )
        if rows:
            mock_result.first.return_value = MagicMock(__getitem__=lambda s, i: list(rows[0].values())[i])
            mock_result.scalar.return_value = list(rows[0].values())[0]
        else:
            mock_result.first.return_value = None
            mock_result.scalar.return_value = 0
        mock_result.all.return_value = [
            MagicMock(__getitem__=lambda s, i, r=r: list(r.values())[i]) for r in rows
        ]
        return mock_result

    mock_conn = MagicMock()
    mock_conn.execute.side_effect = execute
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.__exit__.return_value = False

    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_conn
    mock_engine.begin.return_value = mock_conn

    corpus_service._get_engine.cache_clear()
    with patch.object(corpus_service, "_get_engine", return_value=mock_engine):
        yield


@contextmanager
def _patch_model(dim: int = 384):
    """Patch `_get_model` pour retourner un vecteur déterministe (0.1*i)."""
    mock_model = MagicMock()
    vec = [0.1] * dim
    mock_model.encode.return_value = [vec]
    corpus_service._get_model.cache_clear()
    with patch.object(corpus_service, "_get_model", return_value=mock_model):
        yield


# ─────────────────────────────────────────────────────────────────────────
# Tests : helpers internes
# ─────────────────────────────────────────────────────────────────────────


class TestBestResultPg:
    """Reproduit les cas de `vdb_service._best_result` (scoring identique)."""

    def test_returns_none_for_empty_rows(self):
        assert corpus_service._best_result_pg([], conditions=[]) is None

    def test_picks_highest_score_validation(self):
        rows = [
            _make_row("low", score=0.5),
            _make_row("high", score=0.9),
            _make_row("mid", score=0.7),
        ]
        result = corpus_service._best_result_pg(rows, conditions=[])
        assert result is not None
        assert result["id"] == "high"

    def test_season_bonus_promotes_match(self):
        """Une entrée saison_pluie devrait être favorisée en mois de pluie."""
        rows = [
            _make_row("dry", score=0.85, conditions=["saison_seche"]),
            _make_row("rain", score=0.75, conditions=["saison_pluie"]),
        ]
        with patch.object(corpus_service, "_get_current_season", return_value="saison_pluie"):
            result = corpus_service._best_result_pg(rows, conditions=[])
        # 0.75 + 0.15 (rain match) = 0.90 > 0.85 - 0.05 (dry penalty) = 0.80
        assert result is not None
        assert result["id"] == "rain"

    def test_explicit_condition_bonus(self):
        """Une condition explicite donnée par le caller doit booster +0.05."""
        rows = [
            _make_row("plain", score=0.80, conditions=[]),
            _make_row("matched", score=0.78, conditions=["urgence"]),
        ]
        with patch.object(corpus_service, "_get_current_season", return_value="saison_seche"):
            result = corpus_service._best_result_pg(rows, conditions=["urgence"])
        # plain : 0.80 (pas de saison → +0) = 0.80
        # matched : 0.78 (pas de saison → +0) + 0.05 (urgence match) = 0.83
        assert result is not None
        assert result["id"] == "matched"

    def test_returns_first_culture_as_string(self):
        rows = [_make_row("e1", cultures=["CULTURE_RIZ", "CULTURE_MAIS"], score=0.9)]
        result = corpus_service._best_result_pg(rows, conditions=[])
        assert result is not None
        # vdb_service stockait cultures en CSV ; corpus_service retourne la 1re
        assert result["cultures"] == "CULTURE_RIZ"

    def test_wildcard_culture_fallback(self):
        rows = [_make_row("e1", cultures=[], score=0.9)]
        result = corpus_service._best_result_pg(rows, conditions=[])
        assert result is not None
        assert result["cultures"] == "*"


class TestGetCurrentSeason:
    """Pareil que vdb_service._get_current_season (copie fidèle)."""

    @pytest.mark.parametrize("month,expected", [
        (3, "saison_pluie"), (6, "saison_pluie"), (9, "saison_pluie"), (10, "saison_pluie"),
        (1, "saison_seche"), (7, "saison_seche"), (11, "saison_seche"),
    ])
    def test_season_calendar_ci(self, month, expected):
        with patch("app.services.corpus_service.datetime") as mock_dt:
            mock_dt.now.return_value.month = month
            assert corpus_service._get_current_season() == expected


class TestFormatVector:
    def test_serialize_list_of_floats(self):
        # Fix #184 : `_format_vector` exige `len(vec) == _EMBEDDING_DIM`.
        # On patche la constante a 3 pour preserver la valeur pedagogique
        # du test (assertion exacte sur la string de sortie).
        with patch.object(corpus_service, "_EMBEDDING_DIM", 3):
            out = corpus_service._format_vector([0.1, 0.2, 0.3])
        assert out == "[0.1000000,0.2000000,0.3000000]"

    def test_serialize_numpy_array(self):
        np = pytest.importorskip("numpy")
        with patch.object(corpus_service, "_EMBEDDING_DIM", 2):
            out = corpus_service._format_vector(np.array([0.5, -0.5]))
        assert out == "[0.5000000,-0.5000000]"

    def test_serialize_full_384_dim_vector(self):
        """Cas reel : vecteur de dimension prod (384). Verifie le prefixe."""
        vec = [0.0] * 384
        out = corpus_service._format_vector(vec)
        assert out.startswith("[0.0000000,")
        assert out.endswith("]")
        # 384 valeurs separees par 383 virgules
        assert out.count(",") == 383

    def test_raises_when_dim_mismatch(self):
        """Fix #184 : len(vec) != 384 doit lever ValueError clair."""
        with pytest.raises(ValueError, match="Embedding dim mismatch.*100.*384"):
            corpus_service._format_vector([0.0] * 100)

    def test_raises_when_empty_vector(self):
        """Fix #184 : un vecteur vide doit aussi etre rejete (defense profonde)."""
        with pytest.raises(ValueError, match="Embedding dim mismatch.*0.*384"):
            corpus_service._format_vector([])


# ─────────────────────────────────────────────────────────────────────────
# Tests : API publique avec engine mocké
# ─────────────────────────────────────────────────────────────────────────


class TestChercherReponseIvr:
    def test_returns_none_when_no_match(self):
        with _patch_model(), _patch_engine_returning([], [], []):
            result = corpus_service.chercher_reponse_ivr(
                "UNKNOWN_INTENT", cultures=["CULTURE_RIZ"], conditions=[]
            )
        assert result is None

    def test_essai_1_match_exact_returns_best(self):
        rows = [_make_row("riz_001", cultures=["CULTURE_RIZ"], score=0.9)]
        with _patch_model(), _patch_engine_returning(rows):
            result = corpus_service.chercher_reponse_ivr(
                "CONSEIL_PRODUCTION", cultures=["CULTURE_RIZ"], conditions=[]
            )
        assert result is not None
        assert result["id"] == "riz_001"

    def test_essai_2_match_wildcard_returns_best(self):
        """Cascade essai 2 : intent + cultures = ['*']. Doit matcher quand
        l'essai 1 (culture exacte) ne donne rien."""
        with _patch_model(), _patch_engine_returning(
            [],  # essai 1 : aucun match culture exacte
            [_make_row("wildcard_001", cultures=["*"], score=0.75)],  # essai 2
        ):
            result = corpus_service.chercher_reponse_ivr(
                "CONSEIL_PRODUCTION", cultures=["CULTURE_MAIS"], conditions=[]
            )
        assert result is not None
        assert result["id"] == "wildcard_001"

    def test_falls_through_to_essai_3_intent_only(self):
        # Essai 1 (culture exacte) : vide ; essai 2 (wildcard) : vide ; essai 3 : match
        with _patch_model(), _patch_engine_returning(
            [],  # essai 1
            [],  # essai 2
            [_make_row("generic_001", cultures=["*"], score=0.7)],  # essai 3
        ):
            result = corpus_service.chercher_reponse_ivr(
                "CONSEIL_PRODUCTION", cultures=["CULTURE_RIZ"], conditions=[]
            )
        assert result is not None
        assert result["id"] == "generic_001"


class TestGetReponseFallback:
    def test_returns_db_fallback_when_present(self):
        """Le mock doit injecter `reponse_bambara` en colonne 0 (la requête SQL
        sélectionne `reponse_bambara` uniquement). Assertion forte sur la valeur
        exacte — pas seulement "non vide" (Anti-pattern 7 corrigé)."""
        # On patche directement `conn.execute().first()` pour retourner un row
        # avec une seule colonne (reponse_bambara), évitant l'ambiguïté de
        # _patch_engine_returning qui sérialise le dict entier.
        from unittest.mock import MagicMock
        from contextlib import contextmanager
        from unittest.mock import patch as _patch

        custom_fallback = "custom fallback ba ɛɛɛ"
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda s, i: custom_fallback if i == 0 else None
        mock_result = MagicMock()
        mock_result.first.return_value = mock_row

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = False

        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn

        corpus_service._get_engine.cache_clear()
        with _patch.object(corpus_service, "_get_engine", return_value=mock_engine):
            result = corpus_service.get_reponse_fallback()
        assert result == custom_fallback

    def test_returns_hardcoded_when_db_unreachable(self):
        with patch.object(
            corpus_service, "_get_engine", side_effect=RuntimeError("no db")
        ):
            corpus_service._get_engine.cache_clear()
            result = corpus_service.get_reponse_fallback()
        assert result == corpus_service._FALLBACK_BAMBARA


class TestAjouterReponseValidee:
    def test_insert_returns_true_on_success(self):
        with _patch_model(), _patch_engine_returning([]):
            ok = corpus_service.ajouter_reponse_validee(
                intent="CONSEIL_PRODUCTION",
                cultures=["CULTURE_RIZ"],
                reponse_bambara="aw ye malo sɛnɛ",
                reponse_fr="plantez le riz",
                score_validation=0.8,
                conditions=["saison_pluie"],
                tags=["urgence"],
            )
        assert ok is True

    def test_returns_false_when_engine_fails(self):
        with patch.object(
            corpus_service, "_get_engine", side_effect=RuntimeError("no db")
        ), _patch_model():
            corpus_service._get_engine.cache_clear()
            ok = corpus_service.ajouter_reponse_validee(
                intent="CONSEIL_PRODUCTION",
                cultures=["CULTURE_RIZ"],
                reponse_bambara="x", reponse_fr="x", score_validation=0.5,
            )
        assert ok is False


class TestGetPhrasesForIntent:
    def test_returns_empty_list_when_no_entry(self):
        with _patch_engine_returning([]):
            result = corpus_service.get_phrases_for_intent(
                "UNKNOWN_INTENT", cultures=["CULTURE_RIZ"]
            )
        assert result == []

    def test_returns_empty_list_when_engine_fails(self):
        with patch.object(
            corpus_service, "_get_engine", side_effect=RuntimeError("no db")
        ):
            corpus_service._get_engine.cache_clear()
            result = corpus_service.get_phrases_for_intent(
                "CONSEIL_PRODUCTION", cultures=["CULTURE_RIZ"]
            )
        assert result == []


class TestInitialiserVdb:
    def test_no_exception_when_engine_fails(self):
        # initialiser_vdb doit dégrader gracieusement (log warning, pas lever)
        with patch.object(
            corpus_service, "_get_engine", side_effect=RuntimeError("no db")
        ):
            corpus_service._get_engine.cache_clear()
            corpus_service.initialiser_vdb()  # ne doit pas lever

    def test_happy_path_counts_entries_and_preloads_model(self):
        """Issue #183 : happy path engine OK + count + precharge modele (R3).

        Verifie que :
        1. _get_engine() est appele et la connexion ouverte
        2. SELECT count(*) FROM corpus_entries est execute
        3. _get_model() est appele (precharge R3 mitigation double-charge memoire
           en mode dual avec Chroma simultane)
        """
        mock_result = MagicMock()
        mock_result.scalar.return_value = 162

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = False

        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn

        mock_model = MagicMock()

        corpus_service._get_engine.cache_clear()
        corpus_service._get_model.cache_clear()
        with patch.object(corpus_service, "_get_engine", return_value=mock_engine), \
             patch.object(corpus_service, "_get_model", return_value=mock_model) as mock_get_model:
            corpus_service.initialiser_vdb()

        # R3 mitigation : modele precharge
        mock_get_model.assert_called_once()
        # SELECT count(*) execute
        mock_conn.execute.assert_called_once()
        sql_arg = mock_conn.execute.call_args[0][0]
        assert "count" in str(sql_arg).lower()
        assert "corpus_entries" in str(sql_arg).lower()
