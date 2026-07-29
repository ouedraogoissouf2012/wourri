"""Tests du service de métriques sans PII (issue #41, ADR-0017)."""
from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace

from sqlalchemy import create_engine, text

from app.services import admin_metrics
from app.services.admin_metrics import RequestMetric


def test_admin_metrics_setting_defaults_enabled(monkeypatch):
    monkeypatch.delenv("ADMIN_METRICS_ENABLED", raising=False)
    from app.config import Settings

    assert Settings(_env_file=None).admin_metrics_enabled is True


def test_admin_metrics_setting_can_disable_collection(monkeypatch):
    monkeypatch.setenv("ADMIN_METRICS_ENABLED", "false")
    from app.config import Settings

    assert Settings(_env_file=None).admin_metrics_enabled is False


def _sqlite_metrics_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE admin_request_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    observed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    endpoint TEXT NOT NULL,
                    method TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    intent TEXT,
                    culture TEXT,
                    source TEXT,
                    asr_success BOOLEAN,
                    nlu_out_of_scope BOOLEAN
                )
                """
            )
        )
    return engine


def test_metric_contract_has_no_pii_or_content_fields():
    names = {field.name for field in fields(RequestMetric)}

    assert names == {
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
    assert names.isdisjoint(
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


def test_validated_metric_rejects_free_text_and_clamps_numbers():
    clean = admin_metrics._validated_metric(
        RequestMetric(
            endpoint="/api/chat/{item}",
            method="post",
            status_code=999,
            duration_ms=-8,
            intent="numéro +225 01 02 03",
            culture="CULTURE_RIZ",
            source="ivr_exact",
        )
    )

    assert clean.endpoint == "/api/chat/{item}"
    assert clean.method == "POST"
    assert clean.status_code == 599
    assert clean.duration_ms == 0
    assert clean.intent is None
    assert clean.culture == "CULTURE_RIZ"
    assert clean.source == "ivr_exact"


def test_record_request_metric_persists_only_allowed_columns(monkeypatch):
    engine = _sqlite_metrics_engine()
    monkeypatch.setattr(admin_metrics, "_get_metrics_engine", lambda: engine)

    admin_metrics.record_request_metric(
        RequestMetric(
            endpoint="/api/chat/",
            method="POST",
            status_code=200,
            duration_ms=42,
            intent="CONSEIL_PRODUCTION",
            culture="CULTURE_RIZ",
            source="ivr_exact",
            nlu_out_of_scope=False,
        )
    )

    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM admin_request_metrics")).mappings().one()

    assert row["endpoint"] == "/api/chat/"
    assert row["intent"] == "CONSEIL_PRODUCTION"
    assert row["culture"] == "CULTURE_RIZ"
    assert row["duration_ms"] == 42
    assert set(row) == {
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


def test_background_recording_can_be_disabled(monkeypatch):
    started = []
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: SimpleNamespace(admin_metrics_enabled=False),
    )
    monkeypatch.setattr(admin_metrics, "_ensure_worker", lambda: started.append(True))

    admin_metrics.record_request_metric_background(
        RequestMetric("/api/chat/", "POST", 200, 10)
    )

    assert started == []


def test_background_recording_uses_bounded_queue(monkeypatch):
    events = []
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: SimpleNamespace(admin_metrics_enabled=True),
    )
    monkeypatch.setattr(admin_metrics, "_ensure_worker", lambda: events.append("worker"))
    monkeypatch.setattr(
        admin_metrics,
        "_metric_queue",
        SimpleNamespace(put_nowait=lambda metric: events.append(metric)),
    )
    metric = RequestMetric("/api/chat/", "POST", 200, 10)

    admin_metrics.record_request_metric_background(metric)

    assert events == ["worker", metric]


def test_record_safely_never_raises_when_postgres_is_down(monkeypatch):
    monkeypatch.setattr(
        admin_metrics,
        "record_request_metric",
        lambda metric: (_ for _ in ()).throw(RuntimeError("database down")),
    )
    monkeypatch.setattr(admin_metrics, "_record_failure_warned", False)

    admin_metrics._record_safely(
        RequestMetric("/api/asr/transcribe", "POST", 500, 12)
    )

    assert admin_metrics._record_failure_warned is True
