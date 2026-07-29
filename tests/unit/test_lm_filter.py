"""Tests du filtre KenLM avec un modèle factice déterministe."""
import sys
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


def _active_filter(logprob=-1.0, lexicon=None):
    instance = lm_filter.DioulaLMFilter.__new__(lm_filter.DioulaLMFilter)
    instance._initialized = True
    instance.model_path = MagicMock()
    instance.lm = MagicMock()
    instance.lm.score.return_value = logprob
    instance.lexicon = lexicon or set()
    instance.available = True
    return instance


def test_missing_model_keeps_filter_inactive(tmp_path):
    fake_kenlm = MagicMock()

    with patch.dict(sys.modules, {"kenlm": fake_kenlm}):
        instance = lm_filter.DioulaLMFilter(tmp_path / "missing.binary")

    assert not instance.available
    fake_kenlm.Model.assert_not_called()


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
        instance = lm_filter.DioulaLMFilter(model_path)

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
