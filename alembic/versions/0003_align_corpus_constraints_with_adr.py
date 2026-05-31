"""align corpus constraints with ADR-0008 (Sprint L #178)

Issue #178 : 2 divergences mineures entre la migration 0001 livree et ADR-0008
sont realignees ici (defense en profondeur). Ne casse aucune entree existante
(162/162 ont score_validation dans [0, 1] et reponse_fr non-nul).

Divergence 1 : `score_validation REAL` sans `CHECK`
  ADR-0008 §Phase B specifie `NUMERIC(3,2) ... CHECK (score_validation
  BETWEEN 0.0 AND 1.0)`. La migration 0001 utilise `REAL NOT NULL DEFAULT 0.5`
  sans contrainte de borne. On garde le type `REAL` (pas de risque de
  ré-encoder les 162 entrées) mais on ajoute la `CHECK` constraint.

Divergence 2 : `reponse_fr NOT NULL DEFAULT ''` vs `TEXT` nullable
  ADR specifie `reponse_fr TEXT` (nullable). On retire `NOT NULL`.
  Impact : distinction NULL vs '' (chaine vide) preservee pour les futures
  insertions. Aucune migration de donnees requise (NULL > '' n'est pas vrai
  cote tri/comparaison).

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-31
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Divergence 1 : CHECK constraint sur score_validation ──────────
    # Idempotent via le nom de contrainte : si elle existe deja, ALTER TABLE
    # ADD CONSTRAINT echoue. On utilise un guard SQL minimaliste (information_schema).
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'chk_score_validation_range'
                  AND conrelid = 'public.corpus_entries'::regclass
            ) THEN
                ALTER TABLE corpus_entries
                ADD CONSTRAINT chk_score_validation_range
                CHECK (score_validation >= 0.0 AND score_validation <= 1.0);
            END IF;
        END$$;
        """
    )

    # ── Divergence 2 : DROP NOT NULL sur reponse_fr ───────────────────
    # ALTER COLUMN DROP NOT NULL est idempotent en Postgres (no-op si deja nullable).
    op.execute("ALTER TABLE corpus_entries ALTER COLUMN reponse_fr DROP NOT NULL;")


def downgrade() -> None:
    # Reciproque : remet `NOT NULL` (necessite que toutes les valeurs soient
    # non-NULL — backfill defensif avec '' avant le NOT NULL).
    op.execute("UPDATE corpus_entries SET reponse_fr = '' WHERE reponse_fr IS NULL;")
    op.execute("ALTER TABLE corpus_entries ALTER COLUMN reponse_fr SET NOT NULL;")
    op.execute(
        "ALTER TABLE corpus_entries DROP CONSTRAINT IF EXISTS chk_score_validation_range;"
    )
