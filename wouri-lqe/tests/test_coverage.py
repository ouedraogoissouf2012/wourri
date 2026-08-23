"""Tests du service Couverture (ADR-0034 P1)."""
from app.data import language_registry as reg
from app.db import get_conn
from app.services import coverage
from app.services.catalog import Concept


class FakeCatalog:
    """Impl du contrat ConceptCatalog pour isoler la couverture du pont reel."""

    def __init__(self, concepts):
        self._c = list(concepts)

    def list_concepts(self):
        return self._c

    def get_concept(self, cid):
        return next((c for c in self._c if c.id == cid), None)


def _promote(concept_id, language):
    with get_conn(autocommit=True) as conn:
        conn.execute(
            "INSERT INTO productions (concept_id, language, status)"
            " VALUES (%s, %s, 'production')",
            (concept_id, language),
        )


def test_matrix_only_active_languages(db):
    reg.upsert_language("bci", "Baoule", status="active")
    reg.upsert_language("btg", "Bete", status="backlog")  # exclu (pas active)
    cat = FakeCatalog([Concept(id="a", text_fr="A"), Concept(id="b", text_fr="B")])
    m = coverage.coverage_matrix(cat)
    assert [x.code for x in m] == ["bci"]
    assert m[0].total == 2 and m[0].covered == 0 and m[0].up_to_date is False


def test_matrix_counts_and_up_to_date(db):
    reg.upsert_language("bci", "Baoule", status="active")
    cat = FakeCatalog([Concept(id="a", text_fr="A"), Concept(id="b", text_fr="B")])
    _promote("a", "bci")
    m = coverage.coverage_matrix(cat)
    assert m[0].covered == 1 and m[0].missing == 1
    assert coverage.missing_concept_ids(cat, "bci") == ["b"]
    _promote("b", "bci")
    assert coverage.coverage_matrix(cat)[0].up_to_date is True


def test_only_production_status_counts(db):
    reg.upsert_language("bci", "Baoule", status="active")
    cat = FakeCatalog([Concept(id="a", text_fr="A")])
    with get_conn(autocommit=True) as conn:
        conn.execute(
            "INSERT INTO productions (concept_id, language, status)"
            " VALUES ('a', 'bci', 'bronze')"
        )
    assert coverage.coverage_matrix(cat)[0].covered == 0  # bronze != production
