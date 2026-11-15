"""Les messages météo disent le temps, ils ne prescrivent pas un acte de production.

Règle appliquée : **garder ce qui protège, retirer ce qui prescrit un acte de
production**. Mettre sa récolte à l'abri d'un orage ou se protéger du soleil vaut
quelle que soit la culture — nous savons le dire. Semer, préparer un champ,
irriguer dépendent de la culture, du stade et de la zone : les seuils de WOURI
n'en distinguent aucun (ils ne reçoivent que température, précipitation et code
temps), et ils ne sont pas sourcés agronomiquement (dette tracée, ADR-0038 §5).

Ces tests sont des garde-fous de non-réintroduction : ils échouent si une
prescription de production revient dans un message servi.
"""
import pytest

from app.services import weather_conditions as wc

# Formulations qui prescrivent un acte de production. Volontairement larges :
# mieux vaut un test trop strict qu'une prescription qui repasse.
PRESCRIPTIONS_FR = (
    "semis", "semer", "arros", "irrig", "préparer le champ", "préparez votre champ",
    "cultures maraîchères", "jeunes plants",
)

# Mêmes prescriptions côté dioula, telles qu'elles étaient écrites.
PRESCRIPTIONS_DYU = (
    "sɛnɛ daminɛ",      # « commencer les semis »
    "foro labɛn",       # « préparer le champ »
    "sɛnɛ kalan dɔn",   # « arroser / irriguer les cultures »
)

# EXCEPTION DÉCLARÉE, à lever par le locuteur dioula.
# Dans « chaleur », la phrase dioula mêle l'irrigation et la protection solaire
# en une seule construction reliée par `ani` (« et ») :
#     « Aw ka aw ka sɛnɛ kalan dɔn kosɛbɛ ani aw yɛrɛw lakana tile la »
# La couper exigerait de RÉÉCRIRE du dioula, ce qu'interdit le process ADR-0014
# (aucune chaîne dioula modifiée sans validation native). La version française
# est corrigée ; la dioula attend la validation du locuteur.
# Cette exception doit disparaître dès que la phrase native est validée.
EXEMPTION_DIOULA = {("chaleur", "sɛnɛ kalan dɔn")}

# Ce qui PROTÈGE reste dit : ces messages doivent conserver leur consigne.
PROTECTIONS_ATTENDUES = {
    "orage": "à l'abri",
    "grosse_pluie": "protégez",
}


def _messages_fr():
    return {c.key: c.fr_template for c in wc.METEO_CONDITIONS}


def _messages_dyu():
    return {c.key: c.bam_template for c in wc.METEO_CONDITIONS}


# ------------------------------------------------------- messages du chat


@pytest.mark.parametrize("mot", PRESCRIPTIONS_FR)
def test_aucun_message_francais_ne_prescrit_un_acte_de_production(mot):
    fautifs = [k for k, t in _messages_fr().items() if mot in t.lower()]
    assert fautifs == [], f"« {mot} » prescrit un acte de production, trouvé dans : {fautifs}"


@pytest.mark.parametrize("mot", PRESCRIPTIONS_DYU)
def test_aucun_message_dioula_ne_prescrit_un_acte_de_production(mot):
    fautifs = [k for k, t in _messages_dyu().items()
               if mot in t.lower() and (k, mot) not in EXEMPTION_DIOULA]
    assert fautifs == [], f"« {mot} » prescrit un acte de production, trouvé dans : {fautifs}"


def test_l_exception_dioula_est_encore_reelle():
    """Si le locuteur a validé la phrase, l'exception doit être retirée d'ici.

    Ce test échoue le jour où la prescription disparaît du dioula : c'est le
    rappel qu'il faut alors supprimer `EXEMPTION_DIOULA`, et non le laisser
    masquer silencieusement un garde-fou devenu inutile.
    """
    for cle, mot in EXEMPTION_DIOULA:
        assert mot in _messages_dyu()[cle].lower(), (
            f"« {mot} » a disparu de « {cle} » : retirer l'entrée de EXEMPTION_DIOULA"
        )


@pytest.mark.parametrize("cle,attendu", sorted(PROTECTIONS_ATTENDUES.items()))
def test_les_consignes_de_protection_sont_conservees(cle, attendu):
    """Retirer les prescriptions ne doit pas emporter ce qui protège l'agriculteur."""
    assert attendu in _messages_fr()[cle].lower()


def test_chaque_message_nomme_encore_la_ville_et_le_temps_qu_il_fait():
    """Un message dépouillé de sa prescription doit rester informatif."""
    for cle, texte in _messages_fr().items():
        assert "{city}" in texte, f"{cle} ne nomme plus la ville"
        assert len(texte.strip()) > 15, f"{cle} est devenu vide de sens : {texte!r}"


def test_les_deux_langues_portent_le_meme_nombre_de_phrases():
    """Garde-fou de cohérence : une phrase retirée d'un côté l'est de l'autre.

    Sans cela, un agriculteur en mode bilingue recevrait la prescription en dioula
    et sa version corrigée en français.
    """
    for c in wc.METEO_CONDITIONS:
        n_fr = c.fr_template.count(".") + c.fr_template.count("!")
        n_dyu = c.bam_template.count(".") + c.bam_template.count("!")
        assert n_fr == n_dyu, (
            f"{c.key} : {n_fr} phrase(s) en français contre {n_dyu} en dioula"
        )


# ------------------------------------------------------- conseils de l'API REST


def test_les_conseils_rest_ne_prescrivent_pas_non_plus():
    textes = ([m for _, m in wc.RAIN_ADVICE_FR]
              + [m for _, _, m in wc.TEMP_ADVICE_FR]
              + [wc.STORM_ADVICE_FR])
    for mot in PRESCRIPTIONS_FR:
        fautifs = [t for t in textes if mot in t.lower()]
        assert fautifs == [], f"« {mot} » prescrit encore, dans : {fautifs}"


def test_les_conseils_rest_gardent_leurs_consignes_de_protection():
    assert "à l'abri" in wc.STORM_ADVICE_FR.lower()
    fortes_pluies = wc.RAIN_ADVICE_FR[0][1].lower()
    assert "protégez vos récoltes" in fortes_pluies
    chaleur = wc.TEMP_ADVICE_FR[0][2].lower()
    assert "hydratez-vous" in chaleur


# ------------------------------------------------------- la classification ne change pas


def test_la_classification_reste_identique():
    """La correction porte sur les TEXTES, jamais sur les seuils ni l'ordre.

    Les seuils restent non sourcés (ADR-0038 §5) : les modifier sans validation
    agronomique remplacerait un défaut par un autre.
    """
    assert [c.key for c in wc.METEO_CONDITIONS] == [
        "orage", "grosse_pluie", "pluie_legere", "couvert", "chaleur", "degage",
    ]
    assert wc.classify_meteo(28.0, 0.0, 95).key == "orage"
    assert wc.classify_meteo(28.0, 12.0, 61).key == "grosse_pluie"
    assert wc.classify_meteo(28.0, 0.5, 51).key == "pluie_legere"
    assert wc.classify_meteo(28.0, 0.0, 3).key == "couvert"
    assert wc.classify_meteo(40.0, 0.0, 0).key == "chaleur"
    assert wc.classify_meteo(25.0, 0.0, 0).key == "degage"
