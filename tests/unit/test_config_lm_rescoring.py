"""Config du filtre LM anti-hallucination ASR (ADR-0029, issue #94).

Contrats testés :
- Défauts : flag ENABLE_LM_RESCORING=False + les 4 seuils
  (lm_ppl_reject=500, lm_ppl_caution=150, lm_oov_reject=0.40, lm_repeat_max_reject=3).
- Surcharge par variables d'environnement (chargement Pydantic).
- Validation Field (hardening d'entrée) : un seuil ≤ 0, un ratio OOV hors [0,1]
  ou un nombre de répétitions < 1 est REFUSÉ dès le chargement de la config.

Même pattern de reload hermétique que test_config_loading.py : `Settings` lit
l'env à la construction et le module vit dans sys.modules toute la session, donc
chaque test reconstruit une config sous une env contrôlée puis restaure l'état.
"""
from __future__ import annotations

import importlib

import pytest
from pydantic import ValidationError


@pytest.fixture(autouse=True)
def _restore_config_module(monkeypatch):
    """Restaure app.config avec l'env de session APRÈS le test (cf.
    test_config_loading.py) pour ne pas polluer les autres fichiers de tests."""
    yield
    monkeypatch.undo()
    import app.config

    app.config.get_settings.cache_clear()
    importlib.reload(app.config)


def _fresh_settings(monkeypatch, **env):
    """Recharge app.config sous une env contrôlée et retourne un Settings neuf.

    RATE_LIMIT est retiré (posé par le conftest projet) pour partir d'un état
    propre — sans incidence sur les champs LM testés ici.
    """
    monkeypatch.delenv("RATE_LIMIT", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    import app.config

    app.config.get_settings.cache_clear()
    module = importlib.reload(app.config)
    return module.Settings()


def test_lm_rescoring_defaults(monkeypatch):
    """Défauts : filtre OFF + seuils de la littérature ASR basse-ressource."""
    settings = _fresh_settings(monkeypatch)

    assert settings.enable_lm_rescoring is False
    assert settings.lm_ppl_reject == 500.0
    assert settings.lm_ppl_caution == 150.0
    assert settings.lm_oov_reject == 0.40
    assert settings.lm_oov_caution == 0.15
    assert settings.lm_repeat_max_reject == 3


def test_lm_rescoring_env_override(monkeypatch):
    """Le flag et les seuils sont surchargeables par l'environnement."""
    settings = _fresh_settings(
        monkeypatch,
        ENABLE_LM_RESCORING="true",
        LM_PPL_REJECT="1234.5",
        LM_PPL_CAUTION="99.0",
        LM_OOV_REJECT="0.6",
        LM_OOV_CAUTION="0.2",
        LM_REPEAT_MAX_REJECT="7",
    )

    assert settings.enable_lm_rescoring is True
    assert settings.lm_ppl_reject == 1234.5
    assert settings.lm_ppl_caution == 99.0
    assert settings.lm_oov_reject == 0.6
    assert settings.lm_oov_caution == 0.2
    assert settings.lm_repeat_max_reject == 7


@pytest.mark.parametrize(
    "env",
    [
        {"LM_PPL_REJECT": "0"},         # gt=0
        {"LM_PPL_REJECT": "-1"},        # gt=0
        {"LM_PPL_CAUTION": "0"},        # gt=0
        {"LM_OOV_REJECT": "1.5"},       # le=1
        {"LM_OOV_REJECT": "-0.1"},      # ge=0
        {"LM_OOV_CAUTION": "1.5"},      # le=1
        {"LM_REPEAT_MAX_REJECT": "0"},  # ge=1
    ],
)
def test_lm_rescoring_invalid_thresholds_rejected(monkeypatch, env):
    """Un seuil hors bornes est refusé au chargement (fail-fast Pydantic)."""
    with pytest.raises(ValidationError):
        _fresh_settings(monkeypatch, **env)
