"""
WOURI - Router Chat
Support Bambara/Dioula uniquement (seule langue avec traduction complète)
NLU: si le message contient du bambara (transcription ASR), le NLU reconstruit
     une phrase française claire avant d'envoyer à DeepSeek.
"""
import asyncio
import logging
import re
from fastapi import APIRouter, Request
from app.services.deepseek import chat_with_deepseek
from app.services.weather import get_weather
from app.services.tts_french import synthesize_french
from app.services.tts_bambara import translate_to_bambara, TORCH_AVAILABLE
from app.services.tts_dioula import synthesize_dioula
from app.models.schemas import ChatRequest, ChatResponse, Language
from app.data.cities import IVORIAN_CITIES
from app.data.calendrier_agricole import get_conseil_saisonnier
from fastapi import Depends
from app.config import get_settings
from app.security import require_api_key, limiter

logger = logging.getLogger(__name__)

settings = get_settings()

router = APIRouter(prefix="/api/chat", tags=["Chat"])


def _build_meteo_bambara(weather_data: dict | None, city: str, cultures: list = None) -> tuple[str, str]:
    """
    Construit un message météo + cultures de saison en bambara.

    Args:
        weather_data: données Open-Meteo (code WMO, température, précipitations)
        city: nom de la ville
        cultures: liste de dicts {bambara, fr, phase} depuis get_cultures_du_mois()
    """
    if not weather_data:
        bam = "Aw ka aw ka foro kɔlɔsi ka waati ɲuman sɔrɔ."
        fr  = "Surveillez votre champ et profitez du bon moment."
        return (bam, fr)

    code = weather_data.get("weather_code", 0)
    temp = weather_data.get("temperature", 28)
    precip = weather_data.get("precipitation", 0)
    city_name = weather_data.get("city", city)

    # --- Météo + action urgente ---
    if code >= 95:
        bam = f"{city_name} kɔnɔ sanfɛla bɛ na. Aw ka aw ka dòn ni aw ka fɛnw bɛɛ lakana joona!"
        fr  = f"Un orage arrive sur {city_name}. Mettez à l'abri vos grains et affaires immédiatement !"
    elif code >= 61 or precip > 5:
        bam = f"{city_name} kɔnɔ sanji bɛ na. Aw ka aw ka dòn ni aw ka fɛnw lakana, sanji bɛ se ka u bɔsi. Foro labɛnni waati ye sisan ye!"
        fr  = f"La pluie arrive sur {city_name}. Protégez vos grains et affaires, la pluie peut tout abîmer. C'est le moment de préparer le champ !"
    elif code >= 51 or precip > 0:
        bam = f"{city_name} kɔnɔ sanji fɛrɛn bɛ na. Sɛnɛ daminɛ waati ɲuman ye sisan ye."
        fr  = f"Légère pluie sur {city_name}. C'est un bon moment pour commencer les semis."
    elif code == 3:
        bam = f"{city_name} kɔnɔ sankolo bɛ fara. Sanji bɛ se ka na. Aw ka foro labɛn sisan."
        fr  = f"Ciel couvert sur {city_name}. La pluie peut venir. Préparez votre champ maintenant."
    else:
        if temp > 33:
            bam = f"{city_name} kɔnɔ tile ka jugu, sanji tɛ. Aw ka aw ka sɛnɛ kalan dɔn kosɛbɛ ani aw yɛrɛw lakana tile la."
            fr  = f"Chaleur intense sur {city_name}, pas de pluie. Irriguez bien vos cultures et protégez-vous du soleil."
        else:
            bam = f"{city_name} kɔnɔ tile bɛ ɲɛ, sanji tɛ sisan. Aw ka aw ka sɛnɛ kalan dɔn ni ji."
            fr  = f"Ciel dégagé sur {city_name}, pas de pluie. Pensez à arroser vos cultures."

    # --- Cultures de saison (tissées naturellement dans le message) ---
    if cultures:
        noms_bam = [c["bambara"] for c in cultures]
        noms_fr  = [c["fr"] for c in cultures]
        if len(noms_bam) == 1:
            liste_bam = noms_bam[0]
            liste_fr  = noms_fr[0]
        elif len(noms_bam) == 2:
            liste_bam = f"{noms_bam[0]} ani {noms_bam[1]}"
            liste_fr  = f"{noms_fr[0]} et {noms_fr[1]}"
        else:
            liste_bam = f"{', '.join(noms_bam[:-1])} ani {noms_bam[-1]}"
            liste_fr  = f"{', '.join(noms_fr[:-1])} et {noms_fr[-1]}"
        bam += f" Sisan ye {liste_bam} sɛnɛ waati ye aw ka zone kɔnɔ."
        fr  += f" En ce moment, les cultures de saison dans votre zone sont : {liste_fr}."

    logger.info("[METEO BAM] %s", bam)
    logger.info("[METEO FR]  %s", fr)
    return (bam, fr)


def _apply_nlu_preprocessing(message: str, bambara_text: str | None = None) -> tuple[str, str | None, dict]:
    """Applique le NLU si le message semble être du bambara ou si bambara_text est fourni.

    Retourne (message_final_pour_deepseek, intent_nlu_ou_None, concepts_dict).
    - Si bambara_text fourni → NLU sur bambara_text, french_sentence remplace le message
    - Si message contient des caractères bambara → NLU sur le message lui-même
    - Sinon → message inchangé
    """
    bambara_text_to_analyze = bambara_text or ""

    # Détecter si le message lui-même est en bambara (présence de ɛ, ɔ, ŋ, ɲ)
    bambara_chars = set("ɛɔŋɲɛ̀ɛ́ɔ̀ɔ́")
    if not bambara_text_to_analyze and any(c in message for c in bambara_chars):
        bambara_text_to_analyze = message

    if not bambara_text_to_analyze:
        return message, None, {}

    try:
        from app.services.nlu import get_nlu_service
        nlu = get_nlu_service()
        if nlu is None:
            return message, None, {}

        result = nlu.process(bambara_text_to_analyze)

        # Hors sujet agricole → retourner le message hors-sujet directement
        if result.is_out_of_scope:
            logger.info("[Chat NLU] Hors sujet détecté pour: '%s'", bambara_text_to_analyze[:50])
            return result.out_of_scope_message_fr or message, "HORS_SUJET", {}

        concepts = result.concepts or {}

        # Phrase reconstruite disponible → enrichir avec contexte culture/animal
        if result.french_sentence:
            enriched = _enrich_message_for_deepseek(result.french_sentence, concepts)
            logger.info("[Chat NLU] Phrase reconstruite: '%s'", result.french_sentence)
            return enriched, result.intent, concepts

        return message, result.intent if result.intent else None, concepts

    except Exception as e:
        logger.error("[Chat NLU] Erreur: %s", e)
        return message, None, {}


# Labels lisibles pour les cultures et animaux (pour le contexte DeepSeek)
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


def _enrich_message_for_deepseek(french_sentence: str, concepts: dict) -> str:
    """Ajoute un préfixe de contexte paysan pour guider DeepSeek vers une réponse complète.

    Exemple: "[Paysan cultive: riz] Bonjour, je cherche des conseils..."
    → DeepSeek comprend qu'il faut couvrir timing + sol + action immédiate.
    """
    culture = next((_CULTURE_LABELS[k] for k in concepts if k in _CULTURE_LABELS), None)
    animal = next((_ANIMAL_LABELS[k] for k in concepts if k in _ANIMAL_LABELS), None)

    sujet = culture or animal
    if sujet:
        prefix = f"[Paysan cultive: {sujet}] "
        logger.info("[Chat NLU] Contexte ajouté: %s", prefix.strip())
        return prefix + french_sentence

    return french_sentence


def _chercher_ivr(intent: str, concepts: dict) -> str | None:
    """
    Cherche une réponse bambara pré-validée dans la BD vectorielle IVR.
    Retourne la réponse bambara si trouvée, None sinon (fallback traduction).
    """
    try:
        from app.services.vdb_service import chercher_reponse_ivr

        cultures = [k for k in concepts if k.startswith("CULTURE_") or k.startswith("ANIMAL_")]
        conditions = [k for k in concepts if k.startswith("PROBLEME_") or k.startswith("TEMPS_")]

        if not intent:
            return None

        result = chercher_reponse_ivr(
            intent=intent,
            cultures=cultures if cultures else ["*"],
            conditions=conditions,
        )

        if result:
            score = result.get("score_validation", 0.0)
            logger.info("[VDB] Réponse trouvée: %s (score=%.2f)", result['id'], score)
            logger.info("[REPONSE BAM] %s", result['reponse_bambara'])
            logger.info("[REPONSE FR]  %s", result.get('reponse_fr', '(non disponible)'))
            return result["reponse_bambara"]

    except Exception as e:
        logger.error("[VDB] Erreur recherche IVR: %s", e)

    return None


def _chercher_ivr_par_concept(concepts: dict) -> str | None:
    """
    Fallback IVR niveau 2 : cherche une réponse approchée depuis les concepts seuls.

    Quand l'intent exact n'est pas trouvé (QUESTION_GENERALE, confiance faible...),
    on tente de répondre via la culture détectée + l'action la plus proche.

    Stratégie :
    1. Mappe l'ACTION détectée vers un intent candidat
    2. Cherche : culture + intent candidat
    3. Sinon   : culture + CONSEIL_PRODUCTION (défaut)
    4. Retourne None si aucune culture détectée (→ message non-compris)
    """
    if not concepts:
        return None

    cultures = [k for k in concepts if k.startswith("CULTURE_") or k.startswith("ANIMAL_")]

    # Si ACTION_PLANTER détecté sans culture (ASR a raté le nom de la plante),
    # essayer CULTURE_MAIS (culture #1 en CI) comme défaut
    if not cultures:
        if "ACTION_PLANTER" in concepts or "ACTION_CHERCHER_CONSEIL" in concepts:
            logger.info("[Chat IVR] ACTION_PLANTER sans culture → essai CULTURE_MAIS par défaut")
            cultures = ["CULTURE_MAIS"]
        else:
            return None

    ACTION_TO_INTENT = {
        "ACTION_PLANTER":          "QUESTION_SAISON_PLANTATION",
        "ACTION_RECOLTER":         "QUESTION_RECOLTE",
        "ACTION_ARROSER":          "QUESTION_IRRIGATION",
        "ACTION_TRAITER":          "DIAGNOSTIC_PROBLEME",
        "ACTION_STOCKER":          "QUESTION_STOCKAGE",
        "ACTION_VENDRE":           "QUESTION_VENTE",
        "ACTION_CHERCHER_CONSEIL": "CONSEIL_PRODUCTION",
        "ACTION_LABOURER":         "CONSEIL_PRODUCTION",
    }

    intent_candidat = next(
        (intent for action, intent in ACTION_TO_INTENT.items() if action in concepts),
        None
    )

    try:
        from app.services.vdb_service import chercher_reponse_ivr

        if intent_candidat:
            result = chercher_reponse_ivr(intent=intent_candidat, cultures=cultures, conditions=[])
            if result:
                logger.info("[Chat IVR] Approché par concept: %s (intent=%s)", result['id'], intent_candidat)
                return result["reponse_bambara"]

        # Défaut : conseil de production pour la culture détectée
        result = chercher_reponse_ivr(intent="CONSEIL_PRODUCTION", cultures=cultures, conditions=[])
        if result:
            logger.info("[Chat IVR] Approché par concept: %s (CONSEIL_PRODUCTION défaut)", result['id'])
            return result["reponse_bambara"]

    except Exception as e:
        logger.error("[Chat IVR] Erreur recherche par concept: %s", e)

    return None


async def _translate_to_bambara_enhanced(french_text: str) -> str:
    """Traduit FR→Bambara en essayant DeepSeek+ancres, puis NLLB en fallback."""
    try:
        from app.services.translation.deepseek_translator import translate_fr_to_bambara_with_validation
        from app.services.translation import get_translation_service

        svc = get_translation_service()
        fr_bam_index = svc.get_repository().get_all_words(
            __import__('app.services.translation.interfaces', fromlist=['Direction']).Direction.FR_TO_BAM
        )

        bambara, confidence, method = await translate_fr_to_bambara_with_validation(
            french_text=french_text,
            deepseek_api_key=settings.deepseek_api_key,
            deepseek_base_url=settings.deepseek_base_url,
            deepseek_model=settings.deepseek_model,
            fr_to_bam_index=fr_bam_index,
        )

        if confidence > 0.6:
            logger.info("[Chat Trad] Méthode: %s, conf=%.2f", method, confidence)
            return bambara
        else:
            logger.warning("[Chat Trad] Confiance insuffisante (%.2f < 0.6) → fallback NLLB", confidence)

    except Exception as e:
        logger.error("[Chat Trad] DeepSeek translation erreur: %s", e)

    # Fallback NLLB (chemin existant)
    return translate_to_bambara(french_text)


def detect_city_in_message(message: str) -> str | None:
    """Détecte si le message mentionne une ville ivoirienne.
    Retourne le nom exact de la ville ou None.
    Utilise des word boundaries pour éviter les faux positifs
    ex: "Man" dans "manioc", "Kong" dans "kongobi".
    """
    msg_lower = message.lower()
    # Trier par longueur décroissante pour matcher "San-Pedro" avant "Man"
    for city_name in sorted(IVORIAN_CITIES.keys(), key=len, reverse=True):
        # Word boundary: la ville doit être un mot entier, pas une sous-chaîne
        pattern = r'\b' + re.escape(city_name.lower()) + r'\b'
        if re.search(pattern, msg_lower):
            return city_name
    return None


@router.post("/", response_model=ChatResponse, dependencies=[Depends(require_api_key)])
@limiter.limit("10/minute")
async def chat(request: Request, body: ChatRequest):
    """
    Envoie un message à l'assistant WOURI

    - **message**: Question ou demande de l'utilisateur
    - **city**: Ville pour le contexte météo (défaut: Abidjan)
    - **language**: Langue de réponse (french, dioula, ou both pour les deux)
    - **include_audio**: Générer l'audio de la réponse (défaut: true)

    Langues supportées:
    - Français: Texte + Audio
    - Bambara/Dioula: Texte + Audio (traduction via NLLB-200)
    """
    try:
        # Détecter si le message mentionne une ville différente de celle configurée
        mentioned_city = detect_city_in_message(body.message)
        city = mentioned_city if mentioned_city else body.city
        if mentioned_city and mentioned_city.lower() != body.city.lower():
            logger.info("[Chat] Ville détectée dans le message: %s (défaut: %s)", mentioned_city, body.city)

        # NLU: si bambara_text fourni (depuis ASR), reconstruire une phrase claire
        # Le NLU peut aussi détecter les messages hors-sujet et répondre directement
        message_for_deepseek = body.message
        nlu_intent = None
        nlu_concepts = {}

        if body.language in (Language.DIOULA, Language.BOTH):
            message_for_deepseek, nlu_intent, nlu_concepts = _apply_nlu_preprocessing(
                message=body.message,
                bambara_text=body.bambara_text
            )
            # Si hors sujet → tenter DeepSeek avec prompt agricole strict
            # (évite la frustration face à un message vide pour une vraie question)
            if nlu_intent == "HORS_SUJET":
                pass  # continue vers le chemin DeepSeek normal ci-dessous

        audio_url = None
        response_dioula = None
        audio_language_name = None

        # Récupérer météo tôt (utilisée pour salutations + chemin DeepSeek)
        weather_data = await get_weather(city)

        # CHEMIN PRINCIPAL IVR : chercher réponse bambara pré-validée dans la VDB
        # (évite DeepSeek + traduction pour les cas couverts par le corpus)
        if body.language in (Language.DIOULA, Language.BOTH) and nlu_intent:
            ivr_bambara = _chercher_ivr(intent=nlu_intent, concepts=nlu_concepts)
            if ivr_bambara:
                logger.info("[Chat IVR] Réponse corpus trouvée — chemin direct bambara (intent=%s)", nlu_intent)

                # Remplacer {{METEO_CONTEXTUEL}} si présent (entrées salutation)
                # → inclut météo réelle + cultures de saison selon la zone de la ville
                if "{{METEO_CONTEXTUEL}}" in ivr_bambara:
                    from app.data.calendrier_agricole import get_cultures_du_mois
                    try:
                        cultures_saison = get_cultures_du_mois(city)
                        meteo_bam, _ = _build_meteo_bambara(weather_data, city, cultures_saison)
                    except Exception:
                        meteo_bam = ""
                    ivr_bambara = ivr_bambara.replace("{{METEO_CONTEXTUEL}}", meteo_bam)
                # Sécurité finale : effacer tout tag {{...}} résiduel avant TTS
                ivr_bambara = re.sub(r'\{\{[^}]+\}\}', '', ivr_bambara).strip()

                # Injecter conseil saisonnier selon le mois actuel
                cultures_detectees = [k for k in nlu_concepts if k.startswith("CULTURE_") or k.startswith("ANIMAL_")]
                conseil = get_conseil_saisonnier(cultures_detectees, intent=nlu_intent)
                if conseil:
                    ivr_bambara = ivr_bambara + " " + conseil["bambara"]

                if body.include_audio:
                    from app.services.tts_dioula import synthesize_dioula_text
                    audio_url = await asyncio.to_thread(synthesize_dioula_text, ivr_bambara)
                    audio_language_name = "Dioula"
                cultures = [k for k in nlu_concepts if k.startswith("CULTURE_") or k.startswith("ANIMAL_")]

                # Phrases bambara CI réelles associées à cet intent (pour meta/debug)
                from app.services.vdb_service import get_phrases_for_intent
                phrases_att = get_phrases_for_intent(nlu_intent, cultures)

                return ChatResponse(
                    response=ivr_bambara,
                    response_dioula=ivr_bambara,
                    response_local=None,
                    audio_url=audio_url,
                    city=city,
                    language=body.language.value,
                    audio_language=audio_language_name,
                    meta={
                        "intent": nlu_intent,
                        "cultures": cultures,
                        "source": "ivr_exact",
                        "phrases_attestees": [p["text"] for p in phrases_att[:3]],
                    }
                )

        # CHEMIN FALLBACK : intent exact non trouvé dans l'IVR
        logger.info("[Chat IVR] Hors corpus (intent=%s) → recherche par concept", nlu_intent)

        # DIOULA / BOTH : recherche par concept d'abord
        if body.language in (Language.DIOULA, Language.BOTH):
            bambara_fallback = _chercher_ivr_par_concept(nlu_concepts)
            fallback_source = "ivr_fallback" if bambara_fallback else None

            if bambara_fallback:
                # Concept agricole trouvé dans le corpus → répondre directement
                if body.include_audio:
                    from app.services.tts_dioula import synthesize_dioula_text
                    audio_url = await asyncio.to_thread(synthesize_dioula_text, bambara_fallback)
                    audio_language_name = "Dioula"
                cultures = [k for k in nlu_concepts if k.startswith("CULTURE_") or k.startswith("ANIMAL_")]
                return ChatResponse(
                    response=bambara_fallback,
                    response_dioula=bambara_fallback,
                    response_local=None,
                    audio_url=audio_url,
                    city=city,
                    language=body.language.value,
                    audio_language=audio_language_name,
                    meta={"intent": nlu_intent, "cultures": cultures, "source": fallback_source}
                )

            # Aucun concept agricole identifié → DeepSeek avec prompt agricole strict
            # (question ouverte: "comment traiter la rouille du maïs ?", question hors-corpus, etc.)
            logger.info("[Chat IVR] Aucun concept → DeepSeek fallback agricole (intent=%s)", nlu_intent)
            deepseek_response = await chat_with_deepseek(
                message=message_for_deepseek,
                weather_data=weather_data,
                language=Language.DIOULA,
                user_id=getattr(body, 'user_id', None)
            )
            # Traduire la réponse DeepSeek (FR) en bambara pour l'audio
            from app.services.tts_dioula import synthesize_dioula
            audio_url_dioula, bambara_translated = await asyncio.to_thread(
                lambda: (None, deepseek_response)  # texte français → TTS direct si traduction indispo
            )
            if body.include_audio:
                audio_url, bambara_translated = await synthesize_dioula(deepseek_response)
                audio_language_name = "Dioula"
            cultures = [k for k in nlu_concepts if k.startswith("CULTURE_") or k.startswith("ANIMAL_")]
            return ChatResponse(
                response=deepseek_response,
                response_dioula=bambara_translated or deepseek_response,
                response_local=None,
                audio_url=audio_url,
                city=city,
                language=body.language.value,
                audio_language=audio_language_name,
                meta={"intent": nlu_intent, "cultures": cultures, "source": "deepseek_open"}
            )

        # FRENCH uniquement : DeepSeek reste actif
        weather_data = await get_weather(city)
        response_text = await chat_with_deepseek(
            message=message_for_deepseek,
            weather_data=weather_data,
            language=Language.FRENCH,
            user_id=body.user_id
        )
        if body.include_audio:
            audio_url = await synthesize_french(response_text)
            audio_language_name = "Français"

        return ChatResponse(
            response=response_text,
            response_dioula=None,
            response_local=None,
            audio_url=audio_url,
            city=city,
            language=body.language.value,
            audio_language=audio_language_name
        )
    except Exception as e:
        logger.error("Erreur chat: %s", e)
        return ChatResponse(
            response="Désolé, je rencontre des problèmes de connexion. Vérifiez votre connexion internet et réessayez.",
            response_dioula=None,
            response_local=None,
            audio_url=None,
            city=body.city,
            language=body.language.value,
            audio_language=None
        )


@router.post("/simple", dependencies=[Depends(require_api_key)])
@limiter.limit("10/minute")
async def chat_simple(request: Request, message: str, city: str = "Abidjan"):
    """
    Version simple du chat (paramètres en query)

    - **message**: Question de l'utilisateur
    - **city**: Ville (défaut: Abidjan)
    """
    weather_data = await get_weather(city)

    response_text = await chat_with_deepseek(
        message=message,
        weather_data=weather_data,
        language=Language.FRENCH
    )

    return {"response": response_text, "city": city}


@router.get("/languages")
async def list_audio_languages():
    """
    Liste les langues disponibles pour le chat
    """
    return {
        "available_languages": {
            "french": "Français",
            "dioula": "Bambara/Dioula",
            "both": "Français + Dioula"
        },
        "default": "both",
        "full_support": {
            "languages": ["french", "dioula"],
            "description": "Texte + Traduction + Audio complet"
        },
        "note": "Seul le Bambara/Dioula dispose d'une traduction automatique via NLLB-200"
    }
