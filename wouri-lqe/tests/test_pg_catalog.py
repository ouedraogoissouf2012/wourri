"""Tests du pont lecture seule vers corpus_entries (ADR-0034 P1)."""
from app.services.pg_catalog import PgCorpusCatalog


def test_list_concepts(corpus):
    concepts = PgCorpusCatalog().list_concepts()
    assert [c.id for c in concepts] == ["mais_conseil_001", "riz_conseil_001"]
    mais = concepts[0]
    assert mais.text_fr == "Plante ton mais"          # pivot francais (consigne)
    assert mais.intent == "CONSEIL_PRODUCTION"
    assert mais.cultures == ("CULTURE_MAIS",)
    assert mais.ref_dyu == "Aw ye kaba sene"          # reference dioula


def test_get_concept(corpus):
    cat = PgCorpusCatalog()
    assert cat.get_concept("riz_conseil_001").text_fr == "Plante ton riz"
    assert cat.get_concept("inexistant") is None
