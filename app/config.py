"""
WOURI - Configuration
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
import os
import sys


class Settings(BaseSettings):
    """Configuration de l'application"""

    # Application
    app_name: str = "WOURI"
    app_version: str = "1.0.0"
    # ENV : "development" (défaut) ou "production"
    env: str = "development"
    # debug automatiquement False en production
    debug: bool = True

    # DeepSeek API
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # ========== CLOUD APIs (GRATUIT) ==========
    # Groq API (Whisper ASR)
    groq_api_key: str = ""

    # Note: Lingva Translate est utilise pour la traduction (pas de cle requise)

    # Open-Meteo (gratuit, pas de clé)
    openmeteo_base_url: str = "https://api.open-meteo.com/v1"

    # TTS - VivienneMultilingualNeural: voix féminine plus naturelle et expressive
    tts_french_voice: str = "fr-FR-VivienneMultilingualNeural"
    audio_output_dir: str = "static/audio"

    # Hugging Face (local, pas de clé requise)
    hf_tts_model: str = "facebook/mms-tts-bam"
    hf_translator_model: str = "facebook/nllb-200-distilled-600M"

    # Sécurité API (optionnel en dev, obligatoire en prod)
    # Mettre une valeur dans .env pour activer : API_SECRET_KEY=votre_cle_secrete
    api_secret_key: str = ""

    # Langue TTS ivoirienne par défaut
    default_ivorian_language: str = "bam"

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Retourne les settings (cached)"""
    s = Settings()
    # En production : forcer debug=False et exiger API_SECRET_KEY
    if s.is_production:
        if not s.api_secret_key:
            print(
                "[SECURITY] ERREUR : ENV=production mais API_SECRET_KEY est vide.\n"
                "Configurez API_SECRET_KEY dans .env avant de démarrer en production.",
                file=sys.stderr,
            )
            sys.exit(1)
        # Forcer debug=False même si le .env dit debug=True
        object.__setattr__(s, "debug", False)
    return s


# Créer le dossier audio si nécessaire
settings = get_settings()
os.makedirs(settings.audio_output_dir, exist_ok=True)
