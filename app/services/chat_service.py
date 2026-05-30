"""
WOURI - ChatService : orchestrateur unique pour le pipeline de chat.

Responsabilité unique (SRP) : coordonne NLU → IVR → DeepSeek → TTS
pour produire une réponse complète à partir d'un message utilisateur.

Le routeur chat.py ne fait que valider l'input et retourner le résultat.
"""
import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from app.models.schemas import Language
from app.config import get_settings
from app.data.cities import IVORIAN_CITIES
from app.data.calendrier_agricole import get_conseil_saisonnier

logger = logging.getLogger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Data classes pour les résultats intermédiaires
# ---------------------------------------------------------------------------

@dataclass
class NLUResult:
    """Résultat du preprocessing NLU."""
    message_for_deepseek: str
    intent: Optional[str] = None
    concepts: dict = field(default_factory=dict)
    is_out_of_scope: bool = False


@dataclass
class ChatResult:
    """Résultat final du ChatService, prêt à être converti en ChatResponse."""
    response: str
    response_dioula: Optional[str] = None
    audio_url: Optional[str] = None
    city: str = "Abidjan"
    language: str = "both"
    audio_language: Optional[str] = None
    meta: Optional[dict] = None


# ---------------------------------------------------------------------------
# Labels pour enrichissement DeepSeek
# ---------------------------------------------------------------------------

_CULTURE_LABELS = {
    "CULTURE_RIZ": "riz", "CULTURE_MAIS": "maïs", "CULTURE_MIL": "mil",
    "CULTURE_ARACHIDE": "arachide", "CULTURE_IGNAME": "igname", "CULTURE_MANIOC": "manioc",
    "CULTURE_HARICOT": "haricot", "CULTURE_COTON": "coton", "CULTURE_SESAME": "sésame",
    "CULTURE_BANANE": "banane", "CULTURE_TOMATE": "tomate", "CULTURE_OIGNON": "oignon",
    "CULTURE_PATATE": "patate douce", "CULTURE_GOMBO": "gombo", "CULTURE_CACAO": "cacao",
    "CULTURE_CAFE": "café", "CULTURE_ANANAS": "ananas",
}
_ANIMAL_LABELS = {
    "ANIMAL_POULET": "poulets", "ANIMAL_BOVIN": "bovins", "ANIMAL_OVIN": "moutons",
    "ANIMAL_CAPRIN": "chèvres", "ANIMAL_PORC": "porcs", "ANIMAL_POISSON": "poissons",
}

_ACTION_TO_INTENT = {
    "ACTION_PLANTER": "QUESTION_SAISON_PLANTATION",
    "ACTION_RECOLTER": "QUESTION_RECOLTE",
    "ACTION_ARROSER": "QUESTION_IRRIGATION",
    "ACTION_TRAITER": "DIAGNOSTIC_PROBLEME",
    "ACTION_STOCKER": "QUESTION_STOCKAGE",
    "ACTION_VENDRE": "QUESTION_VENTE",
    "ACTION_CHERCHER_CONSEIL": "CONSEIL_PRODUCTION",
    "ACTION_LABOURER": "CONSEIL_PRODUCTION",
}


class ChatService:
    """Orchestrateur du pipeline de chat Wourri.

    Usage :
        service = ChatService()
        result = await service.process(message, city, language, bambara_text, include_audio)
    """

    # ------------------------------------------------------------------
    # Point d'entrée principal
    # ------------------------------------------------------------------

    async def process(
        self,
        message: str,
        city: str = "Abidjan",
        language: Language = Language.BOTH,
        bambara_text: Optional[str] = None,
        include_audio: bool = True,
        user_id: Optional[str] = None,
    ) -> ChatResult:
        """Pipeline complet : message → NLU → IVR/DeepSeek → TTS → résultat."""
        try:
            # 1. Détection de ville
            detected_city = self._detect_city(message)
            city = detected_city or city

            # 2. NLU preprocessing (si dioula)
            nlu = self._preprocess_nlu(message, bambara_text, language)

            # 3. Météo
            from app.services.weather import get_weather
            weather_data = await get_weather(city)

            # 4. Chercher réponse selon la langue
            if language in (Language.DIOULA, Language.BOTH) and nlu.intent:
                # Chemin IVR exact
                result = await self._try_ivr_exact(
                    nlu, city, weather_data, include_audio, language,
                )
                if result:
                    return result

            # 5. Fallback IVR par concept
            if language in (Language.DIOULA, Language.BOTH):
                result = await self._try_ivr_concept(
                    nlu, city, include_audio, language,
                )
                if result:
                    return result

                # 6. Fallback DeepSeek (dioula)
                return await self._try_deepseek_dioula(
                    nlu, weather_data, city, include_audio, language, user_id,
                )

            # 7. Chemin français uniquement
            return await self._try_deepseek_french(
                nlu, weather_data, city, include_audio, language, user_id,
            )

        except Exception as e:
            logger.error("Erreur ChatService: %s", e, exc_info=True)
            return ChatResult(
                response="Désolé, je rencontre des problèmes de connexion. "
                         "Vérifiez votre connexion internet et réessayez.",
                city=city,
                language=language.value,
            )

    # ------------------------------------------------------------------
    # Étape 1 : Détection de ville
    # ------------------------------------------------------------------

    def _detect_city(self, message: str) -> Optional[str]:
        """Détecte une ville ivoirienne dans le message."""
        msg_lower = message.lower()
        for city_name in sorted(IVORIAN_CITIES.keys(), key=len, reverse=True):
            pattern = r'\b' + re.escape(city_name.lower()) + r'\b'
            if re.search(pattern, msg_lower):
                return city_name
        return None

    # ------------------------------------------------------------------
    # Étape 2 : NLU preprocessing
    # ------------------------------------------------------------------

    def _preprocess_nlu(
        self,
        message: str,
        bambara_text: Optional[str],
        language: Language,
    ) -> NLUResult:
        """Applique le NLU si le message est en dioula/bambara.

        Sprint G.1 (issue #171, #191) : fallback FR pour `language=BOTH` quand
        aucun texte dioula n'est disponible. Le `ConceptExtractor` indexe déjà
        les mots-clés français (`riz`, `planter`, `maïs`, etc. dans
        `dictionnaires/nlu_concepts.json`) — vérifié empiriquement sur 6 phrases
        FR variées. Sans ce fallback, la cascade tombe sur DeepSeek+NLLB qui
        invente des termes hors-vocabulaire validé (ex: `rɛzɛnmɔw` au lieu
        de `malo` pour le riz).
        """
        if language not in (Language.DIOULA, Language.BOTH):
            return NLUResult(message_for_deepseek=message)

        text_to_analyze = bambara_text or ""
        bambara_chars = set("ɛɔŋɲɛ̀ɛ́ɔ̀ɔ́")
        if not text_to_analyze and any(c in message for c in bambara_chars):
            text_to_analyze = message

        # Fallback FR (Sprint G.1) : si mode BOTH et pas de texte dioula,
        # passer le message FR au NLU qui a aussi les keywords agricoles FR.
        if not text_to_analyze and language == Language.BOTH:
            text_to_analyze = message

        if not text_to_analyze:
            return NLUResult(message_for_deepseek=message)

        try:
            from app.services.nlu import get_nlu_service
            nlu = get_nlu_service()
            if nlu is None:
                return NLUResult(message_for_deepseek=message)

            result = nlu.process(text_to_analyze)

            if result.is_out_of_scope:
                logger.info("[ChatService] Hors sujet: '%s'", text_to_analyze[:50])
                return NLUResult(
                    message_for_deepseek=result.out_of_scope_message_fr or message,
                    intent="HORS_SUJET",
                    is_out_of_scope=True,
                )

            concepts = result.concepts or {}
            if result.french_sentence:
                enriched = self._enrich_for_deepseek(result.french_sentence, concepts)
                logger.info("[ChatService] NLU phrase: '%s'", result.french_sentence)
                return NLUResult(
                    message_for_deepseek=enriched,
                    intent=result.intent,
                    concepts=concepts,
                )

            return NLUResult(
                message_for_deepseek=message,
                intent=result.intent,
                concepts=concepts,
            )

        except Exception as e:
            logger.error("[ChatService] NLU erreur: %s", e)
            return NLUResult(message_for_deepseek=message)

    def _enrich_for_deepseek(self, french_sentence: str, concepts: dict) -> str:
        """Ajoute un contexte [Paysan cultive: X] pour guider DeepSeek."""
        culture = next((_CULTURE_LABELS[k] for k in concepts if k in _CULTURE_LABELS), None)
        animal = next((_ANIMAL_LABELS[k] for k in concepts if k in _ANIMAL_LABELS), None)
        sujet = culture or animal
        if sujet:
            prefix = f"[Paysan cultive: {sujet}] "
            logger.info("[ChatService] Contexte: %s", prefix.strip())
            return prefix + french_sentence
        return french_sentence

    # ------------------------------------------------------------------
    # Étape 3 : Chercher IVR exact
    # ------------------------------------------------------------------

    async def _try_ivr_exact(
        self,
        nlu: NLUResult,
        city: str,
        weather_data: dict | None,
        include_audio: bool,
        language: Language,
    ) -> Optional[ChatResult]:
        """Cherche une réponse IVR exacte par intent + culture."""
        # Façade ADR-0008 §Phase C : route vers Chroma (défaut) / dual / pgvector
        # via `corpus_storage_mode`. API identique à `vdb_service`.
        from app.services.corpus_facade import chercher_reponse_ivr, get_phrases_for_intent

        cultures = [k for k in nlu.concepts if k.startswith("CULTURE_") or k.startswith("ANIMAL_")]
        conditions = [k for k in nlu.concepts if k.startswith("PROBLEME_") or k.startswith("TEMPS_")]

        if not nlu.intent:
            return None

        try:
            # Sprint G.2 (issue #193) : `chercher_reponse_ivr` invoque
            # `corpus_service._embed_query()` (SentenceTransformer.encode
            # ~50-200ms) qui bloque le event loop FastAPI sans `to_thread`.
            # Wrapping ici couvre les 2 backends (Chroma + pgvector) via la façade.
            result = await asyncio.to_thread(
                chercher_reponse_ivr,
                nlu.intent,
                cultures if cultures else ["*"],
                conditions,
            )
        except Exception as e:
            logger.error("[ChatService] VDB erreur: %s", e)
            return None

        if not result:
            return None

        logger.info("[ChatService] IVR exact: %s (intent=%s)", result['id'], nlu.intent)
        ivr_bambara = result["reponse_bambara"]
        ivr_fr = result.get("reponse_fr", "")

        # Remplacer {{METEO_CONTEXTUEL}} (bam) et {{METEO_FR}} (fr)
        # Refactor P2-09 PR 1 (Sprint L) : delegue a app.services.chat.meteo_injector
        from app.services.chat.meteo_injector import inject_meteo
        ivr_bambara, ivr_fr = inject_meteo(ivr_bambara, ivr_fr, weather_data, city)

        # Sécurité : effacer tags résiduels dans les 2 langues
        ivr_bambara = re.sub(r'\{\{[^}]+\}\}', '', ivr_bambara).strip()
        ivr_fr = re.sub(r'\{\{[^}]+\}\}', '', ivr_fr).strip()

        # Conseil saisonnier (bilingue)
        conseil = get_conseil_saisonnier(cultures, intent=nlu.intent)
        if conseil:
            ivr_bambara = ivr_bambara + " " + conseil["bambara"]
            if ivr_fr:
                ivr_fr = ivr_fr + " " + conseil["fr"]

        # TTS basé sur le bambara (la version dioula reste autoritative pour l'audio)
        audio_url = None
        if include_audio:
            audio_url = await self._synthesize_dioula(ivr_bambara)

        # Phrases attestées (pour meta)
        try:
            phrases_att = get_phrases_for_intent(nlu.intent, cultures)
        except Exception:
            phrases_att = []

        return ChatResult(
            # response = FR par contrat. Fallback bambara uniquement si l'entrée
            # corpus n'a pas reponse_fr (0/162 actuellement, garde-fou défensif).
            response=ivr_fr or ivr_bambara,
            response_dioula=ivr_bambara,
            audio_url=audio_url,
            city=city,
            language=language.value,
            audio_language="Dioula" if audio_url else None,
            meta={
                "intent": nlu.intent,
                "cultures": cultures,
                "source": "ivr_exact",
                "phrases_attestees": [p["text"] for p in phrases_att[:3]] if phrases_att else [],
            },
        )

    # ------------------------------------------------------------------
    # Étape 4 : Fallback IVR par concept
    # ------------------------------------------------------------------

    async def _try_ivr_concept(
        self,
        nlu: NLUResult,
        city: str,
        include_audio: bool,
        language: Language,
    ) -> Optional[ChatResult]:
        """Cherche une réponse IVR approchée par concept."""
        logger.info("[ChatService] Hors corpus (intent=%s) → recherche concept", nlu.intent)

        # Fix #94 : détection action agricole sans culture → clarification
        has_agri_action = any(
            a in nlu.concepts for a in ("ACTION_PLANTER", "ACTION_CHERCHER_CONSEIL",
                                         "ACTION_RECOLTER", "ACTION_ARROSER",
                                         "ACTION_TRAITER", "ACTION_STOCKER")
        )
        has_culture = any(
            k.startswith("CULTURE_") or k.startswith("ANIMAL_")
            for k in nlu.concepts
        )
        if has_agri_action and not has_culture:
            logger.info("[ChatService] Action agricole sans culture → clarification")
            return await self._clarify_missing_culture(city, include_audio, language, nlu)

        ivr_result = await self._search_ivr_by_concept(nlu.concepts)
        if not ivr_result:
            return None

        ivr_bambara = ivr_result["reponse_bambara"]
        ivr_fr = ivr_result["reponse_fr"]

        audio_url = None
        if include_audio:
            audio_url = await self._synthesize_dioula(ivr_bambara)

        cultures = [k for k in nlu.concepts if k.startswith("CULTURE_") or k.startswith("ANIMAL_")]
        return ChatResult(
            response=ivr_fr or ivr_bambara,
            response_dioula=ivr_bambara,
            audio_url=audio_url,
            city=city,
            language=language.value,
            audio_language="Dioula" if audio_url else None,
            meta={"intent": nlu.intent, "cultures": cultures, "source": "ivr_fallback"},
        )

    async def _clarify_missing_culture(
        self,
        city: str,
        include_audio: bool,
        language: Language,
        nlu: NLUResult,
    ) -> ChatResult:
        """Demande à l'utilisateur de préciser la culture.

        Fix #94 : remplace le fallback silencieux vers CULTURE_MAIS.
        Dit clairement en dioula : "de quelle culture parles-tu ?"
        """
        # Message bilingue dioula + français
        message_dyu = (
            "N'ma a faamu ka ɲɛ. I be kuma sɛnɛ fɛn juma kan? "
            "Malo, kaba, tiga, kakawo wala dɔ wɛrɛ?"
        )
        message_fr = (
            "Je n'ai pas bien compris. De quelle culture parles-tu ? "
            "Riz, maïs, arachide, cacao ou autre ?"
        )

        audio_url = None
        if include_audio:
            audio_url = await self._synthesize_dioula(message_dyu)

        return ChatResult(
            # response = FR par contrat (cf. #166). En mode dioula, le whatsapp-server
            # envoie l'audio dioula ; response sert de fallback texte uniquement si TTS down,
            # auquel cas le FR explicite (préfixé 🇫🇷) reste plus clair qu'un dioula écrit
            # avec drapeau FR.
            response=message_fr,
            response_dioula=message_dyu,
            audio_url=audio_url,
            city=city,
            language=language.value,
            audio_language="Dioula" if audio_url else None,
            meta={
                "intent": nlu.intent,
                "source": "clarification_culture",
                "detected_actions": [a for a in nlu.concepts if a.startswith("ACTION_")],
            },
        )

    async def _search_ivr_by_concept(self, concepts: dict) -> Optional[dict]:
        """Recherche IVR par concept (fallback niveau 2).

        Retourne un dict {reponse_bambara, reponse_fr} pour permettre au caller
        d'envoyer la version FR dans `response` et la version dioula dans
        `response_dioula` (cf. issue #166).

        Sprint G.2 (issue #193) : `async def` car `chercher_reponse_ivr` est
        wrappée via `asyncio.to_thread` (évite de bloquer le event loop avec
        `corpus_service._embed_query()` SentenceTransformer ~50-200ms).
        """
        if not concepts:
            return None

        # Façade ADR-0008 §Phase C : route vers Chroma (défaut) / dual / pgvector.
        from app.services.corpus_facade import chercher_reponse_ivr

        cultures = [k for k in concepts if k.startswith("CULTURE_") or k.startswith("ANIMAL_")]
        if not cultures:
            # Fix #94 : plus de fallback silencieux vers CULTURE_MAIS.
            # Si l'utilisateur exprime une action agricole sans préciser la culture,
            # on retourne None pour déclencher une clarification en amont.
            # Avant ce fix : ACTION_PLANTER sans culture → réponse sur le maïs par défaut (bug)
            logger.info("[ChatService] Action agricole sans culture détectée → clarification nécessaire")
            return None

        intent_candidat = next(
            (intent for action, intent in _ACTION_TO_INTENT.items() if action in concepts),
            None,
        )

        try:
            if intent_candidat:
                # Sprint G.2 : to_thread pour ne pas bloquer event loop sur embed.
                result = await asyncio.to_thread(
                    chercher_reponse_ivr, intent_candidat, cultures, []
                )
                if result:
                    logger.info("[ChatService] IVR concept: %s (intent=%s)", result['id'], intent_candidat)
                    return {
                        "reponse_bambara": result["reponse_bambara"],
                        "reponse_fr": result.get("reponse_fr", ""),
                    }

            result = await asyncio.to_thread(
                chercher_reponse_ivr, "CONSEIL_PRODUCTION", cultures, []
            )
            if result:
                logger.info("[ChatService] IVR concept: %s (CONSEIL_PRODUCTION)", result['id'])
                return {
                    "reponse_bambara": result["reponse_bambara"],
                    "reponse_fr": result.get("reponse_fr", ""),
                }

        except Exception as e:
            logger.error("[ChatService] Erreur recherche concept: %s", e)

        return None

    # ------------------------------------------------------------------
    # Étape 5 : Fallback DeepSeek (dioula)
    # ------------------------------------------------------------------

    async def _try_deepseek_dioula(
        self,
        nlu: NLUResult,
        weather_data: dict | None,
        city: str,
        include_audio: bool,
        language: Language,
        user_id: Optional[str],
    ) -> ChatResult:
        """Fallback DeepSeek pour le dioula : réponse FR → traduction → TTS."""
        from app.services.deepseek import chat_with_deepseek
        from app.services.tts_dioula import synthesize_dioula

        logger.info("[ChatService] DeepSeek fallback (intent=%s)", nlu.intent)

        deepseek_response = await chat_with_deepseek(
            message=nlu.message_for_deepseek,
            weather_data=weather_data,
            language=Language.DIOULA,
            user_id=user_id,
        )

        audio_url = None
        bambara_translated = deepseek_response
        if include_audio:
            audio_url, bambara_translated = await synthesize_dioula(deepseek_response)

        cultures = [k for k in nlu.concepts if k.startswith("CULTURE_") or k.startswith("ANIMAL_")]
        return ChatResult(
            response=deepseek_response,
            response_dioula=bambara_translated or deepseek_response,
            audio_url=audio_url,
            city=city,
            language=language.value,
            audio_language="Dioula" if audio_url else None,
            meta={"intent": nlu.intent, "cultures": cultures, "source": "deepseek_open"},
        )

    # ------------------------------------------------------------------
    # Étape 6 : Chemin français
    # ------------------------------------------------------------------

    async def _try_deepseek_french(
        self,
        nlu: NLUResult,
        weather_data: dict | None,
        city: str,
        include_audio: bool,
        language: Language,
        user_id: Optional[str],
    ) -> ChatResult:
        """Chemin français uniquement via DeepSeek."""
        from app.services.deepseek import chat_with_deepseek
        from app.services.tts_french import synthesize_french

        response_text = await chat_with_deepseek(
            message=nlu.message_for_deepseek,
            weather_data=weather_data,
            language=Language.FRENCH,
            user_id=user_id,
        )

        audio_url = None
        if include_audio:
            audio_url = await synthesize_french(response_text)

        return ChatResult(
            response=response_text,
            audio_url=audio_url,
            city=city,
            language=language.value,
            audio_language="Français" if audio_url else None,
        )

    # ------------------------------------------------------------------
    # Helpers privés
    #
    # Refactor P2-09 PR 1 (Sprint L #204) : _inject_meteo + _build_meteo_bambara
    # extraits vers app/services/chat/meteo_injector.py (module pur, fonctions
    # module-level). Le seul appelant (_try_ivr_exact) importe directement
    # `inject_meteo` depuis le module.
    # ------------------------------------------------------------------

    async def _synthesize_dioula(self, text: str) -> Optional[str]:
        """Synthétise du texte dioula en audio (async wrapper)."""
        from app.services.tts_dioula import synthesize_dioula_text
        return await asyncio.to_thread(synthesize_dioula_text, text)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_chat_service: Optional[ChatService] = None


def get_chat_service() -> ChatService:
    """Retourne le ChatService singleton."""
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service
