"""Tests des fichiers temporaires partagés par les providers ASR."""

from pathlib import Path

from app.services.asr import audio_utils


def test_prepared_wav_name_is_safe_for_temp_paths(tmp_path, monkeypatch):
    """Un nom lisible contenant "/" ne doit jamais créer un sous-dossier.

    `prepared_wav_16k` (#301) construit les chemins temporaires à partir d'un
    label lisible qui peut contenir des séparateurs (ex.
    "MMS-generic (Bambara/Dioula)"). `_safe_prefix` doit les neutraliser.
    """
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

    monkeypatch.setattr(audio_utils, "_TEMP_DIR", str(tmp_path))
    monkeypatch.setattr(audio_utils, "convert_to_wav_16k", fake_convert)

    with audio_utils.prepared_wav_16k(
        b"audio-test", "ogg", "MMS-generic (Bambara/Dioula)"
    ) as wav_path:
        assert Path(wav_path) == observed_paths["wav"]

    # Les deux fichiers temporaires (source + WAV) sont nettoyés à la sortie.
    assert list(tmp_path.iterdir()) == []


def test_prepared_wav_yields_none_on_conversion_failure(tmp_path, monkeypatch):
    """Si ffmpeg échoue, le contexte yield None et nettoie la source."""
    def failing_convert(input_path: str, output_path: str) -> bool:
        return False

    monkeypatch.setattr(audio_utils, "_TEMP_DIR", str(tmp_path))
    monkeypatch.setattr(audio_utils, "convert_to_wav_16k", failing_convert)

    with audio_utils.prepared_wav_16k(b"audio-test", "ogg", "Provider") as wav_path:
        assert wav_path is None

    assert list(tmp_path.iterdir()) == []


def test_prepared_wav_cleans_up_on_exception(tmp_path, monkeypatch):
    """Une exception dans le corps du contexte ne doit pas laisser de fichiers."""
    def fake_convert(input_path: str, output_path: str) -> bool:
        Path(output_path).write_bytes(b"wav")
        return True

    monkeypatch.setattr(audio_utils, "_TEMP_DIR", str(tmp_path))
    monkeypatch.setattr(audio_utils, "convert_to_wav_16k", fake_convert)

    class Boom(Exception):
        pass

    try:
        with audio_utils.prepared_wav_16k(b"audio-test", "ogg", "Provider"):
            raise Boom()
    except Boom:
        pass

    assert list(tmp_path.iterdir()) == []
