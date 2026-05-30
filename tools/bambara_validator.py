"""
Pipeline DÉCOUVERTE bambara/dioula — Wourri (v3)
=================================================
Pour un concept français → chercher dans les sources →
collecter TOUS les termes bambara/dioula trouvés →
le terme qui revient le plus = le meilleur terme.

Sources actives (10) :
  Source 0 : agri_dict.json — dictionnaire agricole validé multi-sources (×5)
  Dioula CI: Koumankan4Dyula TF-IDF (×3), Findora TF-IDF (×3)
  Bambara  : Bayelemabaga TF-IDF (×2), jeli-asr (confirmation), UD Bambara (confirmation)
  En ligne : Bamadaba CNRS (×2), VOA Bambara, Bambara.org, Bamanankan.org

Sources écartées (raison) :
  An ka Taa   → app React/JS, lexicon.php statique utilisé pour alimenter agri_dict
  Lexilogos   → page de liens, pas un dictionnaire
  Live Lingua → téléchargement manuel requis

v3 changements (2026-04-17) :
  - Ajout Koumankan4Dyula (10 929 paires dioula CI, UVCI) poids ×3
  - Ajout Findora (20 513 paires dioula CI) poids ×3
  - Bayelemabaga réduit de ×3 à ×2 (bambara Mali, pas CI)
  - Score max = 5 + 3 + 3 + 2 + 2 + 1 + 1 + 1 + 1 + 1 = 20

Score max = 20
Seuil auto-validation = 8/20
Seuil décision manuelle = 5-7/20
"""

import re
import json
import time
import logging
import requests
from abc import ABC, abstractmethod
from pathlib import Path
from collections import Counter, defaultdict

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "validation_sources"


# ─────────────────────────────────────────────
# Sources — Abstraction OCP (issue #233, PR 1)
# ─────────────────────────────────────────────
#
# Avant refactor : 3 fonctions TF-IDF (`_bayelemabaga`, `_koumankan`,
# `_findora`) avec ~70 lignes de logique strictement identique, 13 globals
# eparpilles, et un registre ad-hoc (`SOURCES_PRINCIPALES`). Ajouter une
# nouvelle source = modifier 4 endroits (state, loader, fonction, registre).
#
# Apres PR 1 : interface `Source` ABC + 1ere implementation `TfidfSource`
# qui encapsule le state (paires fr/dyu + cache freq globale) en attribut
# d'instance plutot qu'en globals module-level.
#
# Scope PR 1 = preuve de concept : seul Bayelemabaga est migre. Les 2
# autres TF-IDF (Koumankan, Findora) et les 4 scrapers HTTP restent
# inchanges. PR 2 et PR 3 finiront la migration une fois le design valide.


class Source(ABC):
    """Interface pour une source de validation bambara/dioula.

    Une source produit un `Counter` (terme → score). Pour les sources TF-IDF,
    le score est `round(tf_rate / idf_rate * 100)` ; pour les listes (scrapers
    HTTP) une couche d'adaptation reste a definir en PR ulterieure.
    """

    name: str
    weight: int

    @abstractmethod
    def load(self) -> None:
        """Charge les donnees en memoire (cache `_loaded`, idempotent)."""

    @abstractmethod
    def find(self, concept_fr: str) -> Counter:
        """Retourne `{terme: score}` pour ce concept. `Counter()` vide si rien."""


class TfidfSource(Source):
    """Source TF-IDF generique sur 2 fichiers texte alignes (paires fr/dyu).

    Encapsule l'etat (paires + cache freq globale) en attribut d'instance.
    Anciennement reparti sur 4 globals module-level (`_baye_fr`, `_baye_bam`,
    `_baye_loaded`, `_baye_global_freq`) repetes par source.
    """

    def __init__(
        self,
        name: str,
        fr_path: Path,
        dyu_path: Path,
        weight: int,
        min_global: int,
        min_match_lignes: int,
    ):
        self.name = name
        self.fr_path = fr_path
        self.dyu_path = dyu_path
        self.weight = weight
        self.min_global = min_global
        self.min_match_lignes = min_match_lignes
        # Etat interne (anciennement globals)
        self._fr: list[str] = []
        self._dyu: list[str] = []
        self._global_freq: Counter = Counter()
        self._loaded = False
        # Garde-fou idempotence pour les sources qui concatenent plusieurs
        # fichiers via `append_split()` (cas Bayelemabaga, 3 splits).
        # Sans ce flag, appeler 2x une fonction d'orchestration externe
        # (ex: _bayelemabaga_load_all_splits) dupliquerait le corpus en
        # memoire → TF-IDF fausse. Fix review issue #233 PR 1 MAJOR-1.
        self._all_splits_loaded: bool = False

    def load(self) -> None:
        if self._loaded:
            return
        if self.fr_path.exists() and self.dyu_path.exists():
            with open(self.fr_path, encoding="utf-8") as f:
                self._fr = f.readlines()
            with open(self.dyu_path, encoding="utf-8") as f:
                self._dyu = f.readlines()
        self._loaded = True
        logger.info(f"[VAL] {self.name}: {len(self._fr)} paires chargees")

    def append_split(self, fr_path: Path, dyu_path: Path) -> None:
        """Ajoute un split additionnel a la source apres `load()`.

        Cas d'usage : Bayelemabaga est splitte en 3 dossiers (train/test/valid).
        `load()` charge le 1er split, `append_split()` ajoute les suivants.

        Invalide automatiquement le cache `_global_freq` pour qu'il soit
        recalcule sur l'ensemble du corpus au prochain `find()`. Fix review
        issue #233 PR 1 MAJOR-2 (encapsulation : remplace l'acces direct aux
        attributs prives `_fr`/`_dyu`/`_global_freq` depuis l'exterieur).
        """
        if not fr_path.exists() or not dyu_path.exists():
            return
        with open(fr_path, encoding="utf-8") as f:
            self._fr.extend(f.readlines())
        with open(dyu_path, encoding="utf-8") as f:
            self._dyu.extend(f.readlines())
        # Invalider le cache global_freq pour recalcul au prochain find()
        self._global_freq = Counter()

    def find(self, concept_fr: str) -> Counter:
        self.load()

        concept = concept_fr.lower()

        # Match en mot entier pour eviter les faux positifs
        # (ex: "mais" comme substring de "mais aussi").
        def _match(ligne_fr: str) -> bool:
            return bool(re.search(r"\b" + re.escape(concept) + r"\b", ligne_fr.lower()))

        lignes_match = [dyu for fr, dyu in zip(self._fr, self._dyu) if _match(fr)]

        if len(lignes_match) < self.min_match_lignes:
            return Counter()

        # TF : frequence dans les lignes matchant
        tf: Counter = Counter()
        for ligne in lignes_match:
            tf.update(_tokeniser_simple(ligne))

        # Cache freq globale (calculee une seule fois)
        if not self._global_freq:
            logger.info(f"[VAL] Calcul frequence globale {self.name} (une fois)...")
            for ligne in self._dyu:
                self._global_freq.update(_tokeniser_simple(ligne))
            logger.info(
                f"[VAL] {self.name} vocabulaire: {len(self._global_freq)} mots uniques"
            )

        n_match = len(lignes_match)
        n_total = max(len(self._dyu), 1)

        scores: Counter = Counter()
        for terme, freq_match in tf.items():
            freq_global = self._global_freq.get(terme, 0)
            if freq_global < self.min_global:
                continue
            if freq_match < 1:
                continue
            tf_rate = freq_match / n_match
            idf_rate = freq_global / n_total
            ratio = tf_rate / idf_rate
            scores[terme] = max(1, round(ratio * 100))

        return scores


# Instance Bayelemabaga (anciens parametres : min_global=3, min_match_lignes=3).
# Volontairement initialisee a None et instanciee lazy dans _bayelemabaga_src()
# pour conserver le comportement "charge a la 1ere utilisation" du module
# (DATA_DIR resolu une seule fois mais fichiers lus sur demande).
_BAYELEMABAGA_SRC: "TfidfSource | None" = None


def _bayelemabaga_src() -> TfidfSource:
    global _BAYELEMABAGA_SRC
    if _BAYELEMABAGA_SRC is None:
        for split in ("train", "test", "valid"):
            # Bayelemabaga est splitte en 3 dossiers. On garde la 1ere paire
            # existante comme initialisation primaire ; les autres splits sont
            # concatenes ci-dessous pour reproduire le comportement legacy.
            base = DATA_DIR / "bayelemabaga" / split
            if (base / f"{split}.fr").exists():
                _BAYELEMABAGA_SRC = TfidfSource(
                    name="bayelemabaga",
                    fr_path=base / f"{split}.fr",
                    dyu_path=base / f"{split}.bam",
                    weight=2,
                    min_global=3,
                    min_match_lignes=3,
                )
                break
        if _BAYELEMABAGA_SRC is None:
            # Aucun split present : TfidfSource avec paths vides → load() sera
            # un no-op, find() renverra Counter() vide. Comportement equivalent
            # a l'ancien code (qui ne chargait rien si fichiers absents).
            _BAYELEMABAGA_SRC = TfidfSource(
                name="bayelemabaga",
                fr_path=DATA_DIR / "bayelemabaga" / "train" / "train.fr",
                dyu_path=DATA_DIR / "bayelemabaga" / "train" / "train.bam",
                weight=2,
                min_global=3,
                min_match_lignes=3,
            )
    return _BAYELEMABAGA_SRC


def _bayelemabaga_load_all_splits() -> None:
    """Concatene les 3 splits (train/test/valid) de Bayelemabaga dans la source.

    Comportement legacy : le module original chargait les 3 splits en boucle
    avant l'introduction de l'abstraction `TfidfSource`. On preserve ce
    comportement en chargeant les splits additionnels apres `load()`.

    Idempotent (fix review #233 PR 1 MAJOR-1) : le flag `_all_splits_loaded`
    sur l'instance empeche une 2e concatenation qui doublerait le corpus.
    Utilise `append_split()` (fix MAJOR-2) plutot qu'un acces direct aux
    attributs prives pour preserver l'encapsulation.
    """
    src = _bayelemabaga_src()
    if src._all_splits_loaded:
        return
    src.load()
    if src._loaded and len(src._fr) > 0:
        # 1er split deja charge par load(). Concatener les autres si dispo.
        deja_charge = src.fr_path.parent.name  # ex: "train"
        for split in ("train", "test", "valid"):
            if split == deja_charge:
                continue
            fr_f = DATA_DIR / "bayelemabaga" / split / f"{split}.fr"
            bam_f = DATA_DIR / "bayelemabaga" / split / f"{split}.bam"
            src.append_split(fr_f, bam_f)
    src._all_splits_loaded = True

# Caractères phonétiques spécifiques au bambara (absents de l'anglais et du HTML)
BAMBARA_CHARS = frozenset("ɛɔɲŋɓɗɪʊ")

# Mots bambara courts connus (≤ 2 chars) — exceptions au filtre longueur
# Ex: ku=igname, ɲɔ=mil — confirmés par An ka Taa, mandenkan, coastsystems
SHORT_AGRI_TERMS = {"ku", "ɲɔ"}

# Mots grammaticaux bambara à ignorer
STOPWORDS_BAM = {
    "ye", "bɛ", "be", "ka", "ko", "la", "ni", "o", "a", "i", "n", "u",
    "an", "aw", "le", "de", "nan", "ma", "do", "kɔ", "fɔ", "fo", "si",
    "so", "da", "wo", "wa", "di", "ke", "se", "to", "bi", "na", "ta",
    "min", "don", "jan", "bɔ", "bo", "in", "tun", "nɔ", "no", "sun",
    "san", "kan", "den", "ten", "kelen", "fila", "saba",
}

# ─────────────────────────────────────────────
# État interne — chargé une seule fois
# ─────────────────────────────────────────────

_agri_dict: dict = {}          # Dictionnaire agricole validé multi-sources
_agri_loaded = False

# Note: les globals `_baye_*` ont ete remplaces par l'attribut d'instance de
# `TfidfSource` (cf. `_BAYELEMABAGA_SRC` plus haut, issue #233 PR 1).
# Les 2 autres TF-IDF (`_kouman_*`, `_findora_*`) seront migres en PR 2.

_jeli_phrases: list = []
_jeli_loaded = False

_ud_mots: set = set()
_ud_loaded = False

# Note: les globals `_kouman_*` et `_findora_*` ont ete remplaces par des
# attributs d'instance TfidfSource (cf. `_KOUMAN_SRC` et `_FINDORA_SRC`
# plus bas, issue #233 PR 2). PR 3 finira la migration avec les 4 scrapers
# HTTP via une nouvelle classe HttpScraperSource.


def _charger_agri_dict():
    global _agri_dict, _agri_loaded
    if _agri_loaded:
        return
    f = DATA_DIR / "agri_dict.json"
    if f.exists():
        with open(f, encoding="utf-8") as fp:
            data = json.load(fp)
        # Construire un index : concept_fr.lower() → terme_bambara
        for concept, info in data.get("cultures", {}).items():
            terme = info.get("bambara")
            if terme:
                _agri_dict[concept.lower()] = terme
            variante = info.get("variante")
            if variante:
                _agri_dict[f"{concept.lower()}__variante"] = variante
    _agri_loaded = True
    logger.info(f"[VAL] agri_dict: {len(_agri_dict)} concepts charges")


def _charger_bayelemabaga():
    """Wrapper de compatibilite (issue #233 PR 1) : delegue a `TfidfSource`.

    L'ancien code chargeait les 3 splits (train/test/valid) en boucle. On
    reproduit ce comportement via `_bayelemabaga_load_all_splits()` qui
    concatene les splits dans l'instance.
    """
    _bayelemabaga_load_all_splits()


def _charger_jeli():
    global _jeli_phrases, _jeli_loaded
    if _jeli_loaded:
        return
    f = DATA_DIR / "jeli_asr_bam.txt"
    if f.exists():
        with open(f, encoding="utf-8") as fp:
            _jeli_phrases = [l.strip().lower() for l in fp if l.strip()]
    _jeli_loaded = True
    logger.info(f"[VAL] jeli-asr: {len(_jeli_phrases)} phrases")


def _charger_ud():
    global _ud_mots, _ud_loaded
    if _ud_loaded:
        return
    f = DATA_DIR / "ud_bambara_words.txt"
    if f.exists():
        with open(f, encoding="utf-8") as fp:
            _ud_mots = {l.strip().lower() for l in fp if l.strip()}
    _ud_loaded = True


# Instances Koumankan + Findora (issue #233 PR 2).
# Anciens parametres preserves : min_global=2, min_match_lignes=2 pour les 2
# (cf. legacy `_koumankan` et `_findora` avant refactor).
# Lazy-init via helpers `_kouman_src()` et `_findora_src()`.
_KOUMAN_SRC: "TfidfSource | None" = None
_FINDORA_SRC: "TfidfSource | None" = None


def _kouman_src() -> TfidfSource:
    global _KOUMAN_SRC
    if _KOUMAN_SRC is None:
        _KOUMAN_SRC = TfidfSource(
            name="koumankan",
            fr_path=DATA_DIR / "koumankan" / "koumankan.fr",
            dyu_path=DATA_DIR / "koumankan" / "koumankan.dyu",
            weight=3,
            min_global=2,
            min_match_lignes=2,
        )
    return _KOUMAN_SRC


def _findora_src() -> TfidfSource:
    global _FINDORA_SRC
    if _FINDORA_SRC is None:
        _FINDORA_SRC = TfidfSource(
            name="findora",
            fr_path=DATA_DIR / "findora" / "findora.fr",
            dyu_path=DATA_DIR / "findora" / "findora.dyu",
            weight=3,
            min_global=2,
            min_match_lignes=2,
        )
    return _FINDORA_SRC


def _charger_koumankan():
    """Wrapper de compatibilite (issue #233 PR 2) : delegue a TfidfSource."""
    _kouman_src().load()


def _charger_findora():
    """Wrapper de compatibilite (issue #233 PR 2) : delegue a TfidfSource."""
    _findora_src().load()


# ─────────────────────────────────────────────
# Tokenizers (deux niveaux de rigueur)
# ─────────────────────────────────────────────

def _tokeniser_simple(texte: str) -> list:
    """
    Tokenizer léger — pour les lignes BAM du corpus Bayelemabaga.
    On SAIT que ces lignes sont en bambara : pas besoin de filtre de langue.
    Rejette les stopwords et les mots trop courts (sauf SHORT_AGRI_TERMS).
    """
    mots = re.findall(r"[a-zA-Zɛɔɲŋɪʊɓɗ'-]+", texte.lower())
    return [
        m for m in mots
        if m not in STOPWORDS_BAM
        and (len(m) > 2 or m in SHORT_AGRI_TERMS)
    ]


def _est_bambara(mot: str) -> bool:
    """
    Un mot venant d'une source HTML est bambara s'il :
      (a) contient au moins un caractère phonétique bambara (ɛ, ɔ, ɲ, ŋ, ɓ, ɗ, ɪ, ʊ)
      (b) OU est dans le dictionnaire UD Bambara (976 mots vérifiés)

    Rejette : 'html', 'script', 'body', 'search', 'location', etc.
    Note: _charger_ud() doit avoir été appelé avant.
    """
    if any(c in BAMBARA_CHARS for c in mot):
        return True
    return mot in _ud_mots


def _tokeniser_bambara(texte: str) -> list:
    """
    Tokenizer strict — pour le contenu HTML des sources en ligne.
    Filtre les mots anglais/HTML qui n'ont aucun caractère bambara.
    _charger_ud() doit avoir été appelé au préalable.
    """
    mots = re.findall(r"[a-zA-Zɛɔɲŋɪʊɓɗ'-]+", texte.lower())
    return [
        m for m in mots
        if m not in STOPWORDS_BAM
        and (len(m) > 2 or m in SHORT_AGRI_TERMS)
        and _est_bambara(m)
    ]


def _extraire_fenetre(texte: str, concept: str, fenetre: int = 250) -> list:
    """
    Extrait les mots bambara dans une fenêtre de `fenetre` caractères
    autour de chaque occurrence du concept dans le texte.

    Avantage : évite de prendre tout le bruit de la page (menus, scripts...).
    """
    _charger_ud()
    texte_lower = texte.lower()
    concept_lower = concept.lower()
    termes = []
    pos = 0
    while True:
        idx = texte_lower.find(concept_lower, pos)
        if idx == -1:
            break
        debut = max(0, idx - fenetre)
        fin = min(len(texte), idx + len(concept) + fenetre)
        extrait = texte[debut:fin]
        termes.extend(_tokeniser_bambara(extrait))
        pos = idx + 1
    return termes


# ─────────────────────────────────────────────
# Source 0 — Dictionnaire agricole validé (local)
# ─────────────────────────────────────────────

def _agri_dict_lookup(concept_fr: str) -> list:
    """
    Cherche le concept français dans le dictionnaire agricole validé.
    Retourne [terme_principal] ou [terme_principal, variante] si trouvé.

    Confiance maximale : termes vérifiés par 2-5 sources académiques.
    Ex: riz → ['malo'], igname → ['ku'], manioc → ['bananku']
    """
    _charger_agri_dict()
    concept = concept_fr.lower()
    termes = []
    if concept in _agri_dict:
        termes.append(_agri_dict[concept])
    variante_key = f"{concept}__variante"
    if variante_key in _agri_dict:
        termes.append(_agri_dict[variante_key])
    return termes


# ─────────────────────────────────────────────
# Source 1 — Bayelemabaga (local, TF-IDF)
# ─────────────────────────────────────────────

def _bayelemabaga(concept_fr: str) -> Counter:
    """Wrapper de compatibilite (issue #233 PR 1) : delegue a `TfidfSource`.

    Anciennement ~69 lignes de logique TF-IDF dupliquees avec `_koumankan`
    et `_findora`. Migre vers `TfidfSource.find()` generique (cf. classe
    en haut du fichier). Les 2 autres TF-IDF seront migres en PR 2.

    Particularite Bayelemabaga : les paires sont splittees en train/test/valid.
    On force la concatenation des 3 splits via `_bayelemabaga_load_all_splits()`
    avant de deleguer.

    Logique TF-IDF inchangee :
      TF    = frequence du terme dans les lignes BAM ou concept_fr apparait
      IDF   = frequence du terme dans TOUT le corpus BAM (normalisee)
      Ratio = TF / IDF → eleve si le terme est SPECIFIQUE a ce concept

    Note : utilise _tokeniser_simple (sans filtre de langue) car les lignes
    BAM de Bayelemabaga sont garanties bambara.
    """
    _bayelemabaga_load_all_splits()
    return _bayelemabaga_src().find(concept_fr)


# ─────────────────────────────────────────────
# Source 1b — Koumankan4Dyula (DIOULA CI, TF-IDF)
# ─────────────────────────────────────────────

def _koumankan(concept_fr: str) -> Counter:
    """Wrapper de compatibilite (issue #233 PR 2) : delegue a TfidfSource.

    Anciennement 47 lignes de TF-IDF dupliquees avec `_bayelemabaga` et
    `_findora`. Migre vers TfidfSource generique (cf. classe en haut du
    fichier, parametres : min_global=2, min_match_lignes=2 pour preserver
    le comportement legacy).

    Particularite Koumankan vs Bayelemabaga : 1 seul fichier de paires
    (pas de splits multiples train/test/valid), donc pas besoin de
    `_load_all_splits()` ni de `_all_splits_loaded`.

    TF-IDF sur Koumankan4Dyula (10 929 paires dioula CI, UVCI).
    """
    return _kouman_src().find(concept_fr)


# ─────────────────────────────────────────────
# Source 1c — Findora (DIOULA CI, TF-IDF)
# ─────────────────────────────────────────────

def _findora(concept_fr: str) -> Counter:
    """Wrapper de compatibilite (issue #233 PR 2) : delegue a TfidfSource.

    Anciennement 47 lignes de TF-IDF dupliquees. Migre vers TfidfSource
    generique (min_global=2, min_match_lignes=2).

    TF-IDF sur Findora (20 513 paires dioula CI).
    """
    return _findora_src().find(concept_fr)


# ─────────────────────────────────────────────
# Source 2 — jeli-asr (confirmation)
# ─────────────────────────────────────────────

def _jeli_confirme(terme: str) -> bool:
    """Vérifie si un terme bambara apparaît dans le corpus oral (67k phrases)."""
    _charger_jeli()
    terme = terme.lower()
    for phrase in _jeli_phrases:
        if re.search(r'\b' + re.escape(terme) + r'\b', phrase):
            return True
    return False


# ─────────────────────────────────────────────
# Source 3 — UD Bambara (confirmation)
# ─────────────────────────────────────────────

def _ud_confirme(terme: str) -> bool:
    """Vérifie si un terme est dans le treebank UD Bambara (CNRS, 976 mots)."""
    _charger_ud()
    return terme.lower() in _ud_mots


# ─────────────────────────────────────────────
# Source 4 — Bamadaba (CNRS, en ligne)
# ─────────────────────────────────────────────

def _bamadaba(concept_fr: str) -> list:
    """
    Bamadaba = dictionnaire bambara du CNRS.
    Cherche le concept en français et extrait les mots bambara
    dans une fenêtre de 150 chars autour de chaque occurrence.
    """
    termes = []
    try:
        url = "http://cormand.huma-num.fr/cgi-bin/corpus.cgi"
        params = {"c": "Bamadaba", "q": concept_fr, "interface_language": "fr"}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200 and concept_fr.lower() in r.text.lower():
            termes = _extraire_fenetre(r.text, concept_fr, fenetre=150)
    except Exception as e:
        logger.debug(f"[VAL] Bamadaba: {e}")
    return termes


# ─────────────────────────────────────────────
# Source 5 — VOA Bambara
# ─────────────────────────────────────────────

def _voa_bambara(concept_fr: str) -> list:
    """
    VOA Bambara = actualités en bambara.
    Extrait les mots bambara dans une fenêtre de 200 chars autour
    de chaque occurrence du concept dans les résultats de recherche.
    """
    termes = []
    try:
        url = f"https://www.voabambara.com/s?k={concept_fr}"
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            termes = _extraire_fenetre(r.text, concept_fr, fenetre=200)
    except Exception as e:
        logger.debug(f"[VAL] VOA: {e}")
    return termes


# ─────────────────────────────────────────────
# Source 6 — Bambara.org (dictionnaire statique)
# ─────────────────────────────────────────────

def _bambara_org(concept_fr: str) -> list:
    """
    Bambara.org/dico = dictionnaire français-bambara en HTML statique.
    Fenêtre petite (100 chars) car les entrées dictionnaire sont courtes.
    """
    termes = []
    try:
        url = "http://www.bambara.org/biblia/bam/dico/dico_f.htm"
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            termes = _extraire_fenetre(r.text, concept_fr, fenetre=100)
    except Exception as e:
        logger.debug(f"[VAL] Bambara.org: {e}")
    return termes


# ─────────────────────────────────────────────
# Source 7 — Bamanankan.org
# ─────────────────────────────────────────────

def _bamanankan_org(concept_fr: str) -> list:
    """
    Bamanankan.org = référence académique bambara (WordPress).
    Les snippets de résultats contiennent des termes bambara
    proches du concept recherché.
    """
    termes = []
    try:
        url = f"https://www.bamanankan.org/?s={concept_fr}"
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            termes = _extraire_fenetre(r.text, concept_fr, fenetre=200)
    except Exception as e:
        logger.debug(f"[VAL] Bamanankan: {e}")
    return termes


# ─────────────────────────────────────────────
# Registre des sources
# ─────────────────────────────────────────────

SOURCES_PRINCIPALES = [
    # (nom, fonction, poids_vote)
    ("agri_dict",    _agri_dict_lookup, 5),  # Dico validé multi-sources — poids maximum
    ("koumankan",    _koumankan,        3),  # Dioula CI (UVCI) — TF-IDF
    ("findora",      _findora,          3),  # Dioula CI — TF-IDF
    ("bayelemabaga", _bayelemabaga,     2),  # Bambara Mali — TF-IDF (réduit de 3→2)
    ("bamadaba",     _bamadaba,         2),  # CNRS, académique
    ("voa_bambara",  _voa_bambara,      1),
    ("bambara_org",  _bambara_org,      1),
    ("bamanankan",   _bamanankan_org,   1),
]

SOURCES_CONFIRMATION = [
    ("jeli_asr",   _jeli_confirme, 1),  # +1 si présent dans corpus oral
    ("ud_bambara", _ud_confirme,   1),  # +1 si présent dans treebank CNRS
]

# Score maximum possible (utilisé pour normaliser en 0.0–1.0)
SCORE_MAX = (
    sum(p for _, _, p in SOURCES_PRINCIPALES) +
    sum(p for _, _, p in SOURCES_CONFIRMATION)
)
# = 5 + 3 + 3 + 2 + 2 + 1 + 1 + 1 + 1 + 1 = 20


# ─────────────────────────────────────────────
# Fonction principale : DÉCOUVERTE du meilleur terme
# ─────────────────────────────────────────────

def trouver_meilleur_terme(concept_fr: str, verbose: bool = True) -> dict:
    """
    Pour un concept français, cherche dans toutes les sources et retourne
    le terme bambara le plus spécifique = le meilleur terme validé.

    Exemple :
        result = trouver_meilleur_terme("igname")
        result["meilleur_terme"]  # → "danburu"
        result["score"]           # → 0.7 (7/10 points)
        result["classement"]      # → top 5 termes avec scores
    """
    votes: dict = defaultdict(lambda: {"count": 0, "sources": []})

    if verbose:
        print(f"\n{'='*60}")
        print(f"  Recherche : '{concept_fr}'")
        print(f"{'='*60}")

    # ── Étape 1 : Collecter les termes depuis chaque source ──
    for nom, fn, poids in SOURCES_PRINCIPALES:
        try:
            if nom == "bayelemabaga":
                # Retourne un Counter (scores TF-IDF)
                compteur = fn(concept_fr)
                top10 = compteur.most_common(10)  # top 10 pour capturer bases de composés
                for terme, score_tfidf in top10:
                    votes[terme]["count"] += poids
                    votes[terme]["sources"].append(f"{nom}(tfidf~{score_tfidf})")
                if verbose:
                    top_str = ", ".join([f"{t}(~{s})" for t, s in top10[:3]])
                    print(f"  [{nom:15s}] -> {top_str if top10 else 'rien trouve'}")
            else:
                # Retourne une liste — on prend les 3 plus fréquents
                termes = fn(concept_fr)
                freq_locale = Counter(termes)
                top3 = [t for t, _ in freq_locale.most_common(3)]
                for terme in top3:
                    votes[terme]["count"] += poids
                    votes[terme]["sources"].append(nom)
                if verbose:
                    print(f"  [{nom:15s}] -> {top3 if top3 else 'rien trouve'}")

            time.sleep(0.3)  # Politesse pour les sites en ligne

        except Exception as e:
            logger.warning(f"[VAL] Erreur source {nom}: {e}")
            if verbose:
                print(f"  [{nom:15s}] -> ERREUR: {e}")

    # ── Étape 2 : Confirmation dans corpus locaux ──
    if verbose:
        print(f"\n  Confirmation corpus locaux (jeli-asr, UD)...")

    for terme in list(votes.keys()):
        for nom, fn, poids in SOURCES_CONFIRMATION:
            if fn(terme):
                votes[terme]["count"] += poids
                votes[terme]["sources"].append(f"✓{nom}")

    # ── Étape 3 : Classement final ──
    if not votes:
        return {
            "concept_fr":     concept_fr,
            "meilleur_terme": None,
            "score":          0.0,
            "classement":     [],
            "message":        "Aucun terme bambara trouvé dans les sources",
        }

    classement = sorted(
        votes.items(),
        key=lambda x: x[1]["count"],
        reverse=True,
    )

    meilleur_terme, meilleur_info = classement[0]
    score = round(meilleur_info["count"] / SCORE_MAX, 2)

    if verbose:
        print(f"\n  Classement final :")
        for i, (terme, info) in enumerate(classement[:5]):
            s = round(info["count"] / SCORE_MAX, 2)
            print(f"    {i+1}. '{terme}' — score={s} — {info['sources']}")
        print(f"\n  MEILLEUR TERME : '{meilleur_terme}' (score={score})")

    return {
        "concept_fr":     concept_fr,
        "meilleur_terme": meilleur_terme,
        "score":          score,
        "sources":        meilleur_info["sources"],
        "classement": [
            {
                "terme":   t,
                "score":   round(info["count"] / SCORE_MAX, 2),
                "sources": info["sources"],
            }
            for t, info in classement[:5]
        ],
    }


# ─────────────────────────────────────────────
# Validation d'un terme existant
# ─────────────────────────────────────────────

def valider_terme_existant(terme_bam: str, concept_fr: str, verbose: bool = True) -> dict:
    """
    Vérifie si un terme bambara existant est bien le meilleur pour un concept.
    Utile pour re-valider les entrées du corpus_ivr.json.

    Retourne :
        {
          "terme_teste":    str,
          "valide":         bool,
          "meilleur_terme": str,
          "score":          float,
          "action":         "garder" | "remplacer" | "verifier_manuellement"
        }
    """
    result = trouver_meilleur_terme(concept_fr, verbose=verbose)
    meilleur = result.get("meilleur_terme")

    if meilleur is None:
        action, valide = "verifier_manuellement", False
    elif meilleur == terme_bam.lower():
        action, valide = "garder", True
    elif result["score"] > 0.5:
        action, valide = "remplacer", False
    else:
        action, valide = "verifier_manuellement", False

    return {
        "terme_teste":    terme_bam,
        "valide":         valide,
        "meilleur_terme": meilleur,
        "score":          result["score"],
        "action":         action,
        "classement":     result.get("classement", []),
    }
