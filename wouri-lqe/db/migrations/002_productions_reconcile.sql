-- ADR-0034 P4 — reconciliation du flux atelier sur une table unique lqe.productions.
-- Le flux (ingest -> decide -> promote) et la couverture partagent desormais CETTE
-- table (status bronze -> admin_accepted -> production), fin du stockage JSONL.
-- Contrainte runner (migrate._statements) : aucun ';' dans un litteral.

ALTER TABLE productions ALTER COLUMN concept_id DROP NOT NULL;

ALTER TABLE productions ADD COLUMN IF NOT EXISTS fingerprint text;

ALTER TABLE productions ADD COLUMN IF NOT EXISTS meta jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE productions ADD COLUMN IF NOT EXISTS promoted_by text;

ALTER TABLE productions ADD COLUMN IF NOT EXISTS promoted_at timestamptz;

ALTER TABLE productions DROP CONSTRAINT IF EXISTS productions_status_check;

ALTER TABLE productions ADD CONSTRAINT productions_status_check CHECK (status IN ('bronze', 'admin_accepted', 'admin_rejected', 'production'));

CREATE UNIQUE INDEX IF NOT EXISTS uq_productions_language_fingerprint ON productions (language, fingerprint) WHERE fingerprint IS NOT NULL;
