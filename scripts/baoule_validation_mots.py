"""Wourri — Validation multi-sources des mots baoulé, méthode du dioula (ADR-0046).

Pour chaque concept du NLU, ses mots français (libellé + mots-clés français) sont
cherchés dans toutes les sources (scripts/baoule_sources.py). Chaque mot baoulé proposé
reçoit le poids de chaque source qui le propose (une source compte une fois par concept),
plus un point par texte baoulé où sa graphie existe. Score sur 20, seuils du dioula
(tools/bambara_validator.py) :
- 8/20 et plus : validé multi-sources ;
- 5 à 7/20     : envoyé au locuteur, dans l'atelier (fiche `mot_cle`) ;
- moins de 5   : écarté (gardé dans le rapport, avec ses sources).

Les mots français d'un concept sont repérés dans les données (vocabulaire de la Bible
française, de GATITOS et de la dictée), sans liste écrite à la main ; les homographes
déclarés dans nlu_concepts.json (« mais », « fini »…) ne sont jamais cherchés (ADR-0041).

Usage :
    python scripts/baoule_validation_mots.py --sources <dossier> --dictee dictee.zip \\
        --common-voice validated_sentences.tsv --locuteur validations.json --out <dossier>
    python scripts/baoule_validation_mots.py --telecharger <dossier>
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import baoule_sources as src  # noqa: E402

CONCEPTS_FR = ROOT / "dictionnaires" / "nlu_concepts.json"
SCORE_MAX = 20
SEUIL_VALIDE, SEUIL_LOCUTEUR = 8, 5
POIDS = {"locuteur": 5, "dictee": 3, "wiktionnaire": 3, "gatitos": 2, "panlex": 2, "bible": 1,
         "common_voice": 1, "zenodo": 1, "smol": 1, "web": 1}
assert sum(POIDS.values()) == SCORE_MAX
# Sources qui donnent un SENS (les autres attestent seulement que la graphie existe).
SENS = ("locuteur", "dictee", "wiktionnaire", "gatitos", "panlex", "bible")
# Sources de sens fortes : locuteur natif, ou sens lu en français sans pivot anglais.
FORTES = {"locuteur", "dictee", "wiktionnaire"}


def mots_outils(textes, seuil: float = 0.03) -> set[str]:
    """Mots présents dans plus de `seuil` des phrases (n, be, ɔ, sran, like…) : mots-outils
    ou trop généraux pour traduire un concept. Mesurés sur les données, pas listés à la main."""
    phrases = [p for t in textes for p in re.split(r"[.!?]", t) if len(p.split()) >= 3]
    df = Counter(w for p in phrases for w in set(src.toks_bci(p)))
    return {w for w, n in df.items() if n / max(len(phrases), 1) >= seuil}


def forme_utile(forme: str, outils: set[str]) -> bool:
    """Écarte chiffres, lettres seules, mots-outils, et n-grammes bordés d'un mot-outil (« duo n »)."""
    toks = forme.split()
    if not toks or any(t.isdigit() or len(t) < 2 for t in toks):
        return False
    return toks[0] not in outils and toks[-1] not in outils


def decider(sources: set[str]) -> tuple[int, int, str]:
    """(score, score de sens, décision). Les attestations prouvent qu'un mot est du baoulé,
    pas qu'il traduit le concept : valider exige deux sources de sens dont une forte ; aller
    au locuteur exige au moins un sens (2 points : la Bible seule ne suffit pas)."""
    score = sum(POIDS[n] for n in sources)
    sens = sum(POIDS[n] for n in sources if n in SENS)
    n_sens = sum(1 for n in sources if n in SENS)
    if score >= SEUIL_VALIDE and n_sens >= 2 and sources & FORTES:
        return score, sens, "valide"
    if score >= SEUIL_LOCUTEUR and sens >= 2:
        return score, sens, "locuteur"
    return score, sens, "ecarte"


def mots_francais(concept: dict, vocab_fr: set[str], homographes: set[str]) -> list[str]:
    """Libellé découpé (« banane / plantain ») + mots-clés dont tous les mots sont français."""
    morceaux = re.split(r"[/,()]", concept.get("label_fr", ""))
    out = [m.strip() for m in morceaux if m.strip()]
    for kw in concept.get("keywords", []):
        mots = src.mots_fr(kw)
        if mots and all(m in vocab_fr for m in mots):
            out.append(kw)
    vus, propres = set(), []
    for m in out:
        f = src.forme_fr(m)
        if f and f not in vus and f not in homographes:
            vus.add(f)
            propres.append(m)
    return propres


def voter(mots: list[str], propositions, attestations, outils: set[str] = frozenset()) -> list[dict]:
    """Candidats d'un concept, du meilleur au moins bon : score, sources, décision."""
    cands: dict[str, dict] = {}
    for s in propositions:
        for mot in mots:
            for forme, graphie in s.proposer(mot).items():
                if not forme_utile(forme, outils):
                    continue
                c = cands.setdefault(forme, {"forme": forme, "graphie": graphie, "sources": set(), "mots_fr": set()})
                c["sources"].add(s.nom)
                c["mots_fr"].add(mot)
    for c in cands.values():
        for a in attestations:
            if a.atteste(c["forme"]):
                c["sources"].add(a.nom)
        c["score"], c["sens"], c["decision"] = decider(c["sources"])
        c["sources"], c["mots_fr"] = sorted(c["sources"]), sorted(c["mots_fr"])
    return sorted(cands.values(), key=lambda c: (-c["score"], -c["sens"], c["forme"]))


def lot_atelier(rapport: dict, labels_fr: dict, deja=()) -> list[dict]:
    """Fiches `mot_cle` des candidats à 5–7/20, sans ceux déjà proposés au locuteur
    (`deja` : lots déjà importés dans l'atelier ; même concept, même forme)."""
    vus = {(e.get("concept_nlu"), src.forme_bci(e.get("text_local"))) for e in deja if e.get("kind") == "mot_cle"}
    out = []
    for concept, bloc in rapport["concepts"].items():
        for c in bloc["candidats"]:
            if c["decision"] == "locuteur" and (concept, c["forme"]) not in vus:
                out.append({"kind": "mot_cle", "id": f"{concept}:{c['forme']}", "text_local": c["graphie"],
                            "text_fr": labels_fr.get(concept, concept), "concept_nlu": concept,
                            "notes": f"multi-sources {c['score']}/{SCORE_MAX} : {', '.join(c['sources'])}"})
    return out


def _texte_zip(zip_path: Path, suffixe: str) -> str:
    with zipfile.ZipFile(zip_path) as z:
        return z.read(next(n for n in z.namelist() if n.endswith(suffixe))).decode("utf-8")


def charger(dossier: Path, dictee: Path, common_voice: Path, locuteur: Path | None):
    """Sources déclarées (une source vide lève SourceVide). `locuteur=None` : source
    désactivée explicitement (consigné dans le rapport)."""
    d = Path(dossier)
    gat_fr, gat_bci = d / "gatitos_en_fr.jsonl", d / "gatitos_en_bci.jsonl"
    props = [
        src.Cooccurrence("dictee", POIDS["dictee"], src.dictee(dictee)),
        src.Dictionnaire("wiktionnaire", POIDS["wiktionnaire"], src.wiktionnaire(d / "wiktionnaire_bci.jsonl")),
        src.Dictionnaire("gatitos", POIDS["gatitos"], src.gatitos_fr_bci(gat_fr, gat_bci)),
        src.Dictionnaire("panlex", POIDS["panlex"], src.panlex_fr_bci(d / "panlex_bci_eng.jsonl", gat_fr)),
        src.Cooccurrence("bible", POIDS["bible"],
                         src.bible_alignee(d / "bible_fr_lsg1910.xml", d / "bible_bci_1998.xml")),
    ]
    if locuteur is not None:
        props.insert(0, src.Dictionnaire("locuteur", POIDS["locuteur"], src.validations_locuteur(locuteur)))
    zen = list(csv.DictReader(io.StringIO(_texte_zip(d / "zenodo_bci.zip", "transcription.tsv")), delimiter="\t"))
    web = (d / "web_bci.txt").read_text(encoding="utf-8").splitlines()
    attest = [
        src.Attestation("common_voice", src.textes_tsv(common_voice, "sentence")),
        src.Attestation("zenodo", (r.get("bci", "") for r in zen)),
        src.Attestation("smol", src.textes_smol(d / "smolsent_en_bci.jsonl", d / "smoldoc_en_bci.jsonl")),
        src.Attestation("web", web, min_occ=3),
    ]
    return props, attest, mots_outils(web)


def vocabulaire_fr(dossier: Path, dictee: Path) -> set[str]:
    d = Path(dossier)
    vocab = set()
    for fr, _ in src.bible_alignee(d / "bible_fr_lsg1910.xml", d / "bible_bci_1998.xml"):
        vocab.update(src.mots_fr(fr))
    for r in src._jsonl(d / "gatitos_en_fr.jsonl"):
        for t in r["trgs"]:
            vocab.update(src.mots_fr(t))
    for fr, _ in src.dictee(dictee):
        vocab.update(src.mots_fr(fr))
    return vocab


def valider(base: dict, props, attest, vocab_fr: set[str], outils: set[str] = frozenset()) -> dict:
    homographes = {src.forme_fr(m) for m in base.get("homographes", {}).get("mots", {})}
    requetes = {c: mots_francais(v, vocab_fr, homographes) for c, v in base["concepts"].items()}
    formes = {f for mots in requetes.values() for s in props for m in mots for f in s.proposer(m)}
    for a in attest:
        a.compter(formes)
    concepts = {c: {"mots_fr": mots, "candidats": voter(mots, props, attest, outils)} for c, mots in requetes.items()}
    return {"version": f"bci-multisources-{date.today().isoformat()}", "date": date.today().isoformat(),
            "score_max": SCORE_MAX, "seuils": {"valide": SEUIL_VALIDE, "locuteur": SEUIL_LOCUTEUR},
            "mots_outils_ecartes": sorted(outils),
            "sources": {n: {"poids": p, "active": n in {s.nom for s in props + attest}} for n, p in POIDS.items()},
            "concepts": concepts}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--telecharger", help="télécharge les sources ouvertes dans ce dossier, puis s'arrête")
    ap.add_argument("--sources", help="dossier des sources (voir --telecharger)")
    ap.add_argument("--dictee", help="export ZIP de l'écran Dictée")
    ap.add_argument("--common-voice", help="validated_sentences.tsv de Common Voice (compte Mozilla)")
    ap.add_argument("--locuteur", help="JSON de /tasks/validations?kind=mot_cle")
    ap.add_argument("--sans-locuteur", action="store_true", help="désactive la source locuteur (consigné)")
    ap.add_argument("--deja", action="append", default=[], help="lot déjà importé dans l'atelier (répétable)")
    ap.add_argument("--out", help="dossier de sortie")
    args = ap.parse_args(argv)
    if args.telecharger:
        print("Téléchargés :", src.telecharger(Path(args.telecharger)) or "rien (déjà présents)")
        return
    if not (args.sources and args.dictee and args.common_voice and args.out):
        ap.error("--sources, --dictee, --common-voice et --out sont requis")
    if bool(args.locuteur) == args.sans_locuteur:
        ap.error("donner --locuteur, ou --sans-locuteur pour la désactiver explicitement")

    base = json.loads(CONCEPTS_FR.read_text(encoding="utf-8"))
    labels_fr = {c: v.get("label_fr", c) for c, v in base["concepts"].items()}
    props, attest, outils = charger(Path(args.sources), Path(args.dictee), Path(args.common_voice),
                                    None if args.sans_locuteur else Path(args.locuteur))
    rapport = valider(base, props, attest, vocabulaire_fr(Path(args.sources), Path(args.dictee)), outils)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    deja = [e for f in args.deja for e in json.loads(Path(f).read_text(encoding="utf-8"))]
    lot = lot_atelier(rapport, labels_fr, deja)
    valides = {c: [x["graphie"] for x in b["candidats"] if x["decision"] == "valide"]
               for c, b in rapport["concepts"].items()}
    ecrire = lambda nom, obj: (out / nom).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")  # noqa: E731
    ecrire("rapport_validation_bci.json", rapport)
    ecrire("lot_atelier_locuteur.json", lot)
    ecrire("mots_valides_multisources.json", {c: v for c, v in valides.items() if v})
    n = {k: sum(1 for b in rapport["concepts"].values() for x in b["candidats"] if x["decision"] == k)
         for k in ("valide", "locuteur", "ecarte")}
    print(f"Validés ≥{SEUIL_VALIDE}/20 : {n['valide']} | au locuteur {SEUIL_LOCUTEUR}–{SEUIL_VALIDE - 1}/20 : "
          f"{n['locuteur']} | écartés : {n['ecarte']} | concepts couverts : {sum(1 for v in valides.values() if v)}"
          f"/{len(valides)}")


if __name__ == "__main__":
    main()
