"""Le corpus baoulé en base : relecture, et synchronisation depuis le fichier relu.

ADR-0050 amendé (2026-11-24) : `dictionnaires/corpus_ivr_bci.json`, relu en PR, reste la
source ; la base (schéma de la migration 0006) en est la copie servie. Ce module ne fait
que des opérations SQL sur une connexion fournie par l'appelant, qui tient la transaction.

Synchroniser = rendre la base égale au lot : ajouter, corriger, supprimer, en n'écrivant
que ce qui change — chaque écriture est historisée par les triggers de la migration
(`historique_linguistique`), avec l'auteur posé ici. Un verrou consultatif sérialise les
synchronisations concurrentes ; la seconde voit le lot déjà appliqué et ne fait rien.
"""
from __future__ import annotations

import hashlib
import json
from typing import NamedTuple, Optional

LANGUE = "bci"
# (rôle, langue, champ du fichier) : les quatre énoncés d'une entrée.
ENONCES = (
    ("question", "bci", "question_bci"),
    ("question", "fr", "question_fr"),
    ("reponse", "bci", "reponse_bci"),
    ("reponse", "fr", "reponse_fr"),
)
METADONNEES = ("filiere", "appariement")


class Bilan(NamedTuple):
    applique: bool
    ajoutees: int = 0
    modifiees: int = 0
    supprimees: int = 0
    reclassees: int = 0


def empreinte(data: dict) -> str:
    """Empreinte du CONTENU (JSON canonique) — identique à celle de la migration 0006."""
    canon = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def lot_courant(conn) -> Optional[str]:
    from sqlalchemy import text

    return conn.execute(text(
        "SELECT empreinte FROM lot_linguistique WHERE langue = :l ORDER BY applique_le DESC LIMIT 1"
    ), {"l": LANGUE}).scalar()


def _ligne(e: dict) -> tuple:
    """Ce que la base porte d'une entrée : (intent, cultures, métadonnées, énoncés)."""
    meta = {k: e[k] for k in METADONNEES}
    enonces = {(role, langue): (e[champ], e["audio_reponse"] if champ == "reponse_bci" else None)
               for role, langue, champ in ENONCES}
    return e["intent"], list(e["cultures"]), meta, enonces


def _en_base(conn) -> dict[str, tuple]:
    """{id: (rang, intent, cultures, métadonnées, énoncés)} tel que la base le porte."""
    from sqlalchemy import text

    enonces: dict[str, dict] = {}
    for rid, role, langue, texte, media in conn.execute(text(
        "SELECT e.reponse_id, e.role, e.langue, e.texte, e.media FROM enonce e "
        "JOIN reponse r ON r.id = e.reponse_id WHERE r.langue = :l"
    ), {"l": LANGUE}):
        enonces.setdefault(rid, {})[(role, langue)] = (texte, media)
    return {
        rid: (rang, intent, list(cultures), dict(meta), enonces.get(rid, {}))
        for rid, rang, intent, cultures, meta in conn.execute(text(
            "SELECT id, rang, intent, cultures, metadonnees FROM reponse WHERE langue = :l"
        ), {"l": LANGUE})
    }


def charger(conn) -> tuple[dict, ...]:
    """Les entrées servies, au format exact du fichier, dans son ordre."""
    lignes = sorted(_en_base(conn).items(), key=lambda kv: kv[1][0])
    out = []
    for rid, (_, intent, cultures, meta, enonces) in lignes:
        texte = {champ: enonces[(role, langue)][0] for role, langue, champ in ENONCES}
        audio = enonces[("reponse", "bci")][1]
        e = {"id": rid, "filiere": meta["filiere"], **{k: texte[k] for k in ("question_bci", "question_fr",
             "reponse_bci", "reponse_fr")}, "intent": intent, "cultures": cultures,
             "audio_reponse": audio, "appariement": meta["appariement"]}
        if audio is None:
            e["audio_a_reenregistrer"] = True  # c'est ce que le fichier porte avec un audio nul
        out.append(e)
    return tuple(out)


def filieres(conn) -> list[str]:
    """Les filières du corpus (le repli n'a besoin que d'elles, pas du corpus entier)."""
    from sqlalchemy import text

    return list(conn.execute(text(
        "SELECT DISTINCT metadonnees->>'filiere' FROM reponse WHERE langue = :l"
    ), {"l": LANGUE}).scalars())


def _rangs(voulus: list[str], actuels: dict[str, int]) -> dict[str, int]:
    """Rang de chaque entrée. Les rangs en place sont gardés tant que l'ordre relatif tient
    (un retrait laisse un trou, un ajout en fin prend la suite) : sinon tout serait réécrit,
    et l'historique noyé, à chaque entrée retirée. Renumérote seulement si l'ordre change."""
    gardes = [i for i in voulus if i in actuels]
    nouveaux = [i for i in voulus if i not in actuels]
    en_fin = voulus[len(gardes):] == nouveaux
    if en_fin and gardes == sorted(gardes, key=actuels.__getitem__):
        suite = max(actuels.values(), default=-1) + 1
        return {**{i: actuels[i] for i in gardes}, **{i: suite + k for k, i in enumerate(nouveaux)}}
    return {i: k for k, i in enumerate(voulus)}


def synchroniser(conn, entrees, empreinte_lot: str, *, auteur: str) -> Bilan:
    """Rend la base égale au lot `entrees`. Ne fait rien si ce lot est déjà appliqué."""
    from sqlalchemy import text

    if not entrees:
        raise ValueError("lot vide : synchronisation refusée — la base garde son contenu")
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('wourri.synchro.' || :l))"), {"l": LANGUE})
    if lot_courant(conn) == empreinte_lot:
        return Bilan(applique=False)
    conn.execute(text("SELECT set_config('wourri.auteur', :a, true)"), {"a": auteur})

    actuel = _en_base(conn)
    voulu = {e["id"]: _ligne(e) for e in entrees}
    rangs = _rangs([e["id"] for e in entrees], {i: v[0] for i, v in actuel.items()})
    retires = [i for i in actuel if i not in voulu]
    if retires:
        conn.execute(text("DELETE FROM reponse WHERE id = ANY(:ids)"), {"ids": retires})
    effets = [_appliquer(conn, rid, ligne, actuel.get(rid), rangs[rid]) for rid, ligne in voulu.items()]

    conn.execute(text(
        "INSERT INTO lot_linguistique (langue, empreinte, auteur) VALUES (:l, :e, :a) "
        "ON CONFLICT (langue, empreinte) DO UPDATE SET auteur = EXCLUDED.auteur, applique_le = NOW()"
    ), {"l": LANGUE, "e": empreinte_lot, "a": auteur})
    return Bilan(True, effets.count("ajoutee"), effets.count("modifiee"), len(retires),
                 effets.count("reclassee"))


def _appliquer(conn, rid: str, ligne: tuple, avant: Optional[tuple], rang: int) -> Optional[str]:
    """Écrit ce qui diffère pour une entrée ; renvoie ajoutee / modifiee / reclassee / None."""
    from sqlalchemy import text

    intent, cultures, meta, enonces = ligne
    params = {"id": rid, "l": LANGUE, "intent": intent, "cultures": cultures, "rang": rang,
              "meta": json.dumps(meta, ensure_ascii=False)}
    if avant is None:
        conn.execute(text("INSERT INTO reponse (id, langue, intent, cultures, rang, metadonnees) "
                          "VALUES (:id, :l, :intent, :cultures, :rang, CAST(:meta AS JSONB))"), params)
    elif (avant[0], avant[1:4]) != (rang, (intent, cultures, meta)):
        conn.execute(text("UPDATE reponse SET intent = :intent, cultures = :cultures, rang = :rang, "
                          "metadonnees = CAST(:meta AS JSONB) WHERE id = :id"), params)
    enonces_changes = [(cle, v) for cle, v in enonces.items() if avant is None or avant[4].get(cle) != v]
    for (role, langue), (texte, media) in enonces_changes:
        conn.execute(text(
            "INSERT INTO enonce (reponse_id, role, langue, texte, media) VALUES (:id, :r, :lg, :t, :m) "
            "ON CONFLICT (reponse_id, role, langue) DO UPDATE SET texte = EXCLUDED.texte, media = EXCLUDED.media"
        ), {"id": rid, "r": role, "lg": langue, "t": texte, "m": media})
    if avant is None:
        return "ajoutee"
    if enonces_changes or avant[1:4] != (intent, cultures, meta):
        return "modifiee"
    return "reclassee" if avant[0] != rang else None
