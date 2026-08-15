"""Tests du filtre KenLM avec un modèle factice déterministe."""
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.validation import lm_filter


@pytest.fixture(autouse=True)
def reset_lm_filter_singletons():
    lm_filter.DioulaLMFilter._instance = None
    lm_filter._default_filter = None
    yield
    lm_filter.DioulaLMFilter._instance = None
    lm_filter._default_filter = None


def _active_filter(
    logprob=-1.0,
    lexicon=None,
    *,
    ppl_reject=lm_filter.PPL_REJECT,
    ppl_caution=lm_filter.PPL_CAUTION,
    oov_reject=lm_filter.OOV_REJECT,
    oov_caution=lm_filter.OOV_CAUTION,
    repeat_max_reject=lm_filter.REPEAT_MAX_REJECT,
):
    instance = lm_filter.DioulaLMFilter.__new__(lm_filter.DioulaLMFilter)
    instance._initialized = True
    instance.model_path = MagicMock()
    instance.lm = MagicMock()
    instance.lm.score.return_value = logprob
    instance.lexicon = lexicon or set()
    instance.available = True
    instance.enabled = True
    instance.ppl_reject = ppl_reject
    instance.ppl_caution = ppl_caution
    instance.oov_reject = oov_reject
    instance.oov_caution = oov_caution
    instance.repeat_max_reject = repeat_max_reject
    return instance


def test_missing_model_keeps_filter_inactive(tmp_path):
    fake_kenlm = MagicMock()

    with patch.dict(sys.modules, {"kenlm": fake_kenlm}):
        # enabled=True explicite : le défaut du constructeur est désormais False
        # (fail-safe) ; on veut ici tester le chemin ACTIF avec binaire absent.
        instance = lm_filter.DioulaLMFilter(tmp_path / "missing.binary", enabled=True)

    assert not instance.available
    fake_kenlm.Model.assert_not_called()
    # Scénario V3 cardinal (#94) : flag ON mais binaire absent → pass-through au
    # niveau VERDICT (pas seulement available). Aucune régression avant provisioning.
    assert instance.score("malo sɛnɛ").verdict == "HIGH"


def test_existing_model_is_loaded(tmp_path):
    model_path = tmp_path / "model.binary"
    model_path.write_bytes(b"model")
    fake_kenlm = MagicMock()
    fake_model = MagicMock()
    fake_kenlm.Model.return_value = fake_model

    with (
        patch.dict(sys.modules, {"kenlm": fake_kenlm}),
        patch("app.services.validation.lm_filter.os.path.getsize", return_value=1024),
    ):
        instance = lm_filter.DioulaLMFilter(
            model_path,
            lexicon={"malo", "sɛnɛ"},
            enabled=True,
        )

    assert instance.available
    assert instance.lm is fake_model
    assert instance.lexicon == {"malo", "sɛnɛ"}
    fake_kenlm.Model.assert_called_once_with(str(model_path))


def test_model_load_error_keeps_filter_inactive(tmp_path):
    model_path = tmp_path / "broken.binary"
    model_path.write_bytes(b"model")
    fake_kenlm = MagicMock()
    fake_kenlm.Model.side_effect = RuntimeError("invalid model")

    with patch.dict(sys.modules, {"kenlm": fake_kenlm}):
        instance = lm_filter.DioulaLMFilter(model_path, enabled=True)

    assert not instance.available


def test_unavailable_filter_is_pass_through():
    instance = _active_filter()
    instance.available = False

    score = instance.score("texte quelconque")

    assert score.verdict == "HIGH"
    assert score.n_tokens == 0
    assert not score.is_suspect


def test_empty_text_is_rejected():
    score = _active_filter().score("   ")

    assert score.verdict == "REJECT"
    assert score.ppl_norm == 1e6
    assert score.oov_ratio == 1.0
    assert score.is_suspect


@pytest.mark.parametrize(
    ("logprob", "text", "lexicon", "expected_verdict"),
    [
        (-1.0, "malo sɛnɛ", {"malo", "sɛnɛ"}, "HIGH"),
        (-5.0, "malo sɛnɛ", {"malo", "sɛnɛ"}, "MEDIUM"),
        (-1.0, "malo inconnu", {"malo", "sɛnɛ"}, "REJECT"),
        (-1.0, "ka ka ka ka ka", {"ka"}, "REJECT"),
    ],
)
def test_composite_verdicts(logprob, text, lexicon, expected_verdict):
    instance = _active_filter(logprob=logprob, lexicon=lexicon)

    score = instance.score(text)

    assert score.verdict == expected_verdict
    assert score.n_tokens == len(text.split())
    instance.lm.score.assert_called_once_with(text, bos=True, eos=True)


def test_rescore_candidates_selects_lowest_perplexity():
    instance = _active_filter()
    scores = {
        "hypothèse faible": lm_filter.LMScore(300, 0, 0, "MEDIUM", -1, 2),
        "malo sɛnɛ": lm_filter.LMScore(12, 0, 0, "HIGH", -1, 2),
    }
    instance.score = MagicMock(side_effect=lambda text: scores[text])

    assert instance.rescore_candidates(
        ["hypothèse faible", "malo sɛnɛ"],
    ) == "malo sɛnɛ"


def test_rescore_candidates_falls_back_when_unavailable_or_empty():
    instance = _active_filter()
    instance.available = False

    assert instance.rescore_candidates(["premier", "second"]) == "premier"
    assert instance.rescore_candidates([]) is None


def test_get_lm_filter_returns_singleton(tmp_path):
    with patch.object(lm_filter.DioulaLMFilter, "_load", return_value=None):
        first = lm_filter.get_lm_filter()
        second = lm_filter.get_lm_filter()

    assert first is second


# ─────────────────────────────────────────────────────────────────────────────
# ADR-0029 / #94 : feature flag ENABLE_LM_RESCORING + seuils externalisés
# ─────────────────────────────────────────────────────────────────────────────


def test_flag_disabled_keeps_filter_inactive_even_with_model(tmp_path):
    """enabled=False → filtre inactif MÊME si kenlm est installé et le binaire
    présent. Le binaire n'est jamais chargé (pass-through, zéro coût)."""
    model_path = tmp_path / "model.binary"
    model_path.write_bytes(b"model")
    fake_kenlm = MagicMock()
    fake_kenlm.Model.return_value = MagicMock()

    with patch.dict(sys.modules, {"kenlm": fake_kenlm}):
        instance = lm_filter.DioulaLMFilter(model_path, enabled=False)

    assert not instance.available
    fake_kenlm.Model.assert_not_called()
    assert instance.score("malo sɛnɛ").verdict == "HIGH"  # pass-through


@pytest.mark.parametrize(
    ("kwargs", "text", "lexicon", "expected"),
    [
        # ppl_reject DURCI : ppl_norm≈3.16 (logprob -1, 2 tokens) franchit 1.0 → REJECT
        (dict(logprob=-1.0, ppl_reject=1.0), "malo sɛnɛ", None, "REJECT"),
        # oov_reject ASSOUPLI : 1 OOV / 2 = 0.5 ; défaut 0.40 rejetterait, 0.9 → MEDIUM (0.5 > oov_caution 0.15)
        (dict(logprob=-1.0, oov_reject=0.9), "malo inconnu", {"malo"}, "MEDIUM"),
        # oov_caution ASSOUPLI en plus : 0.5 ne franchit plus ni 0.9 (reject) ni 0.6 (caution) → HIGH
        (dict(logprob=-1.0, oov_reject=0.9, oov_caution=0.6), "malo inconnu", {"malo"}, "HIGH"),
        # repeat_max_reject ASSOUPLI : "ka"×5 = 4 bigrammes ; défaut 3 rejetterait, 10 → HIGH
        (dict(logprob=-1.0, repeat_max_reject=10), "ka ka ka ka ka", {"ka"}, "HIGH"),
    ],
)
def test_injected_thresholds_drive_verdict(kwargs, text, lexicon, expected):
    """Les 4 seuils sont lus depuis l'instance (injectés par la config), pas
    depuis les constantes module : un seuil modifié change le verdict."""
    instance = _active_filter(lexicon=lexicon, **kwargs)

    assert instance.score(text).verdict == expected


def test_get_lm_filter_injects_settings_flag_and_thresholds():
    """get_lm_filter() lit le flag + les 4 seuils depuis Settings et les injecte.
    Flag OFF → filtre inactif (pass-through) sans toucher kenlm."""
    fake_settings = SimpleNamespace(
        enable_lm_rescoring=False,
        lm_ppl_reject=42.0,
        lm_ppl_caution=7.0,
        lm_oov_reject=0.25,
        lm_oov_caution=0.10,
        lm_repeat_max_reject=9,
    )

    with patch("app.config.get_settings", return_value=fake_settings):
        flt = lm_filter.get_lm_filter()

    assert flt.enabled is False
    assert flt.ppl_reject == 42.0
    assert flt.ppl_caution == 7.0
    assert flt.oov_reject == 0.25
    assert flt.oov_caution == 0.10
    assert flt.repeat_max_reject == 9
    assert not flt.available
    assert flt.score("n'importe quoi").verdict == "HIGH"


def test_default_constructor_is_failsafe_disabled(tmp_path):
    """Fail-safe : le défaut du constructeur est enabled=False. Une construction
    directe (ex. l'exemple du docstring) n'active JAMAIS le rescoring sans opt-in,
    même si kenlm est installé et le binaire présent."""
    model_path = tmp_path / "model.binary"
    model_path.write_bytes(b"model")
    fake_kenlm = MagicMock()
    fake_kenlm.Model.return_value = MagicMock()

    with patch.dict(sys.modules, {"kenlm": fake_kenlm}):
        instance = lm_filter.DioulaLMFilter(model_path)  # pas d'enabled= → défaut

    assert instance.enabled is False
    assert not instance.available
    fake_kenlm.Model.assert_not_called()


def test_kenlm_dyu_path_env_overrides_default(monkeypatch):
    """KENLM_DYU_PATH surcharge le chemin par défaut du binaire (pattern
    MMS_DYU_ADAPTER_PATH). Lu à l'import → on recharge le module sous env, puis
    on restaure l'état par un second reload dans le finally."""
    monkeypatch.setenv("KENLM_DYU_PATH", str(Path("/custom") / "kenlm.binary"))
    try:
        reloaded = importlib.reload(lm_filter)
        assert reloaded._DEFAULT_LM_PATH == Path("/custom") / "kenlm.binary"
    finally:
        monkeypatch.delenv("KENLM_DYU_PATH", raising=False)
        importlib.reload(lm_filter)
