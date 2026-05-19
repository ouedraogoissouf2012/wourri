"""create corpus schema (Sprint F Phase B — ADR-0008)

Crée le schéma SQL applicatif Wourri pour le corpus IVR migré de ChromaDB
vers PostgreSQL + pgvector.

Tables :
- corpus_entries          : entrées IVR validées (intent + cultures + conditions + réponses bambara/FR + embedding)
- corpus_phrases_attestees: phrases bambara CI attestées (en relation 1:N avec corpus_entries)
- corpus_metadata         : métadonnées globales du corpus (version, source, date d'import)

Index :
- ivfflat sur corpus_entries.embedding (cosine) — recherche similarité sémantique
- GIN sur corpus_entries.cultures      — recherche par culture (array)
- GIN sur corpus_entries.conditions    — recherche par condition (array)
- GIN FTS français sur reponse_fr      — recherche plein texte (futur)

Pré-requis : extension `vector` créée par db-init/init.sql (Phase A).

Revision ID: 0001
Revises:
Create Date: 2026-05-19
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Dimension d'embedding du modèle paraphrase-multilingual-MiniLM-L12-v2
# (cohérent avec wouri-api/modeles_manuels/ et vdb_service.py actuel).
# Toute modification exige un nouveau ADR (impact direct sur tous les vecteurs).
# Cross-référence : `scripts/import_corpus_ivr.py::_EMBEDDING_DIM`,
# `tests/integration/test_corpus_schema.py` (littéral "vector(384)" et `["0"] * 384`).
_EMBEDDING_DIM = 384

# Défense en profondeur : la valeur est inlinée dans le DDL via f-string.
# Alembic ne supporte pas les paramètres bind pour les DDL — la seule barrière
# anti-injection est une validation explicite du type/valeur de la constante.
# Si un futur dev relie cette constante à `os.getenv()`, l'assertion bloquera
# tout entier non borné ou non numérique avant qu'il atteigne CREATE TABLE.
assert isinstance(_EMBEDDING_DIM, int) and 1 <= _EMBEDDING_DIM <= 4096, (
    f"_EMBEDDING_DIM invalide : {_EMBEDDING_DIM!r}"
)


def upgrade() -> None:
    # ── Extension pgvector ─────────────────────────────────────────────
    # Idempotent. Phase A la crée déjà via db-init/init.sql, mais on
    # garantit la présence ici pour rejouabilité sur une BDD existante.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # ── Table corpus_entries ───────────────────────────────────────────
    op.execute(
        f"""
        CREATE TABLE corpus_entries (
            id                  TEXT        PRIMARY KEY,
            intent              TEXT        NOT NULL,
            cultures            TEXT[]      NOT NULL DEFAULT ARRAY['*']::TEXT[],
            conditions          TEXT[]      NOT NULL DEFAULT ARRAY[]::TEXT[],
            reponse_bambara     TEXT        NOT NULL,
            reponse_fr          TEXT        NOT NULL DEFAULT '',
            score_validation    REAL        NOT NULL DEFAULT 0.5,
            tags                TEXT[]      NOT NULL DEFAULT ARRAY[]::TEXT[],
            source              TEXT        NOT NULL DEFAULT 'corpus_ivr',
            document_text       TEXT        NOT NULL,
            embedding           vector({_EMBEDDING_DIM}) NOT NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    # ── Table corpus_phrases_attestees ────────────────────────────────
    # Relation 1:N — une entrée peut avoir 0..N phrases attestées
    # (extraites des vidéos Access Agriculture / Common Voice dyu).
    op.execute(
        """
        CREATE TABLE corpus_phrases_attestees (
            id         BIGSERIAL   PRIMARY KEY,
            entry_id   TEXT        NOT NULL
                       REFERENCES corpus_entries(id)
                       ON DELETE CASCADE,
            text       TEXT        NOT NULL,
            source     TEXT        NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE INDEX ix_corpus_phrases_attestees_entry_id "
        "ON corpus_phrases_attestees(entry_id);"
    )

    # ── Table corpus_metadata ─────────────────────────────────────────
    # Clé/valeur (singleton de configuration : version, date import, etc.)
    op.execute(
        """
        CREATE TABLE corpus_metadata (
            key        TEXT        PRIMARY KEY,
            value      TEXT        NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    # ── Index secondaires sur corpus_entries ──────────────────────────
    # B-tree sur intent : filtre exact massif (cf. vdb_service._best_result)
    op.execute("CREATE INDEX ix_corpus_entries_intent ON corpus_entries(intent);")

    # GIN sur arrays cultures / conditions : permet `WHERE cultures && ARRAY[...]`
    op.execute(
        "CREATE INDEX ix_corpus_entries_cultures "
        "ON corpus_entries USING GIN (cultures);"
    )
    op.execute(
        "CREATE INDEX ix_corpus_entries_conditions "
        "ON corpus_entries USING GIN (conditions);"
    )

    # GIN FTS français sur reponse_fr (préparation Phase C : recherche
    # plein texte fallback si la recherche vectorielle ne match pas).
    op.execute(
        "CREATE INDEX ix_corpus_entries_reponse_fr_fts "
        "ON corpus_entries USING GIN (to_tsvector('french', reponse_fr));"
    )

    # ── Index ivfflat sur embedding (cosine) ──────────────────────────
    # `lists = 10` : choix calibré pour le corpus Phase B (162 entrées).
    # Contrainte pgvector : le planner PostgreSQL n'utilise l'index ivfflat
    # que si `rows >= lists × 3`. Avec lists = 100, il faudrait au moins
    # 300 vecteurs pour activer l'index — trop pour Phase B. Avec lists = 10,
    # le seuil tombe à 30 vecteurs, largement atteint dès l'import (162).
    #
    # Tuning futur (Phase D ou nouvel ADR) :
    #   - lists ≈ rows / 1000 pour rows < 1M (pgvector recommandation)
    #   - 10k entrées  → lists = 10  (toujours valide)
    #   - 100k entrées → lists = 100 (recréer l'index : DROP + CREATE)
    op.execute(
        "CREATE INDEX ix_corpus_entries_embedding_ivfflat "
        "ON corpus_entries USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 10);"
    )


def downgrade() -> None:
    # Drop dans l'ordre inverse (les index sont supprimés en cascade
    # avec leur table, mais on est explicite pour la lisibilité).
    op.execute("DROP TABLE IF EXISTS corpus_phrases_attestees;")
    op.execute("DROP TABLE IF EXISTS corpus_entries;")
    op.execute("DROP TABLE IF EXISTS corpus_metadata;")
    # NB : on NE drop PAS l'extension `vector` — elle est gérée par
    # db-init/init.sql (Phase A) et peut être utilisée par d'autres
    # schémas applicatifs futurs.
