"""Tests des adapters ASR réels sans charger leurs modèles ML."""
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.asr import mms_dyu_provider, mms_generic_provider, nemo_provider


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
    async def test_transcribe_delegates_to_shared_audio_pipeline(self):
        provider = mms_dyu_provider.MMSDyuASR()

        with (
            patch.object(provider, "is_available", return_value=True),
            patch.object(
                mms_dyu_provider,
                "transcribe_with_temp_files",
                new=AsyncMock(return_value="  malo sɛnɛ  "),
            ) as shared_pipeline,
        ):
            result = await provider.transcribe(b"audio", "ogg")

        assert result == "  malo sɛnɛ  "
        shared_pipeline.assert_awaited_once_with(
            b"audio",
            "ogg",
            provider._transcribe_wav,
            provider.name,
        )

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
            result = provider._transcribe_wav("question.wav")

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
            assert provider._transcribe_wav("question.wav") is None

        with (
            patch.object(provider, "_get_model", side_effect=RuntimeError("model")),
            pytest.raises(RuntimeError, match="model"),
        ):
            provider._transcribe_wav("question.wav")


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

    @pytest.mark.asyncio
    async def test_transcribe_validates_language_and_uses_shared_pipeline(self):
        provider = mms_generic_provider.MMSGenericASR("unknown")
        with patch.object(provider, "is_available", return_value=True):
            assert await provider.transcribe(b"audio") is None

        provider.set_language("ati")
        with (
            patch.object(provider, "is_available", return_value=True),
            patch.object(
                mms_generic_provider,
                "transcribe_with_temp_files",
                new=AsyncMock(return_value="réponse attié"),
            ) as shared_pipeline,
        ):
            result = await provider.transcribe(b"audio", "mp3")

        assert result == "réponse attié"
        shared_pipeline.assert_awaited_once_with(
            b"audio",
            "mp3",
            provider._transcribe_wav,
            provider.name,
        )

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
            result = provider._transcribe_wav("question.wav")

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
            assert provider._transcribe_wav("missing.wav") is None

        with patch.object(provider, "_get_model", side_effect=RuntimeError("model")):
            with pytest.raises(RuntimeError, match="model"):
                provider._transcribe_wav("missing.wav")


class TestNemoProvider:
    def test_availability_requires_dependency_and_model_file(self):
        provider = nemo_provider.NemoSoloniASR()
        with (
            patch.object(nemo_provider, "_nemo_available", True),
            patch("app.services.asr.nemo_provider.os.path.exists", return_value=True),
        ):
            assert provider.name == "NeMo Soloni"
            assert provider.is_available()

        with patch.object(nemo_provider, "_nemo_available", False):
            assert not provider.is_available()

    @pytest.mark.asyncio
    async def test_transcribe_normalizes_shared_pipeline_result(self):
        provider = nemo_provider.NemoSoloniASR()

        with (
            patch.object(provider, "is_available", return_value=True),
            patch.object(
                nemo_provider,
                "transcribe_with_temp_files",
                new=AsyncMock(return_value="MALO SENE"),
            ) as shared_pipeline,
            patch(
                "app.services.asr_bambara_normalizer.normalize_bambara_asr",
                return_value="malo sɛnɛ",
            ) as normalize,
        ):
            result = await provider.transcribe(b"audio", "webm")

        assert result == "malo sɛnɛ"
        normalize.assert_called_once_with("MALO SENE")
        shared_pipeline.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_transcribe_returns_none_when_unavailable(self):
        provider = nemo_provider.NemoSoloniASR()
        with patch.object(provider, "is_available", return_value=False):
            assert await provider.transcribe(b"audio") is None

    @pytest.mark.parametrize(
        ("raw_result", "expected"),
        [
            (["  liste  "], "liste"),
            (SimpleNamespace(text="  attribut  "), "attribut"),
            ("  chaîne  ", "chaîne"),
            ([], ""),
        ],
    )
    def test_transcribe_wav_normalizes_nemo_result_shapes(
        self,
        raw_result,
        expected,
    ):
        provider = nemo_provider.NemoSoloniASR()
        model = MagicMock()
        model.transcribe.return_value = (
            raw_result if raw_result == [] else [raw_result]
        )
        fake_torch = MagicMock()

        with (
            patch.object(provider, "_get_model", return_value=model),
            patch.object(nemo_provider, "_torch", fake_torch),
        ):
            result = provider._transcribe_wav("question.wav")

        assert result == expected

    def test_transcribe_wav_handles_missing_model_and_inference_error(self):
        provider = nemo_provider.NemoSoloniASR()
        with patch.object(provider, "_get_model", return_value=None):
            assert provider._transcribe_wav("question.wav") is None

        model = MagicMock()
        model.transcribe.side_effect = RuntimeError("inference")
        with (
            patch.object(provider, "_get_model", return_value=model),
            patch.object(nemo_provider, "_torch", MagicMock()),
        ):
            assert provider._transcribe_wav("question.wav") is None
