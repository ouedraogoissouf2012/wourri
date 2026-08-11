# WOURI : baseline de transition Convex, phase 0

**Date** : 2026-08-11

**Issue de pilotage** : #372
**Baseline Git** : `APIPy` à `2aa0b49`

## État constaté

- FastAPI fournit les API chat, ASR, STT, TTS, météo, RAG, feedback et admin.
- Le corpus IVR est dans PostgreSQL + pgvector. Sa recherche dépend d'embeddings
  384 dimensions, de SQL brut et de filtres métier.
- La clé `X-API-Key` est un contrat de service avec le serveur WhatsApp. Il n'y
  a ni compte utilisateur, ni JWT, ni rôle, ni organisation.
- Les conversations sont en mémoire, le RAG additionnel est en mémoire et le
  feedback est partiellement stocké en JSONL. Ces données ne sont pas encore
  des agrégats métiers durables.
- Le déploiement actuel contient FastAPI, PostgreSQL et un service Node/Baileys
  séparé. La source de ce dernier n'est pas sur la branche `APIPy`.

## Frontière de travail retenue pour la phase suivante

Convex prépare le nouveau plan de données et d'autorisation. FastAPI reste le
worker de calcul et conserve l'API compatible WhatsApp. Aucun domaine existant
n'est copié dans Convex avant la définition de son propriétaire autoritaire.

## Risques à fermer avant le schéma

1. L'ancien ADR et la vision doivent être amendés par ADR-0024.
2. La résidence des données, l'effacement et les sous-traitants Convex doivent
   être validés avant toute PII de production.
3. Le contrat d'identité doit remplacer les identifiants fournis par le client.
4. Le corpus pgvector ne peut pas être déplacé par simple duplication.
5. Les migrations entre magasins nécessitent outbox, idempotence,
   réconciliation et rollback, jamais un dual-write best-effort.

## Protocole de suivi

Pour chaque phase de l'issue #372, publier dans l'issue et la PR liée :

1. le périmètre et le propriétaire de données ;
2. les interfaces créées ou modifiées ;
3. les décisions et alternatives rejetées ;
4. les commandes exécutées et leur résultat ;
5. les blocages externes sans les masquer.

Une phase ne passe à la suivante qu'après tests pertinents verts, revue du diff
et synthèse publiée.
