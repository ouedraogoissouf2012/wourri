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
# Niveau 2.5 — routage météo pur (issue #355 T4)
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_meteo_pure_route_vers_reponse_construite_pas_deepseek():
    """intent météo pur + IVR None → build_meteo_response répond, DeepSeek jamais appelé."""
    nlu = _make_nlu(
        intent="QUESTION_METEO_AGRICOLE",
        concepts={"TEMPS_SAISON_PLUIE": True, "TEMPS_DEMAIN": True},
    )
    handler = DioulaHandler()
    meteo_result = _make_chat_result("meteo_prevision", "Demain — pluie")

    with patch(
        "app.services.chat.ivr_searcher.try_ivr_exact",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.services.chat.ivr_searcher.try_ivr_concept",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.services.chat.meteo_responder.build_meteo_response",
        new=AsyncMock(return_value=meteo_result),
    ) as mock_meteo, patch(
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

    assert result is meteo_result
    assert result.meta["source"] == "meteo_prevision"
    mock_meteo.assert_called_once()
    mock_ds.assert_not_called()


@pytest.mark.asyncio
async def test_meteo_pure_none_ne_retombe_PLUS_sur_deepseek():
    """ADR-0039 — CHANGEMENT DE COMPORTEMENT ASSUMÉ.

    Avant : intent météo pur + `build_meteo_response` None (donnée indisponible)
    → repli silencieux sur DeepSeek, qui inventait une prévision (cause de
    l'hallucination constatée en démo le 2026-09-23).
    Après : la météo est une famille à réponse VÉRIFIABLE → le LLM est interdit,
    on renvoie un accusé explicite et on escalade.
    """
    nlu = _make_nlu(
        intent="QUESTION_METEO_AGRICOLE",
        concepts={"TEMPS_SAISON_PLUIE": True},
    )
    handler = DioulaHandler()
    esc_result = _make_chat_result("escalated_factual")

    with patch(
        "app.services.chat.ivr_searcher.try_ivr_exact",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.services.chat.ivr_searcher.try_ivr_concept",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.services.chat.meteo_responder.build_meteo_response",
        new=AsyncMock(return_value=None),
    ) as mock_meteo, patch(
        "app.services.chat.llm_guard.build_escalation_response",
        new=AsyncMock(return_value=esc_result),
    ) as mock_esc, patch(
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

    assert result is esc_result
    mock_meteo.assert_called_once()
    mock_esc.assert_called_once()
    mock_ds.assert_not_called()


@pytest.mark.asyncio
async def test_intent_non_meteo_ne_declenche_pas_le_niveau_meteo():
    """Un intent non météo ne doit JAMAIS appeler build_meteo_response."""
    nlu = _make_nlu(intent="CONSEIL_PRODUCTION", concepts={"CULTURE_RIZ": True})
    handler = DioulaHandler()

    with patch(
        "app.services.chat.ivr_searcher.try_ivr_exact",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.services.chat.ivr_searcher.try_ivr_concept",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.services.chat.meteo_responder.build_meteo_response",
        new=AsyncMock(),
    ) as mock_meteo, patch(
        "app.services.chat.deepseek_router.try_deepseek_dioula",
        new=AsyncMock(return_value=_make_chat_result("deepseek_open")),
    ):
        await handler.process(
            nlu=nlu,
            weather_data=None,
            city="Abidjan",
            include_audio=False,
            language=Language.DIOULA,
            user_id="u1",
        )

    mock_meteo.assert_not_called()


# ─────────────────────────────────────────────
# Niveau 2.7 — « quelle culture pour ma zone » (#543)
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_culture_zone_route_vers_reponse_en_mode_both():
    """intent DÉDIÉ QUESTION_CULTURE_ZONE + IVR None → build_culture_zone_response
    répond (mode both), DeepSeek jamais appelé. Corrige le refus HORS_SUJET (#543)."""
    nlu = _make_nlu(intent="QUESTION_CULTURE_ZONE", concepts={"DEMANDE_CULTURE_ZONE": True})
    handler = DioulaHandler()
    cz_result = _make_chat_result("culture_zone", "À Bouake, tu peux cultiver : ...")

    with patch(
        "app.services.chat.ivr_searcher.try_ivr_exact",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.services.chat.ivr_searcher.try_ivr_concept",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.services.chat.culture_zone_responder.build_culture_zone_response",
        new=AsyncMock(return_value=cz_result),
    ) as mock_cz, patch(
        "app.services.chat.deepseek_router.try_deepseek_dioula",
        new=AsyncMock(),
    ) as mock_ds:
        result = await handler.process(
            nlu=nlu,
            weather_data=None,
            city="Bouake",
            include_audio=False,
            language=Language.BOTH,
            user_id="u1",
        )

    assert result is cz_result
    assert result.meta["source"] == "culture_zone"
    mock_cz.assert_called_once()
    mock_ds.assert_not_called()


@pytest.mark.asyncio
async def test_question_generale_ne_declenche_pas_culture_zone_en_dioula():
    """Garde de périmètre (#543) : QUESTION_GENERALE ne déclenche PAS culture_zone
    dans la DioulaHandler — seul l'intent DÉDIÉ le fait. Le comportement dioula
    existant de QUESTION_GENERALE (→ DeepSeek) est préservé."""
    nlu = _make_nlu(intent="QUESTION_GENERALE", concepts={"CULTURE_RIZ": True})
    handler = DioulaHandler()

    with patch(
        "app.services.chat.ivr_searcher.try_ivr_exact",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.services.chat.ivr_searcher.try_ivr_concept",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.services.chat.culture_zone_responder.build_culture_zone_response",
        new=AsyncMock(),
    ) as mock_cz, patch(
        "app.services.chat.deepseek_router.try_deepseek_dioula",
        new=AsyncMock(return_value=_make_chat_result("deepseek_open")),
    ) as mock_ds:
        result = await handler.process(
            nlu=nlu,
            weather_data=None,
            city="Abidjan",
            include_audio=False,
            language=Language.BOTH,
            user_id="u1",
        )

    mock_cz.assert_not_called()
    assert result.meta["source"] == "deepseek_open"
    mock_ds.assert_called_once()


# ─────────────────────────────────────────────
# Niveau 2.9 — garde LLM (ADR-0039, #550)
# ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_garde_bloque_le_llm_sur_un_fait_verifiable():
    """Question météo dont le répondeur déterministe n'a rien produit (donnée
    indisponible) → accusé + escalade, et le LLM n'est JAMAIS appelé. C'est le
    défaut de la démo du 23/09 : la cascade retombait sur le LLM, qui inventait."""
    nlu = _make_nlu(intent="QUESTION_METEO_AGRICOLE", concepts={"TEMPS_SAISON_PLUIE": True})
    handler = DioulaHandler()
    esc = _make_chat_result("escalated_factual", "je la transmets à un expert")

    with patch(
        "app.services.chat.ivr_searcher.try_ivr_exact", new=AsyncMock(return_value=None)
    ), patch(
        "app.services.chat.ivr_searcher.try_ivr_concept", new=AsyncMock(return_value=None)
    ), patch(
        "app.services.chat.meteo_responder.build_meteo_response", new=AsyncMock(return_value=None)
    ), patch(
        "app.services.chat.llm_guard.build_escalation_response",
        new=AsyncMock(return_value=esc),
    ) as mock_esc, patch(
        "app.services.chat.deepseek_router.try_deepseek_dioula", new=AsyncMock()
    ) as mock_ds:
        result = await handler.process(
            nlu=nlu, weather_data=None, city="Bouake",
            include_audio=False, language=Language.BOTH, user_id="u1",
        )

    assert result is esc
    mock_esc.assert_called_once()
    mock_ds.assert_not_called()  # LE point de l'ADR-0039


@pytest.mark.asyncio
async def test_conseil_general_passe_au_llm_mais_est_escalade():
    """Hors famille factuelle : le LLM répond encore (sinon ~40 % des questions
    resteraient sans réponse), mais la question est escaladée en préventif."""
    nlu = _make_nlu(intent="CONSEIL_PRODUCTION", concepts={"CULTURE_RIZ": True})
    handler = DioulaHandler()

    with patch(
        "app.services.chat.ivr_searcher.try_ivr_exact", new=AsyncMock(return_value=None)
    ), patch(
        "app.services.chat.ivr_searcher.try_ivr_concept", new=AsyncMock(return_value=None)
    ), patch(
        "app.services.chat.llm_guard.escalate"
    ) as mock_esc, patch(
        "app.services.chat.deepseek_router.try_deepseek_dioula",
        new=AsyncMock(return_value=_make_chat_result("deepseek_open")),
    ) as mock_ds:
        result = await handler.process(
            nlu=nlu, weather_data=None, city="Bouake",
            include_audio=False, language=Language.BOTH, user_id="u1",
        )

    assert result.meta["source"] == "deepseek_open"
    mock_ds.assert_called_once()
    mock_esc.assert_called_once()  # remontée PRÉVENTIVE (plus seulement sur 👎)


@pytest.mark.asyncio
async def test_garde_desactive_restaure_le_comportement_anterieur():
    """Rollback par configuration, sans redéploiement."""
    nlu = _make_nlu(intent="QUESTION_METEO_AGRICOLE", concepts={})
    handler = DioulaHandler()

    with patch(
        "app.services.chat.ivr_searcher.try_ivr_exact", new=AsyncMock(return_value=None)
    ), patch(
        "app.services.chat.ivr_searcher.try_ivr_concept", new=AsyncMock(return_value=None)
    ), patch(
        "app.services.chat.meteo_responder.build_meteo_response", new=AsyncMock(return_value=None)
    ), patch(
        "app.services.chat.llm_guard.guard_enabled", return_value=False
    ), patch(
        "app.services.chat.llm_guard.build_escalation_response", new=AsyncMock()
    ) as mock_esc, patch(
        "app.services.chat.deepseek_router.try_deepseek_dioula",
        new=AsyncMock(return_value=_make_chat_result("deepseek_open")),
    ) as mock_ds:
        result = await handler.process(
            nlu=nlu, weather_data=None, city="Bouake",
            include_audio=False, language=Language.BOTH, user_id="u1",
        )

    assert result.meta["source"] == "deepseek_open"
    mock_esc.assert_not_called()
    mock_ds.assert_called_once()
