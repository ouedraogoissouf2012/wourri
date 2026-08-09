"""Logique métier du corpus IVR, partagée entre les backends de persistance.

Le backend corpus (`corpus_service` = pgvector, ADR-0008 Phase E) est
de purs adaptateurs d'I/O : la logique métier commune (saison agricole, scoring
des candidats) vit ici, une seule fois, pour éviter la divergence silencieuse.
"""
