"""
WOURI - Application FastAPI
Assistant agricole intelligent pour la Côte d'Ivoire
"""
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
import os

from app.config import get_settings
from app.routers import weather, chat, tts, stt, rag, asr
from app.services.deepseek import check_deepseek_status
from app.services.tts_bambara import check_models_status
from app.services.stt_whisper import check_whisper_status
from app.services.rag_knowledge import check_rag_status
from app.data.cities import get_all_cities

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestion du cycle de vie de l'application"""
    print("=" * 50)
    print("WOURI - Démarrage")
    print("=" * 50)
    print(f"Version: {settings.app_version}")
    print(f"Debug: {settings.debug}")
    print(f"Villes disponibles: {len(get_all_cities())}")
    print("=" * 50)

    # Précharger les modèles pour des réponses plus rapides
    print("\n[PRELOAD] Chargement des modèles en arrière-plan...")

    # 1. Précharger Faster-Whisper (STT)
    try:
        from app.services.stt_whisper import get_whisper_model
        print("[PRELOAD] Chargement de Faster-Whisper (large-v3-turbo)...")
        get_whisper_model()
        print("[PRELOAD] Faster-Whisper: OK")
    except Exception as e:
        print(f"[PRELOAD] Whisper: ERREUR - {e}")

    # 2. Précharger le TranslationService (dictionnaire + NLLB)
    try:
        from app.services.translation import get_translation_service
        print("[PRELOAD] Chargement du TranslationService (dictionnaire + NLLB)...")
        service = get_translation_service()
        stats = service.get_stats()
        print(f"[PRELOAD] TranslationService: OK ({stats['dictionnaire']['total_mots']} mots)")
    except Exception as e:
        print(f"[PRELOAD] TranslationService: ERREUR - {e}")

    # 3. Précharger TTS Bambara
    try:
        from app.services.tts_bambara import get_tts_model
        print("[PRELOAD] Chargement de TTS Bambara...")
        get_tts_model()
        print("[PRELOAD] TTS Bambara: OK")
    except Exception as e:
        print(f"[PRELOAD] TTS Bambara: ERREUR - {e}")

    print("\n[PRELOAD] Tous les modèles sont chargés!")
    print("=" * 50)

    yield
    print("WOURI - Arrêt")


# Créer l'application FastAPI
app = FastAPI(
    title="WOURI API",
    description="""
    🌾 **WOURI** - Assistant agricole intelligent pour les agriculteurs de Côte d'Ivoire

    ## Fonctionnalités

    * **Météo** - Données météo en temps réel pour 60 villes ivoiriennes
    * **Chat IA** - Assistant conversationnel avec conseils agricoles
    * **TTS Français** - Synthèse vocale en français (Edge-TTS)
    * **TTS Bambara** - Synthèse vocale en Bambara/Dioula (Hugging Face)
    * **Traduction** - Français → Bambara

    ## Technologies

    * FastAPI + Python
    * DeepSeek AI (Chat)
    * Open-Meteo (Météo gratuite)
    * Edge-TTS (TTS français)
    * Hugging Face (TTS + Traduction Bambara)
    """,
    version=settings.app_version,
    lifespan=lifespan
)

# Monter les fichiers statiques
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates Jinja2
templates = Jinja2Templates(directory="templates")

# Inclure les routers
app.include_router(weather.router)
app.include_router(chat.router)
app.include_router(tts.router)
app.include_router(stt.router)
app.include_router(rag.router)
app.include_router(asr.router)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Page d'accueil avec interface de test"""
    cities = get_all_cities()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "cities": cities,
            "app_name": settings.app_name,
            "version": settings.app_version
        }
    )


@app.get("/health")
async def health():
    """Verifie l'etat de l'application"""
    deepseek_ok = await check_deepseek_status()
    hf_status = check_models_status()
    whisper_status = check_whisper_status()
    rag_status = check_rag_status()

    return {
        "status": "ok",
        "app_name": settings.app_name,
        "version": settings.app_version,
        "services": {
            "deepseek": deepseek_ok,
            "weather": True,  # Open-Meteo est toujours disponible
            "tts_french": True,  # Edge-TTS est toujours disponible
            "tts_bambara": hf_status,
            "stt_whisper": whisper_status,
            "rag_knowledge": rag_status
        }
    }


@app.get("/api")
async def api_info():
    """Informations sur l'API"""
    return {
        "name": "WOURI API",
        "version": settings.app_version,
        "endpoints": {
            "weather": "/api/weather/{city}",
            "chat": "/api/chat/",
            "tts": "/api/tts/",
            "tts_ivorian": "/api/tts/ivorian/{language_code}",
            "stt": "/api/stt/transcribe",
            "asr": "/api/asr/transcribe",
            "asr_translate": "/api/asr/transcribe-and-translate",
            "rag": "/api/rag/search",
            "translate": "/api/tts/translate",
            "cities": "/api/weather/cities/list"
        },
        "docs": "/docs"
    }
