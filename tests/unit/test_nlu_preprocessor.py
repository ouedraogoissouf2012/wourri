"""
Tests pour `app/services/chat/nlu_preprocessor.py` (refactor P2-09 PR 3/5).

Couvre :
    - preprocess_nlu() : 6 branches
      (FR pur → skip NLU, bambara vide → skip, fallback FR mode BOTH,
       NLU OK, hors-sujet, exception NLU)
    - enrich_for_deepseek() : 3 branches (culture, animal, aucun sujet)
    - Constantes CULTURE_LABELS / ANIMAL_LABELS / ACTION_TO_INTENT
      (verification existence + non-vide)
    - Compat back-compat : import depuis chat_service (NLUResult + dicts)

Module PUR (fonctions module-level). Tests avec monkeypatch sur
`get_nlu_service` pour eviter de charger les modeles ML.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.models.schemas import Language
from app.services.chat.nlu_preprocessor import (
    NLUResult,
    CULTURE_LABELS,
    ANIMAL_LABELS,
    ACTION_TO_INTENT,
    preprocess_nlu,
    enrich_for_deepseek,
)


# ─────────────────────────────────────────────
# enrich_for_deepseek — 3 branches
# ─────────────────────────────────────────────


def test_enrich_avec_culture():
    """Concept CULTURE_RIZ → prefixe [Paysan cultive: riz]."""
    result = enrich_for_deepseek("Quand semer ?", {"CULTURE_RIZ": True})
    assert result == "[Paysan cultive: riz] Quand semer ?"


def test_enrich_avec_animal_si_pas_culture():
    """Aucune culture mais animal → prefixe [Paysan cultive: poulets]."""
    result = enrich_for_deepseek("Comment soigner ?", {"ANIMAL_POULET": True})
    assert result == "[Paysan cultive: poulets] Comment soigner ?"


def test_enrich_culture_prioritaire_sur_animal():
    """Si culture ET animal → culture priorise (1er hit dans concepts)."""
    result = enrich_for_deepseek(
        "Ma question",
        {"CULTURE_MAIS": True, "ANIMAL_BOVIN": True},
    )
    assert "maïs" in result and "bovins" not in result


def test_enrich_sans_sujet_pas_de_prefixe():
    """Aucun concept culture/animal → phrase inchangee."""
    result = enrich_for_deepseek("Bonjour", {"ACTION_PLANTER": True})
    assert result == "Bonjour"


def test_enrich_concepts_vides_pas_de_prefixe():
    """Concepts vide → phrase inchangee."""
    assert enrich_for_deepseek("Hello", {}) == "Hello"


# ─────────────────────────────────────────────
# preprocess_nlu — branches simples
# ─────────────────────────────────────────────


def test_preprocess_nlu_fr_pur_skip_nlu():
    """language=FRENCH → skip NLU, retourne message inchange."""
    result = preprocess_nlu("Quand semer du riz ?", None, Language.FRENCH)
    assert result.message_for_deepseek == "Quand semer du riz ?"
    assert result.intent is None
    assert result.concepts == {}
    assert result.is_out_of_scope is False


def test_preprocess_nlu_dioula_sans_texte_retourne_message():
    """language=DIOULA mais aucun texte bambara/dioula detecte → message inchange."""
    # Message FR pur sans caracteres bambara → text_to_analyze reste vide
    # → early return NLUResult inchange.
    result = preprocess_nlu("Bonjour comment vas tu", None, Language.DIOULA)
    assert result.message_for_deepseek == "Bonjour comment vas tu"


def test_preprocess_nlu_bambara_chars_detectes(monkeypatch):
    """Message contenant `ɛ`/`ɔ`/`ɲ` → declenche NLU sur le message lui-meme."""
    # Mock get_nlu_service pour controler la sortie
    mock_nlu_service = MagicMock()
    mock_result = MagicMock(
        is_out_of_scope=False,
        concepts={"CULTURE_RIZ": True},
        french_sentence="Quand semer le riz",
        intent="QUESTION_SAISON_PLANTATION",
    )
    mock_nlu_service.process = MagicMock(return_value=mock_result)
    monkeypatch.setattr(
        "app.services.nlu.get_nlu_service",
        lambda: mock_nlu_service,
    )

    result = preprocess_nlu(
        "I bɛ malo sɛnɛ tuma juma?",  # contient ɛ
        None,
        Language.DIOULA,
    )
    assert result.intent == "QUESTION_SAISON_PLANTATION"
    assert "CULTURE_RIZ" in result.concepts
    assert "[Paysan cultive: riz]" in result.message_for_deepseek


def test_preprocess_nlu_fallback_fr_mode_both(monkeypatch):
    """Sprint G.1 (#171/#191) : mode BOTH + pas de texte dioula → NLU sur FR."""
    mock_nlu_service = MagicMock()
    mock_result = MagicMock(
        is_out_of_scope=False,
        concepts={"CULTURE_MAIS": True, "ACTION_PLANTER": True},
        french_sentence="Quand planter le maïs",
        intent="QUESTION_SAISON_PLANTATION",
    )
    mock_nlu_service.process = MagicMock(return_value=mock_result)
    monkeypatch.setattr(
        "app.services.nlu.get_nlu_service",
        lambda: mock_nlu_service,
    )

    result = preprocess_nlu(
        "Je veux planter du maïs",  # FR pur sans bambara_text
        None,
        Language.BOTH,
    )
    # Le fallback FR a fonctionne : NLU a vu la phrase FR
    assert result.intent == "QUESTION_SAISON_PLANTATION"
    assert "CULTURE_MAIS" in result.concepts


def test_preprocess_nlu_hors_sujet(monkeypatch):
    """NLU detecte hors-sujet → flag is_out_of_scope=True + intent=HORS_SUJET."""
    mock_nlu_service = MagicMock()
    mock_result = MagicMock(
        is_out_of_scope=True,
        out_of_scope_message_fr="Question hors agricole",
        concepts={},
        french_sentence=None,
        intent=None,
    )
    mock_nlu_service.process = MagicMock(return_value=mock_result)
    monkeypatch.setattr(
        "app.services.nlu.get_nlu_service",
        lambda: mock_nlu_service,
    )

    result = preprocess_nlu("ɛkélan", None, Language.DIOULA)
    assert result.is_out_of_scope is True
    assert result.intent == "HORS_SUJET"
    assert result.message_for_deepseek == "Question hors agricole"


def test_preprocess_nlu_exception_retourne_message_inchange(monkeypatch):
    """Si get_nlu_service leve, on retourne le message inchange (defensive)."""
    def raise_error():
        raise RuntimeError("NLU pas disponible")

    monkeypatch.setattr("app.services.nlu.get_nlu_service", raise_error)

    result = preprocess_nlu("I bɛ malo ɲini", None, Language.DIOULA)
    # Pas de crash, message renvoye sans NLU
    assert result.message_for_deepseek == "I bɛ malo ɲini"
    assert result.intent is None


def test_preprocess_nlu_service_none(monkeypatch):
    """Si get_nlu_service retourne None (NLU indisponible) → message inchange."""
    monkeypatch.setattr("app.services.nlu.get_nlu_service", lambda: None)

    result = preprocess_nlu(
        "I bɛ malo sɛnɛ",  # contient bambara chars
        None,
        Language.DIOULA,
    )
    assert result.intent is None


# ─────────────────────────────────────────────
# Constantes labels
# ─────────────────────────────────────────────


def test_culture_labels_non_vide_et_format():
    """CULTURE_LABELS contient les cultures principales avec format CULTURE_X→nom_fr."""
    assert len(CULTURE_LABELS) >= 15
    assert CULTURE_LABELS["CULTURE_RIZ"] == "riz"
    assert CULTURE_LABELS["CULTURE_MAIS"] == "maïs"
    # Toutes les clefs commencent par CULTURE_
    assert all(k.startswith("CULTURE_") for k in CULTURE_LABELS)


def test_animal_labels_non_vide():
    """ANIMAL_LABELS contient les animaux principaux."""
    assert len(ANIMAL_LABELS) >= 5
    assert ANIMAL_LABELS["ANIMAL_POULET"] == "poulets"
    assert all(k.startswith("ANIMAL_") for k in ANIMAL_LABELS)


def test_action_to_intent_mapping():
    """ACTION_TO_INTENT mappe les actions NLU vers les intents IVR."""
    assert ACTION_TO_INTENT["ACTION_PLANTER"] == "QUESTION_SAISON_PLANTATION"
    assert ACTION_TO_INTENT["ACTION_RECOLTER"] == "QUESTION_RECOLTE"
    # Toutes les clefs commencent par ACTION_, toutes valeurs par QUESTION_/CONSEIL_/DIAGNOSTIC_
    assert all(k.startswith("ACTION_") for k in ACTION_TO_INTENT)
    assert all(
        v.startswith(("QUESTION_", "CONSEIL_", "DIAGNOSTIC_"))
        for v in ACTION_TO_INTENT.values()
    )


# ─────────────────────────────────────────────
# Back-compat : import depuis chat_service
# ─────────────────────────────────────────────


def test_back_compat_nlu_result_import_chat_service():
    """`from app.services.chat_service import NLUResult` doit toujours fonctionner."""
    from app.services.chat_service import NLUResult as NLUResult_compat
    # Verifie que c'est la MEME classe (alias, pas copie)
    assert NLUResult_compat is NLUResult


def test_back_compat_dicts_import_chat_service():
    """Les dicts re-exportes depuis chat_service avec prefixe `_` doivent matcher."""
    from app.services.chat_service import _CULTURE_LABELS, _ANIMAL_LABELS, _ACTION_TO_INTENT
    assert _CULTURE_LABELS is CULTURE_LABELS
    assert _ANIMAL_LABELS is ANIMAL_LABELS
    assert _ACTION_TO_INTENT is ACTION_TO_INTENT
