"""
Tests des helpers extraits des god-functions de asr_normalizer.

La décomposition de _fuzzy_correct_word et _try_culture_reconstruction expose
des helpers nommés et testables isolément.
"""
from app.services.asr_normalizer import (
    _is_nasalization_only,
    _find_best_culture_fragment,
)


class TestIsNasalizationOnly:
    def test_ajout_n_final_est_nasalisation(self):
        assert _is_nasalization_only("malon", "malo") is True
        assert _is_nasalization_only("malo", "malon") is True

    def test_mots_differents_pas_nasalisation(self):
        assert _is_nasalization_only("malo", "kafe") is False

    def test_meme_longueur_pas_nasalisation(self):
        # Différence de longueur nulle → jamais une nasalisation (ajout/suppression d'un 'n')
        assert _is_nasalization_only("malo", "kalo") is False

    def test_difference_deux_caracteres_pas_nasalisation(self):
        assert _is_nasalization_only("malo", "maloon") is False


class TestFindBestCultureFragment:
    def test_aucun_mot_aucun_match(self):
        # Sur une liste vide, aucun fragment n'est trouvé.
        match, start, end, dist = _find_best_culture_fragment([])
        assert match is None
        assert start == -1

    def test_retour_est_un_quadruplet(self):
        result = _find_best_culture_fragment(["i", "ka", "sɛnɛ"])
        assert isinstance(result, tuple) and len(result) == 4
