"""WOURI — Router Admin (dashboard opérateur, ADR-0017).

Endpoint(s) destinés aux opérateurs (pas aux agriculteurs). Protégés par
`require_api_key` (mode dev permissif si `API_SECRET_KEY` absent dans `.env`).

NOTE (#203) : l'endpoint `/admin/corpus-divergence-report` (comparaison
Chroma↔pgvector du mode `dual`, ADR-0008 Phase D) a été retiré avec la façade
multi-backend — pgvector est le backend unique depuis la Phase E. La table
`corpus_divergences` reste en base (données historiques, coût nul).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import get_settings
from app.security import require_api_key
from app.services.admin_metrics import get_dashboard_data

router = APIRouter(prefix="/admin", tags=["Admin"])
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────
# Pydantic response schemas
# ─────────────────────────────────────────────────────────────────────────


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
    top_sources: list[CountBucket]
    recent_requests: list[RecentRequestMetric]
    recent_errors: list[RecentErrorMetric]


# ─────────────────────────────────────────────────────────────────────────
# Endpoint
# ─────────────────────────────────────────────────────────────────────────


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
