"""
WOURI - TTS Dioula (Côte d'Ivoire)
100% GRATUIT - facebook/mms-tts-dyu + NLLB-200 (dyu_Latn)

Ce service est spécifique au Dioula ivoirien, distinct du Bambara malien.
Les deux langues sont mutuellement intelligibles mais ont des différences
de prononciation et de vocabulaire.

Modèles utilisés:
- TTS: facebook/mms-tts-dyu (Dioula)
- Traduction: facebook/nllb-200-distilled-600M (dyu_Latn)
"""
import uuid
import os
import subprocess
from app.config import get_settings

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
    print("INFO: torch non installé - TTS Dioula désactivé")

# Cache des modèles Dioula
_tts_model_dioula = None
_tts_tokenizer_dioula = None
_translator_model = None
_translator_tokenizer = None


def get_tts_model_dioula():
    """Charge le modèle TTS Dioula (lazy loading)"""
    global _tts_model_dioula, _tts_tokenizer_dioula

    if not TORCH_AVAILABLE:
        return None, None

    if _tts_model_dioula is None:
        print("Chargement du modèle TTS Dioula (mms-tts-dyu)...")
        from transformers import VitsModel, AutoTokenizer

        _tts_model_dioula = VitsModel.from_pretrained("facebook/mms-tts-dyu")
        _tts_tokenizer_dioula = AutoTokenizer.from_pretrained("facebook/mms-tts-dyu")
        print("Modèle TTS Dioula chargé!")

    return _tts_model_dioula, _tts_tokenizer_dioula


def get_translator():
    """Charge le modèle de traduction NLLB (lazy loading) - partagé"""
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


def translate_to_dioula(french_text: str) -> str:
    """Traduit du français vers le Dioula (dyu_Latn)"""
    if not TORCH_AVAILABLE:
        return french_text

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

    # Utiliser le code Dioula
    forced_bos_token_id = tokenizer.convert_tokens_to_ids("dyu_Latn")

    with torch.no_grad():
        generated_tokens = model.generate(
            **inputs,
            forced_bos_token_id=forced_bos_token_id,
            max_length=512,
            num_beams=5,              # Beam search pour meilleure qualité
            no_repeat_ngram_size=3,   # Éviter répétition de 3-grams
            repetition_penalty=1.2,   # Pénaliser les répétitions
            early_stopping=True
        )

    result = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)[0]

    # Nettoyer les répétitions éventuelles
    result = clean_repetitions(result)

    return result


def clean_repetitions(text: str) -> str:
    """Nettoie les répétitions dans le texte traduit"""
    if not text:
        return text

    words = text.split()
    if len(words) < 2:
        return text

    # Détecter et supprimer les répétitions de mots consécutifs
    cleaned_words = [words[0]]
    for i in range(1, len(words)):
        # Ne pas ajouter si c'est une répétition du mot précédent
        if words[i].lower() != words[i-1].lower():
            cleaned_words.append(words[i])

    # Détecter les répétitions de phrases
    result = ' '.join(cleaned_words)

    # Si le texte est très répétitif (plus de 50% de répétition), tronquer
    unique_words = set(w.lower() for w in cleaned_words)
    if len(unique_words) < len(cleaned_words) * 0.3:
        # Trop répétitif, garder seulement la première partie
        result = ' '.join(cleaned_words[:len(cleaned_words)//2])

    return result


def translate_dioula_to_french(dioula_text: str) -> str:
    """Traduit du Dioula vers le Français"""
    if not TORCH_AVAILABLE:
        return dioula_text

    model, tokenizer = get_translator()
    if model is None:
        return dioula_text

    tokenizer.src_lang = "dyu_Latn"

    inputs = tokenizer(
        dioula_text,
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=512
    )

    forced_bos_token_id = tokenizer.convert_tokens_to_ids("fra_Latn")

    with torch.no_grad():
        generated_tokens = model.generate(
            **inputs,
            forced_bos_token_id=forced_bos_token_id,
            max_length=512
        )

    result = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)[0]
    return result


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
    """Convertit un fichier WAV en OGG (Opus)"""
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

    # Fallback pydub
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


def synthesize_dioula_text(dioula_text: str) -> str | None:
    """Génère un fichier audio OGG à partir de texte Dioula"""
    if not TORCH_AVAILABLE or not dioula_text:
        return None

    try:
        model, tokenizer = get_tts_model_dioula()
        if model is None:
            return None

        inputs = tokenizer(dioula_text, return_tensors="pt")

        with torch.no_grad():
            output = model(**inputs).waveform

        waveform = output.squeeze().cpu().numpy()
        waveform = waveform / np.max(np.abs(waveform))
        waveform = (waveform * 32767).astype(np.int16)

        file_id = uuid.uuid4()
        wav_filename = f"dyu_{file_id}.wav"
        ogg_filename = f"dyu_{file_id}.ogg"
        wav_filepath = os.path.join(settings.audio_output_dir, wav_filename)
        ogg_filepath = os.path.join(settings.audio_output_dir, ogg_filename)
        os.makedirs(settings.audio_output_dir, exist_ok=True)

        wav.write(wav_filepath, rate=model.config.sampling_rate, data=waveform)

        if convert_wav_to_ogg(wav_filepath, ogg_filepath):
            if os.path.exists(ogg_filepath) and os.path.getsize(ogg_filepath) > 0:
                return f"/static/audio/{ogg_filename}"

        if os.path.exists(wav_filepath) and os.path.getsize(wav_filepath) > 0:
            return f"/static/audio/{wav_filename}"

    except Exception as e:
        print(f"Erreur TTS Dioula: {e}")

    return None


async def synthesize_dioula(french_text: str) -> tuple[str | None, str | None]:
    """Traduit du français vers le Dioula et génère l'audio"""
    if not TORCH_AVAILABLE or not french_text:
        return None, None

    try:
        dioula_text = translate_to_dioula(french_text)
        try:
            print(f"Traduction Dioula: {french_text[:50]}... -> {dioula_text[:50]}...")
        except UnicodeEncodeError:
            print("Traduction Dioula effectuée")

        audio_url = synthesize_dioula_text(dioula_text)
        return audio_url, dioula_text

    except Exception as e:
        print(f"Erreur synthèse Dioula: {e}")
        return None, None


def check_dioula_status() -> dict:
    """Vérifie le statut des modèles Dioula"""
    return {
        "torch_available": TORCH_AVAILABLE,
        "tts_loaded": _tts_model_dioula is not None,
        "translator_loaded": _translator_model is not None,
        "tts_model": "facebook/mms-tts-dyu",
        "translation_code": "dyu_Latn"
    }
