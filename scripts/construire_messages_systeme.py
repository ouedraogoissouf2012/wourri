"""Wourri — Construit les messages système validés d'une langue (ADR-0049).

Le repli (« je n'ai pas compris »), la salutation et le hors-sujet sont des phrases
que Wourri prononce **de lui-même** : aucune question ne les déclenche par
ressemblance. Elles étaient en français, en dur dans le code ; elles viennent
désormais du locuteur natif, validées dans l'atelier (ADR-0031 : rien d'inventé).

Ce script relève dans l'atelier les contenus **promus** dont le `concept_id`
figure dans `dictionnaires/messages_systeme_sources.json`, et écrit le fichier
versionné que le moteur lit au démarrage :

    dictionnaires/messages_systeme_<langue>.json

Ajouter un message système = **une ligne dans la table des sources**. Aucun code
à toucher, aucune langue à citer — c'est la même discipline que l'atelier
(ADR-0034 P4 : « activer une langue = un INSERT, zéro `if`-langue »).

Il ne télécharge aucun audio : il n'en garde que la **référence**. Les octets sont
publiés séparément par `scripts/publier_audios.py`, qui lit ce même fichier.

Usage :
    export LQE_URL=https://lqe-api.africandigitconsulting.com
    export LQE_USER=adc.admin        # le paramètre `language` exige le rôle admin
    export LQE_PASSWORD=...
    python scripts/construire_messages_systeme.py bci

Puis commiter le fichier produit : le moteur le lit **au démarrage** (ADR-0049,
arbitrage « fichier versionné »), un redéploiement est donc nécessaire.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DICTIONNAIRES = ROOT / "dictionnaires"
SOURCES = DICTIONNAIRES / "messages_systeme_sources.json"


class EchecConstruction(RuntimeError):
    """Erreur attendue (configuration, réseau, données) — message lisible."""


def roles_attendus(chemin: Path | None = None) -> dict[str, str]:
    """{rôle: identifiant du catalogue} — la table des sources."""
    p = chemin or SOURCES
    if not p.is_file():
        raise EchecConstruction(f"table des sources introuvable : {p}")
    try:
        return dict(json.loads(p.read_text(encoding="utf-8")).get("roles") or {})
    except json.JSONDecodeError as exc:
        raise EchecConstruction(f"{p.name} illisible : {exc}") from exc


def connexion(base_url: str, utilisateur: str, mot_de_passe: str):
    """Ouvre une session sur l'atelier et renvoie l'ouvreur qui porte son cookie.

    Le cookie est `Secure` en production : sur une URL en http il n'est pas renvoyé
    et l'appel suivant répond 401 avec les bons identifiants. Toujours viser https.
    """
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    corps = json.dumps({"user": utilisateur, "password": mot_de_passe}).encode("utf-8")
    requete = urllib.request.Request(
        base_url.rstrip("/") + "/auth/login", data=corps,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        opener.open(requete, timeout=30).read()
    except urllib.error.HTTPError as exc:
        raise EchecConstruction(
            f"connexion à l'atelier refusée ({exc.code}) — vérifier LQE_USER / LQE_PASSWORD"
        ) from exc
    except OSError as exc:
        raise EchecConstruction(f"atelier injoignable sur {base_url} : {exc}") from exc
    return opener


def corpus_servi(opener, base_url: str, langue: str) -> list[dict]:
    """Contenus promus de `langue` (route admin `GET /corpus?language=`)."""
    url = f"{base_url.rstrip('/')}/corpus?language={urllib.parse.quote(langue)}"
    try:
        data = json.loads(opener.open(url, timeout=60).read())
    except urllib.error.HTTPError as exc:
        detail = {403: "le compte n'est pas admin", 400: "langue inconnue de l'atelier"}
        raise EchecConstruction(
            f"lecture du corpus {langue} impossible ({exc.code})"
            + (f" — {detail[exc.code]}" if exc.code in detail else "")
        ) from exc
    except OSError as exc:
        raise EchecConstruction(f"atelier injoignable : {exc}") from exc
    return list(data.get("entries") or [])


def messages(entries: list[dict], roles: dict[str, str]) -> tuple[dict, list[str]]:
    """({rôle: message}, rôles non encore produits).

    Une entrée sans texte local ne vaut rien : mieux vaut un rôle manquant — et donc
    le repli français — qu'une phrase vide servie à un agriculteur.
    """
    par_concept = {str(e.get("concept_id") or ""): e for e in entries}
    out: dict[str, dict] = {}
    manquants: list[str] = []
    for role, concept_id in roles.items():
        e = par_concept.get(concept_id)
        texte = (e or {}).get("text_local") or ""
        if not texte.strip():
            manquants.append(role)
            continue
        message = {"texte": texte.strip(), "texte_fr": (e.get("text_fr") or "").strip()}
        audio = (e.get("audio_url") or "").strip()
        if audio:
            message["audio"] = audio
        out[role] = message
    return out, manquants


def ecrire(langue: str, msgs: dict, *, dossier: Path | None = None) -> Path:
    cible = (dossier or DICTIONNAIRES) / f"messages_systeme_{langue}.json"
    contenu = {
        "version": f"{langue}-{datetime.date.today().isoformat()}",
        "langue": langue,
        "messages": msgs,
    }
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(json.dumps(contenu, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return cible


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("langue", help="code ISO de la langue (ex. bci)")
    ap.add_argument("--atelier", default=os.environ.get("LQE_URL", ""),
                    help="URL de l'API atelier (défaut : $LQE_URL)")
    ap.add_argument("--sources", default=None, help="table des sources (défaut : dictionnaires/)")
    ap.add_argument("--out", default=None, help="dossier de sortie (défaut : dictionnaires/)")
    args = ap.parse_args(argv)

    roles = roles_attendus(Path(args.sources) if args.sources else None)
    if not args.atelier:
        raise EchecConstruction("URL de l'atelier manquante : --atelier ou $LQE_URL")
    utilisateur, mot_de_passe = os.environ.get("LQE_USER", ""), os.environ.get("LQE_PASSWORD", "")
    if not (utilisateur and mot_de_passe):
        raise EchecConstruction("identifiants manquants : $LQE_USER et $LQE_PASSWORD")

    opener = connexion(args.atelier, utilisateur, mot_de_passe)
    entries = corpus_servi(opener, args.atelier, args.langue)
    msgs, manquants = messages(entries, roles)

    print(f"Langue {args.langue} — {len(entries)} contenu(s) promu(s) dans l'atelier")
    print(f"  rôles attendus : {len(roles)}")
    for role, m in sorted(msgs.items()):
        voix = "avec voix" if m.get("audio") else "SANS VOIX (à enregistrer)"
        print(f"    {role:<26} {voix}  « {m['texte'][:46]} »")
    for role in sorted(manquants):
        print(f"    {role:<26} pas encore produit par le locuteur")

    if not msgs:
        # Écrire un fichier vide ferait croire à un mécanisme en place : mieux vaut
        # ne rien écrire et laisser le repli français, qui est le comportement défini.
        print("\nAucun message produit : rien n'est écrit, le repli reste en français.")
        return 1

    cible = ecrire(args.langue, msgs, dossier=Path(args.out) if args.out else None)
    print(f"\nÉcrit : {cible}")
    print("  1. commiter ce fichier (le moteur le lit au démarrage)")
    print(f"  2. publier les voix : python scripts/publier_audios.py {args.langue} --vers ./ogg")
    return 1 if manquants else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except EchecConstruction as exc:
        print(f"ÉCHEC : {exc}", file=sys.stderr)
        sys.exit(2)
