"""WOURI — Router Admin (Sprint F Phase D — ADR-0008).

Endpoint(s) destinés aux opérateurs (pas aux agriculteurs). Protégés par
`require_api_key` (mode dev permissif si `API_SECRET_KEY` absent dans `.env`).

## GET /admin/corpus-divergence-report

Rapport d'agrégation des divergences observées en mode `dual` (Phase D).
Délègue la requête SQL à `corpus_facade.get_divergence_report_data(days)` —
le router ne touche pas le singleton engine privé (séparation
responsabilité service ↔ router, cf. Phase D reviewer ARCHITECTURE).

Paramètre :
- `days` (default=7, min=1, max=365) — fenêtre temporelle du rapport.

Référence : ADR-0008 §Phase D « validation terrain ».
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import get_settings
from app.security import require_api_key
from app.services.admin_metrics import get_dashboard_data
from app.services.corpus_facade import get_divergence_report_data

router = APIRouter(prefix="/admin", tags=["Admin"])
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────
# Pydantic response schemas
# ─────────────────────────────────────────────────────────────────────────


class DivergenceDetail(BaseModel):
    intent: str
    cultures: list[str]
    conditions: list[str]  # FIX-4 : indispensable pour reproduire la query
    chroma_id: str | None
    pgvector_id: str | None
    classification: str
    observed_at: datetime


class DivergenceReportResponse(BaseModel):
    """Cf. ADR-0008 §Phase D critères de sortie #2/#3/#4/#5."""

    total_queries: int
    divergences_count: int  # tout ce qui n'est pas `match`
    divergence_rate: float  # 0.0 ↔ 1.0
    by_classification: dict[str, int]
    top_10_divergences: list[DivergenceDetail]
    latency_p95_chroma_ms: float | None
    latency_p95_pgvector_ms: float | None
    latency_ratio: float | None  # p95_pgvector / p95_chroma — critère ≤ 1.5
    since: datetime
    until: datetime


class DashboardSummary(BaseModel):
    total_requests: int
    success_rate: float | None
    average_duration_ms: float | None
    p95_duration_ms: float | None
    asr_success_rate: float | None
    nlu_in_scope_rate: float | None


class CountBucket(BaseModel):
    label: str
    count: int


class DailyMetric(BaseModel):
    day: date
    requests: int
    errors: int


class RecentRequestMetric(BaseModel):
    observed_at: datetime
    endpoint: str
    method: str
    status_code: int
    duration_ms: int
    intent: str | None
    culture: str | None
    source: str | None
    asr_success: bool | None
    nlu_out_of_scope: bool | None


class RecentErrorMetric(RecentRequestMetric):
    error_kind: str


class DashboardDataResponse(BaseModel):
    generated_at: datetime
    days: int
    summary: DashboardSummary
    daily: list[DailyMetric]
    top_intents: list[CountBucket]
    top_cultures: list[CountBucket]
    endpoint_counts: list[CountBucket]
    recent_requests: list[RecentRequestMetric]
    recent_errors: list[RecentErrorMetric]


# ─────────────────────────────────────────────────────────────────────────
# Endpoint
# ─────────────────────────────────────────────────────────────────────────


@router.get(
    "/corpus-divergence-report",
    response_model=DivergenceReportResponse,
    dependencies=[Depends(require_api_key)],
)
async def corpus_divergence_report(
    days: int = Query(default=7, ge=1, le=365, description="Fenêtre temporelle en jours"),
) -> DivergenceReportResponse:
    """Rapport agrégé des divergences mode `dual` (Phase D)."""
    data = get_divergence_report_data(days)

    # `since`/`until` peuvent être None si la table est vide → fallback
    # tz-aware (FIX-9 : `datetime.utcnow()` est déprécié Python 3.12+).
    now_utc = datetime.now(timezone.utc)

    return DivergenceReportResponse(
        total_queries=data["total_queries"],
        divergences_count=data["divergences_count"],
        divergence_rate=data["divergence_rate"],
        by_classification=data["by_classification"],
        top_10_divergences=[
            DivergenceDetail(**d) for d in data["top_10_divergences"]
        ],
        latency_p95_chroma_ms=data["latency_p95_chroma_ms"],
        latency_p95_pgvector_ms=data["latency_p95_pgvector_ms"],
        latency_ratio=data["latency_ratio"],
        since=data["since"] or now_utc,
        until=data["until"] or now_utc,
    )


@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request) -> HTMLResponse:
    """Coquille HTML sans donnée ; l'API JSON est protégée par X-API-Key."""
    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "app_name": get_settings().app_name,
        },
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": (
                "default-src 'self'; "
                "script-src 'self' https://cdn.jsdelivr.net; "
                "style-src 'self'; "
                "img-src 'self' data:; "
                "connect-src 'self'; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            ),
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
        },
    )


@router.get(
    "/dashboard/data",
    response_model=DashboardDataResponse,
    dependencies=[Depends(require_api_key)],
)
async def admin_dashboard_data(
    days: int = Query(default=7, ge=1, le=90),
    recent_limit: int = Query(default=12, ge=1, le=50),
) -> DashboardDataResponse:
    """Agrégats PostgreSQL sans message, transcription, user_id ou IP."""
    if not get_settings().admin_metrics_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Les métriques administrateur sont désactivées.",
        )

    try:
        data = await asyncio.to_thread(
            get_dashboard_data,
            days=days,
            recent_limit=recent_limit,
        )
    except Exception as exc:
        logger.warning(
            "[ADMIN-DASHBOARD] Données indisponibles: %s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Métriques temporairement indisponibles.",
        ) from exc

    return DashboardDataResponse(**data)
