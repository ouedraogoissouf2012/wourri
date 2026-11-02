"""catalogue des concepts NLU, lisible par l'atelier (ADR-0047, #600)

L'atelier doit pouvoir demander au locuteur les mots d'un concept qui n'en a
aucun. Or son conteneur n'a acces ni aux dictionnaires du moteur, ni a aucune
table de concepts : il ne peut donc pas les lui presenter.

Cette table est le pendant exact de `corpus_entries` pour les concepts NLU :
ecrite par le moteur (`scripts/import_nlu_concepts.py`), lue SEULEMENT par
l'atelier via `NluConceptCatalog`. Meme schema `public`, meme sens de lecture,
aucun couplage de systeme de fichiers entre les deux services.

`ref_dyu` porte les mots dioula du concept. Ils sont AFFICHES au locuteur comme
reference, JAMAIS copies : une traduction dioula n'est pas une traduction
baoule (ADR-0046).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-02
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE nlu_concepts (
            id          TEXT        PRIMARY KEY,
            label_fr    TEXT        NOT NULL,
            ref_dyu     TEXT        NOT NULL DEFAULT '',
            intent      TEXT        NOT NULL DEFAULT '',
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        COMMENT ON TABLE nlu_concepts IS
            'Catalogue des concepts NLU. Ecrit par le moteur, lu par l''atelier (ADR-0047).';
        COMMENT ON COLUMN nlu_concepts.ref_dyu IS
            'Mots dioula du concept : affiches comme reference, jamais copies (ADR-0046).';
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS nlu_concepts;")
