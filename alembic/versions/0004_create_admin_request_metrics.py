"""create privacy-safe admin request metrics table (issue #41, ADR-0017)

La table ne contient que des métadonnées techniques non rattachées à une
personne. Aucun message, transcription, numéro de téléphone, user_id, IP,
query string, nom de fichier ou détail d'exception n'est stocké.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-29
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE admin_request_metrics (
            id                  BIGSERIAL   PRIMARY KEY,
            observed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            endpoint            TEXT        NOT NULL,
            method              VARCHAR(8)  NOT NULL,
            status_code         SMALLINT    NOT NULL
                CHECK (status_code BETWEEN 100 AND 599),
            duration_ms         INTEGER     NOT NULL
                CHECK (duration_ms >= 0),
            intent              TEXT,
            culture             TEXT,
            source              TEXT,
            asr_success         BOOLEAN,
            nlu_out_of_scope    BOOLEAN
        );
        """
    )
    op.execute(
        "COMMENT ON TABLE admin_request_metrics IS "
        "'Métadonnées techniques sans PII ni contenu utilisateur — ADR-0017';"
    )
    op.execute(
        "CREATE INDEX ix_admin_request_metrics_observed_at "
        "ON admin_request_metrics(observed_at DESC);"
    )
    op.execute(
        "CREATE INDEX ix_admin_request_metrics_status_code "
        "ON admin_request_metrics(status_code);"
    )
    op.execute(
        "CREATE INDEX ix_admin_request_metrics_intent "
        "ON admin_request_metrics(intent) WHERE intent IS NOT NULL;"
    )
    op.execute(
        "CREATE INDEX ix_admin_request_metrics_culture "
        "ON admin_request_metrics(culture) WHERE culture IS NOT NULL;"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS admin_request_metrics;")
