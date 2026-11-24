"""#650 : chaque transcription laisse une mesure — durée de l'audio, durée de l'appel.

La durée de l'audio est LUE dans l'en-tête Ogg Opus (granule du dernier paquet à 48 kHz,
moins le pre-skip), jamais estimée depuis la taille : le débit d'un vocal WhatsApp réel
n'est pas mesuré (les .ogg du dépôt sont des encodages ffmpeg, ~8,5 Ko/s).
La ligne de journal est faite pour être agrégée : préfixe stable, couples clé=valeur.
"""
import asyncio
import logging
from pathlib import Path

import pytest

from app.services import mesure_asr
from app.services.mesure_asr import PREFIXE, duree_ogg_opus, transcrire_mesure

RACINE = Path(__file__).resolve().parents[2]
TONALITE = (RACINE / "tests" / "e2e" / "fixtures" / "sample_tone.ogg").read_bytes()
VOIX = (RACINE / "test_vivienne.ogg").read_bytes()


def test_la_duree_est_lue_dans_l_en_tete_ogg_opus():
    assert duree_ogg_opus(TONALITE) == pytest.approx(1.0, abs=0.001)
    assert duree_ogg_opus(VOIX) == pytest.approx(4.896, abs=0.001)


@pytest.mark.parametrize("octets", [
    b"",
    b"RIFF\x24\x00\x00\x00WAVEfmt ",           # un WAV : pas de l'Ogg
    b"OggS\x00" + b"\x00" * 40,                 # Ogg sans OpusHead (autre codec)
    b"\x00\xff garbage " * 50,
], ids=["vide", "wav", "ogg_sans_opus", "illisible"])
def test_ce_qui_n_est_pas_de_l_ogg_opus_lisible_n_a_pas_de_duree(octets):
    assert duree_ogg_opus(octets) is None


def test_un_fichier_reduit_a_ses_pages_d_en_tete_n_a_pas_de_duree():
    # Seules les deux pages d'en-tête : granule 0 — « inconnue », pas « 0 seconde ».
    troisieme_page = TONALITE.find(b"OggS", TONALITE.find(b"OggS", TONALITE.find(b"OggS") + 1) + 1)
    assert duree_ogg_opus(TONALITE[:troisieme_page]) is None


class _Chaine:
    def __init__(self, resultat):
        self.resultat = resultat

    async def transcribe(self, audio_bytes, extension):
        if isinstance(self.resultat, Exception):
            raise self.resultat
        return self.resultat


def _mesure(caplog) -> dict:
    lignes = [r.getMessage() for r in caplog.records if r.getMessage().startswith(PREFIXE)]
    assert len(lignes) == 1, lignes
    # L'agrégation doit se faire par simple découpage : pas d'espace dans les valeurs.
    return dict(couple.split("=", 1) for couple in lignes[0][len(PREFIXE):].split())


def _lancer(resultat, octets=TONALITE):
    return asyncio.run(transcrire_mesure(_Chaine(resultat), octets, "ogg",
                                         endpoint="transcribe-and-translate", langue="bam"))


@pytest.mark.parametrize("resultat,attendu", [
    ("malo sɛnɛ", "texte"), ("", "vide"), (None, "aucun"),
], ids=["texte", "vide", "aucun"])
def test_chaque_transcription_laisse_une_ligne_agregeable(caplog, resultat, attendu):
    caplog.set_level(logging.INFO, logger=mesure_asr.__name__)
    assert _lancer(resultat) == resultat
    m = _mesure(caplog)
    assert m["endpoint"] == "transcribe-and-translate" and m["langue"] == "bam" and m["extension"] == "ogg"
    assert int(m["octets"]) == len(TONALITE)
    assert float(m["duree_audio_s"]) == pytest.approx(1.0, abs=0.01)
    assert float(m["duree_appel_s"]) >= 0
    float(m["rapport"])  # appel / audio : un nombre quand la durée de l'audio est connue
    assert m["resultat"] == attendu


def test_une_duree_inconnue_est_ecrite_comme_telle(caplog):
    caplog.set_level(logging.INFO, logger=mesure_asr.__name__)
    _lancer("texte", octets=b"RIFF\x24\x00\x00\x00WAVEfmt ")
    m = _mesure(caplog)
    assert m["duree_audio_s"] == "inconnue" and m["rapport"] == "inconnu"


def test_une_exception_est_mesuree_puis_relancee(caplog):
    caplog.set_level(logging.INFO, logger=mesure_asr.__name__)
    with pytest.raises(RuntimeError):
        _lancer(RuntimeError("mémoire"))
    assert _mesure(caplog)["resultat"] == "exception"
