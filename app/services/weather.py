"""
WOURI - Service Météo (Open-Meteo)
100% GRATUIT - Pas de clé API requise
Avec cache pour réduire les appels API
"""
import logging
import httpx
import time

logger = logging.getLogger(__name__)
from app.data.cities import get_city, get_all_cities
from app.config import get_settings

settings = get_settings()

# ========================================
# CACHE MÉTÉO - 15 minutes
# ========================================
_weather_cache = {}  # { "city_name": { "data": {...}, "timestamp": 123456 } }
CACHE_DURATION = 15 * 60  # 15 minutes en secondes


def get_cached_weather(city_name: str) -> dict | None:
    """Récupère la météo depuis le cache si elle est encore valide"""
    city_lower = city_name.lower()
    if city_lower in _weather_cache:
        cached = _weather_cache[city_lower]
        age = time.time() - cached["timestamp"]
        if age < CACHE_DURATION:
            logger.info(f"[MÉTÉO] Cache HIT pour {city_name} (age: {int(age)}s)")
            return cached["data"]
        else:
            logger.info(f"[MÉTÉO] Cache EXPIRÉ pour {city_name} (age: {int(age)}s)")
    return None


def set_cached_weather(city_name: str, data: dict):
    """Stocke la météo dans le cache"""
    city_lower = city_name.lower()
    _weather_cache[city_lower] = {
        "data": data,
        "timestamp": time.time()
    }
    logger.info(f"[MÉTÉO] Cache SET pour {city_name}")

# Codes météo WMO
WEATHER_CODES = {
    0: "Ciel dégagé",
    1: "Principalement dégagé",
    2: "Partiellement nuageux",
    3: "Couvert",
    45: "Brouillard",
    48: "Brouillard givrant",
    51: "Bruine légère",
    53: "Bruine modérée",
    55: "Bruine dense",
    61: "Pluie légère",
    63: "Pluie modérée",
    65: "Pluie forte",
    80: "Averses légères",
    81: "Averses modérées",
    82: "Averses violentes",
    95: "Orage",
    96: "Orage avec grêle légère",
    99: "Orage avec grêle forte",
}


async def get_weather(city_name: str) -> dict | None:
    """
    Récupère la météo d'une ville via Open-Meteo (GRATUIT)
    Utilise un cache de 15 minutes pour réduire les appels API
    """
    # 1. Vérifier le cache d'abord
    cached = get_cached_weather(city_name)
    if cached:
        return cached

    # 2. Pas de cache, appeler l'API
    city = get_city(city_name)
    if not city:
        return None

    url = f"{settings.openmeteo_base_url}/forecast"
    params = {
        "latitude": city["lat"],
        "longitude": city["lon"],
        "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
        "timezone": "Africa/Abidjan"
    }

    try:
        # Timeout réduit à 5 secondes (était 15s)
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, params=params)

            if response.status_code == 200:
                data = response.json()
                current = data.get("current", {})

                weather_code = current.get("weather_code", 0)
                weather_desc = WEATHER_CODES.get(weather_code, "Inconnu")

                result = {
                    "city": city["name"],
                    "region": city["region"],
                    "temperature": current.get("temperature_2m", 0),
                    "humidity": current.get("relative_humidity_2m", 0),
                    "precipitation": current.get("precipitation", 0),
                    "wind_speed": current.get("wind_speed_10m", 0),
                    "weather_code": weather_code,
                    "weather_description": weather_desc,
                    "advice": generate_farming_advice(
                        current.get("temperature_2m", 25),
                        current.get("precipitation", 0),
                        weather_code
                    )
                }

                # 3. Stocker dans le cache
                set_cached_weather(city_name, result)
                return result

    except Exception as e:
        logger.error(f"[MÉTÉO] Erreur API: {e}")
        return None

    return None


def generate_farming_advice(temperature: float, precipitation: float, weather_code: int) -> str:
    """Génère des conseils agricoles basés sur la météo"""

    advices = []

    # Conseils basés sur la pluie
    if precipitation > 10:
        advices.append("Fortes pluies prévues. Évitez les travaux au champ et protégez vos récoltes.")
    elif precipitation > 2:
        advices.append("Pluies modérées. Bon moment pour les semis si le sol est préparé.")
    elif precipitation > 0:
        advices.append("Légères pluies. Conditions favorables pour l'arrosage naturel.")
    else:
        advices.append("Pas de pluie prévue. Pensez à irriguer vos cultures si nécessaire.")

    # Conseils basés sur la température
    if temperature > 35:
        advices.append("Chaleur intense. Travaillez tôt le matin ou tard le soir. Hydratez-vous.")
    elif temperature > 30:
        advices.append("Température chaude. Protégez les jeunes plants du soleil direct.")
    elif temperature < 20:
        advices.append("Température fraîche. Bonnes conditions pour les cultures maraîchères.")

    # Conseils basés sur les orages
    if weather_code >= 95:
        advices.append("Orages prévus. Mettez vos outils à l'abri et évitez les zones découvertes.")

    return " ".join(advices)


async def get_all_cities_weather() -> list[dict]:
    """Récupère la météo de toutes les villes (pour le dashboard)"""
    cities = get_all_cities()
    results = []

    async with httpx.AsyncClient() as client:
        for city in cities[:10]:  # Limiter à 10 pour éviter trop de requêtes
            weather = await get_weather(city["name"])
            if weather:
                results.append(weather)

    return results
