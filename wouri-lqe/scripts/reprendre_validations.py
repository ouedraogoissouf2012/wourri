"""Remise a zero des validations d'une langue dans l'atelier (ADR-0045, #475).

Cas d'usage : le locuteur reconnait des erreurs et veut tout reprendre. Chaque fiche des
types choisis (par defaut `mot_cle` et `paire_qr`) redevient « a valider » (bronze) avec
son texte d'origine :
- `meta.texte_origine`, garde a la premiere correction ;
- sinon le fichier d'import d'origine (--original), retrouve par l'identifiant externe ;
- sinon le texte reste tel quel (compte a part dans le resume).

Jamais une fiche publiee ('production'), jamais une autre langue.

Essai a blanc par defaut : affiche ce qui changerait, n'ecrit rien. --appliquer ecrit
d'abord une sauvegarde JSON des fiches touchees (etat avant), puis applique.

Usage (depuis wouri-lqe/ ou dans le conteneur de l'atelier, memes variables que l'app) :
    python -m scripts.reprendre_validations --langue bci --original import.json
    python -m scripts.reprendre_validations --langue bci --original import.json --appliquer
    # seulement les paires rejetees, pour que le locuteur les corrige :
    python -m scripts.reprendre_validations --langue bci --types paire_qr --statuts admin_rejected
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from app.services import productions_repo as repo
from app.services import workflow
from app.services.ingest import external_id

TYPES_DEFAUT = ("mot_cle", "paire_qr")


def originaux(entries: list[dict]) -> dict[str, dict]:
    """{identifiant externe: texte d'origine} depuis un fichier d'import de l'atelier."""
    out = {}
    for raw in entries:
        kind = str(raw.get("kind") or repo.CONTENU).strip()
        ext = external_id(raw, kind)
        if ext:
            out[ext] = {"text_local": str(raw.get("text_local") or "").strip()[:2000],
                        "text_fr": str(raw.get("text_fr") or "").strip()[:2000]}
    return out


def planifier(rows: list[dict], origine: dict[str, dict], types, statuts=workflow.REPRENABLE_FROM) -> list[dict]:
    """Fiches a remettre « a valider » : decidees, ou dont le texte differe de l'origine.
    `statuts` restreint aux fiches dans ces statuts (ex. seulement les rejetees)."""
    plan = []
    for r in rows:
        if r["kind"] not in types or r["status"] not in workflow.REPRENABLE_FROM or r["status"] not in statuts:
            continue
        cible = r["meta"].get("texte_origine") or origine.get(r["meta"].get("external_id") or "")
        avant = {"text_local": r["text_local"], "text_fr": r["text_fr"]}
        texte_change = bool(cible) and (cible["text_local"], cible["text_fr"]) != (avant["text_local"], avant["text_fr"])
        if r["status"] == "bronze" and not texte_change and "texte_origine" not in r["meta"]:
            continue
        plan.append({"id": r["id"], "kind": r["kind"], "status": r["status"], "avant": avant,
                     "apres": cible, "texte_change": texte_change, "sans_origine": not cible})
    return plan


def resume(plan: list[dict], rows: list[dict], types) -> str:
    par = Counter((p["kind"], p["status"]) for p in plan)
    publiees = sum(1 for r in rows if r["kind"] in types and r["status"] == "production")
    lignes = [f"Fiches remises « a valider » : {len(plan)}"]
    lignes += [f"  {k} {s} : {n}" for (k, s), n in sorted(par.items())]
    lignes.append(f"  dont texte d'origine restaure : {sum(p['texte_change'] for p in plan)}")
    lignes.append(f"  dont texte d'origine introuvable (texte garde) : {sum(p['sans_origine'] for p in plan)}")
    lignes.append(f"Fiches publiees, non touchees : {publiees}")
    return "\n".join(lignes)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--langue", required=True, help="code de la langue (ex. bci)")
    ap.add_argument("--types", default=",".join(TYPES_DEFAUT), help="types de fiche, separes par des virgules")
    ap.add_argument("--statuts", default=",".join(sorted(workflow.REPRENABLE_FROM)),
                    help="statuts repris, separes par des virgules (ex. admin_rejected)")
    ap.add_argument("--original", action="append", default=[], help="fichier d'import d'origine (repetable)")
    ap.add_argument("--appliquer", action="store_true", help="applique (sinon essai a blanc)")
    ap.add_argument("--sauvegarde", help="fichier de sauvegarde (defaut : reprise_<langue>_<date>.json)")
    args = ap.parse_args(argv)

    types = tuple(t.strip() for t in args.types.split(",") if t.strip())
    inconnus = [t for t in types if t not in repo.KINDS]
    if inconnus:
        ap.error(f"type inconnu : {', '.join(inconnus)}")
    statuts = {s.strip() for s in args.statuts.split(",") if s.strip()}
    if not statuts <= workflow.REPRENABLE_FROM:
        ap.error(f"statut non repris : {', '.join(sorted(statuts - workflow.REPRENABLE_FROM))}")
    origine = {}
    for f in args.original:
        origine.update(originaux(json.loads(Path(f).read_text(encoding="utf-8"))))

    rows = repo.list_by(language=args.langue)
    plan = planifier(rows, origine, types, statuts)
    print(resume(plan, rows, types))
    for p in plan[:10]:
        apres = p["apres"]["text_local"] if p["apres"] else "(inchange)"
        print(f"  #{p['id']} {p['kind']} {p['status']} : {p['avant']['text_local']!r} -> {apres!r}")

    if not args.appliquer:
        print("Essai a blanc : rien n'est ecrit. Relancer avec --appliquer.")
        return 0
    horodatage = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    sauvegarde = Path(args.sauvegarde or f"reprise_{args.langue}_{horodatage}.json")
    touchees = {p["id"] for p in plan}
    sauvegarde.write_text(json.dumps([r for r in rows if r["id"] in touchees], ensure_ascii=False, indent=1),
                          encoding="utf-8")
    print(f"Sauvegarde (etat avant) : {sauvegarde.resolve()}")
    faites = 0
    for p in plan:
        texte = p["apres"] or {}
        faites += repo.reprendre(item_id=p["id"], language=args.langue, allowed_from=workflow.REPRENABLE_FROM,
                                 text_local=texte.get("text_local"), text_fr=texte.get("text_fr"))
    print(f"Appliquee : {faites}/{len(plan)} fiche(s) remise(s) « a valider ».")
    return 0 if faites == len(plan) else 1


if __name__ == "__main__":
    sys.exit(main())
