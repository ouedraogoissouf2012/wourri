"""
Tests unitaires pour ChatService (issue #43).

Valide :
- Détection de ville dans le message
- NLU preprocessing (bambara → intent + concepts)
- Enrichissement DeepSeek avec contexte culture
- Recherche IVR par concept (ACTION_PLANTER → CULTURE_MAIS défaut)
- Construction météo bambara
- Pipeline process() avec mocks
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from typing import Optional

from app.services.chat_service import (
    ChatService,
    NLUResult,
    ChatResult,
    _build_meteo_bambara,
)
from app.models.schemas import Language


class TestDetectCity:
    """Test de la détection de ville dans le message."""

    def setup_method(self):
        self.service = ChatService()

    def test_detect_abidjan(self):
        assert self.service._detect_city("Je suis à Abidjan") == "Abidjan"

    def test_detect_korhogo(self):
        assert self.service._detect_city("La météo à Korhogo ?") == "Korhogo"

    def test_no_city(self):
        assert self.service._detect_city("Bonjour, comment planter du riz ?") is None

    def test_word_boundary(self):
        """'Man' ne doit pas matcher dans 'manioc'."""
        result = self.service._detect_city("Je veux planter du manioc")
        assert result != "Man"

    def test_case_insensitive(self):
        assert self.service._detect_city("je suis à bouake") == "Bouake"


class TestNLUPreprocessing:
    """Test du preprocessing NLU."""

    def setup_method(self):
        self.service = ChatService()

    def test_french_message_no_nlu(self):
        """Un message français ne passe pas par le NLU."""
        result = self.service._preprocess_nlu("Bonjour", None, Language.FRENCH)
        assert result.message_for_deepseek == "Bonjour"
        assert result.intent is None
        assert result.concepts == {}

    def test_no_bambara_text_no_chars(self):
        """Sans texte bambara ni caractères spéciaux, pas de NLU."""
        result = self.service._preprocess_nlu("hello world", None, Language.DIOULA)
        assert result.message_for_deepseek == "hello world"
        assert result.intent is None

    @patch("app.services.nlu.get_nlu_service")
    def test_bambara_text_triggers_nlu(self, mock_nlu_fn):
        """Un texte bambara fourni déclenche le NLU."""
        mock_nlu = MagicMock()
        mock_result = MagicMock()
        mock_result.is_out_of_scope = False
        mock_result.concepts = {"CULTURE_RIZ": True}
        mock_result.intent = "CONSEIL_PRODUCTION"
        mock_result.french_sentence = "Je cherche des conseils pour le riz"
        mock_nlu.process.return_value = mock_result
        mock_nlu_fn.return_value = mock_nlu

        result = self.service._preprocess_nlu(
            "question", "malo bɛ sɛnɛ", Language.DIOULA
        )

        assert result.intent == "CONSEIL_PRODUCTION"
        assert "CULTURE_RIZ" in result.concepts

    @patch("app.services.nlu.get_nlu_service")
    def test_out_of_scope(self, mock_nlu_fn):
        """Un message hors sujet est détecté."""
        mock_nlu = MagicMock()
        mock_result = MagicMock()
        mock_result.is_out_of_scope = True
        mock_result.out_of_scope_message_fr = "Hors sujet"
        mock_nlu.process.return_value = mock_result
        mock_nlu_fn.return_value = mock_nlu

        result = self.service._preprocess_nlu(
            "test", "blabla ɛɔ", Language.DIOULA
        )

        assert result.intent == "HORS_SUJET"
        assert result.is_out_of_scope


class TestEnrichForDeepseek:
    """Test de l'enrichissement contextuel."""

    def setup_method(self):
        self.service = ChatService()

    def test_adds_culture_context(self):
        result = self.service._enrich_for_deepseek(
            "Je cherche des conseils",
            {"CULTURE_RIZ": True}
        )
        assert "[Paysan cultive: riz]" in result

    def test_adds_animal_context(self):
        result = self.service._enrich_for_deepseek(
            "Question sur mes animaux",
            {"ANIMAL_POULET": True}
        )
        assert "[Paysan cultive: poulets]" in result

    def test_no_context_without_culture(self):
        result = self.service._enrich_for_deepseek(
            "Question générale",
            {"ACTION_PLANTER": True}
        )
        assert "[Paysan" not in result


class TestBuildMeteoBambara:
    """Test de la construction du message météo bambara."""

    def test_no_weather_data(self):
        bam, fr = _build_meteo_bambara(None, "Abidjan")
        assert "foro" in bam
        assert "champ" in fr

    def test_storm(self):
        weather = {"weather_code": 95, "temperature": 28, "precipitation": 20, "city": "Bouake"}
        bam, fr = _build_meteo_bambara(weather, "Bouake")
        assert "sanfɛla" in bam
        assert "orage" in fr

    def test_heavy_rain(self):
        weather = {"weather_code": 65, "temperature": 25, "precipitation": 10, "city": "Daloa"}
        bam, fr = _build_meteo_bambara(weather, "Daloa")
        assert "sanji" in bam
        assert "pluie" in fr.lower()

    def test_clear_sky_hot(self):
        weather = {"weather_code": 0, "temperature": 35, "precipitation": 0, "city": "Korhogo"}
        bam, fr = _build_meteo_bambara(weather, "Korhogo")
        assert "tile" in bam
        assert "chaleur" in fr.lower() or "irrig" in fr.lower()

    def test_cultures_appended(self):
        weather = {"weather_code": 0, "temperature": 28, "precipitation": 0, "city": "Man"}
        cultures = [{"bambara": "malo", "fr": "riz", "phase": "semis"}]
        bam, fr = _build_meteo_bambara(weather, "Man", cultures)
        assert "malo" in bam
        assert "riz" in fr


class TestSearchIVRByConcept:
    """Test de la recherche IVR par concept."""

    def setup_method(self):
        self.service = ChatService()

    def test_no_concepts_returns_none(self):
        assert self.service._search_ivr_by_concept({}) is None

    def test_action_planter_without_culture_returns_none(self):
        """ACTION_PLANTER sans culture → None (déclenche clarification en amont, Fix #94).

        Fix #94 a supprimé le fallback silencieux ACTION_PLANTER → CULTURE_MAIS.
        Désormais `_search_ivr_by_concept` retourne directement None quand aucune
        culture n'est détectée, ce qui déclenche `_clarify_missing_culture` dans
        le chemin appelant `_try_ivr_concept`.

        Invariant verrouillé : `chercher_reponse_ivr` ne doit PAS être appelé
        dans ce cas (sinon réintroduction silencieuse d'un fallback).
        """
        with patch("app.services.vdb_service.chercher_reponse_ivr") as mock_vdb:
            result = self.service._search_ivr_by_concept({"ACTION_PLANTER": True})
            assert result is None
            mock_vdb.assert_not_called()

    def test_culture_without_action_uses_conseil_production(self):
        """Culture sans action → CONSEIL_PRODUCTION par défaut."""
        with patch("app.services.vdb_service.chercher_reponse_ivr") as mock_vdb:
            mock_vdb.return_value = {
                "id": "riz_conseil_001",
                "reponse_bambara": "Malo sɛnɛ..."
            }
            result = self.service._search_ivr_by_concept({"CULTURE_RIZ": True})
            assert result is not None


class TestChatResult:
    """Test des data classes."""

    def test_chat_result_defaults(self):
        r = ChatResult(response="test")
        assert r.response == "test"
        assert r.response_dioula is None
        assert r.audio_url is None
        assert r.city == "Abidjan"

    def test_nlu_result_defaults(self):
        r = NLUResult(message_for_deepseek="test")
        assert r.intent is None
        assert r.concepts == {}
        assert not r.is_out_of_scope


class TestIVRResponseContract:
    """Test du contrat IVR (fix #166).

    Le contrat est : pour un match IVR exact ou par concept, `response` doit être
    en français (extrait de `reponse_fr` du corpus) et `response_dioula` doit
    contenir la version bambara (extrait de `reponse_bambara`).

    Régression précédente : le code mettait `reponse_bambara` dans les deux
    champs, ce qui faisait afficher du dioula avec un drapeau 🇫🇷 côté WhatsApp.
    """

    def setup_method(self):
        self.service = ChatService()

    def test_search_ivr_by_concept_returns_dict_with_both_languages(self):
        """`_search_ivr_by_concept` retourne un dict avec reponse_bambara + reponse_fr."""
        with patch("app.services.vdb_service.chercher_reponse_ivr") as mock_vdb:
            mock_vdb.return_value = {
                "id": "riz_conseil_001",
                "reponse_bambara": "Malo sɛnɛ kalo la sanji tuma na.",
                "reponse_fr": "Plante ton riz en mai pendant la saison des pluies.",
            }
            result = self.service._search_ivr_by_concept({"CULTURE_RIZ": True})
            assert isinstance(result, dict), "doit retourner un dict (#166), pas une str"
            assert "reponse_bambara" in result
            assert "reponse_fr" in result
            assert result["reponse_fr"] == "Plante ton riz en mai pendant la saison des pluies."
            assert "Malo" in result["reponse_bambara"]

    def test_search_ivr_by_concept_fallback_fr_empty_when_missing(self):
        """Si `reponse_fr` manque dans l'entrée corpus, retour dict avec reponse_fr=''."""
        with patch("app.services.vdb_service.chercher_reponse_ivr") as mock_vdb:
            mock_vdb.return_value = {
                "id": "test",
                "reponse_bambara": "Malo sɛnɛ.",
                # reponse_fr volontairement absent
            }
            result = self.service._search_ivr_by_concept({"CULTURE_RIZ": True})
            assert result is not None
            assert result["reponse_fr"] == ""
            assert result["reponse_bambara"] == "Malo sɛnɛ."

    def test_inject_meteo_replaces_both_tags(self):
        """`_inject_meteo` doit remplacer {{METEO_CONTEXTUEL}} dans bam ET {{METEO_FR}} dans fr."""
        bam_in = "Aw ni sɔgɔma. {{METEO_CONTEXTUEL}} I bɛ koo?"
        fr_in = "Bonjour. {{METEO_FR}} Comment tu vas ?"
        weather = {"weather_code": 0, "temperature": 30, "precipitation": 0, "city": "Bouake"}

        bam_out, fr_out = self.service._inject_meteo(bam_in, fr_in, weather, "Bouake")

        assert "{{METEO_CONTEXTUEL}}" not in bam_out, "tag bambara doit être remplacé"
        assert "{{METEO_FR}}" not in fr_out, "tag français doit être remplacé"
        # Le bambara contient le mot 'tile' (soleil) pour ciel dégagé
        assert "tile" in bam_out or "Bouake" in bam_out
        # Le français contient une phrase météo (clair ou irrigation selon temp)
        assert any(kw in fr_out.lower() for kw in ("bouake", "ciel", "soleil", "chaleur", "arros", "irrig"))

    def test_inject_meteo_no_tags_returns_unchanged(self):
        """Si aucun tag, retourne les chaînes inchangées (court-circuit)."""
        bam_in = "Pas de tag ici."
        fr_in = "No tag here."
        bam_out, fr_out = self.service._inject_meteo(bam_in, fr_in, None, "Abidjan")
        assert bam_out == bam_in
        assert fr_out == fr_in
