"""Wourri — Import du corpus IVR dans PostgreSQL + pgvector.

Sprint F Phase B (ADR-0008). Lit `dictionnaires/corpus_ivr.json` (162 entrées,
v2.3), calcule l'embedding `paraphrase-multilingual-MiniLM-L12-v2` (384 dims)
de chaque entrée et persiste le tout dans :

- `corpus_entries`           : 162 lignes (une par entrée IVR)
- `corpus_phrases_attestees` : ~157 lignes (phrases bambara CI attestées)
- `corpus_metadata`          : 4 clés (version, source, imported_at, entries_count)

Le script est **idempotent** : il TRUNCATE les 3 tables avant insertion. Cela
respecte la contrainte ADR-0008 §Phase B (« reproductible ») et garantit qu'un
ré-exécution donne le même résultat (pas d'effet de bord d'historique).

Le format `document_text` est volontairement identique à celui de
`vdb_service.py:155` (Phase E pourra basculer sans recalcul d'embeddings) :

    document_text = f"{reponse_fr} {tags joined} {phrases_attestees joined}"

Usage :

    cd wouri-api
    POSTGRES_URL="postgresql+psycopg://wourri:wourri_dev_2026@127.0.0.1:5433/wourri_dev" \\
        python scripts/import_corpus_ivr.py

    # Ou via .env (POSTGRES_URL=...) :
    python scripts/import_corpus_ivr.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# UTF-8 stdout/stderr (Windows console + caractères bambara/dioula)
# Pattern projet — cf. tools/profile_preload.py (Sprint C).
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# Charge .env si présent (cohérent avec uvicorn / alembic).
try:
    from dotenv import load_dotenv

    load_dotenv(_HERE / ".env", override=False)
except ImportError:
    pass

_CORPUS_PATH = _HERE / "dictionnaires" / "corpus_ivr.json"
_MODEL_PATH = _HERE / "modeles_manuels" / "paraphrase-multilingual-MiniLM-L12-v2"
_EMBEDDING_DIM = 384


def _resolve_url() -> str:
    """Cf. cross-référence dans `alembic/env.py::_resolve_url` (duplication
    intentionnelle, contrat identique : lève `RuntimeError` si URL absente).
    La version dans `tests/integration/test_corpus_schema.py` diverge
    intentionnellement (retourne `""` pour le skipif)."""
    url = os.getenv("POSTGRES_URL", "").strip()
    if url:
        return url
    try:
        from app.config import get_settings

        s = (get_settings().postgres_url or "").strip()
        if s:
            return s
    except Exception:
        pass
    raise RuntimeError(
        "POSTGRES_URL non définie. Renseignez-la dans wouri-api/.env "
        "(cf. .env.example) ou exportez-la avant d'invoquer ce script."
    )


def _build_document_text(entry: dict) -> str:
    """Reproduit à l'identique vdb_service.py:155 pour cohérence sémantique.

    Phase E pourra basculer sans recalculer d'embeddings (les vecteurs
    produits par cette fonction sont équivalents à ceux indexés dans Chroma).
    """
    tags_text = " ".join(entry.get("tags", []))
    phrases_text = " ".join(
        p.get("text", "") for p in entry.get("phrases_attestees", [])
    )
    return f"{entry.get('reponse_fr', '')} {tags_text} {phrases_text}"


def _load_corpus() -> dict:
    with open(_CORPUS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_model():
    """Charge le modèle SentenceTransformer local (paraphrase-multilingual)."""
    from sentence_transformers import SentenceTransformer

    if not _MODEL_PATH.exists():
        raise RuntimeError(
            f"Modèle introuvable : {_MODEL_PATH}. "
            "Phase B exige le même modèle que vdb_service.py "
            "(paraphrase-multilingual-MiniLM-L12-v2)."
        )
    print(f"[IMPORT] Chargement du modèle d'embedding : {_MODEL_PATH.name}")
    return SentenceTransformer(str(_MODEL_PATH))


def _truncate_all(conn) -> None:
    """Vide les 3 tables corpus (idempotence) — laisse alembic_version intact."""
    # CASCADE : corpus_phrases_attestees référence corpus_entries.
    from sqlalchemy import text

    conn.execute(
        text(
            "TRUNCATE TABLE corpus_phrases_attestees, corpus_entries, corpus_metadata "
            "RESTART IDENTITY CASCADE;"
        )
    )


def _format_vector(vec) -> str:
    """Sérialise un vecteur (numpy array ou liste) en littéral pgvector.

    Format attendu par pgvector : `[1.0,2.0,3.0]` (sans espaces requis).
    Combiné avec `CAST(:embedding AS vector)` côté SQL, cela évite toute
    dépendance à un adapter psycopg côté Python (test et prod restent
    portables sur n'importe quelle version de psycopg ≥ 3).
    """
    return "[" + ",".join(f"{float(x):.7f}" for x in vec) + "]"


def _import_entries(conn, entries: Iterable[dict], embeddings) -> tuple[int, int]:
    """Insère entries + phrases_attestees. Retourne (n_entries, n_phrases)."""
    from sqlalchemy import text

    insert_entry_sql = text(
        """
        INSERT INTO corpus_entries (
            id, intent, cultures, conditions, reponse_bambara, reponse_fr,
            score_validation, tags, source, document_text, embedding
        ) VALUES (
            :id, :intent, :cultures, :conditions, :reponse_bambara, :reponse_fr,
            :score_validation, :tags, :source, :document_text,
            CAST(:embedding AS vector)
        )
        """
    )
    insert_phrase_sql = text(
        """
        INSERT INTO corpus_phrases_attestees (entry_id, text, source)
        VALUES (:entry_id, :text, :source)
        """
    )

    n_entries = 0
    n_phrases = 0
    for entry, embedding in zip(entries, embeddings):
        cultures = entry.get("cultures") or ["*"]
        conditions = entry.get("conditions") or []
        tags = entry.get("tags") or []

        conn.execute(
            insert_entry_sql,
            {
                "id": entry["id"],
                "intent": entry["intent"],
                "cultures": cultures,
                "conditions": conditions,
                "reponse_bambara": entry["reponse_bambara"],
                "reponse_fr": entry.get("reponse_fr", ""),
                "score_validation": float(entry.get("score_validation", 0.5)),
                "tags": tags,
                "source": entry.get("source", "corpus_ivr"),
                "document_text": _build_document_text(entry),
                "embedding": _format_vector(embedding),
            },
        )
        n_entries += 1

        for phrase in entry.get("phrases_attestees", []):
            txt = phrase.get("text", "").strip()
            if not txt:
                continue
            conn.execute(
                insert_phrase_sql,
                {
                    "entry_id": entry["id"],
                    "text": txt,
                    "source": phrase.get("source", ""),
                },
            )
            n_phrases += 1

    return n_entries, n_phrases


def _upsert_metadata(conn, corpus: dict, n_entries: int) -> None:
    from sqlalchemy import text

    metadata = {
        "version": corpus.get("version", ""),
        "source": "dictionnaires/corpus_ivr.json",
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "entries_count": str(n_entries),
    }
    upsert_sql = text(
        """
        INSERT INTO corpus_metadata (key, value, updated_at)
        VALUES (:key, :value, NOW())
        ON CONFLICT (key) DO UPDATE
        SET value = EXCLUDED.value, updated_at = NOW()
        """
    )
    for key, value in metadata.items():
        conn.execute(upsert_sql, {"key": key, "value": value})


def main() -> int:
    print("[IMPORT] Wourri — Import corpus IVR → PostgreSQL + pgvector (Phase B)")
    url = _resolve_url()
    # Masque le mot de passe dans les logs (cohérent avec pratique projet).
    safe_url = url
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        if "@" in rest:
            creds, host = rest.rsplit("@", 1)
            user = creds.split(":", 1)[0] if ":" in creds else creds
            safe_url = f"{scheme}://{user}:***@{host}"
    print(f"[IMPORT] Cible : {safe_url}")

    corpus = _load_corpus()
    entries = corpus.get("entries", [])
    if not entries:
        print("[IMPORT] ERREUR : corpus vide.", file=sys.stderr)
        return 1
    print(f"[IMPORT] Corpus chargé : version={corpus.get('version')} entries={len(entries)}")

    model = _load_model()
    documents = [_build_document_text(e) for e in entries]
    print(f"[IMPORT] Calcul des {len(documents)} embeddings (dim={_EMBEDDING_DIM})...")
    embeddings = model.encode(
        documents,
        convert_to_numpy=True,
        show_progress_bar=False,
        normalize_embeddings=False,
    )
    if embeddings.shape[1] != _EMBEDDING_DIM:
        print(
            f"[IMPORT] ERREUR : dim modèle = {embeddings.shape[1]} "
            f"(attendu {_EMBEDDING_DIM}).",
            file=sys.stderr,
        )
        return 2

    from sqlalchemy import create_engine

    engine = create_engine(url, future=True)

    with engine.begin() as conn:
        _truncate_all(conn)
        n_entries, n_phrases = _import_entries(conn, entries, embeddings)
        _upsert_metadata(conn, corpus, n_entries)

    print(
        f"[IMPORT] OK — {n_entries} entries + {n_phrases} phrases_attestees "
        f"+ 4 metadata insérés."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
