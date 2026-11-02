"""Wourri — Import du catalogue des concepts NLU dans PostgreSQL (ADR-0047, #600).

Lit `dictionnaires/nlu_concepts.json` et remplit `nlu_concepts`, que l'atelier
lit en SEULE LECTURE pour demander au locuteur les mots d'un concept vide.

Pendant exact de `import_corpus_ivr.py` : le moteur ecrit, l'atelier lit. Le
conteneur de l'atelier n'a pas les dictionnaires — c'est pourquoi le catalogue
passe par la base plutot que par un fichier partage.

`ref_dyu` = les mots dioula du concept, AFFICHES au locuteur comme reference et
JAMAIS copies : une traduction dioula n'est pas une traduction baoule (ADR-0046).

Idempotent : relancer apres toute modification du JSON (meme regle que le
corpus). Un concept retire du JSON est retire de la table.

Usage :
    python -m scripts.import_nlu_concepts [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SOURCE = RACINE / "dictionnaires" / "nlu_concepts.json"

# Les mots dioula affiches en reference : on en montre assez pour situer le sens,
# pas la liste entiere (certains concepts en portent plus de 40).
MAX_REF = 8


def lire(source: Path) -> list[dict]:
    doc = json.loads(source.read_text(encoding="utf-8"))
    concepts = doc.get("concepts") or {}
    out = []
    for cid, v in concepts.items():
        mots = [m for m in (v.get("keywords") or []) if m]
        out.append({
            "id": cid,
            "label_fr": (v.get("label_fr") or cid).strip(),
            "ref_dyu": ", ".join(mots[:MAX_REF]),
            "intent": (v.get("intent") or "").strip(),
        })
    return sorted(out, key=lambda c: c["id"])


def ecrire(lignes: list[dict]) -> int:
    import psycopg

    dsn = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN")
    if not dsn:
        raise SystemExit("DATABASE_URL absent : impossible de se connecter.")
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            ids = [c["id"] for c in lignes]
            # Un concept retire du JSON ne doit plus etre propose au locuteur.
            cur.execute("DELETE FROM nlu_concepts WHERE id <> ALL(%s)", (ids,))
            cur.executemany(
                "INSERT INTO nlu_concepts (id, label_fr, ref_dyu, intent, updated_at)"
                " VALUES (%(id)s, %(label_fr)s, %(ref_dyu)s, %(intent)s, NOW())"
                " ON CONFLICT (id) DO UPDATE SET"
                "   label_fr = EXCLUDED.label_fr, ref_dyu = EXCLUDED.ref_dyu,"
                "   intent = EXCLUDED.intent, updated_at = NOW()",
                lignes,
            )
        conn.commit()
    return len(lignes)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default=str(SOURCE))
    ap.add_argument("--dry-run", action="store_true", help="n'ecrit rien")
    args = ap.parse_args()

    lignes = lire(Path(args.source))
    print(f"Concepts lus : {len(lignes)}")
    for c in lignes[:3]:
        print(f"  {c['id']:26} {c['label_fr'][:30]:32} ref: {c['ref_dyu'][:40]}")
    if args.dry_run:
        print("Essai a blanc : rien n'est ecrit.")
        return 0
    n = ecrire(lignes)
    print(f"Ecrits en base : {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
