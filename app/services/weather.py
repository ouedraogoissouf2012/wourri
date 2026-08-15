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
from app.services.weather_conditions import (
    RAIN_ADVICE_FR,
    STORM_ADVICE_FR,
    STORM_THRESHOLD_CODE,
    TEMP_ADVICE_FR,
)

settings = get_settings()

# ========================================
# CACHE MÉTÉO - 15 minutes
# ========================================
_weather_cache = {}  # { "city_name": { "data": {...}, "timestamp": 123456 } }
_forecast_cache = {}  # { "city_name": { "data": {...}, "timestamp": 123456 } } — prévision J+1 (issue #355)
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


def _get_cached_forecast(city_name: str) -> dict | None:
    """Récupère la prévision J+1 depuis le cache si elle est encore valide."""
    city_lower = city_name.lower()
    if city_lower in _forecast_cache:
        cached = _forecast_cache[city_lower]
        if time.time() - cached["timestamp"] < CACHE_DURATION:
            return cached["data"]
    return None


def _set_cached_forecast(city_name: str, data: dict) -> None:
    """Stocke la prévision J+1 dans le cache."""
    _forecast_cache[city_name.lower()] = {"data": data, "timestamp": time.time()}

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


async def get_weather_forecast_tomorrow(city_name: str) -> dict | None:
    """Récupère la prévision météo du lendemain (J+1) via Open-Meteo (issue #355).

    Distinct de `get_weather()` (météo instantanée) : appelle le même
    endpoint `/forecast` avec le paramètre `daily` au lieu de `current`.
    Cache séparé (15 min) pour ne pas invalider le cache météo actuelle.
    """
    cached = _get_cached_forecast(city_name)
    if cached:
        return cached

    city = get_city(city_name)
    if not city:
        return None

    url = f"{settings.openmeteo_base_url}/forecast"
    params = {
        "latitude": city["lat"],
        "longitude": city["lon"],
        "daily": "precipitation_probability_max,precipitation_sum,weather_code,temperature_2m_max,temperature_2m_min",
        "timezone": "Africa/Abidjan",
        "forecast_days": 2,
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, params=params)

            if response.status_code == 200:
                data = response.json()
                daily = data.get("daily", {})

                # index 0 = aujourd'hui, index 1 = demain (forecast_days=2)
                times = daily.get("time", [])
                if len(times) < 2:
                    return None

                weather_code = daily.get("weather_code", [0, 0])[1]
                temp_max = daily.get("temperature_2m_max", [0, 0])[1]
                temp_min = daily.get("temperature_2m_min", [0, 0])[1]
                precip_proba = daily.get("precipitation_probability_max", [0, 0])[1]
                # precipitation_sum = cumul en mm (quantité), distinct de la
                # probabilité %. Nécessaire pour classify_meteo qui raisonne en
                # mm (issue #355 T3 : conseil agronomique qualitatif).
                precip_mm = daily.get("precipitation_sum", [0, 0])[1]

                result = {
                    "city": city["name"],
                    "region": city["region"],
                    "date": times[1],
                    "temperature_max": temp_max,
                    "temperature_min": temp_min,
                    "precipitation_probability": precip_proba,
                    "precipitation_mm": precip_mm,
                    "weather_code": weather_code,
                    "weather_description": WEATHER_CODES.get(weather_code, "Inconnu"),
                }

                _set_cached_forecast(city_name, result)
                return result

    except Exception as e:
        logger.error(f"[MÉTÉO] Erreur API prévision J+1: {e}")
        return None

    return None


def generate_farming_advice(temperature: float, precipitation: float, weather_code: int) -> str:
    """Génère des conseils agricoles basés sur la météo (axes cumulables : pluie, température, orage)"""

    advices = []

    # Conseils basés sur la pluie
    for threshold, message in RAIN_ADVICE_FR:
        if threshold is None or precipitation > threshold:
            advices.append(message)
            break

    # Conseils basés sur la température
    for comparator, threshold, message in TEMP_ADVICE_FR:
        if (comparator == "gt" and temperature > threshold) or (
            comparator == "lt" and temperature < threshold
        ):
            advices.append(message)
            break

    # Conseils basés sur les orages
    if weather_code >= STORM_THRESHOLD_CODE:
        advices.append(STORM_ADVICE_FR)

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
