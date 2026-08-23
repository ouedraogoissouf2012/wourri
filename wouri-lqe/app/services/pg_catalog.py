"""Pont LECTURE SEULE vers le corpus IVR du moteur (`public.corpus_entries`).

Implemente le contrat `ConceptCatalog` (ADR-0034 P1). Ne fait QUE des SELECT —
jamais d'ecriture vers le corpus du moteur. La table vit dans le schema `public`,
atteinte via le search_path `(lqe, public)` de `get_conn()`.
"""
from __future__ import annotations

from app.db import get_conn
from app.services.catalog import Concept

_SELECT = "SELECT id, reponse_fr, intent, cultures, reponse_bambara FROM corpus_entries"


def _to_concept(row: tuple) -> Concept:
    cid, fr, intent, cultures, ref_dyu = row
    return Concept(
        id=cid,
        text_fr=fr or "",
        intent=intent or "",
        cultures=tuple(cultures or ()),
        ref_dyu=ref_dyu or "",
    )


class PgCorpusCatalog:
    """`ConceptCatalog` en lecture seule sur `corpus_entries` (corpus du moteur)."""

    def list_concepts(self) -> list[Concept]:
        with get_conn() as conn:
            rows = conn.execute(_SELECT + " ORDER BY id").fetchall()
        return [_to_concept(r) for r in rows]

    def get_concept(self, concept_id: str) -> Concept | None:
        with get_conn() as conn:
            row = conn.execute(_SELECT + " WHERE id = %s", (concept_id,)).fetchone()
        return _to_concept(row) if row else None
