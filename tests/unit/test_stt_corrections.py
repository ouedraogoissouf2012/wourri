"""
Tests des helpers STT Whisper (issues #228 + #229).

Couvre :
    - `_apply_corrections` helper (word boundary `\\b` apres issue #228)
    - `_load_corrections` helper (fichier present/absent/corrompu + lru cache)
    - `correct_agricultural_terms` wrapper
    - `correct_city_names` wrapper
    - `postprocess.is_likely_hallucination` (4 criteres)
    - `postprocess.is_likely_dioula_input` (patterns + probability)
    - Absence de faux positifs sur du francais courant
"""
from __future__ import annotations

import pytest

from app.services.stt.postprocess import (
    is_likely_dioula_input,
    is_likely_hallucination,
)
from app.services.stt_whisper import (
    _apply_corrections,
    _load_corrections,
    correct_agricultural_terms,
    correct_city_names,
)


# ─────────────────────────────────────────────────────────────────────
# Helper _apply_corrections — word boundary actif (issue #228)
# ─────────────────────────────────────────────────────────────────────


def test_apply_corrections_text_vide_retourne_vide():
    assert _apply_corrections("", {"foo": "bar"}, "test") == ""


def test_apply_corrections_corrections_vides_retourne_inchange():
    assert _apply_corrections("hello world", {}, "test") == "hello world"


def test_apply_corrections_case_insensitive():
    assert _apply_corrections("ABIJEAN va bien", {"abijean": "Abidjan"}, "ville") == "Abidjan va bien"


def test_apply_corrections_word_boundary_pas_de_substring_match():
    # Sans `\b`, "ment" matcherait dans "vraiment" → "vraiMan"
    # Avec `\b`, seul "ment" isole peut matcher.
    result = _apply_corrections("vraiment important", {"ment": "Man"}, "test")
    assert result == "vraiment important", "Substring match doit etre bloque par word boundary"


def test_apply_corrections_word_boundary_match_isole_ok():
    # "ment" isole (entre 2 word boundaries) doit toujours matcher.
    result = _apply_corrections("je vais ment quelque part", {"ment": "Man"}, "test")
    assert "Man" in result


# ─────────────────────────────────────────────────────────────────────
# correct_city_names — absence de faux positifs (issue #228)
# ─────────────────────────────────────────────────────────────────────


# Phrases francaises courantes qui declenchaient AVANT le fix #228
# des faux positifs vers "Man" (ville Cote d'Ivoire).
@pytest.mark.parametrize(
    "phrase",
    [
        "Je vais vraiment a Bouake",       # "vraiment" contient "ment"
        "Comment vas-tu",                  # "Comment" contient "ment"
        "Mont Blanc est belle",            # "Mont" matchait directement
        "Tu mens beaucoup",                # "mens" matchait directement
        "Il mene une vie tranquille",      # "mene" matchait directement (variante "mène")
        "Donne-moi la main droite",        # "main" matchait directement
        "C'est une jolie manne",           # "manne" matchait directement
        "Je m'appele Mont-Tremblant",      # cas compose, "Mont" interne
        "Maintenant je sais",              # "main" en prefixe — word boundary doit bloquer
        "Element important",               # "ment" en suffixe — word boundary doit bloquer
    ],
)
def test_correct_city_names_pas_de_faux_positif(phrase: str):
    """Apres #228, ces phrases ne doivent jamais etre transformees vers 'Man'."""
    result = correct_city_names(phrase)
    # Heuristique simple : on ne doit pas voir apparaitre "Man" en CamelCase
    # qui ne serait pas deja present dans la phrase d'entree.
    if "Man" in phrase:
        # Si Man etait deja dans l'entree, on tolere (cas rare)
        return
    assert "Man" not in result, f"FAUX POSITIF: {phrase!r} -> {result!r}"


# ─────────────────────────────────────────────────────────────────────
# correct_city_names — corrections legitimes preservees
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "input_text,expected_substring",
    [
        ("abijean est grande", "Abidjan"),
        ("bouake est belle", "Bouaké"),
        ("yamoussoukros est la capitale", "Yamoussoukro"),
        ("korogho est au nord", "Korhogo"),
    ],
)
def test_correct_city_names_corrections_legitimes(input_text: str, expected_substring: str):
    """Les corrections classiques de villes doivent toujours fonctionner."""
    assert expected_substring in correct_city_names(input_text)


# ─────────────────────────────────────────────────────────────────────
# correct_agricultural_terms — sanity check (non touche par #228)
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "input_text,expected_substring",
    [
        ("Je plante du pegole", "période"),
        ("Le paname est mur", "banane"),
        ("Le manioque pousse bien", "manioc"),
        ("J'aime le kakao", "cacao"),
    ],
)
def test_correct_agricultural_terms_corrections_courantes(
    input_text: str, expected_substring: str
):
    """Sanity check : le wrapper agricultural marche toujours apres le fix."""
    assert expected_substring in correct_agricultural_terms(input_text)


# ─────────────────────────────────────────────────────────────────────
# Edge cases
# ─────────────────────────────────────────────────────────────────────


def test_correct_city_names_texte_vide():
    assert correct_city_names("") == ""


def test_correct_agricultural_terms_texte_vide():
    assert correct_agricultural_terms("") == ""


def test_correct_city_names_aucune_correction_necessaire():
    txt = "Hello world, this is a normal text without typos"
    assert correct_city_names(txt) == txt


# ─────────────────────────────────────────────────────────────────────
# _load_corrections — chargement JSON + cache lru (issue #229)
# ─────────────────────────────────────────────────────────────────────


def test_load_corrections_fichier_present_retourne_dict_non_vide():
    """Le fichier `agriculture.json` existe en prod, le chargement marche."""
    _load_corrections.cache_clear()
    result = _load_corrections("agriculture")
    assert isinstance(result, dict)
    assert len(result) > 0
    # Entree connue du dictionnaire
    assert "pegole" in result
    assert result["pegole"] == "période"


def test_load_corrections_fichier_absent_retourne_dict_vide(caplog):
    """Si le fichier n'existe pas, retourne {} (no-op) + log warning."""
    _load_corrections.cache_clear()
    result = _load_corrections("definitely_not_a_real_correction_file_xyz")
    assert result == {}
    # Un warning doit avoir ete logge
    assert any("introuvable" in r.message for r in caplog.records if r.levelname == "WARNING")


def test_load_corrections_json_corrompu_retourne_dict_vide(tmp_path, monkeypatch, caplog):
    """Si le JSON est mal-forme, retourne {} (no-op) + log error.

    Cas decouvert pendant la review MAJOR-2 du refactor stt_whisper.py
    (PR #227) : un contributeur non-Python qui edite le JSON peut
    accidentellement le casser. Le mode degrade evite de planter
    toute la chaine de transcription.
    """
    # Creer un fichier JSON casse dans un tmp_path
    bad_dir = tmp_path / "stt_whisper_corrections"
    bad_dir.mkdir()
    (bad_dir / "bad.json").write_text("{not valid json,,", encoding="utf-8")

    # Override _CORRECTIONS_DIR pour pointer vers bad_dir
    monkeypatch.setattr("app.services.stt_whisper._CORRECTIONS_DIR", bad_dir)
    _load_corrections.cache_clear()

    result = _load_corrections("bad")
    assert result == {}
    # Un error doit avoir ete logge
    assert any("corrompu" in r.message for r in caplog.records if r.levelname == "ERROR")


def test_load_corrections_lru_cache_actif():
    """Le decorateur @lru_cache evite de relire le fichier au 2e appel."""
    _load_corrections.cache_clear()
    _load_corrections("agriculture")
    info_apres_1 = _load_corrections.cache_info()

    _load_corrections("agriculture")
    info_apres_2 = _load_corrections.cache_info()

    # Le 2e appel doit etre un cache hit
    assert info_apres_2.hits == info_apres_1.hits + 1
    # Le miss count ne doit PAS avoir augmente
    assert info_apres_2.misses == info_apres_1.misses


# ─────────────────────────────────────────────────────────────────────
# postprocess.is_likely_hallucination — 4 criteres
# ─────────────────────────────────────────────────────────────────────


def test_hallucination_texte_vide_est_hallucination():
    assert is_likely_hallucination("") is True


def test_hallucination_moins_de_2_mots_est_hallucination():
    assert is_likely_hallucination("salut") is True


def test_hallucination_caracteres_non_latin_majoritaires():
    """> 20 % de caracteres non-latin (au-dela de U+024F) -> hallucination."""
    # 14 caracteres chinois + "hello " (6 chars) = 70% non-latin
    text = "hello 你好世界你好世界你好世界你"
    assert is_likely_hallucination(text) is True


def test_hallucination_repetition_excessive():
    """Un mot qui apparait > 50 % du temps (sur > 4 mots, > 50 chars) -> hallucination."""
    # 12x "test" + 1 autre = 92 % de repetition, ~57 chars
    text = " ".join(["test"] * 12 + ["autre"])
    assert is_likely_hallucination(text) is True


def test_hallucination_pattern_connu_youtube():
    """Pattern Whisper hallucination YouTube standard (accents preserves)."""
    assert is_likely_hallucination("merci d'avoir regardé cette video") is True


def test_hallucination_pattern_connu_sous_titres():
    """Pattern hallucination 'sous-titres realises' (accents preserves)."""
    assert is_likely_hallucination("Voici les sous-titres réalisés par la communaute") is True


def test_hallucination_texte_normal_n_est_pas_hallucination():
    text = "Bonjour comment cultiver le riz cette saison ?"
    assert is_likely_hallucination(text) is False


# ─────────────────────────────────────────────────────────────────────
# postprocess.is_likely_dioula_input — patterns + probability
# ─────────────────────────────────────────────────────────────────────


def test_dioula_input_texte_vide_n_est_pas_dioula():
    """Pas de signal -> default False."""
    assert is_likely_dioula_input("") is False


def test_dioula_input_pattern_incoherent_detecte():
    """Un pattern typique de mauvaise transcription Whisper du dioula."""
    assert is_likely_dioula_input("est-ce que tu parles plus là") is True


def test_dioula_input_onomatopee_detectee():
    """Onomatopees frequentes Dioula -> hein hein, eh eh, mmh mmh."""
    assert is_likely_dioula_input("oui hein hein voila") is True


def test_dioula_input_probability_basse_seule_suffit():
    """Si lang_proba < 0.7 (et > 0), on signale meme sans pattern."""
    assert is_likely_dioula_input("texte normal sans pattern", language_probability=0.5) is True


def test_dioula_input_proba_haute_pas_de_signal():
    """Si lang_proba >= 0.7 ET pas de pattern, c'est pas dioula."""
    assert is_likely_dioula_input("Bonjour comment ca va", language_probability=0.95) is False


def test_dioula_input_proba_zero_default_sans_pattern_false():
    """language_probability=0 (default) n'enclenche pas le signal proba basse."""
    assert is_likely_dioula_input("texte normal sans pattern ni proba") is False
