"""Wourri — Candidats mots-clés baoulé tirés de sources ouvertes, à valider dans l'atelier (ADR-0045).

Source (licence ouverte, citée sur chaque fiche) : Wiktionnaire français, entrées baoulé
(via kaikki.org/wiktextract) — CC BY-SA 4.0.

Chaque mot est rattaché à un concept du NLU par le NLU français, qui lit sa définition
française : aucune table écrite à la main. Ce ne sont que des CANDIDATS : comme ceux de la
dictée, ils n'entrent au dictionnaire qu'une fois acceptés par le locuteur natif dans
l'atelier (même circuit, type `mot_cle`). Les variantes de parler ou d'orthographe
(mannda / banana, awie / avie) sont précisément ce que le locuteur tranche.

Écarté (mesuré le 2026-10-22) : le lexique Google SMOL/GATITOS (anglais → baoulé, CC BY 4.0)
est précieux (variantes : anana, manda, koton, n'zue…), mais rattacher un mot anglais isolé
à un concept par proximité de sens est trop bruité (« ok » → sésame, « three » → arachide,
même au seuil 0,9). À reprendre avec un pont anglais → français fiable.

Usage :
    python scripts/baoule_lexique_ouvert.py --wiktionnaire wikt.jsonl --deja atelier_import.json \\
        --out lexique_ouvert_atelier.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.nlu.baoule_text import prepare_bci  # noqa: E402

CONCEPTS_FR = ROOT / "dictionnaires" / "nlu_concepts.json"
# Familles de concepts utiles à une question agricole (préfixes du NLU, pas une liste de mots).
FAMILLES = ("CULTURE_", "ACTION_", "PROBLEME_", "ENGRAIS_", "ANIMAL_")
WIKT = "Wiktionnaire (CC BY-SA 4.0)"


def lire_jsonl(path) -> list[dict]:
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def utiles(concepts) -> list[str]:
    return [c for c in concepts if c.startswith(FAMILLES)]


def depuis_wiktionnaire(rows, nlu_fr) -> list[dict]:
    """Un candidat par (mot, concept) quand la définition française nomme un concept utile."""
    out = []
    for r in rows:
        mot = (r.get("word") or "").strip()
        gloses = [g for s in r.get("senses", []) for g in s.get("glosses", [])]
        if not mot or not gloses:
            continue
        definition = " ; ".join(gloses)
        for c in utiles(nlu_fr.process(definition).concepts):
            out.append({"mot": mot, "concept": c, "source": WIKT, "sens": definition[:120]})
    return out


def lot_atelier(candidats, labels_fr, deja=()) -> list[dict]:
    """Fiches `mot_cle` pour l'atelier, sans doublon ni mot déjà proposé (même concept, même mot)."""
    vus = {(e.get("concept_nlu"), prepare_bci(e.get("text_local"))) for e in deja if e.get("kind") == "mot_cle"}
    out = []
    for c in candidats:
        cle = (c["concept"], prepare_bci(c["mot"]))
        if not cle[1] or cle in vus:
            continue
        vus.add(cle)
        out.append({
            "kind": "mot_cle", "id": f"{c['concept']}:{cle[1]}",
            "text_local": c["mot"], "text_fr": labels_fr.get(c["concept"], c["concept"]),
            "concept_nlu": c["concept"], "notes": f"source : {c['source']} — {c['sens']}",
        })
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--wiktionnaire", required=True, help="JSONL kaikki.org (Wiktionnaire, baoulé)")
    ap.add_argument("--deja", help="lot déjà importé dans l'atelier (doublons écartés)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    from app.services.nlu.nlu_service import NLUService

    base = json.loads(CONCEPTS_FR.read_text(encoding="utf-8"))
    labels_fr = {c: v.get("label_fr", c) for c, v in base["concepts"].items()}
    candidats = depuis_wiktionnaire(lire_jsonl(args.wiktionnaire), NLUService(str(CONCEPTS_FR), min_confidence=0.0))
    deja = json.loads(Path(args.deja).read_text(encoding="utf-8")) if args.deja else []
    lot = lot_atelier(candidats, labels_fr, deja)
    Path(args.out).write_text(json.dumps(lot, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Candidats : {len(candidats)} | lot pour l'atelier : {len(lot)} (doublons et mots déjà proposés écartés)")


if __name__ == "__main__":
    main()
