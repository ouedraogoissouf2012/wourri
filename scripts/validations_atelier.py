"""Garde des fichiers de validations téléchargés de l'atelier (`/tasks/validations`, #637).

Les décisions du locuteur arrivent par un fichier téléchargé. Lu sans contrôle, un corps
d'erreur (`{"detail": ...}`) devenait « aucune entrée » et un export d'une autre langue
entrait dans le NLU baoulé : les deux en silence. `charger_validations` est le SEUL point
de contrôle ; tout lecteur d'un tel fichier passe par elle.

Le message rapporte, il ne diagnostique pas : ce qui était attendu, ce qui a été trouvé
(cité tel quel — c'est le serveur qui connaît la cause), et la seule remédiation sûre.

Limite : un export périmé est un export valide ; aucune garde lisant le fichier ne le
distingue (#642).
"""
from __future__ import annotations

import json
from pathlib import Path

_CITATION_MAX = 300


class ValidationsInvalides(ValueError):
    """Fichier de validations inutilisable — message lisible, destiné à l'écran."""


def _refus(chemin: Path, kind: str, langue: str, trouve: str) -> ValidationsInvalides:
    return ValidationsInvalides(
        f"fichier de validations inutilisable : {chemin}\n"
        f"  attendu : un export de /tasks/validations (kind={kind}, language={langue}) "
        f"avec une liste « entries »\n"
        f"  trouvé  : {trouve}\n"
        f"  remède  : retélécharger ce fichier."
    )


def _citer(valeur) -> str:
    texte = json.dumps(valeur)  # ASCII : sûr sur toute console
    return texte if len(texte) <= _CITATION_MAX else texte[:_CITATION_MAX] + "…"


def charger_validations(chemin, *, kind: str, langue: str) -> dict:
    """Lit un export de `/tasks/validations` et le rend tel quel s'il est bien du `kind`
    et de la `langue` attendus, avec une liste `entries`. Lève `ValidationsInvalides`
    sinon : fichier absent, JSON illisible, corps d'erreur, autre langue, autre type."""
    chemin = Path(chemin)
    try:
        texte = chemin.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise _refus(chemin, kind, langue, "fichier absent") from None
    try:
        data = json.loads(texte)
    except json.JSONDecodeError as exc:
        raise _refus(chemin, kind, langue, f"JSON illisible ({exc.msg}, ligne {exc.lineno})") from None
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise _refus(chemin, kind, langue, _citer(data))
    for champ, attendu in (("language", langue), ("kind", kind)):
        if data.get(champ) != attendu:
            raise _refus(chemin, kind, langue, f"{champ} = {_citer(data.get(champ))}")
    return data
