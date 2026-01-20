"""
WOURI - TTS Bambara (Hugging Face)
100% GRATUIT - facebook/mms-tts-bam

NOTE: Necessite torch, transformers, scipy (environ 2GB)
Pour installer: pip install torch transformers scipy pydub
"""
import uuid
import os
import subprocess
from app.config import get_settings

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
    print("INFO: torch non installé - TTS Bambara désactivé")
    print("Pour activer: pip install torch transformers scipy")

# Cache des modèles
_tts_model = None
_tts_tokenizer = None
_translator_model = None
_translator_tokenizer = None


def get_tts_model():
    """Charge le modele TTS Bambara (lazy loading)"""
    global _tts_model, _tts_tokenizer

    if not TORCH_AVAILABLE:
        return None, None

    if _tts_model is None:
        print("Chargement du modele TTS Bambara...")
        from transformers import VitsModel, AutoTokenizer

        # Utiliser le modele local s'il existe
        if os.path.exists(TTS_MODEL_PATH) and os.path.exists(os.path.join(TTS_MODEL_PATH, "model.safetensors")):
            print(f"Utilisation du modele local: {TTS_MODEL_PATH}")
            _tts_model = VitsModel.from_pretrained(TTS_MODEL_PATH)
            _tts_tokenizer = AutoTokenizer.from_pretrained(TTS_MODEL_PATH)
        else:
            print("Telechargement depuis HuggingFace...")
            _tts_model = VitsModel.from_pretrained(settings.hf_tts_model)
            _tts_tokenizer = AutoTokenizer.from_pretrained(settings.hf_tts_model)
        print("Modele TTS Bambara charge!")

    return _tts_model, _tts_tokenizer


def get_translator():
    """Charge le modèle de traduction NLLB (lazy loading)"""
    global _translator_model, _translator_tokenizer

    if not TORCH_AVAILABLE:
        return None, None

    if _translator_model is None:
        print("Chargement du modèle de traduction (NLLB-200)...")
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        _translator_tokenizer = AutoTokenizer.from_pretrained(settings.hf_translator_model)
        _translator_model = AutoModelForSeq2SeqLM.from_pretrained(settings.hf_translator_model)
        print("Modèle de traduction chargé!")

    return _translator_model, _translator_tokenizer


def translate_to_bambara(french_text: str) -> str:
    """Traduit du français vers le Bambara"""
    if not TORCH_AVAILABLE:
        return french_text  # Retourne le texte original si pas de torch

    model, tokenizer = get_translator()
    if model is None:
        return french_text

    tokenizer.src_lang = "fra_Latn"

    inputs = tokenizer(
        french_text,
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=512
    )

    forced_bos_token_id = tokenizer.convert_tokens_to_ids("bam_Latn")

    with torch.no_grad():
        generated_tokens = model.generate(
            **inputs,
            forced_bos_token_id=forced_bos_token_id,
            max_length=512
        )

    result = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)[0]
    return result


def find_ffmpeg():
    """Trouve le chemin de ffmpeg sur le systeme"""
    # Chemins possibles pour ffmpeg sur Windows
    possible_paths = [
        'ffmpeg',  # Dans le PATH
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
            # Utiliser ffmpeg pour la conversion
            result = subprocess.run([
                ffmpeg_path, '-y', '-i', wav_path,
                '-c:a', 'libopus', '-b:a', '64k',
                '-vbr', 'on', '-compression_level', '10',
                ogg_path
            ], capture_output=True, text=True, timeout=30)

            if result.returncode == 0 and os.path.exists(ogg_path):
                # Supprimer le fichier WAV temporaire
                os.remove(wav_path)
                print("Conversion WAV -> OGG reussie avec ffmpeg")
                return True
            else:
                print(f"Erreur ffmpeg: {result.stderr}")
        except Exception as e:
            print(f"Erreur ffmpeg: {e}")

    # Fallback: essayer avec pydub
    print("Essai avec pydub...")
    try:
        from pydub import AudioSegment
        # Configurer le chemin ffmpeg pour pydub
        if ffmpeg_path and ffmpeg_path != 'ffmpeg':
            AudioSegment.converter = ffmpeg_path
            ffprobe_path = ffmpeg_path.replace('ffmpeg.exe', 'ffprobe.exe')
            AudioSegment.ffprobe = ffprobe_path

        audio = AudioSegment.from_wav(wav_path)
        audio.export(ogg_path, format="ogg", codec="libopus", bitrate="64k")
        os.remove(wav_path)
        print("Conversion WAV -> OGG reussie avec pydub")
        return True
    except Exception as e:
        print(f"Erreur pydub: {e}")

    return False


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
            print("Fallback: utilisation du fichier WAV")
            return f"/static/audio/{wav_filename}"

    except Exception as e:
        print(f"Erreur TTS Bambara: {e}")

    return None


async def synthesize_bambara(french_text: str) -> tuple[str | None, str | None]:
    """Traduit du français vers le Bambara et génère l'audio"""
    if not TORCH_AVAILABLE or not french_text:
        return None, None

    try:
        bambara_text = translate_to_bambara(french_text)
        # Utiliser encode/decode pour éviter les erreurs d'encodage Windows
        try:
            print(f"Traduction: {french_text} -> {bambara_text}")
        except UnicodeEncodeError:
            print(f"Traduction effectuee (caracteres speciaux Bambara)")

        audio_url = synthesize_bambara_text(bambara_text)
        return audio_url, bambara_text

    except Exception as e:
        try:
            print(f"Erreur synthese Bambara: {e}")
        except UnicodeEncodeError:
            print("Erreur synthese Bambara (erreur encodage)")
        return None, None


def check_models_status() -> dict:
    """Vérifie le statut des modèles Hugging Face"""
    return {
        "torch_available": TORCH_AVAILABLE,
        "tts_loaded": _tts_model is not None,
        "translator_loaded": _translator_model is not None,
        "tts_model": settings.hf_tts_model,
        "translator_model": settings.hf_translator_model
    }
