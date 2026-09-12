"""Wrappers de lookup et de confirmation — une fonction par source.

Chaque wrapper accede aux instances via l'attribut de module
(`_bv_registry._AGRI_DICT_SRC`, jamais `from _bv_registry import _AGRI_DICT_SRC`)
afin que la substitution en test reste effective : un import par valeur
figerait la reference au moment de l'import.
"""
import re

import _bv_registry


def _agri_dict_lookup(concept_fr: str):
    return _bv_registry._AGRI_DICT_SRC.find(concept_fr)


def _bayelemabaga(concept_fr: str):
    _bv_registry._bayelemabaga_load_all_splits()
    return _bv_registry._bayelemabaga_src().find(concept_fr)


def _koumankan(concept_fr: str):
    return _bv_registry._kouman_src().find(concept_fr)


def _findora(concept_fr: str):
    return _bv_registry._findora_src().find(concept_fr)


def _jeli_confirme(terme: str) -> bool:
    _bv_registry._charger_jeli()
    terme = terme.lower()
    motif = re.compile(r"\b" + re.escape(terme) + r"\b")
    return any(motif.search(phrase) for phrase in _bv_registry._jeli_phrases)


def _ud_confirme(terme: str) -> bool:
    _bv_registry._charger_ud()
    return terme.lower() in _bv_registry._ud_mots
