-- ADR-0034 P4 — seed des langues pilotes. Activer une langue = un INSERT (jamais un CSV).
-- dyu = Dioula ivoirien (famille Mande) ; bci = Baoule (famille Kwa). Les deux actives
-- pour le pilote. Les ~60 langues de Cote d'Ivoire s'ajouteront par le meme INSERT.
-- Contrainte runner (migrate._statements) : aucun ';' dans un litteral.

INSERT INTO languages (code, name, family, script, status)
VALUES ('dyu', 'Dioula', 'Mande', 'Latn', 'active'), ('bci', 'Baoule', 'Kwa', 'Latn', 'active')
ON CONFLICT (code) DO NOTHING;
