"""
Tests pour `app/services/chat/city_detector.py` (refactor P2-09 PR 2/5).

Couvre :
    - Detection ville simple ("Je suis a Abidjan" → Abidjan)
    - Word boundary anti-faux-positif ("manioc" ne match pas "Man")
    - Priorite aux noms longs ("San Pedro" gagne sur "San" si les 2 existent)
    - Casse insensible ("ABIDJAN", "abidjan", "Abidjan")
    - Aucune ville → None
    - Texte vide → None

Module PUR (fonction module-level, pas d'etat). Tests simples sans mocking.
"""
from __future__ import annotations

import pytest

from app.services.chat.city_detector import detect_city


def test_detect_abidjan_dans_phrase():
    """Cas nominal : ville reconnue dans une phrase."""
    assert detect_city("Je suis à Abidjan ce matin") == "Abidjan"


def test_detect_korhogo_avec_question():
    """Variante : forme question."""
    assert detect_city("Quelle est la météo à Korhogo ?") == "Korhogo"


def test_aucune_ville_retourne_none():
    """Texte sans ville reconnue → None (pas de fallback dans CE module)."""
    assert detect_city("Bonjour, comment planter du riz ?") is None


def test_texte_vide_retourne_none():
    """Edge case : message vide."""
    assert detect_city("") is None


def test_casse_insensible():
    """La detection ne depend pas de la casse."""
    assert detect_city("je suis à ABIDJAN") == "Abidjan"
    assert detect_city("ville: abidjan") == "Abidjan"
    assert detect_city("Abidjan c'est bien") == "Abidjan"


def test_word_boundary_manioc_ne_match_pas_man():
    """`Man` ne doit pas matcher dans `manioc` (collision substring evitee)."""
    # "Man" est une ville reconnue (sous-prefecture en CI), mais "manioc" ne
    # doit PAS la matcher. Pattern aligne avec city_resolver whatsapp-server PR #199.
    result = detect_city("Je veux planter du manioc")
    assert result != "Man", f"Faux positif : '{result}' au lieu de None"


def test_word_boundary_comment_ne_match_pas_ment_ou_man():
    """'comment' ne doit matcher ni 'ment' ni 'Man' (collisions classiques)."""
    result = detect_city("Comment allez-vous ?")
    assert result is None, f"Faux positif sur 'Comment' : {result}"


def test_word_boundary_main_ne_match_pas_dans_main():
    """'main' (mot FR) ne doit pas matcher 'Man' (collision substring evitee)."""
    result = detect_city("Donne-moi la main")
    assert result != "Man"


def test_word_boundary_mont_blanc_ne_match_pas():
    """'Mont' (Mont-Blanc) ne doit pas matcher une ville CI commencant par 'Mont'."""
    # Defensive : pas de ville CI nommee "Mont", mais valide le pattern.
    result = detect_city("Le Mont-Blanc est en Europe")
    assert result not in ("Mont",), result


def test_priorite_aux_noms_longs():
    """Si 2 noms peuvent matcher, le plus long gagne (tri descending par longueur)."""
    # Si "Bouake" et "Boua" existaient tous 2 dans IVORIAN_CITIES, "Bouake" doit
    # gagner. Cas reel : on teste juste que la priorite est respectee si conflit.
    # "Bouake" = ville reelle, donc on verifie qu'elle est bien detectee.
    assert detect_city("La ville de Bouake est belle") == "Bouake"


def test_casse_mixte_sur_ville_sans_accent():
    """Casse mixte sur un nom sans diacritique : comportement historique.

    Renomme depuis `test_message_avec_accents_normalises` (issue #516) : ce
    test ne couvrait PAS la normalisation des accents — « Abidjan » n'en porte
    aucun, et son propre commentaire admettait que « les accents sont
    preserves ». Il passait donc sans rien prouver sur le sujet annonce.
    La vraie couverture des diacritiques est plus bas.
    """
    result = detect_city("Je suis à abidjan en ce moment")
    assert result == "Abidjan"


# ─────────────────────────────────────────────
# Repli des diacritiques (issue #516)
#
# Le referentiel melange cles accentuees (`Séguéla`, `Odienné`…) et non
# accentuees (`Bouake`…). Avant #516, `detect_city` comparait sans replier :
# un agriculteur ecrivant correctement « Bouaké » n'etait pas localise.
# ─────────────────────────────────────────────


def test_detecte_ville_ecrite_avec_accent_vers_cle_sans_accent():
    """« Bouaké » — orthographe correcte — doit resoudre vers la cle « Bouake »."""
    assert detect_city("je suis à Bouaké en ce moment") == "Bouake"


def test_detecte_ville_ecrite_sans_accent_vers_cle_accentuee():
    """Sens inverse : saisie sans accent, cle du referentiel accentuee."""
    assert detect_city("je cultive du riz a Seguela") == "Séguéla"


@pytest.mark.parametrize(
    "message, attendu",
    [
        ("la météo à Odienne aujourd'hui", "Odienné"),
        ("la météo à Odienné aujourd'hui", "Odienné"),
        ("je pars à Soubre demain", "Soubré"),
        ("je pars à SOUBRÉ demain", "Soubré"),
        ("mon champ est à Ferkessedougou", "Ferkessédougou"),
    ],
)
def test_repli_diacritiques_parametrique(message, attendu):
    """Le repli fonctionne dans les deux sens et se combine avec la casse."""
    assert detect_city(message) == attendu


def test_repli_ne_casse_pas_le_word_boundary():
    """Non-regression critique : le repli ne doit pas rouvrir les faux positifs.

    « manioc » contient « man » ; le word boundary doit continuer de proteger
    apres l'ajout du repli des diacritiques.
    """
    assert detect_city("je cultive du manioc") is None
    assert detect_city("comment planter du riz ?") is None


def test_plusieurs_villes_premiere_match_renvoyee():
    """Si plusieurs villes mentionnees → la 1ere trouvee dans le tri descending
    par longueur est renvoyee (comportement legacy preserve)."""
    # Tri descending par longueur : la plus longue match en premier.
    result = detect_city("Je vais de Abidjan a Daloa")
    # Les 2 villes existent — celle qui gagne depend de la longueur (et de
    # l'ordre des matches re.search). On teste juste qu'une des 2 sort.
    assert result in ("Abidjan", "Daloa"), f"Inattendu : {result}"
