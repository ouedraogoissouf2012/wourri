"""Intégration du pipeline ChatService avec frontières externes mockées."""
from unittest.mock import AsyncMock, patch

import pytest

from app.models.schemas import Language
from app.services.chat_service import ChatService


@pytest.mark.asyncio
async def test_chat_service_runs_nlu_ivr_deepseek_and_tts_pipeline():
    """Un miss IVR doit poursuivre vers DeepSeek puis le TTS Dioula."""
    weather = {
        "temperature": 29,
        "humidity": 74,
        "weather_description": "nuageux",
    }

    with (
        patch(
            "app.services.weather.get_weather",
            new=AsyncMock(return_value=weather),
        ) as get_weather,
        patch(
            "app.services.corpus_service.chercher_reponse_ivr",
            return_value=None,
        ) as search_ivr,
        patch(
            "app.services.deepseek.chat_with_deepseek",
            new=AsyncMock(return_value="Sème le riz au début des pluies."),
        ) as deepseek,
        patch(
            "app.services.tts_dioula.synthesize_dioula",
            new=AsyncMock(
                return_value=(
                    "/static/audio/pipeline-48.ogg",
                    "Sanji daminɛ na, i ka malo sɛnɛ.",
                )
            ),
        ) as synthesize,
    ):
        result = await ChatService().process(
            message="Je veux cultiver du riz",
            city="Abidjan",
            language=Language.DIOULA,
            bambara_text="n bɛ malo sɛnɛ",
            include_audio=True,
            user_id="farmer-pipeline-48",
        )

    assert result.response == "Sème le riz au début des pluies."
    assert result.response_dioula == "Sanji daminɛ na, i ka malo sɛnɛ."
    assert result.audio_url == "/static/audio/pipeline-48.ogg"
    assert result.audio_language == "Dioula"
    assert result.city == "Abidjan"
    assert result.language == "dioula"
    assert result.meta == {
        "intent": "QUESTION_SAISON_PLANTATION",
        "cultures": ["CULTURE_RIZ"],
        "source": "deepseek_open",
    }

    get_weather.assert_awaited_once_with("Abidjan")
    assert search_ivr.call_count >= 2
    assert any(
        call.args[0] == "QUESTION_SAISON_PLANTATION"
        and call.args[1] == ["CULTURE_RIZ"]
        for call in search_ivr.call_args_list
    )
    deepseek.assert_awaited_once()
    deepseek_call = deepseek.await_args.kwargs
    assert deepseek_call["language"] == Language.DIOULA
    assert deepseek_call["user_id"] == "farmer-pipeline-48"
    assert "riz" in deepseek_call["message"]
    synthesize.assert_awaited_once_with("Sème le riz au début des pluies.")
