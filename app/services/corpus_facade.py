"""Wourri — Façade corpus IVR (ADR-0008 §Phase C).

Route les 5 opérations corpus vers ChromaDB legacy (`vdb_service`) ou vers
PostgreSQL+pgvector (`corpus_service`) selon le feature flag
`corpus_storage_mode` (`chroma` | `dual` | `pgvector`).

**Mode `chroma`** (DÉFAUT) : 100 % du trafic vers `vdb_service`. Zéro overhead,
zéro régression sur le comportement actuel.

**Mode `dual`** : retourne le résultat Chroma (autoritatif) mais lance une
comparaison `corpus_service` en background thread. Toute divergence est loggée
via `[VDB-DUAL]` pour Phase D (validation terrain).

**Mode `pgvector`** : 100 % du trafic vers `corpus_service`. Réservé Phase E
après validation terrain.

**Pattern 13 projet** : pure functions module-level (pas de classe), parallélisme
avec `vdb_service.py` lui-même. La façade n'a aucun état persistant local —
elle route vers des singletons gérés par les services sous-jacents.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


def _mode() -> str:
    """Lit `corpus_storage_mode` depuis Settings.

    Pas cache pour permettre l'override `monkeypatch` dans les tests d'intégration.
    Coût d'un appel `get_settings()` : négligeable (lru_cache interne Pydantic).
    """
    from app.config import get_settings

    return get_settings().corpus_storage_mode


# ─────────────────────────────────────────────────────────────────────────
# Comparaison background (mode dual)
# ─────────────────────────────────────────────────────────────────────────


def _compare_chercher_in_background(
    intent: str,
    cultures: list[str],
    conditions: list[str],
    chroma_result: Optional[dict],
) -> None:
    """Compare le résultat Chroma déjà retourné au résultat pgvector (mode dual).

    Log uniquement les divergences sur `id`. Tout exception est attrapée pour
    éviter de polluer les logs avec des stack traces d'un thread daemon
    (risque R5 du plan).
    """
    try:
        from app.services import corpus_service

        pg_result = corpus_service.chercher_reponse_ivr(intent, cultures, conditions)

        chroma_id = chroma_result.get("id") if chroma_result else None
        pg_id = pg_result.get("id") if pg_result else None

        if chroma_id == pg_id:
            logger.debug(
                "[VDB-DUAL] match (intent=%s cultures=%s id=%s)",
                intent, cultures, chroma_id,
            )
        else:
            logger.warning(
                "[VDB-DUAL] DIVERGENCE intent=%s cultures=%s chroma_id=%s pgvector_id=%s",
                intent, cultures, chroma_id, pg_id,
            )
    except Exception:
        # exc_info=True (cf. plan R5) : stack trace pour diagnostic.
        # Pas le message brut de l'exception (sécurité : peut contenir l'URL Postgres).
        logger.error(
            "[VDB-DUAL] Erreur comparaison background (intent=%s)", intent, exc_info=True
        )


# ─────────────────────────────────────────────────────────────────────────
# API publique (signatures identiques à vdb_service / corpus_service)
# ─────────────────────────────────────────────────────────────────────────


def chercher_reponse_ivr(
    intent: str, cultures: list[str], conditions: list[str] = None
) -> dict | None:
    mode = _mode()

    if mode == "pgvector":
        from app.services import corpus_service
        return corpus_service.chercher_reponse_ivr(intent, cultures, conditions)

    from app.services import vdb_service
    chroma_result = vdb_service.chercher_reponse_ivr(intent, cultures, conditions)

    if mode == "dual":
        # Thread daemon : ne bloque pas le shutdown, log async les divergences.
        threading.Thread(
            target=_compare_chercher_in_background,
            args=(intent, list(cultures), list(conditions or []), chroma_result),
            daemon=True,
        ).start()

    return chroma_result


def ajouter_reponse_validee(
    intent: str,
    cultures: list[str],
    reponse_bambara: str,
    reponse_fr: str,
    score_validation: float,
    conditions: list[str] = None,
    tags: list[str] = None,
) -> bool:
    """Écriture : `dual` écrit dans les deux stores (best-effort sur pgvector)."""
    mode = _mode()

    if mode == "pgvector":
        from app.services import corpus_service
        return corpus_service.ajouter_reponse_validee(
            intent, cultures, reponse_bambara, reponse_fr,
            score_validation, conditions, tags,
        )

    from app.services import vdb_service
    chroma_ok = vdb_service.ajouter_reponse_validee(
        intent, cultures, reponse_bambara, reponse_fr,
        score_validation, conditions, tags,
    )

    if mode == "dual":
        # Écriture pgvector en background — l'échec ne propage pas (Chroma reste autoritatif).
        def _write_pg():
            try:
                from app.services import corpus_service
                corpus_service.ajouter_reponse_validee(
                    intent, cultures, reponse_bambara, reponse_fr,
                    score_validation, conditions, tags,
                )
            except Exception:
                # exc_info=True : stack trace dans le log pour diagnostiquer
                # les pannes intermittentes du thread daemon (cf. plan R5).
                # Pas d'inclusion du message brut de l'exception (peut contenir
                # une URL Postgres complète avec password).
                logger.error("[VDB-DUAL] Erreur écriture pgvector", exc_info=True)

        threading.Thread(target=_write_pg, daemon=True).start()

    return chroma_ok


def get_reponse_fallback() -> str:
    mode = _mode()
    if mode == "pgvector":
        from app.services import corpus_service
        return corpus_service.get_reponse_fallback()

    from app.services import vdb_service
    return vdb_service.get_reponse_fallback()


def get_phrases_for_intent(intent: str, cultures: list[str]) -> list[dict]:
    mode = _mode()
    if mode == "pgvector":
        from app.services import corpus_service
        return corpus_service.get_phrases_for_intent(intent, cultures)

    from app.services import vdb_service
    return vdb_service.get_phrases_for_intent(intent, cultures)


def initialiser_vdb() -> None:
    """Préchargement au démarrage selon le mode courant.

    Mode `dual` : précharge les DEUX stores pour éviter une charge tardive
    en première requête (risque R3 du plan : double-charge mémoire).
    """
    mode = _mode()

    if mode in ("chroma", "dual"):
        from app.services import vdb_service
        vdb_service.initialiser_vdb()

    if mode in ("pgvector", "dual"):
        from app.services import corpus_service
        corpus_service.initialiser_vdb()
