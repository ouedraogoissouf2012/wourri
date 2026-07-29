"""Tests du fallback NLLB au moyen d'un registre et modèle factices."""
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.translation import nllb_translator
from app.services.translation.interfaces import Direction


def _runtime():
    model = MagicMock()
    model.generate.return_value = ["generated"]
    tokenizer = MagicMock()
    tokenizer.return_value = {"input_ids": "tokens"}
    tokenizer.convert_tokens_to_ids.side_effect = lambda code: f"id:{code}"
    tokenizer.batch_decode.return_value = ["  traduction NLLB  "]
    torch = MagicMock()
    return model, tokenizer, torch


def test_loader_builds_and_evaluates_model():
    model, tokenizer, torch = _runtime()
    auto_model = MagicMock()
    auto_model.from_pretrained.return_value = model
    auto_tokenizer = MagicMock()
    auto_tokenizer.from_pretrained.return_value = tokenizer
    transformers = SimpleNamespace(
        AutoModelForSeq2SeqLM=auto_model,
        AutoTokenizer=auto_tokenizer,
    )
    settings = SimpleNamespace(hf_translator_model="model-test")

    with (
        patch.dict(
            sys.modules,
            {"torch": torch, "transformers": transformers},
        ),
        patch("app.config.get_settings", return_value=settings),
    ):
        loaded = nllb_translator._load_nllb()

    assert loaded == (model, tokenizer, torch)
    auto_tokenizer.from_pretrained.assert_called_once_with("model-test")
    auto_model.from_pretrained.assert_called_once_with("model-test")
    model.eval.assert_called_once_with()


def test_ensure_loaded_uses_registry_and_gates_retries():
    translator = nllb_translator.NLLBTranslator()

    with patch.object(
        nllb_translator.registry,
        "is_loaded",
        return_value=True,
    ):
        assert translator._ensure_loaded()

    with (
        patch.object(
            nllb_translator.registry,
            "is_loaded",
            return_value=False,
        ),
        patch.object(
            nllb_translator.registry,
            "get",
            return_value=_runtime(),
        ) as get,
    ):
        assert translator._ensure_loaded()
        get.assert_called_once()

    translator._load_failed = True
    with (
        patch.object(
            nllb_translator.registry,
            "is_loaded",
            return_value=False,
        ),
        patch.object(nllb_translator.registry, "get") as get,
    ):
        assert not translator._ensure_loaded()
        get.assert_not_called()


def test_ensure_loaded_records_registry_failure():
    translator = nllb_translator.NLLBTranslator()
    with (
        patch.object(
            nllb_translator.registry,
            "is_loaded",
            return_value=False,
        ),
        patch.object(
            nllb_translator.registry,
            "get",
            side_effect=RuntimeError("OOM"),
        ),
    ):
        assert not translator._ensure_loaded()

    assert translator._load_failed


@pytest.mark.parametrize(
    ("direction", "source_code", "target_code"),
    [
        (Direction.BAM_TO_FR, "bam_Latn", "fra_Latn"),
        (Direction.FR_TO_BAM, "fra_Latn", "bam_Latn"),
    ],
)
def test_translate_generates_for_each_direction(
    direction,
    source_code,
    target_code,
):
    translator = nllb_translator.NLLBTranslator()
    model, tokenizer, torch = _runtime()

    with (
        patch.object(translator, "_ensure_loaded", return_value=True),
        patch.object(
            nllb_translator.registry,
            "get",
            return_value=(model, tokenizer, torch),
        ),
    ):
        result = translator.translate("texte source", direction)

    assert result.text == "  traduction NLLB  "
    assert result.strategy_used == "nllb"
    assert result.confidence == 0.5
    assert tokenizer.src_lang == source_code
    tokenizer.convert_tokens_to_ids.assert_called_once_with(target_code)
    model.generate.assert_called_once()


def test_translate_returns_none_when_unavailable_or_output_invalid():
    translator = nllb_translator.NLLBTranslator()
    with patch.object(translator, "_ensure_loaded", return_value=False):
        assert translator.translate("texte", Direction.BAM_TO_FR) is None

    model, tokenizer, torch = _runtime()
    tokenizer.batch_decode.return_value = [""]
    with (
        patch.object(translator, "_ensure_loaded", return_value=True),
        patch.object(
            nllb_translator.registry,
            "get",
            return_value=(model, tokenizer, torch),
        ),
    ):
        assert translator.translate("texte", Direction.BAM_TO_FR) is None


def test_translate_handles_inference_error():
    translator = nllb_translator.NLLBTranslator()
    with (
        patch.object(translator, "_ensure_loaded", return_value=True),
        patch.object(
            nllb_translator.registry,
            "get",
            side_effect=RuntimeError("inference"),
        ),
    ):
        assert translator.translate("texte", Direction.BAM_TO_FR) is None


def test_get_model_and_tokenizer_and_contract_properties():
    translator = nllb_translator.NLLBTranslator()
    assert translator.name == "nllb"
    assert translator.priority == 3
    assert translator.can_handle("", Direction.BAM_TO_FR)

    with patch.object(translator, "_ensure_loaded", return_value=False):
        assert translator.get_model_and_tokenizer() == (None, None)

    model, tokenizer, torch = _runtime()
    with (
        patch.object(translator, "_ensure_loaded", return_value=True),
        patch.object(
            nllb_translator.registry,
            "get",
            return_value=(model, tokenizer, torch),
        ),
    ):
        assert translator.get_model_and_tokenizer() == (model, tokenizer)
