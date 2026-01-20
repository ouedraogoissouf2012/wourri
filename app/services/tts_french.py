"""
WOURI - TTS Français (Edge-TTS)
100% GRATUIT - Microsoft Edge TTS
"""
import edge_tts
import uuid
import os
import re
from app.config import get_settings

settings = get_settings()


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
    Génère un fichier audio MP3 à partir de texte français

    Returns:
        str: URL relative du fichier audio (/static/audio/xxx.mp3)
    """
    if not text:
        return None

    # Nettoyer le texte
    clean = clean_text(text)
    if not clean:
        return None

    try:
        # Générer le nom du fichier
        filename = f"fr_{uuid.uuid4()}.mp3"
        filepath = os.path.join(settings.audio_output_dir, filename)

        # Créer le dossier si nécessaire
        os.makedirs(settings.audio_output_dir, exist_ok=True)

        # Générer l'audio avec Edge-TTS
        communicate = edge_tts.Communicate(clean, settings.tts_french_voice)
        await communicate.save(filepath)

        # Vérifier que le fichier a été créé
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            return f"/static/audio/{filename}"

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
    "fr-FR-DeniseNeural",      # Femme, standard (recommandée)
    "fr-FR-HenriNeural",        # Homme, standard
    "fr-FR-EloiseNeural",       # Femme, jeune
    "fr-FR-RemyMultilingualNeural",  # Homme, multilingue
]
