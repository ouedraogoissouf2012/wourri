"""Tests des fichiers temporaires partagés par les providers ASR."""

from pathlib import Path

import pytest

from app.services.asr import audio_utils


@pytest.mark.asyncio
async def test_provider_name_is_safe_for_temp_paths(tmp_path, monkeypatch):
    """Un nom lisible contenant "/" ne doit jamais créer un sous-dossier."""
    observed_paths: dict[str, Path] = {}

    def fake_convert(input_path: str, output_path: str) -> bool:
        source = Path(input_path)
        wav = Path(output_path)
        observed_paths["source"] = source
        observed_paths["wav"] = wav

        assert source.parent == tmp_path
        assert wav.parent == tmp_path
        assert source.name.startswith("mms_generic_bambara_dioula_")
        assert source.read_bytes() == b"audio-test"

        wav.write_bytes(b"wav-test")
        return True

    def fake_transcribe(wav_path: str) -> str:
        assert Path(wav_path) == observed_paths["wav"]
        return "kaba sɛnɛ wagati"

    monkeypatch.setattr(audio_utils, "_TEMP_DIR", str(tmp_path))
    monkeypatch.setattr(audio_utils, "convert_to_wav_16k", fake_convert)

    result = await audio_utils.transcribe_with_temp_files(
        b"audio-test",
        "ogg",
        fake_transcribe,
        "MMS-generic (Bambara/Dioula)",
    )

    assert result == "kaba sɛnɛ wagati"
    assert list(tmp_path.iterdir()) == []
