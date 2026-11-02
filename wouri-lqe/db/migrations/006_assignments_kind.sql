-- ADR-0047 (#600) : une assignation dit desormais CE QU'IL FAUT PRODUIRE.
--
-- Jusqu'ici une assignation portait toujours sur une phrase du corpus. Le second
-- catalogue (concepts NLU) demande au locuteur un MOT-CLE, pas une phrase : sans
-- cette colonne, « Produire » creerait un contenu et le mot n'arriverait jamais
-- dans son concept.
--
-- Defaut 'contenu' : les assignations existantes gardent exactement leur sens.
ALTER TABLE assignments
    ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'contenu';

COMMENT ON COLUMN assignments.kind IS
    'Type de fiche attendu du locuteur : contenu (phrase) ou mot_cle (ADR-0047).';
