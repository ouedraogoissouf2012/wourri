"""Logique métier du corpus IVR, partagée entre les backends de persistance.

Les backends (`vdb_service` = Chroma, `corpus_service` = pgvector, ADR-0008) sont
de purs adaptateurs d'I/O : la logique métier commune (saison agricole, scoring
des candidats) vit ici, une seule fois, pour éviter la divergence silencieuse.
"""
