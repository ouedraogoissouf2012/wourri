"""
WOURI - Configuration
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path
from typing import Literal
import os
import sys


def _read_file_secret(name: str) -> str:
    """Lit le contenu du fichier référencé par `{NAME}_FILE` env var.

    Issue #213 — pattern Docker secrets. Le compose monte les fichiers de
    secrets dans `/run/secrets/<nom>`, puis définit dans environment :
        API_SECRET_KEY_FILE=/run/secrets/api_secret_key
    Pydantic Settings lit la valeur d'env `API_SECRET_KEY` (vide), donc on
    surcharge dans `get_settings()` en lisant le fichier ici.

    Backward-compat : si `{NAME}_FILE` n'est pas défini OU le fichier est
    introuvable, retourne `""` → l'opérateur qui n'a pas migré garde le
    comportement précédent (lecture depuis `.env`).
    """
    file_path = os.getenv(f"{name}_FILE")
    if not file_path:
        return ""
    p = Path(file_path)
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8").strip()


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

    # ========== Sécurité PII (P0-05) ==========
    # Salt pour anonymisation SHA-256 des user_id dans les logs
    # Générer une valeur aléatoire stable en prod :
    #   python -c "import secrets; print(secrets.token_hex(32))"
    # Laisser vide en dev (warn sera émis au premier appel)
    pii_salt: str = ""

    # ========== ASR Quality Gate ==========
    # Langue cible pour le gate ASR (filtre blocklist par langue).
    asr_language: str = "dyu"

    # Sources de vocabulaire à charger dans VocabularyRegistry.
    # Chaque entrée : {name, path (relatif à wouri-api/), schema (clé dans _EXTRACTORS)}.
    # Override via .env en JSON : ASR_VOCAB_SOURCES='[{"name":"...","path":"...","schema":"..."}]'
    asr_vocab_sources: list[dict] = [
        {
            "name": "koumankan",
            "path": "data/hf_datasets/koumankan_dyu_fr.json",
            "schema": "list_dict_translation_dyu",
        },
        {
            "name": "findora",
            "path": "data/hf_datasets/findora_fr_dioula.json",
            "schema": "list_dict_flat_dioula",
        },
        {
            "name": "ivr",
            "path": "dictionnaires/corpus_ivr.json",
            "schema": "ivr_entries_reponse_bambara",
        },
        {
            "name": "nlu",
            "path": "dictionnaires/nlu_concepts.json",
            "schema": "nlu_concepts_keywords",
        },
    ]

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

    # Feature flag de bascule storage corpus (ADR-0008 §Phase C).
    # - "chroma"   : legacy ChromaDB (vdb_service.py) — comportement actuel inchangé (DÉFAUT)
    # - "dual"     : double-lecture, retourne Chroma (autoritatif), compare pgvector en background
    # - "pgvector" : PostgreSQL+pgvector seul (Phase E)
    # Plan de rollback : `corpus_storage_mode=chroma` dans `.env` → restart immédiat.
    corpus_storage_mode: Literal["chroma", "dual", "pgvector"] = "chroma"

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


@lru_cache()
def get_settings() -> Settings:
    """Retourne les settings (cached).

    Issue #213 : si `API_SECRET_KEY_FILE` / `API_SECRET_KEY_PREVIOUS_FILE`
    sont définis (pattern Docker secrets), leur contenu OVERRIDE les
    valeurs lues depuis `.env`. Cela permet de stocker les secrets dans
    des fichiers mode 0600 sur la VM plutôt que dans des env vars
    (visibles via `docker inspect`).
    """
    # Construire les overrides depuis Docker secrets si présents.
    # Note : API_SECRET_KEY_PREVIOUS_FILE pourra etre ajoute apres le merge
    # de PR #245 (qui introduit le champ api_secret_key_previous).
    overrides: dict[str, str] = {}
    if file_secret := _read_file_secret("API_SECRET_KEY"):
        overrides["api_secret_key"] = file_secret

    s = Settings(**overrides)
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
