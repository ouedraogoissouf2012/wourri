"""
Tests de caractérisation (golden) pour le pipeline texte TTS Bambara.

Capturent le comportement de clean_bambara_text (et de ses 4 étapes) ainsi que
du prétraitement français, tel qu'il existait inline dans tts_bambara.py avant
la modularisation. Les sorties attendues ont été capturées sur le code d'origine.
"""
import pytest

from app.services.tts_bambara_text import (
    clean_bambara_text,
    fix_nllb_errors,
    preprocess_french_text,
    split_into_sentences,
    protect_city_names,
    restore_city_names,
)


# Sorties capturées sur le clean_bambara_text d'origine (avant scission).
GOLDEN_CLEAN = [
    ("", ""),
    ("malo", "malo"),                                   # < 2 mots -> tel quel, PAS de "."
    ("malo malo", "malo."),                             # dédup consécutif + ponctuation
    ("malo malo sɛnɛ", "malo sɛnɛ."),
    ("ka bo ka bo ka bo", "ka bo."),                    # dédup bi-gram
    ("i ka malo sɛnɛ i ka malo sɛnɛ",
     "i ka malo sɛnɛ i ka malo sɛnɛ."),                 # 4-gram NON dédupliqué (limite bi/tri)
    ("a a a a a a a a a a", "a."),
    ("wari sɛnɛ ka ɲi", "malo sɛnɛ ka ɲi."),            # fix NLLB wari->malo
    ("Aw ye malo sɛnɛ kosɛbɛ", "Aw ye malo sɛnɛ kosɛbɛ."),
    ("ka taa ka taa ka na ka na ka taa ka taa", "ka taa ka na ka taa."),
    ("foo bar foo bar baz qux foo bar foo bar", "foo bar baz qux foo bar."),
]


@pytest.mark.parametrize(("entree", "attendu"), GOLDEN_CLEAN)
def test_clean_bambara_text_golden(entree, attendu):
    assert clean_bambara_text(entree) == attendu


class TestCleanBambaraInvariants:
    def test_texte_un_seul_mot_pas_de_ponctuation_ajoutee(self):
        # Garde historique : < 2 mots renvoyé tel quel (sans étape 4)
        assert clean_bambara_text("malo") == "malo"

    def test_texte_vide_retourne_vide(self):
        assert clean_bambara_text("") == ""

    def test_ponctuation_finale_preservee(self):
        # Un texte finissant déjà par "!" ne reçoit pas de "."
        assert clean_bambara_text("malo sɛnɛ !").endswith("!")


class TestFixNllbErrors:
    def test_wari_devient_malo(self):
        assert fix_nllb_errors("wari sɛnɛ") == "malo sɛnɛ"

    def test_texte_sans_erreur_inchange(self):
        assert fix_nllb_errors("malo ka ɲi") == "malo ka ɲi"

    def test_vide(self):
        assert fix_nllb_errors("") == ""


class TestPreprocessFrenchText:
    def test_supprime_parentheses(self):
        assert preprocess_french_text("riz (variété locale) bon") == "riz bon"

    def test_degres_celsius(self):
        assert "degrés" in preprocess_french_text("il fait 25°C")

    def test_normalise_espaces(self):
        assert preprocess_french_text("a    b   c") == "a b c"

    def test_decimales_simplifiees(self):
        # "12.5" -> "12"
        assert preprocess_french_text("pluie 12.5 mm") == "pluie 12 mm"

    def test_vide(self):
        assert preprocess_french_text("") == ""


class TestSplitIntoSentences:
    def test_separe_sur_ponctuation_finale(self):
        assert split_into_sentences("Il pleut. Le riz pousse.") == ["Il pleut.", "Le riz pousse."]

    def test_phrase_longue_coupee_sur_virgules(self):
        longue = "a" * 40 + ", " + "b" * 45
        parts = split_into_sentences(longue)
        assert len(parts) == 2

    def test_vide(self):
        assert split_into_sentences("") == []


class TestCityProtection:
    def test_protege_puis_restaure_roundtrip(self):
        text = "Le temps à Bouake est bon"
        protected, city_map = protect_city_names(text)
        assert "Bouake" not in protected  # remplacé par placeholder
        assert city_map  # au moins une ville protégée
        restored = restore_city_names(protected, city_map)
        assert restored == text

    def test_aucune_ville_map_vide(self):
        protected, city_map = protect_city_names("un texte sans ville connue xyz")
        assert city_map == {}
