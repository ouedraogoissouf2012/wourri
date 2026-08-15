"""Tests d'intégration — chemin BD de l'import corpus depuis Convex (L3 #410).

Exerce le VRAI comportement SQL (fusion document_text, préservation des
métadonnées locales, insertion, garde-fous) contre PostgreSQL+pgvector, SANS
dépendance ML : le modèle d'embedding est un stub qui renvoie un vecteur nul
384-dim (on teste le SQL et la fusion, pas la qualité des embeddings).

Pré-requis : Postgres+pgvector joignable (service CI, ou container dev). Sinon
le module entier est skip (cf. test_corpus_schema.py). Chaque test se déroule
dans une transaction explicite systématiquement rollback → aucune pollution.
"""
from __future__ import annotations

import pytest

from app.db.url_resolver import resolve_postgres_url
from tests.integration._helpers import postgres_reachable

from scripts.import_corpus_from_convex import (
    _apply_inserts,
    _apply_updates,
    _get_stored_revision,
    _load_local_context,
    _set_revision,
)

_URL = resolve_postgres_url(raise_on_missing=False)
_REACHABLE = postgres_reachable(_URL)

pytestmark = pytest.mark.skipif(
    not _REACHABLE,
    reason="PostgreSQL+pgvector non disponible (cf. test_corpus_schema.py).",
)

_VEC_ZERO = "[" + ",".join(["0"] * 384) + "]"


class _FakeModel:
    """Modèle d'embedding factice : évite la dépendance ML dans ce test SQL."""

    def encode(self, docs, **kwargs):
        import numpy as np

        return np.zeros((len(docs), 384), dtype="float32")


@pytest.fixture(scope="module")
def engine():
    from sqlalchemy import create_engine

    eng = create_engine(_URL, future=True)
    yield eng
    eng.dispose()


def _seed_entry(conn, entry_id, *, intent, reponse_fr, reponse_bambara, tags):
    from sqlalchemy import text

    conn.execute(
        text(
            "INSERT INTO corpus_entries (id, intent, tags, reponse_fr, "
            "  reponse_bambara, document_text, embedding) "
            "VALUES (:id, :intent, :tags, :fr, :bam, :doc, CAST(:vec AS vector))"
        ),
        {
            "id": entry_id,
            "intent": intent,
            "tags": tags,
            "fr": reponse_fr,
            "bam": reponse_bambara,
            "doc": "doc initial",
            "vec": _VEC_ZERO,
        },
    )


def _seed_phrases(conn, entry_id, phrases):
    from sqlalchemy import text

    for txt in phrases:
        conn.execute(
            text(
                "INSERT INTO corpus_phrases_attestees (entry_id, text) "
                "VALUES (:eid, :txt)"
            ),
            {"eid": entry_id, "txt": txt},
        )


def test_update_fuses_convex_text_with_local_tags_and_phrases(engine):
    """UPDATE : reponse_fr/bambara écrasés ; document_text = nouveau reponse_fr
    + tags/phrases LOCAUX ; intent et tags préservés."""
    from sqlalchemy import text

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            _seed_entry(
                conn,
                "test_l3_upd_001",
                intent="TEST_INTENT",
                reponse_fr="ancien_fr",
                reponse_bambara="ancien_bam",
                tags=["riz", "engrais"],
            )
            _seed_phrases(conn, "test_l3_upd_001", ["pa", "pb"])

            ctx = _load_local_context(conn, {"test_l3_upd_001"})
            n = _apply_updates(
                conn,
                _FakeModel(),
                [
                    {
                        "id": "test_l3_upd_001",
                        "reponse_fr": "nouveau_fr",
                        "reponse_bambara": "nouveau_bam",
                    }
                ],
                ctx,
            )
            assert n == 1

            row = conn.execute(
                text(
                    "SELECT reponse_fr, reponse_bambara, document_text, intent, tags "
                    "FROM corpus_entries WHERE id = 'test_l3_upd_001'"
                )
            ).first()
            assert row.reponse_fr == "nouveau_fr"
            assert row.reponse_bambara == "nouveau_bam"
            # Fusion : nouveau reponse_fr + tags locaux + phrases locales (ordre id).
            assert row.document_text == "nouveau_fr riz engrais pa pb"
            # Métadonnées locales préservées.
            assert row.intent == "TEST_INTENT"
            assert row.tags == ["riz", "engrais"]
        finally:
            trans.rollback()


def test_update_skips_empty_bambara_and_preserves_local(engine):
    """Un reponse_bambara vide côté Convex ne doit PAS blanchir le local."""
    from sqlalchemy import text

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            _seed_entry(
                conn,
                "test_l3_upd_empty",
                intent="I",
                reponse_fr="fr",
                reponse_bambara="original_bam",
                tags=[],
            )
            n = _apply_updates(
                conn,
                _FakeModel(),
                [{"id": "test_l3_upd_empty", "reponse_fr": "x", "reponse_bambara": ""}],
                {},
            )
            assert n == 0
            row = conn.execute(
                text(
                    "SELECT reponse_bambara FROM corpus_entries "
                    "WHERE id = 'test_l3_upd_empty'"
                )
            ).first()
            assert row.reponse_bambara == "original_bam"
        finally:
            trans.rollback()


def test_insert_creates_new_entry_from_convex(engine):
    """INSERT : nouvelle entrée servable, source='convex', document_text=reponse_fr."""
    from sqlalchemy import text

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            n = _apply_inserts(
                conn,
                _FakeModel(),
                [
                    {
                        "id": "test_l3_ins_001",
                        "intent": "INS_INTENT",
                        "cultures": ["malo"],
                        "reponse_fr": "insere_fr",
                        "reponse_bambara": "insere_bam",
                    }
                ],
            )
            assert n == 1
            row = conn.execute(
                text(
                    "SELECT intent, cultures, reponse_fr, reponse_bambara, "
                    "  document_text, source, tags "
                    "FROM corpus_entries WHERE id = 'test_l3_ins_001'"
                )
            ).first()
            assert row.intent == "INS_INTENT"
            assert row.cultures == ["malo"]
            assert row.reponse_fr == "insere_fr"
            assert row.reponse_bambara == "insere_bam"
            # Pas de tags/phrases -> reponse_fr seul. La fonction canonique
            # `_build_document_text` pad d'espaces les segments vides (comportement
            # identique à import_corpus_ivr, donc cohérent) -> on strip.
            assert row.document_text.strip() == "insere_fr"
            assert row.source == "convex"
            assert row.tags == []
        finally:
            trans.rollback()


def test_insert_skips_entries_missing_required_fields(engine):
    """intent/reponse_bambara NOT NULL : une entrée qui les manque est ignorée."""
    from sqlalchemy import text

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            n = _apply_inserts(
                conn,
                _FakeModel(),
                [
                    {"id": "test_l3_ins_noint", "reponse_bambara": "b"},  # pas d'intent
                    {"id": "test_l3_ins_nobam", "intent": "I"},  # pas de reponse_bambara
                ],
            )
            assert n == 0
            count = conn.execute(
                text(
                    "SELECT count(*) FROM corpus_entries "
                    "WHERE id IN ('test_l3_ins_noint', 'test_l3_ins_nobam')"
                )
            ).scalar()
            assert count == 0
        finally:
            trans.rollback()


def test_revision_roundtrip_upsert(engine):
    """_set_revision écrit puis met à jour convex_revision ; _get_stored_revision lit."""
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            _set_revision(conn, "398-abc")
            assert _get_stored_revision(conn) == "398-abc"
            _set_revision(conn, "399-def")  # upsert (ON CONFLICT)
            assert _get_stored_revision(conn) == "399-def"
        finally:
            trans.rollback()
