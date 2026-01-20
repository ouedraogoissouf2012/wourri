"""
WOURI - Speech-to-Text avec Whisper
100% GRATUIT - OpenAI Whisper (local)

NOTE: Necessite openai-whisper
Pour installer: pip install openai-whisper
"""
import os
import uuid
import tempfile
from app.config import get_settings

settings = get_settings()

# Verifier si whisper est disponible
WHISPER_AVAILABLE = False
whisper = None

try:
    import whisper as _whisper
    whisper = _whisper
    WHISPER_AVAILABLE = True
except ImportError:
    print("INFO: whisper non installe - STT desactive")
    print("Pour activer: pip install openai-whisper")

# Cache du modele
_whisper_model = None
_model_name = "base"  # tiny, base, small, medium, large


def get_whisper_model(model_name: str = None):
    """Charge le modele Whisper (lazy loading)"""
    global _whisper_model, _model_name

    if not WHISPER_AVAILABLE:
        return None

    if model_name:
        _model_name = model_name

    if _whisper_model is None:
        print(f"Chargement du modele Whisper ({_model_name})...")
        _whisper_model = whisper.load_model(_model_name)
        print(f"Modele Whisper ({_model_name}) charge!")

    return _whisper_model


def transcribe_audio(audio_path: str, language: str = "fr") -> dict | None:
    """
    Transcrit un fichier audio en texte.

    Args:
        audio_path: Chemin vers le fichier audio (mp3, wav, ogg, etc.)
        language: Code langue (fr, en, bam, etc.) ou None pour detection auto

    Returns:
        dict avec 'text', 'language', 'segments' ou None si erreur
    """
    if not WHISPER_AVAILABLE:
        return None

    if not os.path.exists(audio_path):
        print(f"Fichier audio non trouve: {audio_path}")
        return None

    try:
        model = get_whisper_model()
        if model is None:
            return None

        # Options de transcription
        options = {
            "fp16": False,  # Desactive pour compatibilite CPU
        }

        if language:
            options["language"] = language

        # Transcrire
        result = model.transcribe(audio_path, **options)

        return {
            "text": result["text"].strip(),
            "language": result.get("language", language),
            "segments": [
                {
                    "start": seg["start"],
                    "end": seg["end"],
                    "text": seg["text"].strip()
                }
                for seg in result.get("segments", [])
            ]
        }

    except Exception as e:
        print(f"Erreur transcription Whisper: {e}")
        return None


async def transcribe_audio_bytes(audio_bytes: bytes, filename: str = "audio.wav", language: str = "fr") -> dict | None:
    """
    Transcrit des bytes audio en texte.

    Args:
        audio_bytes: Contenu audio en bytes
        filename: Nom du fichier (pour determiner l'extension)
        language: Code langue

    Returns:
        dict avec 'text', 'language', 'segments' ou None si erreur
    """
    if not WHISPER_AVAILABLE or not audio_bytes:
        return None

    # Determiner l'extension
    ext = os.path.splitext(filename)[1] or ".wav"

    # Sauvegarder temporairement
    temp_path = os.path.join(tempfile.gettempdir(), f"whisper_{uuid.uuid4()}{ext}")

    try:
        with open(temp_path, "wb") as f:
            f.write(audio_bytes)

        result = transcribe_audio(temp_path, language)
        return result

    finally:
        # Nettoyer le fichier temporaire
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass


def check_whisper_status() -> dict:
    """Verifie le statut de Whisper"""
    return {
        "whisper_available": WHISPER_AVAILABLE,
        "model_loaded": _whisper_model is not None,
        "model_name": _model_name,
        "supported_languages": ["fr", "en", "bam", "wo", "ff"]  # Langues principales
    }
