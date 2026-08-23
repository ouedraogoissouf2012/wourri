"""Contrat du catalogue de concepts de reference (ADR-0034).

Interface (DIP/OCP) : la couverture et les assignations dependront de CE contrat,
jamais d'une implementation concrete. L'impl reelle = pont **lecture seule** vers
le corpus IVR du moteur, livree en P1 (#463). P0 ne fournit que le contrat + une
impl vide de secours.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Concept:
    id: str                            # = id du corpus IVR (cle de concept partagee)
    text_fr: str                       # pivot = le sens (consigne envoyee au locuteur)
    intent: str = ""
    cultures: tuple[str, ...] = ()
    ref_dyu: str = ""                  # reference dioula (affichee, jamais copiee)


class ConceptCatalog(Protocol):
    """Source de reference des concepts (lecture seule stricte)."""

    def list_concepts(self) -> list[Concept]: ...

    def get_concept(self, concept_id: str) -> Concept | None: ...


class EmptyCatalog:
    """Impl de secours P0 : aucun concept. Remplacee par le pont moteur en P1."""

    def list_concepts(self) -> list[Concept]:
        return []

    def get_concept(self, concept_id: str) -> Concept | None:
        return None
