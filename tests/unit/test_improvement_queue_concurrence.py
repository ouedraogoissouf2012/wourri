"""#656 : la file d'amélioration ne perd plus une tâche, ni une décision, sous concurrence.

Un seul worker ne sérialise PAS ces écritures : FastAPI exécute les gestionnaires `def`
(les trois routes qui appellent decide_task) dans un pool de fils, et feedback_negatif
ajoute depuis la boucle. Mesuré sur le code d'avant (conditions de stress, qui prouvent le
mécanisme et non sa fréquence en production ; le premier test prouve qu'une seule
coïncidence suffit) : 39 tâches perdues sur 2000, 6 lignes devenues illisibles, et 194
décisions perdues sur 200 paires de décisions simultanées.
"""
import builtins
import json
import logging
import pathlib
import threading

import pytest

from app.services import improvement_queue as q


@pytest.fixture
def chemin(tmp_path):
    return tmp_path / "tasks.jsonl"


def _ajouter(chemin, n):
    return q.enqueue_improvement_task(intent="I", source="ivr_exact", cultures=[], excerpt=f"question {n}",
                                      user_anon="u", path=chemin)["task"]["id"]


def _lignes(chemin):
    return [json.loads(l) for l in chemin.read_text(encoding="utf-8").splitlines() if l.strip()]


# Les deux réécritures complètes de la file : décider (atelier) et marquer remise (chat).
REECRITURES = {
    "decide_task": (lambda tid, p: q.decide_task(tid, "speaker_accepted", path=p),
                    lambda tache: tache.get("status") == "speaker_accepted"),
    "mark_delivered": (lambda tid, p: q.mark_delivered(tid, path=p),
                       lambda tache: bool(tache.get("delivered_at"))),
}


@pytest.mark.parametrize("nom", sorted(REECRITURES))
def test_un_ajout_pendant_une_reecriture_n_est_pas_efface(chemin, monkeypatch, nom):
    """Le scénario de l'issue, rendu déterministe à DEUX fils : A réécrit la file ; juste
    après sa lecture, B (un agriculteur qui vote 👎) ajoute sa tâche. Sans verrou, B passe
    et A réécrit sa copie : la question disparaît. Avec verrou, B attend la fin de A."""
    reecrire, appliquee = REECRITURES[nom]
    a_decider = _ajouter(chemin, 0)
    lu, b_fini, fil_a, nouvelle = threading.Event(), threading.Event(), {}, {}
    vraie_lecture = pathlib.Path.read_text

    def lecture(self, *a, **k):
        texte = vraie_lecture(self, *a, **k)
        if self == chemin and threading.current_thread() is fil_a.get("fil") and not lu.is_set():
            lu.set()
            b_fini.wait(0.5)  # sans verrou B finit ici ; avec verrou B est bloqué : délai écoulé
        return texte
    monkeypatch.setattr(pathlib.Path, "read_text", lecture)

    def agriculteur():
        lu.wait(5)
        nouvelle["id"] = _ajouter(chemin, 1)
        b_fini.set()
    fil_a["fil"] = threading.Thread(target=reecrire, args=(a_decider, chemin))
    fil_b = threading.Thread(target=agriculteur)
    fil_a["fil"].start(); fil_b.start(); fil_a["fil"].join(5); fil_b.join(5)

    taches = {t["id"]: t for t in _lignes(chemin)}
    assert nouvelle["id"] in taches, f"la tâche ajoutée pendant {nom} a été effacée"
    assert appliquee(taches[a_decider]), f"{nom} n'a pas été appliqué"


def test_vrais_fils_ni_perte_ni_ligne_illisible(chemin):
    for tour in range(3):
        fichier = chemin.with_name(f"tasks_{tour}.jsonl")
        a_decider, ajoutees, fin = _ajouter(fichier, -1), [], threading.Event()

        def locuteur():
            i = 0
            while not fin.is_set():
                q.decide_task(a_decider, ("speaker_accepted", "speaker_rejected")[i % 2], path=fichier)
                i += 1

        def agriculteurs():
            for n in range(100):
                ajoutees.append(_ajouter(fichier, n))
            fin.set()
        fils = [threading.Thread(target=locuteur), threading.Thread(target=agriculteurs)]
        for f in fils:
            f.start()
        for f in fils:
            f.join(30)
        brut = [l for l in fichier.read_text(encoding="utf-8").splitlines() if l.strip()]
        illisibles = [l for l in brut if not l.startswith("{") or not l.endswith("}")]
        assert not illisibles, f"tour {tour} : lignes illisibles {illisibles[:3]}"
        perdues = set(ajoutees) - {json.loads(l)["id"] for l in brut}
        assert not perdues, f"tour {tour} : {len(perdues)} tâche(s) perdue(s) sur {len(ajoutees)}"


def test_deux_decisions_simultanees_sont_toutes_deux_conservees(chemin):
    for paire in range(50):
        fichier = chemin.with_name(f"paire_{paire}.jsonl")
        a, b = _ajouter(fichier, 1), _ajouter(fichier, 2)
        barriere = threading.Barrier(2)

        def decider(tid, decision):
            barriere.wait()
            q.decide_task(tid, decision, path=fichier)
        fils = [threading.Thread(target=decider, args=(a, "speaker_accepted")),
                threading.Thread(target=decider, args=(b, "admin_rejected"))]
        for f in fils:
            f.start()
        for f in fils:
            f.join(10)
        etats = {t["id"]: t["status"] for t in _lignes(fichier)}
        assert etats == {a: "speaker_accepted", b: "admin_rejected"}, f"paire {paire} : {etats}"


class _DisquePlein:
    """Un fichier ouvert en écriture qui n'écrit que la moitié, puis lève ENOSPC."""

    def __init__(self, fh):
        self._fh = fh

    def write(self, data):
        self._fh.write(data[: len(data) // 2])
        raise OSError(28, "No space left on device")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._fh.close()
        return False

    def __getattr__(self, nom):
        return getattr(self._fh, nom)


def test_une_reecriture_interrompue_laisse_la_file_intacte(chemin, monkeypatch):
    """Disque plein pendant la réécriture : l'ancienne file doit rester entière. Avant, la
    réécriture tronquait d'abord le fichier — un arrêt au milieu laissait une file vide."""
    a_decider = _ajouter(chemin, 0)
    _ajouter(chemin, 1)
    avant = chemin.read_bytes()
    dossier = chemin.parent

    def piege(vraie):
        def ouvrir(fichier, mode="r", *a, **k):
            fh = vraie(fichier, mode, *a, **k)
            return _DisquePlein(fh) if "w" in mode and pathlib.Path(fichier).parent == dossier else fh
        return ouvrir
    monkeypatch.setattr(builtins, "open", piege(builtins.open))
    monkeypatch.setattr(pathlib.Path, "open", piege(pathlib.Path.open))

    resultat = q.decide_task(a_decider, "speaker_accepted", path=chemin)
    monkeypatch.undo()

    assert resultat == {"ok": False, "reason": "io"}
    assert chemin.read_bytes() == avant, "la file a été tronquée par une réécriture interrompue"


def test_une_ligne_illisible_n_est_plus_ignoree_en_silence(chemin, caplog):
    _ajouter(chemin, 0)
    with chemin.open("a", encoding="utf-8") as fh:
        fh.write('acf0aa"}\n')  # le fragment observé après une écriture concurrente
    caplog.set_level(logging.WARNING, logger=q.__name__)
    assert len(q.list_all_tasks(path=chemin)) == 1
    assert any("1 ligne(s) illisible(s)" in r.getMessage() for r in caplog.records), \
        [r.getMessage() for r in caplog.records]
