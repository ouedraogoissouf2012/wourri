from app.services import productions_repo as repo
from app.services import workflow
from app.services.ingest import ingest, parse_upload


def test_ingest_dedup(seeded):
    rows = [{"text_local": "A", "text_fr": "B", "id": "x1"}]
    first = ingest(rows, language="bci", actor="t")
    second = ingest(rows, language="bci", actor="t")
    assert first["accepted"] == 1
    assert second["duplicates_skipped"] == 1


def test_dedup_enforced_by_db_constraint(seeded):
    """La dédup est garantie par l'index unique (language, fingerprint) EN BASE
    (ON CONFLICT DO NOTHING), pas par un cache mémoire : un 2e insert du même
    fingerprint renvoie inserted=False directement au niveau repository."""
    kw = dict(language="dyu", text_local="l", text_fr="f", fingerprint="h:same")
    assert repo.insert_bronze(**kw)["inserted"] is True
    assert repo.insert_bronze(**kw)["inserted"] is False  # contrainte DB, pas un cache


def test_ingest_rejects_unknown_language(seeded):
    r = ingest([{"text_local": "A", "text_fr": "B"}], language="xyz", actor="t")
    assert r["ok"] is False
    assert r["accepted"] == 0


def test_ingest_persists_meta_and_concept(seeded):
    ingest(
        [{"text_local": "loc", "text_fr": "fr", "id": "e1", "concept_id": "c9",
          "region": "ML", "notes": "n"}],
        language="dyu",
        actor="prov",
    )
    row = workflow.list_tasks(language="dyu")[0]
    assert row["concept_id"] == "c9"
    assert row["meta"]["region"] == "ML"       # valeur != défaut 'CI' -> prouve la lecture
    assert row["meta"]["external_id"] == "e1"


def test_ingest_tolerates_bad_row(seeded):
    """Une ligne fautive (octet NUL, rejeté par Postgres) n'annule pas le lot :
    la ligne valide est acceptée, la fautive comptée en erreur (tolérance par ligne)."""
    rows = [
        {"text_local": "bon", "text_fr": "ok", "id": "ok1"},
        {"text_local": "mauvais\x00nul", "text_fr": "x", "id": "bad1"},
    ]
    r = ingest(rows, language="dyu", actor="t")
    assert r["accepted"] == 1
    assert len(r["errors"]) == 1
    assert len(workflow.list_tasks(language="dyu")) == 1


def test_parse_csv():
    raw = "text_local,text_fr\nloc,fr\n".encode("utf-8")
    rows = parse_upload("a.csv", raw)
    assert rows[0]["text_local"] == "loc"
