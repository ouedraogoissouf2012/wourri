"""Pont LECTURE SEULE vers le catalogue des concepts NLU (`public.nlu_concepts`).

Deuxieme implementation du contrat `ConceptCatalog` (ADR-0034), a cote de
`PgCorpusCatalog` :

    ConceptCatalog
    ├── PgCorpusCatalog   -> phrases du corpus a traduire
    └── NluConceptCatalog -> concepts NLU dont le locuteur donne les mots

Les deux alimentent le MEME mecanisme d'assignation et le meme ecran
« Mes demandes » : aucun ecran specifique, aucun `if`-langue, rien a ajouter
quand une langue s'ouvre (ADR-0047).

Ne fait QUE des SELECT. La table est ecrite par le moteur
(`scripts/import_nlu_concepts.py`), jamais ici.

`ref_dyu` porte les mots dioula du concept : AFFICHES au locuteur comme
reference, JAMAIS copies — une traduction dioula n'est pas une traduction
baoule (ADR-0046).
"""
from __future__ import annotations

from app.db import get_conn
from app.services.catalog import Concept

_SELECT = "SELECT id, label_fr, intent, ref_dyu FROM nlu_concepts"


def _to_concept(row: tuple) -> Concept:
    cid, label_fr, intent, ref_dyu = row
    return Concept(
        id=cid,
        # Le pivot envoye au locuteur est le SENS en francais : « comment dit-on
        # "meteo" ? ». C'est la meme consigne que pour une phrase du corpus.
        text_fr=label_fr or cid,
        intent=intent or "",
        cultures=(),
        ref_dyu=ref_dyu or "",
    )


class NluConceptCatalog:
    """`ConceptCatalog` en lecture seule sur `nlu_concepts`."""

    def list_concepts(self) -> list[Concept]:
        with get_conn() as conn:
            rows = conn.execute(_SELECT + " ORDER BY id").fetchall()
        return [_to_concept(r) for r in rows]

    def get_concept(self, concept_id: str) -> Concept | None:
        with get_conn() as conn:
            row = conn.execute(_SELECT + " WHERE id = %s", (concept_id,)).fetchone()
        return _to_concept(row) if row else None
