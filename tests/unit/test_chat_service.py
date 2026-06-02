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
)
# Refactor P2-09 PR 1 (Sprint L) : _build_meteo_bambara migre vers
# app/services/chat/meteo_injector.py. Tests existants continuent de
# l'importer depuis ce module externe pour preserver leur logique.
from app.services.chat.meteo_injector import build_meteo_bambara as _build_meteo_bambara
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

    # ──────────────────────────────────────────────────────────────────
    # Sprint G.1 (issue #171, #191) : fallback FR pour language=BOTH
    # ──────────────────────────────────────────────────────────────────

    @patch("app.services.nlu.get_nlu_service")
    def test_fr_message_both_falls_back_to_nlu(self, mock_nlu_fn):
        """Phrase FR pure en mode BOTH : doit déclencher le NLU sur le message FR
        (le ConceptExtractor a aussi les keywords FR riz/planter/...).

        Sans ce fallback, la cascade tombait sur DeepSeek+NLLB qui inventait
        `rɛzɛnmɔw` au lieu de `malo` (issue #171).
        """
        mock_nlu = MagicMock()
        mock_result = MagicMock()
        mock_result.is_out_of_scope = False
        mock_result.concepts = {"CULTURE_RIZ": 1.0, "ACTION_PLANTER": 1.0}
        mock_result.intent = "QUESTION_SAISON_PLANTATION"
        mock_result.french_sentence = "Quelle est la meilleure saison pour planter du riz ?"
        mock_nlu.process.return_value = mock_result
        mock_nlu_fn.return_value = mock_nlu

        result = self.service._preprocess_nlu(
            "Bonjour je veux planter du riz", None, Language.BOTH
        )

        # Le NLU a bien été appelé sur la phrase FR (pas court-circuité)
        mock_nlu.process.assert_called_once_with("Bonjour je veux planter du riz")
        assert result.intent == "QUESTION_SAISON_PLANTATION"
        assert "CULTURE_RIZ" in result.concepts

    def test_fr_message_french_only_no_nlu(self):
        """Mode FRENCH pure : le NLU ne doit PAS être appelé (régression check)."""
        result = self.service._preprocess_nlu(
            "Bonjour je veux planter du riz", None, Language.FRENCH
        )
        # Pas de NLU en mode FRENCH (court-circuit ligne 172)
        assert result.intent is None
        assert result.concepts == {}
        assert result.message_for_deepseek == "Bonjour je veux planter du riz"

    def test_dioula_priority_over_fr_fallback(self):
        """Si bambara_text est fourni, il a priorité sur le fallback FR."""
        with patch("app.services.nlu.get_nlu_service") as mock_nlu_fn:
            mock_nlu = MagicMock()
            mock_result = MagicMock()
            mock_result.is_out_of_scope = False
            mock_result.concepts = {"CULTURE_RIZ": 1.0}
            mock_result.intent = "CONSEIL_PRODUCTION"
            mock_result.french_sentence = "Je cherche des conseils pour le riz"
            mock_nlu.process.return_value = mock_result
            mock_nlu_fn.return_value = mock_nlu

            result = self.service._preprocess_nlu(
                "Je veux planter du riz", "malo bɛ sɛnɛ", Language.BOTH
            )

            # Le NLU doit recevoir bambara_text, PAS le message FR
            mock_nlu.process.assert_called_once_with("malo bɛ sɛnɛ")
            assert result.intent == "CONSEIL_PRODUCTION"

    def test_fr_message_dioula_only_no_fallback(self):
        """Mode DIOULA pure + message FR sans chars bambara : pas de fallback FR
        (uniquement BOTH déclenche le fallback)."""
        result = self.service._preprocess_nlu(
            "Bonjour je veux planter du riz", None, Language.DIOULA
        )
        # Pas de fallback en mode DIOULA strict
        assert result.intent is None
        assert result.concepts == {}


class TestPreprocessNluFrIntegration:
    """Tests d'intégration : le NLU réel doit retourner les bons concepts
    pour des phrases FR variées (validation empirique du fix Sprint G.1)."""

    def setup_method(self):
        self.service = ChatService()

    # NB sorgho → CULTURE_MIL : choix INTENTIONNEL du projet. Le concept
    # CULTURE_MIL groupe mil + sorgho (keywords "keninge", "keninge foro",
    # "sorgho" dans dictionnaires/nlu_concepts.json) — pattern commun en
    # Afrique de l'Ouest où ces deux céréales sont traitées ensemble.
    # Pas de CULTURE_SORGHO distinct. Si un futur ADR sépare les deux,
    # mettre à jour ce paramètre.
    @pytest.mark.parametrize("phrase,expected_intent,expected_culture", [
        ("Bonjour je veux planter du riz",
         "QUESTION_SAISON_PLANTATION", "CULTURE_RIZ"),
        ("Je voudrais planter du mais cette saison",
         "QUESTION_SAISON_PLANTATION", "CULTURE_MAIS"),
        ("Comment cultiver de l arachide ?",
         "QUESTION_SAISON_PLANTATION", "CULTURE_ARACHIDE"),
        ("Mon manioc est malade que faire ?",
         "DIAGNOSTIC_PROBLEME", "CULTURE_MANIOC"),
        ("Quand recolter le sorgho ?",
         "QUESTION_RECOLTE", "CULTURE_MIL"),  # sorgho → CULTURE_MIL (cf. commentaire ci-dessus)
        ("Je cherche des conseils pour le cacao",
         "CONSEIL_PRODUCTION", "CULTURE_CACAO"),
    ])
    def test_nlu_extracts_culture_and_intent_from_fr(
        self, phrase, expected_intent, expected_culture
    ):
        """Le NLU réel détecte intent + culture sur phrases FR (cible Sprint G.1)."""
        result = self.service._preprocess_nlu(phrase, None, Language.BOTH)
        assert result.intent == expected_intent, (
            f"Intent attendu '{expected_intent}', obtenu '{result.intent}' pour {phrase!r}"
        )
        assert expected_culture in result.concepts, (
            f"Culture '{expected_culture}' absente des concepts {dict(result.concepts)} "
            f"pour {phrase!r}"
        )


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

    async def test_no_concepts_returns_none(self):
        """Sprint G.2 : `_search_ivr_by_concept` est désormais async."""
        assert await self.service._search_ivr_by_concept({}) is None

    async def test_action_planter_without_culture_returns_none(self):
        """ACTION_PLANTER sans culture → None (déclenche clarification en amont, Fix #94).

        Fix #94 a supprimé le fallback silencieux ACTION_PLANTER → CULTURE_MAIS.
        Désormais `_search_ivr_by_concept` retourne directement None quand aucune
        culture n'est détectée, ce qui déclenche `_clarify_missing_culture` dans
        le chemin appelant `_try_ivr_concept`.

        Invariant verrouillé : `chercher_reponse_ivr` ne doit PAS être appelé
        dans ce cas (sinon réintroduction silencieuse d'un fallback).
        """
        with patch("app.services.corpus_facade.chercher_reponse_ivr") as mock_vdb:
            result = await self.service._search_ivr_by_concept({"ACTION_PLANTER": True})
            assert result is None
            mock_vdb.assert_not_called()

    async def test_culture_without_action_uses_conseil_production(self):
        """Culture sans action → CONSEIL_PRODUCTION par défaut."""
        with patch("app.services.corpus_facade.chercher_reponse_ivr") as mock_vdb:
            mock_vdb.return_value = {
                "id": "riz_conseil_001",
                "reponse_bambara": "Malo sɛnɛ..."
            }
            result = await self.service._search_ivr_by_concept({"CULTURE_RIZ": True})
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

    async def test_search_ivr_by_concept_returns_dict_with_both_languages(self):
        """`_search_ivr_by_concept` retourne un dict avec reponse_bambara + reponse_fr.

        Sprint G.2 : méthode async (to_thread sur chercher_reponse_ivr).
        """
        with patch("app.services.corpus_facade.chercher_reponse_ivr") as mock_vdb:
            mock_vdb.return_value = {
                "id": "riz_conseil_001",
                "reponse_bambara": "Malo sɛnɛ kalo la sanji tuma na.",
                "reponse_fr": "Plante ton riz en mai pendant la saison des pluies.",
            }
            result = await self.service._search_ivr_by_concept({"CULTURE_RIZ": True})
            assert isinstance(result, dict), "doit retourner un dict (#166), pas une str"
            assert "reponse_bambara" in result
            assert "reponse_fr" in result
            assert result["reponse_fr"] == "Plante ton riz en mai pendant la saison des pluies."
            assert "Malo" in result["reponse_bambara"]

    async def test_search_ivr_by_concept_fallback_fr_empty_when_missing(self):
        """Si `reponse_fr` manque dans l'entrée corpus, retour dict avec reponse_fr=''."""
        with patch("app.services.corpus_facade.chercher_reponse_ivr") as mock_vdb:
            mock_vdb.return_value = {
                "id": "test",
                "reponse_bambara": "Malo sɛnɛ.",
                # reponse_fr volontairement absent
            }
            result = await self.service._search_ivr_by_concept({"CULTURE_RIZ": True})
            assert result is not None
            assert result["reponse_fr"] == ""
            assert result["reponse_bambara"] == "Malo sɛnɛ."

    def test_inject_meteo_replaces_both_tags(self):
        """`inject_meteo` doit remplacer {{METEO_CONTEXTUEL}} dans bam ET {{METEO_FR}} dans fr.

        Refactor P2-09 PR 1 : `_inject_meteo` n'est plus une methode de
        ChatService — appel direct a `inject_meteo` du module extrait.
        """
        from app.services.chat.meteo_injector import inject_meteo

        bam_in = "Aw ni sɔgɔma. {{METEO_CONTEXTUEL}} I bɛ koo?"
        fr_in = "Bonjour. {{METEO_FR}} Comment tu vas ?"
        weather = {"weather_code": 0, "temperature": 30, "precipitation": 0, "city": "Bouake"}

        bam_out, fr_out = inject_meteo(bam_in, fr_in, weather, "Bouake")

        assert "{{METEO_CONTEXTUEL}}" not in bam_out, "tag bambara doit être remplacé"
        assert "{{METEO_FR}}" not in fr_out, "tag français doit être remplacé"
        # Le bambara contient le mot 'tile' (soleil) pour ciel dégagé
        assert "tile" in bam_out or "Bouake" in bam_out
        # Le français contient une phrase météo (clair ou irrigation selon temp)
        assert any(kw in fr_out.lower() for kw in ("bouake", "ciel", "soleil", "chaleur", "arros", "irrig"))

    def test_inject_meteo_no_tags_returns_unchanged(self):
        """Si aucun tag, retourne les chaînes inchangées (court-circuit)."""
        from app.services.chat.meteo_injector import inject_meteo

        bam_in = "Pas de tag ici."
        fr_in = "No tag here."
        bam_out, fr_out = inject_meteo(bam_in, fr_in, None, "Abidjan")
        assert bam_out == bam_in
        assert fr_out == fr_in


# ─────────────────────────────────────────────────────────────────────────
# Process dispatcher (ADR-0015 PR 3/4)
#
# Verifie que `ChatService.process()` est devenu un thin dispatcher pur qui
# delegue a `HANDLERS[language]`. Plus de cascade if/elif legacy.
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestProcessDispatcher:
    """ADR-0015 PR 3/4 : process() est un dispatcher pur sur HANDLERS."""

    async def _run(self, language: Language, message: str = "test"):
        """Helper : appelle process() avec tous les externes mockes."""
        service = ChatService()
        fake_result = ChatResult(
            response=f"response {language.value}",
            city="Abidjan",
            language=language.value,
        )
        with patch(
            "app.services.chat_service.ChatService._detect_city",
            return_value=None,
        ), patch(
            "app.services.chat_service.ChatService._preprocess_nlu",
            return_value=NLUResult(message_for_deepseek=message),
        ), patch(
            "app.services.weather.get_weather",
            new=AsyncMock(return_value={"city": "Abidjan", "temperature": 28}),
        ), patch.dict(
            "app.services.chat.handlers.HANDLERS",
            clear=False,
        ) as _:
            from app.services.chat.handlers import HANDLERS

            mock_handler = MagicMock()
            mock_handler.process = AsyncMock(return_value=fake_result)
            original = HANDLERS[language]
            HANDLERS[language] = mock_handler
            try:
                result = await service.process(message=message, language=language)
            finally:
                HANDLERS[language] = original

        return result, mock_handler, fake_result

    async def test_dispatches_to_french_handler(self):
        result, handler, expected = await self._run(Language.FRENCH)
        assert result is expected
        handler.process.assert_called_once()

    async def test_dispatches_to_dioula_handler(self):
        result, handler, expected = await self._run(Language.DIOULA)
        assert result is expected
        handler.process.assert_called_once()

    async def test_dispatches_to_both_handler(self):
        result, handler, expected = await self._run(Language.BOTH)
        assert result is expected
        handler.process.assert_called_once()

    async def test_passes_required_kwargs_to_handler(self):
        """Verifie que les bons parametres sont relayes au handler."""
        result, handler, _ = await self._run(Language.FRENCH, message="ma question")
        kwargs = handler.process.call_args.kwargs
        assert "nlu" in kwargs
        assert "weather_data" in kwargs
        assert "city" in kwargs
        assert "include_audio" in kwargs
        assert "language" in kwargs
        assert "user_id" in kwargs
        assert kwargs["language"] == Language.FRENCH

    async def test_returns_error_chat_result_on_exception(self):
        """Si le pipeline leve, retour ChatResult d'erreur graceful (pas de crash)."""
        service = ChatService()
        with patch(
            "app.services.chat_service.ChatService._detect_city",
            side_effect=RuntimeError("boom"),
        ):
            result = await service.process(message="test", language=Language.FRENCH)
        assert isinstance(result, ChatResult)
        assert "problèmes de connexion" in result.response.lower() or \
               "désolé" in result.response.lower()
        assert result.language == "french"
