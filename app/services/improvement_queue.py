"""File d'amélioration native (ADR-0031 / #431).

Aucun numéro : uniquement `user` déjà anonymisé par l'appelant.
Persistance : voir lqe_paths (volume dédié /app/data/lqe en prod, issue #488).

Concurrence (#656). Toute lecture et toute écriture de la file passent par UN verrou
réentrant, et une réécriture est atomique (fichier temporaire, fsync, os.replace). Avant,
mesuré à UN SEUL worker : 39 tâches perdues sur 2000, 6 lignes devenues illisibles, et une
décision perdue dans 194 paires de décisions simultanées sur 200 — un worker ne sérialise
pas ces écritures, FastAPI exécutant les gestionnaires `def` dans un pool de fils.
- C'est un verrou DE PROCESSUS : il ne protège RIEN à N > 1 workers (voir le commentaire
  #520 de Dockerfile.prod). Passer à N > 1 exige d'abord de sortir la file du fichier.
- La boucle d'événements ne doit jamais l'attendre : un appelant `async` passe par
  `asyncio.to_thread`. Pris depuis une boucle, le module le journalise (sans lever).
- Une ligne illisible est comptée et journalisée, jamais ignorée en silence ; les
  réécritures la recopient telle quelle (on compte le dégât sans détruire ce qui se répare).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.services.lqe_paths import improvement_tasks_path

logger = logging.getLogger(__name__)

# Monkeypatch tests : si non None, prioritaire
DEFAULT_TASKS_PATH = None

# Réentrant : enqueue(skip_if_duplicate=True) relit la file sous le même verrou.
_VERROU = threading.RLock()


def _verrou() -> threading.RLock:
    """Le verrou de la file, signalé s'il est pris depuis la boucle d'événements.

    Journalise SANS LEVER, volontairement : `enqueue` a pour contrat de ne jamais lever, et
    un appelant `async` qui oublie `asyncio.to_thread` doit ralentir la boucle, pas casser
    le chat d'un agriculteur. Ne pas « renforcer » en `raise`. Le test structurel
    (tests/unit/test_improvement_queue_hors_boucle.py) empêche les oublis connus ; ceci
    nomme celui que personne n'aura vu venir."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _VERROU  # pas de boucle dans ce fil : c'est le cas normal
    logger.error("[LQE] verrou de la file pris DEPUIS LA BOUCLE d'événements : déporter "
                 "l'appel avec asyncio.to_thread (#656)")
    return _VERROU


def _decoder(lignes: list[str], target: Path) -> list[tuple[str, dict | None]]:
    """(ligne brute, objet ou None si illisible) ; les illisibles sont comptées."""
    out, illisibles = [], 0
    for ligne in lignes:
        if not ligne.strip():
            continue
        try:
            out.append((ligne, json.loads(ligne)))
        except json.JSONDecodeError:
            illisibles += 1
            out.append((ligne, None))
    if illisibles:
        logger.warning("[LQE] %d ligne(s) illisible(s) ignorée(s) dans %s", illisibles, target)
    return out


def _reecrire(target: Path, lignes: list[str]) -> None:
    """Atomique : un échec (disque plein, arrêt) laisse l'ancienne file entière."""
    tmp = target.with_name(f".{target.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lignes) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _tasks_path(path=None) -> Path:
    if path is not None:
        return Path(path)
    if DEFAULT_TASKS_PATH is not None:
        return Path(DEFAULT_TASKS_PATH)
    return improvement_tasks_path()


def content_fingerprint(
    *,
    language: str,
    text_local: str,
    text_fr: str = "",
    external_id: str | None = None,
) -> str:
    """Empreinte stable pour dédoublonnage (id externe ou hash textes)."""
    if external_id:
        return f"ext:{(language or '').lower()}:{external_id.strip().lower()}"
    raw = "|".join(
        [
            (language or "").strip().lower(),
            " ".join((text_local or "").strip().lower().split()),
            " ".join((text_fr or "").strip().lower().split()),
        ]
    )
    return "h:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def list_all_tasks(*, language: str | None = None, path=None) -> list[dict]:
    target = _tasks_path(path)
    with _verrou():
        if not target.is_file():
            return []
        try:
            lignes = target.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            logger.warning("[LQE] lecture file échouée (%s)", exc)
            return []
    out = []
    for _, row in _decoder(lignes, target):
        if row is None:
            continue
        lang = row.get("language") or "dyu"
        if language and lang != language:
            continue
        if not row.get("id"):
            row["id"] = row.get("ts") or ""
        out.append(row)
    return out


def existing_fingerprints(*, language: str, path=None) -> set[str]:
    fps: set[str] = set()
    for row in list_all_tasks(language=language, path=path):
        fp = row.get("fingerprint")
        if fp:
            fps.add(fp)
            continue
        fps.add(
            content_fingerprint(
                language=language,
                text_local=str(row.get("text_local") or row.get("excerpt") or ""),
                text_fr=str(row.get("text_fr") or ""),
                external_id=row.get("external_id"),
            )
        )
    return fps


def enqueue_improvement_task(
    *,
    intent: str | None,
    source: str | None,
    cultures: list | None,
    excerpt: str | None,
    user_anon: str | None,
    path: str | os.PathLike | None = None,
    language: str = "dyu",
    extra: dict | None = None,
    skip_if_duplicate: bool = False,
) -> dict:
    """Ajoute une tâche Bronze. Ne lève jamais."""
    lang = (language or "dyu").strip().lower()
    extra = dict(extra or {})
    text_local = str(extra.get("text_local") or excerpt or "")
    text_fr = str(extra.get("text_fr") or "")
    external_id = extra.get("external_id")
    fp = content_fingerprint(
        language=lang,
        text_local=text_local,
        text_fr=text_fr,
        external_id=external_id if isinstance(external_id, str) else None,
    )

    with _verrou():  # dédoublonnage et ajout : une seule section, sinon deux doublons passent
        return _ajouter(lang, fp, intent=intent, source=source, cultures=cultures, excerpt=excerpt,
                        user_anon=user_anon, path=path, extra=extra, skip_if_duplicate=skip_if_duplicate)


def _ajouter(lang, fp, *, intent, source, cultures, excerpt, user_anon, path, extra,
             skip_if_duplicate) -> dict:
    if skip_if_duplicate:
        if fp in existing_fingerprints(language=lang, path=path):
            return {"ok": True, "duplicate": True, "fingerprint": fp}

    task = {
        "id": uuid.uuid4().hex,
        "ts": datetime.now(timezone.utc).isoformat(),
        "status": "bronze",
        "language": lang,
        "intent": intent or "",
        "source": source or "unknown",
        "cultures": cultures or [],
        "excerpt": (excerpt or "")[:200],
        "user": user_anon or "",
        "fingerprint": fp,
    }
    for k, v in extra.items():
        if v is not None and k not in task:
            task[k] = v
    dumped = json.dumps(task, ensure_ascii=False)
    if "user_id" in dumped or "@s.whatsapp" in dumped:
        logger.error("[LQE] tâche refusée : PII détectée")
        return {"ok": False, "reason": "pii"}
    target = _tasks_path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(dumped + "\n")
        logger.info(
            "[LQE] Bronze lang=%s intent=%s path=%s",
            task["language"],
            task["intent"],
            target,
        )
        return {"ok": True, "task": task, "duplicate": False}
    except OSError as exc:
        logger.warning("[LQE] file indisponible (%s)", exc)
        return {"ok": False, "reason": "io"}


def list_tasks(*, status: str | None = "bronze", language: str = "dyu", path=None) -> list[dict]:
    out = []
    for row in list_all_tasks(language=language, path=path):
        if status and row.get("status") != status:
            continue
        out.append(row)
    return out


def decide_task(task_id: str, decision: str, *, path=None) -> dict:
    allowed = {
        "admin_accepted",
        "admin_rejected",
        "speaker_accepted",
        "speaker_rejected",
        "production",
    }
    if decision not in allowed:
        return {"ok": False, "reason": "bad_decision"}
    target = _tasks_path(path)
    with _verrou():  # lire, modifier, réécrire : une seule section (#656)
        if not target.is_file():
            logger.warning("[LQE] decide missing file id=%s path=%s", task_id, target)
            return {"ok": False, "reason": "missing", "path": str(target)}
        try:
            lines = target.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            logger.warning("[LQE] lecture file échouée (%s)", exc)
            return {"ok": False, "reason": "io"}
        found = False
        rewritten = []
        for line, row in _decoder(lines, target):
            if row is None:
                rewritten.append(line)  # recopiée telle quelle : on ne détruit pas un dégât
                continue
            rid = row.get("id") or row.get("ts") or ""
            if rid == task_id:
                row["status"] = decision
                found = True
            rewritten.append(json.dumps(row, ensure_ascii=False))
        if not found:
            return {"ok": False, "reason": "not_found", "path": str(target)}
        try:
            _reecrire(target, rewritten)
        except OSError as exc:
            logger.warning("[LQE] écriture file échouée (%s)", exc)
            return {"ok": False, "reason": "io"}
    return {"ok": True, "id": task_id, "status": decision}


# ---------------------------------------------------------------------------
# Boucle de retour (ADR-0040 / #558)
# ---------------------------------------------------------------------------

# Statut d'une tâche dont la réponse est validée et servie par le corpus.
# ADR-0031 : seul « production » est testé terrain — on ne rappelle l'agriculteur
# que sur ce niveau. Élargir ici si l'atelier décide de servir « Or » directement.
STATUTS_LIVRABLES = ("production",)


def list_deliverables(user_anon: str, *, path=None) -> list:
    """Questions de CET utilisateur désormais validées et pas encore remises.

    Recherche par EMPREINTE uniquement (`user`), jamais par numéro : l'appelant
    calcule l'empreinte dans le sens direct depuis l'identifiant qu'il détient
    (ADR-0040). Le sens inverse — empreinte → personne — reste impossible.

    Ne lève jamais : un défaut de lecture ne doit pas priver l'agriculteur de la
    réponse à sa question courante.
    """
    if not user_anon:
        return []
    target = _tasks_path(path)
    with _verrou():
        if not target.is_file():
            return []
        try:
            lines = target.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            logger.warning("[LQE] lecture file échouée (boucle de retour) : %s", exc)
            return []
    out = []
    for _, row in _decoder(lines, target):
        if row is None:
            continue
        if (
            row.get("user") == user_anon
            and row.get("status") in STATUTS_LIVRABLES
            and not row.get("delivered_at")
            and (row.get("excerpt") or "").strip()
        ):
            out.append(row)
    return out


def mark_delivered(task_id: str, *, path=None) -> dict:
    """Pose `delivered_at` : la réponse a été remise, on ne la répétera pas.

    Ne lève jamais.
    """
    target = _tasks_path(path)
    with _verrou():  # lire, modifier, réécrire : une seule section (#656)
        if not target.is_file():
            return {"ok": False, "reason": "missing"}
        try:
            lines = target.read_text(encoding="utf-8").splitlines()
        except OSError:
            return {"ok": False, "reason": "io"}
        found = False
        rewritten = []
        for line, row in _decoder(lines, target):
            if row is None:
                rewritten.append(line)
                continue
            if (row.get("id") or row.get("ts") or "") == task_id:
                row["delivered_at"] = datetime.now(timezone.utc).isoformat()
                found = True
            rewritten.append(json.dumps(row, ensure_ascii=False))
        if not found:
            return {"ok": False, "reason": "not_found"}
        try:
            _reecrire(target, rewritten)
        except OSError as exc:
            logger.warning("[LQE] écriture file échouée (remise) : %s", exc)
            return {"ok": False, "reason": "io"}
    return {"ok": True, "id": task_id}
