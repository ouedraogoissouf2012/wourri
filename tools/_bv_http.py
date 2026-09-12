"""Scrapers HTTP du validateur — constructeurs d'URL et instances de source."""
from collections import Counter

import _bv_registry
from _bv_sources import HttpScraperSource


def _bamadaba_url(concept_fr: str):
    return (
        "http://cormand.huma-num.fr/cgi-bin/corpus.cgi",
        {"c": "Bamadaba", "q": concept_fr, "interface_language": "fr"},
    )


def _voa_url(concept_fr: str):
    return (f"https://www.voabambara.com/s?k={concept_fr}", None)


def _bambara_org_url(concept_fr: str):
    return ("http://www.bambara.org/biblia/bam/dico/dico_f.htm", None)


def _bamanankan_url(concept_fr: str):
    return (f"https://www.bamanankan.org/?s={concept_fr}", None)


# `_bv_registry.extraire_fenetre` est la forme liee au lexique de reference :
# elle garantit le chargement du corpus UD avant extraction. La fonction lit
# l'etat du registre a chaque appel, donc une substitution de `_ud_mots` en
# test reste visible malgre la capture de la reference ici.
_BAMADABA_SRC = HttpScraperSource(
    name="bamadaba",
    url_builder=_bamadaba_url,
    weight=2,
    fenetre=150,
    extraire_fenetre=_bv_registry.extraire_fenetre,
    pre_extraction_check=True,
)
_VOA_SRC = HttpScraperSource(
    name="voa_bambara",
    url_builder=_voa_url,
    weight=1,
    fenetre=200,
    extraire_fenetre=_bv_registry.extraire_fenetre,
)
_BAMBARA_ORG_SRC = HttpScraperSource(
    name="bambara_org",
    url_builder=_bambara_org_url,
    weight=1,
    fenetre=100,
    extraire_fenetre=_bv_registry.extraire_fenetre,
)
_BAMANANKAN_SRC = HttpScraperSource(
    name="bamanankan",
    url_builder=_bamanankan_url,
    weight=1,
    fenetre=200,
    extraire_fenetre=_bv_registry.extraire_fenetre,
)


def _bamadaba(concept_fr: str) -> Counter:
    """Wrapper de compatibilite (issue #233 PR 3) : delegue a HttpScraperSource.

    Bamadaba = dictionnaire bambara du CNRS. Cherche le concept en francais
    et extrait les mots bambara dans une fenetre de 150 chars autour de chaque
    occurrence. `pre_extraction_check=True` : on saute l'extraction si le
    concept n'apparait pas dans la page (optimisation legacy preservee).
    """
    return _BAMADABA_SRC.find(concept_fr)


def _voa_bambara(concept_fr: str) -> Counter:
    """Wrapper de compatibilite (issue #233 PR 3) : delegue a HttpScraperSource.

    VOA Bambara = actualites en bambara. Fenetre 200 chars.
    """
    return _VOA_SRC.find(concept_fr)


def _bambara_org(concept_fr: str) -> Counter:
    """Wrapper de compatibilite (issue #233 PR 3) : delegue a HttpScraperSource.

    Bambara.org/dico = dictionnaire francais-bambara en HTML statique. Fenetre
    petite (100 chars) car les entrees dictionnaire sont courtes.
    """
    return _BAMBARA_ORG_SRC.find(concept_fr)


def _bamanankan_org(concept_fr: str) -> Counter:
    """Wrapper de compatibilite (issue #233 PR 3) : delegue a HttpScraperSource.

    Bamanankan.org = reference academique bambara (WordPress). Fenetre 200 chars.
    """
    return _BAMANANKAN_SRC.find(concept_fr)
