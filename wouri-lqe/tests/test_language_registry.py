"""Tests du référentiel de langues (ADR-0034 P0) — activer une langue = 1 INSERT."""
from app.data import language_registry as reg


def test_upsert_and_get(db):
    lang = reg.upsert_language("bci", "Baoule", family="Kwa", status="active", asr_available=True)
    assert lang.code == "bci"
    assert lang.status == "active"
    assert lang.asr_available is True
    got = reg.get_language("BCI")  # insensible à la casse
    assert got is not None and got.name == "Baoule"


def test_is_known(db):
    assert reg.is_known("dyu") is False
    reg.upsert_language("dyu", "Jula", status="active")
    assert reg.is_known("dyu") is True


def test_list_and_status_filter(db):
    reg.upsert_language("dyu", "Jula", status="active")
    reg.upsert_language("btg", "Bete Gagnoa", status="backlog")
    active = reg.list_languages(status="active")
    assert [lg.code for lg in active] == ["dyu"]
    assert len(reg.list_languages()) == 2


def test_upsert_updates_on_conflict(db):
    reg.upsert_language("bci", "Baoule", status="backlog")
    reg.upsert_language("bci", "Baoule", status="active")
    assert reg.get_language("bci").status == "active"
    assert len(reg.list_languages()) == 1  # pas de doublon


def test_set_status(db):
    reg.upsert_language("bci", "Baoule", status="backlog")
    assert reg.set_status("bci", "active") is True
    assert reg.get_language("bci").status == "active"
    assert reg.set_status("zzz", "active") is False  # langue inconnue
