"""Service assignations admin par lot (ADR-0034 P2)."""
from app.db import get_conn
from app.services import assignments
from app.services.catalog import Concept
from app.services.pg_catalog import PgCorpusCatalog


class _Cat:
    def __init__(self, concepts):
        self._c = list(concepts)

    def list_concepts(self):
        return self._c

    def get_concept(self, cid):
        return next((c for c in self._c if c.id == cid), None)


def _promote_concept(concept_id, language):
    with get_conn(autocommit=True) as conn:
        conn.execute(
            "INSERT INTO productions (concept_id, language, status)"
            " VALUES (%s, %s, 'production')",
            (concept_id, language),
        )


def test_assign_batch_idempotent(seeded, corpus):
    cat = PgCorpusCatalog()
    r1 = assignments.assign_batch(
        ["mais_conseil_001", "riz_conseil_001"],
        target_language="bci", assigned_by="admin", catalog=cat,
    )
    assert r1["assigned"] == 2 and r1["already"] == 0
    r2 = assignments.assign_batch(
        ["mais_conseil_001"], target_language="bci", assigned_by="admin", catalog=cat,
    )
    assert r2["assigned"] == 0 and r2["already"] == 1


def test_assign_batch_resolves_source_fr_from_catalog(seeded, corpus):
    assignments.assign_batch(
        ["mais_conseil_001"], target_language="bci", assigned_by="admin",
        catalog=PgCorpusCatalog(),
    )
    rows = assignments.list_open(language="bci")
    assert len(rows) == 1
    assert rows[0]["concept_id"] == "mais_conseil_001"
    assert rows[0]["source_fr"] == "Plante ton mais"  # pivot pris du catalogue, jamais du client


def test_assign_batch_skips_unknown_concept(seeded, corpus):
    r = assignments.assign_batch(
        ["inconnu_999"], target_language="bci", assigned_by="admin",
        catalog=PgCorpusCatalog(),
    )
    assert r["assigned"] == 0
    assert r["skipped"] == ["inconnu_999"]
    assert assignments.list_open(language="bci") == []


def test_missing_to_assign_excludes_already_assigned(seeded, corpus):
    cat = PgCorpusCatalog()
    before = assignments.missing_to_assign(cat, language="bci")
    assert {c["concept_id"] for c in before} == {"mais_conseil_001", "riz_conseil_001"}
    assert all(c["source_fr"] for c in before)  # consigne fr enrichie
    assignments.assign_batch(
        ["mais_conseil_001"], target_language="bci", assigned_by="admin", catalog=cat,
    )
    after = assignments.missing_to_assign(cat, language="bci")
    assert {c["concept_id"] for c in after} == {"riz_conseil_001"}  # l'assigne disparait


def test_mark_done_open_to_done(seeded, corpus):
    assignments.assign_batch(
        ["mais_conseil_001"], target_language="bci", assigned_by="admin",
        catalog=PgCorpusCatalog(),
    )
    assert assignments.mark_done(concept_id="mais_conseil_001", language="bci") is True
    assert assignments.list_open(language="bci") == []  # plus 'open'
    assert assignments.mark_done(concept_id="mais_conseil_001", language="bci") is False  # idempotent


def test_parity_ok_false_when_missing(seeded, corpus):
    assert assignments.parity_ok(PgCorpusCatalog(), language="bci") is False


def test_parity_ok_true_when_fully_covered(seeded):
    cat = _Cat([Concept(id="c1", text_fr="X")])
    _promote_concept("c1", "bci")
    assert assignments.parity_ok(cat, language="bci") is True


def test_missing_to_assign_source_excludes_native(db):
    """Dioula (source) : un concept avec reponse dioula native n'est PAS 'a produire'."""
    cat = _Cat([Concept(id="a", text_fr="A", ref_dyu="Aw ye a ke"),
                Concept(id="b", text_fr="B")])
    missing = assignments.missing_to_assign(cat, language="dyu")
    assert {c["concept_id"] for c in missing} == {"b"}  # 'a' natif -> exclu


def test_parity_ok_true_for_source_via_native(db):
    """Le dioula est a jour des que le corpus porte sa reponse native (sans atelier)."""
    cat = _Cat([Concept(id="a", text_fr="A", ref_dyu="Aw ye a ke")])
    assert assignments.parity_ok(cat, language="dyu") is True
