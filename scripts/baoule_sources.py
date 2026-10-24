"""Wourri — Sources de la validation multi-sources des mots baoulé (ADR-0046).

Même méthode que le dioula (tools/bambara_validator.py) : pour un mot français, chaque
source propose des mots baoulé, et le poids de chaque source qui propose un mot
s'additionne (score sur 20). Trois sortes de sources :
- `Dictionnaire` : paires (français, baoulé) lues telles quelles ;
- `Cooccurrence` : phrases alignées (français, baoulé) ; les mots baoulé sur-représentés
  dans les phrases dont le français contient le mot (TF-IDF, comme le dioula) ;
- `Attestation` : un texte baoulé où la forme proposée existe (confirme la graphie).

Leçon du constat C10 (docs/AUDIT_DIOULA_2026-08.md) : le validateur dioula chargeait ses
sources vides en silence. Ici, une source déclarée absente ou vide lève `SourceVide`.

Les formes baoulé sont comparées après `tokens_bci` (minuscules, tons retirés,
apostrophes → espace) ; la graphie affichée est la plus fréquente dans la source.
Aucun texte n'est versionné : voir `telecharger()` pour le dossier local des sources.
"""
from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from app.services.nlu.baoule_text import tokens_bci

ARTICLES_FR = {"le", "la", "les", "l", "un", "une", "des", "du", "de", "d", "se", "s"}
MAX_MOTS_GLOSE = 3  # au-delà, la glose est une définition, pas une traduction


class SourceVide(RuntimeError):
    """Une source déclarée n'a rien chargé : on arrête au lieu de voter sans elle."""


def mots_fr(texte: str) -> list[str]:
    """Mots français comparables : minuscules, ponctuation retirée, accents gardés."""
    t = unicodedata.normalize("NFC", (texte or "").lower()).replace("’", "'")
    return re.sub(r"[^\w\s]", " ", t).split()


def forme_fr(texte: str) -> str:
    """Glose française sans article : « le cacao » → « cacao »."""
    return " ".join(m for m in mots_fr(texte) if m not in ARTICLES_FR)


_NASALE = re.compile(r"(?<!\w)([nmɲNMƝ])['’ʼ‘`](?=\w)")


def toks_bci(texte: str) -> list[str]:
    """`tokens_bci`, la nasale initiale gardée dans le mot : « n'zue » = « nzue » (eau),
    alors que l'apostrophe finale reste un déterminant séparé (« nzue’n » → nzue + n)."""
    return tokens_bci(_NASALE.sub(r"\1", texte or ""))


def forme_bci(texte: str) -> str:
    return " ".join(toks_bci(texte))


def _exige(nom: str, n: int) -> None:
    if n == 0:
        raise SourceVide(f"source « {nom} » vide ou absente : vérifier le dossier des sources")


class Dictionnaire:
    """Paires (glose française, mot baoulé) ; propose les mots dont la glose est le mot cherché."""

    def __init__(self, nom: str, poids: int, paires):
        self.nom, self.poids = nom, poids
        self._par_glose: dict[str, Counter] = defaultdict(Counter)
        for fr, bci in paires:
            g, b = forme_fr(fr), forme_bci(bci)
            if g and b and len(g.split()) <= MAX_MOTS_GLOSE:
                self._par_glose[g][bci.strip()] += 1
        _exige(nom, len(self._par_glose))

    def proposer(self, mot: str) -> dict[str, str]:
        m = forme_fr(mot)
        out: dict[str, Counter] = defaultdict(Counter)
        for g in (m, m + "s", m + "x"):
            for graphie, n in self._par_glose.get(g, {}).items():
                out[forme_bci(graphie)][graphie] += n
        return {b: c.most_common(1)[0][0] for b, c in out.items()}


class Cooccurrence:
    """Phrases alignées ; propose les n-grammes baoulé sur-représentés (TF-IDF du dioula)."""

    def __init__(self, nom: str, poids: int, phrases, top: int = 3, min_lignes: int = 2, min_global: int = 2):
        self.nom, self.poids, self.top = nom, poids, top
        self.min_lignes, self.min_global = min_lignes, min_global
        self._fr: list[set[str]] = []
        self._bci: list[set[str]] = []
        self._graphies: dict[str, Counter] = defaultdict(Counter)
        for fr, bci in phrases:
            grams = self._grammes(bci)
            if grams:
                self._fr.append(set(mots_fr(fr)))
                self._bci.append(grams)
        _exige(nom, len(self._bci))
        self._global = Counter(g for s in self._bci for g in s)

    def _grammes(self, texte: str) -> set[str]:
        toks = toks_bci(texte)
        for brut in (texte or "").split():  # graphie d'origine du mot, sans déterminant accolé
            sous = toks_bci(brut)
            if sous:
                base = re.split(r"['’ʼ‘`]", _NASALE.sub(r"\1", brut))[0].strip(".,;:!?«»\"()")
                if base and toks_bci(base) == sous[:1]:
                    self._graphies[sous[0]][base] += 1
        return set(toks) | {f"{a} {b}" for a, b in zip(toks, toks[1:])}

    def proposer(self, mot: str) -> dict[str, str]:
        cible = mots_fr(mot)
        lignes = [b for f, b in zip(self._fr, self._bci) if all(w in f for w in cible)]
        if len(lignes) < self.min_lignes:
            return {}
        tf = Counter(g for s in lignes for g in s)
        n_total = len(self._bci)
        scores = {g: (n / len(lignes)) / (self._global[g] / n_total)
                  for g, n in tf.items() if self._global[g] >= self.min_global and n >= self.min_lignes}
        meilleurs = sorted(scores, key=lambda g: (-scores[g], g))[: self.top]
        return {g: self._graphie(g) for g in meilleurs}

    def _graphie(self, g: str) -> str:
        return " ".join(self._graphies[t].most_common(1)[0][0] if self._graphies[t] else t for t in g.split())


class Attestation:
    """Texte baoulé : confirme qu'une forme proposée y existe au moins `min_occ` fois."""

    def __init__(self, nom: str, textes, min_occ: int = 1, poids: int = 1):
        self.nom, self.poids, self.min_occ = nom, poids, min_occ
        self._textes = [t for t in textes if t and t.strip()]
        _exige(nom, len(self._textes))
        self._compte: Counter = Counter()

    def compter(self, formes: set[str]) -> None:
        """Compte en un passage les seules formes candidates (corpus de millions de mots)."""
        n_max = max((len(f.split()) for f in formes), default=1)
        for t in self._textes:
            toks = toks_bci(t)
            for n in range(1, n_max + 1):
                for i in range(len(toks) - n + 1):
                    g = " ".join(toks[i:i + n])
                    if g in formes:
                        self._compte[g] += 1

    def atteste(self, forme: str) -> bool:
        return self._compte[forme] >= self.min_occ


# ── Lecture des fichiers de sources ────────────────────────────────────────

def _jsonl(path: Path):
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def wiktionnaire(path: Path):
    """kaikki.org (Wiktionnaire français, entrées baoulé) : (glose, mot)."""
    for e in _jsonl(path):
        for s in e.get("senses", []):
            for glose in s.get("glosses", []):
                for morceau in re.split(r"[;,]", glose):
                    yield morceau, e.get("word", "")


def gatitos_fr_bci(en_fr: Path, en_bci: Path):
    """GATITOS : la même entrée anglaise traduite en français et en baoulé → (fr, bci)."""
    fr = {r["src"]: r["trgs"] for r in _jsonl(en_fr)}
    for r in _jsonl(en_bci):
        for f in fr.get(r["src"], []):
            for b in r["trgs"]:
                yield f, b


def panlex_fr_bci(bci_eng: Path, en_fr: Path):
    """PanLex (via ChiKhaPo) baoulé → anglais, ramené au français par GATITOS anglais → français."""
    fr = defaultdict(list)
    for r in _jsonl(en_fr):
        fr[r["src"].lower()].extend(r["trgs"])
    for r in _jsonl(bci_eng):
        for en in r.get("target_translations", []):
            for f in fr.get(en.lower(), []):
                yield f, r["source_word"]


def validations_locuteur(path: Path):
    """Mots-clés ACCEPTÉS par le locuteur dans l'atelier (/tasks/validations?kind=mot_cle)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for e in data.get("entries", data) if isinstance(data, dict) else data:
        if e.get("status") == "admin_accepted":
            yield e.get("text_fr", ""), e.get("text_local", "")


def dictee(export: Path):
    """Export de l'écran Dictée (ZIP ou metadata.csv) : (français, transcription)."""
    p = Path(export)
    if p.suffix.lower() == ".zip":
        with zipfile.ZipFile(p) as z:
            texte = z.read(next(n for n in z.namelist() if n.endswith("metadata.csv"))).decode("utf-8")
    else:
        texte = p.read_text(encoding="utf-8")
    for r in csv.DictReader(io.StringIO(texte)):
        yield r.get("text_fr", ""), r.get("transcription", "")


def _versets(path: Path) -> dict[tuple, str]:
    racine = ET.parse(path).getroot()
    out = {}
    for livre in racine.iter("book"):
        for ch in livre.iter("chapter"):
            for v in ch.iter("verse"):
                out[(livre.get("number"), ch.get("number"), v.get("number"))] = "".join(v.itertext())
    return out


def bible_alignee(fr_xml: Path, bci_xml: Path):
    """Versets de même référence (livre, chapitre, verset) : (français, baoulé).

    Décision du valideur (2026-10-24) : la Bible ne sert que mot à mot (statistiques de
    paires de mots), jamais comme phrases du corpus ni comme réponse."""
    fr, bci = _versets(fr_xml), _versets(bci_xml)
    for ref in fr.keys() & bci.keys():
        yield fr[ref], bci[ref]


def textes_tsv(path: Path, colonne: str):
    with open(path, encoding="utf-8") as f:
        yield from (r[colonne] for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def textes_smol(*paths: Path):
    for p in paths:
        for r in _jsonl(p):
            yield from r.get("trgs", [])


# ── Téléchargement des sources ouvertes (dossier local, jamais versionné) ──

HF = "https://huggingface.co/datasets"
TELECHARGEABLES = {
    "wiktionnaire_bci.jsonl": "https://kaikki.org/frwiktionary/Baoul%C3%A9/kaikki.org-dictionary-Baoul%C3%A9.jsonl",
    "gatitos_en_bci.jsonl": f"{HF}/google/smol/resolve/main/gatitos/en_bci.jsonl",
    "gatitos_en_fr.jsonl": f"{HF}/google/smol/resolve/main/gatitos/en_fr.jsonl",
    "smolsent_en_bci.jsonl": f"{HF}/google/smol/resolve/main/smolsent/en_bci.jsonl",
    "smoldoc_en_bci.jsonl": f"{HF}/google/smol/resolve/main/smoldoc/en_bci.jsonl",
    "panlex_bci_eng.jsonl": f"{HF}/ec5ug/chikhapo/resolve/main/data/bci_eng.jsonl",
    "fineweb2_bci.parquet": f"{HF}/HuggingFaceFW/fineweb-2/resolve/main/data/bci_Latn/train/000_00000.parquet",
    "finepdfs_bci.parquet": f"{HF}/HuggingFaceFW/finepdfs/resolve/main/data/bci_Latn/train/000_00000.parquet",
    "glotcc_bci.parquet": f"{HF}/cis-lmu/GlotCC-V1/resolve/main/v1.0/bci-Latn/bci-Latn_0.parquet",
    "madlad_bci.csv": f"{HF}/AfriSpeech/madlad-91-african/resolve/main/Baoul%C3%A9_bci_v2.csv",
    "zenodo_bci.zip": "https://zenodo.org/records/6705861/files/bci-datasets.zip?download=1",
    "bible_bci_1998.xml": "https://raw.githubusercontent.com/Beblia/Holy-Bible-XML-Format/master/Baoule1998Bible.xml",
    "bible_fr_lsg1910.xml": "https://raw.githubusercontent.com/Beblia/Holy-Bible-XML-Format/master/FrenchBible.xml",
}


def telecharger(dossier: Path) -> list[str]:
    """Télécharge les sources ouvertes absentes. Common Voice (compte Mozilla), la dictée
    et les validations du locuteur (exports de l'atelier) se déposent à la main."""
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    faits = []
    for nom, url in TELECHARGEABLES.items():
        cible = dossier / nom
        if not cible.exists():
            urllib.request.urlretrieve(url, cible)
            faits.append(nom)
    if not (dossier / "web_bci.txt").exists():
        assembler_web(dossier)
        faits.append("web_bci.txt")
    return faits


def assembler_web(dossier: Path) -> int:
    """Un document par ligne, les 4 corpus web réunis : ils recoupent les mêmes sites
    (jw.org surtout), ils ne comptent donc que pour UNE attestation. Lecture parquet :
    pyarrow requis (outil de préparation, hors dépendances de l'API)."""
    import pyarrow.parquet as pq

    dossier = Path(dossier)
    docs = []
    for nom, col in (("fineweb2_bci.parquet", "text"), ("finepdfs_bci.parquet", "text"), ("glotcc_bci.parquet", "content")):
        docs.extend(pq.read_table(dossier / nom, columns=[col]).column(col).to_pylist())
    csv.field_size_limit(10**9)
    with open(dossier / "madlad_bci.csv", encoding="utf-8") as f:
        docs.extend(r["local"] for r in csv.DictReader(f))
    lignes = [" ".join(str(d).split()) for d in docs if d and str(d).strip()]
    _exige("web", len(lignes))
    (dossier / "web_bci.txt").write_text("\n".join(lignes), encoding="utf-8")
    return len(lignes)
