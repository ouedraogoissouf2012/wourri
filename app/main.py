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
from app.middleware.admin_metrics import AdminMetricsMiddleware
from app.routers import weather, chat, tts, stt, rag, asr, feedback, admin
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
# Dossier logs canonique — source unique partagée avec la purge de rétention
# (ADR-0025) : writer et purge DOIVENT viser le même dossier.
from app.core.log_retention import DEFAULT_LOG_DIR
LOG_DIR = os.fspath(DEFAULT_LOG_DIR)
setup_logging(
    log_level="DEBUG" if settings.debug else "INFO",
    log_dir=LOG_DIR,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Préchargements de démarrage (issue #42, ADR-0011).
#
# Chaque _preload_* est autonome et testable unitairement : il journalise son
# résultat et retourne le NOM du service à signaler comme indisponible (ajouté
# à preload_issues), ou None si tout va bien. Les imports sont volontairement
# LAZY (dans le corps) pour ne pas charger torch/transformers à l'import du
# module. L'ordre d'exécution est significatif (NLU avant ASR, corpus après
# translation) et fixé par _run_preloads.
# ---------------------------------------------------------------------------


def _preload_nlu() -> str | None:
    """Précharge le service NLU (JSON seulement, très rapide ~10ms)."""
    try:
        from app.services.nlu import get_nlu_service
        logger.info("[PRELOAD] Chargement NLU (lexique concepts bambara)...")
        nlu = get_nlu_service()
        if nlu:
            stats = nlu.get_stats()
            logger.info("[PRELOAD] NLU: OK (%d concepts, %d mots-clés)", stats['total_concepts'], stats['total_keywords'])
        else:
            logger.warning("[PRELOAD] NLU: désactivé (fichier nlu_concepts.json non trouvé)")
            return "NLU"
    except Exception as e:
        logger.error("[PRELOAD] NLU: ERREUR - %s", e)
        return "NLU"
    return None


def _preload_translation() -> str | None:
    """Précharge le TranslationService (dictionnaire seul).

    NLLB-200 lazy-load (ADR-0011 Phase 3) : chargement à la 1re traduction
    hors-dictionnaire (rare car le dict couvre ~15779 mots BAM->FR +
    22010 mots FR->BAM, ~90% des usages typiques).
    Coût accepté : ~5-15s sur la 1re traduction NLLB par démarrage.
    """
    try:
        from app.services.translation import get_translation_service
        logger.info("[PRELOAD] Chargement du TranslationService (dictionnaire)...")
        service = get_translation_service()
        stats = service.get_stats()
        logger.info("[PRELOAD] Dictionnaire: OK (%d mots)", stats['dictionnaire']['total_mots'])
    except Exception as e:
        logger.error("[PRELOAD] TranslationService: ERREUR - %s", e)
        return "TranslationService"
    return None


def _preload_tts_bambara() -> str | None:
    """Précharge le TTS Bambara selon les flags (issue #42).

    enable_mms_bam=False : ne charge JAMAIS (économise ~3 GB RAM, TTS Bambara
      indisponible — pour profils Linux/Mac à RAM contrainte).
    preload_tts_bambara=False : ne pré-charge pas, charge au 1er appel.
    """
    if settings.enable_mms_bam and settings.preload_tts_bambara:
        try:
            from app.services.tts_bambara import get_tts_model
            logger.info("[PRELOAD] Chargement du TTS Bambara (mms-tts-bam)...")
            tts_bambara = get_tts_model()
            if not tts_bambara or not all(tts_bambara):
                logger.warning("[PRELOAD] TTS Bambara: INDISPONIBLE")
                return "TTS Bambara"
            logger.info("[PRELOAD] TTS Bambara: OK")
        except Exception as e:
            logger.error("[PRELOAD] TTS Bambara: ERREUR - %s", e)
            return "TTS Bambara"
    elif not settings.enable_mms_bam:
        logger.info("[PRELOAD] TTS Bambara: DESACTIVE (ENABLE_MMS_BAM=false)")
    else:
        logger.info("[PRELOAD] TTS Bambara: LAZY (PRELOAD_TTS_BAMBARA=false — chargement au 1er appel)")
    return None


def _preload_tts_dioula() -> str | None:
    """Précharge le TTS Dioula (voix ivoirienne) — flags identiques au Bambara."""
    if settings.enable_mms_dyu and settings.preload_tts_dioula:
        try:
            from app.services.tts_dioula import get_tts_model_dioula
            logger.info("[PRELOAD] Chargement du TTS Dioula (mms-tts-dyu)...")
            tts_dioula = get_tts_model_dioula()
            if not tts_dioula or not all(tts_dioula):
                logger.warning("[PRELOAD] TTS Dioula: INDISPONIBLE")
                return "TTS Dioula"
            logger.info("[PRELOAD] TTS Dioula: OK")
        except Exception as e:
            logger.error("[PRELOAD] TTS Dioula: ERREUR - %s", e)
            return "TTS Dioula"
    elif not settings.enable_mms_dyu:
        logger.info("[PRELOAD] TTS Dioula: DESACTIVE (ENABLE_MMS_DYU=false — economise ~3.8 GB)")
    else:
        logger.info("[PRELOAD] TTS Dioula: LAZY (PRELOAD_TTS_DIOULA=false — chargement au 1er appel)")
    return None


def _preload_corpus_ivr() -> str | None:
    """Pré-initialise le corpus IVR — backend pgvector unique (ADR-0008
    Phase E terminée, #203 : Chroma et la façade multi-backend retirés).

    Note : Whisper STT français reste en lazy-load (ADR-0011 Phase 3) —
    chargé à la 1re requête vocale FR (mode minoritaire), pas préchargé ici.
    """
    try:
        from app.services.corpus_service import initialiser_vdb
        logger.info("[PRELOAD] Initialisation BD vectorielle IVR (corpus bambara pré-validé)...")
        initialiser_vdb()
    except Exception as e:
        logger.error("[PRELOAD] BD vectorielle IVR: ERREUR - %s", e)
        return "BD vectorielle IVR"
    return None


def _preload_audio_cleanup() -> str | None:
    """Démarre le nettoyage automatique des fichiers audio."""
    try:
        from app.services.audio_cleanup import start_cleanup_scheduler
        start_cleanup_scheduler()
        logger.info("[PRELOAD] Nettoyage audio: OK (fichiers > 7j supprimés automatiquement)")
    except Exception as e:
        logger.error("[PRELOAD] Nettoyage audio: ERREUR - %s", e)
        return "Nettoyage audio"
    return None


# Ordre de préchargement (significatif) : NLU → Translation → TTS → corpus → cleanup.
# ASR : plus de preload NeMo (ADR-0027) ; MMS-dyu se charge au 1er vocal.
_PRELOADERS = (
    _preload_nlu,
    _preload_translation,
    _preload_tts_bambara,
    _preload_tts_dioula,
    _preload_corpus_ivr,
    _preload_audio_cleanup,
)


def _run_preloads() -> list[str]:
    """Exécute tous les préchargements dans l'ordre et retourne la liste des
    services indisponibles (best-effort : un échec n'interrompt pas les autres)."""
    issues: list[str] = []
    for preloader in _PRELOADERS:
        issue = preloader()
        if issue:
            issues.append(issue)
    return issues


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

    preload_issues = _run_preloads()

    # 7. Démarrer la purge de rétention des logs PII (issue #215, ADR-0025)
    try:
        from app.core.log_retention import start_log_retention_scheduler
        start_log_retention_scheduler(LOG_DIR)
        logger.info(
            "[PRELOAD] Rétention logs: OK (logs > %dj / feedback > %dj purgés)",
            settings.log_retention_days,
            settings.feedback_retention_days,
        )
    except Exception as e:
        logger.error("[PRELOAD] Rétention logs: ERREUR - %s", e)
        preload_issues.append("Rétention logs")

    if preload_issues:
        logger.warning(
            "[PRELOAD] Demarrage termine avec %d service(s) indisponible(s): %s",
            len(preload_issues),
            ", ".join(preload_issues),
        )
    else:
        logger.info("[PRELOAD] Tous les prechargements requis ont reussi!")
    logger.info("=" * 50)

    yield

    # Arrêt propre
    from app.core.log_retention import stop_log_retention_scheduler
    from app.services.audio_cleanup import stop_cleanup_scheduler
    from app.services.model_registry import registry
    stop_log_retention_scheduler()
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

    * **Météo** - Données météo en temps réel pour les villes ivoiriennes couvertes
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

# Rate limiting (issue #307, ADR-0018) : limite GLOBALE unique pilotée par
# RATE_LIMIT (.env, défaut 120/minute) via default_limits — AUCUN décorateur
# par route (un @limiter.limit override default_limits → config morte).
# Le trafic authentifié par clé API interne (whatsapp-server) est exempté par
# ApiKeyExemptRateLimitMiddleware (exemption cryptographique, pas de
# sentinelle IP → insensible à X-Forwarded-For).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Dashboard #41 / ADR-0017 : métadonnées techniques uniquement, jamais le
# corps, les headers, l'IP, le user_id, la transcription ou la query string.
app.add_middleware(AdminMetricsMiddleware)

# Ajouté APRÈS AdminMetricsMiddleware → s'exécute AVANT (plus externe) :
# une requête throttlée est rejetée au plus tôt, sans traverser la pile.
from app.middleware.rate_limit import ApiKeyExemptRateLimitMiddleware
app.add_middleware(ApiKeyExemptRateLimitMiddleware)

# Corrélation X-Request-ID (L5a #412) — ajouté en dernier ⇒ middleware le plus
# externe : request_id lu (ou généré) tôt, disponible pour tout le reste et
# renvoyé dans l'en-tête de réponse.
from app.middleware.request_id import RequestIdMiddleware
app.add_middleware(RequestIdMiddleware)

# CORS — dev : permissif ("*") pour l'interface locale showcase.html.
# Prod (L4 #411, ADR-0030) : allow-list explicite depuis ALLOWED_ORIGINS, jamais "*".
# Prod sans ALLOWED_ORIGINS => aucun middleware CORS (refus cross-origin par défaut, sûr).
if not settings.is_production:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
elif settings.cors_allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Monter les fichiers statiques
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates Jinja2
templates = Jinja2Templates(directory="templates")

# Inclure les routers
from app.routers import health_memory
app.include_router(health_memory.router)
app.include_router(weather.router)
app.include_router(chat.router)
app.include_router(tts.router)
app.include_router(stt.router)
app.include_router(rag.router)
app.include_router(asr.router)
app.include_router(feedback.router)
# Router admin opérateur (Phase D : /admin/corpus-divergence-report)
app.include_router(admin.router)
from app.routers import lqe
app.include_router(lqe.router)


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
@limiter.exempt
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
