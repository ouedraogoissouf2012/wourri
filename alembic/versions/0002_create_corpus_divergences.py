"""create corpus divergences table (Sprint F Phase D — ADR-0008)

Crée la table de persistance des divergences observées en mode `dual` entre
ChromaDB legacy et PostgreSQL+pgvector. Alimentée par `corpus_facade.
_compare_chercher_in_background` (thread daemon).

Schéma :
- `id BIGSERIAL PK`
- `observed_at TIMESTAMPTZ` — horodatage de la comparaison
- `intent`, `cultures TEXT[]`, `conditions TEXT[]` — query d'origine
- `chroma_id`, `pgvector_id` (nullable) — résultats des 2 stores
- `chroma_score`, `pgvector_score REAL` (nullable) — score_validation des 2 stores
- `classification` — `match` | `divergent` | `absence_chroma` | `absence_pgvector` | `reorder` (reorder réservé Phase E)
- `latency_chroma_ms`, `latency_pgvector_ms INTEGER` (nullable)

Index :
- B-tree sur `observed_at` — filtre `WHERE observed_at >= NOW() - INTERVAL '7 days'`
- B-tree sur `classification` — GROUP BY classification (rapport admin)

Pas d'index GIN sur cultures (volume Phase D ≤ 10k lignes, B-tree suffit pour les rapports).

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-20
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE corpus_divergences (
            id                  BIGSERIAL   PRIMARY KEY,
            observed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            intent              TEXT        NOT NULL,
            cultures            TEXT[]      NOT NULL,
            conditions          TEXT[]      NOT NULL DEFAULT ARRAY[]::TEXT[],
            chroma_id           TEXT,
            pgvector_id         TEXT,
            chroma_score        REAL,
            pgvector_score      REAL,
            classification      TEXT        NOT NULL
                CHECK (classification IN (
                    'match','reorder','divergent',
                    'absence_chroma','absence_pgvector'
                )),
            latency_chroma_ms   INTEGER,
            latency_pgvector_ms INTEGER
        );
        """
    )

    op.execute(
        "CREATE INDEX ix_corpus_divergences_observed_at "
        "ON corpus_divergences(observed_at);"
    )
    op.execute(
        "CREATE INDEX ix_corpus_divergences_classification "
        "ON corpus_divergences(classification);"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS corpus_divergences;")
