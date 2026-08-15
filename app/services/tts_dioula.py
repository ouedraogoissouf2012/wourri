"""
WOURI - TTS Dioula (Côte d'Ivoire)
100% GRATUIT - facebook/mms-tts-dyu + NLLB-200 (dyu_Latn)

Ce service est spécifique au Dioula ivoirien, distinct du Bambara malien.
Les deux langues sont mutuellement intelligibles mais ont des différences
de prononciation et de vocabulaire.

Modèles utilisés:
- TTS: facebook/mms-tts-dyu (Dioula)
- Traduction: facebook/nllb-200-distilled-600M (dyu_Latn)

Modularisation 2026-08 : la prosodie/segmentation est dans tts_dioula_prosody.py
et l'orchestration de traduction dans tts_dioula_translation.py. Ce fichier ne
garde que le cœur TTS (modèle, DSP, synthèse) et re-exporte translate_to_dioula
/ translate_dioula_to_french pour compat des callsites.
"""
import asyncio
import uuid
import os
import logging
from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Vérifier si torch est disponible
TORCH_AVAILABLE = False
torch = None
np = None
wav = None

try:
    import torch as _torch
    import numpy as _np
    import scipy.io.wavfile as _wav
    torch = _torch
    np = _np
    wav = _wav
    TORCH_AVAILABLE = True
except ImportError:
    logger.info("torch non installé - TTS Dioula désactivé")

from app.services.model_registry import registry


def _load_tts_dioula():
    """Charge le modèle TTS Dioula (model, tokenizer)."""
    logger.info("Chargement du modèle TTS Dioula (mms-tts-dyu)...")
    from transformers import VitsModel, AutoTokenizer

    model = VitsModel.from_pretrained("facebook/mms-tts-dyu")
    tokenizer = AutoTokenizer.from_pretrained("facebook/mms-tts-dyu")
    logger.info("Modèle TTS Dioula chargé!")
    return model, tokenizer


def is_mms_dyu_enabled() -> bool:
    """Combine torch disponible + flag ENABLE_MMS_DYU (issue #42).

    Lecture lazy de get_settings() pour permettre le monkeypatch en tests
    et la prise en compte d'un éventuel rechargement de config.
    """
    if not TORCH_AVAILABLE:
        return False
    try:
        from app.config import get_settings
        return get_settings().enable_mms_dyu
    except Exception:
        return TORCH_AVAILABLE


def get_tts_model_dioula():
    """Charge le modèle TTS Dioula (lazy loading via ModelRegistry).

    Respect du flag ENABLE_MMS_DYU (issue #42) : si False, retourne (None, None)
    immédiatement sans tenter le chargement (économise ~3.8 GB RAM).
    """
    if not is_mms_dyu_enabled():
        return None, None

    return registry.get("tts_dioula", loader=_load_tts_dioula)


# Prosodie / segmentation : extraite vers tts_dioula_prosody.py (modularisation
# 2026-08). Consommée par synthesize_dioula_text ci-dessous.
from app.services.tts_dioula_prosody import _split_sentences, _get_speaking_rate

# Traduction FR<->Dioula : extraite vers tts_dioula_translation.py. Re-export
# pour compat des callsites (tests, synthesize_dioula ci-dessous).
from app.services.tts_dioula_translation import (  # noqa: F401
    translate_to_dioula,
    translate_dioula_to_french,
)

# Sprint refactor 2026-05-28 : convert_wav_to_ogg deplace dans tts_common.py
# (audit P1 #4 — DRY mutualisation tts_bambara/tts_dioula). Reexport pour
# compat des callsites internes (synthesize_dioula_text ci-dessous).
from app.services.tts_common import convert_wav_to_ogg  # noqa: F401


def _trim_leading_silence(waveform: np.ndarray, threshold: float = 0.01,
                          keep_ms: int = 30, sample_rate: int = 16000) -> np.ndarray:
    """Coupe le silence naturel au début d'un waveform VITS.

    MMS-TTS-DYU produit ~400ms de silence au début de chaque segment
    (transitoire du modèle). On garde keep_ms (30ms) pour éviter
    un démarrage trop brusque.
    """
    above = np.where(np.abs(waveform) > threshold)[0]
    if len(above) == 0:
        return waveform
    voice_start = above[0]
    keep_samples = int(sample_rate * keep_ms / 1000)
    trim_point = max(0, voice_start - keep_samples)
    return waveform[trim_point:]


def _clean_for_tts(text: str) -> str:
    """Nettoie le texte bambara pour le TTS MMS-DYU.

    MMS-TTS-DYU ne gère pas :
    - Les tons diacritiques (à, è, ì, ò, ù) → produit du bruit
    - Les apostrophes dans les contractions (b'a, k'a, n'a) → prononciation erronée

    On retire les tons tout en gardant les caractères bambara (ɛ, ɔ, ŋ, ɲ).
    """
    import unicodedata
    # Décomposer les caractères accentués, retirer les marques de ton
    result = []
    for ch in unicodedata.normalize("NFD", text):
        if unicodedata.category(ch) == "Mn":  # Mark, Nonspacing (tons)
            continue
        result.append(ch)
    cleaned = "".join(result)
    # Remplacer les apostrophes par un espace (b'a → b a)
    cleaned = cleaned.replace("'", " ").replace("'", " ")
    # Réduire les espaces multiples
    cleaned = " ".join(cleaned.split())
    return cleaned


def _synthesize_sentence(sentence: str, model, tokenizer,
                         speaking_rate: float = 1.15) -> np.ndarray | None:
    """Synthétise un segment unique avec le speaking_rate donné.

    Nettoie les tons + apostrophes avant synthèse.
    Trim le silence naturel VITS (~400ms) au début de chaque segment.
    """
    try:
        sentence = _clean_for_tts(sentence)
        inputs = tokenizer(sentence, return_tensors="pt")
        original_rate = model.config.speaking_rate
        model.config.speaking_rate = speaking_rate
        try:
            with torch.no_grad():
                output = model(**inputs).waveform
        finally:
            model.config.speaking_rate = original_rate
        waveform = output.squeeze().cpu().numpy()
        return _trim_leading_silence(waveform, sample_rate=model.config.sampling_rate)
    except Exception as e:
        logger.error(f"[TTS] Erreur synthèse '{sentence[:40]}': {e}")
        return None


def synthesize_dioula_text(dioula_text: str) -> str | None:
    """Génère un fichier audio OGG à partir de texte Dioula.

    v3 — pauses variables :
    - Découpage hiérarchique : . ! ? → virgule → marqueurs bambara → forcé
    - Pause adaptée : 200ms (virgule) / 300ms (marqueur) / 450ms (fin phrase)
    - speaking_rate : 1.05 (salutation) / 1.15 (défaut) / 1.25 (technique)
    """
    if not TORCH_AVAILABLE or not dioula_text:
        return None

    try:
        model, tokenizer = get_tts_model_dioula()
        if model is None:
            return None

        sample_rate = model.config.sampling_rate

        segments = _split_sentences(dioula_text)
        if not segments:
            segments = [(dioula_text, 0.40)]

        audio_parts = []

        # Silence initial 50ms — compense le preskip Opus (104 samples)
        audio_parts.append(np.zeros(int(sample_rate * 0.05), dtype=np.float32))

        for i, (sentence, pause_s) in enumerate(segments):
            rate = _get_speaking_rate(sentence)
            waveform = _synthesize_sentence(sentence, model, tokenizer, speaking_rate=rate)
            if waveform is None:
                continue
            audio_parts.append(waveform)
            # Ajouter le silence APRÈS ce segment
            # Dernier segment → silence de fin 0.30s (évite la coupure brusque)
            actual_pause = pause_s if i < len(segments) - 1 else 0.30
            silence_samples = int(sample_rate * actual_pause)
            audio_parts.append(np.zeros(silence_samples, dtype=np.float32))

        if not audio_parts:
            return None

        combined = np.concatenate(audio_parts)

        # Normalisation
        max_val = np.max(np.abs(combined))
        if max_val > 0:
            combined = combined / max_val
        combined = (combined * 32767).astype(np.int16)

        file_id = uuid.uuid4()
        wav_filename = f"dyu_{file_id}.wav"
        ogg_filename = f"dyu_{file_id}.ogg"
        wav_filepath = os.path.join(settings.audio_output_dir, wav_filename)
        ogg_filepath = os.path.join(settings.audio_output_dir, ogg_filename)
        os.makedirs(settings.audio_output_dir, exist_ok=True)

        wav.write(wav_filepath, rate=sample_rate, data=combined)

        if convert_wav_to_ogg(wav_filepath, ogg_filepath):
            if os.path.exists(ogg_filepath) and os.path.getsize(ogg_filepath) > 0:
                return f"/static/audio/{ogg_filename}"

        if os.path.exists(wav_filepath) and os.path.getsize(wav_filepath) > 0:
            return f"/static/audio/{wav_filename}"

    except Exception as e:
        logger.error(f"Erreur TTS Dioula: {e}")

    return None


async def synthesize_dioula(french_text: str) -> tuple[str | None, str | None]:
    """Traduit du français vers le Dioula et génère l'audio"""
    if not TORCH_AVAILABLE or not french_text:
        return None, None

    try:
        dioula_text = await asyncio.to_thread(translate_to_dioula, french_text)
        try:
            logger.info(f"Traduction Dioula: {french_text[:50]}... -> {dioula_text[:50]}...")
        except UnicodeEncodeError:
            logger.info("Traduction Dioula effectuée")

        audio_url = await asyncio.to_thread(synthesize_dioula_text, dioula_text)
        return audio_url, dioula_text

    except Exception as e:
        logger.error(f"Erreur synthèse Dioula: {e}")
        return None, None


def check_dioula_status() -> dict:
    """Vérifie le statut des modèles Dioula"""
    from app.services.translation import get_translation_service
    nllb_model, _ = get_translation_service().get_nllb_model_and_tokenizer()
    return {
        "torch_available": TORCH_AVAILABLE,
        "tts_loaded": registry.is_loaded("tts_dioula"),
        "translator_loaded": nllb_model is not None,
        "tts_model": "facebook/mms-tts-dyu",
        "translation_code": "dyu_Latn",
        "nllb_shared": True
    }
