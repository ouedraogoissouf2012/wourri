"""Contrats de l'ADR-0019 : le feedback est un signal, jamais une validation.

- Un 👍 sur une réponse de fallback dépose un CANDIDAT (pending_native_review)
  dans feedback_candidates.jsonl — PAS d'ajout au corpus.
- Un 👍 sur ivr_exact ne produit aucun candidat.
- Un 👎 logue en négatif, jamais de candidat.
- Aucune entrée `auto_validated` / `auto_appris` n'est créée par le feedback.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from starlette.requests import Request

import app.routers.feedback as fb


def _make_request() -> Request:
    """Construit un vrai starlette.Request minimal (exigé par le décorateur slowapi)."""
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/feedback/positif",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "query_string": b"",
    }
    return Request(scope)


def _run_positif(req):
    return asyncio.run(fb.feedback_positif(_make_request(), req))


def _run_negatif(req):
    return asyncio.run(fb.feedback_negatif(_make_request(), req))


@pytest.fixture
def redirect_files(tmp_path, monkeypatch):
    """Redirige les fichiers JSONL du router vers un dossier temporaire."""
    cand = tmp_path / "feedback_candidates.jsonl"
    log = tmp_path / "feedback.jsonl"
    neg = tmp_path / "feedback_negatif.jsonl"
    monkeypatch.setattr(fb, "FEEDBACK_CANDIDATES_LOG", str(cand))
    monkeypatch.setattr(fb, "FEEDBACK_LOG", str(log))
    monkeypatch.setattr(fb, "FEEDBACK_NEGATIF_LOG", str(neg))
    return SimpleNamespace(candidates=cand, log=log, negatif=neg)


def _req(**kw):
    base = dict(
        user_id="221600000000",
        reponse_bambara="Aw ye foro labɛn ka ɲɛ.",
        reponse_fr="Prépare bien ton champ.",
        intent="CONSEIL_PRODUCTION",
        cultures=["CULTURE_MAIS"],
        source="ivr_fallback",
    )
    base.update(kw)
    return fb.FeedbackRequest(**base)


def test_positif_fallback_deposits_candidate_not_corpus(redirect_files, monkeypatch):
    # Garde-fou : ajouter_reponse_validee ne DOIT PAS être appelé (ADR-0019).
    called = {"corpus": False}

    def _boom(*a, **k):
        called["corpus"] = True
        raise AssertionError("ADR-0019 violé : ajout direct au corpus interdit")

    monkeypatch.setattr("app.services.corpus_facade.ajouter_reponse_validee", _boom, raising=False)

    resp = _run_positif(_req(source="ivr_fallback"))

    assert resp["action"] == "candidate_queued"
    assert called["corpus"] is False
    # Un candidat a bien été écrit, en statut à revoir.
    lines = redirect_files.candidates.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    cand = json.loads(lines[0])
    assert cand["status"] == "pending_native_review"
    assert cand["reponse_bambara"] == "Aw ye foro labɛn ka ɲɛ."
    assert cand["source"] == "ivr_fallback"


def test_positif_fallback_generic_also_queues_candidate(redirect_files):
    resp = _run_positif(_req(source="fallback_generic"))
    assert resp["action"] == "candidate_queued"
    assert redirect_files.candidates.exists()


def test_positif_ivr_exact_produces_no_candidate(redirect_files):
    resp = _run_positif(_req(source="ivr_exact"))
    assert resp["action"] == "logged"
    # Aucun fichier candidat créé.
    assert not redirect_files.candidates.exists()


def test_positif_empty_bambara_produces_no_candidate(redirect_files):
    resp = _run_positif(_req(source="ivr_fallback", reponse_bambara=""))
    assert resp["action"] == "logged"
    assert not redirect_files.candidates.exists()


def test_negatif_never_creates_candidate(redirect_files):
    resp = _run_negatif(_req(source="ivr_fallback"))
    assert resp["action"] == "logged"
    assert not redirect_files.candidates.exists()
