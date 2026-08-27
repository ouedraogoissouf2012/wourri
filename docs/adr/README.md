# Index des Architecture Decision Records — Wourri

Les ADR (Architecture Decision Records) gravent les décisions structurantes
du projet. Chaque décision passe par cet index et par le workflow du skill
`architectural-decision`.

**Règle** : pas de code sur une brique structurante sans ADR accepté.

## ADRs existants

| ID | Titre | Statut | Date | Résumé |
|---|---|---|---|---|
| [ADR-0000](0000-template.md) | Template | — | — | Modèle à copier pour tout nouvel ADR |
| [ADR-0001](0001-choix-stockage-donnees.md) | Choix du stockage de données | **accepté** | 2026-04-21 | PostgreSQL + pgvector remplace ChromaDB. Plan migration → [ADR-0008](0008-plan-migration-chromadb-pgvector.md). |
| [ADR-0002](0002-ajout-provider-omnilingual.md) | Ajout d'un provider Omnilingual ASR | **accepté** | 2026-04-22 | Meta Omnilingual ASR ajouté à la chain ASR existante (pas remplacement). |
| [ADR-0003](0003-plan-ajout-omnilingual.md) | Plan d'ajout Omnilingual | **accepté** | 2026-04-22 | 5 phases : env → provider → benchmark → intégration → cleanup. Addendum 2026-08-14 (#206/P1-02) : Bambara-ASR-v2 (M4) déjà au benchmark [0001](../benchmarks/0001-asr-dioula-evaluation.md), validation Ruben requise. |
| [ADR-0004](0004-corpus-bambara-afrivoices-nextvoices.md) | Intégration corpus AfVoices/ANV + stratégie multi-variantes Manding | **accepté** | 2026-04-23 | AfVoices (CC-BY-4.0, 423h bambara Mali) intégré en bam_ML séparé. Stratégie multi-modèles isolés par variante (dyu_CI / dyu_ML / bam_ML) pour éviter pollution croisée. Implémentation différée. |
| [ADR-0005](0005-afrolid-language-detection.md) | Détection de langue textuelle via AfroLID | **accepté** | 2026-04-23 | AfroLID (UBC-NLP, Apache 2.0, 517 langues africaines) pour remplacer l'heuristique hardcodée `is_likely_dioula_input`. Implémentation différée P2-P3. |
| [ADR-0008](0008-plan-migration-chromadb-pgvector.md) | Plan migration ChromaDB → PostgreSQL+pgvector | **accepté** | 2026-05-05 | Plan d'exécution en 5 phases (provisionnement → schéma → adapter+double-écriture → validation terrain → bascule). Exécute ADR-0001. |
| [ADR-0010](0010-migration-monorepo.md) | Migration vers monorepo | **proposé** | 2026-04-23 | Structure repo actuelle (3 branches orphelines) → monorepo standard avec sous-dossiers. Exécution planifiée après stabilisation Sprint 2. |
| [ADR-0011](0011-strategie-prechargement-ml.md) | Stratégie de préchargement des modèles ML | **complété** | 2026-05-08 / 2026-05-10 | Lazy-load ciblé NLLB + Whisper, eager pour NeMo + TTS. Toutes phases livrées (PR #130-#133). Métriques mesurées : RSS boot 1503 MB / VMS boot 2793 MB (cibles atteintes). Bug `mkl_malloc` 2026-05-07 résolu. |
| [ADR-0012](0012-securite-whatsapp-server.md) | Sécurité whatsapp-server (CORS + rate limit + npm audit) | **complété** | 2026-05-10 | Sprint A du programme dette technique : 0 vulnérabilité npm (vs 12 avant), CORS strict via `ALLOWED_ORIGINS`, rate limiting 60 req/min/IP. PRs #141, #142, #143. |
| [ADR-0013](0013-ssh-deploy-hardening-options.md) | Durcissement déploiement SSH | **accepté** | 2026-08-15 | Addendum Dokploy : le risque clé SSH CI (Scaleway + `appleboy`) n'est plus le chemin prod ([ADR-0026](0026-deploiement-wourri-dokploy.md)). **Option D** retenue. A/B/C (runner / Tailscale / OIDC Scaleway) = trace historique, ne pas exécuter. |
| [ADR-0014](0014-promotion-corpus-v3-dioula-ci.md) | Promotion du corpus v3 dioula CI vers production | **accepté** | 2026-06-03 | Corpus v3 dioula ivoirien promu en production après validation native ; process de promotion gravé (relecture native > règles écrites). |
| [ADR-0015](0015-strategy-pattern-cascade-chat-et-anglais.md) | Strategy Pattern pour la cascade chat + ajout de l'anglais | **livré** | 2026-06-01 | La cascade 4 tiers de `chat_service` passe en Strategy Pattern (OCP) ; l'anglais s'ajoute sans toucher la logique existante. |
| [ADR-0016](0016-migration-promtail-grafana-alloy.md) | Migration Promtail → Grafana Alloy | **accepté** | 2026-07-29 | Remplace le collecteur Promtail arrivé en fin de vie par Alloy 1.18.0, corrige la découverte Docker staging et conserve le pipeline Loki existant. |
| [ADR-0017](0017-dashboard-observabilite-sans-pii.md) | Dashboard d’observabilité sans contenu PII | **accepté** | 2026-07-29 | Dashboard #41 sur PostgreSQL, métriques techniques sans messages/transcriptions, données protégées par `X-API-Key`. |
| [ADR-0018](0018-strategie-rate-limiting-api.md) | Stratégie de rate limiting de l'API | **accepté** | 2026-08-14 | Issue #307 (CRITIQUE) : **Option A** — limite globale unique pilotée par `RATE_LIMIT` (les 20 décorateurs `10/minute` hardcodés sont retirés), exemption du trafic authentifié par clé API interne via middleware ASGI (zéro sentinelle IP), verrouillage `FORWARDED_ALLOW_IPS` documenté avant le reverse proxy Sprint J. |
| [ADR-0019](0019-feedback-c3-revue-native.md) | Feedback utilisateur : signal analytics + file de revue native | **accepté** | 2026-08-05 | Refonte C3 : le feedback devient un signal analytics doublé d'une file de revue par un locuteur natif. |
| [ADR-0020](0020-filtre-bam-dyu-perimetre-reduit.md) | Filtre BAM↔DYU : périmètre réduit aux règles phonologiques | **accepté** | 2026-08-05 | Refonte #90 : le filtre se limite aux règles phonologiques bambara↔dioula, le lexical sort du périmètre. |
| [ADR-0021](0021-dedup-provider-asr-nemo.md) | Déduplication du provider ASR NeMo Soloni + conversion audio | **accepté** | 2026-08-07 | #303B : un seul provider NeMo et une conversion audio unique ; supprime la duplication de la chaîne ASR. |
| [ADR-0022](0022-composition-chaine-asr-dioula.md) | Composition de la chaîne ASR dioula (ordre des providers, critère de bascule) | **proposé** | 2026-08-09 | Ordre des providers et critère de bascule (bench WER ≥ 30 voix). Complété par [ADR-0027](0027-decision-nemo-installer-ou-retirer.md). |
| [ADR-0023](0023-unification-voix-dioula.md) | Unification de la voix dioula | **accepté** | 2026-08-10 | #362 : une voix dioula unique pour toutes les sorties TTS (cohérence perçue côté utilisateur). |
| [ADR-0024](0024-transition-convex-multitenant.md) | Transition vers le backend Convex multi-tenant | **accepté** | 2026-08-11 | #372 : Convex = magasin unique des nouveaux domaines métier multi-tenant ; FastAPI reste le plan de calcul (ASR/TTS/NLU/LLM) ; PostgreSQL+pgvector garde le corpus IVR (pas de dual-write). Aucune PII de prod dans Convex avant validation résidence/rétention. Amende [ADR-0001](0001-choix-stockage-donnees.md). |
| [ADR-0025](0025-retention-logs-pii-artci.md) | Rétention et purge des logs PII (conformité ARTCI) | **accepté** | 2026-08-14 | Issue #215 : fichiers de log datés append-only (aucun rename, sûr multi-worker) + purge quotidienne in-app. Logs applicatifs 30 j, feedback pseudonymisé 365 j. Politique : [docs/compliance/artci-logs.md](../compliance/artci-logs.md). |
| [ADR-0026](0026-deploiement-wourri-dokploy.md) | Déploiement Wourri sur l'hôte Dokploy existant (ADC) | **accepté** | 2026-08-13 | Cible réelle = VPS Contabo avec Dokploy/Traefik/Swarm déjà en place (pas la VM Scaleway du runbook). Déploiement via Dokploy, interne only, build serveur depuis Git. **Option A retenue** (3 services natifs Dokploy). Renuméroté depuis 0024 (collision, #496). |
| [ADR-0027](0027-decision-nemo-installer-ou-retirer.md) | Décision NeMo Soloni : installer `nemo-toolkit` ou retirer le provider | **accepté** | 2026-08-15 | #358 : **Option A** — retrait propre du provider fantôme (jamais exécuté). MMS-dyu + MMS-generic restent. Réversible `git revert`. Complète [ADR-0022](0022-composition-chaine-asr-dioula.md). |
| [ADR-0028](0028-refonte-qualite-ivr-seuils-semantiques.md) | Refonte qualité IVR : seuils de confiance + score sémantique pgvector | **accepté** | 2026-08-14 | #297 : `MIN_CONFIDENCE_THRESHOLD=0.2` hardcodé ne gate que la phrase FR ; `corpus_service` **jette** la distance cosine pgvector → IVR répond même hors-sujet. **Option A retenue** : instrumentation A1 (exposer+logger la distance) puis gating calibré A2 (`IVR_MAX_SEMANTIC_DISTANCE`) ; `NLU_MIN_CONFIDENCE` externalisé ; Option C (score composite) différée. |
| [ADR-0029](0029-activation-lm-filter-kenlm-dioula.md) | Activation du filtre LM KenLM dioula (anti-hallucination ASR) | **accepté** | 2026-08-14 | #94 : `lm_filter.py` existe mais non câblé, flag `ENABLE_LM_RESCORING` inexistant, binaire non tracké, seuils hardcodés. Rôle acté = filtre anti-hallucination (pas de n-best). **Option A retenue** : activation flag `ENABLE_LM_RESCORING=False` par défaut, seuils externalisés, binaire versionné en V3 (volume monté) ; activation prod conditionnée au bench WER ≥ 30 voix (héritage [ADR-0022](0022-composition-chaine-asr-dioula.md)). |
| [ADR-0030](0030-plateforme-api-produit-convex.md) | Plateforme API (produit + SaaS multi-tenant) sur socle Convex | **accepté** | 2026-08-15 | Exposer l'API Wourri en produit (`/v1`, clés produit scoppées + quotas) ET le SaaS métier, en réutilisant l'auth/RBAC/scopes/quotas du socle Convex #372 (pas de 2ᵉ couche d'auth). **Option A retenue** ; mise en œuvre en phases (Phase 1 = Convex prod-ready) ; l'exposition démo = 1ʳᵉ tranche minimale. Renuméroté depuis 0026 (collision). |
| [ADR-0031](0031-moteur-amelioration-linguistique.md) | Moteur d'amélioration linguistique (statuts, rôles, publication) | **accepté** | 2026-08-16 | #429 / epic #428. **Option A** : Convex = atelier (Bronze→Production, 1 locuteur = 1 langue) ; pgvector = runtime Or+ seulement. Auth = #372. Admin = sas avant corpus. Pas de 2ᵉ auth FastAPI. |
| [ADR-0032](0032-exposition-etroite-moteur-demo.md) | Exposition étroite du moteur pour la démo Console | **accepté** | 2026-08-16 | Amende ADR-0026 : un hostname public limité à `/api/chat`, `/api/tts`, `/health`, `/static`. Pas de `/docs` ni `/admin`. CORS = `ALLOWED_ORIGINS` (Vercel). Domaine = Dokploy. |
| [ADR-0033](0033-lqe-service-separe.md) | Atelier LQE hors du moteur (FastAPI + Vue) | **accepté** | 2026-08-19 | #451. Option A : wouri-lqe FastAPI + wouri-lqe-web Vue 3/Vite/Tailwind. Comptes par langue. |
| [ADR-0034](0034-atelier-parite-linguistique.md) | Atelier de parité linguistique : concepts multilingues, assignations & audio natif | **accepté** | 2026-08-23 | Modèle concept×langue (clé = `id` corpus IVR, pivot FR), matrice de couverture, assignations admin par lot, « parité avant extension », **audio natif requis**, stockage **pgvector** (amende ADR-0033). Archi SOLID/OCP, zéro `if`-langue. Piloter sur dyu/bci/bté, architecturer pour ~60 langues. |
| [ADR-0035](0035-collecte-dataset-asr-dictee.md) | Collecte du dataset ASR par dictée guidée + contrat d'export | **accepté** | 2026-08-25 | #474 (epic #472). Table dédiée `lqe.dictation` (prompt imposé → audio, `todo`/`recorded`) + export ZIP `audio/` + `metadata.csv` (standard HF `audiofolder`). **Option A** : sépare la collecte d'entraînement de la parité (ADR-0034), transcription garantie par dictée. Choix du modèle / fine-tune **différé** (gaté sur benchmark #479). |
| [ADR-0036](0036-choix-modele-asr-baoule.md) | Choix du modèle ASR baoulé (base de fine-tuning) | **accepté** | 2026-08-27 | #474. Benchmark 0003 exécuté (Kaggle) : Omnilingual **1B** CER **22,1 %** > 300M 26,0 % (zero-shot, vrai baoulé). **Option A** : 1B comme base de fine-tune ; 300M = fallback ; service CPU par quantification int8/ONNX différée. |

## ADRs à rédiger (roadmap, issus de [PLAN_ACTION_2026-04.md](../PLAN_ACTION_2026-04.md))

Ces numéros sont **réservés** : ils ne sont pas libres et ne doivent pas être
réattribués à un autre sujet. Le fichier n'existe pas encore — il sera créé
sous ce numéro quand le déclencheur se présente.

| ID | Titre | Priorité | Déclencheur | Nom de fichier réservé |
|---|---|---|---|---|
| ADR-0006 | Migration Baileys → WhatsApp Cloud API | P2 | [P2-07] | `0006-migration-whatsapp-cloud-api.md` |
| ADR-0007 | Choix LLM conversationnel (souveraineté DeepSeek) | P3 | [P3-05] | `0007-choix-llm-conversationnel.md` |
| ADR-0009 | Stratégie IVR téléphonique P2 | P3 | [P3-01] | à définir |

Les deux premiers noms sont déjà cités dans le dépôt ([PLAN_ACTION_2026-04.md](../PLAN_ACTION_2026-04.md), [ADR-0010](0010-migration-monorepo.md)) : les liens vers ces fichiers pointent
volontairement un ADR à venir, ils ne sont pas cassés.

## État des numéros (0000 → 0036)

Cette section rend compte de **chaque** numéro, pour qu'un trou soit toujours une
réponse et jamais un oubli (issue #496).

| Numéro(s) | État |
|---|---|
| 0000–0005, 0008, 0010–0036 | **attribués** — fichier présent dans `docs/adr/`, listé ci-dessus |
| 0006, 0007, 0009 | **réservés** — ADR à rédiger (voir la section précédente). Ne pas réattribuer. |

**Aucun numéro n'est libre entre 0000 et 0036** : le prochain ADR prend **0037**.

### Historique de la collision 0024 (issue #496)

Le numéro 0024 a porté **deux** décisions sans rapport. Arbitrage du 2026-08-27,
sur l'antériorité d'acceptation :

- **0024** reste à [`0024-transition-convex-multitenant.md`](0024-transition-convex-multitenant.md)
  (accepté le **2026-08-11**) ;
- le déploiement Dokploy (accepté le 2026-08-13) devient
  [`0026-deploiement-wourri-dokploy.md`](0026-deploiement-wourri-dokploy.md).

Le numéro 0026 était libre : [ADR-0030](0030-plateforme-api-produit-convex.md)
l'avait quitté à son acceptation, et le brouillon `0026-perimetre-langues-pilote`
n'a jamais été mergé (s'il l'est un jour, il prendra le prochain numéro libre).

> **Hors dépôt** : le fichier `ADR-0026-DOSSIER-ACCEPTATION.md` présent à la
> racine du poste de travail n'est **pas** un ADR (c'est un dossier d'acceptation de
> livrable) et ne réserve aucun numéro.

Toute citation antérieure au 2026-08-27 d'un « ADR-0024 » parlant de déploiement,
de Dokploy ou de Contabo vise en réalité **ADR-0026**.

## Convention de numérotation

- Incrémentale, 4 chiffres (0001, 0002, ...)
- Nom de fichier : `NNNN-description-courte-en-kebab-case.md`
- Un ADR = un sujet. S'il en couvre plusieurs, en rédiger plusieurs.
- **Un numéro = un ADR, définitivement.** Avant d'en prendre un, vérifier la section
  « État des numéros » : les numéros réservés ne sont pas libres. Un ADR
  rédigé sur une branche prend son numéro **au merge**, pas à la rédaction
  (source des collisions 0024 et 0026).
- Un ADR accepté n'est **jamais modifié** sauf pour corriger une faute.
  Les révisions passent par un nouvel ADR qui supersedes le précédent.

## Statuts possibles

- **proposé** : rédigé, attend validation
- **accepté** : validé, sert de source de vérité
- **déprécié** : remplacé par un ADR plus récent (lien vers le remplaçant)
- **rejeté** : étudié mais non retenu (garde sa valeur de traçabilité)
- **complété** : l'implémentation qu'il décrivait est terminée

## Consulter les décisions

- Par ordre chronologique : lire dans l'ordre numérique
- Par thème : voir les mentions dans [PLAN_ACTION_2026-04.md](../PLAN_ACTION_2026-04.md)
- Par mot-clé : `grep -r "mot" docs/adr/`

