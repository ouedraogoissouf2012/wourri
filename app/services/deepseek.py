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


class DeepSeekUnavailableError(RuntimeError):
    """DeepSeek API indisponible (clé absente, erreur HTTP, timeout, réseau).

    Levée au lieu de retourner une string d'erreur. Avant ce fix (audit
    2026-07-21), les messages "Erreur API: 500..." étaient retournés comme
    réponse normale, puis traduits en dioula via NLLB et VOCALISÉS pour
    l'agriculteur en note vocale. L'exception doit remonter jusqu'à FastAPI
    (HTTP 500) : le whatsapp-server enregistre l'échec dans son circuit
    breaker et envoie l'audio d'excuse pré-généré (audio_cache) dans la
    langue de l'utilisateur — le chemin d'erreur conçu pour ça.

    Ne PAS attraper cette exception dans les handlers de langue ni dans
    ChatService (re-raise explicite dans `ChatService.process`).
    """


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
        raise DeepSeekUnavailableError(
            "Clé API DeepSeek non configurée (DEEPSEEK_API_KEY absente du .env)"
        )

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
                # Pas de response.text dans le message d'exception : le corps
                # d'erreur DeepSeek peut contenir des détails internes (fuite).
                logger.error(f"[DeepSeek] Erreur API: {response.status_code}")
                raise DeepSeekUnavailableError(f"DeepSeek HTTP {response.status_code}")

    except DeepSeekUnavailableError:
        raise
    except httpx.TimeoutException:
        logger.warning("[DeepSeek] Timeout après 20s")
        raise DeepSeekUnavailableError("Timeout DeepSeek (20s)") from None
    except Exception as e:
        # Type-only (pattern FIX-6 projet) : les exceptions httpx peuvent
        # embarquer l'URL complète avec query params dans leurs args.
        logger.error(f"[DeepSeek] Erreur: {type(e).__name__}")
        raise DeepSeekUnavailableError(f"Erreur réseau DeepSeek: {type(e).__name__}") from e


async def correct_stt_transcription(
    raw_text: str,
    language: Language = Language.FRENCH,
) -> str:
    """
    Corrige une transcription STT potentiellement erronée en utilisant DeepSeek.

    Le prompt est sélectionné selon `language` depuis le registre
    `STT_CORRECTION_PROMPTS` (cf. `deepseek_prompts.py`). Si la langue n'a
    pas de prompt enregistré (ex: ENGLISH avant ADR-0016), la correction
    est silencieusement skippée et `raw_text` est retourné tel quel.

    Avant 2026-06-02 : prompt FR hardcoded inline → bug "Quand je peux planter
    l'igname" généré pour des vocaux EN. Fix anti-hardcoding via registre.

    Args:
        raw_text: Texte brut de la transcription Whisper
        language: Langue de l'utilisateur (défaut FRENCH = compat)

    Returns:
        Texte corrigé si un prompt existe pour la langue, sinon raw_text.
    """
    if not raw_text or len(raw_text.strip()) < 3:
        return raw_text

    if not settings.deepseek_api_key:
        logger.warning("[STT Correction] Pas de clé DeepSeek, retour texte brut")
        return raw_text

    # Lookup OCP-compliant dans le registre de prompts. Si None pour cette
    # langue, on skip la correction (graceful — évite de traduire un EN vers FR).
    from app.services.deepseek_prompts import get_stt_correction_prompt

    system_prompt = get_stt_correction_prompt(language)
    if system_prompt is None:
        logger.info(
            "[STT Correction] Pas de prompt enregistré pour language=%s, skip correction",
            language.value,
        )
        return raw_text

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
    except Exception:
        return False
