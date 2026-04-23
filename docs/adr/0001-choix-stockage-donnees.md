# ADR-0001 — Choix du système de stockage de données

**Statut** : accepté
**Date** : 2026-04-21
**Auteur** : Claude (assistant) + validation Ruben
**Valideur** : Ruben (validé le 2026-04-21)

---

## Contexte

### Origine

En début de projet (phase MVP), ChromaDB a été choisi comme stockage principal
pour le corpus IVR agricole (162 entrées bambara/dioula). Voir
[app/services/vdb_service.py](../../wouri-api/app/services/vdb_service.py).

Ce choix a été fait **sans ADR**, basé sur un raisonnement tactique "ça marche
pour 162 entrées, facile à setup, local". Il s'agit donc d'un ADR rétrospectif
doublé d'une décision nouvelle.

### Ce qui a changé / remis en cause

Lors d'une revue d'architecture le 2026-04-21, les contraintes réelles du projet
ont été explicitées pour la première fois et formalisées dans
[docs/vision.md](../vision.md) :

- **Horizon 50+ langues africaines** avec phasage validé :
  P1 dioula CI → P2 +baoulé/bété/agni → P3 langues CI restantes + bambara Mali
  → P4 Afrique de l'Ouest → P5 50+.
- **Utilisateurs** : agriculteurs individuels + coopératives + ONGs + gouvernements.
- **Modèle économique payant** (B2C + B2B coopératives + B2G ONG) →
  **multi-tenant obligatoire**, billing, auth téléphone + OTP, row-level security.
- **Canal principal actuel** : WhatsApp voice. **IVR téléphonique** à horizon
  2-3 ans (pas immédiat, mais l'architecture doit pouvoir l'absorber).
- **Free-form queries** à terme (question agricole quelconque hors catalogue).
- **RAG sur documents longs** (ANADER/CGIAR/ICRISAT) à horizon P2-P3.
- **Personnalisation utilisateur** : profil, zone géographique, cultures déclarées,
  historique conversationnel, parcours dans le temps.
- **Hosting** cloud VPS **Europe ou Afrique** (jamais US). Posture
  **GDPR-like dès P1** validée (chiffrement, consentement, droit à l'effacement,
  localisation des données).
- **Équipe** : solo actuellement, équipe à moyen terme → stack **standard**,
  documentée, onboardable.
- **Non-négociable absolu** : qualité, jamais sacrifiée même temporairement.
  Approche par **phases** avec budget qui grandit proportionnellement aux
  utilisateurs payants — pas de sacrifice, juste un séquençage.

Ces contraintes changent radicalement l'analyse : on n'est plus sur un MVP
mais sur un système de production multilingue avec semantic search + RAG
+ personnalisation utilisateur + multi-tenant.

### Pourquoi ChromaDB ne tient plus face à ces contraintes

1. **Modèle d'embedding** : `paraphrase-multilingual-MiniLM-L12-v2` couvre mal
   les langues africaines basse-ressource (bambara, dioula, wolof, peul, baoulé…).
   Le rappel sémantique sera médiocre sur 50 langues.
2. **Scale** : 50 langues × centaines d'entrées + PDFs chunkés = 500k–1M+
   vecteurs. ChromaDB souffre au-delà de ~1M.
3. **Filtres structurés** : actuellement les 3 essais dans `vdb_service.py`
   utilisent d'abord des filtres `$eq` stricts. Un SQL relationnel ferait
   ça mieux et plus vite.
4. **Personnalisation utilisateur** : profils, historiques, zones → schéma
   relationnel. ChromaDB n'est pas fait pour ça.
5. **Ops production** : fichier local = pas de backup distribué, pas de
   réplication, pas de monitoring standard.
6. **Billing multi-tenant** (ONG + coopératives + individuel) : exige un
   modèle de données relationnel strict.

---

## Questions posées avant la décision

Extrait du transcript 2026-04-21 :

1. Le pipeline produit-il toujours `intent+culture` structuré ?
   → **Actuellement oui, mais ce n'est pas le but recherché** (free-form à terme).
2. Combien de langues prévues ?
   → **50+** langues africaines, **phasage graduel validé** (P1 dioula CI → P5 50+).
3. Docs longs à intégrer ?
   → **Fort probable à l'avenir** (ANADER/CGIAR/ICRISAT).
4. Modèle économique ?
   → **Payant** par ONG + coopératives + individuel.
5. Canal ?
   → WhatsApp vocal maintenant. **IVR téléphonique horizon 2-3 ans**
   (pas immédiat, architecture doit l'absorber sans réécriture).
6. Conseil personnalisé ?
   → **Oui**, par zone + historique + futur parcours utilisateur.
7. Hosting ?
   → Cloud VPS **Europe ou Afrique** (jamais US).
8. Souveraineté / GDPR ?
   → **Posture GDPR-like dès P1 validée** — chiffrement, consentement,
   droit à l'effacement, localisation EU/AF.
9. Équipe ?
   → Solo maintenant, équipe à moyen terme → stack standard obligatoire.
10. Non-négociables ?
    → **Qualité, toujours**. Approche par phases, pas de sacrifice.

---

## Options étudiées

### Option A — PostgreSQL + pgvector

**Description** : PostgreSQL (relationnel) avec l'extension pgvector pour la
recherche sémantique. Un seul store, un seul langage (SQL).

**Avantages** :
- Relationnel natif (users, profils, billing, historique, sessions)
- Vector search intégré → filtres structurés + similarité dans la même query
- Scale testé production à des milliards de lignes, centaines de millions de vecteurs
- Standard SQL, migrations Flyway/Alembic, écosystème mature
- Portable (Neon, Supabase, AWS RDS, Azure, self-hosted identique)
- Backup/réplication/monitoring = outils PostgreSQL standard

**Inconvénients** :
- pgvector moins rapide sur benchmarks vs Qdrant à scale très élevée (>10M vecteurs)
- Nécessite gestion serveur PostgreSQL (cloud managed disponibles)

**Coût** :
- Neon / Supabase / Railway : gratuit jusqu'à 500 MB–1 GB, puis ~25 €/mois pour
  commencer. Scale vers 100 €/mois à quelques GB.
- Self-hosted VPS : un pg serveur tient sur 4 GB RAM jusqu'à volumes significatifs.

**Compatibilité contraintes** :
- ✅ Multi-tenant (ONG/coop/individu) — row-level security PG native
- ✅ Multi-langue (colonne `language`)
- ✅ Free-form queries (vector search + full-text search FTS intégrés)
- ✅ RAG docs longs (chunks + métadata)
- ✅ Conseil personnalisé (profils utilisateurs = SQL standard)
- ✅ GDPR (PG supporte chiffrement at-rest, audit log, soft-delete)

---

### Option B — Pinecone (vector DB managed)

**Description** : Pinecone pour le vector search, PostgreSQL ou SQLite à côté
pour le relationnel.

**Avantages** :
- Zéro ops vector side (managed, déjà dans ton MCP)
- Très rapide à scale
- Démarrage immédiat

**Inconvénients** :
- **Deux stores à maintenir** (Pinecone + relationnel) → double opération de
  cohérence, migrations duales, risque de désync
- Coût devient significatif à scale : ~70 €/mois pour ~1M vecteurs p1-x1,
  ~300 €/mois pour 5M
- Verrou vendor (Pinecone = closed source, API propriétaire)
- Pas de filtrage relationnel sur vector (filtres plat uniquement)
- Hosting US/EU uniquement (pas d'option Afrique)

**Coût** :
- Free tier : 100k vecteurs, 2 index
- Standard : 70 €/mois pour 1 M vecteurs

**Compatibilité contraintes** :
- ⚠️ Souveraineté données : hosting US/EU
- ✅ Scale
- ❌ Architecture duale complexifie billing/tenant

---

### Option C — Qdrant (self-hosted ou cloud)

**Description** : Qdrant en Rust, self-hosted dans un container ou Qdrant Cloud.
PostgreSQL à côté pour le relationnel (même contrainte duale que Pinecone).

**Avantages** :
- Performances supérieures à pgvector à très grande échelle
- Rich filtering natif
- Open-source (self-hostable)
- Free tier cloud généreux (1 GB)

**Inconvénients** :
- Même contrainte duale Pinecone (deux stores à synchroniser)
- Écosystème plus petit que PG
- Self-hosted = ops supplémentaire

**Coût** :
- Cloud : gratuit jusqu'à 1 GB, puis ~25 €/mois
- Self-hosted : inclus dans le VPS

**Compatibilité contraintes** : similaire Pinecone.

---

### Option D — SQLite + sqlite-vec (extension)

**Description** : SQLite avec l'extension `sqlite-vec` pour recherche vectorielle.
Zéro serveur, fichier local, comme ChromaDB aujourd'hui mais avec SQL.

**Avantages** :
- Zéro infrastructure, fichier portable
- SQL standard → migration vers PostgreSQL triviale le jour où on scale
- Excellent pour MVP et dev local

**Inconvénients** :
- Pas multi-user concurrent fort
- Scale limité à quelques millions de vecteurs max avant souffrance
- Réplication/backup à scripter soi-même

**Compatibilité contraintes** :
- ❌ Multi-tenant production — SQLite en écriture concurrente est fragile
- ⚠️ Scale 50 langues + docs : proche de la limite
- ✅ Dev local / tests / cache de modèles

---

## Comparatif

| Critère | A. pgvector | B. Pinecone + PG | C. Qdrant + PG | D. SQLite+vec |
|---|---|---|---|---|
| Stack unifiée | ✅ un seul store | ❌ deux stores | ❌ deux stores | ✅ un seul store |
| Scale production 50 langues + RAG | ✅ testé à échelle | ✅ excellent | ✅ excellent | ⚠️ limité |
| Coût à démarrage | Gratuit (Neon) | Gratuit (free tier) | Gratuit (cloud free) | Gratuit |
| Coût à scale (1M vecteurs) | ~50–100 €/mois | ~70 €/mois vec + PG | ~25 €/mois vec + PG | N/A |
| Ops overhead | Moyen | Faible | Moyen | Nul |
| Verrou vendor | Faible | **Élevé** | Faible | Nul |
| Souveraineté (EU/AF) | ✅ | ❌ US/EU only | ✅ | ✅ |
| Maturité multi-tenant | ✅ natif | ⚠️ bricolage | ⚠️ bricolage | ❌ |
| Intégration personnalisation | ✅ relationnel natif | ❌ externe | ❌ externe | ✅ relationnel natif |
| Migration future | SQL standard | Export custom | Snapshot Qdrant | SQL standard |

---

## Décision

**Option retenue** : **Option A — PostgreSQL + pgvector** (validée par Ruben le 2026-04-21).

**Justification** :

1. **Architecture unifiée** : un seul store couvre corpus IVR + vecteurs +
   profils utilisateurs + billing + historique conversationnel. Pas de
   synchronisation inter-store, pas de bug de cohérence.
2. **Alignement avec les contraintes projet** : le multi-tenant (ONG + coop +
   individuel), la personnalisation par zone, l'historique utilisateur sont
   relationnels par nature. Les bricoler par-dessus une VDB pure coûte cher.
3. **Évolutivité progressive** : on peut démarrer sur Neon ou Supabase en
   free tier, scaler horizontalement, migrer vers self-hosted ou AWS RDS plus
   tard sans changer une ligne de code applicatif (SQL reste SQL).
4. **Souveraineté** : offres EU (Neon Frankfurt, Supabase EU) + compatibilité
   hébergement souverain Afrique si requis plus tard (n'importe quel VPS peut
   héberger PG).
5. **Ops standards** : écosystème Python mature (SQLAlchemy, Alembic),
   outils monitoring universels, communauté massive.
6. **Pas de verrou vendor** : tout est standard SQL + extension open-source.

**Option B (Pinecone) est écartée** sauf demande explicite, pour deux raisons :
verrou vendor + architecture duale inutile à notre échelle cible.

---

## Conséquences (si Option A retenue)

### Positives

- Un seul store à opérer, backuper, monitorer
- Schema évolutif propre (migrations versionnées)
- Personnalisation utilisateur, billing, historique = gratuits architecturalement
- Coût maîtrisé avec visibilité à 6-12 mois

### Négatives assumées

- pgvector moins rapide que Qdrant à scale >10M vecteurs. À ce stade, on
  refera un ADR pour migrer si nécessaire. Aujourd'hui inutile.
- Apprendre / gérer PostgreSQL (pas neuf, mais complexité supérieure à fichier
  SQLite). Mitigation : Neon/Supabase managed au début.

### Migration depuis ChromaDB

Plan à détailler dans un ADR-0002 séparé si l'Option A est validée :

1. Schéma PostgreSQL pour le corpus IVR (tables : `concepts`, `entries`,
   `response_translations`, `tags`, `languages`)
2. Script d'import des 162 entrées actuelles depuis `corpus_ivr.json`
3. Réécriture de `vdb_service.py` → `corpus_service.py` avec API compatible
   (même fonction `chercher_reponse_ivr`)
4. Période de coexistence (feature flag) pour validation terrain
5. Déprécation ChromaDB + suppression du code

### Verrous futurs (si Option A retenue)

- Dépendance à PostgreSQL : raisonnable, standard industrie
- Dépendance à pgvector : active, bien maintenue, alternative viable
  (migration vers Qdrant possible si scale explose)

---

## Question d'embedding (à traiter en ADR-0003 séparé)

Le **vrai sujet critique**, indépendant du choix de store : quel modèle
d'embedding pour 50 langues africaines basse-ressource.

Aucune des options A/B/C/D ne résout ce problème par elle-même. Options à étudier
dans un ADR dédié :

1. **Multilingual-E5-large** (Microsoft, 100+ langues)
2. **LaBSE** (Google, 109 langues, plus gros)
3. **Translate-then-embed** : ASR → FR → embed FR → réponse en langue cible
4. **Fine-tuning** d'un embedding sur les corpus projet (AfriBERTa / AfroLM base)

À traiter **après** l'acceptation d'ADR-0001.

---

## Références

- Transcript discussion Claude / Ruben du 2026-04-21
- [CLAUDE.md](../../CLAUDE.md)
- [MEMORY.md](../../../.claude/projects/c--Users-USER-PC-Documents-propre---moi-wourri/memory/MEMORY.md) — section "Fichiers clés"
- `app/services/vdb_service.py` — implémentation ChromaDB actuelle
- pgvector docs : https://github.com/pgvector/pgvector
- Pinecone pricing : https://www.pinecone.io/pricing/
- Qdrant docs : https://qdrant.tech/documentation/

---

## Historique

- **2026-04-21** : ADR rétrospectif + nouvelle décision rédigée. Statut : proposé.
- **2026-04-21** : Contexte précisé après validation de `docs/vision.md` (IVR
  horizon 2-3 ans, phasage graduel accepté, posture GDPR-like validée).
  Options et recommandation inchangées — ces précisions renforcent Option A.
- **2026-04-21** : **Statut → accepté**. Ruben valide Option A (pgvector).
  Prochain ADR-0002 : plan de migration ChromaDB → PostgreSQL + pgvector
  (à rédiger après finalisation du Quality Gate ASR).
