"""
WOURI - Service Chat (DeepSeek API)
"""
import httpx
from app.config import get_settings
from app.models.schemas import Language

settings = get_settings()


async def chat_with_deepseek(
    message: str,
    weather_data: dict | None = None,
    language: Language = Language.FRENCH
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

    # Instructions selon la langue
    if language == Language.DIOULA:
        language_instruction = """
LANGUE: Réponds en FRANÇAIS TRÈS SIMPLE car le texte sera traduit en Bambara.
RÈGLES IMPORTANTES:
1. Phrases COURTES (max 10 mots par phrase)
2. Vocabulaire SIMPLE (pas de mots compliqués)
3. Pas de métaphores ou expressions idiomatiques
4. Structure simple: Sujet + Verbe + Complément
5. Pas de markdown (pas de **, *, #, etc.)
6. Parle comme à un enfant de 10 ans
"""
    else:
        language_instruction = """
LANGUE: Réponds en français clair et accessible.
- Utilise un langage simple adapté aux agriculteurs
- Évite le jargon technique
- Pas de markdown (pas de **, *, #, etc.)
"""

    system_prompt = f"""Tu es WOURI, un assistant agricole intelligent pour les agriculteurs de Côte d'Ivoire.

{language_instruction}

CONTEXTE:
- Tu aides les agriculteurs avec des conseils pratiques sur leurs cultures
- Tu donnes des informations météo et leur impact sur l'agriculture
- Tu es amical, patient et encourageant

{weather_context}

IMPORTANT:
- Sois concis (max 3-4 phrases)
- Donne des conseils pratiques et actionnables
- Mentionne toujours la ville quand tu parles de météo
"""

    url = f"{settings.deepseek_base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ],
        "temperature": 0.7,
        "max_tokens": 500
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"]
            else:
                return f"Erreur API: {response.status_code} - {response.text}"

    except httpx.TimeoutException:
        return "Désolé, le service met trop de temps à répondre. Réessayez."
    except Exception as e:
        return f"Erreur: {str(e)}"


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
