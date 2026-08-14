"""Tests des services opérationnels : météo, audio et historique."""
import asyncio
import os
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import _ffmpeg, audio_cleanup, conversation_history, tts_common
from app.services import weather


@pytest.fixture(autouse=True)
def reset_module_state():
    weather._weather_cache.clear()
    weather._forecast_cache.clear()
    _ffmpeg._ffmpeg_path = None
    _ffmpeg._loudnorm_supported = None
    audio_cleanup._cleanup_task = None
    conversation_history._conversation_history.clear()
    yield
    weather._weather_cache.clear()
    weather._forecast_cache.clear()
    _ffmpeg._ffmpeg_path = None
    _ffmpeg._loudnorm_supported = None
    if audio_cleanup._cleanup_task and not audio_cleanup._cleanup_task.done():
        audio_cleanup._cleanup_task.cancel()
    audio_cleanup._cleanup_task = None
    conversation_history._conversation_history.clear()


class TestWeather:
    def test_cache_set_hit_and_expiry(self):
        with patch("app.services.weather.time.time", return_value=1000):
            weather.set_cached_weather("ABIDJAN", {"temperature": 28})

        with patch("app.services.weather.time.time", return_value=1100):
            assert weather.get_cached_weather("abidjan") == {"temperature": 28}

        with patch(
            "app.services.weather.time.time",
            return_value=1000 + weather.CACHE_DURATION + 1,
        ):
            assert weather.get_cached_weather("Abidjan") is None

    @pytest.mark.asyncio
    async def test_get_weather_returns_cached_value_without_network(self):
        weather._weather_cache["abidjan"] = {
            "data": {"city": "Abidjan"},
            "timestamp": time.time(),
        }

        with patch(
            "app.services.weather.httpx.AsyncClient",
        ) as client_factory:
            result = await weather.get_weather("Abidjan")

        assert result == {"city": "Abidjan"}
        client_factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_weather_returns_none_for_unknown_city(self):
        with patch("app.services.weather.get_city", return_value=None):
            assert await weather.get_weather("Inconnue") is None

    @pytest.mark.asyncio
    async def test_get_weather_maps_successful_api_response_and_caches_it(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "current": {
                "temperature_2m": 33,
                "relative_humidity_2m": 70,
                "precipitation": 3,
                "weather_code": 61,
                "wind_speed_10m": 12,
            },
        }
        client = MagicMock()
        client.get = AsyncMock(return_value=response)
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=client)
        context.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.services.weather.get_city",
                return_value={
                    "name": "Bouaké",
                    "region": "Gbêkê",
                    "lat": 7.69,
                    "lon": -5.03,
                },
            ),
            patch(
                "app.services.weather.httpx.AsyncClient",
                return_value=context,
            ),
        ):
            result = await weather.get_weather("Bouaké")

        assert result["city"] == "Bouaké"
        assert result["weather_description"] == "Pluie légère"
        assert result["temperature"] == 33
        assert "Pluies modérées" in result["advice"]
        assert weather.get_cached_weather("bouaké") == result

    @pytest.mark.asyncio
    async def test_get_weather_handles_http_and_transport_errors(self):
        response = MagicMock(status_code=503)
        client = MagicMock()
        client.get = AsyncMock(return_value=response)
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=client)
        context.__aexit__ = AsyncMock(return_value=False)

        city = {"name": "Man", "region": "Tonkpi", "lat": 7.4, "lon": -7.5}
        with (
            patch("app.services.weather.get_city", return_value=city),
            patch(
                "app.services.weather.httpx.AsyncClient",
                return_value=context,
            ),
        ):
            assert await weather.get_weather("Man") is None

        context.__aenter__ = AsyncMock(side_effect=RuntimeError("network"))
        with (
            patch("app.services.weather.get_city", return_value=city),
            patch(
                "app.services.weather.httpx.AsyncClient",
                return_value=context,
            ),
        ):
            assert await weather.get_weather("Man") is None

    @pytest.mark.asyncio
    async def test_get_weather_forecast_tomorrow_returns_none_for_unknown_city(self):
        with patch("app.services.weather.get_city", return_value=None):
            assert await weather.get_weather_forecast_tomorrow("Inconnue") is None

    @pytest.mark.asyncio
    async def test_get_weather_forecast_tomorrow_maps_daily_index_1_and_caches_it(self):
        """index 0 = aujourd'hui, index 1 = demain (forecast_days=2) — verifie que
        c'est bien l'index 1 qui est utilise, pas l'index 0."""
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "daily": {
                "time": ["2026-08-14", "2026-08-15"],
                "weather_code": [0, 61],
                "temperature_2m_max": [30, 27],
                "temperature_2m_min": [22, 21],
                "precipitation_probability_max": [10, 80],
            },
        }
        client = MagicMock()
        client.get = AsyncMock(return_value=response)
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=client)
        context.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.services.weather.get_city",
                return_value={
                    "name": "Bouaké",
                    "region": "Gbêkê",
                    "lat": 7.69,
                    "lon": -5.03,
                },
            ),
            patch(
                "app.services.weather.httpx.AsyncClient",
                return_value=context,
            ),
        ):
            result = await weather.get_weather_forecast_tomorrow("Bouaké")

        assert result["city"] == "Bouaké"
        assert result["date"] == "2026-08-15"
        assert result["weather_code"] == 61
        assert result["weather_description"] == "Pluie légère"
        assert result["temperature_max"] == 27
        assert result["temperature_min"] == 21
        assert result["precipitation_probability"] == 80
        assert weather._get_cached_forecast("bouaké") == result

    @pytest.mark.asyncio
    async def test_get_weather_forecast_tomorrow_returns_cached_value_without_network(self):
        weather._forecast_cache["abidjan"] = {
            "data": {"city": "Abidjan", "date": "2026-08-15"},
            "timestamp": time.time(),
        }

        with patch("app.services.weather.httpx.AsyncClient") as client_factory:
            result = await weather.get_weather_forecast_tomorrow("Abidjan")

        assert result == {"city": "Abidjan", "date": "2026-08-15"}
        client_factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_weather_forecast_tomorrow_handles_missing_daily_data(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {"daily": {"time": ["2026-08-14"]}}  # 1 seul jour
        client = MagicMock()
        client.get = AsyncMock(return_value=response)
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=client)
        context.__aexit__ = AsyncMock(return_value=False)

        city = {"name": "Man", "region": "Tonkpi", "lat": 7.4, "lon": -7.5}
        with (
            patch("app.services.weather.get_city", return_value=city),
            patch(
                "app.services.weather.httpx.AsyncClient",
                return_value=context,
            ),
        ):
            assert await weather.get_weather_forecast_tomorrow("Man") is None

    @pytest.mark.asyncio
    async def test_get_weather_forecast_tomorrow_handles_http_and_transport_errors(self):
        response = MagicMock(status_code=503)
        client = MagicMock()
        client.get = AsyncMock(return_value=response)
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=client)
        context.__aexit__ = AsyncMock(return_value=False)

        city = {"name": "Man", "region": "Tonkpi", "lat": 7.4, "lon": -7.5}
        with (
            patch("app.services.weather.get_city", return_value=city),
            patch(
                "app.services.weather.httpx.AsyncClient",
                return_value=context,
            ),
        ):
            assert await weather.get_weather_forecast_tomorrow("Man") is None

        context.__aenter__ = AsyncMock(side_effect=RuntimeError("network"))
        with (
            patch("app.services.weather.get_city", return_value=city),
            patch(
                "app.services.weather.httpx.AsyncClient",
                return_value=context,
            ),
        ):
            assert await weather.get_weather_forecast_tomorrow("Man") is None

    @pytest.mark.parametrize(
        ("temperature", "precipitation", "code", "fragments"),
        [
            (36, 11, 0, ["Fortes pluies", "Chaleur intense"]),
            (32, 3, 0, ["Pluies modérées", "Température chaude"]),
            (18, 1, 0, ["Légères pluies", "Température fraîche"]),
            (25, 0, 95, ["Pas de pluie", "Orages prévus"]),
        ],
    )
    def test_generate_farming_advice(
        self,
        temperature,
        precipitation,
        code,
        fragments,
    ):
        advice = weather.generate_farming_advice(
            temperature,
            precipitation,
            code,
        )
        assert all(fragment in advice for fragment in fragments)

    @pytest.mark.asyncio
    async def test_get_all_cities_weather_keeps_available_results(self):
        cities = [{"name": f"Ville-{index}"} for index in range(12)]
        get_weather = AsyncMock(
            side_effect=lambda name: None if name == "Ville-1" else {"city": name}
        )
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=MagicMock())
        context.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.weather.get_all_cities", return_value=cities),
            patch("app.services.weather.get_weather", new=get_weather),
            patch(
                "app.services.weather.httpx.AsyncClient",
                return_value=context,
            ),
        ):
            results = await weather.get_all_cities_weather()

        assert len(results) == 9
        assert get_weather.await_count == 10


class TestFFmpeg:
    def test_find_ffmpeg_prefers_configured_path(self):
        completed = SimpleNamespace(returncode=0)
        with (
            patch.dict(os.environ, {"FFMPEG_PATH": "C:/tools/ffmpeg.exe"}),
            patch(
                "app.services._ffmpeg.subprocess.run",
                return_value=completed,
            ) as run,
        ):
            assert _ffmpeg.find_ffmpeg() == "C:/tools/ffmpeg.exe"

        run.assert_called_once()

    def test_find_ffmpeg_falls_back_to_path_and_reports_missing(self):
        with (
            patch.dict(os.environ, {"FFMPEG_PATH": "bad"}, clear=False),
            patch(
                "app.services._ffmpeg.subprocess.run",
                side_effect=[
                    FileNotFoundError(),
                    SimpleNamespace(returncode=0),
                ],
            ),
        ):
            assert _ffmpeg.find_ffmpeg() == "ffmpeg"

        with (
            patch.dict(os.environ, {"FFMPEG_PATH": ""}, clear=False),
            patch(
                "app.services._ffmpeg.subprocess.run",
                side_effect=subprocess.TimeoutExpired("ffmpeg", 5),
            ),
            pytest.raises(RuntimeError, match="introuvable"),
        ):
            _ffmpeg.find_ffmpeg()

    def test_get_ffmpeg_caches_resolution(self):
        with patch(
            "app.services._ffmpeg.find_ffmpeg",
            return_value="ffmpeg-test",
        ) as find:
            assert _ffmpeg.get_ffmpeg() == "ffmpeg-test"
            assert _ffmpeg.get_ffmpeg() == "ffmpeg-test"
        find.assert_called_once_with()

    def test_loudnorm_probe_is_cached_and_handles_error(self):
        with patch(
            "app.services._ffmpeg.subprocess.run",
            return_value=SimpleNamespace(stdout="... loudnorm ..."),
        ) as run:
            assert _ffmpeg._check_loudnorm_support("ffmpeg")
            assert _ffmpeg._check_loudnorm_support("ffmpeg")
        run.assert_called_once()

        _ffmpeg._loudnorm_supported = None
        with patch(
            "app.services._ffmpeg.subprocess.run",
            side_effect=RuntimeError("probe"),
        ):
            assert not _ffmpeg._check_loudnorm_support("ffmpeg")

    def test_wav_to_ogg_success_builds_loudnorm_command(self):
        completed = SimpleNamespace(returncode=0, stderr="")
        with (
            patch("app.services._ffmpeg.get_ffmpeg", return_value="ffmpeg"),
            patch(
                "app.services._ffmpeg._check_loudnorm_support",
                return_value=True,
            ),
            patch(
                "app.services._ffmpeg.subprocess.run",
                return_value=completed,
            ) as run,
            patch("app.services._ffmpeg.os.path.exists", return_value=True),
            patch("app.services._ffmpeg.os.path.getsize", return_value=128),
            patch("app.services._ffmpeg.os.remove") as remove,
        ):
            assert _ffmpeg.wav_to_ogg_normalized("source.wav", "target.ogg")

        assert "loudnorm=I=-16:TP=-1.5:LRA=11" in run.call_args.args[0]
        remove.assert_called_once_with("source.wav")

    @pytest.mark.parametrize(
        "side_effect",
        [subprocess.TimeoutExpired("ffmpeg", 60), RuntimeError("conversion")],
    )
    def test_wav_to_ogg_handles_conversion_errors(self, side_effect):
        with (
            patch("app.services._ffmpeg.get_ffmpeg", return_value="ffmpeg"),
            patch(
                "app.services._ffmpeg._check_loudnorm_support",
                return_value=False,
            ),
            patch(
                "app.services._ffmpeg.subprocess.run",
                side_effect=side_effect,
            ),
        ):
            assert not _ffmpeg.wav_to_ogg_normalized("source.wav", "target.ogg")

    def test_wav_to_ogg_handles_missing_ffmpeg(self):
        with patch(
            "app.services._ffmpeg.get_ffmpeg",
            side_effect=RuntimeError("missing"),
        ):
            assert not _ffmpeg.wav_to_ogg_normalized("source.wav", "target.ogg")


class TestTTSCommon:
    def test_primary_ffmpeg_conversion_short_circuits(self):
        with (
            patch(
                "app.services.tts_common.wav_to_ogg_normalized",
                return_value=True,
            ),
            patch.dict(sys.modules, {"pydub": MagicMock()}),
        ):
            assert tts_common.convert_wav_to_ogg("source.wav", "target.ogg")

    def test_pydub_fallback_uses_configured_ffmpeg(self):
        audio = MagicMock()
        audio_segment = MagicMock()
        audio_segment.from_wav.return_value = audio
        fake_pydub = MagicMock(AudioSegment=audio_segment)

        with (
            patch(
                "app.services.tts_common.wav_to_ogg_normalized",
                return_value=False,
            ),
            patch(
                "app.services.tts_common.find_ffmpeg",
                return_value="C:/tools/ffmpeg.exe",
            ),
            patch("app.services.tts_common.os.remove") as remove,
            patch.dict(sys.modules, {"pydub": fake_pydub}),
        ):
            assert tts_common.convert_wav_to_ogg("source.wav", "target.ogg")

        assert audio_segment.converter == "C:/tools/ffmpeg.exe"
        audio.export.assert_called_once_with(
            "target.ogg",
            format="ogg",
            codec="libopus",
            bitrate="64k",
        )
        remove.assert_called_once_with("source.wav")

    def test_pydub_fallback_reports_failure(self):
        with (
            patch(
                "app.services.tts_common.wav_to_ogg_normalized",
                return_value=False,
            ),
            patch.dict(sys.modules, {"pydub": None}),
        ):
            assert not tts_common.convert_wav_to_ogg("source.wav", "target.ogg")


class TestAudioCleanup:
    def test_cleanup_missing_directory(self, tmp_path):
        settings = SimpleNamespace(audio_output_dir=str(tmp_path / "missing"))
        with patch(
            "app.services.audio_cleanup.get_settings",
            return_value=settings,
        ):
            assert audio_cleanup.cleanup_old_audio() == 0

    def test_cleanup_removes_only_expired_supported_audio(self, tmp_path):
        old_ogg = tmp_path / "old.ogg"
        old_wav = tmp_path / "old.wav"
        recent_mp3 = tmp_path / "recent.mp3"
        ignored = tmp_path / "old.txt"
        for path in (old_ogg, old_wav, recent_mp3, ignored):
            path.write_bytes(b"audio")

        old_time = time.time() - ((audio_cleanup.MAX_AGE_DAYS + 1) * 86400)
        os.utime(old_ogg, (old_time, old_time))
        os.utime(old_wav, (old_time, old_time))
        os.utime(ignored, (old_time, old_time))

        settings = SimpleNamespace(audio_output_dir=str(tmp_path))
        with patch(
            "app.services.audio_cleanup.get_settings",
            return_value=settings,
        ):
            assert audio_cleanup.cleanup_old_audio() == 2

        assert not old_ogg.exists()
        assert not old_wav.exists()
        assert recent_mp3.exists()
        assert ignored.exists()

    @pytest.mark.asyncio
    async def test_scheduler_starts_and_stops_task(self):
        async def wait_forever():
            await asyncio.Event().wait()

        with (
            patch("app.services.audio_cleanup.cleanup_old_audio", return_value=3),
            patch(
                "app.services.audio_cleanup._cleanup_loop",
                new=wait_forever,
            ),
        ):
            audio_cleanup.start_cleanup_scheduler()
            task = audio_cleanup._cleanup_task
            assert task is not None
            audio_cleanup.stop_cleanup_scheduler()

        assert audio_cleanup._cleanup_task is None
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_cleanup_loop_runs_cleanup_after_sleep(self):
        with (
            patch(
                "app.services.audio_cleanup.asyncio.sleep",
                new=AsyncMock(
                    side_effect=[None, asyncio.CancelledError()],
                ),
            ),
            patch(
                "app.services.audio_cleanup.asyncio.to_thread",
                new=AsyncMock(return_value=1),
            ) as to_thread,
            pytest.raises(asyncio.CancelledError),
        ):
            await audio_cleanup._cleanup_loop()

        to_thread.assert_awaited_once_with(audio_cleanup.cleanup_old_audio)


class TestConversationHistory:
    def test_empty_user_is_ignored(self):
        conversation_history.add_message("", "user", "bonjour")
        assert conversation_history.get_history("") == []

    def test_history_is_trimmed_and_formatted(self):
        for index in range(conversation_history.MAX_HISTORY_LENGTH + 2):
            conversation_history.add_message(
                "farmer",
                "user" if index % 2 == 0 else "assistant",
                f"message-{index}",
            )

        history = conversation_history.get_history("farmer", max_messages=3)
        assert [item["content"] for item in history] == [
            "message-9",
            "message-10",
            "message-11",
        ]
        assert all("timestamp" not in item for item in history)
        assert conversation_history.get_history_for_deepseek(
            "farmer",
            2,
        ) == history[-2:]

    def test_expired_messages_are_removed(self):
        conversation_history._conversation_history["farmer"] = [
            {
                "role": "user",
                "content": "ancien",
                "timestamp": conversation_history.datetime.now()
                - conversation_history.timedelta(hours=25),
            },
            {
                "role": "assistant",
                "content": "récent",
                "timestamp": conversation_history.datetime.now(),
            },
        ]

        assert conversation_history.get_history("farmer") == [
            {"role": "assistant", "content": "récent"},
        ]

    def test_summary_clear_and_stats(self):
        conversation_history.add_message("farmer", "user", "Comment semer ?")
        conversation_history.add_message("farmer", "assistant", "Prépare le sol")

        summary = conversation_history.get_conversation_summary("farmer")
        assert "Agriculteur: Comment semer ?..." in summary
        assert "WOURI: Prépare le sol..." in summary
        assert conversation_history.get_conversation_summary("unknown") is None

        stats = conversation_history.get_stats()
        assert stats["active_users"] == 1
        assert stats["total_messages"] == 2

        conversation_history.clear_history("farmer")
        assert conversation_history.get_history("farmer") == []
