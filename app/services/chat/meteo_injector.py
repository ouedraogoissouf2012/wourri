"""
WOURI — MeteoInjector : extraction de `chat_service.py` (refactor P2-09 PR 1/5).

Module PUR (pas d'etat persistant) qui gere :
  - `build_meteo_bambara()` : construit un message meteo + cultures de saison
    bilingue (bambara + francais) a partir des donnees weather brutes
  - `inject_meteo()` : remplace les tags `{{METEO_CONTEXTUEL}}` (bam) et
    `{{METEO_FR}}` (fr) dans une reponse IVR par la meteo reelle de la ville

Architecture : fonctions module-level (pas de classe) car aucun etat
persistant. Pattern aligne avec le refactor #233 (`tools/bambara_validator.py`)
ou les helpers sans etat sont des fonctions modules + les sources avec etat
sont des classes Source.

Refs :
  - Issue parent : #204 Sprint L item P2-09
  - PR precedente design Source ABC : #250 (refactor #233 pour reference pattern)
"""
from __future__ import annotations

from app.services.weather_conditions import classify_meteo


def build_meteo_bambara(
    weather_data: dict | None,
    city: str,
    cultures: list | None = None,
) -> tuple[str, str]:
    """Construit un message meteo + cultures de saison en bambara + francais.

    Args:
        weather_data: Donnees meteo brutes (open-meteo response) ou None.
        city: Nom de la ville (fallback si weather_data n'inclut pas le nom).
        cultures: Liste optionnelle de cultures du mois (dict avec
                  keys "bambara" et "fr"). Si fourni, ajoute une phrase
                  "Cultures de saison : X, Y".

    Returns:
        Tuple (message_bambara, message_francais). Si weather_data est None,
        retourne un message generique.
    """
    if not weather_data:
        return (
            "Aw ka aw ka foro kɔlɔsi ka waati ɲuman sɔrɔ.",
            "Surveillez votre champ et profitez du bon moment.",
        )

    code = weather_data.get("weather_code", 0)
    temp = weather_data.get("temperature", 28)
    precip = weather_data.get("precipitation", 0)
    city_name = weather_data.get("city", city)

    condition = classify_meteo(temp, precip, code)
    bam = condition.bam_template.format(city=city_name)
    fr = condition.fr_template.format(city=city_name)

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


def build_meteo_prevision(
    forecast: dict | None,
    city: str,
) -> tuple[str, str]:
    """Construit un message de PRÉVISION J+1 (bambara + français) — issue #355 T3.

    Réutilise les templates météo dioula validés nativement (process ADR-0014,
    `weather_conditions.METEO_CONDITIONS`) via `classify_meteo`. Aucune
    formulation dioula nouvelle n'est générée ici : le bambara sort tel quel des
    templates attestés.

    Dette tracée (issue #355 T5/T6, validation native requise) : les templates
    dioula sont au présent (« sanji bɛ na »). L'audio dioula décrit donc la
    condition de demain SANS marqueur explicite « sini » (demain) — cette
    formulation prévisionnelle en dioula doit être produite par un locuteur
    natif. Le texte FR, lui, dit explicitement « Demain » (le français est
    librement composable, hors périmètre ADR-0014).

    Args:
        forecast: Dict de prévision J+1 (retour de
                  `weather.get_weather_forecast_tomorrow`) ou None.
        city: Nom de la ville (fallback si `forecast` n'inclut pas le nom).

    Returns:
        Tuple (message_bambara, message_francais). Si `forecast` est None,
        retourne le message générique (identique à `build_meteo_bambara`).
    """
    if not forecast:
        return (
            "Aw ka aw ka foro kɔlɔsi ka waati ɲuman sɔrɔ.",
            "Surveillez votre champ et profitez du bon moment.",
        )

    # Robustesse : Open-Meteo peut renvoyer null (ex. precipitation_probability_max
    # absente pour certains modèles) → la valeur arrive à None, pas au défaut de
    # .get(). On coalesce vers des valeurs sûres pour ne pas crasher classify_meteo
    # (None > 5) ni round(None), ce qui ferait tomber toute la requête en erreur
    # générique. Les températures gardent un défaut typé (0°C absent en zone CI).
    code = forecast.get("weather_code") or 0
    temp_max = forecast.get("temperature_max")
    temp_max = temp_max if temp_max is not None else 28
    temp_min = forecast.get("temperature_min")
    temp_min = temp_min if temp_min is not None else temp_max
    precip_mm = forecast.get("precipitation_mm") or 0
    proba = forecast.get("precipitation_probability") or 0
    city_name = forecast.get("city") or city

    # classify_meteo raisonne en mm (précip = quantité, pas la probabilité %).
    condition = classify_meteo(temp_max, precip_mm, code)
    bam = condition.bam_template.format(city=city_name)
    # FR : préfixe « Demain » explicite + fenêtre quantitative (prudence :
    # PROBABILITÉ de pluie, pas certitude — cf. point de vigilance #355).
    fr = (
        f"Demain — {condition.fr_template.format(city=city_name)} "
        f"Prévision : {round(temp_min)}–{round(temp_max)}°C, "
        f"probabilité de pluie {round(proba)}%."
    )
    return (bam, fr)


def inject_meteo(
    ivr_bambara: str,
    ivr_fr: str,
    weather_data: dict | None,
    city: str,
) -> tuple[str, str]:
    """Remplace les tags meteo dans une reponse IVR par la meteo reelle.

    Tags supportes :
      - `{{METEO_CONTEXTUEL}}` dans la version bambara
      - `{{METEO_FR}}` dans la version francaise

    Court-circuit : si aucun tag n'est present dans aucune des 2 versions,
    retourne les chaines inchangees sans appeler `get_cultures_du_mois()`.
    Ce court-circuit evite un import + appel inutile pour les ~80% de reponses
    IVR sans contexte meteo.

    Args:
        ivr_bambara: Reponse IVR bambara (peut contenir `{{METEO_CONTEXTUEL}}`).
        ivr_fr: Reponse IVR francaise (peut contenir `{{METEO_FR}}`).
        weather_data: Donnees meteo brutes (open-meteo response) ou None.
        city: Nom de la ville pour les cultures de saison + fallback affichage.

    Returns:
        Tuple (bambara, fr) avec tags remplaces (ou inchanges si pas de tag).
    """
    has_bam_tag = "{{METEO_CONTEXTUEL}}" in ivr_bambara
    has_fr_tag = "{{METEO_FR}}" in ivr_fr
    if not has_bam_tag and not has_fr_tag:
        return ivr_bambara, ivr_fr

    # Import local (ne charge `app.data.calendrier_agricole` que si necessaire)
    from app.data.calendrier_agricole import get_cultures_du_mois
    try:
        cultures_saison = get_cultures_du_mois(city)
        meteo_bam, meteo_fr = build_meteo_bambara(weather_data, city, cultures_saison)
    except Exception:
        meteo_bam, meteo_fr = "", ""

    return (
        ivr_bambara.replace("{{METEO_CONTEXTUEL}}", meteo_bam),
        ivr_fr.replace("{{METEO_FR}}", meteo_fr),
    )
