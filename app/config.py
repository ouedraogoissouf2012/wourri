"""
WOURI - Configuration
"""
from pydantic import Field
from pydantic_settings import BaseSettings
from functools import lru_cache
import logging
import os
import sys

from app.core.log_retention import (
    DEFAULT_FEEDBACK_RETENTION_DAYS,
    DEFAULT_LOG_RETENTION_DAYS,
)

logger = logging.getLogger(__name__)


# Issue #258 : helper extrait vers app/core/secrets.py (2e consommateur :
# app/db/url_resolver.py pour POSTGRES_PASSWORD_FILE). L'alias privé est
# conservé — get_settings() et les importeurs historiques restent valides.
from app.core.secrets import read_file_secret as _read_file_secret


class Settings(BaseSettings):
    """Configuration de l'application"""

    # Application
    app_name: str = "WOURI"
    app_version: str = "1.0.0"
    # ENV : "development" (défaut) ou "production"
    env: str = "development"
    # debug OFF par défaut — activer via DEBUG=true dans .env uniquement en développement
    # raison : expose stack traces + info-leak en cas d'accès accidentel prod
    debug: bool = False

    # DeepSeek API
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # ========== CLOUD APIs (GRATUIT) ==========
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

    # Issue #222 : clé précédente acceptée TEMPORAIREMENT pendant une rotation
    # zero-downtime de WOURI_API_KEY. Quand on rotate :
    #   1. Mettre API_SECRET_KEY_PREVIOUS=$OLD + API_SECRET_KEY=$NEW dans .env
    #   2. Restart wouri-api → accepte les 2 clés
    #   3. Restart whatsapp-server → envoie $NEW (peut envoyer $OLD à la marge)
    #   4. Vider API_SECRET_KEY_PREVIOUS après quelques minutes
    # Tant que cette var est définie, un warning est loggé au démarrage pour
    # alerter l'opérateur de purger après la fenêtre de rotation.
    api_secret_key_previous: str = ""

    # Langue TTS ivoirienne par défaut
    default_ivorian_language: str = "bam"

    # ========== Rétention logs PII (issue #215, ADR-0025) ==========
    # Durées de conservation appliquées par la purge quotidienne
    # (app/core/log_retention.py). Justifications : docs/compliance/artci-logs.md.
    # - logs applicatifs wourri-YYYY-MM-DD.log : transcriptions en clair → 30 j
    # - feedback-YYYY-MM.jsonl : pseudonymisés, reporting C5 saisonnier → 365 j
    # ge=1 : une rétention ≤ 0 rendrait le fichier du jour candidat à la purge
    # (perte des logs actifs) → refusée dès le chargement de la config.
    log_retention_days: int = Field(default=DEFAULT_LOG_RETENTION_DAYS, ge=1)
    feedback_retention_days: int = Field(default=DEFAULT_FEEDBACK_RETENTION_DAYS, ge=1)
    # Interrupteur de la purge (LOG_RETENTION_ENABLED) : False dans la suite de
    # tests (le lifespan TestClient purgerait le logs/ RÉEL du repo) et pour un
    # gel ops ponctuel. La politique ARTCI exige True en production.
    log_retention_enabled: bool = True

    # ========== Sécurité PII (P0-05) ==========
    # Salt pour anonymisation SHA-256 des user_id dans les logs
    # Générer une valeur aléatoire stable en prod :
    #   python -c "import secrets; print(secrets.token_hex(32))"
    # Laisser vide en dev (warn sera émis au premier appel)
    pii_salt: str = ""

    # ========== ASR Quality Gate ==========
    # Langue cible pour le gate ASR (filtre blocklist par langue).
    asr_language: str = "dyu"

    # NOTE (issue #339) : le setting `asr_vocab_sources` a été RETIRÉ. C'était du
    # dead config : aucun code ne le lisait, et le `VocabularyRegistry` / `_EXTRACTORS`
    # décrits dans ses commentaires n'ont jamais existé. Le vocabulaire réellement
    # utilisé est chargé par des chemins dédiés :
    #   - normalisation post-ASR  → app/services/asr_normalizer.py (nlu_concepts.json)
    #   - quality gate agricole   → app/services/asr/chain.py (AGRI_KEYWORDS hardcodés)
    #   - filtre langue OOV       → app/services/validation/lm_filter.py (lexique en paramètre)
    # Les datasets data/hf_datasets/{koumankan,findora}.json restent sur disque pour
    # le fine-tuning ASR (cf. finetune/), pas pour le runtime.

    # Blocklist d'hallucinations ASR (fichier JSON éditable).
    asr_hallucinations_path: str = "data/asr_hallucinations_dyu.json"

    # ========== PostgreSQL + pgvector (Sprint F — ADR-0008) ==========
    # URL de connexion Postgres au format psycopg :
    #   postgresql+psycopg://user:password@host:port/database
    # Valeur par défaut vide : Phase B est purement additive, aucun code prod
    # ne se connecte à Postgres tant que Phase C (adapter + double-écriture)
    # n'est pas livrée. Le script `scripts/import_corpus_ivr.py` et les tests
    # d'intégration construisent leur propre URL à partir des variables
    # POSTGRES_* du .env quand `postgres_url` n'est pas défini.
    postgres_url: str = ""

    # NOTE (#203, ADR-0008 Phase E terminée) : le feature flag
    # `corpus_storage_mode` a été RETIRÉ — pgvector est le backend corpus
    # unique (ChromaDB supprimé : incompatible numpy 2.x, np.float_ removed).
    # Un CORPUS_STORAGE_MODE résiduel dans un .env est ignoré sans erreur
    # (Config.extra = "ignore").

    # ========== Dashboard opérateur sans PII (issue #41, ADR-0017) ==========
    # Enregistre dans PostgreSQL uniquement des métadonnées techniques :
    # route normalisée, statut, durée, intent/culture/source internes et
    # indicateurs ASR/NLU. Aucun message, transcription, user_id ou IP.
    # Best-effort : si PostgreSQL est absent, les routes restent fonctionnelles.
    admin_metrics_enabled: bool = True

    # ========== Piper TTS (FR + EN) — portabilité OS ==========
    # Tous les chemins sont configurables via env var. Defaults universellement
    # portables (binaire dans PATH système + modèles via env explicite). Aucun
    # chemin Windows hardcoded.
    #
    # Exemples par OS :
    #   Linux/Mac (binaire installé via package ou wget) :
    #     PIPER_PATH=piper
    #     PIPER_MODEL_FR=/opt/piper-voices/fr_FR-tom-medium.onnx
    #     PIPER_MODEL_EN=/opt/piper-voices/en_US-amy-medium.onnx
    #   Windows :
    #     PIPER_PATH=C:\piper-tts\piper.exe
    #     PIPER_MODEL_FR=C:\piper-tts\fr_FR-tom-medium.onnx
    #     PIPER_MODEL_EN=C:\piper-tts\en_US-amy-medium.onnx
    #
    # Comportement défaut (env vars vides) : le binaire est cherché dans PATH
    # via "piper" et les modèles non configurés désactivent silencieusement le
    # TTS de la langue concernée (graceful degradation — pas de crash).
    piper_path: str = "piper"
    piper_model_fr: str = ""
    piper_model_en: str = ""

    # ========== Performance — feature flags + lazy load (issue #42) ==========
    # Permet de désactiver entièrement ou de différer le chargement des modèles
    # ML lourds pour réduire la RAM au démarrage. Indispensable sur Windows
    # 8 GB (page file limité → crashes mkl_malloc avec ~7-8 GB de modèles
    # chargés simultanément).
    #
    # ## Flags d'activation (enable_*) : désactive complètement le modèle
    # Si False : le modèle n'est ni pré-chargé ni chargeable. Les endpoints
    # concernés retournent 503 (Service Unavailable).
    #
    # ## Flags de pré-chargement (preload_*) : différe le chargement
    # Si False : le modèle reste « chargeable » mais n'est pas pré-chargé au
    # démarrage. Il est chargé au premier appel (via `model_registry`) avec
    # un coût latence de premier appel (~5-30s selon le modèle).
    #
    # ## Profils mémoire typiques (estimation après mesures empiriques)
    #   - Minimal (EN/FR + dioula lazy)        : ~3-4 GB  (whisper off, mms_dyu lazy)
    #   - Standard (config actuelle)            : ~7-8 GB
    #   - Full (tous pré-chargés)               : ~9-10 GB
    enable_whisper: bool = True
    enable_mms_dyu: bool = True
    enable_mms_bam: bool = True
    preload_tts_dioula: bool = True
    preload_tts_bambara: bool = True

    # ========== Omnilingual ASR (ADR-0002, ADR-0003) ==========
    # Provider Omnilingual créé en Phase 2 mais NON activé dans la chain
    # (sera activé en Phase 4 après benchmark Phase 3).
    # Voir docs/benchmarks/0002-omnilingual-env-setup.md pour install reproductible.
    omnilingual_enabled: bool = False
    # Variante : "300m", "1b", "1.2b", "7b" (cf. MODEL_CARDS dans omnilingual_provider.py)
    omnilingual_model_size: str = "300m"
    # Code langue {lang}_{script} parmi les 1672 langues supportées (ex: "dyu_Latn", "bam_Latn")
    omnilingual_default_lang: str = "dyu_Latn"

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # Tolère les variables du .env lues ailleurs via os.getenv (FFMPEG_PATH
        # par app/services/_ffmpeg.py, HF_TOKEN par les services HuggingFace...)
        # sans les redéclarer ici. Sans ça, Pydantic lève extra_forbidden et
        # l'API ne démarre pas quand ces variables sont présentes dans .env.
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Retourne les settings (cached).

    Issues #213 + #259 : si `API_SECRET_KEY_FILE` / `API_SECRET_KEY_PREVIOUS_FILE`
    sont définis (pattern Docker secrets), leur contenu OVERRIDE les
    valeurs lues depuis `.env`. Cela permet de stocker les secrets dans
    des fichiers mode 0600 sur la VM plutôt que dans des env vars
    (visibles via `docker inspect`).
    """
    # Construire les overrides depuis Docker secrets si présents.
    overrides: dict[str, str] = {}
    if file_secret := _read_file_secret("API_SECRET_KEY"):
        overrides["api_secret_key"] = file_secret
    # Issue #259 : clé PRÉCÉDENTE en fichier (rotation zero-downtime sans
    # remettre de clé en clair dans l'env). Fichier vide (état normal hors
    # rotation) → pas d'override → fallback env/.env, '' par défaut.
    if file_secret := _read_file_secret("API_SECRET_KEY_PREVIOUS"):
        overrides["api_secret_key_previous"] = file_secret

    s = Settings(**overrides)
    # En production : forcer debug=False et exiger API_SECRET_KEY
    if s.is_production:
        if not s.api_secret_key:
            logger.critical(
                "[SECURITY] ERREUR : ENV=production mais API_SECRET_KEY est vide. "
                "Configurez API_SECRET_KEY dans .env avant de démarrer en production."
            )
            sys.exit(1)
        # Forcer debug=False même si le .env dit debug=True
        object.__setattr__(s, "debug", False)
    return s


# Créer le dossier audio si nécessaire
settings = get_settings()
os.makedirs(settings.audio_output_dir, exist_ok=True)
