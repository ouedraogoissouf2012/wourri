"""Tests #301 — la chaîne ASR ne convertit l'audio en WAV 16k qu'UNE fois.

Avant #301, chaque provider de la chaîne (`transcribe(bytes, ext)`) refaisait sa
propre conversion ffmpeg via `transcribe_with_temp_files`. Un audio pouvait être
converti 2 à 4 fois pour une seule requête (subprocess ffmpeg + I/O disque +
timeout 30s à chaque fois). Mesuré avant fix : 2 conversions (provider +
agri_fallback), 3 (cascade 3 providers).

Après #301 : `ASRChain` convertit UNE fois en amont et passe le WAV 16k prêt à
chaque provider via `ASRProvider.transcribe_wav(wav_path)`. Ces tests
verrouillent l'invariant « 1 audio → 1 conversion ».
"""
from __future__ import annotations

from typing import Optional

import pytest

from app.services.asr import audio_utils
from app.services.asr.base import ASRProvider
from app.services.asr.chain import ASRChain


class CountingWavProvider(ASRProvider):
    """Provider de test qui implémente le contrat #301 : l'inférence part d'un
    WAV déjà converti (`transcribe_wav`), jamais des bytes bruts."""

    def __init__(self, provider_name: str, available: bool = True,
                 result: Optional[str] = None):
        self._name = provider_name
        self._available = available
        self._result = result
        self.wav_calls: list[str] = []

    @property
    def name(self) -> str:
        return self._name

    def is_available(self) -> bool:
        return self._available

    def transcribe_wav(self, wav_path: str) -> Optional[str]:
        self.wav_calls.append(wav_path)
        return self._result


@pytest.fixture
def count_conversions(monkeypatch, tmp_path):
    """Compte les appels réels à `convert_to_wav_16k` et écrit un WAV bidon.

    Retourne un dict mutable `{"count": int}` inspectable après le run.
    """
    counter = {"count": 0}

    def fake_convert(input_path: str, output_path: str) -> bool:
        counter["count"] += 1
        with open(output_path, "wb") as f:
            f.write(b"RIFF....WAVEfake")
        return True

    monkeypatch.setattr(audio_utils, "_TEMP_DIR", str(tmp_path))
    monkeypatch.setattr(audio_utils, "convert_to_wav_16k", fake_convert)
    return counter


@pytest.mark.asyncio
async def test_single_provider_converts_once(count_conversions, monkeypatch):
    """Un provider seul → 1 conversion."""
    import app.services.asr.normalizer as nrm

    monkeypatch.setattr(nrm, "normalize_asr_output", lambda x: x)
    p = CountingWavProvider("P1", result="malo sɛnɛ wagati")  # agricole
    chain = ASRChain(providers=[p])

    result = await chain.transcribe(b"audio-ogg", "ogg")

    assert result == "malo sɛnɛ wagati"
    assert count_conversions["count"] == 1
    assert len(p.wav_calls) == 1


@pytest.mark.asyncio
async def test_cascade_three_providers_converts_once(count_conversions, monkeypatch):
    """3 providers, les 2 premiers renvoient None → toujours 1 seule conversion
    (avant #301 : 3 conversions)."""
    import app.services.asr.normalizer as nrm

    monkeypatch.setattr(nrm, "normalize_asr_output", lambda x: x)
    p1 = CountingWavProvider("P1", result=None)
    p2 = CountingWavProvider("P2", result=None)
    p3 = CountingWavProvider("P3", result="kaba sɛnɛ")  # agricole
    chain = ASRChain(providers=[p1, p2, p3])

    result = await chain.transcribe(b"audio-ogg", "ogg")

    assert result == "kaba sɛnɛ"
    assert count_conversions["count"] == 1
    # Chaque provider disponible a bien reçu le MÊME wav path.
    all_wavs = p1.wav_calls + p2.wav_calls + p3.wav_calls
    assert len(all_wavs) == 3
    assert len(set(all_wavs)) == 1  # un seul WAV partagé


@pytest.mark.asyncio
async def test_agri_fallback_reuses_same_wav(count_conversions, monkeypatch):
    """Provider non-agricole + agri_fallback (différent) → 1 seule conversion,
    le fallback réutilise le WAV déjà converti (avant #301 : 2 conversions)."""
    import app.services.asr.normalizer as nrm

    monkeypatch.setattr(nrm, "normalize_asr_output", lambda x: x)
    primary = CountingWavProvider("Primary", result="an ni wula min ye taa")  # pas agri, ≥3 mots
    fallback = CountingWavProvider("Fallback", result="an ni wula min ye taa")
    chain = ASRChain(providers=[primary], agri_fallback=fallback)

    await chain.transcribe(b"audio-ogg", "ogg")

    assert count_conversions["count"] == 1
    assert len(primary.wav_calls) == 1
    assert len(fallback.wav_calls) == 1
    assert primary.wav_calls[0] == fallback.wav_calls[0]  # même WAV


@pytest.mark.asyncio
async def test_conversion_failure_returns_none_without_calling_providers(
    monkeypatch, tmp_path
):
    """Si la conversion ffmpeg échoue, la chaîne retourne None sans appeler
    aucun provider (rien à transcrire)."""
    def failing_convert(input_path: str, output_path: str) -> bool:
        return False

    monkeypatch.setattr(audio_utils, "_TEMP_DIR", str(tmp_path))
    monkeypatch.setattr(audio_utils, "convert_to_wav_16k", failing_convert)

    p = CountingWavProvider("P1", result="devrait pas être appelé")
    chain = ASRChain(providers=[p])

    result = await chain.transcribe(b"audio-ogg", "ogg")

    assert result is None
    assert len(p.wav_calls) == 0
