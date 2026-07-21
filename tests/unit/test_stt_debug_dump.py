"""
Tests pour le dump audio debug opt-in (fix PII audit 2026-07-21).

Bug corrigé : `transcribe_audio_bytes` copiait CHAQUE vocal utilisateur
dans un dossier debug par défaut (%TEMP%/wourri_debug_audio), jamais
nettoyé — accumulation illimitée de données personnelles (conformité
ARTCI). Le log écrivait aussi la transcription complète en clair.

Couvre :
    - WOURRI_DEBUG_AUDIO_DIR non défini (défaut) → AUCUN fichier debug écrit
    - WOURRI_DEBUG_AUDIO_DIR défini → dump dans le dossier indiqué (opt-in)
    - Le log de résultat ne contient pas le texte transcrit (longueur seule)
"""
from __future__ import annotations

import logging
from unittest.mock import patch

import pytest


def _fake_transcribe(temp_path, language):
    """Remplace transcribe_audio (évite de charger Whisper dans les tests)."""
    return {"text": "contenu personnel sensible", "language": language, "segments": []}


@pytest.mark.asyncio
async def test_pas_de_dump_par_defaut(tmp_path, monkeypatch):
    """Env var absente → aucun fichier debug créé nulle part."""
    from app.services import stt_whisper

    monkeypatch.delenv("WOURRI_DEBUG_AUDIO_DIR", raising=False)
    # Rediriger le tempdir vers tmp_path pour observer TOUT fichier créé
    monkeypatch.setattr(stt_whisper.tempfile, "gettempdir", lambda: str(tmp_path))

    with patch.object(stt_whisper, "WHISPER_AVAILABLE", True), \
         patch.object(stt_whisper, "transcribe_audio", _fake_transcribe):
        result = await stt_whisper.transcribe_audio_bytes(b"fake-ogg-bytes", "voix.ogg")

    assert result is not None
    # Le temp whisper_* est nettoyé (finally) et aucun dossier/fichier debug
    # ne doit exister : tmp_path doit être VIDE après l'appel.
    leftovers = list(tmp_path.iterdir())
    assert leftovers == [], f"Fichiers residuels inattendus: {leftovers}"


@pytest.mark.asyncio
async def test_dump_opt_in_quand_env_definie(tmp_path, monkeypatch):
    """Env var définie → une copie de l'audio est écrite dans le dossier."""
    from app.services import stt_whisper

    debug_dir = tmp_path / "debug_audio"
    monkeypatch.setenv("WOURRI_DEBUG_AUDIO_DIR", str(debug_dir))

    with patch.object(stt_whisper, "WHISPER_AVAILABLE", True), \
         patch.object(stt_whisper, "transcribe_audio", _fake_transcribe):
        result = await stt_whisper.transcribe_audio_bytes(b"fake-ogg-bytes", "voix.ogg")

    assert result is not None
    dumped = list(debug_dir.glob("audio_*.ogg"))
    assert len(dumped) == 1
    assert dumped[0].read_bytes() == b"fake-ogg-bytes"


@pytest.mark.asyncio
async def test_log_sans_texte_transcrit(tmp_path, monkeypatch, caplog):
    """Le log de succès n'expose pas le contenu transcrit (PII), juste la longueur."""
    from app.services import stt_whisper

    monkeypatch.delenv("WOURRI_DEBUG_AUDIO_DIR", raising=False)
    monkeypatch.setattr(stt_whisper.tempfile, "gettempdir", lambda: str(tmp_path))

    with patch.object(stt_whisper, "WHISPER_AVAILABLE", True), \
         patch.object(stt_whisper, "transcribe_audio", _fake_transcribe), \
         caplog.at_level(logging.INFO, logger="app.services.stt_whisper"):
        await stt_whisper.transcribe_audio_bytes(b"fake-ogg-bytes", "voix.ogg")

    logs = " ".join(r.getMessage() for r in caplog.records)
    assert "contenu personnel sensible" not in logs
    assert "26 chars" in logs  # len("contenu personnel sensible") == 26
