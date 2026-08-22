"""Settings — aucune langue / compte en dur dans le métier."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    lqe_data_dir: Path = Path("./data")
    lqe_secret: str = "dev-only-not-for-prod"
    lqe_accounts: str = "[]"
    lqe_language_codes: str = "dyu,bci"
    lqe_cors_origins: str = "http://localhost:5173"
    lqe_cookie_name: str = "wouri_lqe"
    lqe_admin_user: str = ""
    lqe_admin_password: str = ""

    def language_codes(self) -> list[str]:
        return [c.strip().lower() for c in self.lqe_language_codes.split(",") if c.strip()]

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


def get_settings() -> Settings:
    return Settings()

