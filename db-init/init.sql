-- Wourri — Initialisation PostgreSQL + pgvector (Sprint F Phase A)
-- Exécuté automatiquement par le container PostgreSQL au premier démarrage
-- (mécanisme docker-entrypoint-initdb.d).
--
-- IMPORTANT : ne PAS ajouter de schéma applicatif ici.
-- Le DDL des tables corpus (corpus_entries, corpus_phrases_attestees, corpus_metadata)
-- est réservé à Phase B et géré via Alembic (migrations versionnées).
-- Référence : ADR-0008 §Phase B.

CREATE EXTENSION IF NOT EXISTS vector;
