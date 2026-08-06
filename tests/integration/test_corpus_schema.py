"""Tests d'intégration — schéma corpus PostgreSQL + pgvector (Sprint F Phase B).

Ces tests valident :
- la migration Alembic `0001_create_corpus_schema` (tables, colonnes, index, FK),
- l'idempotence du script `scripts/import_corpus_ivr.py` (corpus courant),
- la recherche vectorielle (`<=>` cosine) via l'index ivfflat,
- l'intégrité référentielle (FK + ON DELETE CASCADE).

**Pré-requis** : container `wourri_postgres_dev` up (cf. `docker-compose.dev.yml`).
Si POSTGRES_URL est absente ou si la connexion échoue, **tout le module est skip**
— cela évite de casser la régression CI/dev qui ne dispose pas du container.

Référence : ADR-0008 §Phase B (5 critères de sortie).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CORPUS = json.loads(
    (_PROJECT_ROOT / "dictionnaires" / "corpus_ivr.json").read_text(encoding="utf-8")
)
_EXPECTED_COUNT = len(_CORPUS["entries"])
_EXPECTED_VERSION = _CORPUS["version"]

# Source unique partagée avec alembic/env.py, scripts/import_corpus_ivr.py,
# app/services/corpus_service.py. `raise_on_missing=False` est la divergence
# test/prod encodée dans la signature : le skipif ci-dessous a besoin d'une
# valeur falsy pour décider de skip le module entier proprement.
from app.db.url_resolver import resolve_postgres_url  # noqa: E402
from tests.integration._helpers import postgres_reachable  # noqa: E402

_URL = resolve_postgres_url(raise_on_missing=False)
_REACHABLE = postgres_reachable(_URL)

pytestmark = pytest.mark.skipif(
    not _REACHABLE,
    reason=(
        "PostgreSQL+pgvector non disponible. Démarrer le container dev avec :\n"
        "  docker compose -f docker-compose.dev.yml up -d\n"
        "et exporter POSTGRES_URL ou la définir dans .env."
    ),
)


def _import_subprocess_env() -> dict:
    """Construit l'env du subprocess `import_corpus_ivr.py`.

    #189 : `KMP_DUPLICATE_LIB_OK=TRUE` + `OMP_NUM_THREADS=1` préviennent
    l'ACCESS_VIOLATION Windows (returncode 0xC0000005) causé par le double-load
    des DLL OpenMP de torch, quand un test parent a déjà chargé
    SentenceTransformer avant que ce subprocess ne le recharge. C'est le
    contournement standard documenté pour cette classe de crash.

    Durcissement PRÉVENTIF : le crash a été observé au smoke Phase D mais n'est
    pas reproductible sur toutes les configs (non reproduit sur dev Windows le
    2026-08-06). Ces variables ne changent PAS le résultat de l'import — elles
    éliminent seulement le conflit de chargement OpenMP.
    """
    env = os.environ.copy()
    env["POSTGRES_URL"] = _URL
    env["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    env["OMP_NUM_THREADS"] = "1"
    return env


@pytest.fixture(scope="module")
def engine():
    """Engine SQLAlchemy partagé pour le module."""
    from sqlalchemy import create_engine

    eng = create_engine(_URL, future=True)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def imported_corpus(engine):
    """Garantit que le corpus est importé (idempotence).

    Fix #179 §3 : timeout abaisse de 600s a 240s. Le script importe le corpus
    courant et calcule un embedding 384-dim par entrée. Sur CI Linux : ~30-60s.
    Sur dev Windows : ~120-180s observe (subprocess Python complet + warmup
    torch CPU). 240s laisse une marge tout en evitant l'attente 10 min de
    l'ancien 600s si le modele est absent du cache.
    """
    script = _PROJECT_ROOT / "scripts" / "import_corpus_ivr.py"
    env = _import_subprocess_env()
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(_PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=240,
        )
    except subprocess.TimeoutExpired as e:
        pytest.fail(
            f"import_corpus_ivr.py a dépassé 240s (#179 §3). "
            f"Cause probable : modèle SentenceTransformer absent du cache "
            f"local (modeles_manuels/) → tentative de download HF qui peut "
            f"durer plusieurs minutes. Verifier que "
            f"`modeles_manuels/paraphrase-multilingual-MiniLM-L12-v2/` existe.\n"
            f"Exception: {e}"
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

    def test_score_validation_check_rejects_out_of_range(self, engine):
        """Fix #178 : la CHECK constraint chk_score_validation_range refuse
        toute valeur hors [0.0, 1.0].

        Migration 0003 ADD CONSTRAINT alignement ADR-0008 §Phase B.
        """
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError

        vec = "[" + ",".join(["0"] * 384) + "]"

        with engine.connect() as conn:
            trans = conn.begin()
            try:
                with pytest.raises(IntegrityError) as exc_info:
                    conn.execute(
                        text(
                            "INSERT INTO corpus_entries "
                            "(id, intent, reponse_bambara, document_text, "
                            " embedding, score_validation) "
                            "VALUES ('test_chk_score_001', 'TEST', 'x', 'x', "
                            "        CAST(:vec AS vector), 1.5)"
                        ),
                        {"vec": vec},
                    )
                assert "chk_score_validation_range" in str(exc_info.value), (
                    f"L'erreur ne mentionne pas la contrainte: {exc_info.value}"
                )
            finally:
                trans.rollback()

    def test_score_validation_check_rejects_negative(self, engine):
        """Fix #178 : la borne basse 0.0 est aussi rejetee (-0.1 → IntegrityError)."""
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError

        vec = "[" + ",".join(["0"] * 384) + "]"

        with engine.connect() as conn:
            trans = conn.begin()
            try:
                with pytest.raises(IntegrityError):
                    conn.execute(
                        text(
                            "INSERT INTO corpus_entries "
                            "(id, intent, reponse_bambara, document_text, "
                            " embedding, score_validation) "
                            "VALUES ('test_chk_score_002', 'TEST', 'x', 'x', "
                            "        CAST(:vec AS vector), -0.1)"
                        ),
                        {"vec": vec},
                    )
            finally:
                trans.rollback()

    def test_reponse_fr_accepts_null(self, engine):
        """Fix #178 : reponse_fr est desormais nullable (alignement ADR §Phase B).

        Migration 0003 DROP NOT NULL. Avant : NOT NULL DEFAULT ''. Apres :
        nullable, ce qui permet de distinguer NULL (information manquante)
        d'une chaine vide (information presente mais vide).
        """
        from sqlalchemy import text

        vec = "[" + ",".join(["0"] * 384) + "]"

        with engine.connect() as conn:
            trans = conn.begin()
            try:
                conn.execute(
                    text(
                        "INSERT INTO corpus_entries "
                        "(id, intent, reponse_bambara, reponse_fr, "
                        " document_text, embedding) "
                        "VALUES ('test_null_fr_001', 'TEST', 'x', NULL, "
                        "        'x', CAST(:vec AS vector))"
                    ),
                    {"vec": vec},
                )
                row = conn.execute(
                    text(
                        "SELECT reponse_fr FROM corpus_entries "
                        "WHERE id = 'test_null_fr_001'"
                    )
                ).first()
                assert row is not None
                assert row[0] is None, f"reponse_fr aurait du etre NULL, got {row[0]!r}"
            finally:
                trans.rollback()

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
    """Critère ADR-0008 §Phase B #4 (corpus complet + import reproductible)."""

    def test_import_inserts_every_current_entry(self, imported_corpus, engine):
        from sqlalchemy import text

        with engine.connect() as conn:
            count = conn.execute(text("SELECT count(*) FROM corpus_entries")).scalar()
        assert count == _EXPECTED_COUNT

    def test_metadata_version_matches_corpus(self, imported_corpus, engine):
        from sqlalchemy import text

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT value FROM corpus_metadata WHERE key = 'version'")
            ).first()
        assert row is not None
        assert row[0] == _EXPECTED_VERSION

    def test_import_idempotent(self, imported_corpus, engine):
        """Une seconde exécution doit produire le même count (pas de doublons).

        Vérifie à la fois `corpus_entries` (taille du JSON courant) ET
        `corpus_phrases_attestees` (≥ 100, référence historique ≈ 157) —
        le TRUNCATE CASCADE
        doit avoir vidé proprement les phrases avant la 2e insertion.
        """
        script = _PROJECT_ROOT / "scripts" / "import_corpus_ivr.py"
        env = _import_subprocess_env()
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
        assert count_entries == _EXPECTED_COUNT, (
            "import non idempotent : count corpus_entries != taille du corpus "
            "JSON après ré-exécution"
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

    def test_array_search_by_culture_uses_gin_index(self, imported_corpus, engine):
        """Fix #179 §1 : prouve que l'index GIN est *reellement* utilise.

        Avec un petit corpus, le planner peut preferer un seqscan (moins cher
        en cold cache). On force `enable_seqscan=off` et inspecte le plan via
        `EXPLAIN (FORMAT JSON)` : un noeud `Bitmap Index Scan` doit apparaitre.
        """
        import json

        from sqlalchemy import text

        with engine.connect() as conn:
            conn.execute(text("SET LOCAL enable_seqscan = off"))
            plan = conn.execute(
                text(
                    "EXPLAIN (FORMAT JSON) "
                    "SELECT id FROM corpus_entries "
                    "WHERE cultures && ARRAY['*']::text[]"
                )
            ).scalar()

        # plan est une string JSON ou deja une list (selon driver)
        if isinstance(plan, str):
            plan = json.loads(plan)
        plan_str = json.dumps(plan)
        # Bitmap Index Scan = signature GIN/B-tree utilise
        assert "Bitmap Index Scan" in plan_str or "Index Scan" in plan_str, (
            f"GIN index non utilise. Plan complet:\n{plan_str}"
        )
        # Verification supplementaire : index name doit etre dans le plan
        assert "ix_corpus_entries_cultures" in plan_str, (
            f"L'index ix_corpus_entries_cultures n'apparait pas dans le plan:\n{plan_str}"
        )

    def test_ivfflat_search_uses_index(self, imported_corpus, engine):
        """Fix #179 §1 (variante ivfflat) : prouve que ivfflat est utilise.

        Avec le corpus courant et `lists=10`, le seuil pgvector
        (rows >= lists*3 = 30) est largement franchi → ivfflat devrait etre
        choisi pour ORDER BY <=>.
        """
        import json

        from sqlalchemy import text

        # Vecteur arbitraire pour la recherche (384 zeros)
        vec = "[" + ",".join(["0"] * 384) + "]"

        with engine.connect() as conn:
            conn.execute(text("SET LOCAL enable_seqscan = off"))
            plan = conn.execute(
                text(
                    "EXPLAIN (FORMAT JSON) "
                    "SELECT id FROM corpus_entries "
                    "ORDER BY embedding <=> CAST(:vec AS vector) LIMIT 5"
                ),
                {"vec": vec},
            ).scalar()

        if isinstance(plan, str):
            plan = json.loads(plan)
        plan_str = json.dumps(plan)
        assert "ix_corpus_entries_embedding_ivfflat" in plan_str, (
            f"L'index ivfflat n'apparait pas dans le plan:\n{plan_str}"
        )

    def test_array_columns_are_text_array_type(self, engine):
        """Fix #179 §2 : verrouille que cultures/conditions/tags sont bien TEXT[].

        Si une migration future modifie ces colonnes en JSONB, le code corpus
        casse silencieusement (operateur `&&` n'existe pas sur JSONB). Ce test
        garantit que la regression sera detectee.
        """
        from sqlalchemy import text

        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT attname, format_type(atttypid, atttypmod) "
                    "FROM pg_attribute "
                    "WHERE attrelid = 'public.corpus_entries'::regclass "
                    "  AND attname IN ('cultures','conditions','tags') "
                    "ORDER BY attname"
                )
            ).all()

        types_by_name = {r[0]: r[1] for r in rows}
        assert types_by_name == {
            "conditions": "text[]",
            "cultures": "text[]",
            "tags": "text[]",
        }, f"Types divergents: {types_by_name}"


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
