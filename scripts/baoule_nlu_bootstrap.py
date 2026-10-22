"""Wourri — Amorçage du NLU baoulé (bci) à partir de la dictée validée d'esse.

Même méthode que le dioula : le sens passe par des CONCEPTS (culture, action,
problème...) puis par l'intention calculée par le moteur existant
(`IntentClassifier`, même `intents` que `dictionnaires/nlu_concepts.json`) —
jamais par une traduction mot à mot.

Entrée : l'export de l'écran Dictée (ADR-0035), ZIP ou `metadata.csv` :
`file_name, transcription (baoulé), language, filiere, text_fr`. Les phrases
baoulé ont été écrites et validées par un locuteur natif ; rien n'est inventé ici.

Étapes :
1. Questions / réponses : une phrase est une question si sa traduction finit
   par « ? ». Les réponses sont reliées à leur question, filière par filière,
   par un alignement qui garde l'ordre de l'export et maximise la proximité de
   sens des traductions françaises (modèle de phrases multilingue).
2. Étiquettes : concepts du NLU français sur `text_fr` + cultures de la filière
   (le NLU français lu sur le nom de la filière : aucune table écrite à la main).
   L'intention d'une question est celle du NLU français.
3. Mots-clés candidats : un mot (ou une paire de mots) baoulé est candidat pour
   un concept s'il apparaît dans au moins `min_support` phrases portant ce
   concept et si au moins `min_precision` des phrases qui le contiennent le
   portent. Ce ne sont que des CANDIDATS : le locuteur natif valide la liste.
4. Mesure honnête : validation croisée (k plis) sur les questions — les
   mots-clés sont appris sans les questions mesurées.

Usage :
    python scripts/baoule_nlu_bootstrap.py <export.zip|metadata.csv> --out <dossier>
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
CONCEPTS_FR = ROOT / "dictionnaires" / "nlu_concepts.json"

# Même mise en forme que le NLU baoulé de l'API (apostrophes et tons, ADR-0045).
from app.services.nlu.baoule_text import prepare_bci, tokens_bci  # noqa: E402,F401


def read_export(path) -> list[dict]:
    """Lignes de l'export, dans l'ordre : ZIP de l'écran Dictée ou metadata.csv."""
    path = Path(path)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith("metadata.csv"))
            text = z.read(name).decode("utf-8")
    else:
        text = path.read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def is_question(row) -> bool:
    return row["text_fr"].strip().endswith("?")


def align(questions_fr: list[str], answers_fr: list[str], similarity) -> list[tuple[int, int, float]]:
    """Relie chaque réponse à une question distincte en gardant l'ordre.

    Programmation dynamique : maximise la somme des similarités ; la réponse j
    suit la réponse j-1, donc sa question suit celle de j-1. Exige
    len(answers) <= len(questions). Retourne [(index question, index réponse, similarité)].
    """
    n, m = len(questions_fr), len(answers_fr)
    if m > n:
        raise ValueError(f"{m} réponses pour {n} questions : alignement impossible")
    sim = similarity(questions_fr, answers_fr)  # n x m
    neg = float("-inf")
    best = [[neg] * (m + 1) for _ in range(n + 1)]
    take = [[False] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        best[i][0] = 0.0
    for i in range(1, n + 1):
        for j in range(1, min(i, m) + 1):
            skip = best[i - 1][j]
            pair = best[i - 1][j - 1] + sim[i - 1][j - 1]
            if pair >= skip:
                best[i][j], take[i][j] = pair, True
            else:
                best[i][j] = skip
    out, i, j = [], n, m
    while j > 0:
        if take[i][j]:
            out.append((i - 1, j - 1, float(sim[i - 1][j - 1])))
            j -= 1
        i -= 1
    return out[::-1]


def pair_qa(rows, similarity) -> list[dict]:
    """Paires question → réponse, filière par filière (question sans réponse : a=None)."""
    by_filiere: dict[str, dict[str, list]] = defaultdict(lambda: {"q": [], "a": []})
    for idx, row in enumerate(rows):
        by_filiere[row["filiere"]]["q" if is_question(row) else "a"].append(idx)
    pairs = []
    for filiere, d in by_filiere.items():
        qs, ans = d["q"], d["a"]
        linked = {}
        method = "position" if len(qs) == len(ans) else "alignement"
        if ans:
            fr_q = [rows[i]["text_fr"] for i in qs]
            fr_a = [rows[i]["text_fr"] for i in ans]
            for qi, ai, s in align(fr_q, fr_a, similarity):
                linked[qs[qi]] = (ans[ai], s)
        for q in qs:
            a, s = linked.get(q, (None, None))
            pairs.append({"filiere": filiere, "q": q, "a": a, "sim": s, "method": method})
    return pairs


def label_rows(rows, nlu_fr) -> list[dict]:
    """Concepts (NLU français sur text_fr + cultures de la filière) et intention."""
    labels = []
    for row in rows:
        res = nlu_fr.process(row["text_fr"])
        filiere = nlu_fr.process(row["filiere"].replace("|", " "))
        cultures_filiere = [c for c in filiere.concepts if c.startswith("CULTURE_")]
        concepts = list(dict.fromkeys(list(res.concepts) + cultures_filiere))
        labels.append({"concepts": concepts, "intent": res.intent, "cultures_filiere": cultures_filiere})
    return labels


def _grams(tokens: list[str]) -> set[str]:
    return set(tokens) | {f"{a} {b}" for a, b in zip(tokens, tokens[1:])}


def keyword_candidates(texts, concept_sets, min_support=2, min_precision=0.75) -> dict[str, list[tuple]]:
    """{concept: [(mot, phrases avec concept, phrases avec le mot, précision)]}, mieux classés d'abord."""
    doc_grams = [_grams(tokens_bci(t)) for t in texts]
    n_gram = Counter(g for gs in doc_grams for g in gs)
    n_gram_concept: dict[str, Counter] = defaultdict(Counter)
    for gs, cs in zip(doc_grams, concept_sets):
        for c in cs:
            n_gram_concept[c].update(gs)
    out = {}
    for c, counter in n_gram_concept.items():
        cands = [
            (g, k, n_gram[g], k / n_gram[g])
            for g, k in counter.items()
            if k >= min_support and k / n_gram[g] >= min_precision
        ]
        if cands:
            out[c] = sorted(cands, key=lambda x: (-x[3], -x[1], x[0]))
    return out


def build_config(candidates, base_config) -> dict:
    """Config NLU baoulé : mêmes intents que le dioula, mots-clés baoulé par concept."""
    return {
        "version": "bci-amorcage",
        "concepts": {c: {"keywords": [g for g, *_ in cands]} for c, cands in candidates.items()},
        "intents": base_config["intents"],
        "out_of_scope_response": base_config.get("out_of_scope_response", {}),
    }


def atelier_entries(candidates, pairs, rows, concept_labels) -> list[dict]:
    """Lot à importer dans l'atelier (onglet « Ajouter », ADR-0045), à faire valider par
    le locuteur dans « À accepter » :
    - un `mot_cle` par mot candidat : « mot » veut dire « libellé du concept » ;
    - une `paire_qr` par paire reliée par le SENS (alignement) — celles reliées par leur
      position dans l'export n'ont pas besoin de validation.
    """
    out = []
    for concept in sorted(candidates):
        for mot, k, _, _ in candidates[concept]:
            out.append({
                "kind": "mot_cle", "id": f"{concept}:{mot}",
                "text_local": mot, "text_fr": concept_labels.get(concept, concept),
                "concept_nlu": concept, "notes": f"vu dans {k} questions de la dictée",
            })
    for p in pairs:
        if p["method"] != "alignement" or p["a"] is None:
            continue
        q, a = rows[p["q"]], rows[p["a"]]
        out.append({
            "kind": "paire_qr", "id": f"paire:{p['q']}:{p['a']}",
            "text_local": q["transcription"], "text_fr": q["text_fr"],
            "reponse_bci": a["transcription"], "reponse_fr": a["text_fr"],
            "notes": f"{p['filiere']} — reliée par le sens",
        })
    return out


def nlu_from_config(config):
    from app.services.nlu.nlu_service import NLUService

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False)
    return NLUService(f.name, min_confidence=0.0)


def cross_validate(texts, labels, base_config, k=5, **kw) -> dict:
    """Intention et culture retrouvées sur des questions jamais vues par l'amorçage."""
    n = len(texts)
    culture_ok = intent_ok = both_ok = n_cult = 0
    for fold in range(k):
        test = [i for i in range(n) if i % k == fold]
        train = [i for i in range(n) if i % k != fold]
        cands = keyword_candidates([texts[i] for i in train], [labels[i]["concepts"] for i in train], **kw)
        nlu = nlu_from_config(build_config(cands, base_config))
        for i in test:
            res = nlu.process(prepare_bci(texts[i]))
            pred_cult = next((c for c in res.concepts if c.startswith("CULTURE_")), None)
            gold_cult = labels[i]["cultures_filiere"]
            c_ok = (pred_cult in gold_cult) if gold_cult else pred_cult is None
            i_ok = res.intent == labels[i]["intent"]
            n_cult += bool(gold_cult)
            culture_ok += bool(gold_cult) and c_ok
            intent_ok += i_ok
            both_ok += c_ok and i_ok
    return {"n": n, "k": k, "culture_ok": culture_ok, "n_avec_culture": n_cult,
            "intent_ok": intent_ok, "intent_et_culture_ok": both_ok}


def _st_similarity():
    from sentence_transformers import SentenceTransformer, util

    model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

    def similarity(a, b):
        return util.cos_sim(model.encode(a), model.encode(b)).tolist()
    return similarity


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("export", help="ZIP de l'écran Dictée ou metadata.csv")
    ap.add_argument("--out", required=True, help="dossier de sortie (fichiers à valider)")
    ap.add_argument("--min-support", type=int, default=2)
    ap.add_argument("--min-precision", type=float, default=0.75)
    args = ap.parse_args(argv)

    from app.services.nlu.nlu_service import NLUService

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = read_export(args.export)
    base = json.loads(CONCEPTS_FR.read_text(encoding="utf-8"))
    nlu_fr = NLUService(str(CONCEPTS_FR), min_confidence=0.0)
    labels = label_rows(rows, nlu_fr)

    pairs = pair_qa(rows, _st_similarity())
    with (out / "paires_questions_reponses.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["filiere", "methode", "similarite", "question_bci", "question_fr", "reponse_bci", "reponse_fr"])
        for p in pairs:
            q = rows[p["q"]]
            a = rows[p["a"]] if p["a"] is not None else None
            w.writerow([p["filiere"], p["method"], "" if p["sim"] is None else f"{p['sim']:.2f}",
                        q["transcription"], q["text_fr"],
                        a["transcription"] if a else "", a["text_fr"] if a else ""])

    q_idx = [i for i, r in enumerate(rows) if is_question(r)]
    texts = [rows[i]["transcription"] for i in q_idx]
    q_labels = [labels[i] for i in q_idx]
    kw = {"min_support": args.min_support, "min_precision": args.min_precision}
    cands = keyword_candidates(texts, [lab["concepts"] for lab in q_labels], **kw)
    with (out / "mots_cles_candidats.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["concept", "mot_bci", "phrases_avec_concept", "phrases_avec_mot", "precision", "valide (oui/non)"])
        for c in sorted(cands):
            for g, k, n, p in cands[c]:
                w.writerow([c, g, k, n, f"{p:.2f}", ""])
    (out / "nlu_concepts_bci_candidat.json").write_text(
        json.dumps(build_config(cands, base), ensure_ascii=False, indent=1), encoding="utf-8")
    labels_fr = {c: v.get("label_fr", c) for c, v in base["concepts"].items()}
    lot = atelier_entries(cands, pairs, rows, labels_fr)
    (out / "atelier_import.json").write_text(json.dumps(lot, ensure_ascii=False, indent=1), encoding="utf-8")

    cv = cross_validate(texts, q_labels, base, **kw)
    report = (
        f"Phrases : {len(rows)} ({len(q_idx)} questions, {len(rows) - len(q_idx)} réponses)\n"
        f"Paires question->réponse : {sum(p['a'] is not None for p in pairs)} "
        f"(dont {sum(p['method'] == 'alignement' and p['a'] is not None for p in pairs)} par alignement de sens)\n"
        f"Concepts avec mots-clés candidats : {len(cands)} ; mots-clés : {sum(len(v) for v in cands.values())}\n"
        f"Lot pour l'atelier (atelier_import.json) : {sum(e['kind'] == 'mot_cle' for e in lot)} mots-clés, "
        f"{sum(e['kind'] == 'paire_qr' for e in lot)} paires à valider\n"
        f"Validation croisée ({cv['k']} plis, questions jamais vues) :\n"
        f"  culture retrouvée : {cv['culture_ok']}/{cv['n_avec_culture']}\n"
        f"  intention retrouvée : {cv['intent_ok']}/{cv['n']}\n"
        f"  intention ET culture : {cv['intent_et_culture_ok']}/{cv['n']}\n"
    )
    (out / "rapport.txt").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
