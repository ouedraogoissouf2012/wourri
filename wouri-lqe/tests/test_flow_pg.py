"""Flux atelier bout-en-bout sur Postgres + cohérence couverture (ADR-0034 P4).

Verrouille le point de fond de la bascule : la couverture (coverage) lit LA MÊME table
que le flux (ingest/decide/promote) écrit — plus de backend divergent JSONL/PG.
"""
from app.services import coverage, workflow
from app.services.catalog import Concept
from app.services.ingest import ingest


class _Cat:
    def __init__(self, concepts):
        self._c = list(concepts)

    def list_concepts(self):
        return self._c

    def get_concept(self, cid):
        return next((c for c in self._c if c.id == cid), None)


def test_ingest_decide_promote_end_to_end(seeded):
    r = ingest(
        [{"text_local": "Aw ni ce", "text_fr": "Merci", "id": "u_001"}],
        language="dyu",
        actor="prov",
    )
    assert r["accepted"] == 1
    tid = workflow.list_tasks(language="dyu", status="bronze")[0]["id"]
    assert workflow.decide(tid, "admin_accepted", language="dyu")["ok"]
    p = workflow.promote(tid, language="dyu", actor="admin")
    assert p["ok"] and p["entry"]["status"] == "production"
    corpus = workflow.list_corpus(language="dyu")
    assert len(corpus) == 1 and corpus[0]["id"] == tid


def test_coverage_reflects_promoted_concept(seeded):
    # une production RATTACHÉE à un concept, une fois promue, fait bouger la couverture
    cat = _Cat([Concept(id="c_mais", text_fr="Comment planter le mais")])
    ingest(
        [{"text_local": "sɛnɛ", "text_fr": "Comment planter le mais",
          "concept_id": "c_mais", "id": "u1"}],
        language="dyu",
        actor="prov",
    )
    tid = workflow.list_tasks(language="dyu", status="bronze")[0]["id"]
    workflow.decide(tid, "admin_accepted", language="dyu")

    before = {x.code: x for x in coverage.coverage_matrix(cat)}
    assert before["dyu"].covered == 0  # bronze/accepted ne compte pas

    workflow.promote(tid, language="dyu", actor="admin")

    after = {x.code: x for x in coverage.coverage_matrix(cat)}
    assert after["dyu"].covered == 1
    assert after["dyu"].up_to_date is True


def test_coverage_ignores_free_upload_without_concept(seeded):
    # une production SANS concept_id (upload libre) ne fabrique aucune couverture
    cat = _Cat([Concept(id="c_x", text_fr="X")])
    ingest([{"text_local": "a", "text_fr": "b", "id": "free1"}], language="dyu", actor="p")
    tid = workflow.list_tasks(language="dyu", status="bronze")[0]["id"]
    workflow.decide(tid, "admin_accepted", language="dyu")
    workflow.promote(tid, language="dyu", actor="admin")
    after = {x.code: x for x in coverage.coverage_matrix(cat)}
    assert after["dyu"].covered == 0
