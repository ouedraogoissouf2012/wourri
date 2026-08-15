"""
WOURI - TTS Bambara (Hugging Face)
100% GRATUIT - facebook/mms-tts-bam

NOTE: Necessite torch, transformers, scipy (environ 2GB)
Pour installer: pip install torch transformers scipy pydub

Traduction déléguée au TranslationService (Strategy Pattern):
  1. Dictionnaire (11k+ mots Bamadaba + phrases manuelles)
  2. NLLB-200 (fallback IA)

Modularisation 2026-08 : le pipeline texte (prétraitement, nettoyage) est dans
tts_bambara_text.py et l'orchestration de traduction dans
tts_bambara_translation.py. Ce fichier ne garde que le cœur TTS (torch) et
re-exporte translate_to_bambara/translate_to_french pour compat des callsites.
"""
import asyncio
import uuid
import os
import logging
from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Chemin du modele TTS Bambara local
TTS_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "modeles_manuels"
)

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
    logger.info("torch non installé - TTS Bambara désactivé")
    logger.info("Pour activer: pip install torch transformers scipy")

from app.services.model_registry import registry


def _load_tts_bambara():
    """Charge le modele TTS Bambara (model, tokenizer)."""
    logger.info("Chargement du modele TTS Bambara...")
    from transformers import VitsModel, AutoTokenizer

    # Utiliser le modele local s'il existe
    if os.path.exists(TTS_MODEL_PATH) and os.path.exists(os.path.join(TTS_MODEL_PATH, "model.safetensors")):
        logger.info(f"Utilisation du modele local: {TTS_MODEL_PATH}")
        model = VitsModel.from_pretrained(TTS_MODEL_PATH)
        tokenizer = AutoTokenizer.from_pretrained(TTS_MODEL_PATH)
    else:
        logger.info("Telechargement depuis HuggingFace...")
        model = VitsModel.from_pretrained(settings.hf_tts_model)
        tokenizer = AutoTokenizer.from_pretrained(settings.hf_tts_model)
    logger.info("Modele TTS Bambara charge!")
    return model, tokenizer


def is_mms_bam_enabled() -> bool:
    """Combine torch disponible + flag ENABLE_MMS_BAM (issue #42)."""
    if not TORCH_AVAILABLE:
        return False
    try:
        from app.config import get_settings
        return get_settings().enable_mms_bam
    except Exception:
        return TORCH_AVAILABLE


def get_tts_model():
    """Charge le modele TTS Bambara (lazy loading via ModelRegistry).

    Respect du flag ENABLE_MMS_BAM (issue #42) : si False, retourne
    (None, None) immédiatement sans tenter le chargement.
    """
    if not is_mms_bam_enabled():
        return None, None

    return registry.get("tts_bambara", loader=_load_tts_bambara)


# Traduction FR<->Bambara : extraite vers tts_bambara_translation.py
# (modularisation 2026-08). Re-export pour compat des callsites : routers
# asr.py/tts.py, tests, et synthesize_bambara ci-dessous.
from app.services.tts_bambara_translation import (  # noqa: F401
    translate_to_bambara,
    translate_to_french,
)

# Sprint refactor 2026-05-28 : convert_wav_to_ogg deplace dans tts_common.py
# (audit P1 #4 — DRY mutualisation tts_bambara/tts_dioula, 28 lignes
# identiques entre les 2 fichiers). Reexport pour compat des callsites
# internes (synthesize_bambara_text ci-dessous).
from app.services.tts_common import convert_wav_to_ogg  # noqa: F401


def synthesize_bambara_text(bambara_text: str) -> str | None:
    """Génère un fichier audio OGG (Opus) à partir de texte Bambara"""
    if not TORCH_AVAILABLE or not bambara_text:
        return None

    try:
        model, tokenizer = get_tts_model()
        if model is None:
            return None

        inputs = tokenizer(bambara_text, return_tensors="pt")

        with torch.no_grad():
            output = model(**inputs).waveform

        waveform = output.squeeze().cpu().numpy()
        waveform = waveform / np.max(np.abs(waveform))
        waveform = (waveform * 32767).astype(np.int16)

        file_id = uuid.uuid4()
        wav_filename = f"bm_{file_id}.wav"
        ogg_filename = f"bm_{file_id}.ogg"
        wav_filepath = os.path.join(settings.audio_output_dir, wav_filename)
        ogg_filepath = os.path.join(settings.audio_output_dir, ogg_filename)
        os.makedirs(settings.audio_output_dir, exist_ok=True)

        # Ecrire le WAV temporaire
        wav.write(wav_filepath, rate=model.config.sampling_rate, data=waveform)

        # Convertir en OGG pour WhatsApp mobile
        if convert_wav_to_ogg(wav_filepath, ogg_filepath):
            if os.path.exists(ogg_filepath) and os.path.getsize(ogg_filepath) > 0:
                return f"/static/audio/{ogg_filename}"

        # Fallback: retourner le WAV si conversion echoue
        if os.path.exists(wav_filepath) and os.path.getsize(wav_filepath) > 0:
            logger.warning("Fallback: utilisation du fichier WAV")
            return f"/static/audio/{wav_filename}"

    except Exception as e:
        logger.error(f"Erreur TTS Bambara: {e}")

    return None


async def synthesize_bambara(french_text: str) -> tuple[str | None, str | None]:
    """Traduit du français vers le Bambara et génère l'audio"""
    if not TORCH_AVAILABLE or not french_text:
        return None, None

    try:
        bambara_text = await asyncio.to_thread(translate_to_bambara, french_text)
        # Utiliser encode/decode pour éviter les erreurs d'encodage Windows
        try:
            logger.info(f"Traduction: {french_text} -> {bambara_text}")
        except UnicodeEncodeError:
            logger.info(f"Traduction effectuee (caracteres speciaux Bambara)")

        audio_url = await asyncio.to_thread(synthesize_bambara_text, bambara_text)
        return audio_url, bambara_text

    except Exception as e:
        try:
            logger.error(f"Erreur synthese Bambara: {e}")
        except UnicodeEncodeError:
            logger.error("Erreur synthese Bambara (erreur encodage)")
        return None, None


def check_models_status() -> dict:
    """Vérifie le statut des modèles Hugging Face"""
    translator_loaded = False
    try:
        from app.services.translation import get_translation_service
        service = get_translation_service()
        stats = service.get_stats()
        translator_loaded = stats["dictionnaire"]["total_mots"] > 0
    except Exception:
        pass

    return {
        "torch_available": TORCH_AVAILABLE,
        "tts_loaded": registry.is_loaded("tts_bambara"),
        "translator_loaded": translator_loaded,
        "tts_model": settings.hf_tts_model,
        "translator_model": settings.hf_translator_model
    }
