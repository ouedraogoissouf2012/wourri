"""#656 : la boucle d'événements n'attend JAMAIS le verrou de la file d'amélioration.

Le verrou (threading) sérialise les écritures ; pris depuis la boucle, il l'arrêterait le
temps d'une réécriture complète du fichier — aucun agriculteur servi pendant ce temps (même
famille que #622 et #644). Deux défenses :
- structurelle : dans une `async def` de `app/`, aucune fonction de la file (ni ses deux
  enveloppes, `escalate` et `ingest_baoule_json`) n'est appelée directement ; elle est
  passée à `asyncio.to_thread`. Couvre les 9 sites recensés ET ceux de demain ;
- à l'exécution : prise depuis une boucle, le module le journalise (et continue : `enqueue`
  ne lève jamais).
"""
import ast
import asyncio
import logging
import threading
from pathlib import Path

from app.services import improvement_queue as q

APP = Path(__file__).resolve().parents[2] / "app"
# Ce qui prend le verrou de la file, directement ou en l'appelant.
BLOQUANTS = {
    "app.services.improvement_queue": {"enqueue_improvement_task", "decide_task", "mark_delivered",
                                       "list_deliverables", "list_tasks", "list_all_tasks",
                                       "existing_fingerprints"},
    "app.services.chat.llm_guard": {"escalate"},
    "app.services.baoule_provider": {"ingest_baoule_json"},
    "app.services.baoule_corpus": {"promote_task"},
}


def _noms_bloquants(arbre: ast.Module, module: str) -> set[str]:
    """Les noms locaux qui désignent une fonction bloquante : importés (`from … import …`)
    ou définis dans le module lui-même (ex. `escalate`, appelée dans llm_guard)."""
    noms = set(BLOQUANTS.get(module, ()))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.ImportFrom) and noeud.module in BLOQUANTS:
            noms |= {(a.asname or a.name) for a in noeud.names if a.name in BLOQUANTS[noeud.module]}
    return noms


def _appels_directs(fonction: ast.AsyncFunctionDef, noms: set[str]):
    """Appels directs dans le corps de la coroutine, sans descendre dans les `def` imbriqués."""
    a_visiter = list(fonction.body)
    while a_visiter:
        noeud = a_visiter.pop()
        if isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Name) and noeud.func.id in noms:
            yield noeud.func.id, noeud.lineno
        a_visiter.extend(ast.iter_child_nodes(noeud))


def test_aucune_coroutine_n_appelle_la_file_directement():
    fautes = []
    for fichier in sorted(APP.rglob("*.py")):
        arbre = ast.parse(fichier.read_text(encoding="utf-8"))
        module = ".".join(fichier.relative_to(APP.parent).with_suffix("").parts)
        noms = _noms_bloquants(arbre, module)
        if not noms:
            continue
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.AsyncFunctionDef):
                for nom, ligne in _appels_directs(noeud, noms):
                    fautes.append(f"{fichier.relative_to(APP.parent).as_posix()}:{ligne} {nom}() "
                                  f"dans async def {noeud.name}")
    assert not fautes, ("appel bloquant de la file DANS la boucle — le passer à "
                        "`await asyncio.to_thread(...)` :\n" + "\n".join(fautes))


def test_le_module_signale_une_prise_du_verrou_depuis_la_boucle(tmp_path, caplog):
    caplog.set_level(logging.ERROR, logger=q.__name__)

    async def depuis_la_boucle():
        q.list_all_tasks(path=tmp_path / "t.jsonl")
    asyncio.run(depuis_la_boucle())
    assert any("DEPUIS LA BOUCLE" in r.getMessage() for r in caplog.records)


def test_le_module_ne_signale_rien_depuis_un_fil(tmp_path, caplog):
    caplog.set_level(logging.ERROR, logger=q.__name__)

    async def via_un_fil():
        await asyncio.to_thread(q.list_all_tasks, path=tmp_path / "t.jsonl")
    asyncio.run(via_un_fil())
    fil = threading.Thread(target=q.list_all_tasks, kwargs={"path": tmp_path / "t.jsonl"})
    fil.start(); fil.join()
    assert not [r for r in caplog.records if "DEPUIS LA BOUCLE" in r.getMessage()]
