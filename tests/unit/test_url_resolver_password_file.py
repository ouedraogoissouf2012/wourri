"""Tests de l'assemblage d'URL Postgres par composants (issue #258).

`resolve_postgres_url` gagne une 3e source : quand POSTGRES_URL (env) et
Settings.postgres_url sont absents mais que POSTGRES_HOST est défini, l'URL
est assemblée depuis POSTGRES_HOST/PORT/USER/DB + mot de passe lu en priorité
depuis POSTGRES_PASSWORD_FILE (Docker secret, helper partagé
app/core/secrets.py) avec fallback POSTGRES_PASSWORD (env).

Élimine la duplication du mot de passe dans docker-compose.prod.yml
(1× secret pour postgres, 1× env interpolée dans POSTGRES_URL).
"""
from __future__ import annotations

import pytest

from app.db.url_resolver import resolve_postgres_url


@pytest.fixture
def env_components(monkeypatch, tmp_path):
    """Env propre : pas d'URL directe, composants posés par le test.

    - chdir(tmp_path) : Settings lit `.env` du CWD (Config.env_file) — sur un
      poste dev avec un .env contenant POSTGRES_URL, la source n°2 du
      resolver court-circuiterait l'assemblage et ferait échouer ces tests
      localement alors que la CI (sans .env) serait verte.
    - cache_clear avant ET après : ne pas laisser un Settings pollué
      (construit dans le tmp_path) aux autres fichiers de tests.
    """
    monkeypatch.chdir(tmp_path)
    for var in (
        "POSTGRES_URL",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_USER",
        "POSTGRES_DB",
        "POSTGRES_PASSWORD",
        "POSTGRES_PASSWORD_FILE",
    ):
        monkeypatch.delenv(var, raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
    yield monkeypatch
    monkeypatch.undo()
    get_settings.cache_clear()


def _set_base(monkeypatch):
    monkeypatch.setenv("POSTGRES_HOST", "postgres")
    monkeypatch.setenv("POSTGRES_USER", "wourri")
    monkeypatch.setenv("POSTGRES_DB", "wourri_prod")


def test_password_depuis_fichier_seul(env_components, tmp_path):
    """Cas 1 (critère de done) : file only."""
    secret = tmp_path / "postgres_password"
    secret.write_text("s3cret_fichier\n", encoding="utf-8")
    _set_base(env_components)
    env_components.setenv("POSTGRES_PASSWORD_FILE", str(secret))

    url = resolve_postgres_url()

    assert url == "postgresql+psycopg://wourri:s3cret_fichier@postgres:5432/wourri_prod"


def test_password_depuis_env_seul(env_components):
    """Cas 2 : env only (backward-compat)."""
    _set_base(env_components)
    env_components.setenv("POSTGRES_PASSWORD", "s3cret_env")

    url = resolve_postgres_url()

    assert url == "postgresql+psycopg://wourri:s3cret_env@postgres:5432/wourri_prod"


def test_fichier_prioritaire_sur_env(env_components, tmp_path):
    """Les deux définis → le fichier gagne (un seul point de vérité)."""
    secret = tmp_path / "pw"
    secret.write_text("du_fichier", encoding="utf-8")
    _set_base(env_components)
    env_components.setenv("POSTGRES_PASSWORD_FILE", str(secret))
    env_components.setenv("POSTGRES_PASSWORD", "de_l_env")

    assert "du_fichier" in resolve_postgres_url()


def test_ni_fichier_ni_env_leve_erreur_explicite(env_components):
    """Cas 3 : neither → RuntimeError nommant le manque (host défini =
    intention claire d'assemblage, config incomplète = fail loud)."""
    _set_base(env_components)

    with pytest.raises(RuntimeError, match="POSTGRES_PASSWORD"):
        resolve_postgres_url()


def test_ni_fichier_ni_env_contrat_skip_retourne_vide(env_components):
    """Contrat skipif des tests d'intégration préservé : raise_on_missing=False
    ne lève jamais, même sur config partielle."""
    _set_base(env_components)

    assert resolve_postgres_url(raise_on_missing=False) == ""


def test_postgres_url_env_reste_prioritaire(env_components, tmp_path):
    """POSTGRES_URL explicite court-circuite l'assemblage par composants."""
    secret = tmp_path / "pw"
    secret.write_text("ignore", encoding="utf-8")
    _set_base(env_components)
    env_components.setenv("POSTGRES_PASSWORD_FILE", str(secret))
    env_components.setenv("POSTGRES_URL", "postgresql+psycopg://direct:d@h:5/db")

    assert resolve_postgres_url() == "postgresql+psycopg://direct:d@h:5/db"


def test_password_fichier_avec_bom_utf8(env_components, tmp_path):
    """Un BOM U+FEFF (fichier réécrit via éditeur Windows) est retiré —
    parité avec lib/secrets.js côté whatsapp-server (.trim() JS)."""
    secret = tmp_path / "pw"
    secret.write_bytes("﻿cle_bom\n".encode("utf-8"))
    _set_base(env_components)
    env_components.setenv("POSTGRES_PASSWORD_FILE", str(secret))

    assert ":cle_bom@" in resolve_postgres_url()


def test_password_caracteres_speciaux_encode(env_components):
    """Un mot de passe avec :/@ doit être URL-encodé (sinon l'URL est fausse)."""
    _set_base(env_components)
    env_components.setenv("POSTGRES_PASSWORD", "p@ss:w/ord%1")

    url = resolve_postgres_url()

    assert "p%40ss%3Aw%2Ford%251@postgres" in url
    assert "p@ss:w/ord" not in url


def test_password_avec_espace_round_trip_sqlalchemy(env_components):
    """Espace encodé %20 (PAS '+' : make_url/unquote ne re-décode pas '+')
    et espaces de bord du mot de passe env PRÉSERVÉS (pas de strip —
    l'ancienne interpolation compose passait la valeur telle quelle)."""
    from sqlalchemy.engine.url import make_url

    _set_base(env_components)
    env_components.setenv("POSTGRES_PASSWORD", " mot de passe ")

    url = resolve_postgres_url()

    assert "%20mot%20de%20passe%20@" in url
    assert make_url(url).password == " mot de passe "


def test_port_custom_respecte(env_components):
    _set_base(env_components)
    env_components.setenv("POSTGRES_PORT", "5433")
    env_components.setenv("POSTGRES_PASSWORD", "x")

    assert "@postgres:5433/" in resolve_postgres_url()


def test_sans_host_comportement_precedent(env_components):
    """Sans POSTGRES_HOST : le chemin composants est inactif (RuntimeError
    comme avant / '' en mode skip)."""
    env_components.setenv("POSTGRES_USER", "wourri")
    env_components.setenv("POSTGRES_PASSWORD", "x")

    with pytest.raises(RuntimeError):
        resolve_postgres_url()
    assert resolve_postgres_url(raise_on_missing=False) == ""
