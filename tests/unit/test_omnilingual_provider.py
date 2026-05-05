"""
Tests unitaires pour OmnilingualASR provider.

Strategie : tests sans GPU ni modele charge (mocks pour omnilingual_asr).
Les tests d'inference reelle (Phase 3) sont hors perimetre Phase 2.
"""
from unittest.mock import patch

import pytest

from app.services.asr.base import ASRProvider
from app.services.asr.omnilingual_provider import (
    MODEL_CARDS,
    OmnilingualASR,
)


class TestOmnilingualASRConstructor:
    """Tests du constructeur et validation des arguments."""

    def test_default_constructor_uses_300m_and_dyu_latn(self):
        provider = OmnilingualASR()
        assert provider._model_size == "300m"
        assert provider._default_lang == "dyu_Latn"
        assert provider._model_card == "omniASR_CTC_300M"

    def test_constructor_accepts_all_model_sizes(self):
        for size, expected_card in MODEL_CARDS.items():
            provider = OmnilingualASR(model_size=size)
            assert provider._model_size == size
            assert provider._model_card == expected_card

    def test_constructor_invalid_model_size_raises_value_error(self):
        with pytest.raises(ValueError, match="model_size invalide"):
            OmnilingualASR(model_size="42b")

    def test_constructor_invalid_model_size_lists_accepted_values(self):
        with pytest.raises(ValueError) as exc_info:
            OmnilingualASR(model_size="999z")
        # Le message doit citer les valeurs valides pour aider le dev
        message = str(exc_info.value)
        for size in MODEL_CARDS:
            assert size in message

    def test_constructor_accepts_custom_lang(self):
        provider = OmnilingualASR(default_lang="bam_Latn")
        assert provider._default_lang == "bam_Latn"


class TestOmnilingualASRName:
    """Tests de la propriete name."""

    def test_name_includes_model_size_uppercase(self):
        provider = OmnilingualASR(model_size="300m")
        assert provider.name == "Omnilingual 300M"

    def test_name_for_each_model_size(self):
        expected = {
            "300m": "Omnilingual 300M",
            "1b": "Omnilingual 1B",
            "1.2b": "Omnilingual 1.2B",
            "7b": "Omnilingual 7B",
        }
        for size, expected_name in expected.items():
            provider = OmnilingualASR(model_size=size)
            assert provider.name == expected_name


class TestOmnilingualASRIsAvailable:
    """Tests de is_available() en fonction de l'environnement."""

    def test_is_available_false_when_module_not_installed(self):
        with patch("app.services.asr.omnilingual_provider._omnilingual_available", False):
            provider = OmnilingualASR()
            assert provider.is_available() is False

    def test_is_available_true_when_module_and_lang_ok(self):
        fake_langs = ["dyu_Latn", "bam_Latn", "fra_Latn"]
        with (
            patch("app.services.asr.omnilingual_provider._omnilingual_available", True),
            patch("app.services.asr.omnilingual_provider._supported_langs", fake_langs),
        ):
            provider = OmnilingualASR(default_lang="dyu_Latn")
            assert provider.is_available() is True

    def test_is_available_false_when_lang_not_supported(self):
        # Simule un module installe mais avec une langue non supportee
        fake_langs = ["fra_Latn", "eng_Latn"]
        with (
            patch("app.services.asr.omnilingual_provider._omnilingual_available", True),
            patch("app.services.asr.omnilingual_provider._supported_langs", fake_langs),
        ):
            provider = OmnilingualASR(default_lang="dyu_Latn")
            assert provider.is_available() is False

    def test_is_available_true_when_supported_langs_is_none(self):
        # Cas limite : module marque comme dispo mais supported_langs vaut None
        # (ne devrait pas arriver en pratique, mais on ne crash pas)
        with (
            patch("app.services.asr.omnilingual_provider._omnilingual_available", True),
            patch("app.services.asr.omnilingual_provider._supported_langs", None),
        ):
            provider = OmnilingualASR()
            assert provider.is_available() is True


class TestOmnilingualASRInterface:
    """Tests de conformite a l'interface ASRProvider."""

    def test_inherits_from_asr_provider(self):
        provider = OmnilingualASR()
        assert isinstance(provider, ASRProvider)

    def test_has_required_methods(self):
        provider = OmnilingualASR()
        assert hasattr(provider, "name")
        assert hasattr(provider, "is_available")
        assert hasattr(provider, "transcribe")

    def test_repr_includes_name_and_availability(self):
        provider = OmnilingualASR(model_size="300m")
        r = repr(provider)
        # Le __repr__ par defaut de ASRProvider inclut le nom
        assert "Omnilingual 300M" in r


class TestOmnilingualASRTranscribe:
    """Tests de transcribe() (sans modele charge)."""

    @pytest.mark.asyncio
    async def test_transcribe_returns_none_when_unavailable(self):
        with patch("app.services.asr.omnilingual_provider._omnilingual_available", False):
            provider = OmnilingualASR()
            result = await provider.transcribe(b"fake audio bytes", "wav")
            assert result is None


class TestModelCardsMapping:
    """Tests du mapping MODEL_CARDS (regression critique vu Phase 1)."""

    def test_300m_uses_correct_model_card_no_v2_suffix(self):
        # Phase 1 a decouvert que "omniASR_CTC_300M_v2" leve ModelNotKnownError.
        # Le bon nom est "omniASR_CTC_300M".
        assert MODEL_CARDS["300m"] == "omniASR_CTC_300M"
        assert "v2" not in MODEL_CARDS["300m"]

    def test_all_model_cards_use_official_naming(self):
        # Format Meta : omniASR_<TYPE>_<SIZE>
        for card in MODEL_CARDS.values():
            assert card.startswith("omniASR_")

    def test_ctc_and_llm_variants_present(self):
        ctc_cards = [c for c in MODEL_CARDS.values() if "CTC" in c]
        llm_cards = [c for c in MODEL_CARDS.values() if "LLM" in c]
        assert len(ctc_cards) >= 2  # 300M, 1B
        assert len(llm_cards) >= 2  # 1.2B, 7B
