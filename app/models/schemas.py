"""
WOURI - Pydantic Schemas
"""
from pydantic import BaseModel
from enum import Enum
from typing import Optional


class Language(str, Enum):
    """Langues supportées pour les réponses.

    Ajout ENGLISH (ADR-0015 PR 4/4) : mode passthrough via DeepSeek direct,
    pour démos investisseurs et préparation expansion anglophone. Cf. ADR
    docs/adr/0015-strategy-pattern-cascade-chat-et-anglais.md.
    """
    FRENCH = "french"
    DIOULA = "dioula"
    BOTH = "both"  # Français ET Dioula
    ENGLISH = "english"  # ADR-0015 PR 4/4 : passthrough DeepSeek direct + Piper TTS EN


class IvorianLanguage(str, Enum):
    """Langues ivoiriennes TTS disponibles (Facebook MMS).

    IMPORTANT: doit rester synchronisé avec SUPPORTED_LANGUAGES dans app/data/constants.py
    """
    BAMBARA = "bam"       # Bambara/Dioula
    ATTIE = "ati"         # Attié
    SENOUFO_DJIMINI = "dyi"  # Sénoufo Djimini
    SENOUFO_MAMARA = "myk"   # Sénoufo Mamara
    DIDA = "gud"          # Dida Yocoboué
    ADIOUKROU = "adj"     # Adioukrou
    DAN = "dnj"           # Dan/Yacouba
    WOBE = "wob"          # Wobé


class ChatRequest(BaseModel):
    """Requête de chat"""
    message: str
    city: str = "Abidjan"
    language: Language = Language.BOTH  # Par défaut: les deux langues
    include_audio: bool = True
    user_id: Optional[str] = None  # ID utilisateur pour l'historique de conversation
    bambara_text: Optional[str] = None  # Transcription bambara brute (ASR) pour NLU


class ChatResponse(BaseModel):
    """Réponse de chat"""
    response: str
    response_dioula: Optional[str] = None  # Traduction Dioula/Bambara
    response_local: Optional[str] = None   # Texte dans la langue locale (si différent de Dioula)
    audio_url: Optional[str] = None
    city: str
    language: str
    audio_language: Optional[str] = None   # Langue de l'audio généré
    meta: Optional[dict] = None            # Métadonnées NLU pour C4 feedback: {intent, cultures, source}


class WeatherRequest(BaseModel):
    """Requête météo"""
    city: str


class WeatherData(BaseModel):
    """Données météo"""
    city: str
    region: str
    temperature: float
    humidity: int
    precipitation: float
    wind_speed: float
    weather_code: int
    weather_description: str
    advice: str


class TTSRequest(BaseModel):
    """Requête TTS"""
    text: str
    language: Language = Language.FRENCH


class TTSResponse(BaseModel):
    """Réponse TTS"""
    audio_url: str
    text: str
    language: str


class TranslateRequest(BaseModel):
    """Requête de traduction"""
    text: str
    source: str = "fra_Latn"
    target: str = "bam_Latn"


class TranslateResponse(BaseModel):
    """Réponse de traduction"""
    original: str
    translated: str
    source: str
    target: str


class CityInfo(BaseModel):
    """Informations sur une ville"""
    name: str
    lat: float
    lon: float
    region: str


class HealthResponse(BaseModel):
    """Réponse de santé"""
    status: str
    app_name: str
    version: str
    services: dict
