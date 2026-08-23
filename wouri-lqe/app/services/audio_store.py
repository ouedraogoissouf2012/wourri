"""Contrat de stockage des medias audio (ADR-0034).

Interface (DIP/OCP) : la production dependra de CE contrat, jamais du stockage
concret. Impl locale (volume `LQE_DATA_DIR/audio`) aujourd'hui ; un stockage
objet (S3...) pourra la remplacer sans toucher les appelants. L'usage reel de
l'audio arrive en P3 (#465) ; P0 pose le contrat + l'impl locale.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Protocol

from app.config import get_settings

_EXT = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
}


class AudioStore(Protocol):
    def save(self, data: bytes, *, mime: str) -> str:
        """Stocke l'audio et retourne une reference stable (`audio_url`)."""
        ...

    def load(self, ref: str) -> bytes: ...


class LocalAudioStore:
    """Stocke sous `LQE_DATA_DIR/audio/`. Reference = `audio/<uuid><ext>`."""

    def __init__(self, base: Path | None = None) -> None:
        self._base = base or (Path(get_settings().lqe_data_dir) / "audio")

    def save(self, data: bytes, *, mime: str) -> str:
        self._base.mkdir(parents=True, exist_ok=True)
        name = uuid.uuid4().hex + _EXT.get(mime, ".bin")
        (self._base / name).write_bytes(data)
        return f"audio/{name}"

    def load(self, ref: str) -> bytes:
        return (self._base / Path(ref).name).read_bytes()
