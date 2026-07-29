"""Contrats de la cascade dictionnaire → NLLB du service de traduction."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.translation.interfaces import Direction, TranslationResult
from app.services.translation.translation_service import TranslationService


@pytest.fixture
def translation_service():
    """Service réel sur les dictionnaires versionnés, sans chargement NLLB."""
    dictionaries_dir = Path(__file__).resolve().parents[2] / "dictionnaires"
    service = TranslationService(str(dictionaries_dir))

    dictionary_strategy = next(
        strategy
        for strategy in service._strategies
        if strategy.name == "dictionnaire"
    )
    nllb_strategy = MagicMock()
    nllb_strategy.name = "nllb"
    nllb_strategy.priority = 3
    service._strategies = [dictionary_strategy, nllb_strategy]
    service._nllb = nllb_strategy
    return service, nllb_strategy


def test_dictionary_repository_finds_validated_phrase(translation_service):
    """Une phrase validée est retrouvée malgré casse et ponctuation."""
    service, nllb = translation_service

    translated = service.translate_exact_phrase(
        "I NI CE !",
        Direction.BAM_TO_FR,
    )

    assert translated == "Merci"
    nllb.translate.assert_not_called()


def test_high_confidence_dictionary_result_stops_chain(translation_service):
    """Une traduction exacte du dictionnaire ne doit jamais appeler NLLB."""
    service, nllb = translation_service

    result = service.translate("i ni sogoma", Direction.BAM_TO_FR)

    assert result.text == "Bonjour"
    assert result.strategy_used == "dictionnaire"
    assert result.confidence == 1.0
    nllb.translate.assert_not_called()


def test_unknown_phrase_falls_back_to_nllb(translation_service):
    """Une phrase absente du dictionnaire passe à la stratégie NLLB."""
    service, nllb = translation_service
    nllb.translate.return_value = TranslationResult(
        text="traduction générée",
        source_text="expression totalement inconnue xyz",
        direction=Direction.BAM_TO_FR,
        strategy_used="nllb",
        confidence=0.5,
        words_total=4,
    )

    result = service.translate(
        "expression totalement inconnue xyz",
        Direction.BAM_TO_FR,
    )

    assert result.text == "traduction générée"
    assert result.strategy_used == "nllb"
    nllb.translate.assert_called_once_with(
        "expression totalement inconnue xyz",
        Direction.BAM_TO_FR,
    )
