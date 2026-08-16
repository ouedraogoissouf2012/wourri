# Architecture Convex WOURI

Statut : développement. Aucune donnée métier ni personnelle réelle. Ce document
décrit le socle Convex tel qu'il existe dans le code (`convex/`), en cohérence
avec `convex-foundation.md` et l'ADR-0024.

Convex est le magasin unique du socle applicatif : temps réel, threads de
conversation, RAG, autorisation et audit. Il ne fait pas de calcul lourd. Le
calcul (ASR, TTS, NLU, LLM, audio) reste chez FastAPI et le worker Dokploy, et
le corpus IVR historique reste sur PostgreSQL/pgvector jusqu'à une décision de
migration distincte.

## 1. Déploiements

| Environnement | Déploiement Convex | Usage aujourd'hui |
| --- | --- | --- |
| Développement | déploiement dev personnel (`npx convex dev`) | schéma, tests, auth locale email/mot de passe |
| Staging | `wouri-staging` | démo et seed reproductible, jamais de donnée personnelle |
| Production | déploiement production | réservé, aucune exposition avant les gates de `convex-foundation.md` |

Store unique : Better Auth tourne sur Convex (local install), il n'y a pas de
seconde base pour l'authentification. Aucune écriture double n'est admise entre
Convex, FastAPI et PostgreSQL.

## 2. Composants Convex montés

`convex/convex.config.ts` monte trois composants :

- `@convex-dev/better-auth` en local install (`convex/betterAuth/`). Il possède
  les tables d'identité : utilisateurs, sessions, organisations, membres,
  invitations. Le local install est requis pour le plugin `organization` (voir
  la rule projet : les plugins `organization`/`admin` ne sont pas supportés par
  le component NPM standard).
- `@convex-dev/agent`. Il possède les messages et la mémoire conversationnelle
  d'un thread. WOURI ne stocke pas les messages, seulement le contexte métier
  d'un thread (voir §8).
- `@convex-dev/rag`. Il possède les chunks vectoriels et la recherche
  sémantique, isolés par namespace (voir §7).

Better Auth est monté via `authComponent.registerRoutes(http, createAuth)` dans
`convex/http.ts`. La création d'organisation par un utilisateur est désactivée
(`allowUserToCreateOrganization: false`) : seul un workflow opérateur crée une
organisation, et un trigger `organization.onCreate` insère alors un
`organizationProfiles` en statut `provisioning`, sans aucun droit implicite.

## 3. Tables par domaine

Le schéma est assemblé dans `convex/schema.ts` à partir de fichiers par domaine
sous `convex/schema/`. Les tables WOURI référencent l'organisation Better Auth
par la chaîne `organizationId` (jamais par une relation dure), et l'organisation
est toujours dérivée côté serveur, jamais d'un argument client.

### Tenancy (`schema/tenancy.ts`)

- `organizationProfiles` : profil WOURI d'une organisation Better Auth (`kind`,
  `legalName`, `status` provisioning/active/suspended). Index `by_organizationId`.
- `organizationDefaultZones` : zones météo par défaut d'une organisation.
- `organizationRolePolicies` : politiques de rôle (`key`, `permissions[]`,
  `scopeMode` organization/restricted). Source d'autorité runtime des
  permissions ; les presets de `authz/capabilities.ts` la remplissent.
- `memberRoleAssignments` : journal append-only d'assignations membre -> rôle
  (`status` active/revoked). L'assignation active la plus récente gagne.
- `membershipScopeGrants` : grants de périmètre (`scopeType` zone/crop/group,
  `scopeKey`) pour les rôles restreints, avec `expiresAt` optionnel.

### Billing et entitlements (`schema/billing.ts`)

- `organizationSubscriptions` : abonnement fournisseur (statut trialing/active/
  past_due/canceled, `currentPeriodEndsAt`).
- `organizationEntitlements` : capacités de plan activables (`key`, `enabled`,
  `limit` optionnel, `validFrom`/`validUntil`, `source` subscription/manual).
  Rend un plan réellement applicable en code (ex. `maxFarmers`,
  `whatsappEnabled`).
- `subscriptionEvents` : événements fournisseur reçus, idempotence par
  `(provider, providerEventId)`.

### Farmers (`schema/farmers.ts`)

- `farmers` : agriculteur d'une organisation, identifié par
  `externalIdentityHash` (jamais un numéro en clair), statut active/archived.
- `farmerProfiles` : langue préférée, pays, opt-in notification.
- `farmerZoneLinks`, `farmerCropLinks` : rattachement zone / culture (ciblage
  d'audience).
- `farmerGroups`, `farmerGroupMembers` : groupes d'agriculteurs.
- `farmerConsents` : consentements versionnés (purpose, policyVersion, state
  granted/withdrawn, source de capture).

### Conversations (`schema/conversations.ts`)

- `conversationContexts` : couche métier au-dessus d'un thread Agent. Mappe
  `agentThreadId` vers qui parle (`farmerId`), pour quelle organisation, sur
  quel `channel`, dans quelle langue, et depuis quelle alerte (`originAlertId`).
  `originAlertId` est ce qui permet de récupérer l'alerte d'origine (voir §9).
  Index par `agentThreadId`, par `(organizationId, farmerId)`, par
  `(organizationId, originAlertId)`, par `(organizationId, channel, farmerId)`.

### Alerts (`schema/alerts.ts`)

- `alerts` : message diffusé (statut draft/scheduled/sending/completed/canceled,
  `sourceVersionId` optionnel pour la provenance).
- `alertAudienceRules` : règles de ciblage (kind farmer/zone/crop/group,
  `targetKey`, `snapshotAt` optionnel).
- `alertDeliveries` : une livraison par agriculteur (`state`
  created/scheduled/sent/delivered/read/replied/failed, `attemptCount`,
  `providerMessageId`, `conversationContextId` optionnel). Index par
  `(organizationId, state, nextAttemptAt)`, `(alertId, state)`,
  `(farmerId, state)`, `(provider, providerMessageId)`.

### Knowledge (`schema/knowledge.ts`)

Registre de provenance citable (le RAG possède les vecteurs, ces tables
possèdent la provenance) :

- `knowledgeSources` : source (SODEXAM, CNRA...), `visibility` global/
  organization, `authority`, `license`, `canonicalLocator`.
- `knowledgeSourceVersions` : version exacte d'une source (`contentHash`,
  `acquiredAt`, `acquisitionMethod`).
- `knowledgeDocuments` : document ingéré rattaché à une version de source.
- `knowledgeChunks` : fragments citables ordonnés d'un document.

### Weather (`schema/weather.ts`)

- `weatherObservations` : observation SODEXAM structurée par zone (fenêtre
  `validFrom`/`validUntil`, `variables` JSON, `confidence`). `dataOrigin`
  live/staging_fixture garde une fixture distinguable d'une donnée réelle : une
  fixture ne peut jamais être présentée comme une observation de production. La
  météo est lue par l'outil `getWeather`, jamais passée au RAG.

### Language (`schema/language.ts`)

Actifs linguistiques versionnés (jamais écrasés) :

- `approvedPhrases`/`approvedPhraseVersions`, `glossaryTerms`/
  `glossaryTermVersions`, `languageExamples`/`languageExampleVersions` : tête
  stable + versions successives (lifecycle draft/approved/retired).
- `languageCorrections` : corrections pointant une version cible et sa version
  de remplacement.
- `linguisticFeedback` : enregistrement riche de la console validateur
  (transcription/traduction brute vs validée, scores, `errorType`, `status`
  draft/needs_review/validated/rejected, `version`). Voir §10.

### Config (`schema/config.ts`)

- `featureFlags` : flags par environnement staging/production, optionnellement
  par organisation (org > global, défaut fail-closed).
- `promptVersions`, `policyVersions`, `modelConfigs` : registres versionnés
  (prompt, politique anti-hallucination, config modèle). Paramètres uniquement,
  jamais de secret fournisseur. Activation contrôlée : une seule version
  `active` par clé, l'ancienne passe `retired`.

### Observability (`schema/observability.ts`)

- `executionTraces` : trace d'exécution (l'organisation, le contexte, l'intent,
  la langue, les clés/versions prompt/policy/model, `resultStatus`
  running/succeeded/abstained/failed, métriques latence/tokens/coût). Voir §11.
- `executionTraceSteps` : étapes ordonnées (kind tool/retrieval/generation/
  guard, `sourceVersionId`, status ok/error/skipped).
- `errorReports` : occurrences de la taxonomie d'erreur.
- `replaySnapshots` : entrées et contexte figés pour rejeu en staging.

### Audit (`schema/audit.ts`)

- `auditLogs` : journal des opérations sensibles (acteur, action, ressource,
  `before`/`after` sérialisés non sensibles, `traceId` optionnel). Jamais de
  secret. Index par `(organizationId, createdAt)`, `(resourceType, resourceId)`,
  `(action, createdAt)`.

### Jobs (`schema/jobs.ts`)

- `jobRecords` : Convex ne tient que l'ÉTAT d'un job (kind, status queued/
  running/succeeded/failed, `progress`, refs d'entrée/résultat, `fileStorageId`).
  Le calcul lourd (ASR, FFmpeg, TTS) tourne sur le worker Dokploy qui remonte
  son avancement ici.

## 4. Autorisation (RBAC + périmètres)

`convex/authz/` implémente une garde unique, fail-closed, détaillée dans
`convex-permissions-matrix.md`. Points clés d'architecture :

- Catalogue canonique `CAPABILITIES` (`authz/capabilities.ts`). Chaque fonction
  sensible référence `CAPABILITIES.*`, jamais une chaîne magique, donc la
  matrice a une seule source de vérité.
- `ROLE_PRESETS` code en dur les permissions de chaque preset de rôle, partagées
  par le provisioning, le seed, la doc et les tests pour éviter toute dérive.
- Une exigence est `{ permission, scope?, entitlement? }`. `evaluateAuthorization`
  (`authz/policy.ts`) est une fonction pure qui vérifie, dans l'ordre :
  relation active (org active, session non expirée, membre, assignation active,
  policy) -> permission présente -> périmètre requis (organizationId toujours,
  plus zone/culture/groupe via `membershipScopeGrants` quand `scopeMode` est
  `restricted`) -> entitlement encore valide. Tout échec renvoie `null` -> déni.
- Deux points d'entrée dans `authz/authorize.ts` :
  - `authorize(ctx, requirement)` en **query** : déterministe, sans horloge. Un
    entitlement borné dans le temps n'est pas évaluable de façon réactive, donc
    il est traité comme mutation-only tant qu'il n'est pas matérialisé
    (`hasQuerySafeEntitlement`).
  - `authorizeMutation(ctx, requirement)` en **mutation** : passe l'horloge
    serveur `Date.now()`, ce qui permet d'évaluer expiration de session, de
    grant et d'entitlement.
- `authorizeResource(ctx, resourceId, requirement)` : garde anti-fuite. Après
  autorisation, il charge la ressource et **vérifie que son `organizationId`
  correspond à l'organisation autorisée**. Un id deviné d'une autre organisation
  échoue fail-closed sans confirmer son existence.
- Les actions n'ont pas de `ctx.db` : elles autorisent via l'internal query
  `authz/checkAccess.requireCapability`, qui dérive l'organisation de la session
  (jamais d'un argument) et renvoie le contexte autorisé ou lève.

## 5. Couche Agent

`conversationContexts` est le pont entre WOURI et le composant Agent. Le
composant Agent possède les messages ; `conversationContexts` mappe un
`agentThreadId` au métier (organisation, agriculteur, canal, langue, alerte
d'origine). `conversations/model.ts` :

- `ensureConversationForAlert` crée (ou réutilise) un thread Agent via
  `createThread`, enregistre le message de l'alerte comme message assistant, et
  stampe `originAlertId`.
- `contextThread` (internal query) résout `agentThreadId` + organisation pour
  que le pipeline (une action) puisse poster des messages sur le bon thread,
  après avoir vérifié que le thread appartient bien à l'organisation autorisée.

## 6. RAG

`convex/rag/index.ts` définit un RAG typé par `KnowledgeFilters`. Isolation
tenant par **namespace** :

- Une source d'organisation vit dans le namespace de son `organizationId`.
- Une source globale (SODEXAM/CNRA publiée largement) vit dans le namespace
  partagé `global`.

`knowledgeNamespace(visibility, organizationId)` calcule le namespace à
l'ingestion. À la recherche, l'outil `searchKnowledge` interroge uniquement les
namespaces visibles par l'appelant (le sien + `global`). Les filtres de
provenance disponibles sont : `sourceId`, `sourceVersionId`, `authority`,
`language`, `zone`, `culture`, `version`. Chaque résultat porte sa provenance
pour la citation.

Modèle d'embedding : par défaut un modèle local déterministe
(`rag/embeddingModel.ts`, hash FNV-1a, dimension 256), sans clé externe, pour
que staging et tests restent reproductibles. La production remplace le
fournisseur via config ; changer de fournisseur ou de dimension impose de
ré-indexer les namespaces (voir le runbook).

## 7. Flux d'alerte

Piloté par `alerts/mutations.ts` et `alerts/model.ts` :

1. `createAlert` (capability `alerts.create`) : alerte en `draft`.
2. `addAlertAudienceRule` : ajoute une règle de ciblage (farmer/zone/crop/group).
3. `previewAudience` (query) : prévisualise l'audience résolue sans effet de
   bord. `previewAudience` et `publishAlert` partagent les mêmes plafonds
   (`RULE_SCAN_LIMIT`, `MAX_AUDIENCE`) pour qu'un gros tenant ne dépasse jamais
   le budget de transaction.
4. `publishAlert` (capability `alerts.publish`) : résout l'audience (union
   dédupliquée, restreinte à l'organisation), matérialise une `alertDeliveries`
   par agriculteur en état `created`, passe l'alerte en `sending`.

Le cycle d'une livraison est : `created` -> `sent` -> `delivered` -> `read` ->
`replied`, avec `failed` en branche d'échec. La passerelle WhatsApp n'est pas
encore branchée : aucune API externe n'est appelée à la publication ; les états
au-delà de `created` arrivent via le callback fournisseur
(`recordDeliveryCallback`, internal), qui matche par `providerMessageId` et
avance l'état (bump d'`attemptCount` sur échec). Un callback ne régresse jamais
vers `created`/`scheduled`.

## 8. Flux alerte -> conversation (§17)

`conversations/mutations.recordFarmerReply` (internal, appelé par le webhook
serveur, sans session utilisateur) : quand un agriculteur répond à une alerte,
`recordInboundReply` passe la livraison à `replied`, ouvre ou réutilise la
conversation durable issue de l'alerte, lie la livraison au
`conversationContextId`, et enregistre le message entrant sur le thread Agent.
Grâce à `originAlertId`, une relance du type « Et pour mon cacao ? » retrouve le
contexte de l'alerte (contenu, date, provenance, zones ciblées via
`resolveAlertContext`) sans que l'agriculteur ait à le répéter.

## 9. Boucle feedback linguistique

`language/feedback.ts` et `language/promote.ts` (capability
`linguistic.validate`) :

1. `submitFeedback` : crée un `linguisticFeedback` en `needs_review`, version 1.
2. `setFeedbackStatus` : le validateur passe la revue vers `validated` (ou
   `rejected`).
3. `promoteToGlossary` / `promoteToCorpus` : seule une feedback `validated` peut
   être promue. La promotion **appende toujours une nouvelle version** du terme
   de glossaire ou de l'exemple de corpus ; la version précédente n'est jamais
   écrasée, l'historique reste auditable.

## 10. Audit et trace d'exécution

- `lib/audit.recordAudit` écrit un `auditLogs` pour toute opération sensible
  (activation d'organisation, création/publication d'alerte, publication météo,
  ingestion de source, promotion linguistique, mutations AIOPS...). `before`/
  `after` sont des snapshots sérialisés non sensibles.
- `lib/trace.ts` + `lib/traceWrite.ts` écrivent la trace d'exécution : on
  enregistre le CHEMIN d'exécution (étapes, outils, sources, versions, gardes,
  métriques), **jamais le raisonnement privé (chain-of-thought) du modèle**. Les
  actions passent par des internal mutations (`openTrace`, `addTraceStep`,
  `closeTrace`, `logError`) car elles n'ont pas de `ctx.db`.
- Taxonomie d'erreur canonique dans `lib/errors.ts` (`ERROR_TYPES` :
  ASR_ERROR, TRANSLATION_ERROR, RAG_ERROR, SOURCE_ERROR, TOOL_ERROR,
  LLM_HALLUCINATION, OUTDATED_DATA, TTS_PRONUNCIATION, PERMISSION_ERROR,
  DELIVERY_ERROR, INTERNAL_ERROR). `WouriError` porte le code et un message sûr.

## 11. Anti-hallucination

Contrat d'outil partagé (`tools/types.ts`) : chaque outil métier renvoie soit
`ok` avec données + provenance, soit `insufficient_evidence` avec une raison. Un
outil n'invente jamais : l'absence de source produit une abstention.

- `getWeather` lit seulement une observation SODEXAM fraîche ; sinon abstention.
- `searchKnowledge` cherche uniquement les namespaces visibles, filtrés par
  zone/culture/langue ; aucun passage au-dessus du seuil -> abstention (le LLM
  n'est jamais nourri d'un contexte vide à compléter).
- `getFarmerProfile` passe par `authorizeResource` : un id deviné d'une autre
  organisation échoue fail-closed.

Le pipeline `pipeline/answer.answerFarmerQuestion` (action) orchestre :
autorisation (`knowledge.read`), ouverture de trace, appel de l'outil selon
l'intent (weather/agronomy) et, **si aucune source ne soutient la question,
ABSTENTION** (`insufficient_evidence`) plutôt qu'une invention. Chaque run est
tracé avec ses étapes outil et garde, et clos en `succeeded` ou `abstained`.

## 12. Frontière FastAPI (calcul) vs Convex (données/temps réel)

```
        Client / WhatsApp / IVR / consoles
                     |
     +---------------+-------------------+
     |                                   |
     v                                   v
+-----------------------------+   +-----------------------------+
|  FastAPI  (CALCUL)          |   |  Convex  (DONNEES / RT)     |
|  - ASR / NLU / LLM          |   |  - Better Auth (identite)   |
|  - TTS / audio / FFmpeg     |   |  - RBAC + peri. (authorize) |
|  - orchestration modeles    |   |  - farmers / alerts / conv. |
+--------------+--------------+   |  - RAG (namespaces)         |
               |                  |  - Agent threads / contexts |
        etat des jobs             |  - knowledge / weather      |
               v                  |  - audit / execution trace  |
+-----------------------------+   |  - config / registres       |
|  Worker Dokploy (CPU lourd) |   +--------------+--------------+
|  ASR / FFmpeg / TTS         |                  |
|  -> reporte jobRecords ---> |------------------+
+-----------------------------+                  |
                                                 v
                                +-----------------------------+
                                |  PostgreSQL / pgvector      |
                                |  corpus IVR historique      |
                                |  (jusqu'a migration dediee) |
                                +-----------------------------+
```

Règles de frontière : aucune écriture double entre ces magasins ; Convex ne fait
pas de calcul lourd ; FastAPI et le worker ne tiennent pas l'état métier
autorisé (ils le lisent/écrivent via Convex) ; PostgreSQL/pgvector reste
propriétaire du corpus IVR existant jusqu'à une décision de migration séparée.
