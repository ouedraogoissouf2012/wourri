"""
Tests pour `app/services/chat/handlers/dioula_handler.py` (ADR-0015 PR 2/4).

Couvre la cascade 3 niveaux du handler DIOULA :
    - Niveau 1 (IVR exact) match     → retour direct
    - Niveau 1 None → niveau 2 (IVR concept) match → retour
    - Niveau 1 + 2 None → niveau 3 (DeepSeek dioula)
    - nlu.intent vide → skip niveau 1, va direct niveau 2
    - Protocol compliance (handler dans registre HANDLERS)

Pattern de mock : on patche les fonctions module-level orchestrees par
DioulaHandler (`try_ivr_exact`, `try_ivr_concept`, `try_deepseek_dioula`).
Ces fonctions ont deja leurs propres tests dans test_ivr_searcher.py et
test_deepseek_router.py. Ici on teste **l'orchestration** des 3 niveaux.

Ref : ADR-0015 docs/adr/0015-strategy-pattern-cascade-chat-et-anglais.md
Issue : #277 (PR 2/4)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.models.schemas import Language
from app.services.chat._types import ChatResult
from app.services.chat.handlers import HANDLERS, DioulaHandler
from app.services.chat.nlu_preprocessor import NLUResult


def _make_nlu(intent=None, concepts=None) -> NLUResult:
    return NLUResult(
        message_for_deepseek="ma question",
        intent=intent,
        concepts=concepts or {},
    )


def _make_chat_result(source: str, response: str = "x") -> ChatResult:
    """Helper : ChatResult avec source identifiable pour tracer le niveau atteint."""
    return ChatResult(
        response=response,
        city="Abidjan",
        language="dioula",
        meta={"source": source},
    )


# ─────────────────────────────────────────────
# Protocol compliance
# ─────────────────────────────────────────────


class TestProtocolCompliance:
    def test_dioula_handler_is_in_registry(self):
        assert Language.DIOULA in HANDLERS
        assert isinstance(HANDLERS[Language.DIOULA], DioulaHandler)

    def test_dioula_handler_satisfies_protocol(self):
        import inspect
        handler = DioulaHandler()
        assert hasattr(handler, "process")
        assert inspect.iscoroutinefunction(handler.process)


# ─────────────────────────────────────────────
# Cascade 3 niveaux — orchestration
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cascade_niveau_1_ivr_exact_match_retour_direct():
    """nlu.intent existe + IVR exact match → retour niveau 1, niveaux 2 et 3 jamais appeles."""
    nlu = _make_nlu(intent="CONSEIL_PRODUCTION", concepts={"CULTURE_RIZ": True})
    handler = DioulaHandler()
    ivr_exact_result = _make_chat_result("ivr_exact", "Conseil riz")

    with patch(
        "app.services.chat.ivr_searcher.try_ivr_exact",
        new=AsyncMock(return_value=ivr_exact_result),
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
            language=Language.DIOULA,
            user_id="u1",
        )

    assert result is ivr_exact_result
    assert result.meta["source"] == "ivr_exact"
    mock_ivr_exact.assert_called_once()
    mock_ivr_concept.assert_not_called()
    mock_ds.assert_not_called()


@pytest.mark.asyncio
async def test_cascade_niveau_1_none_niveau_2_match():
    """IVR exact retourne None → niveau 2 IVR concept tente → match → retour."""
    nlu = _make_nlu(intent="X", concepts={"CULTURE_RIZ": True})
    handler = DioulaHandler()
    ivr_concept_result = _make_chat_result("ivr_fallback", "Fallback concept")

    with patch(
        "app.services.chat.ivr_searcher.try_ivr_exact",
        new=AsyncMock(return_value=None),
    ) as mock_ivr_exact, patch(
        "app.services.chat.ivr_searcher.try_ivr_concept",
        new=AsyncMock(return_value=ivr_concept_result),
    ) as mock_ivr_concept, patch(
        "app.services.chat.deepseek_router.try_deepseek_dioula",
        new=AsyncMock(),
    ) as mock_ds:
        result = await handler.process(
            nlu=nlu,
            weather_data=None,
            city="Abidjan",
            include_audio=False,
            language=Language.DIOULA,
            user_id="u1",
        )

    assert result is ivr_concept_result
    assert result.meta["source"] == "ivr_fallback"
    mock_ivr_exact.assert_called_once()
    mock_ivr_concept.assert_called_once()
    mock_ds.assert_not_called()


@pytest.mark.asyncio
async def test_cascade_niveau_3_fallback_deepseek():
    """IVR exact + concept retournent None → niveau 3 DeepSeek dioula obligatoire."""
    nlu = _make_nlu(intent="X", concepts={"CULTURE_RIZ": True})
    handler = DioulaHandler()
    ds_result = _make_chat_result("deepseek_open", "DeepSeek FR")

    with patch(
        "app.services.chat.ivr_searcher.try_ivr_exact",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.services.chat.ivr_searcher.try_ivr_concept",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.services.chat.deepseek_router.try_deepseek_dioula",
        new=AsyncMock(return_value=ds_result),
    ) as mock_ds:
        result = await handler.process(
            nlu=nlu,
            weather_data={"city": "Abidjan", "temperature": 28},
            city="Abidjan",
            include_audio=True,
            language=Language.DIOULA,
            user_id="u1",
        )

    assert result is ds_result
    assert result.meta["source"] == "deepseek_open"
    mock_ds.assert_called_once()


@pytest.mark.asyncio
async def test_cascade_sans_intent_skip_niveau_1():
    """nlu.intent=None → IVR exact JAMAIS appele (skip niveau 1), va direct niveau 2."""
    nlu = _make_nlu(intent=None, concepts={"CULTURE_RIZ": True})
    handler = DioulaHandler()
    ivr_concept_result = _make_chat_result("ivr_fallback")

    with patch(
        "app.services.chat.ivr_searcher.try_ivr_exact",
        new=AsyncMock(),
    ) as mock_ivr_exact, patch(
        "app.services.chat.ivr_searcher.try_ivr_concept",
        new=AsyncMock(return_value=ivr_concept_result),
    ) as mock_ivr_concept, patch(
        "app.services.chat.deepseek_router.try_deepseek_dioula",
        new=AsyncMock(),
    ):
        result = await handler.process(
            nlu=nlu,
            weather_data=None,
            city="Abidjan",
            include_audio=False,
            language=Language.DIOULA,
            user_id=None,
        )

    assert result is ivr_concept_result
    # Niveau 1 skip car nlu.intent est None
    mock_ivr_exact.assert_not_called()
    mock_ivr_concept.assert_called_once()


@pytest.mark.asyncio
async def test_cascade_parametres_transmis_correctement():
    """Verifie que les parametres (city, weather, audio, user_id) sont relayes intacts."""
    nlu = _make_nlu(intent="CONSEIL_PRODUCTION", concepts={"CULTURE_RIZ": True})
    handler = DioulaHandler()
    weather = {"city": "Korhogo", "temperature": 32}

    with patch(
        "app.services.chat.ivr_searcher.try_ivr_exact",
        new=AsyncMock(return_value=None),
    ) as mock_ivr_exact, patch(
        "app.services.chat.ivr_searcher.try_ivr_concept",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.services.chat.deepseek_router.try_deepseek_dioula",
        new=AsyncMock(return_value=_make_chat_result("deepseek_open")),
    ) as mock_ds:
        await handler.process(
            nlu=nlu,
            weather_data=weather,
            city="Korhogo",
            include_audio=True,
            language=Language.DIOULA,
            user_id="user-42",
        )

    # Verifier que try_ivr_exact a recu les bons parametres
    ivr_kwargs = mock_ivr_exact.call_args.kwargs
    assert ivr_kwargs["city"] == "Korhogo"
    assert ivr_kwargs["weather_data"] == weather
    assert ivr_kwargs["include_audio"] is True

    # Verifier que try_deepseek_dioula a recu user_id
    ds_kwargs = mock_ds.call_args.kwargs
    assert ds_kwargs["user_id"] == "user-42"
    assert ds_kwargs["weather_data"] == weather


# ─────────────────────────────────────────────
# Backwards compatibility
# ─────────────────────────────────────────────


def test_back_compat_chat_service_methods_exist():
    """Les wrappers _try_ivr_* / _try_deepseek_dioula doivent toujours exister."""
    from app.services.chat_service import ChatService

    assert hasattr(ChatService, "_try_ivr_exact")
    assert hasattr(ChatService, "_try_ivr_concept")
    assert hasattr(ChatService, "_try_deepseek_dioula")
