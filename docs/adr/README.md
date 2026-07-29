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
| [ADR-0003](0003-plan-ajout-omnilingual.md) | Plan d'ajout Omnilingual | **accepté** | 2026-04-22 | 5 phases : env → provider → benchmark → intégration → cleanup. |
| [ADR-0004](0004-corpus-bambara-afrivoices-nextvoices.md) | Intégration corpus AfVoices/ANV + stratégie multi-variantes Manding | **accepté** | 2026-04-23 | AfVoices (CC-BY-4.0, 423h bambara Mali) intégré en bam_ML séparé. Stratégie multi-modèles isolés par variante (dyu_CI / dyu_ML / bam_ML) pour éviter pollution croisée. Implémentation différée. |
| [ADR-0005](0005-afrolid-language-detection.md) | Détection de langue textuelle via AfroLID | **accepté** | 2026-04-23 | AfroLID (UBC-NLP, Apache 2.0, 517 langues africaines) pour remplacer l'heuristique hardcodée `is_likely_dioula_input`. Implémentation différée P2-P3. |
| [ADR-0008](0008-plan-migration-chromadb-pgvector.md) | Plan migration ChromaDB → PostgreSQL+pgvector | **accepté** | 2026-05-05 | Plan d'exécution en 5 phases (provisionnement → schéma → adapter+double-écriture → validation terrain → bascule). Exécute ADR-0001. |
| [ADR-0010](0010-migration-monorepo.md) | Migration vers monorepo | **proposé** | 2026-04-23 | Structure repo actuelle (3 branches orphelines) → monorepo standard avec sous-dossiers. Exécution planifiée après stabilisation Sprint 2. |
| [ADR-0011](0011-strategie-prechargement-ml.md) | Stratégie de préchargement des modèles ML | **complété** | 2026-05-08 / 2026-05-10 | Lazy-load ciblé NLLB + Whisper, eager pour NeMo + TTS. Toutes phases livrées (PR #130-#133). Métriques mesurées : RSS boot 1503 MB / VMS boot 2793 MB (cibles atteintes). Bug `mkl_malloc` 2026-05-07 résolu. |
| [ADR-0012](0012-securite-whatsapp-server.md) | Sécurité whatsapp-server (CORS + rate limit + npm audit) | **complété** | 2026-05-10 | Sprint A du programme dette technique : 0 vulnérabilité npm (vs 12 avant), CORS strict via `ALLOWED_ORIGINS`, rate limiting 60 req/min/IP. PRs #141, #142, #143. |
| [ADR-0013](0013-ssh-deploy-hardening-options.md) | Durcissement déploiement SSH (3 options) | **proposé** | 2026-05-30 | Analyse 3 options pour remplacer la clé SSH statique CI (BLOCKER B1-SEC issue #221) : self-hosted runner, Tailscale SSH, Scaleway OIDC. Recommandation : **Option B (Tailscale)** — meilleur ratio coût/bénéfice, audit logs centralisés synergiques avec ARTCI (#215). En attente validation Ruben. |
| [ADR-0016](0016-migration-promtail-grafana-alloy.md) | Migration Promtail → Grafana Alloy | **accepté** | 2026-07-29 | Remplace le collecteur Promtail arrivé en fin de vie par Alloy 1.18.0, corrige la découverte Docker staging et conserve le pipeline Loki existant. |
| [ADR-0017](0017-dashboard-observabilite-sans-pii.md) | Dashboard d’observabilité sans contenu PII | **accepté** | 2026-07-29 | Dashboard #41 sur PostgreSQL, métriques techniques sans messages/transcriptions, données protégées par `X-API-Key`. |

## ADRs à rédiger (roadmap, issus de [PLAN_ACTION_2026-04.md](../PLAN_ACTION_2026-04.md))

| ID | Titre | Priorité | Déclencheur |
|---|---|---|---|
| ADR-0006 | Migration Baileys → WhatsApp Cloud API | P2 | [P2-07] |
| ADR-0007 | Choix LLM conversationnel (souveraineté DeepSeek) | P3 | [P3-05] |
| ADR-0009 | Stratégie IVR téléphonique P2 | P3 | [P3-01] |

## Convention de numérotation

- Incrémentale, 4 chiffres (0001, 0002, ...)
- Nom de fichier : `NNNN-description-courte-en-kebab-case.md`
- Un ADR = un sujet. S'il en couvre plusieurs, en rédiger plusieurs.
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
