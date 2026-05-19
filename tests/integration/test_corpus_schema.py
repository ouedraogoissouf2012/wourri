"""Tests d'intégration — schéma corpus PostgreSQL + pgvector (Sprint F Phase B).

Ces tests valident :
- la migration Alembic `0001_create_corpus_schema` (tables, colonnes, index, FK),
- l'idempotence du script `scripts/import_corpus_ivr.py` (162 entrées),
- la recherche vectorielle (`<=>` cosine) via l'index ivfflat,
- l'intégrité référentielle (FK + ON DELETE CASCADE).

**Pré-requis** : container `wourri_postgres_dev` up (cf. `docker-compose.dev.yml`).
Si POSTGRES_URL est absente ou si la connexion échoue, **tout le module est skip**
— cela évite de casser la régression CI/dev qui ne dispose pas du container.

Référence : ADR-0008 §Phase B (5 critères de sortie).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _resolve_url() -> str:
    """Cf. cross-référence dans `alembic/env.py::_resolve_url`.

    DIVERGENCE INTENTIONNELLE : retourne `""` au lieu de lever `RuntimeError`,
    car le `pytestmark = pytest.mark.skipif(...)` ci-dessous a besoin d'une
    valeur falsy pour décider de skip le module entier proprement.
    Toute « unification » naïve avec les versions de `alembic/env.py` ou
    `scripts/import_corpus_ivr.py` casserait le skip et ferait planter
    pytest dans les environnements sans container Postgres.
    """
    url = os.getenv("POSTGRES_URL", "").strip()
    if url:
        return url
    try:
        from app.config import get_settings

        s = (get_settings().postgres_url or "").strip()
        if s:
            return s
    except Exception:
        pass
    return ""


def _postgres_reachable(url: str) -> bool:
    if not url:
        return False
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(url, future=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


_URL = _resolve_url()
_REACHABLE = _postgres_reachable(_URL)

pytestmark = pytest.mark.skipif(
    not _REACHABLE,
    reason=(
        "PostgreSQL+pgvector non disponible. Démarrer le container dev avec :\n"
        "  docker compose -f docker-compose.dev.yml up -d\n"
        "et exporter POSTGRES_URL ou la définir dans .env."
    ),
)


@pytest.fixture(scope="module")
def engine():
    """Engine SQLAlchemy partagé pour le module."""
    from sqlalchemy import create_engine

    eng = create_engine(_URL, future=True)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def imported_corpus(engine):
    """Garantit que le corpus est importé (idempotence)."""
    script = _PROJECT_ROOT / "scripts" / "import_corpus_ivr.py"
    env = os.environ.copy()
    env["POSTGRES_URL"] = _URL
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(_PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
    )
    assert result.returncode == 0, (
        f"import_corpus_ivr.py a échoué :\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    return result


# ─────────────────────────────────────────────────────────────────────────
# Schema integrity
# ─────────────────────────────────────────────────────────────────────────


class TestSchemaIntegrity:
    """Critères ADR-0008 §Phase B #1 + #2 + #3."""

    def test_three_tables_exist(self, engine):
        from sqlalchemy import text

        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' "
                    "AND tablename IN ("
                    "  'corpus_entries','corpus_phrases_attestees','corpus_metadata'"
                    ") ORDER BY tablename"
                )
            ).all()
        tables = [r[0] for r in rows]
        assert tables == [
            "corpus_entries",
            "corpus_metadata",
            "corpus_phrases_attestees",
        ]

    def test_embedding_column_is_vector_384(self, engine):
        from sqlalchemy import text

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT format_type(a.atttypid, a.atttypmod) "
                    "FROM pg_attribute a "
                    "WHERE a.attrelid = 'public.corpus_entries'::regclass "
                    "AND a.attname = 'embedding'"
                )
            ).first()
        assert row is not None
        assert row[0] == "vector(384)"

    def test_required_indexes_present(self, engine):
        """ivfflat + GIN cultures + GIN conditions + GIN FTS + B-tree intent."""
        from sqlalchemy import text

        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = 'public' "
                    "AND tablename = 'corpus_entries'"
                )
            ).all()
        names = {r[0] for r in rows}
        expected = {
            "corpus_entries_pkey",
            "ix_corpus_entries_intent",
            "ix_corpus_entries_cultures",
            "ix_corpus_entries_conditions",
            "ix_corpus_entries_reponse_fr_fts",
            "ix_corpus_entries_embedding_ivfflat",
        }
        missing = expected - names
        assert not missing, f"Index manquants : {missing}"

    def test_fk_phrases_to_entries_cascade(self, engine):
        from sqlalchemy import text

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT confdeltype FROM pg_constraint "
                    "WHERE conname = 'corpus_phrases_attestees_entry_id_fkey'"
                )
            ).first()
        # 'c' = CASCADE (cf. https://www.postgresql.org/docs/current/catalog-pg-constraint.html)
        assert row is not None, "FK corpus_phrases_attestees.entry_id absente"
        assert row[0] == "c", f"FK n'est pas en CASCADE : confdeltype={row[0]!r}"


# ─────────────────────────────────────────────────────────────────────────
# Import idempotence + counts
# ─────────────────────────────────────────────────────────────────────────


class TestImportIdempotence:
    """Critère ADR-0008 §Phase B #4 (162 entrées importées + reproductible)."""

    def test_import_inserts_162_entries(self, imported_corpus, engine):
        from sqlalchemy import text

        with engine.connect() as conn:
            count = conn.execute(text("SELECT count(*) FROM corpus_entries")).scalar()
        assert count == 162

    def test_metadata_version_matches_corpus(self, imported_corpus, engine):
        from sqlalchemy import text

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT value FROM corpus_metadata WHERE key = 'version'")
            ).first()
        assert row is not None
        # corpus_ivr.json v2.3 (cf. MEMORY.md "Fichiers clés")
        assert row[0] == "2.3"

    def test_import_idempotent(self, imported_corpus, engine):
        """Une seconde exécution doit produire le même count (pas de doublons).

        Vérifie à la fois `corpus_entries` (162) ET `corpus_phrases_attestees`
        (≥ 100, valeur de référence corpus v2.3 ≈ 157) — le TRUNCATE CASCADE
        doit avoir vidé proprement les phrases avant la 2e insertion.
        """
        script = _PROJECT_ROOT / "scripts" / "import_corpus_ivr.py"
        env = os.environ.copy()
        env["POSTGRES_URL"] = _URL
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(_PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=600,
        )
        assert result.returncode == 0, result.stderr

        from sqlalchemy import text

        with engine.connect() as conn:
            count_entries = conn.execute(
                text("SELECT count(*) FROM corpus_entries")
            ).scalar()
            count_phrases = conn.execute(
                text("SELECT count(*) FROM corpus_phrases_attestees")
            ).scalar()
        assert count_entries == 162, (
            "import non idempotent : count corpus_entries != 162 "
            "après ré-exécution"
        )
        # Lower-bound défensif : la valeur exacte (~157) peut évoluer avec
        # le corpus, mais une double-insertion (> 200) ou une suppression
        # silencieuse (< 100) doivent toutes deux échouer.
        assert 100 <= count_phrases <= 200, (
            f"corpus_phrases_attestees count = {count_phrases} hors [100,200] "
            "après ré-exécution : TRUNCATE CASCADE n'est probablement pas "
            "idempotent."
        )


# ─────────────────────────────────────────────────────────────────────────
# Recherche vectorielle + index ivfflat
# ─────────────────────────────────────────────────────────────────────────


class TestVectorSearch:
    """Critère implicite ADR-0008 : la recherche cosine doit fonctionner."""

    def test_cosine_self_distance_is_zero(self, imported_corpus, engine):
        """Un embedding comparé à lui-même doit avoir distance cosine ≈ 0."""
        from sqlalchemy import text

        with engine.connect() as conn:
            # Anchor : première entrée par id
            anchor_id = conn.execute(
                text("SELECT id FROM corpus_entries ORDER BY id LIMIT 1")
            ).scalar()
            dist = conn.execute(
                text(
                    "SELECT (e.embedding <=> a.embedding) "
                    "FROM corpus_entries e, "
                    "     (SELECT embedding FROM corpus_entries WHERE id = :aid) a "
                    "WHERE e.id = :aid"
                ),
                {"aid": anchor_id},
            ).scalar()
        assert dist is not None
        assert float(dist) < 1e-5, f"self-distance cosine attendue ≈ 0, obtenue {dist}"

    def test_array_search_by_culture(self, imported_corpus, engine):
        """Le GIN sur cultures permet `WHERE cultures && ARRAY[...]`."""
        from sqlalchemy import text

        with engine.connect() as conn:
            # Le corpus contient au moins une entrée avec cultures = ['*'] ou
            # contenant 'malo' (riz) — on prend la cardinalité comme preuve
            # que le requêteur GIN renvoie bien quelque chose.
            count = conn.execute(
                text(
                    "SELECT count(*) FROM corpus_entries "
                    "WHERE cultures && ARRAY['*']::text[]"
                )
            ).scalar()
        assert count is not None and count >= 1


# ─────────────────────────────────────────────────────────────────────────
# Intégrité référentielle
# ─────────────────────────────────────────────────────────────────────────


class TestReferentialIntegrity:
    """FK + ON DELETE CASCADE entre corpus_entries et corpus_phrases_attestees."""

    def test_cascade_delete_removes_child_rows(self, imported_corpus, engine):
        """Insère une entrée + 2 phrases, supprime l'entrée, vérifie cascade.

        Toute la séquence se déroule dans une transaction explicite qui est
        systématiquement rollback en fin de test : aucune pollution du
        dataset importé, même en cas d'assertion failure.
        """
        from sqlalchemy import text

        vec = "[" + ",".join(["0"] * 384) + "]"
        with engine.connect() as conn:
            trans = conn.begin()
            try:
                conn.execute(
                    text(
                        "INSERT INTO corpus_entries (id, intent, reponse_bambara, "
                        "  document_text, embedding) "
                        "VALUES ('test_fk_cascade_001', 'TEST_INTENT', 'test', "
                        "        'test doc', CAST(:vec AS vector))"
                    ),
                    {"vec": vec},
                )
                conn.execute(
                    text(
                        "INSERT INTO corpus_phrases_attestees (entry_id, text) "
                        "VALUES ('test_fk_cascade_001', 'phrase test 1'), "
                        "       ('test_fk_cascade_001', 'phrase test 2')"
                    )
                )
                count_before = conn.execute(
                    text(
                        "SELECT count(*) FROM corpus_phrases_attestees "
                        "WHERE entry_id = 'test_fk_cascade_001'"
                    )
                ).scalar()
                assert count_before == 2

                conn.execute(
                    text(
                        "DELETE FROM corpus_entries WHERE id = 'test_fk_cascade_001'"
                    )
                )
                count_after = conn.execute(
                    text(
                        "SELECT count(*) FROM corpus_phrases_attestees "
                        "WHERE entry_id = 'test_fk_cascade_001'"
                    )
                ).scalar()
                assert count_after == 0, "ON DELETE CASCADE ne s'est pas déclenché"
            finally:
                trans.rollback()
