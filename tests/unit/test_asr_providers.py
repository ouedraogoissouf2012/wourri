"""Tests des adapters ASR réels sans charger leurs modèles ML."""
import contextlib
import sys
from unittest.mock import MagicMock, patch

import pytest

from app.services.asr import mms_dyu_provider, mms_generic_provider


class TestMMSDyuProvider:
    def test_availability_requires_torch_and_adapter(self):
        provider = mms_dyu_provider.MMSDyuASR()
        adapter_path = MagicMock()
        adapter_path.exists.return_value = True

        with (
            patch.object(mms_dyu_provider, "_torch_available", True),
            patch.object(mms_dyu_provider, "ADAPTER_PATH", adapter_path),
        ):
            assert provider.name == "MMS-dyu"
            assert provider.is_available()

        with patch.object(mms_dyu_provider, "_torch_available", False):
            assert not provider.is_available()

    @pytest.mark.asyncio
    async def test_transcribe_converts_once_then_delegates_to_transcribe_wav(self):
        """#301 : transcribe(bytes) convertit UNE fois puis appelle transcribe_wav."""
        provider = mms_dyu_provider.MMSDyuASR()

        @contextlib.contextmanager
        def fake_prepared(audio_bytes, file_extension, label):
            assert audio_bytes == b"audio"
            assert file_extension == "ogg"
            yield "/tmp/prepared_16k.wav"

        with (
            patch.object(provider, "is_available", return_value=True),
            patch.object(
                provider, "transcribe_wav", return_value="  malo sɛnɛ  "
            ) as transcribe_wav,
            patch(
                "app.services.asr.audio_utils.prepared_wav_16k", fake_prepared
            ),
        ):
            result = await provider.transcribe(b"audio", "ogg")

        assert result == "  malo sɛnɛ  "
        transcribe_wav.assert_called_once_with("/tmp/prepared_16k.wav")

    @pytest.mark.asyncio
    async def test_transcribe_returns_none_when_unavailable(self):
        provider = mms_dyu_provider.MMSDyuASR()
        with patch.object(provider, "is_available", return_value=False):
            assert await provider.transcribe(b"audio") is None

    def test_transcribe_wav_decodes_logits(self):
        provider = mms_dyu_provider.MMSDyuASR()
        model = MagicMock()
        model.return_value.logits = "logits"
        processor = MagicMock()
        processor.return_value = {"input_values": "samples"}
        processor.batch_decode.return_value = ["  i ni ce  "]
        fake_torch = MagicMock()
        fake_torch.argmax.return_value = "predicted-ids"
        fake_librosa = MagicMock()
        fake_librosa.load.return_value = ([0.1, -0.1], 16000)

        with (
            patch.object(provider, "_get_model", return_value=(model, processor)),
            patch.object(mms_dyu_provider, "_torch", fake_torch),
            patch.dict(sys.modules, {"librosa": fake_librosa}),
        ):
            result = provider.transcribe_wav("question.wav")

        assert result == "i ni ce"
        fake_librosa.load.assert_called_once_with("question.wav", sr=16000)
        processor.assert_called_once_with(
            [0.1, -0.1],
            sampling_rate=16000,
            return_tensors="pt",
        )

    def test_transcribe_wav_handles_missing_model_and_inference_error(self):
        provider = mms_dyu_provider.MMSDyuASR()
        with patch.object(provider, "_get_model", return_value=None):
            assert provider.transcribe_wav("question.wav") is None

        with (
            patch.object(provider, "_get_model", side_effect=RuntimeError("model")),
            pytest.raises(RuntimeError, match="model"),
        ):
            provider.transcribe_wav("question.wav")


class TestAdapterPathResolution:
    """Tests de garde NON mockés (#358) : le bug historique était un chemin
    ADAPTER_PATH résolvant vers app/modeles_manuels/ (inexistant) → le seul
    modèle ASR fine-tuné dioula CI n'a jamais servi, silencieusement, pendant
    4 mois — et les tests mockés ci-dessus ne pouvaient pas le voir.
    """

    @pytest.mark.skipif(
        "MMS_DYU_ADAPTER_PATH" in __import__("os").environ,
        reason="chemin surchargé par env var — le test vérifie le DÉFAUT",
    )
    def test_adapter_path_resolves_to_repo_root_modeles_manuels(self):
        """Détecte tout off-by-one de .parent sans dépendre du modèle sur disque."""
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]  # tests/unit/ -> wouri-api/
        expected = repo_root / "modeles_manuels" / "mms-dioula-adapter"
        assert mms_dyu_provider.ADAPTER_PATH.resolve() == expected

    @pytest.mark.skipif(
        not mms_dyu_provider.ADAPTER_PATH.exists(),
        reason="adapter absent du disque (CI) — test de cohérence locale uniquement",
    )
    def test_adapter_dir_contains_loadable_wav2vec2_files(self):
        """Quand l'adapter est présent, il doit être réellement chargeable :
        config Wav2Vec2ForCTC + fichiers processor (le dossier n'a contenu que
        model.safetensors pendant des mois — chargement impossible)."""
        import json

        adapter = mms_dyu_provider.ADAPTER_PATH
        for required in ("config.json", "vocab.json", "tokenizer_config.json"):
            assert (adapter / required).is_file(), f"{required} manquant"
        cfg = json.loads((adapter / "config.json").read_text(encoding="utf-8"))
        assert cfg.get("architectures") == ["Wav2Vec2ForCTC"]
        tok = json.loads(
            (adapter / "tokenizer_config.json").read_text(encoding="utf-8")
        )
        assert tok.get("target_lang") == "dyu"


class TestMMSGenericProvider:
    def test_name_language_and_availability(self):
        provider = mms_generic_provider.MMSGenericASR("ati")
        assert provider.name == "MMS-generic (Attié)"

        provider.set_language("bam")
        assert provider.name == "MMS-generic (Bambara/Dioula)"

        with patch.object(mms_generic_provider, "_torch_available", True):
            assert provider.is_available()

    def test_transcribe_wav_rejects_unknown_language(self):
        """Une langue hors IVORIAN_ASR_LANGUAGES → None (garde déplacée dans
        transcribe_wav avec le refactor #301)."""
        provider = mms_generic_provider.MMSGenericASR("unknown")
        assert provider.transcribe_wav("question.wav") is None

    @pytest.mark.asyncio
    async def test_transcribe_converts_once_then_delegates_to_transcribe_wav(self):
        """#301 : transcribe(bytes) convertit UNE fois puis appelle transcribe_wav."""
        provider = mms_generic_provider.MMSGenericASR("ati")

        @contextlib.contextmanager
        def fake_prepared(audio_bytes, file_extension, label):
            assert audio_bytes == b"audio"
            assert file_extension == "mp3"
            yield "/tmp/prepared_16k.wav"

        with (
            patch.object(provider, "is_available", return_value=True),
            patch.object(
                provider, "transcribe_wav", return_value="réponse attié"
            ) as transcribe_wav,
            patch(
                "app.services.asr.audio_utils.prepared_wav_16k", fake_prepared
            ),
        ):
            result = await provider.transcribe(b"audio", "mp3")

        assert result == "réponse attié"
        transcribe_wav.assert_called_once_with("/tmp/prepared_16k.wav")

    @pytest.mark.asyncio
    async def test_transcribe_returns_none_when_unavailable(self):
        provider = mms_generic_provider.MMSGenericASR()
        with patch.object(provider, "is_available", return_value=False):
            assert await provider.transcribe(b"audio") is None

    def test_load_audio_prefers_torchaudio(self):
        provider = mms_generic_provider.MMSGenericASR()
        waveform = MagicMock()
        waveform.squeeze.return_value.numpy.return_value = [0.2, -0.2]
        fake_torchaudio = MagicMock()
        fake_torchaudio.load.return_value = (waveform, 16000)

        with (
            patch.object(mms_generic_provider, "_torchaudio_available", True),
            patch.object(mms_generic_provider, "_torchaudio", fake_torchaudio),
        ):
            audio, sample_rate = provider._load_audio("question.wav")

        assert audio == [0.2, -0.2]
        assert sample_rate == 16000

    def test_load_audio_falls_back_to_soundfile(self):
        provider = mms_generic_provider.MMSGenericASR()
        fake_soundfile = MagicMock()
        fake_soundfile.read.return_value = ([0.3], 8000)

        with (
            patch.object(mms_generic_provider, "_torchaudio_available", False),
            patch.dict(sys.modules, {"soundfile": fake_soundfile}),
        ):
            audio, sample_rate = provider._load_audio("question.wav")

        assert audio == [0.3]
        assert sample_rate == 8000
        fake_soundfile.read.assert_called_once_with(
            "question.wav",
            dtype="float32",
        )

    def test_transcribe_wav_decodes_processor_output(self):
        provider = mms_generic_provider.MMSGenericASR()
        model = MagicMock()
        model.return_value.logits = "logits"
        processor = MagicMock()
        processor.return_value = {"input_values": "samples"}
        processor.decode.return_value = "  transcription  "
        fake_torch = MagicMock()
        fake_torch.argmax.return_value = [["predicted-ids"]]

        with (
            patch.object(provider, "_get_model", return_value=(model, processor)),
            patch.object(provider, "_load_audio", return_value=([0.1], 16000)),
            patch.object(mms_generic_provider, "_torch", fake_torch),
        ):
            result = provider.transcribe_wav("question.wav")

        assert result == "transcription"
        processor.assert_called_once_with(
            [0.1],
            sampling_rate=16000,
            return_tensors="pt",
        )

    def test_transcribe_wav_handles_missing_audio_and_inference_error(self):
        provider = mms_generic_provider.MMSGenericASR()
        with (
            patch.object(provider, "_get_model", return_value=(MagicMock(), MagicMock())),
            patch.object(provider, "_load_audio", return_value=(None, None)),
        ):
            assert provider.transcribe_wav("missing.wav") is None

        with patch.object(provider, "_get_model", side_effect=RuntimeError("model")):
            with pytest.raises(RuntimeError, match="model"):
                provider.transcribe_wav("missing.wav")


class TestDefaultAsrChain:
    def test_default_chain_starts_with_mms_dyu_without_nemo(self):
        """ADR-0027 : NeMo retiré ; tête de chaîne = MMS-dyu."""
        import app.services.asr as asr_pkg

        asr_pkg._asr_chain = None
        try:
            chain = asr_pkg.get_asr_chain()
            names = [p.name for p in chain.providers]
            assert "NeMo Soloni" not in names
            assert names[0] == "MMS-dyu"
            assert any(n.startswith("MMS-generic") for n in names)
        finally:
            asr_pkg._asr_chain = None
