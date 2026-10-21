-- ADR-0045 — type d'element de l'atelier. 'contenu' (defaut) : le flux de parite existant.
-- 'mot_cle' (tel mot local veut dire tel concept du NLU) et 'paire_qr' (telle reponse
-- repond a telle question) se VALIDENT par le locuteur (review) mais ne sont jamais du
-- contenu servi : hors corpus, hors couverture, jamais promouvables.
-- Contrainte runner (migrate._statements) : aucun ';' dans un litteral.

ALTER TABLE productions ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'contenu';

ALTER TABLE productions DROP CONSTRAINT IF EXISTS productions_kind_check;

ALTER TABLE productions ADD CONSTRAINT productions_kind_check CHECK (kind IN ('contenu', 'mot_cle', 'paire_qr'));

CREATE INDEX IF NOT EXISTS idx_productions_lang_kind_status ON productions (language, kind, status);
