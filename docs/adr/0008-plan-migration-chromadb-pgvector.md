# ADR-0008 — Plan de migration ChromaDB → PostgreSQL + pgvector

**Statut** : complete
**Date** : 2026-05-05
**Auteur** : Claude (assistant)
**Valideur** : Ruben (validé le 2026-05-05)
**Exécute** : [ADR-0001](0001-choix-stockage-donnees.md)

---

## Contexte

### Origine

[ADR-0001](0001-choix-stockage-donnees.md) a été accepté le **2026-04-21** :
PostgreSQL + pgvector remplace ChromaDB. La décision technique est prise et
non rediscutée ici.

ADR-0001 mentionnait la rédaction d'un ADR séparé pour le plan d'exécution :

> *"Migration depuis ChromaDB → Plan à détailler dans un ADR-0002 séparé si
> l'Option A est validée"*

ADR-0002 a finalement servi pour Omnilingual ASR (autre sujet). Ce plan
devient donc **ADR-0008**, conformément à la numérotation chronologique.

### État actuel (2026-05-05)

ChromaDB est en production via [`app/services/vdb_service.py`](../../wouri-api/app/services/vdb_service.py)
(387 lignes). Caractéristiques observées :

- **Embedding model** : `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensions, local)
- **Persistence** : fichier local `data/chroma_ivr/`
- **Volume** : 162 entrées corpus IVR (v2.3, ~30 KB indexé)
- **Auto-sync** : recharge automatique sur changement de version corpus
  (via `.corpus_version` file)
- **Logique métier** : 3 essais en cascade (intent+culture exact, intent+wildcard,
  intent seul) + scoring saisonnier + scoring conditions
- **Fallback JSON** : déjà implémenté en cas d'indisponibilité Chroma
  (cf. MEMORY — *"Fallback JSON direct quand mémoire insuffisante (Windows page
  file + NeMo simultané)"*)
- **Bug rencontré** : `$contains→$eq` (résolu par patch dans le code)

### Pourquoi maintenant

1. **2 semaines de retard** depuis acceptation ADR-0001 (21 avril → 5 mai)
2. **Chaque jour de délai** ajoute du code Python couplé à l'API ChromaDB
   qu'il faudra démêler plus tard
3. **Autres ADR en attente** dépendent du choix storage tranché : ADR-0006
   (sessions WhatsApp Cloud), futurs ADR sur multi-tenant et billing
4. **Sprints actuels** : Phase 1+2 d'ADR-0003 viennent d'être livrées ; on est
   dans une fenêtre saine pour rédiger un plan de fond avant Phase 3

### Ce que ce plan PRODUIT

Un plan d'exécution **séquencé en phases atomiques** avec critères de sortie,
plan de rollback, et stratégie de validation terrain. **Ce plan ne réalise pas
la migration** — il l'organise. La migration effective fera l'objet d'un Sprint
dédié, hors scope de cet ADR.

---

## Questions tranchées avant la décision

1. **La décision technique pgvector est-elle toujours valide ?**
   → **Oui** (ADR-0001 accepté, pas remis en cause).

2. **Le provider Postgres est-il choisi (Supabase / Neon / RDS / self-hosted) ?**
   → **Non, hors scope de cet ADR.** Décision séparée à prendre après le MVP
   migration (Phase A peut tester sur 2 providers en parallèle si pertinent).

3. **Le modèle d'embedding change-t-il ?**
   → **Non dans ce plan.** On migre d'abord avec le même modèle
   (`paraphrase-multilingual-MiniLM-L12-v2`, 384 dims) pour isoler la variable.
   Le remplacement par un meilleur embedding multilingue sera un ADR séparé,
   conformément à ADR-0001 qui le mentionne explicitement.

4. **Faut-il une période de coexistence ChromaDB + pgvector ?**
   → **Oui.** Stratégie de double-écriture pendant Phase C-D pour validation
   terrain sans risque, comme déjà acté en ADR-0001.

5. **L'API publique (`chercher_reponse_ivr`, `ajouter_reponse_validee`) change-t-elle ?**
   → **Non.** Refactor isolé : on remplace l'implémentation de `vdb_service.py`
   par `corpus_service.py` mais les signatures publiques restent identiques.
   Les routers/services consommateurs ne changent pas.

6. **Faut-il un ORM (SQLAlchemy) ou des requêtes SQL brutes ?**
   → **À trancher en Phase B selon volume de code.** Recommandation par défaut :
   SQLAlchemy + Alembic (migrations versionnées) cohérent avec écosystème mature
   mentionné en ADR-0001.

---

## Stratégies de migration étudiées

### Option A — Big bang (rejetée)

- Couper ChromaDB, lancer pgvector, prier
- ❌ Impossible de rollback en prod sans downtime
- ❌ Pas de validation terrain comparative
- ❌ Tous les bugs sortent en même temps

### Option B — Phasée séquentielle sans coexistence (rejetée)

- Phase A → B → C → D : on remplace, on bascule, on supprime, sans double-écriture
- ❌ Pas de filet de sécurité après bascule
- ❌ Régressions silencieuses possibles (résultats légèrement différents)
- ❌ Rollback = restaurer un dump ChromaDB potentiellement obsolète

### Option C — Phasée avec double-écriture + feature flag (RETENUE)

- Phase A → E avec coexistence ChromaDB + pgvector pendant 2-3 phases
- Feature flag pour basculer les **lectures** progressivement
- Comparaison automatique des résultats Chroma vs pgvector sur queries réelles
- Rollback = flip du flag (instantané)
- ✅ Filet de sécurité maximal
- ✅ Validation terrain sur trafic réel
- ✅ Détection des régressions avant bascule définitive
- ⚠️ Coût : code de double-écriture temporaire à maintenir pendant ~2 sprints

**Décision** : Option C, conforme à ADR-0001 qui mentionne explicitement
*"Période de coexistence (feature flag) pour validation terrain"*.

---

## Plan d'exécution — 5 phases

### Phase A — Provisionnement environnement (1-2 jours)

**Objectif** : disposer d'un PostgreSQL + pgvector fonctionnel en dev local et
en staging, prêt à recevoir le schéma.

**Tâches** :

1. Créer un fichier `docker-compose.dev.yml` avec service `postgres:16` +
   image `pgvector/pgvector:pg16` pour le dev local
2. Documenter dans `docs/dev-setup.md` la procédure de démarrage
   (`docker compose up -d postgres`)
3. Choisir un provider managed pour staging :
   - **Recommandation par défaut** : Supabase EU (Frankfurt) — free tier 500 MB,
     hébergement EU compatible souveraineté ADR-0001
   - **Alternative** : Neon EU (Frankfurt), Railway, ou self-hosted VPS
   - **Décision finale** différée à un ADR séparé (hors scope ici)
4. Activer l'extension pgvector : `CREATE EXTENSION IF NOT EXISTS vector;`
5. Créer un compte service applicatif avec rôle dédié (privileges minimum)
6. Variables `.env` à ajouter : `POSTGRES_URL`, `POSTGRES_VECTOR_DIM=384`

**Critère de sortie** :

- [ ] `docker compose up -d postgres` démarre un Postgres+pgvector en local
- [ ] `psql -c "SELECT '[1,2,3]'::vector;"` retourne un vecteur (extension active)
- [ ] Variables `.env.example` documentées
- [ ] Doc `docs/dev-setup.md` reproduit en < 10 min par un nouvel intervenant

**Plan de rollback** : aucun — Phase A est purement additive (n'altère pas
le code prod).

---

### Phase B — Schéma SQL + migrations versionnées (1-2 jours)

**Objectif** : disposer d'un schéma SQL versionné capable d'accueillir le
corpus IVR avec sa logique métier (intent, cultures, conditions, scoring,
phrases attestées).

**Tâches** :

1. Choisir l'outil de migrations : **Alembic** par défaut (cohérent SQLAlchemy)
2. Créer la migration initiale `0001_create_corpus_schema.sql` :

```sql
-- Extension pgvector (doit être activée par le DBA en amont)
CREATE EXTENSION IF NOT EXISTS vector;

-- Table principale : entrées du corpus IVR
CREATE TABLE corpus_entries (
    id              TEXT PRIMARY KEY,
    intent          TEXT NOT NULL,
    cultures        TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    conditions      TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    reponse_bambara TEXT NOT NULL,
    reponse_fr      TEXT,
    score_validation NUMERIC(3,2) NOT NULL DEFAULT 0.5
        CHECK (score_validation >= 0.0 AND score_validation <= 1.0),
    source          TEXT NOT NULL DEFAULT 'corpus_ivr',
    tags            TEXT[] DEFAULT ARRAY[]::TEXT[],
    document_text   TEXT NOT NULL,
    embedding       VECTOR(384) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index pour les filtres fréquents
CREATE INDEX corpus_intent_idx ON corpus_entries (intent);
CREATE INDEX corpus_cultures_gin ON corpus_entries USING GIN (cultures);
CREATE INDEX corpus_conditions_gin ON corpus_entries USING GIN (conditions);

-- Index vectoriel (à recréer après import volumineux pour performance)
CREATE INDEX corpus_embedding_ivfflat ON corpus_entries
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Index full-text search (BM25 fallback ou complément)
CREATE INDEX corpus_doc_fts_idx ON corpus_entries
    USING GIN (to_tsvector('french', document_text));

-- Phrases attestées (1-N par entrée)
CREATE TABLE corpus_phrases_attestees (
    id        BIGSERIAL PRIMARY KEY,
    entry_id  TEXT NOT NULL REFERENCES corpus_entries(id) ON DELETE CASCADE,
    text      TEXT NOT NULL,
    source    TEXT
);

CREATE INDEX corpus_phrases_entry_idx ON corpus_phrases_attestees (entry_id);

-- Métadonnées du corpus (version, dates, etc.)
CREATE TABLE corpus_metadata (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

3. Créer un script Python `scripts/import_corpus_ivr.py` qui :
   - Lit `dictionnaires/corpus_ivr.json`
   - Calcule l'embedding de chaque entrée via le même modèle qu'aujourd'hui
   - INSERT dans `corpus_entries` + `corpus_phrases_attestees`
   - Met à jour `corpus_metadata.version` avec la valeur du JSON
4. Tests unitaires `tests/integration/test_corpus_schema.py` (avec `pytest-postgresql`
   ou container éphémère) :
   - Création tables OK
   - Insertion / lecture corpus OK
   - Index vectoriel utilisé (`EXPLAIN ANALYZE` retourne `Index Scan`)

**Critère de sortie** :

- [ ] `alembic upgrade head` crée le schéma sans erreur
- [ ] `python scripts/import_corpus_ivr.py` importe les 162 entrées
- [ ] `SELECT count(*) FROM corpus_entries;` retourne 162
- [ ] Recherche vectorielle de base fonctionne (`SELECT id FROM corpus_entries
      ORDER BY embedding <=> '[...]'::vector LIMIT 5;`)
- [ ] Tests d'intégration passent

**Plan de rollback** : `alembic downgrade base` supprime le schéma. Aucun
impact sur le code prod (qui utilise toujours ChromaDB).

---

### Phase C — Adapter `corpus_service.py` + double-écriture (2-3 jours)

**Objectif** : créer un nouveau service Python avec API **strictement compatible**
avec l'actuel `vdb_service.py`, qui peut être activé/désactivé via feature flag.

**Tâches** :

1. Créer `app/services/corpus_service.py` avec les fonctions publiques :
   - `chercher_reponse_ivr(intent, cultures, conditions=None) -> dict | None`
   - `ajouter_reponse_validee(...) -> bool`
   - `get_reponse_fallback() -> str`
   - `get_phrases_for_intent(intent, cultures) -> list[dict]`
   - `initialiser_vdb()` — équivalent de l'init au démarrage
2. Implémentation reproduisant la **logique métier identique** à `vdb_service.py` :
   - 3 essais en cascade (intent+culture exact, intent+wildcard, intent seul)
   - Scoring `_best_result()` avec bonus saison + conditions
   - Tous les logs `[VDB-PG]` (préfixe distinct pour observabilité)
3. Implémentation de l'écriture vers `corpus_entries` (compatibilité avec
   `ajouter_reponse_validee`)
4. Tests unitaires `tests/unit/test_corpus_service.py` reproduisant les mêmes
   cas que les tests ChromaDB existants
5. Feature flag dans `app/config.py` :
   ```python
   # Feature flag : bascule storage corpus
   # "chroma" = legacy ChromaDB (vdb_service.py)
   # "pgvector" = nouveau PostgreSQL+pgvector (corpus_service.py)
   # "dual" = double-écriture + lecture comparative (Phase C-D)
   corpus_storage_mode: str = "chroma"
   ```
6. **Wrapper de double-écriture** : créer un `corpus_facade.py` qui :
   - En mode `"chroma"` : délègue 100% à `vdb_service.py` (comportement actuel)
   - En mode `"dual"` : écrit dans les **deux** stores, lit Chroma (autoritatif),
     mais lit aussi pgvector et **compare en background** (logs si différence)
   - En mode `"pgvector"` : délègue 100% à `corpus_service.py`
7. Modifier les **2-3 callers** (`chat_service.py`, peut-être `routers/`) pour
   appeler `corpus_facade` au lieu de `vdb_service` directement

**Critère de sortie** :

- [ ] `corpus_service.py` passe les mêmes tests que `vdb_service.py` (mêmes
      cas, même API)
- [ ] `corpus_facade.py` route correctement selon `corpus_storage_mode`
- [ ] Mode `"chroma"` ne change rien au comportement actuel
- [ ] Mode `"dual"` log les divergences mais retourne le résultat Chroma
- [ ] Tests d'intégration : 50 queries du corpus retournent le même `id`
      en mode chroma vs pgvector

**Plan de rollback** : flip `corpus_storage_mode` à `"chroma"` dans `.env`.
Effet immédiat au prochain restart.

---

### Phase D — Validation terrain en mode dual (3-7 jours)

**Objectif** : laisser tourner le mode `"dual"` en staging (puis prod si OK)
pendant 3-7 jours pour collecter des divergences réelles avant de basculer.

**Tâches** :

1. Activer `corpus_storage_mode=dual` en staging
2. Créer un endpoint `/admin/corpus-divergence-report` qui retourne :
   - Nombre total de queries comparées
   - Nombre de divergences détectées (résultat différent)
   - Top 10 des divergences avec query, résultat Chroma, résultat pgvector
3. Analyser les divergences :
   - **Acceptable** : ordre de résultat différent mais score équivalent
   - **À investiguer** : résultat différent OU absence dans un seul store
4. Itérer sur `corpus_service.py` jusqu'à ce que les divergences soient < 5%
   et expliquées (ex: indexation différente sur les diacritiques)
5. Si divergence > 5% ou bug bloquant → **Phase D échoue**, rollback (flag = `chroma`)

**Critère de sortie** :

- [ ] Mode `dual` actif en staging pendant ≥ 3 jours
- [ ] ≥ 100 queries réelles comparées
- [ ] Divergences résiduelles < 5% et toutes documentées
- [ ] Aucune divergence "absence" (un store retourne, l'autre pas, sur même query)
- [ ] Latence pgvector ≤ latence ChromaDB + 50% (mesure sur P95)

**Plan de rollback** : flip flag à `"chroma"`. Le code Chroma continue de
fonctionner sans interruption.

---

### Phase E — Bascule + déprécation ChromaDB (1-2 jours)

**Objectif** : faire de pgvector le store unique, supprimer le code ChromaDB.

**Tâches (uniquement si Phase D PASS)** :

1. Flip `corpus_storage_mode=pgvector` en staging pendant 24h → confirmer
   absence de régression
2. Flip `corpus_storage_mode=pgvector` en prod
3. Surveillance 48h des métriques + logs d'erreur
4. Si stable :
   - Suppression de `app/services/vdb_service.py`
   - Suppression de `app/services/corpus_facade.py` (devenu identité)
   - Renommer `corpus_storage_mode` → soft-deprecation puis suppression
   - Suppression dépendance `chromadb` dans `requirements.txt`
   - Suppression du dossier `data/chroma_ivr/` (après backup)
   - Mise à jour de `MEMORY.md` (section "Fichiers clés")
   - ADR-0008 statut → `complété`

**Critère de sortie** :

- [ ] `corpus_storage_mode=pgvector` en prod depuis ≥ 7 jours sans incident
- [ ] `grep -r "import chromadb" app/` retourne zéro résultat
- [ ] `pip show chromadb` retourne "not found"
- [ ] Tests existants passent (smoke test prod)
- [ ] Backup ChromaDB archivé hors prod (au cas où)

**Plan de rollback** : `git revert` du flip + réinstaller chromadb. Possible
pendant ~30 jours après la suppression du code, après quoi on commit
la rupture.

---

## Schéma SQL final (rappel concentré)

```
corpus_entries
├── id (PK)
├── intent
├── cultures (TEXT[])
├── conditions (TEXT[])
├── reponse_bambara
├── reponse_fr
├── score_validation
├── source
├── tags (TEXT[])
├── document_text
├── embedding (VECTOR(384))
├── created_at
└── updated_at

corpus_phrases_attestees
├── id (PK)
├── entry_id (FK → corpus_entries.id)
├── text
└── source

corpus_metadata
├── key (PK)
├── value
└── updated_at
```

---

## Risques et mitigations

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| Divergence résultats Chroma vs pgvector | **Élevée** | Moyen | Phase D dédiée, seuil < 5% |
| Latence pgvector dégradée vs Chroma local | Faible | Moyen | Index ivfflat tuné, monitoring P95 |
| Dette de double-écriture qui traîne | Moyenne | Faible | Phase E forcée après validation D, revue à 30 j |
| Bug d'embedding (ordre bytes différent) | Faible | Élevé | Tests d'intégration sur même 50 queries |
| Provider Postgres choisi trop tôt | Faible | Faible | Décision différée, Phase A teste localement d'abord |
| Migrations Alembic qui plantent | Faible | Moyen | Tests sur container éphémère avant staging |

---

## Conséquences

### Positives

- **Stack unifiée** : un seul store pour corpus IVR + futurs profils utilisateurs +
  billing + sessions WhatsApp + RAG documents (cf. ADR-0001)
- **Multi-tenant débloqué** : le row-level security PostgreSQL natif devient
  utilisable
- **Backup/réplication** : outils PG standard, plus de dépendance au fichier local
- **Filtres avancés** : SQL `WHERE` riche permet plus que les filtres `$eq` Chroma
- **Évolution embedding facile** : changement du modèle = nouvelle colonne
  embedding + recalcul, sans refactor du store
- **Pas de verrou vendor** : SQL standard, migration possible vers tout PG

### Négatives assumées

- **Coût ops** : un service Postgres à monitorer (vs fichier local Chroma)
- **Coût hosting** : ~25-100 €/mois selon provider (vs 0 € local Chroma).
  Mitigation : free tier Supabase/Neon couvre largement le volume actuel
- **Période de double-écriture** : ~1-2 semaines de code temporaire à maintenir
- **Apprentissage SQLAlchemy/Alembic** : si pas déjà maîtrisé. Mitigation :
  templates standards, migrations versionnées comme protection

### Migration / travail induit

- Nouveau service `app/services/corpus_service.py` (~300-400 lignes)
- Nouveau facade `app/services/corpus_facade.py` (~80 lignes, supprimé en Phase E)
- Migrations Alembic dans `alembic/versions/`
- Script `scripts/import_corpus_ivr.py`
- Tests `tests/unit/test_corpus_service.py` + `tests/integration/test_corpus_schema.py`
- Modification `app/config.py` : 1 setting (supprimé en Phase E)
- Modification `requirements.txt` : `+sqlalchemy`, `+alembic`, `+psycopg[binary]`,
  `+pgvector` ; `-chromadb` (en Phase E)
- Modification 2-3 callers (`chat_service.py`, peut-être `routers/`)
- Documentation `docs/dev-setup.md` (nouvelle section Postgres)

### Verrous futurs

- **Dépendance PostgreSQL** : standard industrie, très faible verrou
- **Dépendance pgvector** : extension active, alternative `Qdrant + PG`
  envisageable si pgvector explose à >10M vecteurs (cf. ADR-0001)
- **Dépendance SQLAlchemy/Alembic** : outils standards Python, alternatives
  triviales (asyncpg + sqlmigrate)

---

## Hors scope de cet ADR

- **Choix du provider Postgres managed** (Supabase vs Neon vs RDS vs self-hosted)
  → ADR séparé après validation MVP (Phase A peut tester en local d'abord)
- **Choix du modèle d'embedding pour 50 langues** → ADR séparé
  (mentionné explicitement par ADR-0001 section "Question d'embedding")
- **Schéma multi-tenant complet** (tables `users`, `tenants`, `subscriptions`)
  → cet ADR cible uniquement le corpus IVR ; le schéma multi-tenant fera
  l'objet d'un ADR dédié quand le besoin sera concret
- **Migration des historiques conversationnels** → pas de stockage actuel,
  donc rien à migrer ; futur sujet
- **Implémentation effective** : ce plan organise, ne réalise pas. La migration
  fera l'objet d'un Sprint dédié avec branches `feat/pgvector-phase-X`

---

## Estimation totale

- **Optimiste** (toolchain OK, pas de divergence) : 8-10 jours calendaires
- **Réaliste** : 12-15 jours
- **Pessimiste** (divergences importantes Phase D, optimisation requise) : 20-25 jours

Ces durées seront affinées à l'ouverture du Sprint d'exécution.

---

## Critères de décision globaux (PASS / FAIL pour chaque phase)

| Phase | Critère PASS | Décision si FAIL |
|---|---|---|
| A | Postgres+pgvector démarre en local | Re-explorer provider, ne PAS bloquer |
| B | 162 entrées importées + recherche vectorielle OK | Investiguer schéma, possible refactor |
| C | API compatible + tests passent | Bug provider PG ou logique métier mal portée → fix |
| D | Divergences < 5% en 3-7 j staging | Re-itérer Phase C OU rollback ADR si bloquant |
| E | Prod stable 7 j post-bascule | Rollback flag, garder Chroma actif |

**Point de non-retour** : Phase E terminée + 30 jours de prod stable sur
pgvector seul. Avant cela, le code Chroma reste récupérable via `git revert`.

---

## Références

- [ADR-0001 — Choix stockage (accepté 2026-04-21)](0001-choix-stockage-donnees.md)
- [`app/services/vdb_service.py`](../../wouri-api/app/services/vdb_service.py) — implémentation actuelle
- [`dictionnaires/corpus_ivr.json`](../../wouri-api/dictionnaires/corpus_ivr.json) — corpus à migrer (162 entrées)
- pgvector docs : https://github.com/pgvector/pgvector
- Alembic docs : https://alembic.sqlalchemy.org/
- Supabase EU : https://supabase.com/docs/guides/platform/regions
- Neon : https://neon.tech/
- ADR-0001 historique du choix
- [docs/vision.md](../vision.md) — contraintes projet (50+ langues, multi-tenant, GDPR-like)
- [Plan d'action 2026-04](../PLAN_ACTION_2026-04.md) — actions consolidées

---

## Historique

- **2026-05-05 (rédaction)** : ADR-0008 rédigé. Statut : **proposé**, attend validation Ruben.
  Reprend le plan évoqué dans ADR-0001 et le structure en 5 phases atomiques
  avec critères de sortie et plan de rollback.
- **2026-05-05 (acceptation)** : Ruben valide le plan. Statut basculé à **accepté**.
  Exécution effective différée à un Sprint dédié (à planifier). Phase A peut
  démarrer dès que l'environnement Postgres+pgvector dev local est provisionné.
- ADR-0001 mentionnait initialement "ADR-0002 séparé" pour ce plan.
  ADR-0002 ayant servi pour Omnilingual ASR, le plan migration storage
  prend la prochaine référence libre = **0008**.
- **2026-08-09 (Phase E terminée, #203)** : statut basculé à **complete**.
  Bascule pgvector effectuée AVANT staging (écart au plan assumé et motivé) :
  chromadb s'est révélé CASSÉ avec numpy 2.x (`np.float_ removed`, reproduit) —
  le mode chroma ne chargeait plus le corpus et le mode dual aurait servi None
  sur toutes les recherches. Décision Ruben (« chroma n'est plus nécessaire on
  balance sur pgvector », 2026-08-08) + validation fonctionnelle réelle
  (source=ivr_exact prouvé en local, #354). Étape 1 de #203 (mesure latence
  dual ≥7j staging) rendue impossible et sans objet : il n'y avait plus
  d'alternative à comparer. Livré : suppression vdb_service.py, corpus_facade.py
  (les consommateurs pointent corpus_service), endpoint /admin/corpus-divergence-report,
  scripts/phase_d_load_test.py, flag corpus_storage_mode, dépendance chromadb.
  La table corpus_divergences reste en base (données historiques, coût nul).
  data/chroma_ivr/ : suppression manuelle laissée à l'opérateur.
