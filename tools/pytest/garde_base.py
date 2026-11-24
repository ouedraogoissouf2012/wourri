"""Garde de la base (#638) : aucun test n'atteint PostgreSQL sans l'avoir DÉCLARÉ, et un
test déclaré n'atteint qu'une base JETABLE (nom finissant par `_test`).

Chargée par le `conftest.py` RACINE du moteur et de l'atelier (`pytest_plugins`), et
installée dès son import : avant `tests/conftest.py` et avant la collecte. Prouvée par
`tests/unit/test_garde_base.py`, `tests/integration/test_garde_base_pool.py` et
`wouri-lqe/tests/test_garde_base_atelier.py` ; sa présence dans chaque suite, par les
tests `test_la_garde_est_branchee_dans_cette_session`.

DÉCLARER : `@pytest.mark.base_de_donnees` (ou `pytestmark` pour un module). Dans
l'atelier, demander la fixture `db` vaut déclaration (posée par `wouri-lqe/tests/
conftest.py`). Tout le reste se voit refuser la base. Aucune liste de chemins ici : la
déclaration se lit dans le test.

POURQUOI REFUSER, ET NON COMPTER. Les réglages lisent le `.env` du checkout ; celui du
poste de développement pointe sur `wourri_dev`. Un test fautif ne tombait donc pas : il se
CONNECTAIT à la base de dev, où des fixtures font TRUNCATE et deux tests de l'atelier
`DROP SCHEMA … CASCADE` hors de la fixture `db`. Un compteur aurait documenté le dégât
après l'avoir laissé faire. Le refus est levé AVANT le réseau, et il est aussi ENREGISTRÉ :
le test échoue même si le code avale l'exception (le repli de `baoule_ivr` le fait).

POURQUOI LES REQUÊTES, ET PAS SEULEMENT `connect`. Mesure de #638 : sur 4 tests unitaires
fautifs, UN SEUL ouvrait une connexion ; les 3 autres réutilisaient celle du pool. Une
garde réduite à `connect` en attrape 1 sur 4 — et 0 si un test d'intégration a rempli le
pool avant. Ne pas « alléger » la garde en retirant les curseurs.

POURQUOI L'ALIAS `psycopg.connect`. C'est lui que SQLAlchemy appelle, pas
`Connection.connect` : une sonde qui n'enveloppait que la méthode voyait zéro connexion.

LIMITES CONNUES — à lire avant de croire la garde complète :
- Sous-processus : seul l'environnement TRANSMIS est inspecté (POSTGRES_URL,
  LQE_DATABASE_URL, POSTGRES_DB), et seulement pendant un test déclaré. Un enfant qui
  trouve sa base autrement (un `.env` lu dans son répertoire, un argument, PGDATABASE)
  n'est pas vu ; un sous-processus lancé par un test NON déclaré n'est pas inspecté (la
  CI exporte POSTGRES_URL pour toute la suite). `os.system` / `os.spawn*` non plus.
- Seul psycopg (3) est surveillé : seul pilote des deux suites au 2026-11-24. Un autre
  pilote (psycopg2, asyncpg) passerait sans être vu.
- Un fil qui SURVIT à son test : la garde ne sait pas quel test l'a lancé ; elle impute
  l'accès à la zone en cours au moment où il est DÉCIDÉ. Un test innocent peut donc être
  accusé — c'est un faux positif, pas une imprécision (mesuré, #649 : 5 passes sur 30 de
  l'atelier, un fil de `psycopg_pool` configurant sa connexion 0,13 ms après la fin du test
  qui l'avait demandée). Le remède est dans les suites, qui ne laissent survivre aucun fil :
  ADMIN_METRICS_ENABLED=false dans `tests/conftest.py`, et le pool fermé au démontage dans
  `wouri-lqe/tests/conftest.py`. Ce que la garde garantit, elle : décision, message et
  imputation portent sur la MÊME zone, lue une fois — un refus décidé dans un test n'est
  jamais enregistré sous un autre (`tests/unit/test_garde_base_fils.py`).
- Un pool (`psycopg_pool`) qui survit à son test : après un refus, il espace ses
  tentatives ; le test suivant qui l'attend échoue sur PoolTimeout, rouge mais SANS le
  message de la garde (mesuré, #649 : 2 sur 10 avec un pool partagé entre deux tests,
  0 sur 10 une fois le pool fermé au démontage). Même racine que le faux positif
  ci-dessus, même remède : aucune suite ne laisse un pool survivre à son test.
"""
from __future__ import annotations

import os
import subprocess
import threading
import traceback
from dataclasses import dataclass
from urllib.parse import urlsplit

import pytest

MARQUEUR = "base_de_donnees"
SUFFIXE = "_test"
_VARIABLES_URL = ("POSTGRES_URL", "LQE_DATABASE_URL")
_VARIABLES_NOM = ("POSTGRES_DB",)
# Paramètres de psycopg.connect qui ne sont pas des paramètres de connexion libpq.
_HORS_CONNINFO = {"autocommit", "prepare_threshold", "context", "row_factory", "cursor_factory"}
_REQUETES = ("execute", "executemany", "copy", "stream")
_INTERNES = ("/psycopg/", "/psycopg_pool/", "/sqlalchemy/", "/threading.py", "/asyncio/",
             "/subprocess.py", "/concurrent/", "/contextlib.py", "garde_base.py")


class AccesBaseRefuse(RuntimeError):
    """Levée avant le réseau. Le code peut l'avaler : le refus est aussi enregistré."""


@dataclass(frozen=True)
class _Zone:
    nom: str
    declare: bool
    collecte: bool = False


_HORS = _Zone("hors de tout test", declare=False)
_zone = _HORS
_refus: dict[str, list[str]] = {}
_verrou = threading.Lock()
_originaux: list[tuple[object, str, object]] = []


def _origine() -> str:
    """La première ligne qui n'appartient ni à la garde ni à la pile psycopg/SQLAlchemy."""
    for cadre in reversed(traceback.extract_stack()):
        chemin = cadre.filename.replace("\\", "/")
        if not any(interne in chemin for interne in _INTERNES):
            try:
                chemin = os.path.relpath(cadre.filename).replace("\\", "/")
            except ValueError:  # autre lecteur (Windows)
                pass
            return f"{chemin}:{cadre.lineno}"
    return "?"


def _refuser(message: str, z: _Zone):
    """Imputé à `z`, la zone CAPTURÉE au moment de la décision — jamais relue ici (#649) :
    entre la décision et cet enregistrement, un fil peut voir commencer un autre test."""
    with _verrou:
        _refus.setdefault(z.nom, []).append(message)
    raise AccesBaseRefuse(message)


def _non_declare(point: str, z: _Zone) -> str:
    lieu = f"{point} depuis {_origine()}"
    if z.collecte:
        return (f"la collecte de {z.nom} atteint PostgreSQL ({lieu}) : aucune connexion n'est "
                "permise pendant la collecte (import d'un module, crochet de collecte) — "
                "déplace-la dans une fixture d'un test déclaré.")
    if z is _HORS:
        return f"PostgreSQL atteint hors de tout test ({lieu}) : seul un test déclaré y a droit."
    return (f"{z.nom} a atteint PostgreSQL sans le déclarer ({lieu}). S'il n'a pas besoin de la "
            f"base : remplace l'accès (monkeypatch). S'il en a besoin : @pytest.mark.{MARQUEUR}, "
            f"sur une base dont le nom finit par `{SUFFIXE}`.")


def _non_jetable(nom: str, z: _Zone) -> str:
    return f"{z.nom} : base non jetable : {nom} (attendu : un nom finissant par `{SUFFIXE}`)"


def _nom_de_base(conninfo: str, kwargs: dict) -> str:
    """La base que libpq visera, calculée AVANT de la contacter."""
    from psycopg.conninfo import conninfo_to_dict

    params = {k: v for k, v in kwargs.items() if k not in _HORS_CONNINFO and v is not None}
    try:
        p = conninfo_to_dict(conninfo or "", **params)
    except Exception:  # noqa: BLE001 — conninfo illisible : psycopg le refusera lui-même
        p = {}
    return str(p.get("dbname") or os.environ.get("PGDATABASE") or p.get("user")
               or os.environ.get("PGUSER") or "?")


def _controler_connexion(point: str, conninfo: str, kwargs: dict) -> None:
    z = _zone  # UNE lecture : décision, message et imputation portent sur la même zone
    if not z.declare:
        _refuser(_non_declare(point, z), z)
    nom = _nom_de_base(conninfo, kwargs)
    if not nom.endswith(SUFFIXE):
        _refuser(_non_jetable(nom, z), z)


def _remplacer(cible, nom: str, nouveau) -> None:
    _originaux.append((cible, nom, cible.__dict__[nom] if isinstance(cible, type) else getattr(cible, nom)))
    nouveau.__garde__ = True
    setattr(cible, nom, nouveau)


def _garder_connect(cls) -> None:
    vraie = cls.__dict__["connect"].__func__

    def connect(klass, conninfo: str = "", **kwargs):
        _controler_connexion(f"{cls.__name__}.connect", conninfo, kwargs)
        return vraie(klass, conninfo, **kwargs)

    _originaux.append((cls, "connect", cls.__dict__["connect"]))
    connect.__garde__ = True
    cls.connect = classmethod(connect)


def _garder_requete(cls, methode: str) -> None:
    vraie = cls.__dict__[methode]

    def requete(self, *args, **kwargs):  # def simple : le refus tombe à l'appel, même en async
        z = _zone
        if not z.declare:
            _refuser(_non_declare(f"{cls.__name__}.{methode}", z), z)
        return vraie(self, *args, **kwargs)

    _remplacer(cls, methode, requete)


def _nom_dans(variable: str, valeur: str | None) -> str | None:
    if not valeur:
        return None
    if variable in _VARIABLES_URL:
        return urlsplit(valeur).path.lstrip("/") or None
    return valeur


def _garder_sous_processus() -> None:
    vraie = subprocess.Popen.__init__

    def __init__(self, args, *a, **kwargs):
        z = _zone
        if z.declare:
            env = kwargs.get("env") if "env" in kwargs else (a[9] if len(a) > 9 else None)
            env = os.environ if env is None else env
            for variable in (*_VARIABLES_URL, *_VARIABLES_NOM):
                nom = _nom_dans(variable, env.get(variable))
                if nom and not nom.endswith(SUFFIXE):
                    _refuser(f"sous-processus ({variable}) — {_non_jetable(nom, z)}", z)
        vraie(self, args, *a, **kwargs)

    _remplacer(subprocess.Popen, "__init__", __init__)


def _installer() -> None:
    if _originaux:
        return
    import psycopg

    vraie_alias = psycopg.connect

    def connect(conninfo: str = "", **kwargs):
        _controler_connexion("psycopg.connect", conninfo, kwargs)
        return vraie_alias(conninfo, **kwargs)

    _remplacer(psycopg, "connect", connect)
    for cls in (psycopg.Connection, psycopg.AsyncConnection):
        _garder_connect(cls)
    for cls in (psycopg.Cursor, psycopg.ServerCursor, psycopg.AsyncCursor, psycopg.AsyncServerCursor):
        for methode in _REQUETES:
            if methode in cls.__dict__:
                _garder_requete(cls, methode)
    _garder_sous_processus()


def _desinstaller() -> None:
    while _originaux:
        cible, nom, original = _originaux.pop()
        setattr(cible, nom, original)


# Dès l'import, et non dans un crochet : le conftest racine importe la garde AVANT
# `tests/conftest.py` ; un conftest qui se connecterait à l'import est donc vu.
_installer()


def pytest_configure(config):
    config.addinivalue_line("markers", f"{MARQUEUR}: le test atteint PostgreSQL, sur une base "
                                       f"dont le nom finit par `{SUFFIXE}` (garde #638)")
    _installer()  # idempotent ; réinstalle après un pytest_unconfigure (sessions imbriquées)


def pytest_unconfigure(config):
    _desinstaller()


def _imputer(rapport, nom: str) -> None:
    with _verrou:
        messages = _refus.pop(nom, None)
    if messages:
        rapport.outcome = "failed"
        rapport.longrepr = "garde de la base (#638) :\n" + "\n".join(messages)


@pytest.hookimpl(hookwrapper=True)
def pytest_make_collect_report(collector):
    # Les collectes S'IMBRIQUENT : la Session collecte en elle-même les dossiers qui mènent
    # aux chemins demandés. Zone locale, imputée telle quelle, et zone PRÉCÉDENTE restaurée
    # en sortie : sinon, après un enfant, la Session continuait en « hors de tout test » et
    # ses propres refus n'étaient jamais imputés à sa collecte.
    global _zone
    precedente, zone = _zone, _Zone(collector.nodeid or "<session>", declare=False, collecte=True)
    _zone = zone
    try:
        resultat = yield
        _imputer(resultat.get_result(), zone.nom)
    finally:
        _zone = precedente


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    global _zone
    _zone = _Zone(item.nodeid, declare=item.get_closest_marker(MARQUEUR) is not None)
    try:
        yield
    finally:
        _zone = _HORS


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    resultat = yield
    _imputer(resultat.get_result(), item.nodeid)


@pytest.hookimpl(tryfirst=True)
def pytest_sessionfinish(session, exitstatus):
    with _verrou:
        restants = [m for messages in _refus.values() for m in messages]
        _refus.clear()
    if restants:
        session.config._garde_base_hors_test = restants
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    restants = getattr(config, "_garde_base_hors_test", None)
    if restants:
        terminalreporter.section("garde de la base (#638) — accès hors de tout test", red=True)
        for message in restants:
            terminalreporter.write_line(message)
