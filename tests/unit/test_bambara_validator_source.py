"""
Tests pour l'abstraction `Source` ABC + `TfidfSource` introduite dans
`tools/bambara_validator.py` (issue #233 PR 1).

Couverture :
    - `Source` ABC non-instanciable (sanity check abstract methods)
    - `TfidfSource.load()` : fichiers presents / absents / idempotence
    - `TfidfSource.find()` : concept absent / < min_match_lignes / cas nominal
    - Cache `_global_freq` : ne recalcule pas au 2e `find()`
    - Filtres `min_global` / `min_match_lignes` : effectifs

NOTE : `tools/bambara_validator.py` est un outil OFFLINE de maintenance
corpus (deplace en PR #232). Pas dans le hot path runtime. Mais aucune
couverture de test n'existait avant cette PR — ce test fournit aussi
le filet anti-regression pour les PRs 2/3 qui finiront le refactor.
"""
from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from pathlib import Path

import pytest

# Charger le module via importlib (tools/ n'est pas un package).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT_PATH = PROJECT_ROOT / "tools" / "bambara_validator.py"
_spec = importlib.util.spec_from_file_location("bambara_validator", _SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


# ─────────────────────────────────────────────
# Source ABC — sanity check
# ─────────────────────────────────────────────


def test_source_abc_non_instanciable():
    """`Source` est une ABC : impossible d'instancier directement."""
    with pytest.raises(TypeError, match="abstract"):
        _mod.Source()


# ─────────────────────────────────────────────
# TfidfSource.load()
# ─────────────────────────────────────────────


def _make_paires(tmp_path: Path, fr_lines: list[str], dyu_lines: list[str]):
    """Cree 2 fichiers fr/dyu dans tmp_path et retourne les Path."""
    fr_path = tmp_path / "src.fr"
    dyu_path = tmp_path / "src.dyu"
    fr_path.write_text("\n".join(fr_lines) + "\n", encoding="utf-8")
    dyu_path.write_text("\n".join(dyu_lines) + "\n", encoding="utf-8")
    return fr_path, dyu_path


def test_tfidf_source_load_fichiers_presents(tmp_path):
    fr_path, dyu_path = _make_paires(
        tmp_path,
        ["je mange du riz", "il pleut"],
        ["n be malo dun", "san be na"],
    )
    src = _mod.TfidfSource(
        name="test",
        fr_path=fr_path,
        dyu_path=dyu_path,
        weight=2,
        min_global=1,
        min_match_lignes=1,
    )
    src.load()
    assert len(src._fr) == 2
    assert len(src._dyu) == 2
    assert src._loaded is True


def test_tfidf_source_load_fichiers_absents_no_op(tmp_path):
    """Fichiers absents → load() est no-op, find() renvoie Counter() vide."""
    src = _mod.TfidfSource(
        name="missing",
        fr_path=tmp_path / "nope.fr",
        dyu_path=tmp_path / "nope.dyu",
        weight=2,
        min_global=1,
        min_match_lignes=1,
    )
    src.load()
    assert src._fr == []
    assert src._dyu == []
    assert src._loaded is True  # marque comme charge meme si vide
    assert src.find("riz") == Counter()


def test_tfidf_source_load_idempotent(tmp_path):
    """Appeler load() 2 fois ne re-lit pas les fichiers."""
    fr_path, dyu_path = _make_paires(tmp_path, ["a"], ["b"])
    src = _mod.TfidfSource(
        name="idempotent",
        fr_path=fr_path,
        dyu_path=dyu_path,
        weight=1,
        min_global=1,
        min_match_lignes=1,
    )
    src.load()
    # Modifier le fichier sur disque sans appeler load() → ne change rien
    fr_path.write_text("modified\n", encoding="utf-8")
    src.load()  # 2e appel
    assert src._fr == ["a\n"], "load() idempotent : pas de re-lecture"


# ─────────────────────────────────────────────
# TfidfSource.find()
# ─────────────────────────────────────────────


def test_tfidf_find_concept_absent_du_corpus(tmp_path):
    """Concept totalement absent → Counter() vide."""
    fr_path, dyu_path = _make_paires(
        tmp_path,
        ["bonjour comment vas tu", "il fait beau aujourdhui"],
        ["ini sogoma", "tile ka di bi"],
    )
    src = _mod.TfidfSource(
        name="test",
        fr_path=fr_path,
        dyu_path=dyu_path,
        weight=2,
        min_global=1,
        min_match_lignes=1,
    )
    assert src.find("inexistant") == Counter()


def test_tfidf_find_sous_min_match_lignes(tmp_path):
    """Concept present mais < min_match_lignes → Counter() vide (peu fiable)."""
    fr_path, dyu_path = _make_paires(
        tmp_path,
        ["je mange du riz"],  # 1 seule ligne avec "riz"
        ["malo dun"],
    )
    src = _mod.TfidfSource(
        name="test",
        fr_path=fr_path,
        dyu_path=dyu_path,
        weight=2,
        min_global=1,
        min_match_lignes=3,  # exige 3 lignes
    )
    assert src.find("riz") == Counter()


def test_tfidf_find_cas_nominal_remonte_terme_specifique(tmp_path):
    """Cas nominal : un terme specifique au concept doit remonter top.

    Renforce assertion (fix review NICE-1) : `most_common(1)` au lieu de
    `in result`. Sans ca, une regression qui inverserait TF et IDF passerait
    le test (le terme parasite apparait dans le Counter mais pas en tete).
    """
    # 4 lignes avec "riz" → "malo" apparait 4 fois (specifique)
    # 4 lignes sans "riz" → "ji" (eau) apparait 4 fois (commun, IDF eleve)
    fr_lines = [
        "je mange du riz",
        "le riz est bon",
        "achete du riz",
        "le riz pousse",
        "boire de leau",
        "leau coule",
        "lhomme boit",
        "il pleut beaucoup",
    ]
    dyu_lines = [
        "malo malo",  # tres specifique a riz
        "malo ka di",
        "malo san",
        "malo bena",
        "ji minye",
        "ji bena",
        "ji minye fana",
        "san caman",
    ]
    fr_path, dyu_path = _make_paires(tmp_path, fr_lines, dyu_lines)
    src = _mod.TfidfSource(
        name="test",
        fr_path=fr_path,
        dyu_path=dyu_path,
        weight=2,
        min_global=2,
        min_match_lignes=3,
    )
    result = src.find("riz")
    assert isinstance(result, Counter)
    # Assertion FORTE : "malo" doit etre en tete du classement (le terme le
    # plus specifique au concept "riz" parmi tous les termes du corpus).
    assert result.most_common(1)[0][0] == "malo", (
        f"'malo' doit etre top-1 du TF-IDF, got: {result.most_common(3)}"
    )


def test_tfidf_find_cache_global_freq_actif(tmp_path):
    """Le cache `_global_freq` n'est calcule qu'une seule fois (2 appels successifs)."""
    fr_path, dyu_path = _make_paires(
        tmp_path,
        ["riz riz riz", "riz again", "riz here"],
        ["malo abc", "malo def", "malo ghi"],
    )
    src = _mod.TfidfSource(
        name="cache",
        fr_path=fr_path,
        dyu_path=dyu_path,
        weight=2,
        min_global=1,
        min_match_lignes=1,
    )
    src.find("riz")
    snapshot = dict(src._global_freq)
    # Modifier le cache directement pour detecter une 2e recalculation
    src._global_freq.update({"sentinelle": 42})
    src.find("riz")  # 2e appel
    # Si recalcul, la sentinelle aurait ete ecrasee. Si cache : preservee.
    assert src._global_freq.get("sentinelle") == 42, "Cache _global_freq doit etre actif"


def test_tfidf_find_filtre_min_global(tmp_path):
    """Termes apparaissant globalement < min_global sont filtres.

    Renforce assertion (fix review NICE-4) : ajoute assertion POSITIVE pour
    garantir que le Counter n'est pas vide pour d'autres raisons (exception
    silencieuse, early-return). Sans ca, une regression qui ferait crasher
    `find()` retournerait Counter() vide et le `"rare" not in result` passerait.
    """
    # "rare" apparait 1 seule fois (rare global), "commun" 4 fois
    fr_lines = ["riz un", "riz deux", "riz trois", "autre chose"]
    dyu_lines = ["rare commun", "commun seul", "commun bis", "commun ter"]
    fr_path, dyu_path = _make_paires(tmp_path, fr_lines, dyu_lines)
    src = _mod.TfidfSource(
        name="filter",
        fr_path=fr_path,
        dyu_path=dyu_path,
        weight=2,
        min_global=3,  # exige >= 3 occurrences globales
        min_match_lignes=2,
    )
    result = src.find("riz")
    # Assertion POSITIVE : "commun" (4 occ globales) doit etre present
    assert "commun" in result, (
        f"'commun' (4 occ globales) doit passer le filtre min_global=3. "
        f"Counter: {dict(result)}"
    )
    # Assertion NEGATIVE : "rare" (1 occ) doit etre filtre
    assert "rare" not in result, (
        f"min_global=3 doit filtrer 'rare' (1 occ). Counter: {dict(result)}"
    )


# ─────────────────────────────────────────────
# Contract anti-regression _bayelemabaga()
# ─────────────────────────────────────────────


def test_bayelemabaga_wrapper_appelle_tfidf_source(tmp_path, monkeypatch):
    """Verifier que `_bayelemabaga()` delegue bien a `TfidfSource.find()`.

    Sans repliquer la logique TF-IDF (qui est testee par les tests TfidfSource
    ci-dessus), on verifie que le wrapper invoque la classe et propage le
    Counter retourne.
    """
    # Forcer un TfidfSource controlle avec donnees synthetiques
    fr_path, dyu_path = _make_paires(
        tmp_path,
        ["mange du riz", "riz pousse", "riz bon"],
        ["malo dun", "malo bena", "malo ka di"],
    )
    fake_src = _mod.TfidfSource(
        name="bayelemabaga",
        fr_path=fr_path,
        dyu_path=dyu_path,
        weight=2,
        min_global=2,
        min_match_lignes=3,
    )
    monkeypatch.setattr(_mod, "_BAYELEMABAGA_SRC", fake_src)
    # Court-circuit la concatenation des splits (les paths pointent ailleurs)
    monkeypatch.setattr(_mod, "_bayelemabaga_load_all_splits", lambda: fake_src.load())

    result = _mod._bayelemabaga("riz")
    assert isinstance(result, Counter)
    assert "malo" in result, (
        f"Le wrapper _bayelemabaga doit retourner les scores de TfidfSource. "
        f"Counter: {dict(result)}"
    )


# ─────────────────────────────────────────────
# Tests scenario reel _bayelemabaga_load_all_splits (fix review MAJOR-1 tests)
# ─────────────────────────────────────────────


def _setup_bayelemabaga_splits(tmp_path: Path, monkeypatch) -> Path:
    """Cree une arborescence Bayelemabaga avec 3 splits dans tmp_path.

    train/ : 2 paires
    test/  : 2 paires
    valid/ : 2 paires
    Total apres concat : 6 paires.

    Patch `_mod.DATA_DIR` vers tmp_path, reset `_BAYELEMABAGA_SRC` pour
    forcer la re-initialisation depuis la fixture.
    """
    bayelemabaga = tmp_path / "bayelemabaga"
    splits = {
        "train": (["riz un train", "riz deux train"], ["malo a train", "malo b train"]),
        "test": (["riz un test", "riz deux test"], ["malo a test", "malo b test"]),
        "valid": (["riz un valid", "riz deux valid"], ["malo a valid", "malo b valid"]),
    }
    for split, (fr_lines, bam_lines) in splits.items():
        split_dir = bayelemabaga / split
        split_dir.mkdir(parents=True)
        (split_dir / f"{split}.fr").write_text("\n".join(fr_lines) + "\n", encoding="utf-8")
        (split_dir / f"{split}.bam").write_text("\n".join(bam_lines) + "\n", encoding="utf-8")

    monkeypatch.setattr(_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(_mod, "_BAYELEMABAGA_SRC", None)
    return tmp_path


def test_bayelemabaga_load_all_splits_concatene_les_3_splits(tmp_path, monkeypatch):
    """Scenario reel : `_bayelemabaga_load_all_splits()` doit concatener
    les 3 splits dans l'instance + invalider le cache `_global_freq`.

    Fix review MAJOR-1 tests : le contract anti-regression promis dans la
    docstring de `_bayelemabaga_load_all_splits()` doit etre verifie sur
    un scenario reel avec arborescence de splits.
    """
    _setup_bayelemabaga_splits(tmp_path, monkeypatch)

    _mod._bayelemabaga_load_all_splits()
    src = _mod._bayelemabaga_src()

    # 6 paires totales (2 par split × 3 splits)
    assert len(src._fr) == 6, f"3 splits concatenes = 6 paires, got {len(src._fr)}"
    assert len(src._dyu) == 6
    # Cache freq globale invalide apres concat (sera recalcule au prochain find())
    assert src._global_freq == Counter(), (
        "Cache _global_freq doit etre invalide apres concat splits"
    )
    # Flag idempotence positionne
    assert src._all_splits_loaded is True


def test_bayelemabaga_load_all_splits_idempotent(tmp_path, monkeypatch):
    """Fix review MAJOR-1 archi : appeler `_load_all_splits()` 2x ne doit
    PAS doubler le corpus. Sans le flag `_all_splits_loaded`, un 2e appel
    re-concatenait test/+valid/ → 10 paires au lieu de 6 → TF-IDF fausse.
    """
    _setup_bayelemabaga_splits(tmp_path, monkeypatch)

    _mod._bayelemabaga_load_all_splits()
    src = _mod._bayelemabaga_src()
    longueur_apres_1er_appel = len(src._fr)

    # 2e appel : doit etre no-op
    _mod._bayelemabaga_load_all_splits()
    assert len(src._fr) == longueur_apres_1er_appel, (
        f"Idempotence cassee : 1er appel = {longueur_apres_1er_appel} paires, "
        f"2e appel = {len(src._fr)} paires (doublement)"
    )


def test_bayelemabaga_src_fallback_sans_splits(tmp_path, monkeypatch):
    """Fix review MAJOR-2 tests : la branche fallback de `_bayelemabaga_src()`
    (aucun split present dans DATA_DIR) doit creer une instance TfidfSource
    avec paths inexistants → find() renvoie Counter() vide sans crasher.
    """
    # tmp_path est vide (pas de sous-dossier bayelemabaga/)
    monkeypatch.setattr(_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(_mod, "_BAYELEMABAGA_SRC", None)

    src = _mod._bayelemabaga_src()
    assert src is not None, "fallback doit creer une instance, pas retourner None"
    assert isinstance(src, _mod.TfidfSource)
    assert src.name == "bayelemabaga"
    # Le path pointe vers train/ par defaut (1er split tente)
    assert "train" in str(src.fr_path)
    # find() doit fonctionner sans crash (load() = no-op car fichiers absents)
    assert src.find("riz") == Counter()


# ─────────────────────────────────────────────
# Tests Koumankan + Findora (issue #233 PR 2)
# ─────────────────────────────────────────────


def test_kouman_src_cree_instance_avec_bons_parametres(tmp_path, monkeypatch):
    """`_kouman_src()` doit creer une TfidfSource avec les bons parametres
    legacy (weight=3, min_global=2, min_match_lignes=2)."""
    monkeypatch.setattr(_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(_mod, "_KOUMAN_SRC", None)

    src = _mod._kouman_src()
    assert isinstance(src, _mod.TfidfSource)
    assert src.name == "koumankan"
    assert src.weight == 3
    assert src.min_global == 2
    assert src.min_match_lignes == 2
    # Path attendu : DATA_DIR/koumankan/koumankan.{fr,dyu}
    assert "koumankan" in str(src.fr_path)


def test_koumankan_wrapper_appelle_tfidf_source(tmp_path, monkeypatch):
    """Le wrapper `_koumankan()` doit deleguer a `TfidfSource.find()`."""
    # Setup arborescence Koumankan reelle dans tmp_path
    kdir = tmp_path / "koumankan"
    kdir.mkdir()
    (kdir / "koumankan.fr").write_text(
        "le riz pousse\nje mange du riz\nriz est bon\n", encoding="utf-8"
    )
    (kdir / "koumankan.dyu").write_text(
        "malo bena\nmalo dun\nmalo ka di\n", encoding="utf-8"
    )
    monkeypatch.setattr(_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(_mod, "_KOUMAN_SRC", None)

    result = _mod._koumankan("riz")
    assert isinstance(result, Counter)
    assert "malo" in result, (
        f"_koumankan doit retourner les scores de TfidfSource. Counter: {dict(result)}"
    )


def test_findora_src_cree_instance_avec_bons_parametres(tmp_path, monkeypatch):
    """`_findora_src()` doit creer une TfidfSource avec les bons parametres
    legacy (weight=3, min_global=2, min_match_lignes=2)."""
    monkeypatch.setattr(_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(_mod, "_FINDORA_SRC", None)

    src = _mod._findora_src()
    assert isinstance(src, _mod.TfidfSource)
    assert src.name == "findora"
    assert src.weight == 3
    assert src.min_global == 2
    assert src.min_match_lignes == 2
    assert "findora" in str(src.fr_path)


def test_findora_wrapper_appelle_tfidf_source(tmp_path, monkeypatch):
    """Le wrapper `_findora()` doit deleguer a `TfidfSource.find()`."""
    fdir = tmp_path / "findora"
    fdir.mkdir()
    (fdir / "findora.fr").write_text(
        "achete du mais\nle mais pousse\nmais est cher\n", encoding="utf-8"
    )
    (fdir / "findora.dyu").write_text(
        "kaba san\nkaba bena\nkaba ka da\n", encoding="utf-8"
    )
    monkeypatch.setattr(_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(_mod, "_FINDORA_SRC", None)

    result = _mod._findora("mais")
    assert isinstance(result, Counter)
    assert "kaba" in result, (
        f"_findora doit retourner les scores de TfidfSource. Counter: {dict(result)}"
    )


# ─────────────────────────────────────────────
# Tests HttpScraperSource (issue #233 PR 3)
# ─────────────────────────────────────────────


class _FakeResponse:
    """Mock minimal d'une reponse requests.get."""

    def __init__(self, status_code: int = 200, text: str = ""):
        self.status_code = status_code
        self.text = text


def _builder_constant(url: str, params=None):
    """Construit un url_builder reutilisable pour les tests."""
    return lambda concept: (url, params)


def test_http_scraper_user_agent_par_defaut_mozilla(monkeypatch):
    """Le User-Agent par defaut est Mozilla (harmonise Bamadaba qui n'en avait pas)."""
    capture = {}

    def fake_get(url, params=None, timeout=None, headers=None):
        capture["headers"] = headers
        return _FakeResponse(200, "riz malo")

    monkeypatch.setattr(_mod.requests, "get", fake_get)
    monkeypatch.setattr(_mod, "_ud_loaded", True)
    monkeypatch.setattr(_mod, "_ud_mots", {"malo"})

    src = _mod.HttpScraperSource(
        name="test",
        url_builder=_builder_constant("http://example.com"),
        weight=1,
        fenetre=100,
    )
    src.find("riz")
    assert capture["headers"]["User-Agent"] == _mod.HttpScraperSource.DEFAULT_USER_AGENT


def test_http_scraper_user_agent_personnalise(monkeypatch):
    """Le User-Agent peut etre override au constructeur."""
    capture = {}

    def fake_get(url, params=None, timeout=None, headers=None):
        capture["headers"] = headers
        return _FakeResponse(200, "")

    monkeypatch.setattr(_mod.requests, "get", fake_get)

    src = _mod.HttpScraperSource(
        name="test",
        url_builder=_builder_constant("http://example.com"),
        weight=1,
        fenetre=100,
        user_agent="WouriValidator/1.0",
    )
    src.find("riz")
    assert capture["headers"]["User-Agent"] == "WouriValidator/1.0"


def test_http_scraper_status_non_200_retourne_counter_vide(monkeypatch):
    """Status != 200 → Counter() vide sans crash."""
    monkeypatch.setattr(_mod.requests, "get", lambda *a, **k: _FakeResponse(404, "ignored"))

    src = _mod.HttpScraperSource(
        name="test",
        url_builder=_builder_constant("http://example.com"),
        weight=1,
        fenetre=100,
    )
    assert src.find("riz") == Counter()


def test_http_scraper_exception_reseau_retourne_counter_vide(monkeypatch):
    """Exception (timeout, DNS, etc.) → Counter() vide + log debug (pas de crash)."""
    def fake_get(*a, **k):
        raise ConnectionError("simulated network failure")

    monkeypatch.setattr(_mod.requests, "get", fake_get)

    src = _mod.HttpScraperSource(
        name="test",
        url_builder=_builder_constant("http://example.com"),
        weight=1,
        fenetre=100,
    )
    assert src.find("riz") == Counter()


def test_http_scraper_pre_extraction_check_actif(monkeypatch):
    """Avec `pre_extraction_check=True`, on saute l'extraction si concept absent
    du contenu de la page (optimisation legacy Bamadaba)."""
    # Page ne contient PAS "riz" → check echoue → Counter vide retourne sans
    # appeler _extraire_fenetre.
    page_sans_riz = "malo ɛɔɲ contenu html sans le concept recherche"
    monkeypatch.setattr(_mod.requests, "get", lambda *a, **k: _FakeResponse(200, page_sans_riz))

    src = _mod.HttpScraperSource(
        name="test",
        url_builder=_builder_constant("http://example.com"),
        weight=1,
        fenetre=100,
        pre_extraction_check=True,
    )
    assert src.find("riz") == Counter()


def test_http_scraper_extrait_termes_dans_fenetre(monkeypatch):
    """Cas nominal : page 200 avec concept → extraction fenetre retourne Counter."""
    # Page contient le concept + des termes bambara (caracteres phonetiques)
    page_html = (
        "intro <p>blah blah riz signifie malo ɛn dioula ɛn ce contexte agricole "
        "le malo ɲɔ est cultive partout</p> footer"
    )
    monkeypatch.setattr(_mod.requests, "get", lambda *a, **k: _FakeResponse(200, page_html))
    # Pre-charger _ud_mots vide pour que _est_bambara se base uniquement sur
    # les caracteres phonetiques (ɛ, ɲ, etc.)
    monkeypatch.setattr(_mod, "_ud_loaded", True)
    monkeypatch.setattr(_mod, "_ud_mots", set())

    src = _mod.HttpScraperSource(
        name="test",
        url_builder=_builder_constant("http://example.com"),
        weight=1,
        fenetre=200,
    )
    result = src.find("riz")
    assert isinstance(result, Counter)
    # "malo" sera retenu via _ud_mots si on l'ajoute ; sans ud_mots, il faut
    # un caractere phonetique pour passer le filtre _est_bambara.
    # On verifie simplement que des termes phonetiques sont remontes.
    assert any(any(c in _mod.BAMBARA_CHARS for c in term) for term in result), (
        f"Au moins un terme avec caractere phonetique bambara attendu. Got: {dict(result)}"
    )


# ─────────────────────────────────────────────
# Tests wrappers HTTP + dispatcher trouver_meilleur_terme (fix MAJOR-3 archi)
# ─────────────────────────────────────────────


def test_bamadaba_wrapper_retourne_counter_unifie(monkeypatch):
    """Le wrapper `_bamadaba()` retourne maintenant un Counter (PR 3) au lieu
    d'une `list` comme avant. Ceci permet le dispatcher unifie par TYPE dans
    `trouver_meilleur_terme()` (fix MAJOR-3 archi).
    """
    monkeypatch.setattr(_mod.requests, "get", lambda *a, **k: _FakeResponse(200, "ignored"))

    result = _mod._bamadaba("riz")
    assert isinstance(result, Counter), (
        f"_bamadaba doit retourner Counter (PR 3 unification), got {type(result).__name__}"
    )


def test_dispatcher_par_type_pas_par_nom(monkeypatch):
    """Fix MAJOR-3 archi : `trouver_meilleur_terme()` dispatche par TYPE
    retourne (Counter vs list) et non plus par NOM hardcode.

    On verifie qu'on peut traiter une source qui s'appellerait `"bayelemabaga"`
    mais retournerait une `list` (cas hypothetique post-refactor agri_dict)
    sans declencher la branche TF-IDF par erreur — preuve que le NOM n'est
    plus utilise pour dispatcher.
    """
    # Source factice qui s'appelle "bayelemabaga" mais retourne une LIST.
    # Si l'ancien `if nom == "bayelemabaga"` etait encore en place, cette
    # source serait traitee comme un Counter et crasherait sur .most_common(10).
    fake_sources = [("bayelemabaga", lambda c: ["term1", "term2", "term1"], 2)]
    monkeypatch.setattr(_mod, "SOURCES_PRINCIPALES", fake_sources)
    # Court-circuiter SOURCES_CONFIRMATION pour ne pas charger jeli/UD
    monkeypatch.setattr(_mod, "SOURCES_CONFIRMATION", [])
    # Court-circuit sleep
    monkeypatch.setattr(_mod.time, "sleep", lambda _: None)

    result = _mod.trouver_meilleur_terme("riz", verbose=False)
    # Pas de crash → dispatch par type a fonctionne
    assert result["meilleur_terme"] in ("term1", "term2"), result
    assert result["concept_fr"] == "riz"


def test_dispatcher_traite_counter_en_top10(monkeypatch):
    """Verifie que le branche Counter du dispatcher prend les top10 (pas top3)."""
    # Counter avec 5 termes — tous doivent passer dans la branche top10.
    fake_counter = Counter({"a": 10, "b": 8, "c": 6, "d": 4, "e": 2})
    fake_sources = [("any_name", lambda c: fake_counter, 1)]
    monkeypatch.setattr(_mod, "SOURCES_PRINCIPALES", fake_sources)
    monkeypatch.setattr(_mod, "SOURCES_CONFIRMATION", [])
    monkeypatch.setattr(_mod.time, "sleep", lambda _: None)

    result = _mod.trouver_meilleur_terme("riz", verbose=False)
    classement_termes = [c["terme"] for c in result["classement"]]
    # Les 5 termes doivent etre presents (top10 capture tout)
    assert set(classement_termes) == {"a", "b", "c", "d", "e"}, classement_termes
    # Le top doit etre "a" (score le plus haut)
    assert result["meilleur_terme"] == "a"
