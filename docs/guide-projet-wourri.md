# Comprendre Wourri pas à pas

> **Public visé** : toi (Ouedraogo Issouf / Ruben), nouveau dev rejoignant le projet,
> ou investisseur/sponsor qui veut comprendre l'architecture.
>
> **Objectif** : à la fin de ce document tu sais expliquer comment Wourri fonctionne,
> tu sais lire chaque ligne de `docker-compose.dev.yml`, tu sais ce que fait chaque
> table dans la BDD, et tu peux dépanner une panne dev sans aide.
>
> **Temps de lecture** : ~30 minutes. **Pré-requis** : avoir installé Docker Desktop.

---

## Table des matières

1. [Vue d'ensemble Wourri](#1-vue-densemble-wourri)
2. [Pourquoi Docker](#2-pourquoi-docker)
3. [Anatomie du `docker-compose.dev.yml`](#3-anatomie-du-docker-composedevyml-wourri)
4. [Cycle de vie d'un container Postgres dev](#4-cycle-de-vie-dun-container-postgres-dev)
5. [Pourquoi PostgreSQL + pgvector (vs ChromaDB)](#5-pourquoi-postgresql--pgvector-vs-chromadb)
6. [Le schéma SQL (3 tables + 6 index)](#6-le-schéma-sql-3-tables--6-index)
7. [Les 3 refontes Sprint F livrées 2026-05-19](#7-les-3-refontes-sprint-f-livrées-2026-05-19)
8. [Cheatsheet et FAQ « expliquer à un tiers »](#8-cheatsheet-et-faq-pour-expliquer-à-un-tiers)

---

## 1. Vue d'ensemble Wourri

### Le produit en une phrase

**Wourri est un bot WhatsApp qui répond en audio bambara/dioula à des questions
agricoles posées en audio bambara/dioula par des agriculteurs ivoiriens et maliens.**

### Le parcours utilisateur (golden path)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│   📱 Agriculteur en Côte d'Ivoire (Bouaké, Korhogo, Yamoussoukro…)      │
│                                                                         │
│   1. Envoie un message vocal WhatsApp                                   │
│      « ne be malo senɛ, ji man di ne ma »                               │
│      (« je plante du riz, je n'ai pas d'eau »)                          │
│                                                                         │
│                              │                                          │
│                              ▼                                          │
│                                                                         │
│   2. WhatsApp Server (Node.js + Baileys, port 3001)                     │
│      - Reçoit l'audio                                                   │
│      - Renvoie vers l'API Python                                        │
│                                                                         │
│                              │                                          │
│                              ▼                                          │
│                                                                         │
│   3. API FastAPI Python (port 8000)                                     │
│      a. ASR : Audio → Texte bambara (NeMo Soloni / Omnilingual)         │
│      b. NLU : Texte → intent + concepts                                 │
│         (« QUESTION_IRRIGATION », « CULTURE_RIZ »)                      │
│      c. Recherche corpus : Chroma (legacy) ou Postgres+pgvector         │
│         (cascade : exact → wildcard → intent seul)                      │
│      d. Si pas de match : DeepSeek API + NLLB-200 (traduction FR→bam)   │
│      e. TTS : Texte bambara → Audio (facebook/mms-tts-dyu)              │
│                                                                         │
│                              │                                          │
│                              ▼                                          │
│                                                                         │
│   4. Renvoie l'audio bambara à l'agriculteur via WhatsApp               │
│      « aw ye ji caman di malo ma… »                                     │
│      (« donnez beaucoup d'eau au riz… »)                                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### L'architecture en deux services

| Service | Langage | Port | Rôle |
|---|---|---|---|
| `whatsapp-server/` | Node.js + Baileys | 3001 | Reçoit/envoie WhatsApp, transcode audio, relais HTTP |
| `wouri-api/` | Python + FastAPI | 8000 | ASR + NLU + corpus + LLM fallback + TTS |

Et depuis Sprint F (mai 2026), un troisième service **infra-only en développement** :

| Service | Image | Port | Rôle |
|---|---|---|---|
| `wourri_postgres_dev` | `pgvector/pgvector:pg16` | `127.0.0.1:5433` | Base SQL + recherche vectorielle (remplace ChromaDB à terme) |

### Pour expliquer à un investisseur

> « Nous résolvons un problème concret : 70 % des agriculteurs en Côte d'Ivoire
> n'écrivent pas le français mais parlent WhatsApp tous les jours. Wourri leur
> permet de parler à un conseil agricole expert dans leur langue maternelle —
> bambara/dioula — au lieu de devoir aller chercher quelqu'un qui parle français
> ou lit dans une langue qu'ils maîtrisent peu. Techniquement, c'est un pipeline
> audio→texte→IA→texte→audio entièrement adapté aux langues mandé. »

---

## 2. Pourquoi Docker

### Le problème que Docker résout

Imagine que tu installes PostgreSQL sur ton PC Windows pour développer Wourri.
Tu installes la version 16, tu configures un mot de passe, tu crées une base.
Six mois plus tard, un nouveau dev rejoint le projet. Il a déjà PostgreSQL 14
installé sur son Mac pour un autre projet. Il essaie d'installer la version 16
en parallèle : conflit de ports, conflit de fichiers de config, prise de tête
pendant 2 jours.

**C'est le « ça marche chez moi » classique.** Et c'est exactement ce que
Docker élimine.

### Le concept en 3 mots-clés

#### Image

Une **image Docker** est une « photo figée » d'un système prêt à fonctionner :
le système d'exploitation Linux minimal + PostgreSQL installé + l'extension
pgvector compilée + une config par défaut. C'est un fichier inerte qui ne fait
rien tant que tu ne le démarres pas.

Exemple : `pgvector/pgvector:pg16` est une image officielle qui contient
exactement PostgreSQL 16 + pgvector compilé pour cette version. Tu la
télécharges une fois, elle ne change jamais (sauf si tu changes de tag).

#### Container

Un **container** est une instance vivante d'une image. C'est comme la différence
entre une classe (image) et un objet (container). Quand tu fais
`docker compose up -d`, Docker prend l'image, en fait une copie isolée, lui
donne un nom (`wourri_postgres_dev`) et la lance.

Le container est **isolé** : il a son propre système de fichiers, ses propres
processus, sa propre couche réseau. Il ne peut pas voir ce qu'il y a en dehors
sauf ce que tu lui donnes explicitement.

#### Volume

Un **volume** est un espace de stockage qui **survit** à la destruction du
container. Si tu détruis ton container Postgres, les données seraient perdues
sans volume. Avec un volume, tu peux faire `docker compose down -v` ne supprime
PAS les données (sauf si tu ajoutes `-v` explicitement = « volumes aussi »).

Wourri utilise un volume nommé `pgdata_wourri` (déclaré dans le compose).

### Pourquoi `docker compose` plutôt que `docker run` ?

`docker run` est la commande basique pour démarrer un container, mais elle
prend des dizaines d'options en ligne de commande (ports, volumes, env vars,
healthcheck, etc.). Imagine devoir taper :

```bash
docker run -d --name wourri_postgres_dev \
  --restart unless-stopped \
  -p 127.0.0.1:5433:5432 \
  -e POSTGRES_USER=wourri \
  -e POSTGRES_PASSWORD=wourri_dev_2026 \
  -e POSTGRES_DB=wourri_dev \
  -v pgdata_wourri:/var/lib/postgresql/data \
  -v $(pwd)/db-init:/docker-entrypoint-initdb.d:ro \
  --health-cmd "pg_isready -U wourri -d wourri_dev" \
  --health-interval 10s --health-timeout 5s \
  --health-retries 5 --health-start-period 30s \
  pgvector/pgvector:pg16
```

… à chaque fois. **Docker Compose** permet d'écrire cette config une fois pour
toutes dans un fichier YAML (`docker-compose.dev.yml`) et de lancer le tout
avec une simple commande :

```bash
docker compose -f docker-compose.dev.yml up -d
```

### Pour expliquer à un tiers (analogie)

> « Docker, c'est comme livrer un appartement déjà meublé clé en main au lieu de
> demander à chaque dev d'acheter et monter ses propres meubles IKEA. Quand un
> nouveau dev arrive, il ne perd pas 2 jours à installer PostgreSQL — il lance
> une commande, l'environnement est prêt, identique à celui des autres. »

---

## 3. Anatomie du `docker-compose.dev.yml` Wourri

Lecture commentée du fichier livré en Sprint F Phase A (PR #176, 2026-05-19) :

```yaml
# Wourri — Environnement de développement local
# ──────────────────────────────────────────────
# Usage standard :
#   docker compose -f docker-compose.dev.yml up -d

services:
  postgres:                          # 1. Nom logique du service
    image: pgvector/pgvector:pg16    # 2. Image officielle PostgreSQL 16 + pgvector
    container_name: wourri_postgres_dev  # 3. Nom du container (pour `docker exec`, logs…)
    restart: unless-stopped          # 4. Redémarre auto si crash (sauf si arrêté manuellement)

    # 5. Mapping de ports : "host:container"
    #    127.0.0.1: → bind localhost UNIQUEMENT (et non 0.0.0.0 par défaut)
    #    Pourquoi ? En télétravail (Wi-Fi café, hotspot), un bind 0.0.0.0
    #    rendrait Postgres accessible à toutes les machines du LAN avec un
    #    password potentiellement déjà publié dans `.env.example`.
    #    Port host 5433 (et non 5432) → évite le conflit avec une instance
    #    Postgres locale (pgAdmin, Laragon…).
    ports:
      - "127.0.0.1:5433:5432"

    # 6. Variables d'environnement lues par PostgreSQL au premier démarrage.
    #    Syntaxe ${VAR:-default} : lit VAR depuis .env, défaut sinon.
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-wourri}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-wourri_dev_2026}
      POSTGRES_DB: ${POSTGRES_DB:-wourri_dev}

    # 7. Volumes (deux entrées) :
    volumes:
      # 7a. Named volume Docker pour les données PostgreSQL.
      #     - "named volume" : géré par Docker, invisible dans `git status`
      #     - Survit aux `docker compose down` (sauf `down -v`)
      #     - Alternative écartée : bind mount (./pgdata:/var/lib/...) qui
      #       pollue le dossier projet et l'historique git.
      - pgdata_wourri:/var/lib/postgresql/data

      # 7b. Bind mount read-only des scripts d'initialisation.
      #     - PostgreSQL exécute automatiquement les .sql dans ce dossier
      #       AU PREMIER démarrage uniquement (mécanisme officiel
      #       docker-entrypoint-initdb.d).
      #     - `:ro` = read-only → le container ne peut pas modifier ces
      #       fichiers (protection contre une attaque ou un bug interne).
      - ./db-init:/docker-entrypoint-initdb.d:ro

    # 8. Healthcheck : Docker vérifie périodiquement que Postgres répond.
    healthcheck:
      # pg_isready : binaire officiel PostgreSQL qui retourne 0 si la BDD
      # accepte des connexions, !=0 sinon. Pas besoin de password.
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-wourri} -d ${POSTGRES_DB:-wourri_dev}"]
      interval: 10s      # check toutes les 10 secondes une fois démarré
      timeout: 5s        # le check doit répondre en < 5s sinon échec
      retries: 5         # 5 échecs consécutifs = container marqué unhealthy
      start_period: 30s  # 30s de grâce au démarrage (Docker Desktop Windows
                         # est plus lent qu'un Docker Linux natif)

volumes:
  # 9. Déclaration du named volume référencé en 7a.
  #    `name: pgdata_wourri` → préfixe explicite, évite collision avec d'autres
  #    projets Docker locaux (sinon Docker préfixe avec le nom du dossier).
  pgdata_wourri:
    name: pgdata_wourri
```

### Les 4 décisions de design importantes (à savoir expliquer)

1. **`pgvector/pgvector:pg16`** au lieu de `postgres:16` + extension manuelle
   → image officielle pré-buildée, tag figé, reproductible à 100 %.
2. **`127.0.0.1:5433:5432`** → bind localhost (sécurité réseau) + port 5433 (évite conflits).
3. **Named volume `pgdata_wourri`** → pas de pollution `git status`, géré par Docker.
4. **`start_period: 30s`** → tolérance Docker Desktop Windows (lent à démarrer).

---

## 4. Cycle de vie d'un container Postgres dev

### De `up -d` à `healthy`

```
┌──────────────────────────────────────────────────────────────────────┐
│ $ docker compose -f docker-compose.dev.yml up -d                      │
│                                                                       │
│   1. Docker lit le YAML, calcule ce qu'il faut faire                  │
│                                                                       │
│   2. Image absente localement ?                                       │
│      → Pull `pgvector/pgvector:pg16` depuis Docker Hub                │
│        (≈ 130 MB, peut être lent depuis CI / Wi-Fi instable)          │
│                                                                       │
│   3. Volume `pgdata_wourri` absent ?                                  │
│      → Création (volume vide)                                         │
│                                                                       │
│   4. Création du container `wourri_postgres_dev`                      │
│      - Mount `pgdata_wourri` sur /var/lib/postgresql/data             │
│      - Mount `./db-init` sur /docker-entrypoint-initdb.d (read-only)  │
│      - Configure les variables d'environnement                        │
│                                                                       │
│   5. Lancement du process PostgreSQL dans le container                │
│      a. PostgreSQL voit que /var/lib/postgresql/data est VIDE         │
│         → Phase d'initialisation :                                    │
│           - initdb (création du cluster)                              │
│           - création de l'utilisateur `wourri`                        │
│           - création de la base `wourri_dev`                          │
│      b. PostgreSQL voit les .sql dans /docker-entrypoint-initdb.d     │
│         → Exécute `init.sql` :                                        │
│              CREATE EXTENSION IF NOT EXISTS vector;                   │
│         L'extension pgvector est ACTIVÉE dans wourri_dev              │
│      c. PostgreSQL démarre normalement (accepte des connexions)       │
│                                                                       │
│   6. Healthcheck démarre (interval=10s, start_period=30s)             │
│      → `pg_isready -U wourri -d wourri_dev` doit retourner 0          │
│        - Container marqué `(health: starting)` pendant 30s            │
│        - Puis `(healthy)` dès que le check passe                      │
│                                                                       │
│   7. Container `Up X seconds (healthy)` — prêt à recevoir des         │
│      connexions depuis localhost:5433                                 │
└──────────────────────────────────────────────────────────────────────┘
```

### Ce qui se passe au DEUXIÈME `docker compose up -d`

L'initialisation (étape 5a + 5b) ne se rejoue PAS. PostgreSQL voit que
`/var/lib/postgresql/data` contient déjà les fichiers de l'initialisation
précédente → il démarre directement.

**Conséquence** : si tu modifies `db-init/init.sql` après le premier démarrage,
les changements ne seront PAS appliqués automatiquement. Pour les forcer :
```bash
docker compose -f docker-compose.dev.yml down -v
docker volume rm pgdata_wourri
docker compose -f docker-compose.dev.yml up -d
```

### Dépannage rapide

| Symptôme | Cause probable | Solution |
|---|---|---|
| `port is already allocated` | Autre instance Postgres écoute sur 5433 | `netstat -ano \| findstr :5433` (Windows) puis arrêter le concurrent |
| `Cannot connect to Docker daemon` | Docker Desktop pas démarré | Lancer Docker Desktop, attendre que l'icône systray dise « Engine running » |
| `(health: starting)` qui dure 60s+ | Premier démarrage lent | Patienter. `docker compose logs -f postgres` pour suivre |
| `type "vector" does not exist` | Volume hérité d'un démarrage sans `init.sql` | Reset complet (voir ci-dessus) |
| TLS handshake timeout | CDN Docker Hub instable depuis CI | Retry sous 1-3 jours — pattern projet observé en Sprint F Phase A |

---

## 5. Pourquoi PostgreSQL + pgvector (vs ChromaDB)

### Ce qu'on avait avant : ChromaDB

ChromaDB est une base vectorielle légère, écrite en Python. On l'utilisait
pour stocker les 162 entrées du corpus IVR (chaque entrée a un texte +
métadonnées + un vecteur d'embedding 384 dimensions calculé par
`paraphrase-multilingual-MiniLM-L12-v2`).

**Ce que faisait Chroma pour Wourri** :
- Stocker les 162 entrées avec leur vecteur
- Permettre la recherche par similarité cosine (« quelle entrée ressemble le
  plus à `intent=CONSEIL_PRODUCTION + culture=CULTURE_RIZ` ? »)

**Limites de ChromaDB pour Wourri** :

| Limite | Impact projet |
|---|---|
| **Embarqué dans le process Python** | Pas de partage entre instances, mémoire dupliquée à chaque worker |
| **Pas de SQL standard** | Impossible de joindre avec d'autres tables (feedback users, logs analytics, etc.) |
| **Observabilité limitée** | Pas de `EXPLAIN ANALYZE`, pas de monitoring standard |
| **Scalabilité** | Conçu pour < 1M vecteurs locaux ; au-delà → réécriture |
| **Backup/restore** | Pas de `pg_dump` équivalent → procédures custom |
| **Index figés** | Algorithme HNSW non paramétrable, pas d'alternative ivfflat |

### Ce vers quoi on va : PostgreSQL + pgvector

**PostgreSQL** est la BDD relationnelle de référence depuis 30 ans. Stable,
documentée, monitoring industriel, sauvegardes incrémentales, etc.

**pgvector** est une extension PostgreSQL qui ajoute :
- Un type de colonne `vector(N)` (vecteur de N dimensions)
- Trois opérateurs de distance : `<->` L2, `<=>` cosine, `<#>` produit scalaire
- Deux algorithmes d'index pour la recherche approximative :
  - **ivfflat** : partition en `lists` clusters, scan partiel (rapide, RAM)
  - **HNSW** : graph hiérarchique (plus rapide, plus RAM)

Wourri utilise **ivfflat avec cosine** (cf. chapitre 6 pour pourquoi `lists=10`).

### Pourquoi c'est mieux pour Wourri

| Bénéfice | Concrètement |
|---|---|
| **SQL standard** | Requêtes mixtes : `WHERE intent='...' AND cultures && ARRAY[...] ORDER BY embedding <=> :q` |
| **JOIN possibles** | Phase D : joindre `corpus_entries` avec `feedback_log` pour personnaliser |
| **GIN sur arrays** | Filtre rapide `cultures && ARRAY['CULTURE_RIZ', '*']` sans table de liaison |
| **FTS français natif** | `to_tsvector('french', reponse_fr)` → fallback texte si la recherche vectorielle ne match pas |
| **Observabilité** | `EXPLAIN ANALYZE`, `pg_stat_*`, métriques Prometheus, etc. |
| **Backup** | `pg_dump` → fichier SQL portable, restore en 1 commande |
| **Communauté** | 30 ans de tooling, partout en Afrique francophone et Asie |

### Pour expliquer à un sponsor technique

> « ChromaDB nous a permis de prototyper rapidement en 2025, mais c'est une
> base vectorielle de niche. PostgreSQL + pgvector est le combo standard en
> 2026 (Supabase, Anthropic, Stripe l'utilisent). On garde la même qualité de
> recherche sémantique tout en gagnant : capacité de scaler, possibilité de
> joindre avec d'autres données (feedback, analytics), backups standards,
> recrutement DBA facilité (toute personne qui connaît Postgres devient
> productive en 1 jour). C'est notre fondation infra pour les 5 prochaines
> années. »

---

## 6. Le schéma SQL (3 tables + 6 index)

Livré par Sprint F Phase B (PR #181, migration `alembic/versions/0001_create_corpus_schema.py`).

### Table 1 : `corpus_entries` (162 lignes)

C'est la table principale : une ligne par entrée IVR du corpus.

```sql
CREATE TABLE corpus_entries (
    id                  TEXT        PRIMARY KEY,
    intent              TEXT        NOT NULL,
    cultures            TEXT[]      NOT NULL DEFAULT ARRAY['*']::TEXT[],
    conditions          TEXT[]      NOT NULL DEFAULT ARRAY[]::TEXT[],
    reponse_bambara     TEXT        NOT NULL,
    reponse_fr          TEXT        NOT NULL DEFAULT '',
    score_validation    REAL        NOT NULL DEFAULT 0.5,
    tags                TEXT[]      NOT NULL DEFAULT ARRAY[]::TEXT[],
    source              TEXT        NOT NULL DEFAULT 'corpus_ivr',
    document_text       TEXT        NOT NULL,
    embedding           vector(384) NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Pourquoi chaque colonne ?**

| Colonne | Type | Rôle |
|---|---|---|
| `id` | TEXT PK | Ex. `agrumes_conseil_001`, identifiant stable lisible |
| `intent` | TEXT | Ex. `CONSEIL_PRODUCTION`, clé de routage |
| `cultures` | TEXT[] | Ex. `{CULTURE_RIZ, CULTURE_MAIS}`, filtre via opérateur GIN `&&` |
| `conditions` | TEXT[] | Ex. `{saison_pluie}`, scoring bonus +0.15 si saison courante |
| `reponse_bambara` | TEXT | Texte audio à retourner à l'agriculteur |
| `reponse_fr` | TEXT | Traduction française (UI admin + analytics) |
| `score_validation` | REAL | 0.5-1.0, qualité humaine de l'entrée |
| `tags` | TEXT[] | Métadonnées libres |
| `source` | TEXT | `corpus_ivr` (initial), `auto_validated` (feedback 👍) |
| `document_text` | TEXT | Texte combiné qui a servi à calculer `embedding` (cohérence Phase E) |
| `embedding` | **vector(384)** | Vecteur 384 dim, calculé par paraphrase-multilingual-MiniLM-L12-v2 |
| `created_at` / `updated_at` | TIMESTAMPTZ | Audit temporel |

### Table 2 : `corpus_phrases_attestees` (~157 lignes)

Relation 1:N avec `corpus_entries`. Une entrée peut avoir 0 à N phrases
bambara CI attestées (extraites des vidéos Access Agriculture, Common Voice
dyu, etc.). Ces phrases servent à enrichir le `document_text` qui calcule
l'embedding.

```sql
CREATE TABLE corpus_phrases_attestees (
    id         BIGSERIAL   PRIMARY KEY,
    entry_id   TEXT        NOT NULL
               REFERENCES corpus_entries(id)
               ON DELETE CASCADE,                    -- ← clé cascade
    text       TEXT        NOT NULL,
    source     TEXT        NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_corpus_phrases_attestees_entry_id
    ON corpus_phrases_attestees(entry_id);
```

**Pourquoi `ON DELETE CASCADE` ?** Si on supprime une entrée parent, ses
phrases attachées doivent disparaître automatiquement. Pas d'orphelins en
base.

### Table 3 : `corpus_metadata` (4 lignes)

Configuration clé/valeur — version du corpus, date d'import, etc.

```sql
CREATE TABLE corpus_metadata (
    key        TEXT        PRIMARY KEY,
    value      TEXT        NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Contenu actuel après import :
```
       key      |              value
----------------+----------------------------------
 entries_count  | 162
 imported_at    | 2026-05-19T15:07:34.016201+00:00
 source         | dictionnaires/corpus_ivr.json
 version        | 2.3
```

### Les 6 index sur `corpus_entries`

Chaque index existe pour une raison précise. Si on en supprime un, une requête
spécifique devient lente.

| Index | Type | Sert à |
|---|---|---|
| `corpus_entries_pkey` | B-tree (PK) | Lookup `WHERE id = '...'` |
| `ix_corpus_entries_intent` | B-tree | Lookup `WHERE intent = 'CONSEIL_PRODUCTION'` (cardinalité ≈ 30 valeurs distinctes) |
| `ix_corpus_entries_cultures` | **GIN** sur `TEXT[]` | `WHERE cultures && ARRAY['CULTURE_RIZ']::text[]` (opérateur overlap) |
| `ix_corpus_entries_conditions` | **GIN** sur `TEXT[]` | `WHERE conditions && ARRAY['saison_pluie']::text[]` |
| `ix_corpus_entries_reponse_fr_fts` | **GIN** FTS français | `WHERE to_tsvector('french', reponse_fr) @@ to_tsquery('français','plantation')` (fallback texte futur) |
| `ix_corpus_entries_embedding_ivfflat` | **ivfflat** cosine | `ORDER BY embedding <=> :query LIMIT 5` (cœur de la recherche sémantique) |

### Le piège ivfflat (leçon Phase C review)

Initialement on avait écrit `WITH (lists = 100)`. **Erreur** : pgvector exige
`rows >= lists × 3` pour que le planner utilise l'index. Avec 162 entrées et
`lists=100`, il faudrait au moins 300 entrées → planner ignorait l'index et
faisait du seqscan. **Fix** : `lists = 10` (seuil 30, atteint dès l'import).

**Règle pratique** : `lists ≈ rows / 1000`. Pour passer à 10k entrées :
toujours `lists=10`. Pour 100k+, recréer l'index avec `lists=100`.

### Schéma visuel des relations

```
┌─────────────────────────────────┐
│  corpus_metadata                │  (4 lignes)
│  - key (PK)                     │
│  - value, updated_at            │
└─────────────────────────────────┘

┌─────────────────────────────────┐         ┌─────────────────────────────────┐
│  corpus_entries (162 lignes)    │         │  corpus_phrases_attestees       │
│  ─ id (PK)                      │ 1     N │  (~157 lignes)                  │
│  ─ intent                       ├────────►│  ─ id (BIGSERIAL PK)            │
│  ─ cultures TEXT[]              │ ON DEL  │  ─ entry_id (FK)                │
│  ─ conditions TEXT[]            │ CASCADE │  ─ text                         │
│  ─ reponse_bambara              │         │  ─ source                       │
│  ─ reponse_fr                   │         │  ─ created_at                   │
│  ─ embedding vector(384) ◄──────┤         └─────────────────────────────────┘
│  ─ ... (10 colonnes au total)   │
└─────────────────────────────────┘
       │
       ▼ 6 index :
       PK btree • intent btree • cultures GIN • conditions GIN
       • reponse_fr FTS GIN • embedding ivfflat(cosine, lists=10)
```

---

## 7. Les 3 refontes Sprint F livrées 2026-05-19

Toute la migration ChromaDB → PostgreSQL+pgvector a été planifiée dans
**ADR-0008** (5 phases). Trois ont été livrées le même jour.

### Phase A — Provisionnement Docker + pgvector (PR #176, 11:38 UTC)

**Problème résolu** : on n'avait pas encore d'environnement PostgreSQL dev local
sur lequel construire la suite.

**Scope** : **purement additif**. Aucune ligne de code Python touchée.

**Fichiers livrés (4)** :
1. `docker-compose.dev.yml` — décrit le service `wourri_postgres_dev`
2. `db-init/init.sql` — `CREATE EXTENSION IF NOT EXISTS vector;`
3. `.env.example` — 5 variables `POSTGRES_*` documentées
4. `docs/dev-setup.md` — procédure complète pour un nouveau dev (< 10 min)

**Validation E2E** :
```bash
docker compose -f docker-compose.dev.yml up -d
# → wourri_postgres_dev (healthy) en ~1 minute
docker exec -it wourri_postgres_dev psql -U wourri -d wourri_dev \
  -c "SELECT '[1,2,3]'::vector;"
# → [1,2,3] retourné = extension active
```

**Décision sécurité importante (BLOCKER appliqué inline avant push)** : le port
host était initialement `5433:5432` → bind sur toutes les interfaces (`0.0.0.0`).
Le reviewer SÉCURITÉ a flagué : en télétravail (Wi-Fi café), n'importe quelle
machine du LAN aurait pu se connecter avec le password publié dans
`.env.example`. **Fix inline** : `127.0.0.1:5433:5432` → bind localhost uniquement.

### Phase B — Schéma SQL + Alembic + import 162 entrées (PR #181, 15:30 UTC)

**Problème résolu** : on avait l'infra Postgres mais aucune table applicative.

**Scope** : toujours **additif**. Aucun code prod n'utilise encore Postgres.

**Fichiers livrés (9)** :
1. `alembic.ini` + `alembic/env.py` + `alembic/script.py.mako` — config Alembic
2. `alembic/versions/0001_create_corpus_schema.py` — migration raw SQL (3 tables + 6 index + FK CASCADE)
3. `scripts/import_corpus_ivr.py` — import idempotent (TRUNCATE+INSERT) des 162 entrées + calcul de leurs embeddings
4. `tests/integration/test_corpus_schema.py` — 10 tests (schéma, idempotence, recherche cosine, intégrité référentielle)
5. `requirements.txt` — +5 deps : sqlalchemy, alembic, psycopg, pgvector, sentence-transformers
6. `app/config.py` — +`postgres_url: str = ""` (optionnel)
7. `.env.example` — driver passe à `postgresql+psycopg://`

**Workflow strict 4 phases** appliqué pour la 1re fois sur Phase B :
- **PLAN** (agent code-architect) → 6 décisions tranchées
- **CODE** → 9 fichiers ordonnés (deps → config → alembic → migration → smoke → script import → smoke → tests → régression)
- **REVIEW** → 4 agents parallèles (SÉCURITÉ, ARCHITECTURE, DRY/SOLID, TESTS), 0 BLOCKER, MAJORs convergents
- **SYNTHÈSE** → 5 FIX inline (lists=10 ivfflat, cross-refs `_resolve_url`, harmonisation `_EMBEDDING_DIM`, assertion défensive, test count phrases)

**Résultat** : 217/217 pytest verts (207 régression + 10 nouveaux). 162 entries + 157 phrases attestées + 4 metadata insérés. Recherche cosine validée (`agrumes_conseil_001 <=> self = 0.0000`).

### Phase C — Adapter + façade + feature flag (PR #185, 17:12 UTC)

**Problème résolu** : on avait les données en Postgres mais aucun code applicatif ne savait les lire. On voulait pouvoir basculer sans risque.

**Scope** : **première modification de code prod**. Le défi : zéro régression.

**Fichiers livrés (13)** :
1. `app/db/url_resolver.py` — extraction `_resolve_url()` au 4e consommateur (résout l'issue #180 backlogée)
2. `app/services/corpus_service.py` — adapter pgvector, 5 fonctions API **identiques** à `vdb_service.py`
3. `app/services/corpus_facade.py` — **router** chroma / dual / pgvector
4. `app/config.py` — `+corpus_storage_mode: Literal["chroma","dual","pgvector"] = "chroma"`
5. `app/services/chat_service.py` + `app/routers/feedback.py` + `app/main.py` — **TOUS les callers prod sous la façade**
6. `tests/unit/test_corpus_service.py` — 26 tests unitaires (mocks SQLAlchemy)
7. `tests/integration/test_corpus_facade.py` — 4 tests (routing 3 modes + 50 queries cohérence chroma↔pgvector ≥ 90 %)

**La façade — pourquoi c'est élégant** :

```python
# Quand chat_service appelle :
from app.services.corpus_facade import chercher_reponse_ivr
result = chercher_reponse_ivr(intent, cultures, conditions)

# La façade lit le feature flag :
mode = settings.corpus_storage_mode  # "chroma" par défaut

# Et route :
if mode == "pgvector":
    # 100% pgvector (Phase E future)
    return corpus_service.chercher_reponse_ivr(...)

# Sinon : Chroma autoritatif
result = vdb_service.chercher_reponse_ivr(...)

if mode == "dual":
    # Lance un thread daemon : compare pgvector silencieusement
    # et log les divergences. Phase D = validation terrain.
    threading.Thread(target=_compare_in_background, daemon=True).start()

return result
```

**Plan de rollback total** : `corpus_storage_mode=chroma` dans `.env` → restart. Effet immédiat.

**Workflow Phase 3 a sauvé un bug silencieux** : le reviewer ARCHITECTURE a détecté que `feedback.py` (lignes 67, 112) et `main.py` (ligne 114) importaient encore `vdb_service` directement → bypass de la façade en mode dual. **Sans ce review**, les feedbacks 👍 n'auraient JAMAIS alimenté le store pgvector pendant Phase D, faussant complètement la validation terrain. **Fix inline** : 3 imports → `corpus_facade`.

**6 autres MAJORs convergents** corrigés inline :
- Commentaire `document_text` trompeur → clarifié
- `normalize_embeddings=False` non documenté → commentaire + ref empirique
- `_safe_error(e)` créé pour masquer URL Postgres dans logs (anti-leak credentials)
- Assertion faible `get_reponse_fallback` BDD → assertion forte
- Essai 2 cascade wildcard non testé → 1 nouveau test
- `_postgres_reachable` dupliqué → cross-références + `engine.dispose()`

**Résultat final** : 247/247 pytest verts (mode chroma : zéro régression).

### Bilan : 3 phases en 9 heures de travail effectif

```
11:38 ────────────────► 15:30 ────────────────► 17:12
   │ Phase A (1h)         │ Phase B (4h)         │ Phase C (5h)
   │ Docker + pgvector    │ Alembic + import     │ Adapter + façade
   │ 4 fichiers infra     │ 9 fichiers           │ 13 fichiers
   │ 0 BLOCKER review     │ 0 BLOCKER + 5 FIX    │ 1 BLOCKER + 6 FIX
   │ 4/4 critères ADR     │ 5/5 critères ADR     │ 5/5 critères ADR
   │ 207 tests inchangés  │ 217 tests verts      │ 247 tests verts
```

### Pour expliquer à un sponsor (ATHARI, ARTCI, investisseur)

> « En une journée, on a fait 3 livraisons rigoureuses (chaque PR a un workflow
> de 4 phases : architecture, code, revue par 4 agents spécialisés, synthèse +
> merge) qui posent les fondations d'une migration BDD sans interruption de
> service. Aujourd'hui le code prod tourne toujours sur l'ancienne stack
> (ChromaDB) — la nouvelle (PostgreSQL+pgvector) est en place, testée à 247
> tests verts, mais s'active uniquement quand on bascule un feature flag.
> Phase D : on observera en staging pendant 3 à 7 jours pour confirmer que la
> nouvelle stack donne des résultats équivalents. Phase E : bascule complète
> et dépréciation de l'ancienne. À aucun moment on n'a interrompu le service
> existant. C'est l'approche industrielle. »

---

## 8. Cheatsheet et FAQ « pour expliquer à un tiers »

### Les 10 commandes à connaître par cœur

| Commande | Quand l'utiliser |
|---|---|
| `docker compose -f docker-compose.dev.yml up -d` | Démarrer Postgres dev |
| `docker compose -f docker-compose.dev.yml ps` | Vérifier que le container est `healthy` |
| `docker compose -f docker-compose.dev.yml logs -f postgres` | Suivre les logs en temps réel |
| `docker compose -f docker-compose.dev.yml down` | Arrêter (les données restent dans le volume) |
| `docker compose -f docker-compose.dev.yml down -v` | **Détruire** y compris les données (rare, à utiliser quand le volume est corrompu) |
| `docker exec -it wourri_postgres_dev psql -U wourri -d wourri_dev` | Ouvrir une console psql interactive |
| `docker exec wourri_postgres_dev psql -U wourri -d wourri_dev -c "SELECT count(*) FROM corpus_entries;"` | Compte rapide |
| `POSTGRES_URL=... python -m alembic upgrade head` | Appliquer toutes les migrations BDD |
| `POSTGRES_URL=... python scripts/import_corpus_ivr.py` | Importer/réimporter le corpus (idempotent) |
| `POSTGRES_URL=... python -m pytest` | Lancer toute la suite de tests (247 verts) |

### Les 5 commandes SQL utiles dans `psql`

```sql
-- Lister toutes les tables du schéma public
\dt

-- Voir la structure complète de corpus_entries (colonnes, index, FK)
\d corpus_entries

-- Compter les entrées
SELECT count(*) FROM corpus_entries;

-- Trouver les top 3 entrées les plus proches d'un vecteur de requête
WITH anchor AS (
  SELECT embedding FROM corpus_entries WHERE id = 'agrumes_conseil_001'
)
SELECT id, intent, (embedding <=> (SELECT embedding FROM anchor)) AS cos_dist
FROM corpus_entries
ORDER BY cos_dist
LIMIT 3;

-- Lister les entrées qui mentionnent la culture du riz
SELECT id, intent FROM corpus_entries
WHERE cultures && ARRAY['CULTURE_RIZ']::text[];
```

### FAQ pour expliquer à un tiers

#### Q1 : « Pourquoi un bot WhatsApp et pas une app dédiée ? »

> Les agriculteurs en CI/Mali ont WhatsApp Business sur leur téléphone, pas
> un app store ou des Mo de données pour télécharger une app dédiée. WhatsApp
> est déjà installé, gratuit avec leur forfait. On va à eux, pas l'inverse.

#### Q2 : « Pourquoi le bambara/dioula et pas le français ? »

> 70 % de la cible ne lit pas couramment le français. Quand un agriculteur
> reçoit un message vocal en dioula par WhatsApp, il l'écoute en marchant
> dans son champ. C'est ce qui change tout.

#### Q3 : « Pourquoi Docker plutôt qu'une vraie BDD installée sur serveur ? »

> En dev local, Docker garantit que tous les développeurs ont **exactement**
> le même environnement. En prod, on prévoit Postgres managé (Supabase, RDS,
> ou hébergé en CI sur Scaleway). L'image `pgvector/pgvector:pg16` reste la
> référence.

#### Q4 : « C'est quoi un vecteur, dimension 384 ? »

> Un vecteur, c'est une liste de 384 nombres décimaux qui représente le sens
> d'un texte. Deux textes proches sémantiquement (même sujet) ont des vecteurs
> proches géométriquement. Quand on veut trouver l'entrée du corpus la plus
> proche de « je plante du riz, je n'ai pas d'eau », on calcule le vecteur de
> cette phrase, on cherche le vecteur le plus proche dans la base, et on
> retourne la réponse associée. C'est la base de la recherche sémantique
> moderne.

#### Q5 : « Pourquoi ChromaDB d'abord, puis PostgreSQL ? »

> ChromaDB nous a permis de prototyper en quelques jours en 2025, avec un
> setup minimal. Mais c'est une base de niche, pas conçue pour scaler ou
> s'intégrer avec d'autres outils. PostgreSQL + pgvector est devenu le
> standard en 2026 (Supabase, OpenAI ChatGPT history, etc.). On migre de
> manière progressive avec un feature flag pour ne casser personne.

#### Q6 : « Et si Postgres tombe en panne ? »

> En mode `chroma` (défaut actuel), le service tourne entièrement sur ChromaDB
> embarqué. Postgres peut être down, le bot continue de répondre. En mode
> `dual` (Phase D), Postgres n'est utilisé qu'en background pour comparaison
> — sa panne ne dégrade pas les réponses. En mode `pgvector` (Phase E future),
> on aura un fallback applicatif vers ChromaDB le temps qu'on stabilise.

#### Q7 : « C'est vrai qu'on a livré 3 PRs en une journée ? Ce n'est pas du bricolage ? »

> Chacune des 3 PRs (`#176`, `#181`, `#185`) a suivi un workflow de 4 phases :
> (1) un agent code-architect dédié rédige un plan détaillé que je valide,
> (2) j'implémente dans l'ordre prescrit avec smokes après chaque étape,
> (3) 4 agents reviewers indépendants (SÉCURITÉ, ARCHITECTURE, DRY/SOLID, TESTS)
> auditent en parallèle, (4) je corrige inline tous les BLOCKERs et MAJORs
> avant de pusher. Les agents ont détecté plusieurs problèmes que j'avais
> manqués — dont 1 BLOCKER en Phase C qui aurait causé un bug silencieux en
> production. Ce n'est pas du bricolage, c'est de la méthodologie industrielle
> compressée par des outils IA.

#### Q8 : « Si je veux toucher au code, je commence par quoi ? »

> 1. Lire `CLAUDE.md` à la racine du projet (règles obligatoires)
> 2. Lire `docs/dev-setup.md` (setup environnement, 10 min)
> 3. Lire ce document (architecture)
> 4. Lire l'ADR pertinent dans `docs/adr/` selon le domaine que tu modifies
> 5. Créer une issue GitHub avec proposition de scope
> 6. Branche feature, code, PR, review, merge — comme dans les PRs du Sprint F

---

## Ressources externes

- **Documentation pgvector** : https://github.com/pgvector/pgvector
- **Documentation Docker Compose** : https://docs.docker.com/compose/
- **Documentation PostgreSQL 16** : https://www.postgresql.org/docs/16/
- **Documentation Alembic** : https://alembic.sqlalchemy.org/
- **ADR-0008 (migration Wourri ChromaDB → pgvector)** : [`docs/adr/0008-plan-migration-chromadb-pgvector.md`](adr/0008-plan-migration-chromadb-pgvector.md)
- **Procédure setup dev local** : [`docs/dev-setup.md`](dev-setup.md)

---

## Glossaire

| Terme | Définition |
|---|---|
| **ADR** | Architecture Decision Record — document de décision technique versionné |
| **Alembic** | Outil de migration BDD pour SQLAlchemy (équivalent Flyway/Liquibase) |
| **Cosine distance** | Distance entre deux vecteurs, `<=>` dans pgvector. 0 = identiques, 2 = opposés |
| **CRUD** | Create, Read, Update, Delete — les 4 opérations de base sur une BDD |
| **Embedding** | Vecteur numérique qui représente le sens d'un texte |
| **FastAPI** | Framework Python web moderne (équivalent Express/Spring) |
| **Feature flag** | Variable de configuration qui active/désactive une fonctionnalité sans rebuild |
| **FK** | Foreign Key — contrainte d'intégrité référentielle entre 2 tables |
| **FTS** | Full-Text Search — recherche plein texte (PostgreSQL natif) |
| **GIN** | Generalized Inverted Index — type d'index pour arrays / JSONB / FTS |
| **HNSW** | Hierarchical Navigable Small World — algorithme d'index vectoriel (alternative à ivfflat) |
| **Idempotent** | Une opération qui produit le même résultat même répétée N fois |
| **ivfflat** | Inverted File Flat — algorithme d'index vectoriel (le nôtre) |
| **NeMo** | Toolkit NVIDIA pour l'ASR (notre Soloni dyu) |
| **NLLB** | No Language Left Behind — modèle Meta de traduction multilingue |
| **NLU** | Natural Language Understanding — étape texte → intent + concepts |
| **pgvector** | Extension PostgreSQL pour stocker/rechercher des vecteurs |
| **psycopg** | Driver Python pour PostgreSQL (v3 = nouvelle génération) |
| **PR** | Pull Request GitHub |
| **SQLAlchemy** | ORM Python (notre couche d'abstraction BDD) |
| **TTS** | Text-to-Speech — texte → audio |

---

*Document créé le 2026-05-19 sur la base des PRs Sprint F Phase A/B/C (#176, #181, #185).*
*À mettre à jour quand Phase D ou Phase E sont livrées.*
