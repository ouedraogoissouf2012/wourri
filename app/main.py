"""
WOURI - Application FastAPI
Assistant agricole intelligent pour la Côte d'Ivoire
"""
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
import os
import psutil

from app.core.logging_config import setup_logging
from app.config import get_settings
from app.routers import weather, chat, tts, stt, rag, asr, feedback
from app.services.deepseek import check_deepseek_status
from app.services.tts_bambara import check_models_status
from app.services.stt_whisper import check_whisper_status
from app.services.rag_knowledge import check_rag_status
from app.services.model_registry import registry
from app.data.cities import get_all_cities

# Process psutil partagé (ADR-0011 Phase 4) pour /health
# psutil.Process() sans argument = process Python courant
_psutil_proc = psutil.Process()

settings = get_settings()
setup_logging(
    log_level="DEBUG" if settings.debug else "INFO",
    log_dir=os.path.join(os.path.dirname(__file__), "..", "logs"),
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestion du cycle de vie de l'application"""
    logger.info("=" * 50)
    logger.info("WOURI - Démarrage")
    logger.info("=" * 50)
    logger.info("Version: %s", settings.app_version)
    logger.info("Debug: %s", settings.debug)
    logger.info("Villes disponibles: %d", len(get_all_cities()))
    logger.info("=" * 50)

    # 0. Précharger le service NLU (JSON seulement, très rapide ~10ms)
    try:
        from app.services.nlu import get_nlu_service
        logger.info("[PRELOAD] Chargement NLU (lexique concepts bambara)...")
        nlu = get_nlu_service()
        if nlu:
            stats = nlu.get_stats()
            logger.info("[PRELOAD] NLU: OK (%d concepts, %d mots-clés)", stats['total_concepts'], stats['total_keywords'])
        else:
            logger.warning("[PRELOAD] NLU: désactivé (fichier nlu_concepts.json non trouvé)")
    except Exception as e:
        logger.error("[PRELOAD] NLU: ERREUR - %s", e)

    # 1. Précharger ASR NeMo Soloni (decodeur TDT complet, bambara)
    try:
        from app.services.asr_soloni_nemo import get_nemo_model
        logger.info("[PRELOAD] Chargement ASR NeMo Soloni (TDT, bambara)...")
        get_nemo_model()
        logger.info("[PRELOAD] ASR NeMo Soloni: OK")
    except Exception as e:
        logger.error("[PRELOAD] ASR NeMo Soloni: ERREUR - %s", e)

    # 2. Précharger le TranslationService (dictionnaire seul)
    # NLLB-200 lazy-load (ADR-0011 Phase 3) : chargement à la 1re traduction
    # hors-dictionnaire (rare car le dict couvre ~15779 mots BAM->FR +
    # 22010 mots FR->BAM, ~90% des usages typiques).
    # Coût accepté : ~5-15s sur la 1re traduction NLLB par démarrage.
    try:
        from app.services.translation import get_translation_service
        logger.info("[PRELOAD] Chargement du TranslationService (dictionnaire)...")
        service = get_translation_service()
        stats = service.get_stats()
        logger.info("[PRELOAD] Dictionnaire: OK (%d mots)", stats['dictionnaire']['total_mots'])
    except Exception as e:
        logger.error("[PRELOAD] TranslationService: ERREUR - %s", e)

    # 3. Précharger TTS Bambara
    try:
        from app.services.tts_bambara import get_tts_model
        logger.info("[PRELOAD] Chargement du TTS Bambara (mms-tts-bam)...")
        get_tts_model()
        logger.info("[PRELOAD] TTS Bambara: OK")
    except Exception as e:
        logger.error("[PRELOAD] TTS Bambara: ERREUR - %s", e)

    # 3b. Précharger TTS Dioula (voix ivoirienne pour utilisateurs en mode dioula)
    try:
        from app.services.tts_dioula import get_tts_model_dioula
        logger.info("[PRELOAD] Chargement du TTS Dioula (mms-tts-dyu)...")
        get_tts_model_dioula()
        logger.info("[PRELOAD] TTS Dioula: OK")
    except Exception as e:
        logger.error("[PRELOAD] TTS Dioula: ERREUR - %s", e)

    # 4. Whisper STT français : lazy-load (ADR-0011 Phase 3)
    # Chargement à la 1re requête vocale FR (mode `french` minoritaire selon
    # le profil utilisateur cible : agriculteurs dioula majoritairement
    # peu alphabétisés, modes `dioula`/`both` dominants).
    # Coût accepté : ~30-60s sur le 1er vocal FR par démarrage.
    # Timeout côté WhatsApp Baileys = 180s, marge confortable.

    # 5. Pré-initialiser la BD vectorielle IVR via la façade ADR-0008 §Phase C
    # (mode `chroma` défaut → équivalent à initialiser_vdb legacy ;
    #  mode `dual` → préchargement chroma + pgvector ; mode `pgvector` → pgvector seul)
    try:
        from app.services.corpus_facade import initialiser_vdb
        logger.info("[PRELOAD] Initialisation BD vectorielle IVR (corpus bambara pré-validé)...")
        initialiser_vdb()
    except Exception as e:
        logger.error("[PRELOAD] BD vectorielle IVR: ERREUR - %s", e)

    # 6. Démarrer le nettoyage automatique des fichiers audio
    try:
        from app.services.audio_cleanup import start_cleanup_scheduler
        start_cleanup_scheduler()
        logger.info("[PRELOAD] Nettoyage audio: OK (fichiers > 7j supprimés automatiquement)")
    except Exception as e:
        logger.error("[PRELOAD] Nettoyage audio: ERREUR - %s", e)

    logger.info("[PRELOAD] Tous les modeles charges!")
    logger.info("=" * 50)

    yield

    # Arrêt propre
    from app.services.audio_cleanup import stop_cleanup_scheduler
    from app.services.model_registry import registry
    stop_cleanup_scheduler()
    registry.unload_all()
    logger.info("WOURI - Arrêt")


# Créer l'application FastAPI
from app.security import limiter

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

# Rate limiting — 10 req/min par IP
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — permissif uniquement en dev (test interface locale showcase.html)
# En production, restreindre via une allow-list explicite (ADR-0011 futur).
if not settings.is_production:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
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
app.include_router(feedback.router)


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
    """Verifie l'etat de l'application + observabilité modèles ML.

    Le bloc `models` (ADR-0011 Phase 4) permet à un opérateur ou monitoring
    de visualiser quels modèles sont actuellement chargés en RAM via le
    `ModelRegistry`, ainsi que l'empreinte mémoire totale du process Python
    (RSS = mémoire physique résidente, VMS = mémoire virtuelle).
    """
    deepseek_ok = await check_deepseek_status()
    hf_status = check_models_status()
    whisper_status = check_whisper_status()
    rag_status = check_rag_status()

    # Observabilité ML (ADR-0011 Phase 4)
    loaded_keys = sorted(registry.list_loaded())
    mem_info = _psutil_proc.memory_info()

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
        },
        "models": {
            "registry": {
                "loaded_keys": loaded_keys,
                "count": len(loaded_keys),
            },
            "process": {
                "rss_mb": round(mem_info.rss / (1024 * 1024), 1),
                "vms_mb": round(mem_info.vms / (1024 * 1024), 1),
            },
        },
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
