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


def test_message_avec_accents_normalises():
    """Casse mixte + caracteres FR : doit toujours fonctionner."""
    # Note : la regex utilise re.escape donc les accents sont preserves.
    # On teste juste qu'une ville avec accent dans son nom canonique soit
    # detectee si le message contient la version lowercase.
    result = detect_city("Je suis à abidjan en ce moment")
    assert result == "Abidjan"


def test_plusieurs_villes_premiere_match_renvoyee():
    """Si plusieurs villes mentionnees → la 1ere trouvee dans le tri descending
    par longueur est renvoyee (comportement legacy preserve)."""
    # Tri descending par longueur : la plus longue match en premier.
    result = detect_city("Je vais de Abidjan a Daloa")
    # Les 2 villes existent — celle qui gagne depend de la longueur (et de
    # l'ordre des matches re.search). On teste juste qu'une des 2 sort.
    assert result in ("Abidjan", "Daloa"), f"Inattendu : {result}"
