"""Construction des messages système d'une langue (ADR-0049).

Le test qui tient tout : `test_ce_qui_est_ecrit_est_ce_que_le_moteur_sait_lire`.
Le script et le service se parlent par un fichier ; si leurs formats divergent,
le mécanisme reste muet sans qu'aucune erreur ne se produise.
"""
import json

import pytest

from app.services import messages_systeme as msys
from scripts import construire_messages_systeme as cms

ROLES = {
    "_SYSTEME_REPLI": "generic_fallback_001",
    "_SYSTEME_SALUTATION": "generic_salutation_001",
}

# Forme exacte d'une ligne renvoyée par `GET /corpus` (productions_repo._row).
PRODUCTION_REPLI = {
    "concept_id": "generic_fallback_001",
    "text_local": "N timan ɔ ndɛ'n i wlɛ.",
    "text_fr": "Je n'ai pas compris ta question.",
    "audio_url": "audio/eee555.webm",
    "status": "production",
    "kind": "contenu",
}
PRODUCTION_SALUT = {
    "concept_id": "generic_salutation_001",
    "text_local": "Akwaba.",
    "text_fr": "Bienvenue.",
    "audio_url": None,
    "status": "production",
    "kind": "contenu",
}


# ------------------------------------------------------------------ table des sources


def test_table_des_sources_du_depot_est_lisible():
    roles = cms.roles_attendus()
    assert roles["_SYSTEME_REPLI"] == "generic_fallback_001"
    # Les salutations horaires portent un gabarit météo : hors périmètre (ADR-0049).
    assert "salutation_matin_001" not in roles.values()


def test_table_absente_echoue_clairement(tmp_path):
    with pytest.raises(cms.EchecConstruction, match="introuvable"):
        cms.roles_attendus(tmp_path / "absent.json")


# ------------------------------------------------------------------ assemblage


def test_les_productions_sont_rangees_par_role():
    msgs, manquants = cms.messages([PRODUCTION_REPLI, PRODUCTION_SALUT], ROLES)
    assert manquants == []
    assert msgs["_SYSTEME_REPLI"]["texte"] == "N timan ɔ ndɛ'n i wlɛ."
    assert msgs["_SYSTEME_REPLI"]["audio"] == "audio/eee555.webm"


def test_un_role_non_produit_est_signale_pas_invente():
    msgs, manquants = cms.messages([PRODUCTION_REPLI], ROLES)
    assert list(msgs) == ["_SYSTEME_REPLI"]
    assert manquants == ["_SYSTEME_SALUTATION"]


def test_un_message_sans_voix_est_garde_sans_cle_audio():
    """Le texte validé vaut mieux que rien ; l'absence de voix ne doit pas le bloquer."""
    msgs, _ = cms.messages([PRODUCTION_SALUT], ROLES)
    assert "audio" not in msgs["_SYSTEME_SALUTATION"]
    assert msgs["_SYSTEME_SALUTATION"]["texte"] == "Akwaba."


def test_un_texte_vide_vaut_pas_produit():
    """Mieux vaut le repli français qu'une phrase vide servie à un agriculteur."""
    vide = dict(PRODUCTION_REPLI, text_local="   ")
    msgs, manquants = cms.messages([vide], ROLES)
    assert msgs == {} and sorted(manquants) == sorted(ROLES)


def test_les_contenus_hors_table_sont_ignores():
    autre = {"concept_id": "mais_conseil_001", "text_local": "x", "text_fr": "y"}
    msgs, _ = cms.messages([autre, PRODUCTION_REPLI], ROLES)
    assert list(msgs) == ["_SYSTEME_REPLI"]


# ------------------------------------------------------------------ le contrat


def test_ce_qui_est_ecrit_est_ce_que_le_moteur_sait_lire(tmp_path, monkeypatch):
    """Le script écrit, le service relit — sans ce test, les deux peuvent diverger
    en silence et le mécanisme resterait muet sans la moindre erreur."""
    msgs, _ = cms.messages([PRODUCTION_REPLI, PRODUCTION_SALUT], ROLES)
    cible = cms.ecrire("bci", msgs, dossier=tmp_path)
    assert cible.name == "messages_systeme_bci.json"

    monkeypatch.setattr(msys, "DOSSIER", tmp_path)
    msys.vider_cache()
    try:
        lu = msys.message("bci", msys.REPLI)
        assert lu.texte == "N timan ɔ ndɛ'n i wlɛ."
        assert lu.texte_fr == "Je n'ai pas compris ta question."
        assert msys.url_audio(lu, "http://voix/audio") == "http://voix/audio/eee555.ogg"

        sans_voix = msys.message("bci", msys.SALUTATION)
        assert sans_voix.texte == "Akwaba." and sans_voix.audio is None
    finally:
        msys.vider_cache()


def test_le_fichier_ecrit_porte_sa_langue_et_sa_date(tmp_path):
    import datetime

    msgs, _ = cms.messages([PRODUCTION_REPLI], ROLES)
    data = json.loads(cms.ecrire("bci", msgs, dossier=tmp_path).read_text(encoding="utf-8"))
    assert data["langue"] == "bci"
    assert data["version"].startswith("bci-") and datetime.date.today().isoformat() in data["version"]


# ------------------------------------------------------------------ garde-fous


def test_rien_de_produit_n_ecrit_aucun_fichier(tmp_path, monkeypatch):
    """Un fichier vide ferait croire à un mécanisme en place. On préfère le repli."""
    monkeypatch.setenv("LQE_USER", "u")
    monkeypatch.setenv("LQE_PASSWORD", "x" * 12)
    monkeypatch.setattr(cms, "connexion", lambda *a, **k: object())
    monkeypatch.setattr(cms, "corpus_servi", lambda *a, **k: [])
    code = cms.main(["bci", "--atelier", "http://atelier", "--out", str(tmp_path)])
    assert code == 1
    assert not (tmp_path / "messages_systeme_bci.json").exists()


def test_identifiants_manquants_echouent_clairement(monkeypatch):
    monkeypatch.delenv("LQE_USER", raising=False)
    monkeypatch.delenv("LQE_PASSWORD", raising=False)
    with pytest.raises(cms.EchecConstruction, match="identifiants"):
        cms.main(["bci", "--atelier", "http://atelier"])


def test_un_role_manquant_sort_en_echec_mais_ecrit_le_reste(tmp_path, monkeypatch):
    """Il faut que l'écart se voie dans un enchaînement de commandes, sans perdre
    le message déjà produit."""
    monkeypatch.setenv("LQE_USER", "u")
    monkeypatch.setenv("LQE_PASSWORD", "x" * 12)
    monkeypatch.setattr(cms, "connexion", lambda *a, **k: object())
    monkeypatch.setattr(cms, "corpus_servi", lambda *a, **k: [PRODUCTION_REPLI])
    code = cms.main(["bci", "--atelier", "http://atelier", "--out", str(tmp_path)])
    assert code == 1
    data = json.loads((tmp_path / "messages_systeme_bci.json").read_text(encoding="utf-8"))
    assert list(data["messages"]) == ["_SYSTEME_REPLI"]
