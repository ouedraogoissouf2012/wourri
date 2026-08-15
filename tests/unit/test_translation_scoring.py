"""
Tests de caractérisation pour le module de scoring de traduction.

Capturent le comportement de `pick_best_translation` et `_is_grammar_annotation`
tel qu'il existait inline dans word_translator.py avant l'extraction, pour
garantir l'absence de régression lors de la modularisation.
"""
from app.services.translation.translation_scoring import (
    pick_best_translation,
    _is_grammar_annotation,
)


class TestIsGrammarAnnotation:
    def test_tag_exact_est_annotation(self):
        assert _is_grammar_annotation("1sg") is True
        assert _is_grammar_annotation("REFL") is True  # via _GRAMMAR_TAGS lower + casesensitive
        assert _is_grammar_annotation("nom") is True

    def test_all_caps_abreviation_case_sensitive(self):
        # ^[A-Z0-9.]+$ ne matche que les ALL CAPS
        assert _is_grammar_annotation("IPFV.AFF") is True
        assert _is_grammar_annotation("3PL") is True

    def test_pattern_technique_bamadaba(self):
        assert _is_grammar_annotation("marqueur predicatif") is True
        assert _is_grammar_annotation("postposition") is True
        assert _is_grammar_annotation("sens de futur") is True

    def test_mot_normal_pas_annotation(self):
        assert _is_grammar_annotation("riz") is False
        assert _is_grammar_annotation("cultiver") is False
        assert _is_grammar_annotation("maïs") is False


class TestPickBestTranslation:
    def test_liste_vide_retourne_vide(self):
        assert pick_best_translation([]) == ""

    def test_candidat_unique_normal(self):
        assert pick_best_translation(["riz"]) == "riz"

    def test_candidat_unique_annotation_retourne_vide(self):
        assert pick_best_translation(["1sg"]) == ""
        assert pick_best_translation(["IPFV.AFF"]) == ""

    def test_candidat_unique_points_composites_nettoyes(self):
        # "homme.etonnant" -> "homme etonnant" (point non final remplacé par espace)
        assert pick_best_translation(["homme.etonnant"]) == "homme etonnant"

    def test_bonus_agricole_prefere(self):
        # "riz" (agricole, +30) doit battre "chose" (générique)
        assert pick_best_translation(["chose truc machin", "riz"]) == "riz"

    def test_penalise_tag_grammatical_parmi_candidats(self):
        # "3sg" est un tag (-500) ; "manger" gagne
        assert pick_best_translation(["3sg", "manger"]) == "manger"

    def test_penalise_description_technique(self):
        # "marqueur predicatif" pénalisé (-200) ; "faire" gagne
        assert pick_best_translation(["marqueur predicatif", "faire"]) == "faire"

    def test_prefere_court_sur_long(self):
        court = "eau"
        longue = "liquide transparent que l'on boit habituellement"
        assert pick_best_translation([longue, court]) == court

    def test_tous_annotations_retourne_vide(self):
        # Tous les candidats sont des tags/patterns → score <= -200 → ""
        assert pick_best_translation(["1sg", "IPFV.AFF", "3pl"]) == ""

    def test_penalise_double_tiret_reference_interne(self):
        assert pick_best_translation(["devant -- voir", "sous"]) == "sous"

    def test_points_composites_nettoyes_sur_meilleur(self):
        # Le meilleur candidat "peigne.de.tisserand" est nettoyé en sortie
        result = pick_best_translation(["peigne.de.tisserand", "outil de tissage long descriptif ici"])
        assert "." not in result
