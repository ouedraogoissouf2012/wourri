"""Tests — settings d'instrumentation qualité IVR (issue #297, ADR-0028 A1).

Contrats testés (chargement Pydantic, sans base ni réseau) :
- `nlu_min_confidence` : défaut 0.2 (INCHANGÉ vs l'ancien hardcode),
  surchargeable via la variable d'environnement NLU_MIN_CONFIDENCE ;
- `ivr_max_semantic_distance` : défaut provisoire 1.0 (A2), surchargeable
  via IVR_MAX_SEMANTIC_DISTANCE ;
- bornes de validation : confiance ∈ [0,1], distance cosine ∈ [0,2].

On construit un `Settings()` neuf par test (la classe relit os.environ à chaque
instanciation) — pas besoin de recharger le module comme pour le singleton caché.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def _settings(monkeypatch, **env):
    """Retourne un Settings neuf avec un environnement contrôlé pour les 2 champs."""
    for key in ("NLU_MIN_CONFIDENCE", "IVR_MAX_SEMANTIC_DISTANCE"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings()


def test_nlu_min_confidence_default_is_0_2(monkeypatch):
    """Défaut inchangé (0.2) → comportement NLU identique à avant l'externalisation."""
    assert _settings(monkeypatch).nlu_min_confidence == 0.2


def test_nlu_min_confidence_override_by_env(monkeypatch):
    assert _settings(monkeypatch, NLU_MIN_CONFIDENCE="0.5").nlu_min_confidence == 0.5


def test_ivr_max_semantic_distance_default_is_1_0(monkeypatch):
    """Défaut provisoire 1.0 (déclaré pour A2, non utilisé en A1)."""
    assert _settings(monkeypatch).ivr_max_semantic_distance == 1.0


def test_ivr_max_semantic_distance_override_by_env(monkeypatch):
    assert (
        _settings(monkeypatch, IVR_MAX_SEMANTIC_DISTANCE="0.75").ivr_max_semantic_distance
        == 0.75
    )


def test_nlu_min_confidence_rejects_out_of_range(monkeypatch):
    """Une confiance > 1 est une erreur de config → refus au chargement (fail-fast)."""
    with pytest.raises(ValidationError):
        _settings(monkeypatch, NLU_MIN_CONFIDENCE="1.5")


def test_ivr_max_semantic_distance_rejects_out_of_range(monkeypatch):
    """La distance cosine pgvector vit dans [0,2] → au-delà, refus au chargement."""
    with pytest.raises(ValidationError):
        _settings(monkeypatch, IVR_MAX_SEMANTIC_DISTANCE="3.0")
