"""
Tests pour feature flags performance ML (issue #42 T2/T3/T4/T5).

Couvre :
    - Settings : 5 nouveaux flags lus + defaults sains
    - is_whisper_enabled / is_mms_dyu_enabled / is_mms_bam_enabled : combinent
      import-check + flag .env
    - get_whisper_model / get_tts_model_dioula / get_tts_model retournent None
      quand le flag est désactivé (économise RAM sans crash)
    - /api/health/memory : retourne process info + models loaded + flags

Anti-régression : les defaults (tous True) préservent le comportement
historique. Tout test qui dépend du chargement réel reste vert.

Ref : issue #42, feedback_no_hardcoding (flags via Pydantic Settings).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────
# Settings : 5 nouveaux flags
# ─────────────────────────────────────────────


class TestPerfFeatureFlagsSettings:
    """Vérifie les defaults Pydantic Settings (config.py)."""

    def _isolated_settings(self, monkeypatch):
        """Construit Settings en ignorant le .env du dev local."""
        for var in (
            "ENABLE_WHISPER",
            "ENABLE_MMS_DYU",
            "ENABLE_MMS_BAM",
            "PRELOAD_TTS_DIOULA",
            "PRELOAD_TTS_BAMBARA",
        ):
            monkeypatch.delenv(var, raising=False)
        from app.config import Settings
        return Settings(_env_file=None)

    def test_default_enable_whisper_true(self, monkeypatch):
        s = self._isolated_settings(monkeypatch)
        assert s.enable_whisper is True

    def test_default_enable_mms_dyu_true(self, monkeypatch):
        s = self._isolated_settings(monkeypatch)
        assert s.enable_mms_dyu is True

    def test_default_enable_mms_bam_true(self, monkeypatch):
        s = self._isolated_settings(monkeypatch)
        assert s.enable_mms_bam is True

    def test_default_preload_tts_dioula_true(self, monkeypatch):
        s = self._isolated_settings(monkeypatch)
        assert s.preload_tts_dioula is True

    def test_default_preload_tts_bambara_true(self, monkeypatch):
        s = self._isolated_settings(monkeypatch)
        assert s.preload_tts_bambara is True

    def test_env_var_disables_whisper(self, monkeypatch):
        monkeypatch.setenv("ENABLE_WHISPER", "false")
        from app.config import Settings
        s = Settings(_env_file=None)
        assert s.enable_whisper is False

    def test_env_var_disables_mms_dyu(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MMS_DYU", "false")
        from app.config import Settings
        s = Settings(_env_file=None)
        assert s.enable_mms_dyu is False


# ─────────────────────────────────────────────
# is_xxx_enabled : combinaison import + flag
# ─────────────────────────────────────────────


class TestIsWhisperEnabled:
    """Vérifie is_whisper_enabled (stt_whisper.py)."""

    def test_returns_true_when_import_ok_and_flag_true(self):
        from app.services.stt_whisper import is_whisper_enabled
        with patch("app.services.stt_whisper.WHISPER_AVAILABLE", True), \
             patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.enable_whisper = True
            assert is_whisper_enabled() is True

    def test_returns_false_when_flag_disabled(self):
        from app.services.stt_whisper import is_whisper_enabled
        with patch("app.services.stt_whisper.WHISPER_AVAILABLE", True), \
             patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.enable_whisper = False
            assert is_whisper_enabled() is False

    def test_returns_false_when_import_unavailable(self):
        from app.services.stt_whisper import is_whisper_enabled
        with patch("app.services.stt_whisper.WHISPER_AVAILABLE", False):
            # Même avec enable_whisper=True, si pas installé → False
            assert is_whisper_enabled() is False


class TestIsMmsDyuEnabled:
    """Vérifie is_mms_dyu_enabled (tts_dioula.py)."""

    def test_returns_true_when_torch_ok_and_flag_true(self):
        from app.services.tts_dioula import is_mms_dyu_enabled
        with patch("app.services.tts_dioula.TORCH_AVAILABLE", True), \
             patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.enable_mms_dyu = True
            assert is_mms_dyu_enabled() is True

    def test_returns_false_when_flag_disabled(self):
        from app.services.tts_dioula import is_mms_dyu_enabled
        with patch("app.services.tts_dioula.TORCH_AVAILABLE", True), \
             patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.enable_mms_dyu = False
            assert is_mms_dyu_enabled() is False

    def test_returns_false_when_torch_unavailable(self):
        from app.services.tts_dioula import is_mms_dyu_enabled
        with patch("app.services.tts_dioula.TORCH_AVAILABLE", False):
            assert is_mms_dyu_enabled() is False


class TestIsMmsBamEnabled:
    """Vérifie is_mms_bam_enabled (tts_bambara.py)."""

    def test_returns_true_when_torch_ok_and_flag_true(self):
        from app.services.tts_bambara import is_mms_bam_enabled
        with patch("app.services.tts_bambara.TORCH_AVAILABLE", True), \
             patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.enable_mms_bam = True
            assert is_mms_bam_enabled() is True

    def test_returns_false_when_flag_disabled(self):
        from app.services.tts_bambara import is_mms_bam_enabled
        with patch("app.services.tts_bambara.TORCH_AVAILABLE", True), \
             patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.enable_mms_bam = False
            assert is_mms_bam_enabled() is False


# ─────────────────────────────────────────────
# get_xxx_model : respect du flag (return None si désactivé)
# ─────────────────────────────────────────────


class TestGetModelRespectsFlag:
    """Vérifie que get_xxx_model retourne None si désactivé via flag."""

    def test_get_whisper_model_returns_none_when_disabled(self):
        from app.services.stt_whisper import get_whisper_model
        with patch("app.services.stt_whisper.is_whisper_enabled", return_value=False):
            assert get_whisper_model() is None

    def test_get_tts_model_dioula_returns_none_when_disabled(self):
        from app.services.tts_dioula import get_tts_model_dioula
        with patch("app.services.tts_dioula.is_mms_dyu_enabled", return_value=False):
            result = get_tts_model_dioula()
        assert result == (None, None)

    def test_get_tts_model_bambara_returns_none_when_disabled(self):
        from app.services.tts_bambara import get_tts_model
        with patch("app.services.tts_bambara.is_mms_bam_enabled", return_value=False):
            result = get_tts_model()
        assert result == (None, None)


# ─────────────────────────────────────────────
# /api/health/memory endpoint
# ─────────────────────────────────────────────


class TestHealthMemoryEndpoint:
    """Vérifie l'endpoint /api/health/memory (issue #42 T5)."""

    @pytest.mark.asyncio
    async def test_returns_expected_structure(self):
        from app.routers.health_memory import get_memory_status
        result = await get_memory_status()
        assert "process" in result
        assert "models_loaded" in result
        assert "models_count" in result
        assert "feature_flags" in result

    @pytest.mark.asyncio
    async def test_feature_flags_all_present(self):
        from app.routers.health_memory import get_memory_status
        result = await get_memory_status()
        flags = result["feature_flags"]
        assert "enable_whisper" in flags
        assert "enable_mms_dyu" in flags
        assert "enable_mms_bam" in flags
        assert "preload_tts_dioula" in flags
        assert "preload_tts_bambara" in flags

    @pytest.mark.asyncio
    async def test_process_has_rss_vms_keys(self):
        from app.routers.health_memory import get_memory_status
        result = await get_memory_status()
        assert "rss_mb" in result["process"]
        assert "vms_mb" in result["process"]

    @pytest.mark.asyncio
    async def test_models_count_consistent_with_loaded_list(self):
        from app.routers.health_memory import get_memory_status
        result = await get_memory_status()
        assert result["models_count"] == len(result["models_loaded"])

    @pytest.mark.asyncio
    async def test_psutil_failure_graceful(self):
        """Si psutil échoue, rss/vms sont None mais pas de crash."""
        from app.routers import health_memory
        with patch.object(health_memory, "_get_process_memory_mb",
                          return_value={"rss_mb": None, "vms_mb": None}):
            result = await health_memory.get_memory_status()
        assert result["process"]["rss_mb"] is None
        assert result["process"]["vms_mb"] is None


# ─────────────────────────────────────────────
# Anti-régression : settings export les flags
# ─────────────────────────────────────────────


class TestAntiRegressionSettingsExport:
    """Garantit que les 5 flags sont accessibles via get_settings() — anti-
    régression si quelqu'un les renomme ou les supprime."""

    @pytest.mark.parametrize("flag", [
        "enable_whisper",
        "enable_mms_dyu",
        "enable_mms_bam",
        "preload_tts_dioula",
        "preload_tts_bambara",
    ])
    def test_flag_accessible_via_settings(self, flag):
        from app.config import get_settings
        s = get_settings()
        assert hasattr(s, flag), f"Flag {flag} manque dans Settings (issue #42)"
        assert isinstance(getattr(s, flag), bool), f"Flag {flag} doit etre bool"
