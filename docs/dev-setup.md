# Guide de mise en place de l'environnement de développement Wourri

Ce document décrit la procédure d'installation et de démarrage de l'environnement de
développement local de Wourri. **Objectif : un nouvel intervenant doit pouvoir reproduire
l'environnement en moins de 10 minutes** (critère ADR-0008 §Phase A).

---

## Prérequis

| Outil | Version minimale | Lien |
|---|---|---|
| Docker Desktop | 4.x | https://www.docker.com/products/docker-desktop/ |
| Git | 2.x | https://git-scm.com/ |
| Python | 3.11+ | https://www.python.org/ |

**Windows** : Docker Desktop nécessite **WSL2 activé** (recommandation officielle Docker
sur Windows 10/11). Vérification : `wsl --status` doit retourner un nom de distribution
par défaut (Ubuntu par exemple).

---

## 1. Cloner le projet

```bash
git clone https://github.com/ouedraogoissouf2012/wourri.git
cd wourri/wouri-api
```

---

## 2. Démarrer PostgreSQL + pgvector (Sprint F Phase A)

L'environnement Postgres est fourni via `docker-compose.dev.yml`. Aucune installation
PostgreSQL native n'est requise — Docker s'occupe de tout.

```bash
docker compose -f docker-compose.dev.yml up -d
```

Vérifier que le service est `healthy` (peut prendre 30–60 secondes au premier démarrage,
le temps que PostgreSQL initialise sa base de données) :

```bash
docker compose -f docker-compose.dev.yml ps
```

Sortie attendue :

```
NAME                    IMAGE                       STATUS
wourri_postgres_dev     pgvector/pgvector:pg16      Up (healthy)
```

### Vérification que l'extension pgvector est active

```bash
docker exec -it wourri_postgres_dev psql -U wourri -d wourri_dev -c "SELECT '[1,2,3]'::vector;"
```

Résultat attendu :

```
 vector
---------
 [1,2,3]
(1 row)
```

Pour une validation plus stricte (preuve de persistance dans une colonne `vector`,
recommandée par la review TESTS) :

```bash
docker exec -it wourri_postgres_dev psql -U wourri -d wourri_dev -c "CREATE TEMP TABLE t(v vector(3)); INSERT INTO t VALUES ('[1,2,3]'); SELECT v FROM t;"
```

Le `INSERT` puis `SELECT` prouve que le stockage colonne `vector` fonctionne (et pas
seulement le parser de type). Phase B s'appuie directement sur ce stockage.

Si l'un des deux tests réussit, **Phase A est validée** sur ta machine.

Si tu vois `ERROR: type "vector" does not exist`, voir la section [Troubleshooting](#troubleshooting).

---

## 3. Configurer les variables d'environnement

```bash
cp .env.example .env
```

Éditer `.env` pour :

- Remplir `DEEPSEEK_API_KEY` avec ta clé (obligatoire pour le chat et les fallbacks)
- Définir une `API_SECRET_KEY` (obligatoire en production, optionnel en dev) :
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```
- Les variables `POSTGRES_*` ont des valeurs par défaut cohérentes avec
  `docker-compose.dev.yml` — pas besoin de les modifier pour le dev local.

---

## 4. Installer les dépendances Python

```bash
pip install -r requirements.txt
```

Note : Phase A n'ajoute **aucune nouvelle dépendance Python** au `requirements.txt`.
Les dépendances `sqlalchemy`, `alembic`, `psycopg`, `pgvector` seront ajoutées en
Phase B (ADR-0008).

---

## 5. Démarrer l'API FastAPI

```bash
uvicorn app.main:app --port 8000 --reload
```

L'API est disponible sur `http://localhost:8000`.

Vérification de santé :

```bash
curl http://localhost:8000/health
```

---

## Arrêt et reset

### Arrêt simple (les données PostgreSQL sont conservées)

```bash
docker compose -f docker-compose.dev.yml down
```

### Reset complet (supprime le volume → perd les données dev)

À utiliser si l'extension `vector` n'est pas active alors que le container démarre
correctement (typique d'un volume hérité d'un démarrage antérieur sans le script
`init.sql`).

```bash
docker compose -f docker-compose.dev.yml down -v
docker volume rm pgdata_wourri
```

Puis redémarrer normalement avec `docker compose ... up -d`. Le script
`db-init/init.sql` sera ré-exécuté car le volume est neuf.

---

## Troubleshooting

| Symptôme | Cause probable | Solution |
|---|---|---|
| `no such service: postgres` ou `no configuration file provided` | Commande `docker compose` lancée sans `-f docker-compose.dev.yml` (le fichier n'est pas le nom par défaut `docker-compose.yml`) | Toujours utiliser `docker compose -f docker-compose.dev.yml ...`. Alternative : exporter `COMPOSE_FILE=docker-compose.dev.yml` dans son shell. |
| `port is already allocated` au `up` | Une autre instance PostgreSQL écoute sur 5433 | Vérifier avec `netstat -ano \| findstr :5433` (Windows) ou `lsof -i :5433` (Linux/Mac). Soit arrêter l'autre service, soit modifier le port dans `docker-compose.dev.yml` (`5434:5432`) et mettre à jour `POSTGRES_URL` dans `.env` |
| `Cannot connect to the Docker daemon` | Docker Desktop pas démarré | Lancer Docker Desktop depuis le menu Démarrer (Windows) ou Applications (Mac). Attendre que l'icône systray indique "Engine running" |
| Statut `healthcheck: starting` qui dure plusieurs minutes | Premier démarrage PostgreSQL lent (initialisation de la base) | Patienter jusqu'à 60s. Surveiller les logs : `docker compose -f docker-compose.dev.yml logs -f postgres` |
| `type "vector" does not exist` lors du `SELECT '[1,2,3]'::vector;` | Volume Docker hérité d'un précédent démarrage sans `init.sql` | Faire un reset complet (cf. section [Arrêt et reset](#arrêt-et-reset)) |
| Connexion refusée sur `localhost:5433` depuis un client externe | Restriction WSL2/firewall | Essayer `127.0.0.1:5433` au lieu de `localhost:5433`. Si toujours en échec, vérifier la configuration WSL2 (`wsl --status`) |
| `permission denied` sur `db-init/` | Droits NTFS Windows (rare) | Vérifier que le dossier est lisible par l'utilisateur courant. Au pire, recréer le dossier manuellement |

---

## Prochaines phases (référence ADR-0008)

Cette Phase A est **purement additive** : aucun code applicatif n'utilise encore PostgreSQL.
Le serveur Wourri fonctionne toujours sur ChromaDB local (`app/services/vdb_service.py`).

Les phases suivantes (à venir dans des sprints dédiés) :

| Phase | Sujet | Ajouts |
|---|---|---|
| **B** | Schéma SQL + migrations Alembic | `requirements.txt` : `sqlalchemy`, `alembic`, `psycopg[binary]`, `pgvector` ; dossier `alembic/` ; script `scripts/import_corpus_ivr.py` |
| **C** | Service `corpus_service.py` + feature flag | `app/services/corpus_service.py`, `app/services/corpus_facade.py`, setting `corpus_storage_mode` |
| **D** | Validation terrain mode `dual` | Endpoint `/admin/corpus-divergence-report`, observabilité |
| **E** | Bascule + déprécation ChromaDB | Suppression `vdb_service.py`, retrait `chromadb` de `requirements.txt` |

---

## Références

- [ADR-0008 — Plan migration ChromaDB → PostgreSQL+pgvector](adr/0008-plan-migration-chromadb-pgvector.md)
- [ADR-0001 — Choix stockage : PostgreSQL+pgvector](adr/0001-choix-stockage-donnees.md)
- [Documentation officielle pgvector](https://github.com/pgvector/pgvector)
- [Docker Desktop pour Windows](https://docs.docker.com/desktop/install/windows-install/)
