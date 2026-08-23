def test_create_user_unknown_language(seeded, tmp_path, monkeypatch):
    monkeypatch.setenv("LQE_DATA_DIR", str(tmp_path))
    from app.services.users import create_user
    r = create_user(user="x", password="password1", language="xyz", roles=["review"])
    assert r["ok"] is False
    assert r["reason"] == "unknown_language"


def test_create_and_find(seeded, tmp_path, monkeypatch):
    monkeypatch.setenv("LQE_DATA_DIR", str(tmp_path))
    from app.services.users import create_user, find_user
    from app.services.passwords import verify_password
    r = create_user(user="nana", password="password1", language="dyu", roles=["review"])
    assert r["ok"] is True
    rec = find_user("nana")
    assert rec["language"] == "dyu"
    assert rec["roles"] == ["review"]
    assert verify_password("password1", rec["password_hash"])
    assert "password" not in rec


def test_create_admin_gets_wildcard_language(tmp_path, monkeypatch):
    # l'admin court-circuite is_known → aucun besoin de Postgres/seed ici
    monkeypatch.setenv("LQE_DATA_DIR", str(tmp_path))
    from app.services.users import create_user, find_user
    r = create_user(user="patron", password="password1", language="dyu", roles=["admin"])
    assert r["ok"] is True
    rec = find_user("patron")
    assert rec["language"] == "*"
    assert "admin" in rec["roles"]
