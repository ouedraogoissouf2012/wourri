"""Tests — externalisation du seuil de confiance NLU (issue #297, ADR-0028 A1).

Le seuil (ex-`NLUService.MIN_CONFIDENCE_THRESHOLD`, hardcodé à 0.2) est désormais
lu depuis `settings.nlu_min_confidence` et injectable au constructeur (DIP).
Aucune base réelle : seuls le fichier de concepts versionné et un `settings`
simulé sont utilisés. La valeur exposée est lue via l'API publique `get_stats()`.
"""
from __future__ import annotations

import types
from pathlib import Path
from unittest.mock import MagicMock

from app.services.nlu.nlu_service import NLUService

# Fichier de concepts réel (comme test_nlu_contracts.py) — pas de base, pas de réseau.
_CONCEPTS_PATH = str(
    Path(__file__).resolve().parents[2] / "dictionnaires" / "nlu_concepts.json"
)


def test_threshold_read_from_config(monkeypatch):
    """Sans injection, le seuil provient de `settings.nlu_min_confidence`.

    On remplace le singleton settings par un stub : si NLUService lisait encore
    une constante hardcodée, l'assertion échouerait.
    """
    monkeypatch.setattr(
        "app.config.settings", types.SimpleNamespace(nlu_min_confidence=0.37)
    )
    svc = NLUService(_CONCEPTS_PATH)
    assert svc.get_stats()["min_confidence_threshold"] == 0.37


def test_injection_takes_precedence_over_config(monkeypatch):
    """Le seuil injecté prime : la config n'est pas consultée (court-circuit DIP)."""
    monkeypatch.setattr(
        "app.config.settings", types.SimpleNamespace(nlu_min_confidence=0.9)
    )
    svc = NLUService(_CONCEPTS_PATH, min_confidence=0.55)
    assert svc.get_stats()["min_confidence_threshold"] == 0.55


def test_default_value_unchanged():
    """Bout-en-bout sans stub : le défaut réel de la config reste 0.2 (inchangé)."""
    svc = NLUService(_CONCEPTS_PATH)
    assert svc.get_stats()["min_confidence_threshold"] == 0.2


def _service_with_mocked_pipeline(min_confidence: float, classifier_confidence: float):
    """NLUService dont le classifier renvoie une confiance fixe et le builder un sentinel.

    Permet de prouver que le SEUIL injecté gouverne réellement la décision de
    reconstruction dans `process()` (nlu_service.py — `confidence >= self._min_confidence`),
    et pas seulement la valeur reportée par `get_stats()`.
    """
    svc = NLUService(_CONCEPTS_PATH, min_confidence=min_confidence)
    svc._extractor = MagicMock()
    svc._extractor.extract.return_value = {"CULTURE_RIZ": 1.0}
    svc._classifier = MagicMock()
    # Intent métier normal (ni HORS_SUJET ni SALUTATION_SEULE) → passe par le gate seuil.
    svc._classifier.classify.return_value = (
        "QUESTION_ENGRAIS",
        classifier_confidence,
        {"has_greeting": False},
    )
    svc._builder = MagicMock()
    svc._builder.build.return_value = "PHRASE_FR_RECONSTRUITE"
    return svc


def test_threshold_gates_reconstruction_when_confidence_below():
    """Confiance 0.35 < seuil injecté 0.5 → PAS de reconstruction (builder non appelé)."""
    svc = _service_with_mocked_pipeline(min_confidence=0.5, classifier_confidence=0.35)
    result = svc.process("n bɛ malo sɛnɛ")
    assert result.french_sentence is None
    svc._builder.build.assert_not_called()


def test_threshold_allows_reconstruction_when_confidence_above():
    """MÊME confiance 0.35, mais seuil injecté 0.2 → reconstruction effectuée.

    La bascule de comportement à confiance constante prouve que c'est bien le
    seuil externalisé (injecté) qui pilote la décision, pas un hardcode résiduel.
    """
    svc = _service_with_mocked_pipeline(min_confidence=0.2, classifier_confidence=0.35)
    result = svc.process("n bɛ malo sɛnɛ")
    assert result.french_sentence == "PHRASE_FR_RECONSTRUITE"
    svc._builder.build.assert_called_once()
