"""
Tests anti-hardcoding pour la correction STT (fix 2026-06-02).

Vérifie que `correct_stt_transcription` :
    - Utilise le registre `STT_CORRECTION_PROMPTS` (pas de hardcoding inline)
    - Skip silencieusement quand pas de prompt pour la langue (ENGLISH)
    - Applique le prompt FR pour FRENCH/DIOULA/BOTH (comportement historique)
    - Mapping ISO → Language enum dans le router stt.py

Mécanisme anti-régression structurel :
    - Toute langue de `SYSTEM_PROMPTS` DOIT avoir une entrée dans
      `STT_CORRECTION_PROMPTS` (str OU None — au moins déclarée).
      Si une langue future est ajoutée à `SYSTEM_PROMPTS` sans entrée
      dans `STT_CORRECTION_PROMPTS`, ce test échoue automatiquement.

Ref : feedback_no_hardcoding (règle gravée 2026-06-02)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.models.schemas import Language
from app.services.deepseek import correct_stt_transcription
from app.services.deepseek_prompts import (
    FRENCH_STT_CORRECTION,
    STT_CORRECTION_PROMPTS,
    SYSTEM_PROMPTS,
    get_stt_correction_prompt,
)


# ─────────────────────────────────────────────
# Registre STT_CORRECTION_PROMPTS
# ─────────────────────────────────────────────


class TestSttCorrectionPromptsRegistry:
    def test_french_dioula_both_use_french_correction_prompt(self):
        """FR / DIOULA / BOTH partagent le prompt FR (correction villes CI + agri)."""
        assert STT_CORRECTION_PROMPTS[Language.FRENCH] is FRENCH_STT_CORRECTION
        assert STT_CORRECTION_PROMPTS[Language.DIOULA] is FRENCH_STT_CORRECTION
        assert STT_CORRECTION_PROMPTS[Language.BOTH] is FRENCH_STT_CORRECTION

    def test_english_has_no_correction_prompt(self):
        """ENGLISH = None → skip correction (évite traduction EN→FR bug 2026-06-02)."""
        assert STT_CORRECTION_PROMPTS[Language.ENGLISH] is None

    def test_french_prompt_contains_critical_markers(self):
        """Le prompt FR doit conserver les marqueurs CI (villes, cultures, etc.)."""
        assert "Korhogo" in FRENCH_STT_CORRECTION
        assert "Bouaké" in FRENCH_STT_CORRECTION
        assert "igname" in FRENCH_STT_CORRECTION


class TestGetSttCorrectionPrompt:
    """Helper `get_stt_correction_prompt` avec fallback graceful."""

    def test_returns_french_prompt_for_french(self):
        assert get_stt_correction_prompt(Language.FRENCH) is FRENCH_STT_CORRECTION

    def test_returns_none_for_english(self):
        assert get_stt_correction_prompt(Language.ENGLISH) is None

    def test_returns_none_for_unknown_language_fallback(self):
        """Defense en profondeur : si une langue n'est pas dans le registre,
        retourne None au lieu de KeyError (graceful)."""
        class FakeLanguage:
            value = "klingon"

        assert get_stt_correction_prompt(FakeLanguage()) is None


# ─────────────────────────────────────────────
# correct_stt_transcription : routage selon language
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_correct_stt_returns_raw_text_for_english_no_prompt():
    """ENGLISH user → pas de prompt → correction skip → raw_text inchangé."""
    raw = "When I plant rice in Bouake"
    # Aucun appel httpx ne doit être fait (DeepSeek pas sollicité)
    with patch("httpx.AsyncClient") as mock_client:
        result = await correct_stt_transcription(raw, language=Language.ENGLISH)
    assert result == raw  # texte EN brut conservé tel quel
    mock_client.assert_not_called()


@pytest.mark.asyncio
async def test_correct_stt_uses_french_prompt_for_french_user():
    """FRENCH user → prompt FR du registre passé dans le payload DeepSeek."""
    raw = "Quand planter le riz a Bouake ?"

    # Mock de l'API DeepSeek pour capturer le payload système prompt envoyé
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json = lambda: {
        "choices": [{"message": {"content": "Quand planter le riz à Bouaké ?"}}]
    }

    captured_payload = {}

    async def mock_post(url, headers=None, json=None):
        captured_payload.update(json)
        return mock_response

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = mock_post
        mock_client_cls.return_value = mock_client

        # Mock settings pour avoir une clé DeepSeek "présente"
        with patch("app.services.deepseek.settings.deepseek_api_key", "fake-key"):
            result = await correct_stt_transcription(raw, language=Language.FRENCH)

    # Le system prompt envoyé doit contenir les marqueurs critique du prompt FR
    system_msg = captured_payload["messages"][0]
    assert system_msg["role"] == "system"
    assert "Korhogo" in system_msg["content"]
    assert "Bouaké" in system_msg["content"]
    assert "igname" in system_msg["content"]


@pytest.mark.asyncio
async def test_correct_stt_default_language_is_french_back_compat():
    """Sans argument `language` explicite, fallback FRENCH (compat appels existants)."""
    raw = "Quand planter ?"
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json = lambda: {"choices": [{"message": {"content": "Quand planter ?"}}]}

    captured_payload = {}

    async def mock_post(url, headers=None, json=None):
        captured_payload.update(json)
        return mock_response

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = mock_post
        mock_client_cls.return_value = mock_client
        with patch("app.services.deepseek.settings.deepseek_api_key", "fake-key"):
            await correct_stt_transcription(raw)  # pas de language → default

    # Default = FRENCH → marqueurs FR présents
    system_msg = captured_payload["messages"][0]
    assert "Korhogo" in system_msg["content"]


@pytest.mark.asyncio
async def test_correct_stt_text_too_short_skipped():
    """Texte < 3 chars → return raw_text (court-circuit avant tout appel API)."""
    with patch("httpx.AsyncClient") as mock_client:
        result = await correct_stt_transcription("a", language=Language.FRENCH)
    assert result == "a"
    mock_client.assert_not_called()


@pytest.mark.asyncio
async def test_correct_stt_no_api_key_returns_raw():
    """Pas de clé DeepSeek → raw_text retourné (graceful, pas crash)."""
    raw = "Quand planter le riz a Bouake ?"
    with patch("app.services.deepseek.settings.deepseek_api_key", ""):
        result = await correct_stt_transcription(raw, language=Language.FRENCH)
    assert result == raw


# ─────────────────────────────────────────────
# Mapping ISO → Language dans stt.py router
# ─────────────────────────────────────────────


class TestIsoLanguageMapping:
    """Vérifie le mapping ISO code → Language enum dans stt.py."""

    def test_fr_to_french(self):
        from app.routers.stt import _map_iso_to_language
        assert _map_iso_to_language("fr") == Language.FRENCH

    def test_en_to_english(self):
        from app.routers.stt import _map_iso_to_language
        assert _map_iso_to_language("en") == Language.ENGLISH

    def test_bam_dyu_to_dioula(self):
        from app.routers.stt import _map_iso_to_language
        assert _map_iso_to_language("bam") == Language.DIOULA
        assert _map_iso_to_language("dyu") == Language.DIOULA

    def test_unknown_code_fallback_french(self):
        """Code ISO inconnu → fallback FRENCH (compat existant, pas de crash)."""
        from app.routers.stt import _map_iso_to_language
        assert _map_iso_to_language("xx") == Language.FRENCH
        assert _map_iso_to_language("") == Language.FRENCH


# ─────────────────────────────────────────────
# Mécanisme anti-régression : couverture par langue
# ─────────────────────────────────────────────


class TestAntiRegressionLanguageCoverage:
    """Garantit que toute langue de SYSTEM_PROMPTS a une entrée dans
    STT_CORRECTION_PROMPTS (str OU None — au moins déclarée).

    Si une 5e langue future est ajoutée à SYSTEM_PROMPTS sans entrée
    correspondante dans STT_CORRECTION_PROMPTS, ce test échoue → impossible
    de merger en oubliant le registre STT.

    C'est l'équivalent côté Python du mécanisme i18n côté JavaScript
    (validateI18nCompleteness + tests parametrize) introduit en PR #288.
    """

    def test_all_system_prompt_languages_have_stt_entry(self):
        missing = []
        for lang in SYSTEM_PROMPTS.keys():
            if lang not in STT_CORRECTION_PROMPTS:
                missing.append(lang.value)
        assert not missing, (
            f"Langues présentes dans SYSTEM_PROMPTS mais absentes de "
            f"STT_CORRECTION_PROMPTS : {missing}. Ajouter une entrée "
            f"(str avec prompt OU None pour skip) dans deepseek_prompts.py."
        )

    @pytest.mark.parametrize(
        "lang",
        [Language.FRENCH, Language.DIOULA, Language.BOTH, Language.ENGLISH],
    )
    def test_each_language_has_valid_entry(self, lang):
        """Chaque langue doit avoir une entrée str non-vide OU None.
        Pas de chaîne vide acceptée (= bug silencieux possible)."""
        assert lang in STT_CORRECTION_PROMPTS, f"{lang.value} manque dans STT_CORRECTION_PROMPTS"
        entry = STT_CORRECTION_PROMPTS[lang]
        assert entry is None or (isinstance(entry, str) and len(entry) > 50), (
            f"Entrée {lang.value} invalide : doit être None (skip) ou str non-vide (prompt)"
        )
