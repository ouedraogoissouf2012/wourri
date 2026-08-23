"""Service Couverture — matrice concepts x langues (ADR-0034 P1/P4).

Pour chaque langue `active`, quels concepts du catalogue sont deja couverts par une
production PROMUE (`status='production'`) dans cette langue, et lesquels manquent. La
'parite' d'une langue = 100 % des concepts couverts.

Depend du contrat `ConceptCatalog` (DIP) et du repository `productions` (source unique,
la meme table que le flux ingest/decide/promote ecrit — plus de divergence JSONL/PG).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.data import language_registry
from app.services import productions_repo as repo
from app.services.catalog import ConceptCatalog


@dataclass(frozen=True)
class LanguageCoverage:
    code: str
    name: str
    total: int
    covered: int
    missing: int
    up_to_date: bool


def _covered_ids(language: str) -> set[str]:
    return repo.covered_concept_ids(language=language)


def coverage_matrix(catalog: ConceptCatalog) -> list[LanguageCoverage]:
    concept_ids = {c.id for c in catalog.list_concepts()}
    total = len(concept_ids)
    out: list[LanguageCoverage] = []
    for lang in language_registry.list_languages(status="active"):
        n = len(concept_ids & _covered_ids(lang.code))
        out.append(
            LanguageCoverage(
                code=lang.code,
                name=lang.name,
                total=total,
                covered=n,
                missing=total - n,
                up_to_date=(total > 0 and n == total),
            )
        )
    return out


def missing_concept_ids(catalog: ConceptCatalog, language: str) -> list[str]:
    """Concepts du catalogue pas encore couverts (promus) dans `language`."""
    covered = _covered_ids(language)
    return sorted(c.id for c in catalog.list_concepts() if c.id not in covered)
