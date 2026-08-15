#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WOURI — Profilage mémoire du préchargement des modèles ML (Phase 0 audit).

Charge dans l'ordre les mêmes modèles que `app/main.py` lifespan, en mesurant
avant/après chaque chargement :
  - RSS (Resident Set Size = RAM réelle utilisée par le process Python)
  - VMS (Virtual Memory Size = mémoire virtuelle = RAM + swap/page file)
  - Mémoire système disponible (psutil.virtual_memory)
  - Durée du chargement

Les chiffres alimentent docs/audits/preload-2026-05.md (§ 10.1) et serviront
de base à l'ADR-0011 "Stratégie de préchargement des modèles ML".

NON-INVASIF : aucune modification de main.py ou des services. Le script
réutilise les mêmes loaders publics.

Usage :
    cd wouri-api
    python tools/profile_preload.py
    # ou pour limiter aux N premiers modèles :
    python tools/profile_preload.py --max 4
    # pour skip des étapes spécifiques :
    python tools/profile_preload.py --skip whisper,vdb

Conditions recommandées :
  - Aucune instance uvicorn de wouri-api ne tourne (sinon double comptage RAM).
  - Idéalement : fermer Chrome / VS Code lourds pour mesurer en isolation.
  - Lancer depuis un terminal frais (pas dans un venv déjà chargé en mémoire).

Sorties :
  - Console : tableau markdown lisible + résumé.
  - Fichier : docs/audits/profile_preload_<DATE>.json (résultats bruts,
    écriture incrémentale après chaque étape pour résister à un crash hard).

Robustesse :
  - try/except par étape : un échec sur Whisper n'empêche pas la suite.
  - Écriture JSON incrémentale : même en cas de crash process, les mesures
    déjà capturées sont persistées sur disque.
  - GC.collect() entre étapes pour mesures plus stables.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

# ── Chemins / sys.path ───────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent  # wouri-api/
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # certains services s'attendent à un CWD = wouri-api/

# ── Encodage console : forcer UTF-8 sur Windows (cp1252 par défaut) ──────────
# Les print() de ce script contiennent des caractères Unicode (Δ, é, ✅, —, …)
# qui crashent sur cp1252.
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# ── Dépendances tierces ──────────────────────────────────────────────────────
try:
    import psutil
except ImportError:
    print("ERREUR : psutil requis. Installer via 'pip install psutil'.", file=sys.stderr)
    sys.exit(2)


# ── Modèle de données ────────────────────────────────────────────────────────
@dataclass
class StepResult:
    step: int
    name: str
    started_at: str
    elapsed_sec: Optional[float] = None
    status: str = "pending"          # pending | success | error | skipped
    error_short: Optional[str] = None
    rss_before_mb: float = 0.0
    rss_after_mb: float = 0.0
    rss_delta_mb: float = 0.0
    vms_before_mb: float = 0.0
    vms_after_mb: float = 0.0
    vms_delta_mb: float = 0.0
    sys_avail_before_mb: float = 0.0
    sys_avail_after_mb: float = 0.0
    sys_avail_delta_mb: float = 0.0
    notes: list[str] = field(default_factory=list)


# ── Helpers psutil ───────────────────────────────────────────────────────────
_proc = psutil.Process(os.getpid())


def _bytes_to_mb(b: int) -> float:
    return round(b / (1024 * 1024), 1)


def _snapshot_proc() -> tuple[float, float]:
    """Retourne (RSS_mb, VMS_mb) du process Python courant."""
    info = _proc.memory_info()
    return _bytes_to_mb(info.rss), _bytes_to_mb(info.vms)


def _snapshot_sys_avail() -> float:
    """Retourne la mémoire système disponible (MB)."""
    return _bytes_to_mb(psutil.virtual_memory().available)


# ── Loaders (mêmes que main.py lifespan, dans le même ordre) ─────────────────
def _load_nlu():
    from app.services.nlu import get_nlu_service
    nlu = get_nlu_service()
    if nlu is None:
        raise RuntimeError("NLU non chargé (fichier nlu_concepts.json absent ?)")
    return nlu


def _load_translation_dict():
    """Charge le dictionnaire de traduction (sans NLLB).

    Reproduit le comportement de main.py post-ADR-0011 Phase 3 :
    le TranslationService init charge le dictionnaire (15779 mots BAM->FR
    + 22010 mots FR->BAM), NLLB reste lazy.
    """
    from app.services.translation import get_translation_service
    return get_translation_service()


def _load_nllb():
    """Charge NLLB-200 (distilled 600M) via preload_nllb().

    Le TranslationService doit déjà avoir été instancié (via
    `_load_translation_dict`). Ce step est lazy post-Phase 3, à utiliser
    avec `--skip nllb` pour mesurer le scénario optimisé.
    """
    from app.services.translation import get_translation_service
    service = get_translation_service()
    service.preload_nllb()
    return service


def _load_tts_bambara():
    from app.services.tts_bambara import get_tts_model
    return get_tts_model()


def _load_tts_dioula():
    from app.services.tts_dioula import get_tts_model_dioula
    return get_tts_model_dioula()


def _load_whisper():
    from app.services.stt_whisper import get_whisper_model
    return get_whisper_model()


def _load_vdb():
    from app.services.vdb_service import initialiser_vdb
    return initialiser_vdb()


# Liste ordonnée (key, label, loader) — l'ordre matche app/main.py lifespan
# Post-ADR-0011 Phase 3 : NLLB et Whisper sont skippés en eager.
# Pour mesurer le scénario post-Phase 3 : `--skip nllb,whisper`.
STEPS: list[tuple[str, str, Callable[[], object]]] = [
    ("nlu", "NLU JSON", _load_nlu),
    ("translation_dict", "Translation Dictionnaire (15779 mots BAM->FR)", _load_translation_dict),
    ("nllb", "NLLB-200 distilled 600M (traduction)", _load_nllb),
    ("tts_bam", "TTS Bambara mms-tts-bam (VITS)", _load_tts_bambara),
    ("tts_dyu", "TTS Dioula mms-tts-dyu (VITS)", _load_tts_dioula),
    ("whisper", "Faster-Whisper large-v3-turbo int8 (STT FR)", _load_whisper),
    ("vdb", "ChromaDB + MiniLM-L12-v2 (RAG)", _load_vdb),
]


# ── Coeur de l'instrumentation ───────────────────────────────────────────────
def _run_step(idx: int, key: str, label: str, loader: Callable[[], object]) -> StepResult:
    rss_before, vms_before = _snapshot_proc()
    sys_avail_before = _snapshot_sys_avail()
    started_at = datetime.now().isoformat(timespec="seconds")

    result = StepResult(
        step=idx,
        name=label,
        started_at=started_at,
        rss_before_mb=rss_before,
        vms_before_mb=vms_before,
        sys_avail_before_mb=sys_avail_before,
    )

    t0 = time.perf_counter()
    try:
        loader()
        result.status = "success"
    except Exception as exc:  # noqa: BLE001 — on veut capturer toute exception
        result.status = "error"
        # Message court pour le tableau ; trace détaillée logguée séparément
        result.error_short = f"{type(exc).__name__}: {exc}"[:160]
        traceback.print_exc(file=sys.stderr)
    finally:
        elapsed = time.perf_counter() - t0
        # Forcer un cycle GC pour des mesures plus stables (les modules
        # transformers gardent parfois des temporaires).
        gc.collect()

        rss_after, vms_after = _snapshot_proc()
        sys_avail_after = _snapshot_sys_avail()

        result.elapsed_sec = round(elapsed, 2)
        result.rss_after_mb = rss_after
        result.vms_after_mb = vms_after
        result.sys_avail_after_mb = sys_avail_after
        result.rss_delta_mb = round(rss_after - rss_before, 1)
        result.vms_delta_mb = round(vms_after - vms_before, 1)
        # Mémoire système : un delta positif = on a libéré, négatif = consommé.
        # On stocke la valeur signée pour clarté en sortie.
        result.sys_avail_delta_mb = round(sys_avail_after - sys_avail_before, 1)

    return result


def _persist_results(results: list[StepResult], json_path: Path, baseline: dict) -> None:
    """Écrit les résultats sur disque (incrémental). Atomique : tmp + replace."""
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "machine": {
            "platform": sys.platform,
            "python": sys.version.split()[0],
            "cpu_count": os.cpu_count(),
        },
        "system_memory_total_mb": _bytes_to_mb(psutil.virtual_memory().total),
        "baseline": baseline,
        "steps": [asdict(r) for r in results],
    }
    tmp_path = json_path.with_suffix(json_path.suffix + ".tmp")
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(json_path)


def _print_markdown_table(results: list[StepResult], baseline: dict) -> None:
    print()
    print("## Profil de préchargement ML — résultats")
    print()
    print(f"- Machine RAM totale : {baseline['sys_total_mb']:.0f} MB")
    print(f"- Process Python baseline (avant tout chargement) : "
          f"RSS={baseline['rss_mb']:.0f} MB, VMS={baseline['vms_mb']:.0f} MB")
    print(f"- Mémoire système disponible baseline : {baseline['sys_avail_mb']:.0f} MB")
    print()
    print("| # | Étape | Statut | Δ RSS (MB) | Δ VMS (MB) | Δ Sys avail (MB) | Durée (s) |")
    print("|---|---|---|---:|---:|---:|---:|")
    for r in results:
        status_icon = {
            "success": "✅",
            "error": "❌",
            "skipped": "⏭",
            "pending": "…",
        }.get(r.status, "?")
        name = r.name if r.status != "error" else f"{r.name} ({r.error_short})"
        print(
            f"| {r.step} | {name} | {status_icon} | "
            f"{r.rss_delta_mb:+.1f} | {r.vms_delta_mb:+.1f} | "
            f"{r.sys_avail_delta_mb:+.1f} | {r.elapsed_sec or 0:.2f} |"
        )

    # Cumul des deltas RSS sur succès uniquement
    cum_rss = sum(r.rss_delta_mb for r in results if r.status == "success")
    cum_vms = sum(r.vms_delta_mb for r in results if r.status == "success")
    print()
    print(f"**Cumul RSS (succès uniquement)** : {cum_rss:+.1f} MB")
    print(f"**Cumul VMS (succès uniquement)** : {cum_vms:+.1f} MB")

    # Mémoire système disponible finale
    if results:
        final_avail = results[-1].sys_avail_after_mb
        print(f"**Mémoire système disponible finale** : {final_avail:.0f} MB")


def main() -> int:
    parser = argparse.ArgumentParser(description="Profilage mémoire des modèles ML Wourri")
    parser.add_argument("--max", type=int, default=None,
                        help="Limiter aux N premiers modèles")
    parser.add_argument("--skip", type=str, default="",
                        help="Clés à skipper (séparées par virgule), ex: 'whisper,vdb'")
    parser.add_argument("--out", type=str, default=None,
                        help="Chemin du JSON de sortie (défaut: docs/audits/profile_preload_<DATE>.json)")
    args = parser.parse_args()

    skip_keys = {s.strip() for s in args.skip.split(",") if s.strip()}

    today = datetime.now().strftime("%Y-%m-%d")
    if args.out:
        json_path = Path(args.out)
    else:
        json_path = ROOT / "docs" / "audits" / f"profile_preload_{today}.json"

    # Baseline : process Python avant tout import lourd. Note : à ce stade,
    # on a déjà importé psutil + std lib, donc le RSS est non nul (~30-50 MB
    # typique). C'est notre point de référence.
    rss_baseline, vms_baseline = _snapshot_proc()
    baseline = {
        "rss_mb": rss_baseline,
        "vms_mb": vms_baseline,
        "sys_avail_mb": _snapshot_sys_avail(),
        "sys_total_mb": _bytes_to_mb(psutil.virtual_memory().total),
    }

    print(f"=== Profilage préchargement ML — {today} ===")
    print(f"Sortie JSON : {json_path}")
    print(f"Baseline : RSS={rss_baseline:.0f} MB, VMS={vms_baseline:.0f} MB, "
          f"Sys avail={baseline['sys_avail_mb']:.0f} / {baseline['sys_total_mb']:.0f} MB")
    print()

    results: list[StepResult] = []
    steps_to_run = STEPS if args.max is None else STEPS[: args.max]

    for idx, (key, label, loader) in enumerate(steps_to_run, start=1):
        if key in skip_keys:
            print(f"[{idx}/{len(steps_to_run)}] {label} — SKIP (--skip {key})")
            results.append(StepResult(
                step=idx, name=label,
                started_at=datetime.now().isoformat(timespec="seconds"),
                status="skipped",
            ))
            _persist_results(results, json_path, baseline)
            continue

        print(f"[{idx}/{len(steps_to_run)}] {label} — chargement…")
        result = _run_step(idx, key, label, loader)
        results.append(result)
        _persist_results(results, json_path, baseline)

        if result.status == "success":
            print(f"    OK en {result.elapsed_sec:.2f}s, "
                  f"Δ RSS = {result.rss_delta_mb:+.1f} MB, "
                  f"Δ Sys avail = {result.sys_avail_delta_mb:+.1f} MB")
        else:
            print(f"    ECHEC : {result.error_short}")

    _print_markdown_table(results, baseline)
    print()
    print(f"✅ Résultats persistés : {json_path}")

    # Code de sortie : 0 si toutes succès, 1 si au moins un échec
    has_errors = any(r.status == "error" for r in results)
    return 1 if has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
