"""Contrats de l'ADR-0019 : le feedback est un signal, jamais une validation.

Condition corrigée par #359 — la file de revue native cible le dioula MACHINE :
- Un 👍 sur deepseek_open (traduction NLLB du fallback DeepSeek) dépose un
  CANDIDAT (pending_native_review) dans feedback_candidates.jsonl — PAS d'ajout
  au corpus.
- Un 👍 sur ivr_exact OU ivr_fallback (texte déjà issu du corpus validé) ne
  produit aucun candidat.
- deepseek_open sans caractères dioula (réponse FR non traduite,
  include_audio=False) ne produit aucun candidat.
- Un 👎 logue en négatif, jamais de candidat.
- Aucune entrée `auto_validated` / `auto_appris` n'est créée par le feedback.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

import app.routers.feedback as fb


def _run_positif(req):
    return asyncio.run(fb.feedback_positif(req))


def _run_negatif(req):
    return asyncio.run(fb.feedback_negatif(req))


@pytest.fixture
def redirect_files(tmp_path, monkeypatch):
    """Redirige les fichiers JSONL du router vers un dossier temporaire."""
    cand = tmp_path / "feedback_candidates.jsonl"
    neg = tmp_path / "feedback_negatif.jsonl"
    monkeypatch.setattr(fb, "FEEDBACK_CANDIDATES_LOG", str(cand))
    # ADR-0025 : le log général est mensuel (feedback-YYYY-MM.jsonl) dans LOG_DIR
    monkeypatch.setattr(fb, "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(fb, "FEEDBACK_NEGATIF_LOG", str(neg))
    return SimpleNamespace(candidates=cand, log_dir=tmp_path, negatif=neg)


def _req(**kw):
    base = dict(
        user_id="221600000000",
        reponse_bambara="Aw ye foro labɛn ka ɲɛ.",
        reponse_fr="Prépare bien ton champ.",
        intent="CONSEIL_PRODUCTION",
        cultures=["CULTURE_MAIS"],
        source="deepseek_open",
    )
    base.update(kw)
    return fb.FeedbackRequest(**base)


def test_log_general_ecrit_dans_fichier_mensuel(redirect_files):
    """ADR-0025 : le log général part dans feedback-YYYY-MM.jsonl du mois
    courant (même horloge date.today() que le handler et la purge)."""
    from datetime import date

    from app.core.log_retention import monthly_feedback_filename

    _run_positif(_req(source="ivr_exact"))

    monthly = redirect_files.log_dir / monthly_feedback_filename(date.today())
    assert monthly.exists()
    entry = json.loads(monthly.read_text(encoding="utf-8").strip().splitlines()[0])
    assert entry["vote"] == "positif"
    assert entry["user"].startswith("usr_")  # pseudonymisé, jamais brut


def test_positif_deepseek_open_deposits_candidate_not_corpus(redirect_files, monkeypatch):
    # Garde-fou : ajouter_reponse_validee ne DOIT PAS être appelé (ADR-0019).
    called = {"corpus": False}

    def _boom(*a, **k):
        called["corpus"] = True
        raise AssertionError("ADR-0019 violé : ajout direct au corpus interdit")

    monkeypatch.setattr("app.services.corpus_service.ajouter_reponse_validee", _boom, raising=False)

    resp = _run_positif(_req(source="deepseek_open"))

    assert resp["action"] == "candidate_queued"
    assert called["corpus"] is False
    # Un candidat a bien été écrit, en statut à revoir.
    lines = redirect_files.candidates.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    cand = json.loads(lines[0])
    assert cand["status"] == "pending_native_review"
    assert cand["reponse_bambara"] == "Aw ye foro labɛn ka ɲɛ."
    assert cand["source"] == "deepseek_open"


def test_positif_ivr_fallback_is_corpus_text_no_candidate(redirect_files):
    """#359 : ivr_fallback = texte déjà issu du corpus validé — plus de mise
    en file (l'ancienne condition le capturait à tort)."""
    resp = _run_positif(_req(source="ivr_fallback"))
    assert resp["action"] == "logged"
    assert not redirect_files.candidates.exists()


def test_positif_fallback_generic_legacy_value_no_candidate(redirect_files):
    """`fallback_generic` n'est produit nulle part dans l'API (vérifié #359) —
    une valeur legacy reçue ne déclenche plus la file."""
    resp = _run_positif(_req(source="fallback_generic"))
    assert resp["action"] == "logged"
    assert not redirect_files.candidates.exists()


def test_positif_ivr_exact_produces_no_candidate(redirect_files):
    resp = _run_positif(_req(source="ivr_exact"))
    assert resp["action"] == "logged"
    assert not redirect_files.candidates.exists()


def test_positif_deepseek_english_produces_no_candidate(redirect_files):
    """Le mode EN produit de l'anglais — rien à faire valider par le natif dioula."""
    resp = _run_positif(
        _req(source="deepseek_english", reponse_bambara="Plant your maize early.")
    )
    assert resp["action"] == "logged"
    assert not redirect_files.candidates.exists()


def test_positif_deepseek_open_without_dioula_chars_no_candidate(redirect_files):
    """Garde #359 : avec include_audio=False, response_dioula est la réponse
    FRANÇAISE non traduite — elle ne doit pas polluer la file de revue native."""
    resp = _run_positif(
        _req(
            source="deepseek_open",
            reponse_bambara="Preparez bien votre champ avant les pluies.",
        )
    )
    assert resp["action"] == "logged"
    assert not redirect_files.candidates.exists()


def test_positif_empty_bambara_produces_no_candidate(redirect_files):
    resp = _run_positif(_req(source="deepseek_open", reponse_bambara=""))
    assert resp["action"] == "logged"
    assert not redirect_files.candidates.exists()


def test_negatif_never_creates_candidate(redirect_files):
    resp = _run_negatif(_req(source="deepseek_open"))
    assert resp["action"] == "logged"
    assert not redirect_files.candidates.exists()
