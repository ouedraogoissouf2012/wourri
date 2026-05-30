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

    if code >= 95:
        bam = f"{city_name} kɔnɔ sanfɛla bɛ na. Aw ka aw ka dòn ni aw ka fɛnw bɛɛ lakana joona!"
        fr = f"Un orage arrive sur {city_name}. Mettez à l'abri vos grains et affaires immédiatement !"
    elif code >= 61 or precip > 5:
        bam = f"{city_name} kɔnɔ sanji bɛ na. Aw ka aw ka dòn ni aw ka fɛnw lakana, sanji bɛ se ka u bɔsi. Foro labɛnni waati ye sisan ye!"
        fr = f"La pluie arrive sur {city_name}. Protégez vos grains et affaires. C'est le moment de préparer le champ !"
    elif code >= 51 or precip > 0:
        bam = f"{city_name} kɔnɔ sanji fɛrɛn bɛ na. Sɛnɛ daminɛ waati ɲuman ye sisan ye."
        fr = f"Légère pluie sur {city_name}. C'est un bon moment pour commencer les semis."
    elif code == 3:
        bam = f"{city_name} kɔnɔ sankolo bɛ fara. Sanji bɛ se ka na. Aw ka foro labɛn sisan."
        fr = f"Ciel couvert sur {city_name}. La pluie peut venir. Préparez votre champ maintenant."
    elif temp > 33:
        bam = f"{city_name} kɔnɔ tile ka jugu, sanji tɛ. Aw ka aw ka sɛnɛ kalan dɔn kosɛbɛ ani aw yɛrɛw lakana tile la."
        fr = f"Chaleur intense sur {city_name}, pas de pluie. Irriguez bien vos cultures et protégez-vous du soleil."
    else:
        bam = f"{city_name} kɔnɔ tile bɛ ɲɛ, sanji tɛ sisan. Aw ka aw ka sɛnɛ kalan dɔn ni ji."
        fr = f"Ciel dégagé sur {city_name}, pas de pluie. Pensez à arroser vos cultures."

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
