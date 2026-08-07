"""Intégration PostgreSQL des métriques anonymes du dashboard #41."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.db.url_resolver import resolve_postgres_url
from app.services.admin_metrics import (
    RequestMetric,
    _get_metrics_engine,
    get_dashboard_data,
    record_request_metric,
)
from tests.integration._helpers import postgres_reachable

_URL = resolve_postgres_url(raise_on_missing=False)
pytestmark = pytest.mark.skipif(
    not postgres_reachable(_URL),
    reason="PostgreSQL+pgvector non disponible pour le dashboard #41.",
)


@pytest.fixture
def clean_metrics():
    engine = _get_metrics_engine()
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE admin_request_metrics RESTART IDENTITY;"))
    yield
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE admin_request_metrics RESTART IDENTITY;"))


def test_persist_and_aggregate_privacy_safe_metrics(clean_metrics):
    rows = (
        RequestMetric(
            "/api/chat/",
            "POST",
            200,
            100,
            intent="CONSEIL_PRODUCTION",
            culture="CULTURE_RIZ",
            source="ivr_exact",
            nlu_out_of_scope=False,
        ),
        RequestMetric(
            "/api/chat/",
            "POST",
            200,
            200,
            intent="CONSEIL_PRODUCTION",
            culture="CULTURE_RIZ",
            source="deepseek_open",
            nlu_out_of_scope=False,
        ),
        RequestMetric(
            "/api/asr/transcribe",
            "POST",
            200,
            300,
            asr_success=True,
            source="asr",
        ),
        RequestMetric(
            "/api/asr/transcribe",
            "POST",
            500,
            400,
            asr_success=False,
            source="asr",
        ),
    )
    for row in rows:
        record_request_metric(row)

    data = get_dashboard_data(days=7, recent_limit=10)

    assert data["summary"]["total_requests"] == 4
    assert data["summary"]["success_rate"] == 0.75
    assert data["summary"]["average_duration_ms"] == 250.0
    assert data["summary"]["asr_success_rate"] == 0.5
    assert data["summary"]["nlu_in_scope_rate"] == 1.0
    assert data["top_intents"] == [
        {"label": "CONSEIL_PRODUCTION", "count": 2}
    ]
    assert data["top_cultures"] == [{"label": "CULTURE_RIZ", "count": 2}]
    # #304 : agrégation par source (ORDER BY count DESC, source) — permet de
    # mesurer le % corpus validé (ivr_exact) vs chemin dégradé (deepseek_open).
    assert data["top_sources"] == [
        {"label": "asr", "count": 2},
        {"label": "deepseek_open", "count": 1},
        {"label": "ivr_exact", "count": 1},
    ]
    assert data["recent_errors"][0]["error_kind"] == "server_error"


def test_database_schema_contains_no_pii_or_content_columns(clean_metrics):
    with _get_metrics_engine().connect() as conn:
        columns = {
            row.column_name
            for row in conn.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'admin_request_metrics'
                    """
                )
            )
        }

    assert columns == {
        "id",
        "observed_at",
        "endpoint",
        "method",
        "status_code",
        "duration_ms",
        "intent",
        "culture",
        "source",
        "asr_success",
        "nlu_out_of_scope",
    }
    assert columns.isdisjoint(
        {
            "user_id",
            "phone",
            "ip",
            "message",
            "transcription",
            "response",
            "headers",
            "query",
            "filename",
            "exception",
        }
    )
