"""
Tests pour `app/services/chat/handlers/both_handler.py` (ADR-0015 PR 2/4).

Mode `Language.BOTH` herite de `DioulaHandler` sans override. Les tests ici
verifient :
    - L'heritage est correct (BothHandler IS-A DioulaHandler)
    - L'instance dans HANDLERS[BOTH] est de type BothHandler
    - Le pipeline cascade fonctionne de bout en bout en mode BOTH
    - Le champ ChatResult.language reflete bien "both" (relaye par les fonctions
      de cascade qui utilisent `language.value`)

Pour les tests exhaustifs de la cascade 3 niveaux, voir `test_dioula_handler.py`.

Ref : ADR-0015 docs/adr/0015-strategy-pattern-cascade-chat-et-anglais.md
Issue : #277 (PR 2/4)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.models.schemas import Language
from app.services.chat._types import ChatResult
from app.services.chat.handlers import HANDLERS, BothHandler, DioulaHandler
from app.services.chat.nlu_preprocessor import NLUResult


def _make_nlu(intent=None, concepts=None) -> NLUResult:
    return NLUResult(
        message_for_deepseek="ma question",
        intent=intent,
        concepts=concepts or {},
    )


# ─────────────────────────────────────────────
# Heritage et registre
# ─────────────────────────────────────────────


class TestInheritanceAndRegistry:
    def test_both_handler_inherits_from_dioula_handler(self):
        """BothHandler doit etre une sous-classe de DioulaHandler (cascade identique)."""
        assert issubclass(BothHandler, DioulaHandler)

    def test_both_handler_instance_is_dioula_handler(self):
        handler = BothHandler()
        assert isinstance(handler, DioulaHandler)
        assert isinstance(handler, BothHandler)

    def test_both_handler_is_in_registry(self):
        assert Language.BOTH in HANDLERS
        assert isinstance(HANDLERS[Language.BOTH], BothHandler)

    def test_both_handler_distinct_from_dioula_in_registry(self):
        """HANDLERS[BOTH] doit etre une instance distincte de HANDLERS[DIOULA]
        pour permettre des overrides futurs sans contamination croisee."""
        assert HANDLERS[Language.BOTH] is not HANDLERS[Language.DIOULA]


# ─────────────────────────────────────────────
# Pipeline cascade en mode BOTH
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_both_handler_cascade_atteint_deepseek_avec_language_both():
    """Mode BOTH : cascade traverse les 3 niveaux et relaye language=BOTH au DeepSeek."""
    nlu = _make_nlu(intent=None, concepts={})
    handler = BothHandler()
    ds_result = ChatResult(
        response="Reponse FR",
        response_dioula="Reponse bambara",
        city="Abidjan",
        language="both",
        meta={"source": "deepseek_open"},
    )

    with patch(
        "app.services.chat.ivr_searcher.try_ivr_exact",
        new=AsyncMock(),
    ) as mock_ivr_exact, patch(
        "app.services.chat.ivr_searcher.try_ivr_concept",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.services.chat.deepseek_router.try_deepseek_dioula",
        new=AsyncMock(return_value=ds_result),
    ) as mock_ds:
        result = await handler.process(
            nlu=nlu,
            weather_data=None,
            city="Abidjan",
            include_audio=False,
            language=Language.BOTH,
            user_id="u1",
        )

    # nlu.intent=None → niveau 1 skippe
    mock_ivr_exact.assert_not_called()
    # Niveau 3 atteint avec language=BOTH transmis
    mock_ds.assert_called_once()
    ds_kwargs = mock_ds.call_args.kwargs
    assert ds_kwargs["language"] == Language.BOTH
    assert result.language == "both"


@pytest.mark.asyncio
async def test_both_handler_ivr_exact_retourne_match():
    """Mode BOTH : si IVR exact match, on l'utilise directement."""
    nlu = _make_nlu(intent="CONSEIL_PRODUCTION", concepts={"CULTURE_RIZ": True})
    handler = BothHandler()
    ivr_result = ChatResult(
        response="Plantez le riz",
        response_dioula="Aw ye malo sɛnɛ",
        city="Abidjan",
        language="both",
        meta={"source": "ivr_exact"},
    )

    with patch(
        "app.services.chat.ivr_searcher.try_ivr_exact",
        new=AsyncMock(return_value=ivr_result),
    ) as mock_ivr_exact, patch(
        "app.services.chat.ivr_searcher.try_ivr_concept",
        new=AsyncMock(),
    ) as mock_ivr_concept, patch(
        "app.services.chat.deepseek_router.try_deepseek_dioula",
        new=AsyncMock(),
    ) as mock_ds:
        result = await handler.process(
            nlu=nlu,
            weather_data=None,
            city="Abidjan",
            include_audio=False,
            language=Language.BOTH,
            user_id=None,
        )

    assert result is ivr_result
    # Verifier que language=BOTH a ete transmis au niveau 1
    ivr_kwargs = mock_ivr_exact.call_args.kwargs
    assert ivr_kwargs["language"] == Language.BOTH
    mock_ivr_concept.assert_not_called()
    mock_ds.assert_not_called()
