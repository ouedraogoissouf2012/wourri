"""Wourri — Façade corpus IVR (ADR-0008 §Phase C + Phase D).

Route les 5 opérations corpus vers ChromaDB legacy (`vdb_service`) ou vers
PostgreSQL+pgvector (`corpus_service`) selon le feature flag
`corpus_storage_mode` (`chroma` | `dual` | `pgvector`).

**Mode `chroma`** (DÉFAUT) : 100 % du trafic vers `vdb_service`. Zéro overhead,
zéro régression sur le comportement actuel.

**Mode `dual`** (Phase D) : retourne le résultat Chroma (autoritatif) mais lance
une comparaison `corpus_service` en background thread. Chaque comparaison est
PERSISTÉE dans la table `corpus_divergences` (cf. migration 0002) avec
classification (match / divergent / absence_*) et mesures de latence pour
permettre le rapport `/admin/corpus-divergence-report`.

**Mode `pgvector`** : 100 % du trafic vers `corpus_service`. Réservé Phase E
après validation terrain.

**Pattern 13 projet** : pure functions module-level (pas de classe), parallélisme
avec `vdb_service.py` lui-même. La façade n'a aucun état persistant local —
elle route vers des singletons gérés par les services sous-jacents.
"""
from __future__ import annotations

import logging
import threading
import time
from functools import lru_cache
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
# Persistance des divergences (Phase D)
# ─────────────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _get_divergence_engine():
    """Engine SQLAlchemy partagé pour la table `corpus_divergences` (singleton).

    Le pool est dimensionné pour absorber les threads daemon concurrents lancés
    par le mode `dual` (cf. plan Phase D risque R3).

    Si `POSTGRES_URL` est absente, on lève — l'appelant catch (best-effort).
    """
    from sqlalchemy import create_engine
    from app.db.url_resolver import resolve_postgres_url

    url = resolve_postgres_url(raise_on_missing=True)
    return create_engine(
        url,
        future=True,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


def _classify_divergence(chroma_id: Optional[str], pg_id: Optional[str]) -> str:
    """Catégorise la comparaison Chroma vs pgvector en 1 classe sur 5.

    - `match`            : les deux retournent le même id (y compris None==None)
    - `absence_chroma`   : Chroma vide, pgvector a un résultat
    - `absence_pgvector` : pgvector vide, Chroma a un résultat
    - `divergent`        : deux résultats distincts (les deux non-None)
    - `reorder` (réservé Phase E) : non utilisé en Phase D
    """
    if chroma_id == pg_id:
        return "match"
    if chroma_id is None and pg_id is not None:
        return "absence_chroma"
    if pg_id is None and chroma_id is not None:
        return "absence_pgvector"
    return "divergent"


def get_divergence_report_data(days: int) -> dict:
    """Lit + agrège la table `corpus_divergences` sur la fenêtre `days`.

    Fonction publique exposée pour le router admin (`app/routers/admin.py`).
    Encapsule la logique SQL : le router ne touche jamais le singleton engine
    directement (séparation responsabilité service ↔ router, cf. Phase D
    reviewer ARCHITECTURE).

    Retourne un dict prêt à mapper vers `DivergenceReportResponse` (Pydantic).
    """
    from sqlalchemy import text

    engine = _get_divergence_engine()

    with engine.connect() as conn:
        agg = conn.execute(
            text(
                """
                SELECT
                    count(*) AS total_queries,
                    count(*) FILTER (WHERE classification != 'match') AS divergences_count,
                    percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_chroma_ms)
                        FILTER (WHERE latency_chroma_ms IS NOT NULL) AS p95_chroma,
                    percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_pgvector_ms)
                        FILTER (WHERE latency_pgvector_ms IS NOT NULL) AS p95_pgvector,
                    min(observed_at) AS since,
                    max(observed_at) AS until
                FROM corpus_divergences
                WHERE observed_at >= NOW() - make_interval(days => :days)
                """
            ),
            {"days": days},
        ).one()

        rows = conn.execute(
            text(
                """
                SELECT classification, count(*) AS n
                FROM corpus_divergences
                WHERE observed_at >= NOW() - make_interval(days => :days)
                GROUP BY classification
                """
            ),
            {"days": days},
        ).all()

        top = conn.execute(
            text(
                """
                SELECT intent, cultures, conditions, chroma_id, pgvector_id,
                       classification, observed_at
                FROM corpus_divergences
                WHERE observed_at >= NOW() - make_interval(days => :days)
                  AND classification != 'match'
                ORDER BY observed_at DESC
                LIMIT 10
                """
            ),
            {"days": days},
        ).all()

    by_class = {c: 0 for c in (
        "match", "reorder", "divergent", "absence_chroma", "absence_pgvector"
    )}
    for r in rows:
        by_class[r.classification] = int(r.n)

    total = int(agg.total_queries or 0)
    divergences = int(agg.divergences_count or 0)
    rate = (divergences / total) if total > 0 else 0.0

    p95_chroma = float(agg.p95_chroma) if agg.p95_chroma is not None else None
    p95_pg = float(agg.p95_pgvector) if agg.p95_pgvector is not None else None
    ratio = (
        p95_pg / p95_chroma
        if (p95_chroma and p95_chroma > 0 and p95_pg is not None)
        else None
    )

    return {
        "total_queries": total,
        "divergences_count": divergences,
        "divergence_rate": rate,
        "by_classification": by_class,
        "top_10_divergences": [
            {
                "intent": r.intent,
                "cultures": list(r.cultures),
                "conditions": list(r.conditions),
                "chroma_id": r.chroma_id,
                "pgvector_id": r.pgvector_id,
                "classification": r.classification,
                "observed_at": r.observed_at,
            }
            for r in top
        ],
        "latency_p95_chroma_ms": p95_chroma,
        "latency_p95_pgvector_ms": p95_pg,
        "latency_ratio": ratio,
        "since": agg.since,
        "until": agg.until,
    }


def _persist_divergence(
    *,
    intent: str,
    cultures: list[str],
    conditions: list[str],
    chroma_id: Optional[str],
    pg_id: Optional[str],
    chroma_score: Optional[float],
    pg_score: Optional[float],
    classification: str,
    latency_chroma_ms: Optional[int],
    latency_pgvector_ms: Optional[int],
) -> None:
    """Insère une ligne dans `corpus_divergences`. Best-effort : silent fail.

    Appelée depuis le thread daemon de `_compare_chercher_in_background` ;
    toute exception est attrapée plus haut.
    """
    from sqlalchemy import text

    engine = _get_divergence_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO corpus_divergences (
                    intent, cultures, conditions,
                    chroma_id, pgvector_id,
                    chroma_score, pgvector_score,
                    classification,
                    latency_chroma_ms, latency_pgvector_ms
                ) VALUES (
                    :intent, :cultures, :conditions,
                    :chroma_id, :pgvector_id,
                    :chroma_score, :pgvector_score,
                    :classification,
                    :latency_chroma_ms, :latency_pgvector_ms
                )
                """
            ),
            {
                "intent": intent,
                "cultures": list(cultures),
                "conditions": list(conditions),
                "chroma_id": chroma_id,
                "pgvector_id": pg_id,
                "chroma_score": chroma_score,
                "pgvector_score": pg_score,
                "classification": classification,
                "latency_chroma_ms": latency_chroma_ms,
                "latency_pgvector_ms": latency_pgvector_ms,
            },
        )


# ─────────────────────────────────────────────────────────────────────────
# Comparaison background (mode dual)
# ─────────────────────────────────────────────────────────────────────────


def _compare_chercher_in_background(
    intent: str,
    cultures: list[str],
    conditions: list[str],
    chroma_result: Optional[dict],
    latency_chroma_ms: Optional[int],
) -> None:
    """Compare le résultat Chroma déjà retourné au résultat pgvector (mode dual).

    Persiste la divergence (classification + latences) dans `corpus_divergences`
    pour permettre le rapport `/admin/corpus-divergence-report`. Tout exception
    est attrapée pour éviter de polluer les logs avec des stack traces d'un
    thread daemon (plan R5).
    """
    try:
        from app.services import corpus_service

        t0 = time.perf_counter()
        pg_result = corpus_service.chercher_reponse_ivr(intent, cultures, conditions)
        latency_pgvector_ms = int((time.perf_counter() - t0) * 1000)

        chroma_id = chroma_result.get("id") if chroma_result else None
        pg_id = pg_result.get("id") if pg_result else None

        chroma_score = (
            float(chroma_result["score_validation"])
            if chroma_result and "score_validation" in chroma_result
            else None
        )
        pg_score = (
            float(pg_result["score_validation"])
            if pg_result and "score_validation" in pg_result
            else None
        )

        classification = _classify_divergence(chroma_id, pg_id)

        if classification == "match":
            logger.debug(
                "[VDB-DUAL] match (intent=%s cultures=%s id=%s)",
                intent, cultures, chroma_id,
            )
        else:
            logger.warning(
                "[VDB-DUAL] %s intent=%s cultures=%s chroma_id=%s pgvector_id=%s",
                classification, intent, cultures, chroma_id, pg_id,
            )

        try:
            _persist_divergence(
                intent=intent,
                cultures=cultures,
                conditions=conditions,
                chroma_id=chroma_id,
                pg_id=pg_id,
                chroma_score=chroma_score,
                pg_score=pg_score,
                classification=classification,
                latency_chroma_ms=latency_chroma_ms,
                latency_pgvector_ms=latency_pgvector_ms,
            )
        except Exception as exc:
            # FIX-6 : type-only au lieu de exc_info=True. La stack trace
            # psycopg/SQLAlchemy peut contenir l'URL Postgres+password dans
            # `args` des exceptions imbriquées (cf. reviewer SÉCURITÉ M1).
            # On accepte la perte de stack trace en échange de la garantie
            # qu'aucun credential ne fuit dans les logs.
            logger.error(
                "[VDB-DUAL] Erreur persistance divergence (intent=%s) type=%s",
                intent, type(exc).__name__,
            )
    except Exception as exc:
        # FIX-6 : type-only (cf. ci-dessus).
        logger.error(
            "[VDB-DUAL] Erreur comparaison background (intent=%s) type=%s",
            intent, type(exc).__name__,
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

    # Mesure latence Chroma (Phase D — critère ADR §Phase D #5).
    # En mode `chroma` pur la mesure est négligeable et inutilisée ; en `dual`
    # elle est passée au thread daemon.
    t0 = time.perf_counter()
    chroma_result = vdb_service.chercher_reponse_ivr(intent, cultures, conditions)
    latency_chroma_ms = int((time.perf_counter() - t0) * 1000)

    if mode == "dual":
        # Thread daemon : ne bloque pas le shutdown, log async les divergences.
        threading.Thread(
            target=_compare_chercher_in_background,
            args=(intent, list(cultures), list(conditions or []), chroma_result, latency_chroma_ms),
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
            except Exception as exc:
                # FIX-6 : type-only au lieu de exc_info=True (cf. reviewer
                # SÉCURITÉ M1 — la stack trace psycopg peut contenir l'URL
                # Postgres avec password).
                logger.error(
                    "[VDB-DUAL] Erreur écriture pgvector type=%s",
                    type(exc).__name__,
                )

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
