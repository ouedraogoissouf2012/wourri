# -*- coding: utf-8 -*-
"""
WOURI - Lecture des secrets pattern Docker `*_FILE` (issues #213, #258).

Helper partagé, extrait de `app/config.py::_read_file_secret` (issue #258 —
2e consommateur : `app/db/url_resolver.py` pour POSTGRES_PASSWORD_FILE).

Le compose monte les fichiers de secrets dans `/run/secrets/<nom>` puis
définit dans l'environnement du service :
    API_SECRET_KEY_FILE=/run/secrets/api_secret_key
Les consommateurs lisent alors le contenu du fichier (strip appliqué —
newline finale des fichiers de secrets) en priorité sur la variable brute.

Backward-compat : si `{NAME}_FILE` n'est pas défini OU si le fichier est
introuvable, retourne `""` → l'appelant garde son fallback (lecture de la
variable d'environnement brute / `.env`).
"""
from __future__ import annotations

import os
from pathlib import Path


def read_file_secret(name: str) -> str:
    """Lit le contenu du fichier référencé par la variable `{name}_FILE`.

    Args:
        name: nom logique du secret (ex: "API_SECRET_KEY",
            "POSTGRES_PASSWORD") — la variable lue est `{name}_FILE`.

    Returns:
        Le contenu du fichier (strip), ou `""` si `{name}_FILE` n'est pas
        défini ou si le fichier n'existe pas (no-op silencieux, backward-compat).
    """
    file_path = os.getenv(f"{name}_FILE")
    if not file_path:
        return ""
    p = Path(file_path)
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8").strip()
