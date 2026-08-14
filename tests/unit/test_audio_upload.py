"""Tests des helpers de validation d'upload audio partagés (#312)."""
from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, UploadFile

from app.routers._audio_upload import (
    ALLOWED_EXTENSIONS,
    MAX_AUDIO_BYTES,
    read_audio_within_limits,
    resolve_extension,
)


def _upload(data: bytes, filename: str = "q.ogg") -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=filename)


class TestReadAudioWithinLimits:
    @pytest.mark.asyncio
    async def test_returns_bytes_for_valid_audio(self):
        audio = _upload(b"valid-audio")
        assert await read_audio_within_limits(audio) == b"valid-audio"

    @pytest.mark.asyncio
    async def test_rejects_oversized_with_413(self):
        audio = _upload(b"\x00" * (MAX_AUDIO_BYTES + 1))
        with pytest.raises(HTTPException) as exc:
            await read_audio_within_limits(audio)
        assert exc.value.status_code == 413
        assert "10 MB" in exc.value.detail

    @pytest.mark.asyncio
    async def test_rejects_empty_with_400(self):
        audio = _upload(b"")
        with pytest.raises(HTTPException) as exc:
            await read_audio_within_limits(audio)
        assert exc.value.status_code == 400
        assert "vide" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_read_failure_raises_400(self):
        broken = MagicMock(spec=UploadFile)
        broken.read = AsyncMock(side_effect=OSError("disk gone"))
        with pytest.raises(HTTPException) as exc:
            await read_audio_within_limits(broken)
        assert exc.value.status_code == 400
        assert "lecture" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_accepts_exactly_max_size(self):
        """La borne est stricte (> max rejette, == max passe)."""
        audio = _upload(b"\x00" * MAX_AUDIO_BYTES)
        assert len(await read_audio_within_limits(audio)) == MAX_AUDIO_BYTES


class TestResolveExtension:
    @pytest.mark.parametrize("filename,expected", [
        ("question.wav", "wav"),
        ("question.OGG", "ogg"),        # normalisation casse
        ("audio.mp3", "mp3"),
        ("clip.webm", "webm"),
        ("voice.m4a", "m4a"),
        ("archive.v2.wav", "wav"),      # multi-points → dernière extension
        ("question.backup.mp3", "mp3"),  # multi-points
        (".ogg", "ogg"),                # nom caché (point de tête)
    ])
    def test_known_extensions(self, filename, expected):
        assert resolve_extension(filename) == expected

    @pytest.mark.parametrize("filename", [
        "question.flac",   # extension inconnue
        "noextension",     # pas d'extension
        "audio.",          # point traînant → extension vide
        None,              # pas de nom
        "",                # nom vide
    ])
    def test_unknown_falls_back_to_ogg(self, filename):
        assert resolve_extension(filename) == "ogg"

    def test_all_allowed_extensions_resolve_to_themselves(self):
        for ext in ALLOWED_EXTENSIONS:
            assert resolve_extension(f"file.{ext}") == ext
