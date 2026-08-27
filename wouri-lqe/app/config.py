"""Settings — aucune langue / compte en dur dans le métier."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict

# Secret de session par defaut = valeur de DEV. Refuse en production (main.lifespan).
DEFAULT_LQE_SECRET = "dev-only-not-for-prod"
# Placeholders connus faibles a refuser en prod (defauts historiques compose/.env.example).
_WEAK_SECRETS = {DEFAULT_LQE_SECRET, "dev-only-change-me-16", "change-me-min-16-chars"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    lqe_env: str = "dev"  # dev | prod — pilote les garde-fous secret + cookie Secure
    lqe_data_dir: Path = Path("./data")
    lqe_secret: str = DEFAULT_LQE_SECRET
    lqe_accounts: str = "[]"
    lqe_cors_origins: str = "http://localhost:5173"
    lqe_cookie_name: str = "wouri_lqe"
    lqe_admin_user: str = ""
    lqe_admin_password: str = ""

    # ===== PostgreSQL + pgvector (ADR-0034) =====
    lqe_db_schema: str = "lqe"
    lqe_database_url: str = ""
    postgres_host: str = ""
    postgres_port: int = 5432
    postgres_user: str = ""
    postgres_db: str = ""
    postgres_password: str = ""
    postgres_password_file: str = ""

    # ===== Pool de connexions (issue #494) =====
    # false = une connexion par unite de travail, comportement d'avant le pool.
    lqe_db_pool_enabled: bool = True
    lqe_db_pool_min_size: int = 1
    lqe_db_pool_max_size: int = 8
    # attente max d'une connexion libre : echouer vite vaut mieux que suspendre
    # une requete de l'atelier pendant les 30 s par defaut de psycopg_pool.
    lqe_db_pool_timeout: float = 10.0

    def is_prod(self) -> bool:
        return self.lqe_env.strip().lower() in ("prod", "production")

    def secret_is_default(self) -> bool:
        """Secret == placeholder PUBLIC du depot : jamais acceptable, meme en dev."""
        return (self.lqe_secret or "").strip() in _WEAK_SECRETS

    def secret_is_weak(self) -> bool:
        s = (self.lqe_secret or "").strip()
        return s in _WEAK_SECRETS or len(s) < 16

    def accounts(self) -> list[dict]:
        raw = json.loads(self.lqe_accounts or "[]")
        if not isinstance(raw, list):
            return []
        out = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            user = str(item.get("user") or "").strip()
            password = str(item.get("password") or "")
            language = str(item.get("language") or "").strip().lower()
            if user and password and language:
                out.append({"user": user, "password": password, "language": language})
        return out

    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.lqe_cors_origins.split(",") if o.strip()]

    def database_url(self) -> str:
        """DSN psycopg. `LQE_DATABASE_URL` prioritaire, sinon composé depuis POSTGRES_*."""
        if self.lqe_database_url:
            return self.lqe_database_url
        pwd = self.postgres_password
        if not pwd and self.postgres_password_file:
            pwd = Path(self.postgres_password_file).read_text(encoding="utf-8").strip()
        return (
            f"postgresql://{quote(self.postgres_user)}:{quote(pwd)}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


def get_settings() -> Settings:
    return Settings()
