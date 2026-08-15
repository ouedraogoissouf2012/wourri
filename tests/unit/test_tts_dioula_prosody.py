"""
Tests de caractérisation (golden) pour la prosodie/segmentation TTS Dioula.

Capturent le comportement de _split_sentences, _get_speaking_rate,
_split_on_bambara_markers et _force_split_long tel qu'il existait inline dans
tts_dioula.py avant l'extraction. Sorties capturées sur le code d'origine.
"""
import pytest

from app.services.tts_dioula_prosody import (
    _split_sentences,
    _get_speaking_rate,
    _split_on_bambara_markers,
    _force_split_long,
)


class TestSplitSentences:
    def test_deux_phrases_fin_de_phrase(self):
        assert _split_sentences("Aw ni ce. Malo sɛnɛ ka ɲi kosɛbɛ.") == [
            ("Aw ni ce.", 0.45),
            ("Malo sɛnɛ ka ɲi kosɛbɛ.", 0.45),
        ]

    def test_virgules_et_marqueur_nka(self):
        assert _split_sentences(
            "I ka foro labɛn, nka a kana ban, fɔlɔ i ka dugukolo labɛn ka ɲɛ."
        ) == [
            ("I ka foro labɛn", 0.2),
            ("nka a kana ban", 0.2),
            ("fɔlɔ i ka dugukolo labɛn ka ɲɛ.", 0.45),
        ]

    def test_segment_sans_ponctuation_finale(self):
        assert _split_sentences("NPK nɔgɔ ka ɲi kosɛbɛ") == [("NPK nɔgɔ ka ɲi kosɛbɛ", 0.4)]

    def test_templates_supprimes(self):
        # {{template}} retiré, laissant un double espace (comportement historique)
        assert _split_sentences("Sɛnɛ ka ɲi {{template}} tuma bɛɛ.") == [
            ("Sɛnɛ ka ɲi  tuma bɛɛ.", 0.45),
        ]

    def test_texte_vide(self):
        assert _split_sentences("") == []

    def test_decoupage_force_segment_long(self):
        # 23 tokens d'une lettre → coupé en deux (max_words=20 par défaut)
        segs = _split_sentences("a b c d e f g h i j k l m n o p q r s t u v w")
        assert segs == [
            ("a b c d e f g h i j k", 0.3),
            ("l m n o p q r s t u v w", 0.4),
        ]


class TestGetSpeakingRate:
    def test_salutation_rate_lent(self):
        assert _get_speaking_rate("Aw ni sɔgɔma") == 1.05

    def test_technique_rate_tres_lent(self):
        assert _get_speaking_rate("NPK nɔgɔ ka ɲi kosɛbɛ") == 1.25

    def test_conseil_defaut(self):
        assert _get_speaking_rate("Malo sɛnɛ ka ɲi") == 1.15

    def test_exclamation_courte_rate_lent(self):
        assert _get_speaking_rate("Aw ni ce!") == 1.05


class TestSplitOnBambaraMarkers:
    def test_decoupe_sur_nka_si_4_mots_de_chaque_cote(self):
        assert _split_on_bambara_markers(
            "i ka foro labɛn kosɛbɛ nka a kana ban abada tugun"
        ) == [
            ("i ka foro labɛn kosɛbɛ", 0.3),
            ("nka a kana ban abada tugun", 0.0),
        ]

    def test_pas_de_decoupe_si_fragment_trop_court(self):
        # "nka a" < 4 mots après le marqueur → pas de découpe
        result = _split_on_bambara_markers("i ka foro labɛn nka a")
        assert result == [("i ka foro labɛn nka a", 0.0)]


class TestForceSplitLong:
    def test_coupe_en_deux_au_dela_du_seuil(self):
        assert _force_split_long("un deux trois quatre cinq six sept huit", 0.45, max_words=4) == [
            ("un deux trois quatre", 0.3),
            ("cinq six sept huit", 0.45),
        ]

    def test_pas_de_coupe_sous_le_seuil(self):
        assert _force_split_long("un deux trois", 0.45, max_words=20) == [("un deux trois", 0.45)]
