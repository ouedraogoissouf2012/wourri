"""
WOURI - Router Chat
Support Bambara/Dioula uniquement (seule langue avec traduction complète)
NLU: si le message contient du bambara (transcription ASR), le NLU reconstruit
     une phrase française claire avant d'envoyer à DeepSeek.
"""
from fastapi import APIRouter
from app.services.deepseek import chat_with_deepseek
from app.services.weather import get_weather
from app.services.tts_french import synthesize_french
from app.services.tts_bambara import translate_to_bambara, TORCH_AVAILABLE
from app.services.tts_dioula import synthesize_dioula
from app.models.schemas import ChatRequest, ChatResponse, Language
from app.data.cities import IVORIAN_CITIES
from app.data.calendrier_agricole import get_conseil_saisonnier
from app.config import get_settings

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

    print(f"[METEO BAM] {bam}")
    print(f"[METEO FR]  {fr}")
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
            print(f"[Chat NLU] Hors sujet détecté pour: '{bambara_text_to_analyze[:50]}'")
            return result.out_of_scope_message_fr or message, "HORS_SUJET", {}

        concepts = result.concepts or {}

        # Phrase reconstruite disponible → enrichir avec contexte culture/animal
        if result.french_sentence:
            enriched = _enrich_message_for_deepseek(result.french_sentence, concepts)
            print(f"[Chat NLU] Phrase reconstruite: '{result.french_sentence}'")
            return enriched, result.intent, concepts

        return message, result.intent if result.intent else None, concepts

    except Exception as e:
        print(f"[Chat NLU] Erreur: {e}")
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
        print(f"[Chat NLU] Contexte ajouté: {prefix.strip()}")
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
            print(f"[VDB] Réponse trouvée: {result['id']} (score={score:.2f})")
            print(f"[REPONSE BAM] {result['reponse_bambara']}")
            print(f"[REPONSE FR]  {result.get('reponse_fr', '(non disponible)')}")
            return result["reponse_bambara"]

    except Exception as e:
        print(f"[VDB] Erreur recherche IVR: {e}")

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
    if not cultures:
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
                print(f"[Chat IVR] Approché par concept: {result['id']} (intent={intent_candidat})")
                return result["reponse_bambara"]

        # Défaut : conseil de production pour la culture détectée
        result = chercher_reponse_ivr(intent="CONSEIL_PRODUCTION", cultures=cultures, conditions=[])
        if result:
            print(f"[Chat IVR] Approché par concept: {result['id']} (CONSEIL_PRODUCTION défaut)")
            return result["reponse_bambara"]

    except Exception as e:
        print(f"[Chat IVR] Erreur recherche par concept: {e}")

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
            print(f"[Chat Trad] Méthode: {method}, conf={confidence:.2f}")
            return bambara
        else:
            print(f"[Chat Trad] Confiance insuffisante ({confidence:.2f} < 0.6) → fallback NLLB")

    except Exception as e:
        print(f"[Chat Trad] DeepSeek translation erreur: {e}")

    # Fallback NLLB (chemin existant)
    return translate_to_bambara(french_text)


def detect_city_in_message(message: str) -> str | None:
    """Détecte si le message mentionne une ville ivoirienne.
    Retourne le nom exact de la ville ou None.
    La ville configurée est le défaut, mais si l'utilisateur
    mentionne une autre ville, on utilise celle-là.
    """
    msg_lower = message.lower()
    # Trier par longueur décroissante pour matcher "San-Pedro" avant "Man"
    for city_name in sorted(IVORIAN_CITIES.keys(), key=len, reverse=True):
        if city_name.lower() in msg_lower:
            return city_name
    return None


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest):
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
        mentioned_city = detect_city_in_message(request.message)
        city = mentioned_city if mentioned_city else request.city
        if mentioned_city and mentioned_city.lower() != request.city.lower():
            print(f"[Chat] Ville détectée dans le message: {mentioned_city} (défaut: {request.city})")

        # NLU: si bambara_text fourni (depuis ASR), reconstruire une phrase claire
        # Le NLU peut aussi détecter les messages hors-sujet et répondre directement
        message_for_deepseek = request.message
        nlu_intent = None
        nlu_concepts = {}

        if request.language in (Language.DIOULA, Language.BOTH):
            message_for_deepseek, nlu_intent, nlu_concepts = _apply_nlu_preprocessing(
                message=request.message,
                bambara_text=request.bambara_text
            )
            # Si hors sujet, répondre directement sans appeler DeepSeek
            if nlu_intent == "HORS_SUJET":
                from app.services.vdb_service import get_reponse_fallback
                bambara_hors_sujet = get_reponse_fallback()
                return ChatResponse(
                    response=message_for_deepseek,
                    response_dioula=bambara_hors_sujet,
                    response_local=None,
                    audio_url=None,
                    city=city,
                    language=request.language.value,
                    audio_language=None
                )

        audio_url = None
        response_dioula = None
        audio_language_name = None

        # Récupérer météo tôt (utilisée pour salutations + chemin DeepSeek)
        weather_data = await get_weather(city)

        # CHEMIN PRINCIPAL IVR : chercher réponse bambara pré-validée dans la VDB
        # (évite DeepSeek + traduction pour les cas couverts par le corpus)
        if request.language in (Language.DIOULA, Language.BOTH) and nlu_intent:
            ivr_bambara = _chercher_ivr(intent=nlu_intent, concepts=nlu_concepts)
            if ivr_bambara:
                print(f"[Chat IVR] Réponse corpus trouvée — chemin direct bambara (intent={nlu_intent})")

                # Remplacer {{METEO_CONTEXTUEL}} si présent (entrées salutation)
                # → inclut météo réelle + cultures de saison selon la zone de la ville
                if "{{METEO_CONTEXTUEL}}" in ivr_bambara:
                    from app.data.calendrier_agricole import get_cultures_du_mois
                    cultures_saison = get_cultures_du_mois(city)
                    meteo_bam, meteo_fr = _build_meteo_bambara(weather_data, city, cultures_saison)
                    ivr_bambara = ivr_bambara.replace("{{METEO_CONTEXTUEL}}", meteo_bam)

                # Injecter conseil saisonnier selon le mois actuel
                cultures_detectees = [k for k in nlu_concepts if k.startswith("CULTURE_") or k.startswith("ANIMAL_")]
                conseil = get_conseil_saisonnier(cultures_detectees, intent=nlu_intent)
                if conseil:
                    ivr_bambara = ivr_bambara + " " + conseil["bambara"]

                if request.include_audio:
                    from app.services.tts_dioula import synthesize_dioula_text
                    audio_url = synthesize_dioula_text(ivr_bambara)
                    audio_language_name = "Dioula"
                cultures = [k for k in nlu_concepts if k.startswith("CULTURE_") or k.startswith("ANIMAL_")]
                return ChatResponse(
                    response=ivr_bambara,
                    response_dioula=ivr_bambara,
                    response_local=None,
                    audio_url=audio_url,
                    city=city,
                    language=request.language.value,
                    audio_language=audio_language_name,
                    meta={"intent": nlu_intent, "cultures": cultures, "source": "ivr_exact"}
                )

        # CHEMIN FALLBACK : intent exact non trouvé dans l'IVR
        print(f"[Chat IVR] Hors corpus (intent={nlu_intent}) → recherche par concept")

        # DIOULA / BOTH : recherche par concept → jamais NLLB ni DeepSeek
        if request.language in (Language.DIOULA, Language.BOTH):
            bambara_fallback = _chercher_ivr_par_concept(nlu_concepts)
            fallback_source = "ivr_fallback" if bambara_fallback else "fallback_generic"

            if not bambara_fallback:
                from app.services.vdb_service import get_reponse_fallback
                bambara_fallback = get_reponse_fallback()
                print(f"[Chat IVR] Aucun concept agricole → message non-compris")

            if request.include_audio:
                from app.services.tts_dioula import synthesize_dioula_text
                audio_url = synthesize_dioula_text(bambara_fallback)
                audio_language_name = "Dioula"

            cultures = [k for k in nlu_concepts if k.startswith("CULTURE_") or k.startswith("ANIMAL_")]
            return ChatResponse(
                response=bambara_fallback,
                response_dioula=bambara_fallback,
                response_local=None,
                audio_url=audio_url,
                city=city,
                language=request.language.value,
                audio_language=audio_language_name,
                meta={"intent": nlu_intent, "cultures": cultures, "source": fallback_source}
            )

        # FRENCH uniquement : DeepSeek reste actif
        weather_data = await get_weather(city)
        response_text = await chat_with_deepseek(
            message=message_for_deepseek,
            weather_data=weather_data,
            language=Language.FRENCH,
            user_id=request.user_id
        )
        if request.include_audio:
            audio_url = await synthesize_french(response_text)
            audio_language_name = "Français"

        return ChatResponse(
            response=response_text,
            response_dioula=None,
            response_local=None,
            audio_url=audio_url,
            city=city,
            language=request.language.value,
            audio_language=audio_language_name
        )
    except Exception as e:
        print(f"Erreur chat: {e}")
        return ChatResponse(
            response="Désolé, je rencontre des problèmes de connexion. Vérifiez votre connexion internet et réessayez.",
            response_dioula=None,
            response_local=None,
            audio_url=None,
            city=request.city,
            language=request.language.value,
            audio_language=None
        )


@router.post("/simple")
async def chat_simple(message: str, city: str = "Abidjan"):
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
