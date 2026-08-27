"""Tests — empreinte du corpus IVR et détection d'écart JSON ↔ pgvector (#487).

Mode d'échec couvert : `dictionnaires/corpus_ivr.json` est corrigé (validation
dioula par un natif) mais `scripts/import_corpus_ivr.py` n'est pas relancé. Le
moteur répond alors avec l'ancienne formulation, sans aucun signal — jusqu'à
cette issue.

Contrat vérifié ici :
    - l'import écrit `corpus_metadata.source_sha256` (empreinte du JSON) ;
    - `initialiser_vdb()` la relit et loggue un WARNING actionnable en cas
      d'écart ;
    - la fonction d'empreinte est **une seule et même** des deux côtés (sinon
      écriture et vérification divergeraient silencieusement).

Aucune connexion Postgres réelle : la connexion SQLAlchemy est mockée.
"""
from __future__ import annotations

import hashlib
import importlib.util
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services import corpus_service


_LOGGER_NAME = "app.services.corpus_service"

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "import_corpus_ivr.py"


@pytest.fixture
def import_module():
    """Charge `scripts/import_corpus_ivr.py` sans déclencher `main()`."""
    spec = importlib.util.spec_from_file_location("import_corpus_ivr", _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def corpus_json(tmp_path):
    """Un faux `corpus_ivr.json` isolé, que les tests peuvent modifier."""
    path = tmp_path / "corpus_ivr.json"
    path.write_bytes(b'{"version": "2.4.1", "entries": [{"id": "riz_001"}]}')
    return path


def _mock_conn(empreinte_stockee):
    """Connexion mockée dont le SELECT `corpus_metadata` retourne l'empreinte."""
    row = None
    if empreinte_stockee is not None:
        row = MagicMock(__getitem__=lambda _s, _i: empreinte_stockee)
    result = MagicMock()
    result.first.return_value = row
    conn = MagicMock()
    conn.execute.return_value = result
    return conn


def _mock_engine_initialiser(count, empreinte_stockee):
    """Engine mocké pour `initialiser_vdb` : 1er execute = count, 2e = empreinte."""
    result_count = MagicMock()
    result_count.scalar.return_value = count

    row = None
    if empreinte_stockee is not None:
        row = MagicMock(__getitem__=lambda _s, _i: empreinte_stockee)
    result_empreinte = MagicMock()
    result_empreinte.first.return_value = row

    conn = MagicMock()
    conn.execute.side_effect = [result_count, result_empreinte]
    conn.__enter__.return_value = conn
    conn.__exit__.return_value = False

    engine = MagicMock()
    engine.connect.return_value = conn
    return engine


# ─────────────────────────────────────────────────────────────────────────
# compute_corpus_fingerprint
# ─────────────────────────────────────────────────────────────────────────


class TestComputeCorpusFingerprint:
    def test_retourne_le_sha256_des_octets_du_fichier(self, corpus_json):
        attendu = hashlib.sha256(corpus_json.read_bytes()).hexdigest()
        assert corpus_service.compute_corpus_fingerprint(corpus_json) == attendu

    def test_delegue_a_la_definition_canonique_sur_octets(self, corpus_json):
        """`compute_corpus_fingerprint` n'est qu'un lecteur de fichier :
        l'algorithme vit dans `corpus_fingerprint_from_bytes`, seule
        definition partagee avec le script d'import."""
        assert corpus_service.compute_corpus_fingerprint(
            corpus_json
        ) == corpus_service.corpus_fingerprint_from_bytes(corpus_json.read_bytes())

    def test_change_quand_le_contenu_change(self, corpus_json):
        avant = corpus_service.compute_corpus_fingerprint(corpus_json)
        corpus_json.write_bytes(b'{"version": "2.4.2", "entries": [{"id": "riz_001"}]}')
        assert corpus_service.compute_corpus_fingerprint(corpus_json) != avant

    def test_fichier_absent_retourne_none_et_loggue(self, tmp_path, caplog):
        absent = tmp_path / "jamais_cree.json"
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            assert corpus_service.compute_corpus_fingerprint(absent) is None
        assert "Empreinte corpus non calculable" in caplog.text

    def test_sans_argument_cible_le_corpus_du_depot(self):
        """Le défaut doit pointer sur le vrai `dictionnaires/corpus_ivr.json`."""
        assert corpus_service._CORPUS_JSON_PATH.name == "corpus_ivr.json"
        assert corpus_service._CORPUS_JSON_PATH.exists()
        assert corpus_service.compute_corpus_fingerprint() == hashlib.sha256(
            corpus_service._CORPUS_JSON_PATH.read_bytes()
        ).hexdigest()


# ─────────────────────────────────────────────────────────────────────────
# _verifier_fraicheur_corpus — le cœur de #487
# ─────────────────────────────────────────────────────────────────────────


class TestVerifierFraicheurCorpus:
    def test_json_modifie_base_non_reimportee_produit_un_warning(
        self, corpus_json, caplog
    ):
        """Cas nominal de l'issue : le JSON change, l'import n'est pas relancé.

        Le signal doit être un WARNING qui nomme l'action corrective — sans
        quoi l'écart reste invisible en production.
        """
        empreinte_importee = corpus_service.compute_corpus_fingerprint(corpus_json)
        # Une correction dioula validée est appliquée au JSON…
        corpus_json.write_bytes(b'{"version": "2.4.2", "entries": [{"id": "riz_002"}]}')
        # …mais scripts/import_corpus_ivr.py n'est pas relancé : la base garde
        # l'ancienne empreinte.
        conn = _mock_conn(empreinte_importee)

        with patch.object(corpus_service, "_CORPUS_JSON_PATH", corpus_json), \
             caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            frais = corpus_service._verifier_fraicheur_corpus(conn)

        assert frais is False
        assert [r for r in caplog.records if r.levelno == logging.WARNING], (
            "aucun WARNING émis — l'écart resterait silencieux"
        )
        assert "corpus_ivr.json modifié mais pgvector non réimporté" in caplog.text
        assert "scripts/import_corpus_ivr.py" in caplog.text

    def test_json_inchange_ne_produit_aucun_warning(self, corpus_json, caplog):
        empreinte = corpus_service.compute_corpus_fingerprint(corpus_json)
        conn = _mock_conn(empreinte)

        with patch.object(corpus_service, "_CORPUS_JSON_PATH", corpus_json), \
             caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
            frais = corpus_service._verifier_fraicheur_corpus(conn)

        assert frais is True
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert "inchangé depuis le dernier import" in caplog.text

    def test_empreinte_absente_en_base_produit_un_warning_distinct(
        self, corpus_json, caplog
    ):
        """Base importée avant #487 : la clé n'existe pas encore.

        On ne peut alors rien garantir → WARNING, mais avec un message
        différent de celui de l'écart (le diagnostic ops n'est pas le même).
        """
        conn = _mock_conn(None)

        with patch.object(corpus_service, "_CORPUS_JSON_PATH", corpus_json), \
             caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            frais = corpus_service._verifier_fraicheur_corpus(conn)

        assert frais is False
        assert "Aucune empreinte corpus en base" in caplog.text
        assert corpus_service.CORPUS_FINGERPRINT_KEY in caplog.text
        # `import_corpus_ivr.py` TRUNCATE les 3 tables : conseiller sa
        # relance sans reserve detruirait un corpus synchronise depuis
        # Convex (#410), qui n'ecrit que `convex_revision`.
        assert "TRUNCATE" in caplog.text
        assert "Convex" in caplog.text

    def test_json_illisible_ninterroge_pas_la_base_et_ne_leve_pas(
        self, tmp_path, caplog
    ):
        conn = _mock_conn("peu importe")
        with patch.object(
            corpus_service, "_CORPUS_JSON_PATH", tmp_path / "absent.json"
        ), caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            assert corpus_service._verifier_fraicheur_corpus(conn) is False
        conn.execute.assert_not_called()

    def test_erreur_sql_ne_leve_pas(self, corpus_json, caplog):
        """Un défaut de vérification ne doit jamais empêcher le démarrage."""
        conn = MagicMock()
        conn.execute.side_effect = RuntimeError("relation corpus_metadata absente")

        with patch.object(corpus_service, "_CORPUS_JSON_PATH", corpus_json), \
             caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            assert corpus_service._verifier_fraicheur_corpus(conn) is False
        assert "Vérification fraîcheur corpus impossible" in caplog.text


# ─────────────────────────────────────────────────────────────────────────
# initialiser_vdb — critère de clôture : signal observable AU DÉMARRAGE
# ─────────────────────────────────────────────────────────────────────────


class TestInitialiserVdbSignaleLEcart:
    def test_demarrage_avec_corpus_modifie_loggue_un_warning(
        self, corpus_json, caplog
    ):
        """Critère de clôture #487 : un démarrage avec un `corpus_ivr.json`
        modifié et non importé produit un signal observable (WARNING)."""
        empreinte_importee = corpus_service.compute_corpus_fingerprint(corpus_json)
        corpus_json.write_bytes(b'{"version": "2.4.2", "entries": []}')
        engine = _mock_engine_initialiser(163, empreinte_importee)

        corpus_service._get_engine.cache_clear()
        corpus_service._get_model.cache_clear()
        with patch.object(corpus_service, "_get_engine", return_value=engine), \
             patch.object(corpus_service, "_get_model", return_value=MagicMock()), \
             patch.object(corpus_service, "_CORPUS_JSON_PATH", corpus_json), \
             caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
            corpus_service.initialiser_vdb()

        assert "corpus_ivr.json modifié mais pgvector non réimporté" in caplog.text
        # Le moteur démarre malgré tout : le compte d'entrées est bien loggué.
        assert "163" in caplog.text

    def test_demarrage_corpus_a_jour_sans_warning(self, corpus_json, caplog):
        empreinte = corpus_service.compute_corpus_fingerprint(corpus_json)
        engine = _mock_engine_initialiser(163, empreinte)

        corpus_service._get_engine.cache_clear()
        corpus_service._get_model.cache_clear()
        with patch.object(corpus_service, "_get_engine", return_value=engine), \
             patch.object(corpus_service, "_get_model", return_value=MagicMock()), \
             patch.object(corpus_service, "_CORPUS_JSON_PATH", corpus_json), \
             caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
            corpus_service.initialiser_vdb()

        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert "inchangé depuis le dernier import" in caplog.text


# ─────────────────────────────────────────────────────────────────────────
# scripts/import_corpus_ivr.py — écriture de l'empreinte
# ─────────────────────────────────────────────────────────────────────────


class TestImportEcritLEmpreinte:
    def test_upsert_metadata_ecrit_source_sha256(self, import_module, corpus_json):
        conn = MagicMock()
        empreinte = corpus_service.compute_corpus_fingerprint(corpus_json)
        with patch.object(import_module, "_CORPUS_PATH", corpus_json):
            n_cles = import_module._upsert_metadata(
                conn, {"version": "2.4.1"}, 163, empreinte
            )

        ecrit = {
            call.args[1]["key"]: call.args[1]["value"]
            for call in conn.execute.call_args_list
        }
        assert n_cles == 5, f"5 clés attendues, obtenu {n_cles} : {sorted(ecrit)}"
        assert ecrit[import_module.CORPUS_FINGERPRINT_KEY] == hashlib.sha256(
            corpus_json.read_bytes()
        ).hexdigest()
        # Les 4 clés historiques restent écrites (pas de régression).
        assert {"version", "source", "imported_at", "entries_count"} <= set(ecrit)

    def test_empreinte_decrit_les_octets_importes_pas_le_fichier_final(
        self, import_module, corpus_json
    ):
        """Régression TOCTOU : l'empreinte doit décrire le contenu IMPORTÉ.

        Le calcul des embeddings dure plusieurs minutes. Si le JSON est édité
        pendant ce laps et que l'import re-lit le fichier pour le hasher, il
        stocke l'empreinte d'un contenu jamais inséré — et le contrôle au
        démarrage certifie « inchangé » une base pourtant obsolète.
        """
        octets_importes = corpus_json.read_bytes()
        conn = MagicMock()

        with patch.object(import_module, "_CORPUS_PATH", corpus_json):
            corpus, empreinte = import_module._load_corpus()
            # Le JSON est corrigé APRÈS la lecture, pendant les embeddings.
            corpus_json.write_bytes(b'{"version": "9.9.9", "entries": []}')
            import_module._upsert_metadata(conn, corpus, 1, empreinte)

        ecrit = {
            call.args[1]["key"]: call.args[1]["value"]
            for call in conn.execute.call_args_list
        }
        stockee = ecrit[import_module.CORPUS_FINGERPRINT_KEY]
        assert stockee == hashlib.sha256(octets_importes).hexdigest(), (
            "l'empreinte stockée doit être celle des octets réellement importés"
        )
        assert stockee != hashlib.sha256(corpus_json.read_bytes()).hexdigest(), (
            "l'empreinte ne doit PAS provenir d'une relecture du fichier"
        )
        # Le prochain démarrage voit donc bien un écart, comme attendu.
        with patch.object(corpus_service, "_CORPUS_JSON_PATH", corpus_json):
            assert corpus_service._verifier_fraicheur_corpus(
                _mock_conn(stockee)
            ) is False

    def test_le_script_reutilise_la_fonction_canonique_du_service(self, import_module):
        """Garde-fou : une duplication du hash ferait diverger écriture et
        vérification, et l'écart deviendrait indétectable (ou permanent)."""
        assert (
            import_module.corpus_fingerprint_from_bytes
            is corpus_service.corpus_fingerprint_from_bytes
        )
        assert (
            import_module.CORPUS_FINGERPRINT_KEY
            == corpus_service.CORPUS_FINGERPRINT_KEY
        )
