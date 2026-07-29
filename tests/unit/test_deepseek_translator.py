"""Tests du traducteur DeepSeek avec ancres, sans appel réseau."""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.translation.deepseek_translator import (
    build_anchors,
    build_deepseek_translation_prompt,
    extract_anchor_candidates,
    score_back_translation,
    translate_fr_to_bambara_deepseek,
    translate_fr_to_bambara_with_validation,
)
from app.services.translation.interfaces import DictionaryEntry


def test_anchor_candidates_prioritize_agricultural_words_and_filter_stop_words():
    candidates = extract_anchor_candidates(
        "Bonjour, je veux planter le maïs dans mon grand champ rapidement."
    )

    assert candidates[:3] == ["champ", "maïs", "planter"]
    assert "bonjour" not in candidates
    assert "dans" not in candidates


def test_anchor_candidates_are_limited_to_fifteen():
    text = " ".join(f"important{index}" for index in range(20))
    assert len(extract_anchor_candidates(text)) == 15


def test_build_anchors_uses_direct_and_unaccented_entries():
    index = {
        "maïs": DictionaryEntry(word="maïs", translations=["kaba"]),
        "recolter": DictionaryEntry(word="recolter", translations=["lajɛ"]),
        "vide": DictionaryEntry(word="vide", translations=[""]),
    }

    anchors = build_anchors(["maïs", "récolter", "vide", "inconnu"], index)

    assert anchors == {"maïs": "kaba", "récolter": "lajɛ"}


def test_prompt_includes_anchors_and_translation_rules():
    prompt = build_deepseek_translation_prompt(
        "Planter le maïs",
        {"maïs": "kaba", "planter": "sɛnɛ"},
    )

    assert "maïs → kaba" in prompt
    assert "planter → sɛnɛ" in prompt
    assert 'Texte à traduire: "Planter le maïs"' in prompt


def test_prompt_without_anchors_omits_mandatory_section():
    prompt = build_deepseek_translation_prompt("Texte simple", {})
    assert "MOTS-CLÉS OBLIGATOIRES" not in prompt


@pytest.mark.parametrize(
    ("original", "back_translation", "expected"),
    [
        ("", "du riz", 0.0),
        ("du riz", "", 0.0),
        ("oui", "oui", 0.5),
        ("Planter le riz au champ", "Planter le riz", 0.5),
        ("Planter le riz", "Planter le riz au champ", 1.0),
    ],
)
def test_back_translation_score(original, back_translation, expected):
    assert score_back_translation(original, back_translation) == pytest.approx(expected)


def _mock_http_client(response=None, side_effect=None):
    client = MagicMock()
    client.post = AsyncMock(return_value=response, side_effect=side_effect)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=False)
    return context, client


@pytest.mark.asyncio
async def test_deepseek_translation_requires_api_key():
    result = await translate_fr_to_bambara_deepseek(
        "Planter le riz",
        "",
        "https://api.example.test",
        "deepseek-test",
    )
    assert result == (None, 0.0)


@pytest.mark.asyncio
async def test_deepseek_translation_posts_anchored_prompt_and_cleans_quotes():
    response = MagicMock(status_code=200)
    response.json.return_value = {
        "choices": [{"message": {"content": '"I ka malo sɛnɛ"'}}],
    }
    context, client = _mock_http_client(response=response)
    index = {
        "riz": DictionaryEntry(word="riz", translations=["malo"]),
        "planter": DictionaryEntry(word="planter", translations=["sɛnɛ"]),
    }

    with patch(
        "app.services.translation.deepseek_translator.httpx.AsyncClient",
        return_value=context,
    ):
        result = await translate_fr_to_bambara_deepseek(
            "Planter le riz",
            "secret",
            "https://api.example.test",
            "deepseek-test",
            index,
        )

    assert result == ("I ka malo sɛnɛ", 0.6)
    post = client.post.await_args
    assert post.args[0] == "https://api.example.test/chat/completions"
    assert post.kwargs["headers"]["Authorization"] == "Bearer secret"
    assert "riz → malo" in post.kwargs["json"]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_deepseek_translation_handles_http_error():
    response = MagicMock(status_code=429)
    context, _ = _mock_http_client(response=response)

    with patch(
        "app.services.translation.deepseek_translator.httpx.AsyncClient",
        return_value=context,
    ):
        result = await translate_fr_to_bambara_deepseek(
            "Planter le riz",
            "secret",
            "https://api.example.test",
            "deepseek-test",
        )

    assert result == (None, 0.0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [httpx.TimeoutException("timeout"), RuntimeError("broken response")],
)
async def test_deepseek_translation_handles_transport_errors(error):
    context, _ = _mock_http_client(side_effect=error)

    with patch(
        "app.services.translation.deepseek_translator.httpx.AsyncClient",
        return_value=context,
    ):
        result = await translate_fr_to_bambara_deepseek(
            "Planter le riz",
            "secret",
            "https://api.example.test",
            "deepseek-test",
        )

    assert result == (None, 0.0)


@pytest.mark.asyncio
async def test_validated_translation_passthrough_when_deepseek_fails():
    with patch(
        "app.services.translation.deepseek_translator.translate_fr_to_bambara_deepseek",
        new=AsyncMock(return_value=(None, 0.0)),
    ):
        result = await translate_fr_to_bambara_with_validation(
            "Planter le riz",
            "secret",
            "https://api.example.test",
            "deepseek-test",
        )

    assert result == ("Planter le riz", 0.0, "passthrough")


@pytest.mark.asyncio
async def test_validated_translation_accepts_matching_back_translation():
    service = MagicMock()
    service.translate.return_value.text = "Planter le riz"

    with (
        patch(
            "app.services.translation.deepseek_translator.translate_fr_to_bambara_deepseek",
            new=AsyncMock(return_value=("I ka malo sɛnɛ", 0.6)),
        ),
        patch(
            "app.services.translation.get_translation_service",
            return_value=service,
        ),
    ):
        result = await translate_fr_to_bambara_with_validation(
            "Planter le riz",
            "secret",
            "https://api.example.test",
            "deepseek-test",
        )

    assert result == ("I ka malo sɛnɛ", 0.8, "deepseek+anchors+backval")


@pytest.mark.asyncio
async def test_validated_translation_rejects_low_back_translation_score():
    service = MagicMock()
    service.translate.return_value.text = "météo sans rapport"

    with (
        patch(
            "app.services.translation.deepseek_translator.translate_fr_to_bambara_deepseek",
            new=AsyncMock(return_value=("texte bambara", 0.6)),
        ),
        patch(
            "app.services.translation.get_translation_service",
            return_value=service,
        ),
    ):
        result = await translate_fr_to_bambara_with_validation(
            "Planter le riz",
            "secret",
            "https://api.example.test",
            "deepseek-test",
        )

    assert result == ("Planter le riz", 0.0, "passthrough")


@pytest.mark.asyncio
async def test_validated_translation_keeps_unvalidated_result_on_back_error():
    service = MagicMock()
    service.translate.side_effect = RuntimeError("back translation unavailable")

    with (
        patch(
            "app.services.translation.deepseek_translator.translate_fr_to_bambara_deepseek",
            new=AsyncMock(return_value=("texte bambara", 0.6)),
        ),
        patch(
            "app.services.translation.get_translation_service",
            return_value=service,
        ),
    ):
        result = await translate_fr_to_bambara_with_validation(
            "Planter le riz",
            "secret",
            "https://api.example.test",
            "deepseek-test",
        )

    assert result == ("texte bambara", pytest.approx(0.42), "deepseek+anchors")
