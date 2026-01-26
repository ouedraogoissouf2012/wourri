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
import uuid
import os
import subprocess
from typing import Optional, Dict, Tuple
from app.config import get_settings

settings = get_settings()

# Configuration des langues ivoiriennes avec TTS
IVORIAN_LANGUAGES = {
    # Code: (nom_affichage, modele_huggingface, code_nllb_traduction)
    "bam": ("Bambara/Dioula", "facebook/mms-tts-bam", "bam_Latn"),
    "ati": ("Attié", "facebook/mms-tts-ati", None),  # Pas de traduction NLLB
    "dyi": ("Sénoufo Djimini", "facebook/mms-tts-dyi", None),
    "myk": ("Sénoufo Mamara", "facebook/mms-tts-myk", None),
    "gud": ("Dida Yocoboué", "facebook/mms-tts-gud", None),
    "adj": ("Adioukrou", "facebook/mms-tts-adj", None),
    "dnj": ("Dan/Yacouba", "facebook/mms-tts-dnj", None),
    "wob": ("Wobé", "facebook/mms-tts-wob", None),
}

# Alias pour faciliter l'utilisation
LANGUAGE_ALIASES = {
    "bambara": "bam",
    "dioula": "bam",
    "jula": "bam",
    "attie": "ati",
    "senoufo": "dyi",  # Djimini par défaut
    "senoufo_djimini": "dyi",
    "senoufo_mamara": "myk",
    "dida": "gud",
    "adioukrou": "adj",
    "dan": "dnj",
    "yacouba": "dnj",
    "wobe": "wob",
}

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
    print("INFO: torch non installé - TTS Ivoirien désactivé")
    print("Pour activer: pip install torch transformers scipy")

# Cache des modèles TTS (un par langue)
_tts_models: Dict[str, Tuple] = {}


def get_supported_languages() -> Dict[str, str]:
    """Retourne la liste des langues supportées"""
    return {code: info[0] for code, info in IVORIAN_LANGUAGES.items()}


def resolve_language_code(language: str) -> Optional[str]:
    """Résout un alias de langue vers son code ISO"""
    language_lower = language.lower().strip()

    # Vérifier si c'est déjà un code valide
    if language_lower in IVORIAN_LANGUAGES:
        return language_lower

    # Vérifier les alias
    if language_lower in LANGUAGE_ALIASES:
        return LANGUAGE_ALIASES[language_lower]

    return None


def get_tts_model(language_code: str):
    """Charge le modèle TTS pour une langue spécifique (lazy loading)"""
    global _tts_models

    if not TORCH_AVAILABLE:
        return None, None

    # Résoudre le code de langue
    resolved_code = resolve_language_code(language_code)
    if not resolved_code:
        print(f"Langue non supportée: {language_code}")
        return None, None

    # Vérifier le cache
    if resolved_code in _tts_models:
        return _tts_models[resolved_code]

    # Charger le modèle
    lang_info = IVORIAN_LANGUAGES[resolved_code]
    model_name = lang_info[1]

    print(f"Chargement du modèle TTS {lang_info[0]} ({model_name})...")

    try:
        from transformers import VitsModel, AutoTokenizer

        model = VitsModel.from_pretrained(model_name)
        tokenizer = AutoTokenizer.from_pretrained(model_name)

        _tts_models[resolved_code] = (model, tokenizer)
        print(f"Modèle TTS {lang_info[0]} chargé!")

        return model, tokenizer

    except Exception as e:
        print(f"Erreur chargement modèle {model_name}: {e}")
        return None, None


def find_ffmpeg():
    """Trouve le chemin de ffmpeg sur le système"""
    possible_paths = [
        'ffmpeg',
        r'C:\Users\USER PC\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe',
    ]

    for ffmpeg_path in possible_paths:
        try:
            result = subprocess.run([ffmpeg_path, '-version'],
                                  capture_output=True, timeout=5)
            if result.returncode == 0:
                return ffmpeg_path
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    return None


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
            print(f"Erreur ffmpeg: {e}")

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
        print(f"Erreur pydub: {e}")

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
        print(f"Langue non supportée: {language}")
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
        print(f"Erreur TTS {language}: {e}")

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

    audio_url = synthesize_ivorian_text(text, resolved_code)
    lang_name = IVORIAN_LANGUAGES[resolved_code][0]

    return audio_url, lang_name


def check_models_status() -> dict:
    """Vérifie le statut des modèles TTS ivoiriens"""
    status = {
        "torch_available": TORCH_AVAILABLE,
        "languages_available": get_supported_languages(),
        "models_loaded": list(_tts_models.keys()),
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
