"""
WOURI - TTS Français (Piper TTS)
100% GRATUIT - Voix locale haute qualité
Conversion en OGG Opus pour compatibilité WhatsApp
"""
import uuid
import os
import re
import subprocess
from app.config import get_settings

settings = get_settings()

# Chemins Piper TTS
PIPER_PATH = r"C:\piper-tts\piper.exe"
# Voix masculine Tom (homme français)
PIPER_MODEL = r"C:\piper-tts\fr_FR-tom-medium.onnx"

# Chemin vers ffmpeg
FFMPEG_PATH = r"C:\Users\USER PC\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"


def clean_text(text: str) -> str:
    """Nettoie le texte du markdown avant TTS"""
    # Supprimer le gras **text** ou __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    # Supprimer l'italique *text* ou _text_
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    # Supprimer les titres # ## ###
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    # Supprimer les puces - ou *
    text = re.sub(r'^[\-\*]\s+', '', text, flags=re.MULTILINE)
    # Supprimer les liens [text](url)
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    # Supprimer les backticks `code`
    text = re.sub(r'`(.+?)`', r'\1', text)
    # Nettoyer les espaces multiples
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


async def synthesize_french(text: str) -> str | None:
    """
    Génère un fichier audio OGG Opus à partir de texte français avec Piper TTS
    Format OGG Opus = format natif WhatsApp pour meilleure compatibilité

    Returns:
        str: URL relative du fichier audio (/static/audio/xxx.ogg)
    """
    if not text:
        return None

    # Nettoyer le texte
    clean = clean_text(text)
    if not clean:
        return None

    try:
        # Générer les noms de fichiers
        file_id = uuid.uuid4()
        wav_filename = f"fr_{file_id}_temp.wav"
        ogg_filename = f"fr_{file_id}.ogg"

        # Utiliser des chemins absolus pour Piper
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        audio_dir = os.path.join(base_dir, settings.audio_output_dir)
        wav_filepath = os.path.join(audio_dir, wav_filename)
        ogg_filepath = os.path.join(audio_dir, ogg_filename)

        # Créer le dossier si nécessaire
        os.makedirs(audio_dir, exist_ok=True)

        # Générer l'audio avec Piper TTS (chemins absolus obligatoires)
        piper_process = subprocess.run(
            [PIPER_PATH, '--model', PIPER_MODEL, '--output_file', wav_filepath],
            input=clean.encode('utf-8'),
            capture_output=True,
            timeout=30,
            cwd=r"C:\piper-tts"
        )

        # Convertir WAV en OGG Opus pour WhatsApp
        if os.path.exists(wav_filepath) and os.path.getsize(wav_filepath) > 0:
            try:
                # Conversion WAV -> OGG Opus (format WhatsApp)
                result = subprocess.run([
                    FFMPEG_PATH,
                    '-i', wav_filepath,
                    '-c:a', 'libopus',
                    '-b:a', '64k',
                    '-ar', '48000',
                    '-ac', '1',
                    '-y',
                    ogg_filepath
                ], capture_output=True, timeout=30)

                # Supprimer le fichier WAV temporaire
                os.remove(wav_filepath)

                if os.path.exists(ogg_filepath) and os.path.getsize(ogg_filepath) > 0:
                    return f"/static/audio/{ogg_filename}"

            except Exception as conv_err:
                print(f"Erreur conversion ffmpeg: {conv_err}")
                # Fallback: retourner le WAV si conversion échoue
                if os.path.exists(wav_filepath):
                    return f"/static/audio/{wav_filename}"

    except Exception as e:
        print(f"Erreur TTS français Piper: {e}")

    return None


async def get_available_voices() -> list[dict]:
    """Liste les voix Piper disponibles"""
    return [
        {"name": "fr_FR-tom-medium", "gender": "Male", "locale": "fr-FR", "quality": "medium"},
        {"name": "fr_FR-siwis-medium", "gender": "Female", "locale": "fr-FR", "quality": "medium"}
    ]


# Voix Piper installée (Tom = homme)
PIPER_VOICE = "fr_FR-tom-medium"
