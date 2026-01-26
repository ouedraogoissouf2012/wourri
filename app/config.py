"""
WOURI - Configuration
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    """Configuration de l'application"""

    # Application
    app_name: str = "WOURI"
    app_version: str = "1.0.0"
    debug: bool = True

    # DeepSeek API
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # Open-Meteo (gratuit, pas de clé)
    openmeteo_base_url: str = "https://api.open-meteo.com/v1"

    # TTS - VivienneMultilingualNeural: voix féminine plus naturelle et expressive
    tts_french_voice: str = "fr-FR-VivienneMultilingualNeural"
    audio_output_dir: str = "static/audio"

    # Hugging Face (local, pas de clé requise)
    hf_tts_model: str = "facebook/mms-tts-bam"
    hf_translator_model: str = "facebook/nllb-200-distilled-600M"

    # Langue TTS ivoirienne par défaut
    default_ivorian_language: str = "bam"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Retourne les settings (cached)"""
    return Settings()


# Créer le dossier audio si nécessaire
settings = get_settings()
os.makedirs(settings.audio_output_dir, exist_ok=True)
