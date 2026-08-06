"""Wourri — Service BD Vectorielle IVR — adapter PostgreSQL+pgvector (ADR-0008 §Phase C).

Adapter strictement compatible avec l'API de `vdb_service.py` (ChromaDB legacy).
Cible : remplacer ChromaDB par PostgreSQL+pgvector à terme (Phase E).

API publique identique à `vdb_service` :
- `chercher_reponse_ivr(intent, cultures, conditions=None) -> dict | None`
- `ajouter_reponse_validee(intent, cultures, reponse_bambara, reponse_fr, score_validation, conditions=None, tags=None) -> bool`
- `get_reponse_fallback() -> str`
- `get_phrases_for_intent(intent, cultures) -> list[dict]`
- `initialiser_vdb() -> None`

**Logique métier** : cascade 3 essais + scoring saison/conditions copie fidèle
de `vdb_service._best_result` (vdb_service.py:245-293). Format `document_text`
identique à `vdb_service.py:155` (cohérence sémantique des embeddings — Phase E
ne recalculera PAS les vecteurs).

**Logs** : préfixe `[VDB-PG]` (distinct du `[VDB]` chromadb) pour observabilité
en mode dual (Phase D).

**Singletons lazy** :
- `_get_engine()` : SQLAlchemy engine, créé au premier appel via `lru_cache`
- `_get_model()` : SentenceTransformer paraphrase-multilingual, idem

Aucun I/O au module import (cf. discipline tests unit avec mock).
"""
from __future__ import annotations

import logging
import time
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.services.corpus import season_scoring

logger = logging.getLogger(__name__)

_MODEL_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "modeles_manuels"
    / "paraphrase-multilingual-MiniLM-L12-v2"
)
_EMBEDDING_DIM = 384

# Fallback bambara hardcodé (identique à vdb_service.py:342)
_FALLBACK_BAMBARA = "N bɛ i dɛmɛ i ka sɛnɛ ko la. I ka i ka ɲinini wele fɔ cogo wɛrɛ."


def _safe_error(e: Exception) -> str:
    """Retourne une représentation log-safe d'une exception SQLAlchemy/psycopg.

    Évite la fuite de credentials : `psycopg.OperationalError` peut inclure
    l'URL complète (`postgresql+psycopg://user:password@host/db`) dans son
    message. On garde le type + un message tronqué qui exclut les motifs
    sensibles (`@`, `password=`, `://`).
    """
    msg = str(e)
    # Tronque agressivement à 200 chars et masque les URL connues
    for pattern in ("postgresql+psycopg://", "postgresql://", "password="):
        if pattern in msg:
            return f"{type(e).__name__} (message masqué — contient un secret potentiel)"
    if len(msg) > 200:
        msg = msg[:200] + "..."
    return f"{type(e).__name__}: {msg}"


# ─────────────────────────────────────────────────────────────────────────
# Singletons lazy
# ─────────────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _get_engine():
    """Retourne l'engine SQLAlchemy (créé une fois, partagé)."""
    from sqlalchemy import create_engine

    from app.db.url_resolver import resolve_postgres_url

    url = resolve_postgres_url(raise_on_missing=True)
    logger.info("[VDB-PG] Initialisation engine SQLAlchemy")
    return create_engine(url, future=True, pool_pre_ping=True)


@lru_cache(maxsize=1)
def _get_model():
    """Charge le modèle SentenceTransformer local (paraphrase-multilingual)."""
    from sentence_transformers import SentenceTransformer

    if not _MODEL_PATH.exists():
        raise RuntimeError(
            f"[VDB-PG] Modèle introuvable : {_MODEL_PATH}. "
            "Phase C exige le même modèle que vdb_service.py "
            "(paraphrase-multilingual-MiniLM-L12-v2)."
        )
    logger.info("[VDB-PG] Chargement modèle d'embedding : %s", _MODEL_PATH.name)
    return SentenceTransformer(str(_MODEL_PATH))


# ─────────────────────────────────────────────────────────────────────────
# Helpers internes (reproduits de vdb_service.py pour cohérence métier)
# ─────────────────────────────────────────────────────────────────────────


def _format_vector(vec) -> str:
    """Sérialise un vecteur en littéral pgvector `[1.0,2.0,...]`.

    Dupliqué intentionnellement de `scripts/import_corpus_ivr.py:_format_vector`
    (2 consommateurs < seuil 4 du projet). Évite un couplage entre le script
    one-shot d'import et ce module de service (le script manipule `sys.path`).

    Issue #184 : defense en profondeur. Si un modele downgrade ou un mock test
    produit une dimension autre que `_EMBEDDING_DIM`, on leve plutot que
    d'inserer un vecteur invalide qui produirait une erreur SQL opaque cote
    pgvector. Symetrique avec l'assertion defensive de
    `alembic/versions/0001_create_corpus_schema.py:47` (FIX-4 Phase B).
    """
    if len(vec) != _EMBEDDING_DIM:
        raise ValueError(
            f"Embedding dim mismatch: {len(vec)} != {_EMBEDDING_DIM}"
        )
    return "[" + ",".join(f"{float(x):.7f}" for x in vec) + "]"


def _embed_query(text: str):
    """Encode une chaîne de requête via le modèle local. Retourne numpy array.

    `normalize_embeddings=False` : cohérent avec `scripts/import_corpus_ivr.py:251`
    (les vecteurs en base ont été calculés sans normalisation). La distance
    cosine pgvector (`<=>`) est invariante à l'échelle pour des comparaisons
    *internes pgvector* — c'est ce qui compte pour la recherche.

    Cohérence cross-store Chroma↔pgvector : validée empiriquement par
    `tests/integration/test_corpus_facade.py::test_50_queries_match_at_least_90_percent`
    (≥ 90 % de match observé). Si Phase D révèle un taux < 90 %, investiguer le
    biais d'embedding ChromaDB (qui peut normaliser via `SentenceTransformerEmbeddingFunction`).
    """
    model = _get_model()
    return model.encode(
        [text], convert_to_numpy=True, show_progress_bar=False, normalize_embeddings=False
    )[0]


def _best_result_pg(
    rows: list[dict], conditions: list[str], season: str | None = None
) -> dict | None:
    """Sélectionne la meilleure entrée parmi les candidats pgvector.

    Le scoring métier (saison + conditions) est délégué à
    `season_scoring.score_entry` — logique partagée avec le backend Chroma
    (`vdb_service._best_result`). Ce backend ne fait que son I/O : mapper les
    `rows` SQL (conditions déjà en array Postgres) vers la structure de sortie.

    Args:
        rows: candidats `{id, intent, cultures, conditions, reponse_bambara,
            reponse_fr, score_validation}` retournés par la requête SQL.
        season: saison courante, injectable pour les tests ; par défaut
            `season_scoring.get_current_season()`.
    """
    if not rows:
        return None

    if season is None:
        season = season_scoring.get_current_season()
    best = None
    best_score = -1.0

    for row in rows:
        base = float(
            row.get("score_validation", season_scoring.DEFAULT_VALIDATION_SCORE)
        )
        # pgvector stocke les conditions en array natif → déjà une liste.
        entry_conditions = list(row.get("conditions") or [])
        score = season_scoring.score_entry(base, entry_conditions, conditions, season)

        if score > best_score:
            best_score = score
            cultures_list = list(row.get("cultures") or ["*"])
            best = {
                "id": row["id"],
                "reponse_bambara": row["reponse_bambara"],
                "reponse_fr": row.get("reponse_fr", "") or "",
                "score_validation": base,
                "intent": row["intent"],
                # Cohérence avec vdb_service : Chroma stockait `cultures` en CSV ;
                # ici on retourne la 1re culture (la plus spécifique) en string.
                "cultures": cultures_list[0] if cultures_list else "*",
            }

    return best


def _query_candidates(intent: str, query_text: str, culture_filter: Optional[str]) -> list[dict]:
    """Exécute une requête SQL pgvector avec filtres intent + culture optionnels.

    Retourne jusqu'à 5 candidats ordonnés par distance cosine croissante.
    """
    from sqlalchemy import text

    query_emb = _embed_query(query_text)
    emb_literal = _format_vector(query_emb)

    if culture_filter is not None:
        sql = text(
            """
            SELECT id, intent, cultures, conditions, reponse_bambara, reponse_fr,
                   score_validation
            FROM corpus_entries
            WHERE intent = :intent
              AND cultures && ARRAY[:culture]::text[]
            ORDER BY embedding <=> CAST(:query_emb AS vector)
            LIMIT 5
            """
        )
        params = {"intent": intent, "culture": culture_filter, "query_emb": emb_literal}
    else:
        sql = text(
            """
            SELECT id, intent, cultures, conditions, reponse_bambara, reponse_fr,
                   score_validation
            FROM corpus_entries
            WHERE intent = :intent
            ORDER BY embedding <=> CAST(:query_emb AS vector)
            LIMIT 5
            """
        )
        params = {"intent": intent, "query_emb": emb_literal}

    engine = _get_engine()
    with engine.connect() as conn:
        result = conn.execute(sql, params)
        return [dict(row._mapping) for row in result]


# ─────────────────────────────────────────────────────────────────────────
# API publique (signatures identiques à vdb_service.py)
# ─────────────────────────────────────────────────────────────────────────


def chercher_reponse_ivr(
    intent: str, cultures: list[str], conditions: list[str] = None
) -> dict | None:
    """Cherche la meilleure réponse dans corpus_entries.

    Stratégie en cascade (identique à vdb_service.py:171-242) :
    1. Filtre intent + culture exacte (pour chaque culture donnée)
    2. Filtre intent + culture wildcard `*`
    3. Filtre intent seul

    Returns: dict `{id, reponse_bambara, reponse_fr, score_validation, intent, cultures}`
    ou None si aucun match.
    """
    conditions = conditions or []

    # Essai 1 : intent + chaque culture exacte
    for culture in cultures:
        try:
            rows = _query_candidates(intent, f"{intent} {culture}", culture)
            best = _best_result_pg(rows, conditions)
            if best:
                logger.info(
                    "[VDB-PG] Match exact: %s (intent=%s, culture=%s)",
                    best["id"], intent, culture,
                )
                return best
        except Exception as e:
            logger.warning("[VDB-PG] Erreur essai 1 (culture=%s): %s", culture, _safe_error(e))

    # Essai 2 : intent + wildcard
    try:
        rows = _query_candidates(intent, intent, "*")
        best = _best_result_pg(rows, conditions)
        if best:
            logger.info(
                "[VDB-PG] Match générique: %s (intent=%s, culture=*)",
                best["id"], intent,
            )
            return best
    except Exception as e:
        logger.warning("[VDB-PG] Erreur essai 2 (wildcard): %s", _safe_error(e))

    # Essai 3 : intent seul (toutes cultures)
    try:
        query_text = f"{intent} {' '.join(cultures)}".strip()
        rows = _query_candidates(intent, query_text, None)
        best = _best_result_pg(rows, conditions)
        if best:
            logger.info("[VDB-PG] Match intent seul: %s (intent=%s)", best["id"], intent)
            return best
    except Exception as e:
        logger.warning("[VDB-PG] Erreur essai 3 (intent seul): %s", _safe_error(e))

    logger.info("[VDB-PG] Aucun résultat pour intent=%s, cultures=%s", intent, cultures)
    return None


def ajouter_reponse_validee(
    intent: str,
    cultures: list[str],
    reponse_bambara: str,
    reponse_fr: str,
    score_validation: float,
    conditions: list[str] = None,
    tags: list[str] = None,
) -> bool:
    """Insère une nouvelle réponse validée dans corpus_entries.

    ⚠️ STATUT (2026-08-05) : **aucun appelant de production** depuis ADR-0019.
    Conservée délibérément comme adapter pgvector de la **double-écriture**
    (ADR-0008 Phase C-D, à reprendre). Ne pas supprimer sans ADR. Cf.
    `corpus_facade.ajouter_reponse_validee`.

    Format `document_text` (entrée dynamique) : `f"{reponse_fr} {' '.join(tags)}"`.
    Identique à `vdb_service.ajouter_reponse_validee` (vdb_service.py:315) — les
    entrées dynamiques n'ont pas de `phrases_attestees` à leur création.

    NB — distinct du format d'import initial (`scripts/import_corpus_ivr.py::
    _build_document_text` qui inclut `phrases_attestees`). C'est intentionnel :
    les phrases attestées sont collectées humainement après création initiale
    via les vidéos Access Agriculture / Common Voice. Cohérence sémantique
    inter-stores : on reproduit fidèlement le comportement Chroma legacy.
    """
    from sqlalchemy import text

    conditions = conditions or []
    tags = tags or []
    entry_id = f"dynamic_{intent}_{cultures[0] if cultures else 'generic'}_{int(time.time())}"

    document_text = f"{reponse_fr} {' '.join(tags)}".strip()
    try:
        emb = _embed_query(document_text or reponse_fr or intent)
        emb_literal = _format_vector(emb)

        engine = _get_engine()
        with engine.begin() as conn:
            conn.execute(
                text(
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
                ),
                {
                    "id": entry_id,
                    "intent": intent,
                    "cultures": list(cultures) if cultures else ["*"],
                    "conditions": list(conditions),
                    "reponse_bambara": reponse_bambara,
                    "reponse_fr": reponse_fr or "",
                    "score_validation": float(score_validation),
                    "tags": list(tags),
                    "source": "auto_validated",
                    "document_text": document_text,
                    "embedding": emb_literal,
                },
            )
        logger.info(
            "[VDB-PG] Nouvelle entrée validée ajoutée: %s (score=%.2f)",
            entry_id, score_validation,
        )
        return True
    except Exception as e:
        logger.error("[VDB-PG] Erreur ajout entrée: %s", _safe_error(e))
        return False


def get_reponse_fallback() -> str:
    """Retourne la réponse bambara de sécurité (intent=_FALLBACK ou hardcoded)."""
    from sqlalchemy import text

    try:
        engine = _get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT reponse_bambara FROM corpus_entries "
                    "WHERE intent = :intent LIMIT 1"
                ),
                {"intent": "_FALLBACK"},
            ).first()
            if row:
                return row[0]
    except Exception as e:
        logger.warning("[VDB-PG] Erreur lecture fallback: %s", _safe_error(e))
    return _FALLBACK_BAMBARA


def get_phrases_for_intent(intent: str, cultures: list[str]) -> list[dict]:
    """Retourne les phrases attestées du 1er match (intent + culture parmi celles donnees + '*').

    Décision D6 ADR-0008 §Phase C : lit `corpus_phrases_attestees` via SQL
    (cohérence avec le store pgvector + autonomie Phase E vs vdb_service qui
    lisait le corpus JSON en mémoire).

    Returns: list de dicts `{text, source, langue?}` (forme compatible vdb_service).
    """
    from sqlalchemy import text

    cultures_filter = list(cultures) + ["*"]
    try:
        engine = _get_engine()
        with engine.connect() as conn:
            # Trouve la 1re entrée matchant intent + culture (priorité à la 1re
            # culture donnée), puis récupère ses phrases attestées.
            entry_row = conn.execute(
                text(
                    """
                    SELECT id FROM corpus_entries
                    WHERE intent = :intent
                      AND cultures && CAST(:cultures AS text[])
                    ORDER BY array_position(CAST(:cultures AS text[]), cultures[1])
                             NULLS LAST
                    LIMIT 1
                    """
                ),
                {"intent": intent, "cultures": cultures_filter},
            ).first()
            if not entry_row:
                return []
            entry_id = entry_row[0]

            rows = conn.execute(
                text(
                    "SELECT text, source FROM corpus_phrases_attestees "
                    "WHERE entry_id = :entry_id ORDER BY id"
                ),
                {"entry_id": entry_id},
            ).all()
            return [{"text": r[0], "source": r[1] or ""} for r in rows]
    except Exception as e:
        logger.warning(
            "[VDB-PG] Erreur lecture phrases_attestees (intent=%s): %s", intent, _safe_error(e)
        )
        return []


def initialiser_vdb() -> None:
    """Pré-initialise l'engine + modèle au démarrage (équivalent vdb_service.initialiser_vdb).

    Précharge le modèle SentenceTransformer pour éviter une charge tardive en mode
    dual (risque R3 du plan : double-charge mémoire avec Chroma simultané).
    """
    logger.info("[VDB-PG] Initialisation BD vectorielle Postgres...")
    try:
        from sqlalchemy import text

        engine = _get_engine()
        _ = _get_model()  # précharge (R3 mitigation)

        with engine.connect() as conn:
            count = conn.execute(text("SELECT count(*) FROM corpus_entries")).scalar()
        logger.info("[VDB-PG] Prête — %s entrées", count)
    except Exception as e:
        logger.warning("[VDB-PG] BD Postgres non disponible: %s", _safe_error(e))
