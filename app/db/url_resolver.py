"""Wourri — Résolution centralisée de l'URL Postgres (ADR-0008 §Phase C).

Issue #180. Avant Phase C, la logique `_resolve_url()` était dupliquée à
trois endroits avec un contrat de sortie qui divergeait :

- `alembic/env.py`                              → lève `RuntimeError`
- `scripts/import_corpus_ivr.py`                → lève `RuntimeError`
- `tests/integration/test_corpus_schema.py`     → retourne `""` (pour pytest skipif)

Phase C ajoute `app/services/corpus_service.py` comme 4e consommateur. Le seuil
projet d'extraction (≥ 4 consommateurs, Pattern Helpers partagés Sprint D.4) est
atteint. La divergence test/prod est encodée explicitement via le paramètre
`raise_on_missing`, supprimant toute possibilité d'unification naïve qui aurait
cassé le skip silencieusement.

Sources lues, dans l'ordre de priorité :
1. variable d'environnement `POSTGRES_URL`
2. `app.config.Settings.postgres_url` (chargé depuis `.env`)
"""
from __future__ import annotations

import os


def resolve_postgres_url(*, raise_on_missing: bool = True) -> str:
    """Retourne l'URL Postgres ou `""` selon le contrat demandé.

    Args:
        raise_on_missing: si True (défaut), lève `RuntimeError` quand
            ni `POSTGRES_URL` ni `Settings.postgres_url` ne sont définies.
            Si False, retourne `""` — utilisé par les tests d'intégration
            pour piloter `pytest.mark.skipif`.

    Returns:
        L'URL au format `postgresql+psycopg://user:pwd@host:port/db`, ou
        `""` quand `raise_on_missing=False` et qu'aucune source n'est définie.

    Raises:
        RuntimeError: si `raise_on_missing=True` et qu'aucune URL n'est trouvée.
    """
    url = os.getenv("POSTGRES_URL", "").strip()
    if url:
        return url

    try:
        from app.config import get_settings

        settings_url = (get_settings().postgres_url or "").strip()
        if settings_url:
            return settings_url
    except Exception:
        # Settings indisponible (config Pydantic cassée par ex.) : on traite
        # comme une absence d'URL et on laisse le contrat décider.
        pass

    if raise_on_missing:
        raise RuntimeError(
            "POSTGRES_URL n'est pas définie. Renseignez-la dans wouri-api/.env "
            "(cf. .env.example) ou exportez-la dans l'environnement."
        )
    return ""
