"""Métriques techniques du dashboard opérateur (issue #41, ADR-0017).

Ce module est volontairement incapable de recevoir ou stocker un message,
une transcription, un user_id, une IP ou un détail d'exception. Son contrat
se limite à des métadonnées internes bornées.

L'écriture est best-effort et peut être lancée dans un thread daemon afin
qu'une panne PostgreSQL n'ajoute ni latence ni erreur aux routes utilisateur.
"""
from __future__ import annotations

import logging
import queue
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache

logger = logging.getLogger(__name__)

MAX_DASHBOARD_DAYS = 90
MAX_RECENT_ROWS = 50
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_./:{}-]+$")
_record_failure_warned = False
_record_failure_lock = threading.Lock()
_queue_full_warned = False
_queue_full_lock = threading.Lock()
_metric_queue: queue.Queue[RequestMetric] = queue.Queue(maxsize=1_000)
_worker_started = False
_worker_lock = threading.Lock()


@dataclass(frozen=True)
class RequestMetric:
    """Une observation technique sans contenu utilisateur."""

    endpoint: str
    method: str
    status_code: int
    duration_ms: int
    intent: str | None = None
    culture: str | None = None
    source: str | None = None
    asr_success: bool | None = None
    nlu_out_of_scope: bool | None = None


def _safe_token(value: object, *, max_length: int = 120) -> str | None:
    """Accepte uniquement les identifiants techniques produits par le code."""
    if not isinstance(value, str):
        return None
    candidate = value.strip()[:max_length]
    if not candidate or not _SAFE_TOKEN.fullmatch(candidate):
        return None
    return candidate


def _validated_metric(metric: RequestMetric) -> RequestMetric:
    endpoint = _safe_token(metric.endpoint) or "/api/unknown"
    method = _safe_token(metric.method, max_length=8) or "UNKNOWN"
    status_code = min(max(int(metric.status_code), 100), 599)
    duration_ms = min(max(int(metric.duration_ms), 0), 2_147_483_647)

    return RequestMetric(
        endpoint=endpoint,
        method=method.upper(),
        status_code=status_code,
        duration_ms=duration_ms,
        intent=_safe_token(metric.intent),
        culture=_safe_token(metric.culture),
        source=_safe_token(metric.source),
        asr_success=metric.asr_success if isinstance(metric.asr_success, bool) else None,
        nlu_out_of_scope=(
            metric.nlu_out_of_scope
            if isinstance(metric.nlu_out_of_scope, bool)
            else None
        ),
    )


@lru_cache(maxsize=1)
def _get_metrics_engine():
    """Retourne l'engine PostgreSQL partagé du dashboard."""
    from sqlalchemy import create_engine

    from app.db.url_resolver import resolve_postgres_url

    return create_engine(
        resolve_postgres_url(raise_on_missing=True),
        future=True,
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=5,
        pool_timeout=3,
        connect_args={"connect_timeout": 3},
    )


def record_request_metric(metric: RequestMetric) -> None:
    """Persiste une observation validée.

    Cette fonction synchrone est exposée pour les tests et les outils. Les
    requêtes HTTP utilisent `record_request_metric_background`.
    """
    from sqlalchemy import text

    clean = _validated_metric(metric)
    with _get_metrics_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO admin_request_metrics (
                    endpoint, method, status_code, duration_ms,
                    intent, culture, source, asr_success, nlu_out_of_scope
                )
                VALUES (
                    :endpoint, :method, :status_code, :duration_ms,
                    :intent, :culture, :source, :asr_success, :nlu_out_of_scope
                )
                """
            ),
            {
                "endpoint": clean.endpoint,
                "method": clean.method,
                "status_code": clean.status_code,
                "duration_ms": clean.duration_ms,
                "intent": clean.intent,
                "culture": clean.culture,
                "source": clean.source,
                "asr_success": clean.asr_success,
                "nlu_out_of_scope": clean.nlu_out_of_scope,
            },
        )


def _record_safely(metric: RequestMetric) -> None:
    global _record_failure_warned
    try:
        record_request_metric(metric)
    except Exception as exc:  # noqa: BLE001 - frontière best-effort volontaire
        # Un seul warning par process : PostgreSQL peut être volontairement
        # absent en développement. Ne jamais inclure le contenu de la requête.
        with _record_failure_lock:
            if not _record_failure_warned:
                logger.warning(
                    "[ADMIN-METRICS] Persistance indisponible, métriques ignorées: %s",
                    type(exc).__name__,
                )
                _record_failure_warned = True


def _metric_worker() -> None:
    while True:
        metric = _metric_queue.get()
        try:
            _record_safely(metric)
        finally:
            _metric_queue.task_done()


def _ensure_worker() -> None:
    global _worker_started
    if _worker_started:
        return
    with _worker_lock:
        if _worker_started:
            return
        threading.Thread(
            target=_metric_worker,
            name="wourri-admin-metrics",
            daemon=True,
        ).start()
        _worker_started = True


def record_request_metric_background(metric: RequestMetric) -> None:
    """Place l'écriture dans une file bornée sans bloquer la réponse HTTP."""
    global _queue_full_warned
    from app.config import get_settings

    if not get_settings().admin_metrics_enabled:
        return

    _ensure_worker()
    try:
        _metric_queue.put_nowait(metric)
    except queue.Full:
        with _queue_full_lock:
            if not _queue_full_warned:
                logger.warning(
                    "[ADMIN-METRICS] File pleine, métriques supplémentaires ignorées"
                )
                _queue_full_warned = True


def _error_kind(row) -> str:
    if row.status_code >= 500:
        return "server_error"
    if row.status_code >= 400:
        return "client_error"
    if row.asr_success is False:
        return "asr_failure"
    return "nlu_out_of_scope"


def _row_to_recent(row, *, include_error_kind: bool = False) -> dict:
    item = {
        "observed_at": row.observed_at,
        "endpoint": row.endpoint,
        "method": row.method,
        "status_code": int(row.status_code),
        "duration_ms": int(row.duration_ms),
        "intent": row.intent,
        "culture": row.culture,
        "source": row.source,
        "asr_success": row.asr_success,
        "nlu_out_of_scope": row.nlu_out_of_scope,
    }
    if include_error_kind:
        item["error_kind"] = _error_kind(row)
    return item


# Colonnes autorisées pour un regroupement "top N". Interpolées dans le SQL par
# _query_grouped_counts : restreindre à cette allow-list interdit toute injection
# même si un futur appelant passait une valeur non littérale.
_GROUP_COUNT_COLUMNS = frozenset({"intent", "culture", "endpoint", "source"})

# Colonnes projetées par les requêtes de lignes récentes (recent / errors).
_RECENT_COLUMNS = (
    "observed_at, endpoint, method, status_code, duration_ms, "
    "intent, culture, source, asr_success, nlu_out_of_scope"
)

# Prédicat "ligne en erreur" partagé par la requête `errors` et l'agrégat daily.
_ERROR_PREDICATE = (
    "status_code >= 400 OR asr_success IS FALSE OR nlu_out_of_scope IS TRUE"
)


def _query_summary(conn, params):
    """Agrégat global de la fenêtre : totaux, latences, taux ASR/NLU."""
    from sqlalchemy import text

    return conn.execute(
        text(
            """
            SELECT
                count(*) AS total_requests,
                count(*) FILTER (WHERE status_code < 400) AS successful_requests,
                avg(duration_ms) AS average_duration_ms,
                percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms)
                    AS p95_duration_ms,
                count(*) FILTER (WHERE asr_success IS NOT NULL) AS asr_total,
                count(*) FILTER (WHERE asr_success IS TRUE) AS asr_successes,
                count(*) FILTER (WHERE nlu_out_of_scope IS NOT NULL) AS nlu_total,
                count(*) FILTER (WHERE nlu_out_of_scope IS FALSE)
                    AS nlu_in_scope
            FROM admin_request_metrics
            WHERE observed_at >= NOW() - make_interval(days => :days)
            """
        ),
        params,
    ).one()


def _query_daily(conn, params):
    """Nombre de requêtes et d'erreurs par jour sur la fenêtre."""
    from sqlalchemy import text

    return conn.execute(
        text(
            f"""
            SELECT
                CAST(observed_at AS date) AS day,
                count(*) AS requests,
                count(*) FILTER (WHERE {_ERROR_PREDICATE}) AS errors
            FROM admin_request_metrics
            WHERE observed_at >= NOW() - make_interval(days => :days)
            GROUP BY CAST(observed_at AS date)
            ORDER BY day
            """
        ),
        params,
    ).all()


def _query_grouped_counts(conn, params, column: str, *, exclude_null: bool = True):
    """Top 8 des valeurs de `column` par nombre de requêtes décroissant.

    Mutualise les requêtes top_intents / top_cultures / top_sources
    (exclude_null=True) et endpoint_counts (exclude_null=False).

    `column` DOIT appartenir à _GROUP_COUNT_COLUMNS (jamais un input utilisateur) :
    il est interpolé dans le SQL, l'allow-list garantit l'absence d'injection.
    """
    if column not in _GROUP_COUNT_COLUMNS:
        raise ValueError(f"colonne de regroupement non autorisée: {column!r}")
    from sqlalchemy import text

    null_filter = f"AND {column} IS NOT NULL" if exclude_null else ""
    return conn.execute(
        text(
            f"""
            SELECT {column} AS label, count(*) AS count
            FROM admin_request_metrics
            WHERE observed_at >= NOW() - make_interval(days => :days)
              {null_filter}
            GROUP BY {column}
            ORDER BY count DESC, {column}
            LIMIT 8
            """
        ),
        params,
    ).all()


def _query_recent_rows(conn, params, *, errors_only: bool = False):
    """Dernières lignes de la fenêtre (ou dernières erreurs si errors_only)."""
    from sqlalchemy import text

    error_filter = f"AND ( {_ERROR_PREDICATE} )" if errors_only else ""
    return conn.execute(
        text(
            f"""
            SELECT {_RECENT_COLUMNS}
            FROM admin_request_metrics
            WHERE observed_at >= NOW() - make_interval(days => :days)
              {error_filter}
            ORDER BY observed_at DESC
            LIMIT :recent_limit
            """
        ),
        params,
    ).all()


def _build_summary(summary) -> dict:
    """Construit le bloc `summary` (taux dérivés) depuis la row d'agrégat."""
    total = int(summary.total_requests or 0)
    asr_total = int(summary.asr_total or 0)
    nlu_total = int(summary.nlu_total or 0)
    return {
        "total_requests": total,
        "success_rate": (
            int(summary.successful_requests or 0) / total if total else None
        ),
        "average_duration_ms": (
            round(float(summary.average_duration_ms), 1)
            if summary.average_duration_ms is not None
            else None
        ),
        "p95_duration_ms": (
            round(float(summary.p95_duration_ms), 1)
            if summary.p95_duration_ms is not None
            else None
        ),
        "asr_success_rate": (
            int(summary.asr_successes or 0) / asr_total if asr_total else None
        ),
        "nlu_in_scope_rate": (
            int(summary.nlu_in_scope or 0) / nlu_total if nlu_total else None
        ),
    }


def get_dashboard_data(*, days: int = 7, recent_limit: int = 12) -> dict:
    """Agrège les métriques sans exposer de contenu utilisateur.

    Orchestre les requêtes d'agrégation (déléguées à des helpers _query_*) sur
    une unique connexion, puis assemble le payload du dashboard.
    """
    if not 1 <= days <= MAX_DASHBOARD_DAYS:
        raise ValueError(f"days doit être compris entre 1 et {MAX_DASHBOARD_DAYS}")
    if not 1 <= recent_limit <= MAX_RECENT_ROWS:
        raise ValueError(
            f"recent_limit doit être compris entre 1 et {MAX_RECENT_ROWS}"
        )

    engine = _get_metrics_engine()
    params = {"days": days, "recent_limit": recent_limit}

    with engine.connect() as conn:
        summary = _query_summary(conn, params)
        daily = _query_daily(conn, params)
        top_intents = _query_grouped_counts(conn, params, "intent")
        top_cultures = _query_grouped_counts(conn, params, "culture")
        # Répartition par `source` et par endpoint (issue #304) : source donne le
        # % de trafic servi par le corpus validé (ivr_exact) vs l'IA (deepseek_open),
        # métrique produit clé. endpoint_counts n'exclut pas les valeurs nulles.
        endpoint_counts = _query_grouped_counts(conn, params, "endpoint", exclude_null=False)
        top_sources = _query_grouped_counts(conn, params, "source")
        recent = _query_recent_rows(conn, params)
        errors = _query_recent_rows(conn, params, errors_only=True)

    return {
        "generated_at": datetime.now(timezone.utc),
        "days": days,
        "summary": _build_summary(summary),
        "daily": [
            {
                "day": row.day,
                "requests": int(row.requests),
                "errors": int(row.errors),
            }
            for row in daily
        ],
        "top_intents": [
            {"label": row.label, "count": int(row.count)} for row in top_intents
        ],
        "top_cultures": [
            {"label": row.label, "count": int(row.count)} for row in top_cultures
        ],
        "endpoint_counts": [
            {"label": row.label, "count": int(row.count)} for row in endpoint_counts
        ],
        "top_sources": [
            {"label": row.label, "count": int(row.count)} for row in top_sources
        ],
        "recent_requests": [_row_to_recent(row) for row in recent],
        "recent_errors": [
            _row_to_recent(row, include_error_kind=True) for row in errors
        ],
    }
