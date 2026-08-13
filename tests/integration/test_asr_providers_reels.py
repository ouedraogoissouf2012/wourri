"""Disponibilité RÉELLE des providers ASR — aucun mock.

Pourquoi ce fichier existe (issue #358)
---------------------------------------
Les tests ASR existants mockent `is_available()`. Ils passent donc au vert même
quand le seul modèle dioula de Côte d'Ivoire ne se charge pas, et que 100 % de
l'audio dioula part vers le modèle générique `facebook/mms-1b-all` entraîné sur
du bambara malien.

Aggravant constaté le 13/08 : `MMSDyuASR.is_available()` ne teste que
l'existence du RÉPERTOIRE de l'adapter. Ce répertoire contient les fichiers de
configuration (`config.json`, `vocab.json`, ...) mais pas forcément le fichier de
poids `model.safetensors` (~3,86 Go, exclu du dépôt par `.gitignore`). Le
provider se déclare donc disponible, échoue au chargement, et la chaîne bascule
en silence.

Ces tests vérifient l'état réel du disque, sans rien simuler. Ils ne remplacent
pas les tests unitaires mockés : ils les complètent en rendant la dégradation
silencieuse impossible à ignorer.

Convention
----------
- Les tests de DIAGNOSTIC affichent l'état et n'échouent jamais : ils servent au
  débogage local et en CI sans bloquer un poste qui n'a pas les 3,86 Go.
- Le test de GARDE échoue si l'adapter est présent mais INCOMPLET, c'est-à-dire
  exactement le cas qui produit un faux vert.
- Le test STRICT ne s'exécute que si `WOURI_REQUIRE_DIOULA_MODEL=1`. À activer
  sur l'environnement de démonstration et de production, où l'absence du modèle
  dioula doit être une erreur franche.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.services.asr.mms_dyu_provider import ADAPTER_PATH, MMSDyuASR
from app.services.asr.mms_generic_provider import MMSGenericASR
from app.services.asr.nemo_provider import NemoSoloniASR

# Fichiers que `Wav2Vec2ForCTC.from_pretrained` et `Wav2Vec2Processor` exigent
# réellement pour charger l'adapter.
POIDS_ATTENDUS = ("model.safetensors", "pytorch_model.bin")
CONFIGS_ATTENDUES = ("config.json", "vocab.json")

REQUIRE_DIOULA = os.environ.get("WOURI_REQUIRE_DIOULA_MODEL") == "1"


def _poids_present() -> bool:
    """Vrai si au moins un format de poids est présent dans l'adapter."""
    return any((ADAPTER_PATH / nom).is_file() for nom in POIDS_ATTENDUS)


def _configs_presentes() -> list[str]:
    return [nom for nom in CONFIGS_ATTENDUES if (ADAPTER_PATH / nom).is_file()]


def test_diagnostic_etat_reel_des_providers(capsys: pytest.CaptureFixture[str]) -> None:
    """Affiche l'état réel de chaque provider. N'échoue jamais."""
    lignes = ["", "=== Disponibilité RÉELLE des providers ASR ==="]
    for provider in (NemoSoloniASR(), MMSDyuASR(), MMSGenericASR(language_code="bam")):
        etat = "DISPONIBLE" if provider.is_available() else "indisponible"
        lignes.append(f"  {provider.name:<16} {etat}")

    lignes.append(f"  adapter dioula   : {ADAPTER_PATH}")
    lignes.append(f"    répertoire     : {'présent' if ADAPTER_PATH.is_dir() else 'ABSENT'}")
    lignes.append(f"    poids          : {'présents' if _poids_present() else 'ABSENTS'}")
    lignes.append(f"    configs        : {', '.join(_configs_presentes()) or 'aucune'}")
    with capsys.disabled():
        print("\n".join(lignes))


def test_adapter_dioula_jamais_partiellement_installe() -> None:
    """GARDE — un adapter présent mais sans poids est le pire des cas.

    C'est la situation qui produit un faux vert : `is_available()` retourne True
    parce que le répertoire existe, puis `from_pretrained` échoue et la chaîne
    bascule en silence sur le modèle générique. Mieux vaut un adapter absent,
    franchement indisponible, qu'un adapter à moitié installé.
    """
    if not ADAPTER_PATH.is_dir():
        pytest.skip(
            "Adapter dioula absent : cas franc, le provider se déclare "
            "indisponible et la chaîne bascule explicitement."
        )

    assert _poids_present(), (
        f"Adapter dioula INCOMPLET dans {ADAPTER_PATH}.\n"
        f"  Configurations présentes : {', '.join(_configs_presentes()) or 'aucune'}\n"
        f"  Poids attendus (l'un des deux) : {', '.join(POIDS_ATTENDUS)} — ABSENTS\n\n"
        "Conséquence : is_available() retourne True (le répertoire existe), le "
        "chargement échoue, et 100 % de l'audio dioula part vers le modèle "
        "générique facebook/mms-1b-all entraîné sur du bambara malien.\n"
        "Voir ADR-0026 et issue #358. Récupérer model.safetensors (~3,86 Go), "
        "ou retirer le répertoire pour rendre l'indisponibilité franche."
    )


@pytest.mark.skipif(
    not REQUIRE_DIOULA,
    reason="Nécessite WOURI_REQUIRE_DIOULA_MODEL=1 (démonstration, production).",
)
def test_modele_dioula_exigible_charge_reellement() -> None:
    """STRICT — sur un environnement qui promet du dioula, le modèle doit charger.

    Ne se contente pas de `is_available()` : effectue le chargement réel, seul
    moyen de prouver que la transcription dioula ne sera pas assurée par le
    modèle générique.
    """
    provider = MMSDyuASR()
    assert provider.is_available(), (
        f"Provider dioula indisponible alors que WOURI_REQUIRE_DIOULA_MODEL=1. "
        f"Adapter attendu dans {ADAPTER_PATH}."
    )

    charge = provider._get_model()  # noqa: SLF001 — vérification de chargement réel
    assert charge is not None, (
        "Le provider dioula se déclare disponible mais son chargement échoue. "
        "C'est exactement la dégradation silencieuse décrite dans l'issue #358 : "
        "la chaîne va basculer sur le modèle générique sans erreur visible."
    )
    modele, processeur = charge
    assert modele is not None and processeur is not None


def test_chaine_ne_presente_jamais_le_generique_comme_dioula() -> None:
    """Le modèle générique doit rester identifiable, jamais confondu avec du dioula.

    Garde-fou de nommage : la démonstration et les traces doivent pouvoir dire
    quel modèle a produit une transcription (ADR-0026, décision 4).
    """
    generique = MMSGenericASR(language_code="bam")
    dioula = MMSDyuASR()

    assert generique.name != dioula.name
    assert "dyu" not in generique.name.lower(), (
        f"Le provider générique s'appelle '{generique.name}' : un nom contenant "
        "'dyu' laisserait croire à du dioula ivoirien alors qu'il s'agit du "
        "modèle générique entraîné sur du bambara malien."
    )
