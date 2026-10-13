"""
Tests des helpers extraits des god-functions de asr_normalizer.

La décomposition de _fuzzy_correct_word et _try_culture_reconstruction expose
des helpers nommés et testables isolément.
"""
from app.services.asr.normalizer.culture import _has_culture_word
from app.services.asr.normalizer.ecart import CONFUSIONS_RECONSTRUCTION, ecart_admis
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


class TestFusionDeFragments:
    """Étape 4 : aucun mot courant n'est réécrit, les fragments documentés si (ADR-0042)."""

    def test_mot_courant_seul_jamais_reecrit(self):
        # « foro » devenait « ɲɔforo » (mil) : aucune confusion documentée n'y mène.
        match, start, _, _ = _find_best_culture_fragment(["foro"])
        assert match is None
        assert start == -1

    def test_consonne_differente_refusee(self):
        # « ka ɲi » devenait « kaba » (dictionnaires/bambara_phrases.json, phrase 91).
        match, _, _, _ = _find_best_culture_fragment(["ka", "ɲi"])
        assert match is None

    def test_mot_nlu_jamais_fondu(self):
        # « bana » (maladie) est un mot NLU : « ka bana » ne devient pas « kaban ».
        match, _, _, _ = _find_best_culture_fragment(["ka", "bana"])
        assert match is None

    def test_nom_coupe_en_deux_mots_refondu(self):
        # « ti ga » en deux mots : data/issue_51_native_validation_2026-08-02.json
        # (arachide_stockage_001). La fusion redonne le mot-clé « tiga ».
        assert _find_best_culture_fragment(["ti", "ga"]) == ("tiga", 0, 2, 0)

    def test_mot_court_du_vocabulaire_fondu_si_nom_exact(self):
        # « sɔ » (ACTION_PLANTER) n'empêche plus « sɔ mɔ » de redevenir « sɔmɔ »
        # (anacarde, dictionnaires/corpus_ivr.json, anacarde_validation_008).
        assert _find_best_culture_fragment(["sɔ", "mɔ"]) == ("sɔmɔ", 0, 2, 0)


class TestErreursDocumenteesSansCle:
    """Les erreurs de l'issue #85 (tests/unit/test_asr_normalizer.py), sans leur
    entrée de asr_corrections.json : l'étape 4 les corrige seule."""

    def test_confusion_g_r_sur_un_mot_seul(self):
        # « mangogo » → « mangoro » : g lu pour r, nom de culture de 7 lettres.
        assert _find_best_culture_fragment(["ka", "mangogo", "sɛnɛ"]) == ("mangoro", 1, 2, 1)

    def test_consonne_parasite_retiree(self):
        # « tigka » → « tiga » : deux consonnes se suivent sans nasale en tête.
        assert _find_best_culture_fragment(["ka", "tigka", "sɛnɛ"]) == ("tiga", 1, 2, 1)

    def test_mot_outil_final_avant_un_verbe_agricole(self):
        # « kɔrɔ ni sɛnɛ » → « kɔrɔni sɛnɛ » : « ni » peut finir la fusion, juste
        # avant le verbe agricole.
        assert _find_best_culture_fragment(["ka", "kɔrɔ", "ni", "sɛnɛ"]) == ("kɔrɔni", 1, 3, 0)


class TestMotsCourantsProteges:
    """Garde-fous de l'étape 4, mesurés sur les jeux data/hf_datasets (ADR-0042)."""

    def test_mot_outil_final_sans_verbe_agricole_refuse(self):
        # « a facɛ kɔrɔ ni a bɔra » (findora_fr_dioula.json, rang 4138 : « S'il le
        # quitte… ») ne devient pas « kɔrɔni » (coton).
        match, _, _, _ = _find_best_culture_fragment(["a", "facɛ", "kɔrɔ", "ni", "a", "bɔra"])
        assert match is None

    def test_nom_de_quatre_lettres_exclu_du_mot_seul(self):
        # « nɛgɛ » (le métal, 114 fois dans findora_fr_dioula.json) ne devient pas
        # « nɛrɛ » (néré).
        match, _, _, _ = _find_best_culture_fragment(["nɛgɛ"])
        assert match is None

    def test_groupe_nasale_consonne_jamais_corrige(self):
        # « ntomati » (data/issue_58_tomate_native_validation_2026-08-05.json,
        # tomate_saison_001) : « nt » est un groupe dioula, pas une erreur.
        match, _, _, _ = _find_best_culture_fragment(["ntomati"])
        assert match is None


class TestDetectionCultures:
    def test_nom_francais_compte_comme_culture(self):
        # « ananas » n'est pas une cible de reconstruction mais nomme une culture
        # (dictionnaires/corpus_ivr.json, ananas_conseil_001).
        assert _has_culture_word("ananas sɛnɛ la ka ɲi kote d'ivoire la caman") is True

    def test_mot_cle_court_ne_compte_pas(self):
        # « ku » (igname) est trop court pour prouver qu'une culture est nommée :
        # « ba nan ku » doit pouvoir redevenir « bananku » (corpus_ivr.json,
        # manioc_conseil_001). Une expression qui le contient compte toujours.
        assert _has_culture_word("ba nan ku bɛ bɔ kalo 8 ni 18 cɛ") is False
        assert _has_culture_word("ku foro") is True

    def test_homographe_francais_ignore(self):
        # « mais » est aussi la conjonction française (mots_ignores du JSON).
        assert _has_culture_word("mais") is False


class TestEcartAdmis:
    def test_confusion_courante_admise(self):
        assert ecart_admis("mali", "malo") is True   # i → o (test_mali_to_malo)
        assert ecart_admis("sene", "sɛnɛ") is True   # e → ɛ

    def test_sens_non_observe_refuse(self):
        assert ecart_admis("malo", "mali") is False  # o → i

    def test_allongement_final_admis(self):
        assert ecart_admis("sanjiii", "sanji") is True
        assert ecart_admis("sɔ̀mɔɔ", "sɔ̀mɔ") is True

    def test_voyelle_longue_interieure_refusee(self):
        # « feere » (vendre) ne devient plus « fere ».
        assert ecart_admis("feere", "fere") is False

    def test_voyelle_hors_confusions_refusee(self):
        assert ecart_admis("tigɛ", "tiga") is False  # ɛ → a

    def test_consonne_ajoutee_ou_retiree_refusee(self):
        assert ecart_admis("mugan", "mugu") is False
        assert ecart_admis("fura", "furaw") is False

    def test_mot_seul_jamais_rapproche_d_une_expression(self):
        # « tila » devenait « ka tile » : l'espace compte comme une consonne.
        assert ecart_admis("tila", "ka tile") is False

    def test_confusions_de_reconstruction_reservees_a_l_etape_4(self):
        # g → r (« mangogo ») et a → ɔ (« sagɔma ») : seulement avec
        # CONFUSIONS_RECONSTRUCTION, jamais avec les confusions courantes.
        assert ecart_admis("mangogo", "mangoro") is False
        assert ecart_admis("mangogo", "mangoro", CONFUSIONS_RECONSTRUCTION) is True
        assert ecart_admis("sagɔma", "sɔgɔma") is False
        assert ecart_admis("sagɔma", "sɔgɔma", CONFUSIONS_RECONSTRUCTION) is True
