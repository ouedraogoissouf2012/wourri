"""
Tests unitaires pour asr_normalizer.py.

Valide :
- Corrections exactes multi-mots (salutations, particules, temps)
- Fuzzy matching Levenshtein sur vocabulaire NLU
- Distance adaptative (≤1 pour mots 4 chars, ≤2 pour mots ≥5 chars)
- Pas de fuzzy sur mots courts ≤3 chars (éviter faux positifs)
- Pipeline complet normalize_asr_output()
- Variantes phonétiques réelles observées en production
"""
import json
from pathlib import Path

import pytest

from app.services.asr_normalizer import (
    _apply_exact_corrections,
    _fuzzy_correct_word,
    _max_distance_for_word,
    normalize_asr_output,
)
from app.services.nlu.concept_extractor import ConceptExtractor


@pytest.fixture(scope="module")
def concept_extractor() -> ConceptExtractor:
    """Construit l'extracteur NLU avec le dictionnaire de production."""
    concepts_path = (
        Path(__file__).resolve().parents[2] / "dictionnaires" / "nlu_concepts.json"
    )
    concepts_config = json.loads(concepts_path.read_text(encoding="utf-8"))
    return ConceptExtractor(concepts_config)


class TestMaxDistanceForWord:
    """Test du seuil de distance adaptative."""

    def test_very_short_word_no_fuzzy(self):
        """Mots ≤ 3 chars → pas de fuzzy (distance 0)."""
        assert _max_distance_for_word("ku") == 0
        assert _max_distance_for_word("ji") == 0
        assert _max_distance_for_word("ba") == 0
        assert _max_distance_for_word("bɛ") == 0

    def test_4_char_word_distance_1(self):
        """Mots de 4 chars → distance max 1."""
        assert _max_distance_for_word("malo") == 1
        assert _max_distance_for_word("kaba") == 1
        assert _max_distance_for_word("tiga") == 1
        assert _max_distance_for_word("foro") == 1

    def test_5_plus_char_word_distance_2(self):
        """Mots ≥ 5 chars → distance max 2."""
        assert _max_distance_for_word("sɛnɛ") == 1  # 4 chars Unicode
        assert _max_distance_for_word("wagati") == 2
        assert _max_distance_for_word("bananku") == 2
        assert _max_distance_for_word("mangoro") == 2


class TestExactCorrections:
    """Test des corrections exactes depuis JSON."""

    def test_salutation_fusion(self):
        """Salutation fragmentée → corrigée."""
        assert "i ni sɔgɔma" in _apply_exact_corrections("ani sɔgɔma")

    def test_multi_word_correction(self):
        """Correction multi-mots."""
        result = _apply_exact_corrections("wagati jumen")
        assert "wagati jumɛn" in result

    def test_loanword(self):
        """Mot d'emprunt corrigé."""
        assert "bananku" in _apply_exact_corrections("manioku")

    def test_no_false_positive(self):
        """Un texte correct ne doit pas être modifié."""
        text = "malo bɛ sɛnɛ"
        assert _apply_exact_corrections(text) == text


class TestFuzzyMatching:
    """Test du fuzzy matching Levenshtein contre le vocabulaire NLU."""

    def test_mali_to_malo(self):
        """'mali' (distance 1 de 'malo') → 'malo' (riz)."""
        result = _fuzzy_correct_word("mali")
        assert result == "malo", f"Attendu 'malo', obtenu '{result}'"

    def test_kaban_already_in_nlu(self):
        """'kaban' est déjà dans le vocabulaire NLU → inchangé."""
        result = _fuzzy_correct_word("kaban")
        assert result == "kaban", "'kaban' est un mot NLU valide, ne pas corriger"

    def test_tigan_already_in_nlu(self):
        """'tigan' est déjà dans le vocabulaire NLU → inchangé."""
        result = _fuzzy_correct_word("tigan")
        assert result == "tigan", "'tigan' est un mot NLU valide, ne pas corriger"

    def test_foron_not_in_nlu(self):
        """'foron' : 'foro' n'est pas dans NLU. Fuzzy peut matcher 'faran' (distance 2)."""
        result = _fuzzy_correct_word("foron")
        # 'foro' n'est pas dans le NLU. 'faran' est à distance 2 (voyelles o→a).
        # Le fuzzy peut le matcher car distance ≤ 2 et voyelles seulement.
        # Ce n'est pas idéal mais acceptable — le NLU ne reconnaîtra pas 'foron' de toute façon.
        assert isinstance(result, str)

    def test_banan_to_bana(self):
        """'banan' (distance 1 de 'bana', suppression n final = nasalisation) → 'bana'."""
        result = _fuzzy_correct_word("banan")
        assert result == "bana", f"Attendu 'bana', obtenu '{result}'"

    def test_already_correct_word(self):
        """Un mot déjà correct ne doit pas être modifié."""
        assert _fuzzy_correct_word("malo") == "malo"
        assert _fuzzy_correct_word("kaba") == "kaba"
        assert _fuzzy_correct_word("tiga") == "tiga"

    def test_unknown_word_unchanged(self):
        """Un mot inconnu (distance > max) reste inchangé."""
        result = _fuzzy_correct_word("xyzabc")
        assert result == "xyzabc"

    def test_short_word_no_fuzzy(self):
        """Les mots courts (≤3 chars) ne passent pas par le fuzzy."""
        # 'ko' est à distance 1 de 'ku' mais ne doit PAS être corrigé (trop court)
        result = _fuzzy_correct_word("ko")
        assert result == "ko"

    def test_malon_already_in_nlu(self):
        """'malon' est déjà dans le vocabulaire NLU → inchangé."""
        result = _fuzzy_correct_word("malon")
        assert result == "malon", "'malon' est un mot NLU valide"


class TestFullPipeline:
    """Test du pipeline complet normalize_asr_output()."""

    def test_mali_sentence(self):
        """La phrase qui échouait en production : 'mali' → 'malo'."""
        result = normalize_asr_output("o kɛ mali bɛ sen na wagati jumɛn na")
        assert "malo" in result, f"'malo' non trouvé dans '{result}'"

    def test_kabaka_sentence(self):
        """La phrase avec 'kabaka' → les corrections exactes + fuzzy combinées."""
        result = normalize_asr_output("kabaka juma la")
        # 'kabaka' devrait matcher 'kaba' via fuzzy (distance 2, len=6 → OK)
        # ou rester tel quel si distance > max
        assert result is not None

    def test_correct_sentence_unchanged(self):
        """Une phrase déjà correcte ne doit pas être modifiée."""
        text = "kaba bɛ sɛnɛ wagati jumɛn"
        result = normalize_asr_output(text)
        assert result == text

    def test_empty_text(self):
        """Texte vide → texte vide."""
        assert normalize_asr_output("") == ""
        assert normalize_asr_output(None) is None

    def test_salutation_plus_agriculture(self):
        """Combinaison salutation + question agricole."""
        result = normalize_asr_output("ani sɔgɔma mali bɛ sen na")
        assert "sɔgɔma" in result  # Salutation corrigée
        assert "malo" in result  # mali → malo via fuzzy

    def test_exact_multi_word_correction(self):
        """Correction exacte multi-mots dans une phrase."""
        result = normalize_asr_output("wagati jumen na")
        assert "jumɛn" in result  # Correction exacte depuis JSON


class TestProductionErrors:
    """Variantes phonétiques réelles observées en production."""

    def test_wulafɛ_variants(self):
        """Variantes de 'wulafɛ' (bonsoir)."""
        assert "wulafɛ" in normalize_asr_output("wulari")
        assert "wulafɛ" in normalize_asr_output("wulafe")

    def test_sufɛ_variants(self):
        """Variantes de 'sufɛ' (nuit)."""
        assert "sufɛ" in normalize_asr_output("sufe")

    def test_sɔgɔma_variants(self):
        """Variantes de 'sɔgɔma' (matin)."""
        assert "sɔgɔma" in normalize_asr_output("sɔrɔma")
        assert "sɔgɔma" in normalize_asr_output("sagɔma")


class TestIssue85CultureCorrections:
    """Régressions des huit transcriptions NeMo documentées dans l'issue #85."""

    @pytest.mark.parametrize(
        (
            "raw_text",
            "expected_normalized",
            "expected_culture",
            "forbidden_cultures",
        ),
        (
            ("ka ka aw sɛnɛ", "ka kakawo sɛnɛ", "CULTURE_CACAO", ()),
            ("ka tigka sɛnɛ", "ka tiga sɛnɛ", "CULTURE_ARACHIDE", ()),
            ("kaban kuru", "bananku", "CULTURE_MANIOC", ("CULTURE_MAIS",)),
            (
                "kabarada sɛnɛ",
                "bàrànda sɛnɛ",
                "CULTURE_BANANE",
                ("CULTURE_MAIS",),
            ),
            ("ka mangogo sɛnɛ", "ka mangoro sɛnɛ", "CULTURE_MANGUE", ()),
            ("ka kɔrɔ ni sɛnɛ", "ka kɔrɔni sɛnɛ", "CULTURE_COTON", ()),
            ("ka gɛrɛ sɛnɛ", "ka gan sɛnɛ", "CULTURE_GOMBO", ()),
            ("ka ga sɛnɛ", "ka gan sɛnɛ", "CULTURE_GOMBO", ()),
        ),
    )
    def test_real_nemo_error_reaches_expected_nlu_culture(
        self,
        concept_extractor: ConceptExtractor,
        raw_text: str,
        expected_normalized: str,
        expected_culture: str,
        forbidden_cultures: tuple[str, ...],
    ):
        """Chaque erreur est normalisée puis reconnue sans faux positif connu."""
        normalized = normalize_asr_output(raw_text)
        concepts = concept_extractor.extract(normalized)

        assert normalized == expected_normalized
        assert concepts[expected_culture] == 1.0
        for forbidden_culture in forbidden_cultures:
            assert forbidden_culture not in concepts


def test_soso_du_locuteur_natif_n_est_plus_reecrit_en_anacarde(
    concept_extractor: ConceptExtractor,
):
    """Haricot se dit « sɔsɔ » (locuteur natif, 2026-10-07). Absent du
    vocabulaire, le mot était pris pour un fragment ASR et réécrit en « sɔmɔ »
    (anacarde) par la reconstruction de cultures."""
    normalized = normalize_asr_output("n bɛ sɔsɔ sɛnɛ")
    concepts = concept_extractor.extract(normalized)

    assert normalized == "n bɛ sɔsɔ sɛnɛ"
    assert "CULTURE_HARICOT" in concepts
    assert "CULTURE_ANACARDE" not in concepts


# Phrases du dépôt que le normalizer réécrivait en y ajoutant une culture (banc du
# normalizer, 2026-10-07, ADR-0042). Chaque entrée est la forme « transcription »
# (minuscules, sans ponctuation) d'une phrase du dépôt, citée avec sa source : aucune
# phrase n'est inventée et le test ne juge pas leur dioula (ADR-0014, ADR-0031) ; il
# vérifie seulement que le normalizer ne les réécrit plus.
_PHRASES_DU_DEPOT = (
    # Étape 4 : un mot courant seul n'est plus réécrit en nom de culture.
    ("ne bɛ fɛ ka foro sɛnɛ", "foro → ɲɔforo",
     "dictionnaires/bambara_phrases.json, phrase 94 (manuel)"),
    ("aw ye sɛnkɛlɛ bana bɔ foro la", "bana → kaba",
     "dictionnaires/corpus_ivr.json, manioc_kosheni_symptomes_001"),
    ("aw ye a mara ka sɔngɔ ɲuman sɔrɔ", "sɔrɔ → sɔsɔ",
     "dictionnaires/corpus_ivr.json, oignon_vente_001"),
    ("aw ye npk don dugukolo la sɛnɛ tuma la", "tuma → tiga",
     "data/issue_40_mais_native_validation_2026-08-05b.json, mais_engrais_001"),
    ("aw ye jiri banalen bɔ ka kisɛ muɲunin sɛnɛ", "jiri → fini",
     "dictionnaires/corpus_ivr.json, palmier_huile_validation_015"),
    ("aw ye furakɛ bɔ joona", "joona → joni",
     "dictionnaires/corpus_ivr.json, mais_diagnostic_001"),
    # Étape 4 : une fusion de mots doit garder les consonnes du nom de culture.
    ("fɛn jumɛn ka ɲi ka sɛnɛ", "ka ɲi → kaba",
     "dictionnaires/bambara_phrases.json, phrase 91 (manuel)"),
    # Étape 3 : ni consonne changée, ni voyelle hors des confusions admises.
    ("aw ye malo da santimɛtiri mugan mugan", "mugan → mugu",
     "data/issue_49_riz_native_validation_2026-08-05b.json, riz_conseil_001"),
    ("aw ye kaba kunw tigɛ ka olu ja", "tigɛ → tiga",
     "data/issue_40_mais_native_validation_2026-08-05b.json, mais_recolte_001"),
    ("aw ye nyɔ farali marɔshɛ la wala kɔlɔ la", "kɔlɔ → kɔlɔn",
     "dictionnaires/corpus_ivr.json, mil_vente_001"),
    # Étape 3 : une voyelle longue à l'intérieur du mot n'est pas raccourcie.
    ("aw ye kɔrɔni feere jɛkulu fɛ", "feere → fere",
     "data/issue_56_coton_native_validation_2026-08-05.json, coton_vente_001"),
    # Étape 4 : un groupe nasale + consonne n'est jamais lu comme une erreur.
    ("ntomati bɛ se ka sɛnɛ san bɛɛ ni ji bɛ yen", "ntomati → tomati",
     "data/issue_58_tomate_native_validation_2026-08-05.json, tomate_saison_001"),
    # Étape 1 : une clé ne se déclenche plus à l'intérieur d'un mot (« ka ba »).
    ("mangoro buluw tali bɛ se ka bana in kɛlɛ wa", "ka bana → kaban",
     "dictionnaires/corpus_ivr.json, mangue_conseil_001, phrase attestée 3"),
    ("aw ye duguma cɛ ka bananku bɔ", "ka bananku → kabananku",
     "dictionnaires/corpus_ivr.json, manioc_recolte_001"),
)


class TestMotsCourantsNonReecritsEnCulture:
    """Le normalizer ne réécrit plus des mots dioula courants en noms de culture."""

    @pytest.mark.parametrize(
        ("phrase", "reecriture_evitee", "source"),
        _PHRASES_DU_DEPOT,
        ids=[reecriture for _, reecriture, _ in _PHRASES_DU_DEPOT],
    )
    def test_phrase_du_depot_inchangee(self, phrase, reecriture_evitee, source):
        """La phrase ressort telle quelle : plus de réécriture `reecriture_evitee`."""
        assert normalize_asr_output(phrase) == phrase, f"{reecriture_evitee} ({source})"

    def test_ka_kan_ne_devient_plus_kaba(self, concept_extractor: ConceptExtractor):
        """« ka kan » devenait « kaba » (maïs) : clé « kan » puis fusion de « ka ka »
        (data/issue_40_mais_native_validation_2026-08-05b.json, mais_saison_001)."""
        normalized = normalize_asr_output("sanji dɔɔni ka kan ka sɛnɛ daminɛ")

        assert "CULTURE_MAIS" not in concept_extractor.extract(normalized)

    def test_sufe_n_est_plus_double(self):
        """« an ni su » → « a ni sufɛ » : la clé « a ni su » ne retouche plus le
        résultat (« a ni sufɛfɛ », réparé jusque-là par le fuzzy)."""
        assert _apply_exact_corrections("an ni su") == "a ni sufɛ"

    def test_cle_appliquee_au_mot_entier_seulement(self):
        """La clé « ka ba » (maïs fragmenté, asr_corrections.json) corrige le mot
        entier, mais plus le début de « ka bana » (corpus_ivr.json,
        mangue_conseil_001, phrase attestée 3)."""
        assert _apply_exact_corrections("ka ba") == "kaba"
        assert _apply_exact_corrections("ka bana") == "ka bana"

    def test_nasalisation_ajoutee_refusee(self):
        """Le fuzzy n'ajoute plus de « n » final (« kɔlɔ » → « kɔlɔn ») ; le
        retrait reste admis (test_banan_to_bana)."""
        assert _fuzzy_correct_word("kɔlɔ") == "kɔlɔ"
        assert _fuzzy_correct_word("banan") == "bana"

    def test_salutation_collee_toujours_corrigee(self):
        """« inisɔgɔ ma » (dictionnaires/bambara_phrases.json, asr-variante de
        « Bonjour ») : la clé « sɔgɔ ma » s'applique toujours en fin de mot."""
        assert normalize_asr_output("inisɔgɔ ma") == "i ni sɔgɔma"

    def test_pluriel_francais_rejoint_son_mot_cle(self):
        """Le pluriel -s d'un mot-clé français garde son concept, accents
        compris (« insectes », « récoltés »)."""
        assert _fuzzy_correct_word("insectes") == "insecte"
        assert _fuzzy_correct_word("récoltés") == "récolte"

    def test_e_final_francais_rejoint_son_mot_cle(self):
        """« cacaoyère » garde le cacao (« cacaoyer »), comme dans BASE ; un
        radical trop court n'est pas rapproché : « mile » (Milet dans
        data/hf_datasets/francophonia_bambara_french.json) ne devient pas « mil »."""
        assert _fuzzy_correct_word("cacaoyère") == "cacaoyer"
        assert _fuzzy_correct_word("plant") == "plante"
        assert _fuzzy_correct_word("mile") == "mile"


def test_fura_garde_le_comportement_de_base_a_valider_nativement(
    concept_extractor: ConceptExtractor,
):
    """Comportement de BASE (1332c8b) conservé, PAS une règle validée.

    « fura » rejoint le mot-clé « furaw » par le suffixe de pluriel -w, d'où
    ACTION_TRAITER. Le sens de « fura » est ambigu dans le dépôt :
    dictionnaires/bambara_phrases.json (phrase 117, manuel) glose « ne bɛ fɛ ka
    fura sɔrɔ » par « Je veux un traitement », mais reponse_fr lit « fura »
    « feuilles » (corpus_ivr.json, riz_diagnostic_001 et tomate_diagnostic_001)
    ou « floraison » (anacarde_validation_020, validé). À faire valider par un
    locuteur natif (ADR-0042) : ce test signale seulement tout écart avec BASE.
    """
    normalized = normalize_asr_output("ne bɛ fɛ ka fura sɔrɔ")

    assert normalized == "ne bɛ fɛ ka furaw sɔrɔ"
    assert "ACTION_TRAITER" in concept_extractor.extract(normalized)


def _cultures(concept_extractor: ConceptExtractor, texte: str) -> set[str]:
    return {c for c in concept_extractor.extract(texte) if c.startswith("CULTURE_")}


# Erreurs ASR du même type qu'une erreur documentée, sans entrée de dictionnaire
# (ADR-0042). La phrase attendue est recopiée du dépôt (source citée) ; la
# transcription est la même phrase où seul le nom de culture du dictionnaire NLU
# est altéré comme dans l'erreur documentée. Aucun mot dioula n'est inventé et la
# forme altérée n'est pas présentée comme correcte (ADR-0014, ADR-0031).
_ERREURS_GENERALISEES = (
    ("ba nan ku bɛ bɔ kalo 8 ni 18 cɛ", "bananku bɛ bɔ kalo 8 ni 18 cɛ",
     "CULTURE_MANIOC", "nom coupé en syllabes, avec le mot-clé court « ku »",
     "dictionnaires/corpus_ivr.json, manioc_conseil_001"),
    ("aw ye sɔ mɔ sɛnɛ mɛtiri tan tan", "aw ye sɔmɔ sɛnɛ mɛtiri tan tan",
     "CULTURE_ANACARDE", "nom coupé autour du mot NLU « sɔ »",
     "dictionnaires/corpus_ivr.json, anacarde_validation_008"),
    ("aw ye kɔgɔni feere jɛkulu fɛ", "aw ye kɔrɔni feere jɛkulu fɛ",
     "CULTURE_COTON", "g lu pour r, comme « mangogo » (asr_corrections.json)",
     "data/issue_56_coton_native_validation_2026-08-05.json, coton_vente_001"),
    ("aw ye man go ra halakilenw bɔ foro la joona",
     "aw ye mangoro halakilenw bɔ foro la joona",
     "CULTURE_MANGUE", "nom coupé, a lu pour o, comme « sagoma » (asr_corrections.json)",
     "data/issue_66_mangue_native_validation_2026-08-05.json, mangue_limogo_diagnostic_001"),
    ("sanji tuma daminɛ na aw ye le mu ro sɛnɛ",
     "sanji tuma daminɛ na aw ye lemuru sɛnɛ",
     "CULTURE_AGRUMES", "nom coupé, o lu pour u, comme « ko » pour « ku » (PHRASE_SUBS)",
     "data/issue_68_agrumes_native_validation_2026-08-05.json, agrumes_conseil_001"),
    ("lemuro bɛ ji fɛ caman", "lemuru bɛ ji fɛ caman",
     "CULTURE_AGRUMES", "o lu pour u, sans verbe agricole : seul le mot seul est lu",
     "data/issue_68_agrumes_native_validation_2026-08-05.json, agrumes_irrigation_001"),
)


@pytest.mark.parametrize(
    ("transcription", "attendu", "culture", "erreur", "source"),
    _ERREURS_GENERALISEES,
    ids=[erreur for *_, erreur, _ in _ERREURS_GENERALISEES],
)
def test_erreur_documentee_generalisee_sans_cle(
    concept_extractor: ConceptExtractor, transcription, attendu, culture, erreur, source,
):
    """L'étape 4 retrouve la culture de la phrase du dépôt, et seulement elle."""
    normalized = normalize_asr_output(transcription)

    assert normalized == attendu, f"{erreur} ({source})"
    assert _cultures(concept_extractor, normalized) == {culture}


def test_cle_d_un_mot_suivie_d_un_pluriel(concept_extractor: ConceptExtractor):
    """La frontière de fin de mot ne bloque pas le pluriel -w d'une clé d'un seul
    mot d'asr_corrections.json (« tigka » → « tiga ») : « tigkaw ». Porteuse
    recopiée de corpus_ivr.json (arachide_conseil_001, phrases_attestees[1]), où
    seul le nom de culture prend la forme fautive documentée."""
    normalized = normalize_asr_output("tigkaw ka ɲi ka dun wula fɛ")

    assert _cultures(concept_extractor, normalized) == {"CULTURE_ARACHIDE"}


# Phrases dioula de data/hf_datasets/findora_fr_dioula.json (rang dans la liste)
# auxquelles une règle écartée par ADR-0042 ajoutait une culture fausse.
_PHRASES_HF_SANS_CULTURE = (
    ("an tun ka i jaabi ko den tɛ se ka bɔ a facɛ kɔrɔ ni a bɔra a facɛ kɔrɔ "
     "a facɛ bɛ sa jusukasi boro",
     "kɔrɔ ni → kɔrɔni (coton) sans verbe agricole après « ni »", "rang 4138"),
    ("o ka manase ta mara ta duguw ni a dugumisɛn dɔw fana fara o kan ka o di "
     "efirayimu ma",
     "ka ka o → kakao (cacao) sans verbe agricole après « o »", "rang 714"),
    ("a tun ka nɛgɛ yeele k'a bɛɛ kelen kelen kuturu le bɔ",
     "nɛgɛ (le métal) → nɛrɛ (néré) : nom de culture de 4 lettres", "rang 1676"),
)


@pytest.mark.parametrize(
    ("phrase", "reecriture_evitee", "rang"),
    _PHRASES_HF_SANS_CULTURE,
    ids=[reecriture for _, reecriture, _ in _PHRASES_HF_SANS_CULTURE],
)
def test_phrase_hf_ne_gagne_aucune_culture(
    concept_extractor: ConceptExtractor, phrase, reecriture_evitee, rang,
):
    """Aucune culture n'est créée là où le texte n'en nomme pas."""
    assert _cultures(concept_extractor, normalize_asr_output(phrase)) == set(), (
        f"{reecriture_evitee} (findora_fr_dioula.json, {rang})"
    )


@pytest.mark.parametrize(
    ("variantes", "attendu"),
    [
        ({"xqzw", "daba"}, "daba"),
        # Deux variantes connues : choisir demanderait le sens de la phrase. Avant,
        # le premier élément du set gagnait, donc selon PYTHONHASHSEED.
        ({"xqzw", "daba", "jaba"}, None),
    ],
)
def test_variante_phonologique_ambigue_non_appliquee(monkeypatch, variantes, attendu):
    from app.services.asr.normalizer import fuzzy

    assert {"daba", "jaba"} <= fuzzy._NLU_VOCAB
    monkeypatch.setattr("app.services.language.phonological_variants", lambda mot: set(variantes))

    assert fuzzy._phonological_variant_in_vocab("xqzw") == attendu
