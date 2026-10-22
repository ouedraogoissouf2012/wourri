"""Wourri — Construit le NLU baoulé et le corpus de réponses baoulé (ADR-0045).

Produit les deux fichiers lus par l'API :
- `dictionnaires/nlu_concepts_bci.json` : mots-clés baoulé par concept (les intents
  restent ceux de nlu_concepts.json, jamais recopiés) ;
- `dictionnaires/corpus_ivr_bci.json` : paires question → réponse de la dictée, natives,
  étiquetées (intention, cultures), avec le fichier audio de la réponse.

Deux modes :
- validé (par défaut) : uniquement ce que le locuteur a ACCEPTÉ dans l'atelier
  (`/tasks/validations`, texte éventuellement corrigé) ; une paire reliée par le sens
  n'entre au corpus que si elle a été acceptée ;
- `--provisoire` : les candidats de l'amorçage, pour développer et tester avant la
  validation. Le fichier porte `"statut": "provisoire"` : à ne jamais déployer.

Mesure : les questions de la dictée, bruitées artificiellement au taux d'erreur de
l'ASR, doivent retrouver leur propre réponse. Mesure optimiste (les questions ont servi
à l'amorçage) : le vrai test reste des questions vocales nouvelles.

Usage :
    python scripts/baoule_nlu_build.py <export.zip> --provisoire
    python scripts/baoule_nlu_build.py <export.zip> --mots-cles mots.json --paires paires.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import baoule_nlu_bootstrap as boot  # noqa: E402

DICTIONNAIRES = ROOT / "dictionnaires"
ACCEPTE = "admin_accepted"


def accepted(entries) -> list[dict]:
    """Éléments acceptés par le locuteur (réponse de /tasks/validations ou liste)."""
    if isinstance(entries, dict):
        entries = entries.get("entries", [])
    return [e for e in entries if e.get("status") == ACCEPTE]


def keywords_from_validations(mots_cles) -> dict[str, list[str]]:
    """{concept: [mot baoulé normalisé]} depuis les mots-clés acceptés (texte corrigé compris)."""
    out: dict[str, list[str]] = {}
    for e in accepted(mots_cles):
        concept = (e.get("meta") or {}).get("concept_nlu")
        mot = boot.prepare_bci(e.get("text_local"))
        if concept and mot and mot not in out.setdefault(concept, []):
            out[concept].append(mot)
    return out


def accepted_pair_ids(paires) -> set[str]:
    """Identifiants `paire:<q>:<a>` des paires acceptées (external_id `paire_qr:paire:q:a`)."""
    ids = set()
    for e in accepted(paires):
        ext = (e.get("meta") or {}).get("external_id") or ""
        ids.add(ext.split(":", 1)[1] if ext.startswith("paire_qr:") else ext)
    return ids


def nlu_file(keywords: dict[str, list[str]], labels_fr: dict, statut: str) -> dict:
    return {
        "version": f"bci-{date.today().isoformat()}",
        "statut": statut,
        "description": "NLU baoulé (ADR-0045) : mots-clés par concept ; intents = nlu_concepts.json",
        "concepts": {c: {"label_fr": labels_fr.get(c, c), "keywords": kws} for c, kws in sorted(keywords.items())},
    }


def corpus_entries(rows, labels, pairs, keep_alignement) -> list[dict]:
    """Une entrée par paire gardée : position toujours, alignement si `keep_alignement(id)`."""
    out = []
    for p in pairs:
        if p["a"] is None:
            continue
        pid = f"paire:{p['q']}:{p['a']}"
        if p["method"] == "alignement" and not keep_alignement(pid):
            continue
        q, a, lab = rows[p["q"]], rows[p["a"]], labels[p["q"]]
        cultures = lab["cultures_filiere"] or [c for c in lab["concepts"] if c.startswith("CULTURE_")]
        out.append({
            "id": f"bci-q{p['q']}", "filiere": p["filiere"],
            "question_bci": q["transcription"], "question_fr": q["text_fr"],
            "reponse_bci": a["transcription"], "reponse_fr": a["text_fr"],
            "intent": lab["intent"], "cultures": cultures,
            "audio_reponse": a["file_name"], "appariement": p["method"],
        })
    return out


def bruiter(text: str, taux: float, rng: random.Random, alphabet: str) -> str:
    """Erreurs de caractères au hasard (substitution, suppression, insertion) au taux donné."""
    out = []
    for ch in text:
        if ch.isalpha() and rng.random() < taux:
            op = rng.choice(("sub", "del", "ins"))
            if op == "sub":
                out.append(rng.choice(alphabet))
            elif op == "ins":
                out.extend((ch, rng.choice(alphabet)))
            continue
        out.append(ch)
    return "".join(out)


def mesurer(corpus, nlu, taux: float, seed=0) -> dict:
    """Part des questions du corpus (bruitées) qui retrouvent leur propre réponse."""
    from app.services import baoule_ivr

    rng = random.Random(seed)
    alphabet = "".join(sorted({c for e in corpus for c in e["question_bci"].lower() if c.isalpha()}))
    bonne = mauvaise = aucune = 0
    for e in corpus:
        texte = bruiter(e["question_bci"], taux, rng, alphabet) if taux else e["question_bci"]
        res = nlu.process(boot.prepare_bci(texte))
        t = baoule_ivr.chercher(texte, res.intent, res.concepts, corpus=corpus)
        if t is None:
            aucune += 1
        elif t.entry["id"] == e["id"]:
            bonne += 1
        else:
            mauvaise += 1
    return {"taux": taux, "n": len(corpus), "bonne": bonne, "mauvaise": mauvaise, "aucune": aucune}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("export", help="ZIP de l'écran Dictée ou metadata.csv")
    ap.add_argument("--provisoire", action="store_true", help="candidats de l'amorçage (jamais déployé)")
    ap.add_argument("--mots-cles", help="JSON de /tasks/validations?kind=mot_cle (atelier)")
    ap.add_argument("--paires", help="JSON de /tasks/validations?kind=paire_qr (atelier)")
    ap.add_argument("--out", default=str(DICTIONNAIRES), help="dossier de sortie")
    ap.add_argument("--taux-bruit", type=float, default=0.19, help="CER simulé (fiche 0006 : 18,7 %)")
    args = ap.parse_args(argv)
    if not args.provisoire and not (args.mots_cles and args.paires):
        ap.error("--mots-cles et --paires requis (ou --provisoire)")

    from app.services.nlu.nlu_service import NLUService, build_bci_config

    rows = boot.read_export(args.export)
    base = json.loads(boot.CONCEPTS_FR.read_text(encoding="utf-8"))
    labels_fr = {c: v.get("label_fr", c) for c, v in base["concepts"].items()}
    labels = boot.label_rows(rows, NLUService(str(boot.CONCEPTS_FR), min_confidence=0.0))
    pairs = boot.pair_qa(rows, boot._st_similarity())

    if args.provisoire:
        q_idx = [i for i, r in enumerate(rows) if boot.is_question(r)]
        cands = boot.keyword_candidates([rows[i]["transcription"] for i in q_idx],
                                        [labels[i]["concepts"] for i in q_idx])
        keywords = {c: [g for g, *_ in v] for c, v in cands.items()}
        statut, keep = "provisoire", (lambda pid: True)
    else:
        load = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))  # noqa: E731
        keywords = keywords_from_validations(load(args.mots_cles))
        ok_pairs = accepted_pair_ids(load(args.paires))
        statut, keep = "valide", (lambda pid: pid in ok_pairs)

    nlu_json = nlu_file(keywords, labels_fr, statut)
    corpus = corpus_entries(rows, labels, pairs, keep)
    out = Path(args.out)
    (out / "nlu_concepts_bci.json").write_text(json.dumps(nlu_json, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out / "corpus_ivr_bci.json").write_text(json.dumps(
        {"version": nlu_json["version"], "statut": statut, "entries": corpus}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")

    nlu = NLUService(config=build_bci_config(nlu_json, base), min_confidence=0.0)
    print(f"Statut : {statut} | concepts : {len(keywords)} | mots-clés : {sum(map(len, keywords.values()))} "
          f"| entrées du corpus : {len(corpus)}")
    for taux in (0.0, args.taux_bruit):
        m = mesurer(corpus, nlu, taux)
        print(f"Questions bruitées à {taux:.0%} : bonne réponse {m['bonne']}/{m['n']}, "
              f"mauvaise {m['mauvaise']}, aucune (repli honnête) {m['aucune']}")


if __name__ == "__main__":
    main()
