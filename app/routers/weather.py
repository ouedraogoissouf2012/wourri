"""
WOURI - Router Météo
"""
from fastapi import APIRouter, HTTPException, Depends
from app.services.weather import get_weather, get_all_cities_weather
from app.data.cities import get_all_cities, get_city, search_cities
from app.models.schemas import WeatherData, CityInfo
from app.security import require_api_key

router = APIRouter(prefix="/api/weather", tags=["Météo"])


@router.get("/{city_name}", response_model=WeatherData, dependencies=[Depends(require_api_key)])
async def weather_by_city(city_name: str):
    """
    Récupère la météo d'une ville de Côte d'Ivoire

    - **city_name**: Nom de la ville (ex: Abidjan, Bouake, Korhogo)
    """
    weather = await get_weather(city_name)

    if not weather:
        raise HTTPException(
            status_code=404,
            detail=f"Ville '{city_name}' non trouvée. Utilisez /api/weather/cities pour la liste."
        )

    return weather


@router.get("/", response_model=list[WeatherData], dependencies=[Depends(require_api_key)])
async def weather_all():
    """Récupère la météo des principales villes"""
    return await get_all_cities_weather()


@router.get("/cities/list", response_model=list[CityInfo])
async def list_cities():
    """Liste toutes les villes disponibles (60 villes ivoiriennes)"""
    return get_all_cities()


@router.get("/cities/search/{query}", response_model=list[CityInfo])
async def search_city(query: str):
    """Recherche une ville par nom partiel"""
    results = search_cities(query)
    if not results:
        raise HTTPException(status_code=404, detail=f"Aucune ville trouvée pour '{query}'")
    return results
