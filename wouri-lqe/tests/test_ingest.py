from app.services import workflow
from app.services.ingest import ingest, parse_upload


def test_ingest_dedup(seeded):
    rows = [{"text_local": "A", "text_fr": "B", "id": "x1"}]
    first = ingest(rows, language="bci", actor="t")
    second = ingest(rows, language="bci", actor="t")
    assert first["accepted"] == 1
    assert second["duplicates_skipped"] == 1


def test_ingest_dedup_persists_in_db(seeded):
    """La dédup passe par l'index unique (language, fingerprint) en base — pas un cache
    mémoire : deux appels distincts ⇒ une seule ligne (protège des ingests concurrents)."""
    rows = [{"text_local": "Z", "text_fr": "Y", "id": "zz"}]
    ingest(rows, language="dyu", actor="t")
    ingest(rows, language="dyu", actor="t")
    assert len(workflow.list_tasks(language="dyu")) == 1


def test_ingest_rejects_unknown_language(seeded):
    r = ingest([{"text_local": "A", "text_fr": "B"}], language="xyz", actor="t")
    assert r["ok"] is False
    assert r["accepted"] == 0


def test_ingest_persists_meta_and_concept(seeded):
    ingest(
        [{"text_local": "loc", "text_fr": "fr", "id": "e1", "concept_id": "c9",
          "region": "CI", "notes": "n"}],
        language="dyu",
        actor="prov",
    )
    row = workflow.list_tasks(language="dyu")[0]
    assert row["concept_id"] == "c9"
    assert row["meta"]["region"] == "CI"
    assert row["meta"]["external_id"] == "e1"


def test_parse_csv():
    raw = "text_local,text_fr\nloc,fr\n".encode("utf-8")
    rows = parse_upload("a.csv", raw)
    assert rows[0]["text_local"] == "loc"
