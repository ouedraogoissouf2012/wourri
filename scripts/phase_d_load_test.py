"""Wourri — Load test Sprint F Phase D (ADR-0008).

Génère 150+ queries variées via `corpus_facade.chercher_reponse_ivr` en mode
`dual` pour collecter des divergences réelles entre ChromaDB et pgvector.

**Pré-requis impératifs** :
- Container Postgres dev up (cf. `docker-compose.dev.yml`)
- Migration 0002 appliquée (`alembic upgrade head`)
- Corpus importé (`python scripts/import_corpus_ivr.py`)
- **`CORPUS_STORAGE_MODE=dual`** dans `.env` (sinon le script avorte avec un message)

Stratégie d'échantillonnage des 150 queries :
- 130 queries = tirage aléatoire d'entrées du corpus_ivr.json (avec leurs cultures)
- 20 queries = combinaisons (intent corpus × culture aléatoire) — teste les
  cas où la combinaison n'est pas explicitement dans le corpus
- Quelques cas hors-corpus (intent inconnu) — teste les `absence_*`

Appel direct à `corpus_facade.chercher_reponse_ivr` (pas HTTP, cf. décision
D7 du plan) : élimine la dépendance à DeepSeek/NeMo/TTS, cible exactement le
chemin testé par Phase D.

Après les 150 queries, attend ≥ 10s pour laisser les threads daemon finir,
puis appelle `/admin/corpus-divergence-report` et affiche le rapport JSON.

Validation manuelle des 5 critères ADR §Phase D :
- ≥ 100 queries comparées (script génère 150) ✓
- Divergences < 5 % (à vérifier dans le rapport)
- Aucune divergence `absence_*` non documentée (à vérifier dans top 10)
- Latence pgvector ≤ Chroma + 50 % (`latency_ratio` ≤ 1.5)
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path

# UTF-8 stdout/stderr (Windows console + caractères bambara/dioula).
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

try:
    from dotenv import load_dotenv

    load_dotenv(_HERE / ".env", override=False)
except ImportError:
    pass

_CORPUS_PATH = _HERE / "dictionnaires" / "corpus_ivr.json"
_TOTAL_QUERIES = 150  # ≥ 100 (critère ADR §Phase D #2)
_WAIT_THREADS_SECS = 15  # marge pour les threads daemon


def _build_query_plan(entries: list[dict]) -> list[tuple[str, list[str], list[str]]]:
    """Construit 150 paires (intent, cultures, conditions) à tester.

    Composition :
    - 130 tirées aléatoirement du corpus (avec leurs cultures réelles)
    - 15 combinaisons croisées (intent corpus × culture aléatoire du corpus)
    - 5 cas hors-corpus pour tester les classifications `absence_*`
    """
    rng = random.Random(42)  # seed fixe : reproductibilité

    all_intents = sorted({e["intent"] for e in entries})
    all_cultures = sorted({c for e in entries for c in e.get("cultures") or []})

    plan: list[tuple[str, list[str], list[str]]] = []

    # Bloc 1 : 130 entrées du corpus
    sampled = rng.sample(entries, min(130, len(entries)))
    while len(sampled) < 130:
        sampled.append(rng.choice(entries))
    for e in sampled[:130]:
        plan.append((
            e["intent"],
            list(e.get("cultures") or ["*"]),
            list(e.get("conditions") or []),
        ))

    # Bloc 2 : 15 combinaisons croisées
    for _ in range(15):
        intent = rng.choice(all_intents)
        culture = rng.choice(all_cultures)
        plan.append((intent, [culture], []))

    # Bloc 3 : 5 cas hors-corpus
    fake_intents = [
        "QUESTION_NON_AGRICOLE",
        "INTENT_INEXISTANT",
        "FAKE_PRODUCTION",
        "_UNKNOWN_",
        "TEST_HORS_CORPUS",
    ]
    for intent in fake_intents:
        plan.append((intent, ["CULTURE_RIZ"], []))

    rng.shuffle(plan)
    return plan


def _print_section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def main() -> int:
    _print_section("Wourri — Sprint F Phase D Load Test")

    # 1. Vérification mode dual
    from app.config import get_settings

    settings = get_settings()
    if settings.corpus_storage_mode != "dual":
        print(
            "ERREUR : corpus_storage_mode = "
            f"{settings.corpus_storage_mode!r} (attendu 'dual').\n"
            "Définir CORPUS_STORAGE_MODE=dual dans wouri-api/.env et relancer.",
            file=sys.stderr,
        )
        return 1
    print("[OK] corpus_storage_mode = 'dual'")

    # 2. Chargement corpus
    with open(_CORPUS_PATH, encoding="utf-8") as f:
        entries = json.load(f).get("entries", [])
    if not entries:
        print("ERREUR : corpus vide.", file=sys.stderr)
        return 2
    print(f"[OK] Corpus chargé : {len(entries)} entrées")

    # 3. Préchargement modèles (warm-up — mitigation R4 du plan : sinon les
    #    premières mesures latence pgvector sont polluées par le chargement
    #    du SentenceTransformer ~5s)
    print("[WARMUP] Préchargement Chroma + pgvector...")
    t0 = time.perf_counter()
    from app.services.corpus_facade import chercher_reponse_ivr, initialiser_vdb

    initialiser_vdb()  # mode dual : précharge les 2 stores (cf. corpus_facade)
    print(f"[WARMUP] OK ({time.perf_counter() - t0:.1f}s)")

    # 4. Plan des 150 queries
    plan = _build_query_plan(entries)
    _print_section(f"Exécution de {len(plan)} queries (mode dual)")

    t_start = time.perf_counter()
    for i, (intent, cultures, conditions) in enumerate(plan, start=1):
        try:
            chercher_reponse_ivr(intent, cultures, conditions)
        except Exception as e:
            print(f"  [WARN] Query {i} : {type(e).__name__}", file=sys.stderr)
        if i % 25 == 0:
            elapsed = time.perf_counter() - t_start
            print(f"  Progression : {i}/{len(plan)} ({elapsed:.1f}s écoulées)")
    print(f"[OK] {len(plan)} queries lancées en {time.perf_counter() - t_start:.1f}s")

    # 5. Attendre les threads daemon (comparaison + persistance)
    print(f"[WAIT] {_WAIT_THREADS_SECS}s pour les threads daemon...")
    time.sleep(_WAIT_THREADS_SECS)

    # 6. Récupération du rapport via l'endpoint
    _print_section("Rapport /admin/corpus-divergence-report")
    from fastapi.testclient import TestClient
    from app.main import app

    # FIX-5 (Phase D reviewer SÉCURITÉ M2) : éviter d'importer la variable
    # privée `_API_SECRET_KEY` depuis app.security. Lecture directe de l'env.
    api_key = os.getenv("API_SECRET_KEY", "").strip() or None
    headers = {"X-API-Key": api_key} if api_key else {}
    client = TestClient(app)
    resp = client.get("/admin/corpus-divergence-report?days=1", headers=headers)
    if resp.status_code != 200:
        print(f"ERREUR : endpoint retourne {resp.status_code}", file=sys.stderr)
        print(resp.text, file=sys.stderr)
        return 3

    report = resp.json()
    print(json.dumps(report, indent=2, ensure_ascii=False))

    # 7. Validation des 5 critères ADR §Phase D
    _print_section("Validation des 5 critères ADR §Phase D")

    total = report["total_queries"]
    div_rate = report["divergence_rate"]
    absence_chroma = report["by_classification"].get("absence_chroma", 0)
    absence_pg = report["by_classification"].get("absence_pgvector", 0)
    ratio = report.get("latency_ratio")

    crit_2 = total >= 100
    crit_3 = div_rate < 0.05
    crit_4 = absence_chroma == 0 and absence_pg == 0
    crit_5 = ratio is None or ratio <= 1.5

    ok = lambda b: "[OK] " if b else "[FAIL]"  # noqa: E731
    print(f"{ok(True)} 1. Mode dual actif (script tournait en dual)")
    print(f"{ok(crit_2)} 2. ≥ 100 queries comparées : {total}")
    print(f"{ok(crit_3)} 3. Divergences < 5 % : {div_rate:.1%}")
    print(f"{ok(crit_4)} 4. Aucune divergence absence : "
          f"absence_chroma={absence_chroma}, absence_pgvector={absence_pg}")
    print(f"{ok(crit_5)} 5. Latence pgvector ≤ Chroma + 50 % : "
          f"ratio={ratio:.2f}" if ratio is not None else
          f"{ok(crit_5)} 5. Latence : insuffisant de données (latency_ratio=None)")

    all_pass = crit_2 and crit_3 and crit_4 and crit_5
    if all_pass:
        print("\n✅ Phase D : TOUS les critères passent.")
        return 0
    print("\n⚠️  Phase D : certains critères échouent — investiguer avant Phase E.")
    return 4


if __name__ == "__main__":
    sys.exit(main())
