"""
WOURI - Router Chat
Support Bambara/Dioula uniquement (seule langue avec traduction complète)
"""
from fastapi import APIRouter
from app.services.deepseek import chat_with_deepseek
from app.services.weather import get_weather
from app.services.tts_french import synthesize_french
from app.services.tts_bambara import synthesize_bambara, translate_to_bambara, TORCH_AVAILABLE
from app.models.schemas import ChatRequest, ChatResponse, Language

router = APIRouter(prefix="/api/chat", tags=["Chat"])


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
        # Récupérer la météo pour le contexte (peut échouer si pas de connexion)
        weather_data = await get_weather(request.city)

        # Obtenir la réponse de DeepSeek (toujours en français d'abord)
        response_text = await chat_with_deepseek(
            message=request.message,
            weather_data=weather_data,
            language=Language.FRENCH,  # Réponse de base toujours en français
            user_id=request.user_id  # Pour l'historique de conversation
        )

        audio_url = None
        response_dioula = None
        audio_language_name = None

        # Mode BOTH: Français + Dioula
        if request.language == Language.BOTH:
            # Traduire vers Bambara/Dioula ET générer l'audio en une seule passe
            # (synthesize_bambara fait déjà la traduction)
            if request.include_audio:
                audio_url, bambara_text = await synthesize_bambara(response_text)
                if bambara_text:
                    response_dioula = bambara_text
                audio_language_name = "Bambara/Dioula"
            elif TORCH_AVAILABLE:
                # Si pas d'audio, juste traduire
                response_dioula = translate_to_bambara(response_text)

        # Mode DIOULA uniquement
        elif request.language == Language.DIOULA:
            if request.include_audio:
                audio_url, bambara_text = await synthesize_bambara(response_text)
                if bambara_text:
                    response_dioula = bambara_text
                    response_text = bambara_text  # Remplacer le texte principal
                audio_language_name = "Bambara/Dioula"
            else:
                # Juste traduire sans audio
                if TORCH_AVAILABLE:
                    bambara_text = translate_to_bambara(response_text)
                    if bambara_text:
                        response_dioula = bambara_text
                        response_text = bambara_text

        # Mode FRENCH uniquement
        elif request.language == Language.FRENCH:
            if request.include_audio:
                audio_url = await synthesize_french(response_text)
                audio_language_name = "Français"

        return ChatResponse(
            response=response_text,
            response_dioula=response_dioula,
            response_local=None,
            audio_url=audio_url,
            city=request.city,
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
