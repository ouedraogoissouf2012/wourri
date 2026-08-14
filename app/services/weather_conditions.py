"""
WOURI — Source de vérité unique pour les textes/seuils météo (issue #356).

Regroupe les deux logiques de conseil météo qui existaient dupliquées :
  - Classification EXCLUSIVE (une seule condition retenue par priorité) :
    utilisée par le chat (`meteo_injector.build_meteo_bambara`), messages
    narratifs bambara + français. Le texte bambara est validé nativement
    (process ADR-0014) — NE PAS modifier une chaîne bam sans re-validation.
  - Conseils CUMULABLES (pluie + température + orage évalués indépendamment) :
    utilisés par l'API REST (`weather.generate_farming_advice`), français
    uniquement.

Ce ne sont pas deux traductions du même verdict : les seuils et la
sémantique (exclusif vs cumulable) diffèrent réellement (cf. issue #356).
Ce module centralise les DEUX pour qu'il n'existe plus qu'un seul endroit
où lire/modifier un texte ou un seuil météo, sans forcer une fusion des
deux logiques qui casserait soit le dioula validé, soit le comportement
actuel de l'API REST.

Issue #357 (conversion météo en langage simple, dioula+FR uniquement pour
ce lot) : `MeteoCondition.bam_template`/`fr_template` EST la table
condition → message par langue demandée. Anglais (ADR-0015 EnglishHandler,
DeepSeek direct sans cascade IVR) et les 6 autres langues ivoiriennes
déclarées dans `SUPPORTED_LANGUAGES` restent hors périmètre de ce lot —
décision explicite, pas un oubli. Ajouter une langue = ajouter un champ
`{lang}_template` à `MeteoCondition` (pas de moteur de règles générique
tant qu'une 3e langue n'est pas réellement demandée).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class MeteoCondition:
    key: str
    predicate: Callable[[float, float, int], bool]  # (temp, precip, code) -> bool
    bam_template: str
    fr_template: str


# Cascade exclusive : évaluée dans l'ordre, la première condition qui
# matche gagne. Ordre identique à l'ancien if/elif de build_meteo_bambara —
# ne pas réordonner sans revalider le comportement.
# Textes bambara copiés à l'identique (process ADR-0014, dioula validé).
METEO_CONDITIONS: list[MeteoCondition] = [
    MeteoCondition(
        "orage",
        lambda temp, precip, code: code >= 95,
        "{city} kɔnɔ sanfɛla bɛ na. Aw ka aw ka dòn ni aw ka fɛnw bɛɛ lakana joona!",
        "Un orage arrive sur {city}. Mettez à l'abri vos grains et affaires immédiatement !",
    ),
    MeteoCondition(
        "grosse_pluie",
        lambda temp, precip, code: code >= 61 or precip > 5,
        "{city} kɔnɔ sanji bɛ na. Aw ka aw ka dòn ni aw ka fɛnw lakana, sanji bɛ se ka u bɔsi. Foro labɛnni waati ye sisan ye!",
        "La pluie arrive sur {city}. Protégez vos grains et affaires. C'est le moment de préparer le champ !",
    ),
    MeteoCondition(
        "pluie_legere",
        lambda temp, precip, code: code >= 51 or precip > 0,
        "{city} kɔnɔ sanji fɛrɛn bɛ na. Sɛnɛ daminɛ waati ɲuman ye sisan ye.",
        "Légère pluie sur {city}. C'est un bon moment pour commencer les semis.",
    ),
    MeteoCondition(
        "couvert",
        lambda temp, precip, code: code == 3,
        "{city} kɔnɔ sankolo bɛ fara. Sanji bɛ se ka na. Aw ka foro labɛn sisan.",
        "Ciel couvert sur {city}. La pluie peut venir. Préparez votre champ maintenant.",
    ),
    MeteoCondition(
        "chaleur",
        lambda temp, precip, code: temp > 33,
        "{city} kɔnɔ tile ka jugu, sanji tɛ. Aw ka aw ka sɛnɛ kalan dɔn kosɛbɛ ani aw yɛrɛw lakana tile la.",
        "Chaleur intense sur {city}, pas de pluie. Irriguez bien vos cultures et protégez-vous du soleil.",
    ),
    MeteoCondition(
        "degage",
        lambda temp, precip, code: True,
        "{city} kɔnɔ tile bɛ ɲɛ, sanji tɛ sisan. Aw ka aw ka sɛnɛ kalan dɔn ni ji.",
        "Ciel dégagé sur {city}, pas de pluie. Pensez à arroser vos cultures.",
    ),
]


def classify_meteo(temperature: float, precipitation: float, weather_code: int) -> MeteoCondition:
    """Retourne la première condition exclusive qui matche (cascade priorisée)."""
    for condition in METEO_CONDITIONS:
        if condition.predicate(temperature, precipitation, weather_code):
            return condition
    return METEO_CONDITIONS[-1]  # inatteignable ("degage" est toujours vrai)


# ── Conseils cumulables FR (API REST) — axes indépendants, seuils propres ──
# Copiés à l'identique depuis l'ancien generate_farming_advice (weather.py).
RAIN_ADVICE_FR: list[tuple[float | None, str]] = [
    (10, "Fortes pluies prévues. Évitez les travaux au champ et protégez vos récoltes."),
    (2, "Pluies modérées. Bon moment pour les semis si le sol est préparé."),
    (0, "Légères pluies. Conditions favorables pour l'arrosage naturel."),
    (None, "Pas de pluie prévue. Pensez à irriguer vos cultures si nécessaire."),
]

TEMP_ADVICE_FR: list[tuple[str, float | None, str]] = [
    ("gt", 35, "Chaleur intense. Travaillez tôt le matin ou tard le soir. Hydratez-vous."),
    ("gt", 30, "Température chaude. Protégez les jeunes plants du soleil direct."),
    ("lt", 20, "Température fraîche. Bonnes conditions pour les cultures maraîchères."),
]

STORM_ADVICE_FR = "Orages prévus. Mettez vos outils à l'abri et évitez les zones découvertes."
STORM_THRESHOLD_CODE = 95
