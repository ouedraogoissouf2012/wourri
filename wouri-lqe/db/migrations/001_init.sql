-- ADR-0034 P0 — socle de l'atelier de parite linguistique.
-- Les tables sont creees dans le schema pointe par search_path (regle par le runner).
-- Contrainte : pas de ';' dans les litteraux (le runner decoupe sur ';').

CREATE TABLE IF NOT EXISTS languages (
    code           text PRIMARY KEY,                 -- ISO 639-3 : dyu, bci, btg...
    name           text NOT NULL,
    family         text,
    script         text NOT NULL DEFAULT 'Latn',
    asr_available  boolean NOT NULL DEFAULT false,
    tts_available  boolean NOT NULL DEFAULT false,
    status         text NOT NULL DEFAULT 'backlog',  -- active | backlog
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS assignments (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    concept_id       text NOT NULL,                  -- = id du corpus IVR
    target_language  text NOT NULL REFERENCES languages(code) ON DELETE CASCADE,
    source_fr        text NOT NULL,                  -- pivot francais extrait
    status           text NOT NULL DEFAULT 'open',   -- open | done | cancelled
    assigned_by      text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (concept_id, target_language)
);

CREATE TABLE IF NOT EXISTS productions (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    concept_id   text NOT NULL,
    language     text NOT NULL REFERENCES languages(code) ON DELETE CASCADE,
    text_local   text,
    text_fr      text,
    audio_url    text,
    intent       text,
    cultures     text[] NOT NULL DEFAULT '{}',
    status       text NOT NULL DEFAULT 'bronze',     -- bronze | admin_accepted | production
    created_by   text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS media (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    production_id  bigint REFERENCES productions(id) ON DELETE CASCADE,
    url            text NOT NULL,
    mime           text,
    duration_s     numeric,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_productions_concept_lang ON productions (concept_id, language);
CREATE INDEX IF NOT EXISTS idx_assignments_lang_status ON assignments (target_language, status);
