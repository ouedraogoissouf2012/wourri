"""Wourri — Publie vers le serveur voix les audios que le corpus déclare servir (ADR-0049).

Le fichier versionné (`dictionnaires/corpus_ivr_<langue>.json`, et plus tard
`messages_systeme_<langue>.json`) dit **ce qui est servi** à l'agriculteur. Ce script
fait en sorte que l'audio correspondant **existe** là où le serveur voix le cherche.

Avant lui, les 433 `.ogg` servis avaient été convertis et copiés à la main le
2026-11-02 : rien ne signalait un écart, et onze jours de corrections du locuteur
étaient restés invisibles pour la même raison (ADR-0049 §Contexte).

Trois propriétés :
  - **idempotent** : seuls les fichiers absents de la destination sont traités ;
  - **sans perte** : l'atelier enregistre en WebM/Opus, le serveur voix sert de l'Ogg —
    un remux (`-c:a copy`) suffit, le flux audio n'est pas ré-encodé. Les autres formats
    acceptés par l'atelier (wav, mp3, m4a) ne peuvent pas être remuxés : ils sont
    ré-encodés en Opus, et le script le dit ;
  - **il rend compte** : l'écart entre ce que le corpus promet et ce qui est publié
    devient un chiffre, plus un oubli silencieux.

Les octets viennent de l'atelier **par son API** (`GET /media/<nom>`), jamais de sa base :
le moteur et l'atelier restent deux services séparés (ADR-0033).

Usage :
    export LQE_URL=https://lqe-api.africandigitconsulting.com
    export LQE_USER=adc.admin
    export LQE_PASSWORD=...
    python scripts/publier_audios.py bci --vers ./ogg
    python scripts/publier_audios.py bci --vers ./ogg --verifier   # compte sans rien écrire

La destination est un dossier local ; il est ensuite recopié sur le serveur voix
(le script affiche la commande). La conversion reste hors du serveur de production,
qui n'a pas de dépendance ffmpeg (ADR-0035).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
DICTIONNAIRES = ROOT / "dictionnaires"

# Le serveur voix sert `<stem>.ogg` : c'est la forme que `baoule_handler._audio_url`
# construit à partir de `audio_reponse`. La destination doit donc porter ce nom exact.
EXTENSION_SERVIE = ".ogg"


class EchecPublication(RuntimeError):
    """Erreur attendue (configuration, réseau, conversion) — message lisible, pas de trace."""


# --------------------------------------------------------------------------- lecture


def _charger(chemin: Path) -> dict:
    return json.loads(chemin.read_text(encoding="utf-8"))


def refs_attendues(langue: str, *, dossier: Path | None = None) -> list[tuple[str, str]]:
    """[(identifiant, référence audio)] que les fichiers versionnés déclarent servir.

    La référence est celle de l'atelier (`audio/<uuid>.<ext>`). Les entrées sans audio
    — réponse corrigée en attente de réenregistrement — sont exclues : elles sont
    servies en texte, c'est voulu, et elles sont comptées à part par `etat()`.
    """
    base = dossier or DICTIONNAIRES
    out: list[tuple[str, str]] = []

    corpus = base / f"corpus_ivr_{langue}.json"
    if corpus.is_file():
        for e in _charger(corpus).get("entries", []):
            ref = e.get("audio_reponse")
            if ref:
                out.append((str(e.get("id") or ""), str(ref)))

    # Messages système (repli, salutation) — fichier introduit par l'ADR-0049, absent
    # tant que le locuteur n'a pas produit les textes. Son absence n'est pas une erreur.
    messages = base / f"messages_systeme_{langue}.json"
    if messages.is_file():
        for cle, m in (_charger(messages).get("messages") or {}).items():
            ref = (m or {}).get("audio")
            if ref:
                out.append((str(cle), str(ref)))

    return out


def sans_audio(langue: str, *, dossier: Path | None = None) -> list[str]:
    """Identifiants servis EN TEXTE : le locuteur a corrigé la réponse, l'audio est à refaire."""
    corpus = (dossier or DICTIONNAIRES) / f"corpus_ivr_{langue}.json"
    if not corpus.is_file():
        return []
    return [
        str(e.get("id") or "")
        for e in _charger(corpus).get("entries", [])
        if not e.get("audio_reponse")
    ]


def cible(ref: str, vers: Path) -> Path:
    """Chemin du fichier publié pour une référence d'atelier."""
    return vers / (PurePosixPath(ref).stem + EXTENSION_SERVIE)


def a_publier(refs: list[tuple[str, str]], vers: Path) -> list[tuple[str, str]]:
    """Ce qui manque à la destination. C'est ici qu'est l'idempotence."""
    return [(ident, ref) for ident, ref in refs if not cible(ref, vers).is_file()]


# --------------------------------------------------------------------------- atelier


def connexion(base_url: str, utilisateur: str, mot_de_passe: str):
    """Ouvre une session sur l'atelier et renvoie l'ouvreur qui porte son cookie."""
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar())
    )
    corps = json.dumps({"user": utilisateur, "password": mot_de_passe}).encode("utf-8")
    requete = urllib.request.Request(
        base_url.rstrip("/") + "/auth/login",
        data=corps,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        opener.open(requete, timeout=30).read()
    except urllib.error.HTTPError as exc:
        raise EchecPublication(
            f"connexion à l'atelier refusée ({exc.code}) — vérifier LQE_USER / LQE_PASSWORD"
        ) from exc
    except OSError as exc:
        raise EchecPublication(f"atelier injoignable sur {base_url} : {exc}") from exc
    return opener


def telecharger(opener, base_url: str, ref: str) -> bytes | None:
    """Octets de l'audio, ou None s'il n'existe plus dans l'atelier (404)."""
    url = base_url.rstrip("/") + "/media/" + PurePosixPath(ref).name
    try:
        return opener.open(url, timeout=60).read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise EchecPublication(f"lecture de {ref} impossible ({exc.code})") from exc


# --------------------------------------------------------------------------- conversion


def _ffmpeg() -> str:
    chemin = shutil.which("ffmpeg")
    if not chemin:
        raise EchecPublication(
            "ffmpeg est requis pour la conversion et n'est pas installé.\n"
            "La conversion reste volontairement hors du serveur de production (ADR-0035)."
        )
    return chemin


def convertir(octets: bytes, ref: str, destination: Path) -> str:
    """Écrit `destination` en Ogg. Renvoie « remux » ou « réencodage ».

    L'atelier enregistre en WebM/Opus : le flux est recopié tel quel, sans perte. Il
    accepte aussi wav/mp3/m4a (`_ALLOWED_AUDIO`), qui ne contiennent pas d'Opus — la
    recopie échoue alors et on ré-encode, en le signalant.
    """
    ffmpeg = _ffmpeg()
    destination.parent.mkdir(parents=True, exist_ok=True)
    suffixe = PurePosixPath(ref).suffix or ".webm"
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / ("source" + suffixe)
        source.write_bytes(octets)
        for codec, nom in (("copy", "remux"), ("libopus", "réencodage")):
            r = subprocess.run(
                [ffmpeg, "-y", "-loglevel", "error", "-i", str(source),
                 "-vn", "-c:a", codec, str(destination)],
                capture_output=True, text=True,
            )
            if r.returncode == 0 and destination.is_file() and destination.stat().st_size:
                return nom
            destination.unlink(missing_ok=True)
    raise EchecPublication(f"conversion impossible pour {ref} : {r.stderr.strip()[:200]}")


# --------------------------------------------------------------------------- rapport


def etat(langue: str, vers: Path, *, dossier: Path | None = None) -> dict:
    """Ce que le corpus promet, ce qui est publié, ce qui manque."""
    refs = refs_attendues(langue, dossier=dossier)
    manquants = a_publier(refs, vers)
    muets = sans_audio(langue, dossier=dossier)
    return {
        "attendus": len(refs),
        "publies": len(refs) - len(manquants),
        "manquants": len(manquants),
        "sans_audio": len(muets),
        "a_faire": manquants,
    }


def _afficher(langue: str, vers: Path, e: dict) -> None:
    print(f"Langue {langue} — destination {vers}")
    print(f"  audios déclarés par les fichiers versionnés : {e['attendus']}")
    print(f"  déjà publiés                                : {e['publies']}")
    print(f"  à publier                                   : {e['manquants']}")
    if e["sans_audio"]:
        print(f"  servis en TEXTE (audio à réenregistrer)     : {e['sans_audio']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("langue", help="code de la langue (ex. bci)")
    ap.add_argument("--vers", required=True, help="dossier de destination des .ogg")
    ap.add_argument("--verifier", action="store_true",
                    help="compte l'écart sans rien télécharger ni écrire")
    ap.add_argument("--atelier", default=os.environ.get("LQE_URL", ""),
                    help="URL de l'API atelier (défaut : $LQE_URL)")
    ap.add_argument("--dictionnaires", default=None,
                    help="dossier des fichiers versionnés (défaut : dictionnaires/)")
    args = ap.parse_args(argv)

    vers = Path(args.vers)
    dossier = Path(args.dictionnaires) if args.dictionnaires else None
    e = etat(args.langue, vers, dossier=dossier)
    _afficher(args.langue, vers, e)

    if not e["attendus"]:
        print(f"\nAucun fichier versionné pour « {args.langue} » : rien à publier.")
        return 0
    if args.verifier or not e["manquants"]:
        if not e["manquants"]:
            print("\nRien à faire : la destination est à jour.")
        return 0

    if not args.atelier:
        raise EchecPublication("URL de l'atelier manquante : --atelier ou $LQE_URL")
    utilisateur = os.environ.get("LQE_USER", "")
    mot_de_passe = os.environ.get("LQE_PASSWORD", "")
    if not (utilisateur and mot_de_passe):
        raise EchecPublication("identifiants manquants : $LQE_USER et $LQE_PASSWORD")

    opener = connexion(args.atelier, utilisateur, mot_de_passe)
    publies, introuvables, reencodes = 0, [], 0
    for ident, ref in e["a_faire"]:
        octets = telecharger(opener, args.atelier, ref)
        if octets is None:
            introuvables.append(ident)
            continue
        if convertir(octets, ref, cible(ref, vers)) == "réencodage":
            reencodes += 1
        publies += 1

    print(f"\n  publiés maintenant : {publies}")
    if reencodes:
        print(f"    dont ré-encodés (source non Opus) : {reencodes}")
    if introuvables:
        print(f"  INTROUVABLES dans l'atelier : {len(introuvables)} — {', '.join(introuvables[:8])}")
        print("  Ces entrées seront servies SANS voix tant que l'audio manque.")
    print(f"\nÀ recopier sur le serveur voix :\n"
          f"  rsync -av --ignore-existing {vers}/ "
          f"marcel@serveur.africandigitconsulting.com:/home/marcel/voix-bci/donnees/reponses_ogg/")
    return 1 if introuvables else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except EchecPublication as exc:
        print(f"ÉCHEC : {exc}", file=sys.stderr)
        sys.exit(2)
