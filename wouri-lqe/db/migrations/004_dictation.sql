-- ADR-0035 — collecte du dataset ASR par dictee guidee (phrase imposee -> audio).
-- Table ISOLEE du flux de parite (productions) : le texte est impose au locuteur
-- (transcription garantie) et un audio de dictee ne couvre AUCUN concept. Cycle de vie
-- propre : todo -> recorded. Idempotence de l'import via (language, prompt_hash).
-- Contrainte runner (migrate._statements) : aucun ';' dans un litteral.

CREATE TABLE IF NOT EXISTS dictation (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    language     text NOT NULL REFERENCES languages(code) ON DELETE CASCADE,
    filiere      text NOT NULL DEFAULT '',
    text_local   text NOT NULL,
    text_fr      text NOT NULL DEFAULT '',
    prompt_hash  text NOT NULL,
    audio_url    text,
    status       text NOT NULL DEFAULT 'todo',
    recorded_by  text,
    recorded_at  timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT dictation_status_check CHECK (status IN ('todo', 'recorded'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_dictation_language_prompt ON dictation (language, prompt_hash);

CREATE INDEX IF NOT EXISTS idx_dictation_language_status ON dictation (language, status);
