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

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.security import require_api_key
from app.services.corpus_facade import get_divergence_report_data

router = APIRouter(prefix="/admin", tags=["Admin"])


# ─────────────────────────────────────────────────────────────────────────
# Pydantic response schemas
# ─────────────────────────────────────────────────────────────────────────


class DivergenceDetail(BaseModel):
    intent: str
    cultures: list[str]
    conditions: list[str]  # FIX-4 : indispensable pour reproduire la query
    chroma_id: Optional[str]
    pgvector_id: Optional[str]
    classification: str
    observed_at: datetime


class DivergenceReportResponse(BaseModel):
    """Cf. ADR-0008 §Phase D critères de sortie #2/#3/#4/#5."""

    total_queries: int
    divergences_count: int  # tout ce qui n'est pas `match`
    divergence_rate: float  # 0.0 ↔ 1.0
    by_classification: dict[str, int]
    top_10_divergences: list[DivergenceDetail]
    latency_p95_chroma_ms: Optional[float]
    latency_p95_pgvector_ms: Optional[float]
    latency_ratio: Optional[float]  # p95_pgvector / p95_chroma — critère ≤ 1.5
    since: datetime
    until: datetime


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
