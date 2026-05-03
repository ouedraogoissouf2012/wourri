# Index des Architecture Decision Records — Wourri

Les ADR (Architecture Decision Records) gravent les décisions structurantes
du projet. Chaque décision passe par cet index et par le workflow du skill
`architectural-decision`.

**Règle** : pas de code sur une brique structurante sans ADR accepté.

## ADRs existants

| ID | Titre | Statut | Date | Résumé |
|---|---|---|---|---|
| [ADR-0000](0000-template.md) | Template | — | — | Modèle à copier pour tout nouvel ADR |
| [ADR-0001](0001-choix-stockage-donnees.md) | Choix du stockage de données | **accepté** | 2026-04-21 | PostgreSQL + pgvector remplace ChromaDB. Migration planifiée ADR futur. |
| [ADR-0002](0002-ajout-provider-omnilingual.md) | Ajout d'un provider Omnilingual ASR | **accepté** | 2026-04-22 | Meta Omnilingual ASR ajouté à la chain ASR existante (pas remplacement). |
| [ADR-0003](0003-plan-ajout-omnilingual.md) | Plan d'ajout Omnilingual | **accepté** | 2026-04-22 | 5 phases : env → provider → benchmark → intégration → cleanup. |
| [ADR-0004](0004-corpus-bambara-afrivoices-nextvoices.md) | Intégration corpus AfVoices/ANV + stratégie multi-variantes Manding | **proposé** | 2026-04-23 | AfVoices (CC-BY-4.0, 423h bambara Mali) intégré en bam_ML séparé. Stratégie multi-modèles isolés par variante (dyu_CI / dyu_ML / bam_ML) pour éviter pollution croisée. Implémentation différée. |
| [ADR-0005](0005-afrolid-language-detection.md) | Détection de langue textuelle via AfroLID | **accepté** | 2026-04-23 | AfroLID (UBC-NLP, Apache 2.0, 517 langues africaines) pour remplacer l'heuristique hardcodée `is_likely_dioula_input`. Implémentation différée P2-P3. |
| [ADR-0010](0010-migration-monorepo.md) | Migration vers monorepo | **proposé** | 2026-04-23 | Structure repo actuelle (3 branches orphelines) → monorepo standard avec sous-dossiers. Exécution planifiée après stabilisation Sprint 2. |

## ADRs à rédiger (roadmap, issus de [PLAN_ACTION_2026-04.md](../PLAN_ACTION_2026-04.md))

| ID | Titre | Priorité | Déclencheur |
|---|---|---|---|
| ADR-0006 | Migration Baileys → WhatsApp Cloud API | P2 | [P2-07] |
| ADR-0007 | Choix LLM conversationnel (souveraineté DeepSeek) | P3 | [P3-05] |
| ADR-0008 | Plan migration ChromaDB → pgvector | P2-P3 | après ADR-0001 |
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
