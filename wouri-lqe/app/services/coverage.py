"""Service Couverture — matrice concepts x langues (ADR-0034 P1/P4).

Un concept est COUVERT dans une langue s'il a, soit :
  - une production PROMUE (`status='production'`) dans cette langue (table `productions`), soit
  - une reponse NATIVE dans le corpus du moteur pour cette langue. Le corpus moteur
    (`corpus_entries`) porte la reponse dioula (`reponse_bambara`) : le dioula (langue
    SOURCE) est donc deja couvert par le corpus lui-meme, sans passer par l'atelier. Les
    autres langues (baoule...) n'ont pas de reponse native et se produisent via l'atelier.

La 'parite' d'une langue = 100 % des concepts couverts. Depend du contrat `ConceptCatalog`
(DIP) et du repository `productions` (source unique, meme table qu'ingest/decide/promote).
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.data import language_registry
from app.services import productions_repo as repo
from app.services.catalog import Concept, ConceptCatalog

# Langue SOURCE du corpus moteur : `corpus_entries.reponse_bambara` est natif en dioula.
# Le dioula est la reference de parite, couverte par le corpus lui-meme (pas par l'atelier).
SOURCE_LANGUAGE = "dyu"


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


def native_covered_ids(concepts: Iterable[Concept], language: str) -> set[str]:
    """Concepts couverts NATIVEMENT par le corpus moteur pour `language`. Seul le dioula
    (SOURCE_LANGUAGE) a une reponse native (`ref_dyu`) : un concept est natif-couvert si sa
    reponse dioula est non-vide. Les autres langues -> aucun natif (a produire via l'atelier)."""
    if language != SOURCE_LANGUAGE:
        return set()
    return {c.id for c in concepts if (c.ref_dyu or "").strip()}


def coverage_matrix(catalog: ConceptCatalog) -> list[LanguageCoverage]:
    concepts = catalog.list_concepts()
    concept_ids = {c.id for c in concepts}
    total = len(concept_ids)
    out: list[LanguageCoverage] = []
    for lang in language_registry.list_languages(status="active"):
        covered = (concept_ids & _covered_ids(lang.code)) | native_covered_ids(concepts, lang.code)
        n = len(covered)
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
    """Concepts du catalogue pas encore couverts (produits OU natifs) dans `language`."""
    concepts = catalog.list_concepts()
    covered = _covered_ids(language) | native_covered_ids(concepts, language)
    return sorted(c.id for c in concepts if c.id not in covered)
