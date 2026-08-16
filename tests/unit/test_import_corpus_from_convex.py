"""Tests — import du corpus depuis Convex (L3 #410) : logique pure + autonomie.

Couvre les décisions à risque sans toucher la BD ni le modèle ML :
- `should_import` (comparaison de révision, jeton opaque, égalité) ;
- `plan_fusion` (partition update-existant vs insert-nouveau) ;
- `fetch_corpus_export` (autonomie : Convex injoignable / non-200 -> None).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.import_corpus_from_convex import (  # noqa: E402
    should_import,
    plan_fusion,
    fetch_corpus_export,
    is_publishable,
    filter_publishable,
)


class _FakeResp:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self):
        return self._json


class _FakeClient:
    def __init__(self, resp=None, raise_exc=None):
        self._resp = resp
        self._raise = raise_exc
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": headers})
        if self._raise:
            raise self._raise
        return self._resp


# --- should_import : jeton opaque, comparaison d'égalité --------------------

def test_should_import_true_when_revision_differs():
    assert should_import("398-1786668123122", "397-1786000000000") is True


def test_should_import_false_when_revision_same():
    assert should_import("398-1786668123122", "398-1786668123122") is False


def test_should_import_true_when_no_stored_revision():
    assert should_import("398-1786668123122", None) is True


def test_should_import_false_when_fetched_revision_empty():
    # Ne jamais importer sur une révision vide/absente (donnée douteuse).
    assert should_import("", "397") is False
    assert should_import(None, "397") is False


# --- plan_fusion : update-existant vs insert-nouveau -----------------------

def test_plan_fusion_splits_update_vs_insert():
    convex = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    local_ids = {"a", "c"}
    to_update, to_insert = plan_fusion(convex, local_ids)
    assert [e["id"] for e in to_update] == ["a", "c"]
    assert [e["id"] for e in to_insert] == ["b"]


def test_plan_fusion_all_new():
    to_update, to_insert = plan_fusion([{"id": "x"}, {"id": "y"}], set())
    assert to_update == []
    assert [e["id"] for e in to_insert] == ["x", "y"]


# --- fetch_corpus_export : autonomie ---------------------------------------

def test_fetch_export_returns_dict_on_200_with_key_header():
    payload = {"revision": "398-1", "entries": [{"id": "x"}]}
    client = _FakeClient(resp=_FakeResp(200, payload))
    out = fetch_corpus_export("https://convex.site", "ck_secret", client=client)
    assert out == payload
    assert client.calls[0]["headers"]["X-Corpus-Key"] == "ck_secret"
    assert client.calls[0]["url"].endswith("/corpus/export")


def test_fetch_export_none_on_non_200_autonomy():
    client = _FakeClient(resp=_FakeResp(503))
    assert fetch_corpus_export("https://convex.site", "ck", client=client) is None


def test_fetch_export_none_on_exception_autonomy():
    client = _FakeClient(raise_exc=RuntimeError("network down"))
    assert fetch_corpus_export("https://convex.site", "ck", client=client) is None


# --- ADR-0031 / #430 : Or+ seulement, bam non revalidé exclu ---------------

def test_publishable_missing_status_keeps_current_export():
    """Export actuel (197 fiches) n'a pas de status → Production implicite."""
    assert is_publishable({"id": "a", "reponse_bambara": "x"}) is True


def test_publishable_rejects_bronze_and_silver():
    assert is_publishable({"id": "a", "status": "bronze"}) is False
    assert is_publishable({"id": "a", "status": "Bronze"}) is False
    assert is_publishable({"id": "a", "status": "argent"}) is False
    assert is_publishable({"id": "a", "status": "silver"}) is False


def test_publishable_accepts_gold_and_production():
    assert is_publishable({"id": "a", "status": "or"}) is True
    assert is_publishable({"id": "a", "status": "gold"}) is True
    assert is_publishable({"id": "a", "status": "production"}) is True


def test_publishable_rejects_bam_without_dyu_revalidation():
    assert is_publishable({"id": "a", "status": "production", "source_lang": "bam"}) is False
    assert is_publishable({"id": "a", "source_lang": "bambara"}) is False


def test_publishable_accepts_bam_revalidated_as_dyu():
    assert is_publishable({
        "id": "a",
        "status": "or",
        "source_lang": "bam",
        "validated_as": "dyu",
    }) is True


def test_filter_publishable_drops_bronze_keeps_gold():
    entries = [
        {"id": "bronze", "status": "bronze"},
        {"id": "or", "status": "or"},
        {"id": "legacy"},
    ]
    kept, skipped = filter_publishable(entries)
    assert [e["id"] for e in kept] == ["or", "legacy"]
    assert [e["id"] for e in skipped] == ["bronze"]
