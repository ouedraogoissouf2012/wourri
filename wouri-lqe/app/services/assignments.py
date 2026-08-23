"""Assignations admin par lot (ADR-0034 P2) — couche metier mince.

Calque `workflow.py`. Depend du contrat `ConceptCatalog` (DIP), jamais de l'impl
concrete : le pivot francais (`source_fr`) est TOUJOURS resolu depuis le catalogue
cote serveur, jamais envoye par le client.
"""
from __future__ import annotations

from app.services import assignments_repo as repo
from app.services import coverage
from app.services import productions_repo
from app.services.catalog import ConceptCatalog


def assign_batch(concept_ids, *, target_language: str, assigned_by: str, catalog: ConceptCatalog) -> dict:
    """Assigne un lot de concepts a une langue. Idempotent (UNIQUE concept+langue).
    Retourne {assigned, already, skipped} — skipped = concept absent du corpus/sans pivot."""
    assigned = 0
    already = 0
    skipped: list[str] = []
    for raw in concept_ids:
        cid = str(raw).strip()
        if not cid:
            continue
        concept = catalog.get_concept(cid)
        if concept is None or not (concept.text_fr or "").strip():
            skipped.append(cid)
            continue
        if repo.assign_one(
            concept_id=cid, target_language=target_language,
            source_fr=concept.text_fr, assigned_by=assigned_by,
        ):
            assigned += 1
        else:
            already += 1
    return {"assigned": assigned, "already": already, "skipped": skipped,
            "target_language": target_language}


def list_open(*, language: str) -> list[dict]:
    return repo.list_by(target_language=language, status="open")


def missing_to_assign(catalog: ConceptCatalog, *, language: str) -> list[dict]:
    """Concepts manquants NON encore assignes (open), enrichis (consigne fr + ref dioula)."""
    open_assigned = repo.assigned_concept_ids(target_language=language, status="open")
    out: list[dict] = []
    for cid in coverage.missing_concept_ids(catalog, language):
        if cid in open_assigned:
            continue
        c = catalog.get_concept(cid)
        if c is None:
            continue
        out.append({"concept_id": c.id, "source_fr": c.text_fr,
                    "intent": c.intent, "ref_dyu": c.ref_dyu})
    return out


def mark_done(*, concept_id: str, language: str) -> bool:
    return repo.set_done(concept_id=concept_id, target_language=language)


def parity_ok(catalog: ConceptCatalog, *, language: str) -> bool:
    """True si `language` couvre 100 % des concepts du catalogue — base de la garde
    parite-avant-extension. Catalogue vide => non a jour (bloque). Mono-langue : une seule
    requete de couverture (pas de recalcul de toute la matrice)."""
    concept_ids = {c.id for c in catalog.list_concepts()}
    if not concept_ids:
        return False
    covered = productions_repo.covered_concept_ids(language=language)
    return concept_ids <= covered
