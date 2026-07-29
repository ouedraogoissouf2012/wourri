# ADR-0017 — Dashboard d’observabilité sans contenu PII

**Statut** : accepté
**Date** : 2026-07-29
**Auteur** : Codex, sous direction du propriétaire du projet
**Valideur** : propriétaire du projet (validation explicite du 2026-07-29)

## Contexte

L’issue #41 demandait initialement un dashboard administrateur alimenté par
SQLite et conservant les conversations, transcriptions ASR et réponses IVR.
Cette formulation est antérieure à deux décisions structurantes :

- l’ADR-0001 impose PostgreSQL comme stockage relationnel de production ;
- l’issue critique #215 bloque la conservation durable de logs contenant des
  numéros de téléphone ou des transcriptions tant que la politique ARTCI de
  rétention et de purge n’est pas définie.

Le dépôt dispose déjà d’une authentification opérateur par `X-API-Key` et d’un
router `/admin`. Ajouter un mot de passe administrateur distinct créerait un
second mécanisme de secrets et de rotation sans bénéfice.

## Décision

Le dashboard de #41 utilise PostgreSQL et ne persiste que des métadonnées
techniques non rattachées à une personne :

- horodatage ;
- route FastAPI normalisée et méthode HTTP ;
- code de statut et durée totale ;
- intent, culture et source internes lorsqu’ils sont déjà produits par le NLU ;
- succès/échec ASR et indicateur NLU hors sujet.

Il est interdit à cette table de contenir :

- numéro de téléphone, `user_id`, adresse IP ou identifiant pseudonymisé ;
- message utilisateur, transcription, réponse IVR/LLM ou audio ;
- en-tête HTTP, query string, nom de fichier ou détail d’exception.

La page HTML est une coquille statique sans donnée. L’endpoint JSON qui fournit
les métriques est protégé par le mécanisme existant `X-API-Key`. La clé est
conservée uniquement dans `sessionStorage` par le navigateur et n’est jamais
placée dans une URL.

L’enregistrement est *best effort* et asynchrone : une indisponibilité
PostgreSQL ne doit jamais dégrader une réponse destinée à un agriculteur.

## Conséquences

### Positives

- aucune duplication SQLite/PostgreSQL ;
- statistiques exploitables sans créer un nouveau stock de PII ;
- réutilisation de la rotation de clé déjà documentée ;
- faible impact de latence sur les routes utilisateur ;
- schéma extensible par migrations Alembic.

### Limites assumées

- le widget « conversations récentes » devient « requêtes récentes » et
  n’affiche aucun texte ;
- les métriques par étape ASR/NLU/IVR/TTS ne sont pas inventées : seule la
  durée totale est mesurée dans cette version ;
- l’affichage de transcriptions ou de conversations reste bloqué par #215.

## Alternatives rejetées

### SQLite

Rejeté car contraire à l’ADR-0001 et fragile sous écritures concurrentes.

### Conservation des transcriptions avec identifiant haché

Rejetée : une transcription peut contenir des données personnelles même sans
numéro de téléphone, et un hash stable reste une donnée pseudonymisée.

### Mot de passe admin séparé

Rejeté : il dupliquerait le stockage, la rotation et les contrôles déjà assurés
par `API_SECRET_KEY`.

## Critères de validation

- migration PostgreSQL réversible ;
- aucun champ PII ou contenu libre dans le schéma ;
- dashboard et endpoint de données testés ;
- endpoint de données protégé par `require_api_key` ;
- panne PostgreSQL sans impact sur les réponses API instrumentées ;
- tests de non-régression du pipeline existant verts.

## Références

- issue #41 — dashboard administrateur ;
- issue #215 — conformité ARTCI des logs PII ;
- ADR-0001 — PostgreSQL + pgvector ;
- ADR-0008 — migrations et accès PostgreSQL ;
- `app/security.py` — authentification `X-API-Key`.
