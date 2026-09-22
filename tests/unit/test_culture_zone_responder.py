"""Tests — réponse déterministe « quelle culture pour ma zone » (#509 C2)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.models.schemas import Language
from app.services.chat.culture_zone_responder import (
    _liste_dyu,
    _ordonner,
    build_culture_zone_response,
    is_culture_zone_intent,
)
from app.services.chat.nlu_preprocessor import NLUResult


def _nlu(intent="QUESTION_GENERALE") -> NLUResult:
    return NLUResult(message_for_deepseek="quoi cultiver", intent=intent, concepts={})


def test_is_culture_zone_intent():
    assert is_culture_zone_intent(_nlu("QUESTION_CULTURE_ZONE")) is True  # intent dédié #543
    assert is_culture_zone_intent(_nlu("QUESTION_GENERALE")) is True       # fallback FR #511
    assert is_culture_zone_intent(_nlu("QUESTION_METEO_AGRICOLE")) is False
    assert is_culture_zone_intent(_nlu(None)) is False


@pytest.mark.asyncio
async def test_culture_zone_fr_liste_les_cultures():
    with patch("app.data.zones_agricoles.get_cultures_zone",
               return_value=["CULTURE_COTON", "CULTURE_MAIS", "CULTURE_MIL"]), \
         patch("app.data.zones_agricoles.get_zone_for_city", return_value="ZONE_NORD_SAVANE"), \
         patch("app.data.calendrier_agricole.get_cultures_du_mois", return_value=[]), \
         patch("app.services.tts_french.synthesize_french", new=AsyncMock(return_value=None)):
        r = await build_culture_zone_response(
            _nlu(), "Korhogo", include_audio=False, language=Language.FRENCH,
        )
    assert r is not None
    assert r.meta["source"] == "culture_zone"
    assert "coton" in r.response and "maïs" in r.response and "mil" in r.response
    assert "Korhogo" in r.response
    assert r.language == "french"


@pytest.mark.asyncio
async def test_culture_zone_priorise_la_saison():
    with patch("app.data.zones_agricoles.get_cultures_zone", return_value=["CULTURE_MAIS"]), \
         patch("app.data.zones_agricoles.get_zone_for_city", return_value="ZONE_CENTRE"), \
         patch("app.data.calendrier_agricole.get_cultures_du_mois",
               return_value=[{"fr": "maïs", "phase": "plantation"}]), \
         patch("app.services.tts_french.synthesize_french", new=AsyncMock(return_value=None)):
        r = await build_culture_zone_response(
            _nlu(), "Bouake", include_audio=False, language=Language.FRENCH,
        )
    assert "bonne période" in r.response  # phrase de saison ajoutée


@pytest.mark.asyncio
async def test_culture_zone_both_renvoie_reponse_fr():
    """#543 : en both/dioula, la réponse est désormais RENDUE EN FRANÇAIS (comme
    date_responder) au lieu de None — c'est ce qui corrige le refus HORS_SUJET du
    mode both (démo SODEXAM). La formulation dioula reste une dette (ADR-0014)."""
    with patch("app.data.zones_agricoles.get_cultures_zone",
               return_value=["CULTURE_COTON", "CULTURE_MAIS"]), \
         patch("app.data.zones_agricoles.get_zone_for_city", return_value="ZONE_NORD_SAVANE"), \
         patch("app.data.calendrier_agricole.get_cultures_du_mois", return_value=[]), \
         patch("app.services.tts_french.synthesize_french", new=AsyncMock(return_value=None)):
        r = await build_culture_zone_response(
            _nlu("QUESTION_CULTURE_ZONE"), "Korhogo", include_audio=False, language=Language.BOTH,
        )
    assert r is not None
    assert r.meta["source"] == "culture_zone"
    assert "coton" in r.response and "maïs" in r.response
    assert r.language == Language.BOTH.value
    # #545 : le texte dioula validé est renseigné (sert l'audio MMS-dyu ; ordre canonique).
    assert r.response_dioula == "Korhogo la, aw ye kaba ni kɔrɔni sɛnɛ."


@pytest.mark.asyncio
async def test_culture_zone_sans_cultures_renvoie_none():
    with patch("app.data.zones_agricoles.get_cultures_zone", return_value=[]):
        r = await build_culture_zone_response(
            _nlu(), "VilleInconnue", include_audio=False, language=Language.FRENCH,
        )
    assert r is None


@pytest.mark.asyncio
async def test_culture_zone_nord_inclut_anacarde_donnees_reelles():
    """Données réelles enrichies (#509) : le Nord (Korhogo) inclut l'anacarde."""
    r = await build_culture_zone_response(
        _nlu(), "Korhogo", include_audio=False, language=Language.FRENCH,
    )
    assert r is not None
    low = r.response.lower()
    assert "anacarde" in low and "coton" in low


# ─────────────────────────────────────────────
# Vocal dioula (#545) — gabarit natif-validé + audio MMS-dyu
# ─────────────────────────────────────────────


def test_liste_dyu_connecteur_et_repli():
    assert _liste_dyu(["CULTURE_RIZ"]) == "malo"
    assert _liste_dyu(["CULTURE_RIZ", "CULTURE_MAIS", "CULTURE_ANACARDE"]) == "malo, kaba ni sɔmɔ"
    # Culture sans dioula validé → None (→ repli audio FR, règle §14)
    assert _liste_dyu(["CULTURE_TOMATE"]) is None


def test_ordonner_ordre_canonique():
    """Vivriers d'abord, cultures de rente ensuite (#545) — reproduit l'ordre validé."""
    brut = ["CULTURE_ANACARDE", "CULTURE_IGNAME", "CULTURE_MAIS", "CULTURE_RIZ",
            "CULTURE_ARACHIDE", "CULTURE_MANIOC", "CULTURE_COTON"]
    assert _ordonner(brut) == [
        "CULTURE_RIZ", "CULTURE_MAIS", "CULTURE_ARACHIDE", "CULTURE_MANIOC",
        "CULTURE_IGNAME", "CULTURE_COTON", "CULTURE_ANACARDE",
    ]


@pytest.mark.asyncio
async def test_culture_zone_dioula_phrase_validee_bouake():
    """Golden test (#545) : la phrase dioula de Bouaké est EXACTEMENT celle validée
    nativement le 2026-09-22 (données réelles zone Centre)."""
    r = await build_culture_zone_response(
        _nlu("QUESTION_CULTURE_ZONE"), "Bouake", include_audio=False, language=Language.BOTH,
    )
    assert r.response_dioula is not None
    assert r.response_dioula.startswith(
        "Bouake la, aw ye malo, kaba, tiga, bananku, ku, kɔrɔni ni sɔmɔ sɛnɛ."
    )


@pytest.mark.asyncio
async def test_culture_zone_audio_dioula_en_both():
    """En both, l'audio est en DIOULA (MMS-dyu) sur la phrase validée, pas Piper FR."""
    with patch("app.data.zones_agricoles.get_cultures_zone",
               return_value=["CULTURE_MAIS", "CULTURE_RIZ"]), \
         patch("app.data.zones_agricoles.get_zone_for_city", return_value="ZONE_CENTRE"), \
         patch("app.data.calendrier_agricole.get_cultures_du_mois", return_value=[]), \
         patch("app.services.chat.culture_zone_responder._synthesize_dioula",
               new=AsyncMock(return_value="/static/audio/cz.ogg")) as mock_dyu, \
         patch("app.services.tts_french.synthesize_french",
               new=AsyncMock(return_value=None)) as mock_fr:
        r = await build_culture_zone_response(
            _nlu("QUESTION_CULTURE_ZONE"), "Bouake", include_audio=True, language=Language.BOTH,
        )
    assert r.audio_language == "Dioula"
    assert r.audio_url == "/static/audio/cz.ogg"
    mock_dyu.assert_called_once()
    mock_fr.assert_not_called()
    # Audio synthétisé sur la phrase validée (ordre canonique : malo avant kaba).
    assert mock_dyu.call_args.args[0] == "Bouake la, aw ye malo ni kaba sɛnɛ."


@pytest.mark.asyncio
async def test_culture_zone_audio_francais_en_mode_fr():
    """En FRANÇAIS pur, l'audio reste Piper FR (inchangé) — pas d'audio dioula."""
    with patch("app.data.zones_agricoles.get_cultures_zone", return_value=["CULTURE_RIZ"]), \
         patch("app.data.zones_agricoles.get_zone_for_city", return_value="ZONE_CENTRE"), \
         patch("app.data.calendrier_agricole.get_cultures_du_mois", return_value=[]), \
         patch("app.services.chat.culture_zone_responder._synthesize_dioula",
               new=AsyncMock()) as mock_dyu, \
         patch("app.services.tts_french.synthesize_french",
               new=AsyncMock(return_value="/static/audio/fr.ogg")):
        r = await build_culture_zone_response(
            _nlu("QUESTION_CULTURE_ZONE"), "Bouake", include_audio=True, language=Language.FRENCH,
        )
    assert r.audio_language == "Français"
    mock_dyu.assert_not_called()


@pytest.mark.asyncio
async def test_culture_zone_repli_audio_fr_si_culture_sans_dioula():
    """Règle §14 : si une culture de zone n'a pas de dioula validé, le texte dioula
    est None et l'audio retombe en FR (jamais de perte d'info)."""
    with patch("app.data.zones_agricoles.get_cultures_zone",
               return_value=["CULTURE_TOMATE"]), \
         patch("app.data.zones_agricoles.get_zone_for_city", return_value="ZONE_CENTRE"), \
         patch("app.data.calendrier_agricole.get_cultures_du_mois", return_value=[]), \
         patch("app.services.chat.culture_zone_responder._synthesize_dioula",
               new=AsyncMock()) as mock_dyu, \
         patch("app.services.tts_french.synthesize_french",
               new=AsyncMock(return_value="/static/audio/fr.ogg")):
        r = await build_culture_zone_response(
            _nlu("QUESTION_CULTURE_ZONE"), "Bouake", include_audio=True, language=Language.BOTH,
        )
    assert r.response_dioula is None
    assert r.audio_language == "Français"
    mock_dyu.assert_not_called()
