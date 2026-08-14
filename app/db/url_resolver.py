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
3. assemblage par composants (issue #258) : `POSTGRES_HOST` [+ `POSTGRES_PORT`,
   défaut 5432] + `POSTGRES_USER` + `POSTGRES_DB` + mot de passe lu depuis
   `POSTGRES_PASSWORD_FILE` (Docker secret, prioritaire) ou `POSTGRES_PASSWORD`.
   Élimine la duplication du mot de passe dans docker-compose.prod.yml
   (1× secret pour postgres, 1× env interpolée dans POSTGRES_URL).
"""
from __future__ import annotations

import os
from urllib.parse import quote

from app.core.secrets import read_file_secret


def _assemble_from_components(*, raise_on_incomplete: bool) -> str:
    """Assemble l'URL depuis les composants POSTGRES_* (issue #258).

    Le chemin ne s'active que si `POSTGRES_HOST` est défini (intention
    explicite d'assemblage). Config partielle → RuntimeError nommant les
    manques (fail loud), sauf en mode skip (`raise_on_incomplete=False`).
    User/password/db sont URL-encodés (mots de passe avec `:/@%` valides).
    """
    host = os.getenv("POSTGRES_HOST", "").strip()
    if not host:
        return ""

    user = os.getenv("POSTGRES_USER", "").strip()
    db = os.getenv("POSTGRES_DB", "").strip()
    port = os.getenv("POSTGRES_PORT", "").strip() or "5432"
    # Priorité au Docker secret (un seul point de vérité), fallback env brut.
    # PAS de strip() sur le mot de passe env : un mot de passe avec espaces
    # de bord est légal et l'ancienne interpolation compose le passait tel
    # quel (le fichier secret, lui, est strippé — newline de fin).
    password = read_file_secret("POSTGRES_PASSWORD") or os.getenv(
        "POSTGRES_PASSWORD", ""
    )

    missing = [
        label
        for label, value in (
            ("POSTGRES_USER", user),
            ("POSTGRES_DB", db),
            ("POSTGRES_PASSWORD_FILE ou POSTGRES_PASSWORD", password),
        )
        if not value
    ]
    if missing:
        if raise_on_incomplete:
            raise RuntimeError(
                "POSTGRES_HOST est défini mais la configuration est incomplète "
                f"— manquant : {', '.join(missing)} (cf. docker-compose.prod.yml "
                "service wouri-api, issue #258)."
            )
        return ""

    # quote(safe="") et PAS quote_plus : quote_plus encode l'espace en '+',
    # que make_url/unquote de SQLAlchemy ne re-décode pas en espace → un mot
    # de passe contenant un espace arriverait faux à Postgres.
    return (
        f"postgresql+psycopg://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{host}:{port}/{quote(db, safe='')}"
    )


def resolve_postgres_url(*, raise_on_missing: bool = True) -> str:
    """Retourne l'URL Postgres ou `""` selon le contrat demandé.

    Args:
        raise_on_missing: si True (défaut), lève `RuntimeError` quand aucune
            des 3 sources (POSTGRES_URL, Settings.postgres_url, composants
            POSTGRES_*) n'aboutit. Si False, retourne `""` — utilisé par les
            tests d'intégration pour piloter `pytest.mark.skipif` (ne lève
            jamais, même sur configuration partielle).

    Returns:
        L'URL au format `postgresql+psycopg://user:pwd@host:port/db`, ou
        `""` quand `raise_on_missing=False` et qu'aucune source n'aboutit.

    Raises:
        RuntimeError: si `raise_on_missing=True` et qu'aucune URL n'est
            trouvée, ou que l'assemblage par composants est incomplet.
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

    assembled = _assemble_from_components(raise_on_incomplete=raise_on_missing)
    if assembled:
        return assembled

    if raise_on_missing:
        raise RuntimeError(
            "POSTGRES_URL n'est pas définie. Renseignez-la dans wouri-api/.env "
            "(cf. .env.example), exportez-la dans l'environnement, ou "
            "définissez les composants POSTGRES_HOST/USER/DB + "
            "POSTGRES_PASSWORD[_FILE] (issue #258)."
        )
    return ""
