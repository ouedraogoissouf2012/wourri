"""
WOURI - TTS Multi-langues Ivoiriennes
Support des langues locales de Côte d'Ivoire via Facebook MMS-TTS
100% GRATUIT - Modèles Hugging Face

Langues supportées:
- Bambara/Dioula (bam) - ACTIF
- Attié (ati) - NOUVEAU
- Sénoufo Djimini (dyi) - NOUVEAU
- Sénoufo Mamara (myk) - NOUVEAU
- Dida Yocoboué (gud) - NOUVEAU
- Adioukrou (adj) - NOUVEAU
- Dan/Yacouba (dnj) - NOUVEAU
- Wobé (wob) - NOUVEAU
"""
import asyncio
import uuid
import os
import subprocess
import logging
from typing import Optional, Dict, Tuple
from app.config import get_settings
from app.data.constants import get_tts_languages, LANGUAGE_ALIASES as _LANG_ALIASES, resolve_language_alias

logger = logging.getLogger(__name__)

settings = get_settings()

# Configuration des langues ivoiriennes avec TTS (source unique : constants.py)
IVORIAN_LANGUAGES = get_tts_languages()

# Alias pour faciliter l'utilisation (source unique : constants.py)
LANGUAGE_ALIASES = _LANG_ALIASES

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
    logger.info("torch non installé - TTS Ivoirien désactivé")
    logger.info("Pour activer: pip install torch transformers scipy")

from app.services.model_registry import registry


def get_supported_languages() -> Dict[str, str]:
    """Retourne la liste des langues supportées"""
    return {code: info[0] for code, info in IVORIAN_LANGUAGES.items()}


def resolve_language_code(language: str) -> Optional[str]:
    """Résout un alias de langue vers son code ISO"""
    return resolve_language_alias(language)


def _make_ivoirian_loader(resolved_code: str):
    """Crée un loader pour un modèle TTS ivoirien donné."""
    lang_info = IVORIAN_LANGUAGES[resolved_code]
    model_name = lang_info[1]

    def _loader():
        logger.info(f"Chargement du modèle TTS {lang_info[0]} ({model_name})...")
        from transformers import VitsModel, AutoTokenizer

        model = VitsModel.from_pretrained(model_name)
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        logger.info(f"Modèle TTS {lang_info[0]} chargé!")
        return model, tokenizer

    return _loader


def get_tts_model(language_code: str):
    """Charge le modèle TTS pour une langue spécifique (lazy loading via ModelRegistry)"""
    if not TORCH_AVAILABLE:
        return None, None

    # Résoudre le code de langue
    resolved_code = resolve_language_code(language_code)
    if not resolved_code:
        logger.warning(f"Langue non supportée: {language_code}")
        return None, None

    registry_key = f"tts_ivoirian_{resolved_code}"

    try:
        return registry.get(registry_key, loader=_make_ivoirian_loader(resolved_code))
    except Exception as e:
        logger.error(f"Erreur chargement modèle {IVORIAN_LANGUAGES[resolved_code][1]}: {e}")
        return None, None


from app.services._ffmpeg import get_ffmpeg as find_ffmpeg


def convert_wav_to_ogg(wav_path: str, ogg_path: str) -> bool:
    """Convertit un fichier WAV en OGG (Opus) pour WhatsApp mobile"""
    ffmpeg_path = find_ffmpeg()

    if ffmpeg_path:
        try:
            result = subprocess.run([
                ffmpeg_path, '-y', '-i', wav_path,
                '-c:a', 'libopus', '-b:a', '64k',
                '-vbr', 'on', '-compression_level', '10',
                ogg_path
            ], capture_output=True, text=True, timeout=30)

            if result.returncode == 0 and os.path.exists(ogg_path):
                os.remove(wav_path)
                return True
        except Exception as e:
            logger.error(f"Erreur ffmpeg: {e}")

    # Fallback avec pydub
    try:
        from pydub import AudioSegment
        if ffmpeg_path and ffmpeg_path != 'ffmpeg':
            AudioSegment.converter = ffmpeg_path

        audio = AudioSegment.from_wav(wav_path)
        audio.export(ogg_path, format="ogg", codec="libopus", bitrate="64k")
        os.remove(wav_path)
        return True
    except Exception as e:
        logger.error(f"Erreur pydub: {e}")

    return False


def synthesize_ivorian_text(text: str, language: str = "bam") -> Optional[str]:
    """
    Génère un fichier audio OGG à partir de texte dans une langue ivoirienne

    Args:
        text: Le texte à synthétiser
        language: Code de langue (bam, ati, dyi, myk, gud, adj, dnj, wob)

    Returns:
        URL du fichier audio ou None en cas d'erreur
    """
    if not TORCH_AVAILABLE or not text:
        return None

    # Résoudre le code de langue
    resolved_code = resolve_language_code(language)
    if not resolved_code:
        logger.warning(f"Langue non supportée: {language}")
        return None

    try:
        model, tokenizer = get_tts_model(resolved_code)
        if model is None:
            return None

        inputs = tokenizer(text, return_tensors="pt")

        with torch.no_grad():
            output = model(**inputs).waveform

        waveform = output.squeeze().cpu().numpy()
        waveform = waveform / np.max(np.abs(waveform))
        waveform = (waveform * 32767).astype(np.int16)

        # Générer les noms de fichiers
        file_id = uuid.uuid4()
        wav_filename = f"{resolved_code}_{file_id}.wav"
        ogg_filename = f"{resolved_code}_{file_id}.ogg"
        wav_filepath = os.path.join(settings.audio_output_dir, wav_filename)
        ogg_filepath = os.path.join(settings.audio_output_dir, ogg_filename)
        os.makedirs(settings.audio_output_dir, exist_ok=True)

        # Écrire le WAV temporaire
        wav.write(wav_filepath, rate=model.config.sampling_rate, data=waveform)

        # Convertir en OGG pour WhatsApp
        if convert_wav_to_ogg(wav_filepath, ogg_filepath):
            if os.path.exists(ogg_filepath) and os.path.getsize(ogg_filepath) > 0:
                return f"/static/audio/{ogg_filename}"

        # Fallback WAV
        if os.path.exists(wav_filepath) and os.path.getsize(wav_filepath) > 0:
            return f"/static/audio/{wav_filename}"

    except Exception as e:
        logger.error(f"Erreur TTS {language}: {e}")

    return None


async def synthesize_ivorian(text: str, language: str = "bam") -> Tuple[Optional[str], str]:
    """
    Synthétise du texte dans une langue ivoirienne

    Args:
        text: Le texte à synthétiser
        language: Code ou nom de la langue

    Returns:
        Tuple (url_audio, langue_utilisée)
    """
    if not TORCH_AVAILABLE or not text:
        return None, language

    resolved_code = resolve_language_code(language)
    if not resolved_code:
        return None, language

    audio_url = await asyncio.to_thread(synthesize_ivorian_text, text, resolved_code)
    lang_name = IVORIAN_LANGUAGES[resolved_code][0]

    return audio_url, lang_name


def check_models_status() -> dict:
    """Vérifie le statut des modèles TTS ivoiriens"""
    status = {
        "torch_available": TORCH_AVAILABLE,
        "languages_available": get_supported_languages(),
        "models_loaded": [
            code for code in IVORIAN_LANGUAGES
            if registry.is_loaded(f"tts_ivoirian_{code}")
        ],
        "total_languages": len(IVORIAN_LANGUAGES),
    }
    return status


def preload_model(language: str) -> bool:
    """Précharge un modèle TTS pour une langue spécifique"""
    model, tokenizer = get_tts_model(language)
    return model is not None


def preload_all_models() -> Dict[str, bool]:
    """Précharge tous les modèles TTS (attention: ~1GB RAM par modèle)"""
    results = {}
    for code in IVORIAN_LANGUAGES.keys():
        results[code] = preload_model(code)
    return results
