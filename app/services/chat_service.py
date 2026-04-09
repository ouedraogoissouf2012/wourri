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
        """Applique le NLU si le message est en dioula/bambara."""
        if language not in (Language.DIOULA, Language.BOTH):
            return NLUResult(message_for_deepseek=message)

        text_to_analyze = bambara_text or ""
        bambara_chars = set("ɛɔŋɲɛ̀ɛ́ɔ̀ɔ́")
        if not text_to_analyze and any(c in message for c in bambara_chars):
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
        from app.services.vdb_service import chercher_reponse_ivr, get_phrases_for_intent

        cultures = [k for k in nlu.concepts if k.startswith("CULTURE_") or k.startswith("ANIMAL_")]
        conditions = [k for k in nlu.concepts if k.startswith("PROBLEME_") or k.startswith("TEMPS_")]

        if not nlu.intent:
            return None

        try:
            result = chercher_reponse_ivr(
                intent=nlu.intent,
                cultures=cultures if cultures else ["*"],
                conditions=conditions,
            )
        except Exception as e:
            logger.error("[ChatService] VDB erreur: %s", e)
            return None

        if not result:
            return None

        logger.info("[ChatService] IVR exact: %s (intent=%s)", result['id'], nlu.intent)
        ivr_bambara = result["reponse_bambara"]

        # Remplacer {{METEO_CONTEXTUEL}}
        ivr_bambara = self._inject_meteo(ivr_bambara, weather_data, city)

        # Sécurité : effacer tags résiduels
        ivr_bambara = re.sub(r'\{\{[^}]+\}\}', '', ivr_bambara).strip()

        # Conseil saisonnier
        conseil = get_conseil_saisonnier(cultures, intent=nlu.intent)
        if conseil:
            ivr_bambara = ivr_bambara + " " + conseil["bambara"]

        # TTS
        audio_url = None
        if include_audio:
            audio_url = await self._synthesize_dioula(ivr_bambara)

        # Phrases attestées (pour meta)
        try:
            phrases_att = get_phrases_for_intent(nlu.intent, cultures)
        except Exception:
            phrases_att = []

        return ChatResult(
            response=ivr_bambara,
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

        bambara = self._search_ivr_by_concept(nlu.concepts)
        if not bambara:
            return None

        audio_url = None
        if include_audio:
            audio_url = await self._synthesize_dioula(bambara)

        cultures = [k for k in nlu.concepts if k.startswith("CULTURE_") or k.startswith("ANIMAL_")]
        return ChatResult(
            response=bambara,
            response_dioula=bambara,
            audio_url=audio_url,
            city=city,
            language=language.value,
            audio_language="Dioula" if audio_url else None,
            meta={"intent": nlu.intent, "cultures": cultures, "source": "ivr_fallback"},
        )

    def _search_ivr_by_concept(self, concepts: dict) -> Optional[str]:
        """Recherche IVR par concept (fallback niveau 2)."""
        if not concepts:
            return None

        from app.services.vdb_service import chercher_reponse_ivr

        cultures = [k for k in concepts if k.startswith("CULTURE_") or k.startswith("ANIMAL_")]
        if not cultures:
            if "ACTION_PLANTER" in concepts or "ACTION_CHERCHER_CONSEIL" in concepts:
                logger.info("[ChatService] ACTION_PLANTER sans culture → CULTURE_MAIS défaut")
                cultures = ["CULTURE_MAIS"]
            else:
                return None

        intent_candidat = next(
            (intent for action, intent in _ACTION_TO_INTENT.items() if action in concepts),
            None,
        )

        try:
            if intent_candidat:
                result = chercher_reponse_ivr(intent=intent_candidat, cultures=cultures, conditions=[])
                if result:
                    logger.info("[ChatService] IVR concept: %s (intent=%s)", result['id'], intent_candidat)
                    return result["reponse_bambara"]

            result = chercher_reponse_ivr(intent="CONSEIL_PRODUCTION", cultures=cultures, conditions=[])
            if result:
                logger.info("[ChatService] IVR concept: %s (CONSEIL_PRODUCTION)", result['id'])
                return result["reponse_bambara"]

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
    # ------------------------------------------------------------------

    def _inject_meteo(self, ivr_bambara: str, weather_data: dict | None, city: str) -> str:
        """Remplace {{METEO_CONTEXTUEL}} par la météo réelle en bambara."""
        if "{{METEO_CONTEXTUEL}}" not in ivr_bambara:
            return ivr_bambara

        from app.data.calendrier_agricole import get_cultures_du_mois
        try:
            cultures_saison = get_cultures_du_mois(city)
            meteo_bam, _ = _build_meteo_bambara(weather_data, city, cultures_saison)
        except Exception:
            meteo_bam = ""

        return ivr_bambara.replace("{{METEO_CONTEXTUEL}}", meteo_bam)

    async def _synthesize_dioula(self, text: str) -> Optional[str]:
        """Synthétise du texte dioula en audio (async wrapper)."""
        from app.services.tts_dioula import synthesize_dioula_text
        return await asyncio.to_thread(synthesize_dioula_text, text)


# ---------------------------------------------------------------------------
# Fonction météo bambara (utilisée par ChatService et potentiellement d'autres)
# ---------------------------------------------------------------------------

def _build_meteo_bambara(weather_data: dict | None, city: str, cultures: list = None) -> tuple[str, str]:
    """Construit un message météo + cultures de saison en bambara."""
    if not weather_data:
        return ("Aw ka aw ka foro kɔlɔsi ka waati ɲuman sɔrɔ.",
                "Surveillez votre champ et profitez du bon moment.")

    code = weather_data.get("weather_code", 0)
    temp = weather_data.get("temperature", 28)
    precip = weather_data.get("precipitation", 0)
    city_name = weather_data.get("city", city)

    if code >= 95:
        bam = f"{city_name} kɔnɔ sanfɛla bɛ na. Aw ka aw ka dòn ni aw ka fɛnw bɛɛ lakana joona!"
        fr = f"Un orage arrive sur {city_name}. Mettez à l'abri vos grains et affaires immédiatement !"
    elif code >= 61 or precip > 5:
        bam = f"{city_name} kɔnɔ sanji bɛ na. Aw ka aw ka dòn ni aw ka fɛnw lakana, sanji bɛ se ka u bɔsi. Foro labɛnni waati ye sisan ye!"
        fr = f"La pluie arrive sur {city_name}. Protégez vos grains et affaires. C'est le moment de préparer le champ !"
    elif code >= 51 or precip > 0:
        bam = f"{city_name} kɔnɔ sanji fɛrɛn bɛ na. Sɛnɛ daminɛ waati ɲuman ye sisan ye."
        fr = f"Légère pluie sur {city_name}. C'est un bon moment pour commencer les semis."
    elif code == 3:
        bam = f"{city_name} kɔnɔ sankolo bɛ fara. Sanji bɛ se ka na. Aw ka foro labɛn sisan."
        fr = f"Ciel couvert sur {city_name}. La pluie peut venir. Préparez votre champ maintenant."
    elif temp > 33:
        bam = f"{city_name} kɔnɔ tile ka jugu, sanji tɛ. Aw ka aw ka sɛnɛ kalan dɔn kosɛbɛ ani aw yɛrɛw lakana tile la."
        fr = f"Chaleur intense sur {city_name}, pas de pluie. Irriguez bien vos cultures et protégez-vous du soleil."
    else:
        bam = f"{city_name} kɔnɔ tile bɛ ɲɛ, sanji tɛ sisan. Aw ka aw ka sɛnɛ kalan dɔn ni ji."
        fr = f"Ciel dégagé sur {city_name}, pas de pluie. Pensez à arroser vos cultures."

    if cultures:
        noms_bam = [c["bambara"] for c in cultures]
        noms_fr = [c["fr"] for c in cultures]
        if len(noms_bam) == 1:
            liste_bam, liste_fr = noms_bam[0], noms_fr[0]
        elif len(noms_bam) == 2:
            liste_bam = f"{noms_bam[0]} ani {noms_bam[1]}"
            liste_fr = f"{noms_fr[0]} et {noms_fr[1]}"
        else:
            liste_bam = f"{', '.join(noms_bam[:-1])} ani {noms_bam[-1]}"
            liste_fr = f"{', '.join(noms_fr[:-1])} et {noms_fr[-1]}"
        bam += f" Sisan ye {liste_bam} sɛnɛ waati ye aw ka zone kɔnɔ."
        fr += f" En ce moment, les cultures de saison dans votre zone sont : {liste_fr}."

    return (bam, fr)


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
