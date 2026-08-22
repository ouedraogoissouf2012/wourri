from app.services.fingerprint import fingerprint
from app.services.auth import sign_session, read_session


def test_fingerprint_stable():
    a = fingerprint(language="bci", text_local="Bonjour", text_fr="Hi")
    b = fingerprint(language="bci", text_local="  bonjour ", text_fr="hi")
    assert a == b
    assert fingerprint(language="dyu", text_local="Bonjour", text_fr="Hi") != a


def test_session_roundtrip(monkeypatch):
    monkeypatch.setenv("LQE_SECRET", "unit-test-secret-16")
    tok = sign_session("u1", "bci", ["review"])
    sess = read_session(tok)
    assert sess["u"] == "u1"
    assert sess["lang"] == "bci"
    assert "review" in sess["roles"]
