"""schema linguistique normalise, phase 1 : le corpus baoule en base (ADR-0050, #623)

Cree le schema cible de l'ADR-0050 (option E) et y verse les 193 entrees du corpus
baoule. Une langue n'y ajoute que des lignes, jamais de colonne :
  - `langue`   : les langues, en lignes (bci, fr ; dyu en phase 2) ;
  - `reponse`  : une entree du corpus = un concept (intention x cultures). Ce qui est
                 propre a une langue (filiere, appariement pour le baoule) va dans
                 `metadonnees`, pas dans une colonne que la langue suivante porterait vide ;
  - `enonce`   : un texte, sa langue, son role (question / reponse) et son media ;
  - `lot_linguistique` : quel lot de contenu la base porte, avec son empreinte ;
  - `historique_linguistique` : toute ecriture, quel qu'en soit l'auteur (script, SQL
                 a la main), avec l'avant et l'apres — la trace consultable et
                 reversible exigee par l'ADR-0050 §6.

Le dioula (`corpus_entries`) n'est pas touche : sa migration est la phase 2 (#624).
Rien ne lit encore ces tables : le moteur continue de servir le fichier. La bascule
des lectures est une PR separee, ouverte seulement apres cette migration en production.

Le contenu vient d'un lot FIGE (`alembic/data/`), verifie par son empreinte : la
migration se rejoue a l'identique meme apres le retrait du fichier de `dictionnaires/`,
et refuse de peupler avec un lot altere. Aucune chaine n'est reecrite (ADR-0014).

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-24
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LOT = Path(__file__).resolve().parents[1] / "data" / "corpus_ivr_bci_2026-11-13.json"
# Empreinte du CONTENU (JSON canonique), pas des octets : indépendante des fins de ligne.
EMPREINTE_LOT = "222d13597992adc2cae77a4602de6a923c489e35e312f1ab392959f306afadc4"
AUTEUR = "migration 0006"


def empreinte(data: dict) -> str:
    canon = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def charger_lot(chemin: Path, attendue: str) -> list[dict]:
    """Les entrées du lot, ou ValueError si son contenu n'est pas celui qui a été relu."""
    data = json.loads(Path(chemin).read_text(encoding="utf-8"))
    obtenue = empreinte(data)
    if obtenue != attendue:
        raise ValueError(
            f"Lot {Path(chemin).name} : empreinte {obtenue} au lieu de {attendue} — refus de peupler"
        )
    return data["entries"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE langue (
            code  TEXT PRIMARY KEY,
            nom   TEXT NOT NULL
        );
        CREATE TABLE reponse (
            id           TEXT    PRIMARY KEY,
            langue       TEXT    NOT NULL REFERENCES langue(code),
            intent       TEXT    NOT NULL,
            cultures     TEXT[]  NOT NULL DEFAULT '{}',
            rang         INTEGER NOT NULL,
            metadonnees  JSONB   NOT NULL DEFAULT '{}'
        );
        CREATE TABLE enonce (
            id          BIGSERIAL PRIMARY KEY,
            reponse_id  TEXT NOT NULL REFERENCES reponse(id) ON DELETE CASCADE,
            role        TEXT NOT NULL CONSTRAINT enonce_role_check CHECK (role IN ('question', 'reponse')),
            langue      TEXT NOT NULL REFERENCES langue(code),
            texte       TEXT NOT NULL,
            media       TEXT,
            UNIQUE (reponse_id, role, langue)
        );
        CREATE TABLE lot_linguistique (
            langue      TEXT        NOT NULL REFERENCES langue(code),
            empreinte   TEXT        NOT NULL,
            auteur      TEXT        NOT NULL,
            applique_le TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (langue, empreinte)
        );
        CREATE TABLE historique_linguistique (
            id         BIGSERIAL   PRIMARY KEY,
            table_nom  TEXT        NOT NULL,
            operation  TEXT        NOT NULL,
            avant      JSONB,
            apres      JSONB,
            auteur     TEXT        NOT NULL,
            le         TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        -- L'auteur est posé par l'écrivain (`SET LOCAL wourri.auteur`) ; à défaut,
        -- l'utilisateur Postgres : une écriture n'est jamais anonyme.
        CREATE FUNCTION historiser_linguistique() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            INSERT INTO historique_linguistique (table_nom, operation, avant, apres, auteur)
            VALUES (
                TG_TABLE_NAME, TG_OP,
                CASE WHEN TG_OP <> 'INSERT' THEN to_jsonb(OLD) END,
                CASE WHEN TG_OP <> 'DELETE' THEN to_jsonb(NEW) END,
                COALESCE(NULLIF(current_setting('wourri.auteur', true), ''), current_user)
            );
            RETURN NULL;
        END $$;
        CREATE TRIGGER langue_historique AFTER INSERT OR UPDATE OR DELETE ON langue
            FOR EACH ROW EXECUTE FUNCTION historiser_linguistique();
        CREATE TRIGGER reponse_historique AFTER INSERT OR UPDATE OR DELETE ON reponse
            FOR EACH ROW EXECUTE FUNCTION historiser_linguistique();
        CREATE TRIGGER enonce_historique AFTER INSERT OR UPDATE OR DELETE ON enonce
            FOR EACH ROW EXECUTE FUNCTION historiser_linguistique();

        -- Pas d'index GIN sur reponse.cultures : VOULU, pas oublié. Avec 193 lignes, un
        -- parcours séquentiel coûte moins que l'index. À créer si le volume l'exige.

        COMMENT ON TABLE reponse IS
            'Entrée de corpus, toutes langues (ADR-0050). Le propre d''une langue va dans metadonnees.';
        COMMENT ON COLUMN reponse.rang IS 'Ordre du lot d''origine : départage déterministe des candidats.';
        COMMENT ON COLUMN enonce.media IS
            'Référence d''atelier de l''enregistrement (audio/<uuid>.<ext>) ; NULL = à réenregistrer.';
        COMMENT ON TABLE historique_linguistique IS
            'Toute écriture sur langue/reponse/enonce, avec avant et après (ADR-0050 §6).';
        """
    )

    entrees = charger_lot(LOT, EMPREINTE_LOT)
    bind = op.get_bind()
    bind.execute(sa.text("SELECT set_config('wourri.auteur', :auteur, true)"), {"auteur": AUTEUR})
    bind.execute(sa.text("INSERT INTO langue (code, nom) VALUES ('bci', 'Baoulé'), ('fr', 'Français')"))
    bind.execute(
        sa.text(
            "INSERT INTO reponse (id, langue, intent, cultures, rang, metadonnees) "
            "VALUES (:id, 'bci', :intent, :cultures, :rang, CAST(:metadonnees AS JSONB))"
        ),
        [
            {
                "id": e["id"], "intent": e["intent"], "cultures": list(e["cultures"]), "rang": rang,
                "metadonnees": json.dumps(
                    {"filiere": e["filiere"], "appariement": e["appariement"]}, ensure_ascii=False
                ),
            }
            for rang, e in enumerate(entrees)
        ],
    )
    bind.execute(
        sa.text(
            "INSERT INTO enonce (reponse_id, role, langue, texte, media) "
            "VALUES (:reponse_id, :role, :langue, :texte, :media)"
        ),
        [
            {"reponse_id": e["id"], "role": role, "langue": langue, "texte": e[champ],
             "media": e["audio_reponse"] if champ == "reponse_bci" else None}
            for e in entrees
            for role, langue, champ in (
                ("question", "bci", "question_bci"), ("question", "fr", "question_fr"),
                ("reponse", "bci", "reponse_bci"), ("reponse", "fr", "reponse_fr"),
            )
        ],
    )
    bind.execute(
        sa.text("INSERT INTO lot_linguistique (langue, empreinte, auteur) VALUES ('bci', :e, :auteur)"),
        {"e": EMPREINTE_LOT, "auteur": AUTEUR},
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS historique_linguistique;
        DROP TABLE IF EXISTS lot_linguistique;
        DROP TABLE IF EXISTS enonce;
        DROP TABLE IF EXISTS reponse;
        DROP TABLE IF EXISTS langue;
        DROP FUNCTION IF EXISTS historiser_linguistique();
        """
    )
