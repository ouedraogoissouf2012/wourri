"""Répartition de Common Voice 27 baoulé pour le 2e fine-tune (#474, ADR-0044, révision 2026-10-24).

Le test du benchmark 0003 (290 clips, 9 voix) bloquait 5 h des 11 h validées de Common Voice.
On le remplace par un test choisi par une règle écrite, aussi honnête :
- phrases de test S = les 290 phrases du test officiel : aucune voix ne les lit à l'entraînement ;
- voix de test T = parmi les 9 voix du test officiel, le sous-ensemble qui laisse le plus
  d'heures à l'entraînement en gardant au moins `MIN_CLIPS` clips et `MIN_VOIX` voix au test,
  et `MIN_VOIX_DEV` voix au dev (mesuré le 2026-10-24 : avec une seule voix au dev, 6,77 h
  d'entraînement mais un choix de version fragile ; avec deux, 5,93 h, un dev de 738 clips et
  un test de 623 clips sur 7 voix) ;
- test  = clips validés des voix T sur les phrases S ;
- dev   = clips validés des voix T sur les autres phrases : voix jamais entraînées, texte déjà
  vu. Il sert à CHOISIR la version, jamais à la noter ;
- train = clips validés des autres voix, hors phrases S.

Le modèle actuel (fiche 0006) a été entraîné sur les 3 voix du train officiel et la dictée : il
n'a vu ni les voix T ni les phrases S. Les trois modèles (départ, actuel, nouveau) se comparent
donc sur ce test, dans la même session.

Les phrases sont comparées après `normalize_text` (la normalisation de l'entraînement).
Common Voice interdit le re-hébergement : ce module lit les fichiers sur la machine, il n'écrit
aucun identifiant de voix (le manifeste ne garde que les chemins et les phrases du test).

Ce module est recopié tel quel dans le notebook GPU (cellule %%writefile) :
`python finetune/colab/sync_smoke_test_notebook.py` le resynchronise, un test le vérifie.
"""
from __future__ import annotations

import csv
import itertools
from pathlib import Path

import dictee_to_parquet as d2p

MIN_CLIPS = 290  # autant que le test du benchmark 0003
MIN_VOIX = 4
MIN_VOIX_DEV = 2  # choisir la version sur une seule voix serait fragile


def _tsv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def trouver(racine) -> Path:
    """Dossier `…/bci` d'un Common Voice extrait (celui qui contient validated.tsv)."""
    hits = sorted(Path(racine).rglob("validated.tsv"))
    if len(hits) != 1:
        raise SystemExit(f"{len(hits)} validated.tsv sous {racine} : 1 attendu (archive Common Voice extraite)")
    return hits[0].parent


def lire(dossier) -> tuple[list[dict], list[dict]]:
    """(clips validés avec durée en heures et phrase normalisée, clips du test officiel)."""
    d = Path(dossier)
    duree = {r["clip"]: int(r["duration[ms]"]) / 3.6e6 for r in _tsv(d / "clip_durations.tsv")}
    valides = []
    for r in _tsv(d / "validated.tsv"):
        valides.append({"client_id": r["client_id"], "path": r["path"], "sentence": r["sentence"],
                        "cle": d2p.normalize_text(r["sentence"]), "h": duree.get(r["path"], 0.0)})
    return valides, _tsv(d / "test.tsv")


def repartir(valides, phrases_test: set[str], voix_test: set[str]) -> dict[str, list[dict]]:
    rep = {"train": [], "dev": [], "test": []}
    for r in valides:
        if r["client_id"] in voix_test:
            rep["test" if r["cle"] in phrases_test else "dev"].append(r)
        elif r["cle"] not in phrases_test:
            rep["train"].append(r)
    return rep


def choisir_voix_test(valides, phrases_test: set[str], voix_officielles, min_clips=None,
                      min_voix=None, min_voix_dev=None) -> set[str]:
    """Sous-ensemble des voix du test officiel qui maximise les heures d'entraînement.

    À égalité : plus de clips au test, puis ordre des identifiants (résultat reproductible).
    Seuils par défaut : constantes du module, lues à l'appel."""
    min_clips = MIN_CLIPS if min_clips is None else min_clips
    min_voix = MIN_VOIX if min_voix is None else min_voix
    min_voix_dev = MIN_VOIX_DEV if min_voix_dev is None else min_voix_dev
    voix = sorted(voix_officielles)
    meilleur, cle_meilleure = None, None
    for n in range(min_voix, len(voix) + 1):
        for combo in itertools.combinations(voix, n):
            rep = repartir(valides, phrases_test, set(combo))
            if len(rep["test"]) < min_clips or len({r["client_id"] for r in rep["dev"]}) < min_voix_dev:
                continue
            cle = (round(sum(r["h"] for r in rep["train"]), 6), len(rep["test"]))
            if cle_meilleure is None or cle > cle_meilleure:
                meilleur, cle_meilleure = set(combo), cle
    if meilleur is None:
        raise SystemExit(f"aucun choix de voix ne donne {min_clips} clips et {min_voix} voix au test, "
                         f"{min_voix_dev} voix au dev")
    return meilleur


def verifier(rep, phrases_test: set[str], voix_test: set[str], autres_textes=()) -> None:
    """Arrête tout si une voix ou une phrase du test peut être apprise (Common Voice, Zenodo, dictée)."""
    fuites = [r["path"] for r in rep["train"] if r["client_id"] in voix_test or r["cle"] in phrases_test]
    fuites += [t for t in autres_textes if d2p.normalize_text(t) in phrases_test]
    if fuites:
        raise ValueError(f"{len(fuites)} élément(s) du test dans l'entraînement, ex. {fuites[:3]}")
    if not rep["test"] or not rep["dev"] or not rep["train"]:
        raise ValueError("un split est vide : vérifier l'archive Common Voice")


def preparer(dossier, autres_textes=()) -> tuple[dict[str, list[dict]], dict]:
    """Répartition vérifiée + manifeste (sans identifiant de voix)."""
    valides, test_officiel = lire(dossier)
    phrases_test = {d2p.normalize_text(r["sentence"]) for r in test_officiel}
    voix_test = choisir_voix_test(valides, phrases_test, {r["client_id"] for r in test_officiel})
    rep = repartir(valides, phrases_test, voix_test)
    verifier(rep, phrases_test, voix_test, autres_textes)
    manifeste = {
        "regle": "test = voix T x phrases du test officiel ; dev = voix T x autres phrases ; "
                 "train = autres voix hors phrases du test (finetune/cv27_split.py)",
        "splits": {s: {"clips": len(rows), "heures": round(sum(r["h"] for r in rows), 2),
                       "voix": len({r["client_id"] for r in rows})} for s, rows in rep.items()},
        "test": [{"path": r["path"], "sentence": r["sentence"]} for r in rep["test"]],
    }
    return rep, manifeste
