"""Session locuteur — signature cookie, pas de PII téléphone."""
from app.services.speaker_session import read_session, sign_session


def test_sign_and_read_roundtrip(monkeypatch):
    monkeypatch.setenv("API_SECRET_KEY", "test-secret-speaker-key-xx")
    from app.config import get_settings

    get_settings.cache_clear()
    token = sign_session("locuteur@example.com")
    sess = read_session(token)
    assert sess is not None
    assert sess["email"] == "locuteur@example.com"
    assert sess["lang"] == "dyu"


def test_tampered_cookie_rejected(monkeypatch):
    monkeypatch.setenv("API_SECRET_KEY", "test-secret-speaker-key-xx")
    from app.config import get_settings

    get_settings.cache_clear()
    token = sign_session("a@b.c")
    bad = token[:-4] + "dead"
    assert read_session(bad) is None


def test_push_bronze_unconfigured(monkeypatch):
    monkeypatch.delenv("CONVEX_BASE_URL", raising=False)
    monkeypatch.delenv("CONVEX_SITE_URL", raising=False)
    from app.services.lqe_convex_push import push_bronze_task

    assert push_bronze_task(intent="x", source="y", cultures=[], excerpt="z")["skipped"] == "unconfigured"
