"""
Test de non-régression SQL pour get_dashboard_data (admin_metrics).

Les tests d'intégration qui exercent réellement get_dashboard_data nécessitent
PostgreSQL (souvent absent en CI unitaire). Ce test capture, sans DB, le SQL émis
par la fonction refactorée et le compare aux 8 requêtes de référence (celles
générées avant la décomposition en helpers _query_*). La comparaison ignore tout
espace : elle détecte toute altération de tokens SQL (colonne, filtre, ordre)
sans être fragile au formatage.
"""
from unittest.mock import MagicMock, patch

import pytest

import app.services.admin_metrics as am


# SQL de référence capturés sur la version inline (avant modularisation).
_REFERENCE_SQL = [
    # 0 — summary
    "SELECT count(*) AS total_requests, count(*) FILTER (WHERE status_code < 400) "
    "AS successful_requests, avg(duration_ms) AS average_duration_ms, "
    "percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_duration_ms, "
    "count(*) FILTER (WHERE asr_success IS NOT NULL) AS asr_total, "
    "count(*) FILTER (WHERE asr_success IS TRUE) AS asr_successes, "
    "count(*) FILTER (WHERE nlu_out_of_scope IS NOT NULL) AS nlu_total, "
    "count(*) FILTER (WHERE nlu_out_of_scope IS FALSE) AS nlu_in_scope "
    "FROM admin_request_metrics "
    "WHERE observed_at >= NOW() - make_interval(days => :days)",
    # 1 — daily
    "SELECT CAST(observed_at AS date) AS day, count(*) AS requests, "
    "count(*) FILTER ( WHERE status_code >= 400 OR asr_success IS FALSE "
    "OR nlu_out_of_scope IS TRUE ) AS errors FROM admin_request_metrics "
    "WHERE observed_at >= NOW() - make_interval(days => :days) "
    "GROUP BY CAST(observed_at AS date) ORDER BY day",
    # 2 — top_intents
    "SELECT intent AS label, count(*) AS count FROM admin_request_metrics "
    "WHERE observed_at >= NOW() - make_interval(days => :days) AND intent IS NOT NULL "
    "GROUP BY intent ORDER BY count DESC, intent LIMIT 8",
    # 3 — top_cultures
    "SELECT culture AS label, count(*) AS count FROM admin_request_metrics "
    "WHERE observed_at >= NOW() - make_interval(days => :days) AND culture IS NOT NULL "
    "GROUP BY culture ORDER BY count DESC, culture LIMIT 8",
    # 4 — endpoint_counts (pas de filtre IS NOT NULL)
    "SELECT endpoint AS label, count(*) AS count FROM admin_request_metrics "
    "WHERE observed_at >= NOW() - make_interval(days => :days) "
    "GROUP BY endpoint ORDER BY count DESC, endpoint LIMIT 8",
    # 5 — top_sources
    "SELECT source AS label, count(*) AS count FROM admin_request_metrics "
    "WHERE observed_at >= NOW() - make_interval(days => :days) AND source IS NOT NULL "
    "GROUP BY source ORDER BY count DESC, source LIMIT 8",
    # 6 — recent
    "SELECT observed_at, endpoint, method, status_code, duration_ms, intent, culture, "
    "source, asr_success, nlu_out_of_scope FROM admin_request_metrics "
    "WHERE observed_at >= NOW() - make_interval(days => :days) "
    "ORDER BY observed_at DESC LIMIT :recent_limit",
    # 7 — errors
    "SELECT observed_at, endpoint, method, status_code, duration_ms, intent, culture, "
    "source, asr_success, nlu_out_of_scope FROM admin_request_metrics "
    "WHERE observed_at >= NOW() - make_interval(days => :days) "
    "AND ( status_code >= 400 OR asr_success IS FALSE OR nlu_out_of_scope IS TRUE ) "
    "ORDER BY observed_at DESC LIMIT :recent_limit",
]


def _no_ws(s: str) -> str:
    return "".join(s.split())


class _FakeResult:
    def one(self):
        return MagicMock()

    def all(self):
        return []


class _FakeConn:
    def __init__(self, sink):
        self._sink = sink

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params):
        self._sink.append(str(sql))
        return _FakeResult()


def _capture_sql() -> list[str]:
    captured: list[str] = []
    fake_engine = MagicMock()
    fake_engine.connect.return_value = _FakeConn(captured)
    with patch.object(am, "_get_metrics_engine", return_value=fake_engine):
        # L'assemblage final échoue sur des rows mockées, mais les 8 execute()
        # ont déjà eu lieu — c'est tout ce qu'on veut capturer.
        try:
            am.get_dashboard_data(days=7, recent_limit=10)
        except Exception:
            pass
    return captured


def test_dashboard_emits_eight_queries_in_order():
    captured = _capture_sql()
    assert len(captured) == 8


@pytest.mark.parametrize("index", range(8))
def test_dashboard_sql_matches_reference(index):
    captured = _capture_sql()
    assert _no_ws(captured[index]) == _no_ws(_REFERENCE_SQL[index])


class TestGroupedCountsGuard:
    def test_colonne_autorisee_ok(self):
        # Ne doit pas lever pour une colonne de l'allow-list (conn mocké).
        conn = MagicMock()
        conn.execute.return_value.all.return_value = []
        am._query_grouped_counts(conn, {"days": 7}, "intent")

    def test_colonne_non_autorisee_rejetee(self):
        with pytest.raises(ValueError, match="non autorisée"):
            am._query_grouped_counts(MagicMock(), {}, "evil; DROP TABLE x")
