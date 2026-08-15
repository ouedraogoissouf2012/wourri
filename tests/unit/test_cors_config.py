"""Tests — parsing des origines CORS depuis ALLOWED_ORIGINS (L4 #411).

Le champ `allowed_origins` (CSV lu depuis l'env `ALLOWED_ORIGINS`) doit être
exposé en liste propre via `Settings.cors_allowed_origins` : vide -> [], espaces
et entrées vides ignorés. Utilisé par app/main.py pour le CORS en production
(allow-list explicite, jamais "*").
"""
from app.config import Settings


def test_cors_origins_empty_gives_empty_list():
    assert Settings(allowed_origins="").cors_allowed_origins == []


def test_cors_origins_single():
    assert Settings(allowed_origins="https://wouri-site.vercel.app").cors_allowed_origins == [
        "https://wouri-site.vercel.app"
    ]


def test_cors_origins_multiple_are_split_and_stripped():
    s = Settings(allowed_origins=" https://a.ci , https://b.ci ,")
    assert s.cors_allowed_origins == ["https://a.ci", "https://b.ci"]


def test_cors_origins_default_is_empty():
    # Sans ALLOWED_ORIGINS -> aucune origine (refus cross-origin par défaut, sûr).
    assert Settings().cors_allowed_origins == []
