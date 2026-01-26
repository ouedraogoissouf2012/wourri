"""
WOURI - TTS Français (Edge-TTS)
100% GRATUIT - Microsoft Edge TTS
Conversion en OGG Opus pour compatibilité WhatsApp
"""
import edge_tts
import uuid
import os
import re
import subprocess
from app.config import get_settings

settings = get_settings()

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
    Génère un fichier audio OGG Opus à partir de texte français
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
        mp3_filename = f"fr_{file_id}_temp.mp3"
        ogg_filename = f"fr_{file_id}.ogg"
        mp3_filepath = os.path.join(settings.audio_output_dir, mp3_filename)
        ogg_filepath = os.path.join(settings.audio_output_dir, ogg_filename)

        # Créer le dossier si nécessaire
        os.makedirs(settings.audio_output_dir, exist_ok=True)

        # Générer l'audio avec Edge-TTS (MP3 temporaire)
        communicate = edge_tts.Communicate(clean, settings.tts_french_voice)
        await communicate.save(mp3_filepath)

        # Convertir en OGG Opus pour WhatsApp
        if os.path.exists(mp3_filepath) and os.path.getsize(mp3_filepath) > 0:
            try:
                # Conversion MP3 -> OGG Opus (format WhatsApp)
                result = subprocess.run([
                    FFMPEG_PATH,
                    '-i', mp3_filepath,
                    '-c:a', 'libopus',
                    '-b:a', '64k',
                    '-ar', '48000',
                    '-ac', '1',
                    '-y',
                    ogg_filepath
                ], capture_output=True, timeout=30)

                # Supprimer le fichier MP3 temporaire
                os.remove(mp3_filepath)

                if os.path.exists(ogg_filepath) and os.path.getsize(ogg_filepath) > 0:
                    return f"/static/audio/{ogg_filename}"

            except Exception as conv_err:
                print(f"Erreur conversion ffmpeg: {conv_err}")
                # Fallback: retourner le MP3 si conversion échoue
                if os.path.exists(mp3_filepath):
                    final_mp3 = f"fr_{file_id}.mp3"
                    os.rename(mp3_filepath, os.path.join(settings.audio_output_dir, final_mp3))
                    return f"/static/audio/{final_mp3}"

    except Exception as e:
        print(f"Erreur TTS français: {e}")

    return None


async def get_available_voices() -> list[dict]:
    """Liste les voix françaises disponibles"""
    try:
        voices = await edge_tts.list_voices()
        french_voices = [
            {"name": v["Name"], "gender": v["Gender"], "locale": v["Locale"]}
            for v in voices
            if v["Locale"].startswith("fr-")
        ]
        return french_voices
    except:
        return []


# Voix recommandées
RECOMMENDED_VOICES = [
    "fr-FR-VivienneMultilingualNeural",  # Femme, multilingue, très naturelle (recommandée)
    "fr-FR-DeniseNeural",                 # Femme, standard
    "fr-FR-HenriNeural",                  # Homme, standard
    "fr-FR-EloiseNeural",                 # Femme, jeune
    "fr-FR-RemyMultilingualNeural",       # Homme, multilingue
]
