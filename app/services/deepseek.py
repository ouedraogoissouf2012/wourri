"""
WOURI - Service Chat (DeepSeek API)
"""
import logging
import httpx

logger = logging.getLogger(__name__)
from app.config import get_settings
from app.core.pii_utils import anonymize_user_id
from app.models.schemas import Language
from app.services.conversation_history import get_history_for_deepseek, add_message

settings = get_settings()


async def chat_with_deepseek(
    message: str,
    weather_data: dict | None = None,
    language: Language = Language.FRENCH,
    user_id: str | None = None
) -> str:
    """
    Envoie un message à DeepSeek et retourne la réponse
    """
    if not settings.deepseek_api_key:
        return "Erreur: Clé API DeepSeek non configurée. Ajoutez DEEPSEEK_API_KEY dans .env"

    # Construire le contexte météo
    weather_context = ""
    if weather_data:
        weather_context = f"""
Données météo actuelles pour {weather_data['city']}:
- Température: {weather_data['temperature']}°C
- Humidité: {weather_data['humidity']}%
- Précipitations: {weather_data['precipitation']} mm
- Vent: {weather_data['wind_speed']} km/h
- Conditions: {weather_data['weather_description']}
"""

    # Lookup OCP-compliant dans le registre de prompts (ADR-0015 PR 3/4).
    # Ajouter une langue future = 1 entree dans SYSTEM_PROMPTS, jamais
    # de modification ici.
    from app.services.deepseek_prompts import SYSTEM_PROMPTS

    language_instruction = SYSTEM_PROMPTS[language]

    system_prompt = f"""Tu es WOURI, un assistant agricole expert pour les agriculteurs de Côte d'Ivoire et du Mali.

{language_instruction}

{weather_context}
"""

    url = f"{settings.deepseek_base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json"
    }

    # Construire la liste des messages avec historique
    messages = [{"role": "system", "content": system_prompt}]

    # Ajouter l'historique de conversation si user_id est fourni
    if user_id:
        history = get_history_for_deepseek(user_id, max_messages=6)
        if history:
            messages.extend(history)
            logger.info(f"[DeepSeek] Historique chargé: {len(history)} messages pour {anonymize_user_id(user_id)}")

    # Ajouter le message actuel
    messages.append({"role": "user", "content": message})

    # Lookup OCP-compliant dans le registre de parametres d'inference
    # (ADR-0015 PR 3/4). Ajouter une langue future = 1 entree dans
    # DEEPSEEK_PARAMS, jamais de modification ici.
    from app.services.deepseek_prompts import get_deepseek_params

    params = get_deepseek_params(language)
    payload = {
        "model": settings.deepseek_model,
        "messages": messages,
        "temperature": params["temperature"],
        "max_tokens": params["max_tokens"],
        "top_p": 0.9,
    }

    try:
        # Timeout réduit à 20s (était 30s) - suffisant pour des réponses courtes
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                data = response.json()
                response_text = data["choices"][0]["message"]["content"]

                # Sauvegarder la conversation dans l'historique
                if user_id:
                    add_message(user_id, "user", message)
                    add_message(user_id, "assistant", response_text)

                return response_text
            else:
                logger.error(f"[DeepSeek] Erreur API: {response.status_code}")
                return f"Erreur API: {response.status_code} - {response.text}"

    except httpx.TimeoutException:
        logger.warning("[DeepSeek] Timeout après 20s")
        return "Désolé, le service met trop de temps à répondre. Réessayez."
    except Exception as e:
        logger.error(f"[DeepSeek] Erreur: {e}")
        return f"Erreur: {str(e)}"


async def correct_stt_transcription(raw_text: str) -> str:
    """
    Corrige une transcription STT potentiellement erronée en utilisant DeepSeek.

    Le modèle comprend le contexte agricole ivoirien et peut corriger:
    - Noms de villes mal transcrits (ex: "coraux go" -> "Korhogo")
    - Termes agricoles confondus (ex: "Paname" -> "banane")
    - Erreurs phonétiques courantes

    Args:
        raw_text: Texte brut de la transcription Whisper

    Returns:
        Texte corrigé
    """
    if not raw_text or len(raw_text.strip()) < 3:
        return raw_text

    if not settings.deepseek_api_key:
        logger.warning("[STT Correction] Pas de clé DeepSeek, retour texte brut")
        return raw_text

    # Prompt spécialisé pour la correction STT
    system_prompt = """Tu es un correcteur de transcription vocale pour une application agricole en Côte d'Ivoire.

CONTEXTE: Un agriculteur ivoirien parle de cultures et météo. La transcription automatique fait des erreurs.

CORRECTIONS OBLIGATOIRES:

1. CULTURES (le mot est souvent coupé ou déformé):
   - "signes d'igname", "signe igname", "cygne" → igname
   - "Paname", "panama", "bannan" → banane
   - "pégole", "pégo", "des goles" → période
   - "maniac", "maniaque" → manioc
   - "maize", "mais" → maïs
   - "rie", "ri" → riz

2. VILLES IVOIRIENNES:
   - "coraux go", "koro go", "korogho", "corps au go" → Korhogo
   - "bouquet", "bois ké", "bouaquer" → Bouaké
   - "main", "mane", "ment", "mène", "manne", "mans", "mont", "ment", "menthe", "ma", "mam", "mang", "en main", "le mans", "laman" → Man (ville de l'ouest)
   - "fer ké", "ferques", "fair ké" → Ferkessédougou
   - "yam ou soukro", "yamoussokro" → Yamoussoukro
   - "bono", "bonnois", "beau noix" → Bonoua
   - "dallois", "da lois" → Daloa
   - "gagne oui", "gagnois" → Gagnoa

3. EXPRESSIONS AGRICOLES:
   - "faire des signes" dans contexte agricole → cultiver/planter
   - "quelle est la meilleure" + culture → période de plantation

RÈGLES STRICTES:
- Retourne UNIQUEMENT le texte corrigé, rien d'autre
- Garde la structure de la phrase originale
- Comprends le SENS: si quelqu'un parle d'igname, il ne parle pas de "signes"
- Pas de guillemets, pas d'explication"""

    url = f"{settings.deepseek_base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Corrige cette transcription: {raw_text}"}
        ],
        "temperature": 0.1,  # Très bas pour corrections déterministes
        "max_tokens": 150,   # Texte court
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:  # Timeout court
            response = await client.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                data = response.json()
                corrected = data["choices"][0]["message"]["content"].strip()

                # Nettoyer les guillemets si DeepSeek en ajoute
                if corrected.startswith('"') and corrected.endswith('"'):
                    corrected = corrected[1:-1]
                if corrected.startswith("'") and corrected.endswith("'"):
                    corrected = corrected[1:-1]

                logger.info(f"[STT Correction] '{raw_text}' → '{corrected}'")
                return corrected
            else:
                logger.error(f"[STT Correction] Erreur API: {response.status_code}")
                return raw_text

    except httpx.TimeoutException:
        logger.warning("[STT Correction] Timeout, retour texte brut")
        return raw_text
    except Exception as e:
        logger.error(f"[STT Correction] Erreur: {e}")
        return raw_text


async def check_deepseek_status() -> bool:
    """Vérifie si DeepSeek est accessible"""
    if not settings.deepseek_api_key:
        return False

    try:
        url = f"{settings.deepseek_base_url}/models"
        headers = {"Authorization": f"Bearer {settings.deepseek_api_key}"}

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, headers=headers)
            return response.status_code == 200
    except:
        return False
