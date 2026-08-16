# Matrice des permissions WOURI

Matrice dérivée directement de `ROLE_PRESETS` dans
`convex/authz/capabilities.ts`. Elle est la source de vérité pour le
provisioning, le seed et les tests, qui partagent tous ce même objet : la
matrice ne peut donc pas dériver du code.

Convention : « ✓ » = capability présente dans le preset ; case vide = absente.
`adcAdmin` reçoit `ALL_CAPABILITIES`, donc toutes les capabilities.

## Rôles

- `adcAdmin` : opérateur plateforme ADC, administration complète.
- `sodexamOperator` : fournisseur de données météo et diffuseur d'alertes.
- `cnraOperator` : fournisseur de connaissances agronomiques.
- `clientAdmin` : organisation cliente (coopérative/ONG), gère ses agriculteurs.
- `clientOperator` : opérateur d'une organisation cliente, périmètre réduit.
- `linguist` : validateur linguistique, cantonné à la console de validation.

## Matrice

### Plateforme et organisation

| Rôle | platform.manage | organization.read | organization.manage | organization.members.manage | entitlements.manage |
| --- | :---: | :---: | :---: | :---: | :---: |
| adcAdmin | ✓ | ✓ | ✓ | ✓ | ✓ |
| sodexamOperator |  | ✓ |  |  |  |
| cnraOperator |  | ✓ |  |  |  |
| clientAdmin |  | ✓ | ✓ | ✓ |  |
| clientOperator |  | ✓ |  |  |  |
| linguist |  | ✓ |  |  |  |

### Agriculteurs et consentements

| Rôle | farmers.read | farmers.write | consents.write |
| --- | :---: | :---: | :---: |
| adcAdmin | ✓ | ✓ | ✓ |
| sodexamOperator |  |  |  |
| cnraOperator |  |  |  |
| clientAdmin | ✓ | ✓ | ✓ |
| clientOperator | ✓ | ✓ |  |
| linguist |  |  |  |

### Alertes

| Rôle | alerts.create | alerts.publish | alerts.read |
| --- | :---: | :---: | :---: |
| adcAdmin | ✓ | ✓ | ✓ |
| sodexamOperator | ✓ | ✓ | ✓ |
| cnraOperator | ✓ |  | ✓ |
| clientAdmin | ✓ | ✓ | ✓ |
| clientOperator |  |  | ✓ |
| linguist |  |  |  |

### Connaissances et météo

| Rôle | weather.publish | sources.publish | knowledge.ingest | knowledge.publish | knowledge.read |
| --- | :---: | :---: | :---: | :---: | :---: |
| adcAdmin | ✓ | ✓ | ✓ | ✓ | ✓ |
| sodexamOperator | ✓ | ✓ |  |  | ✓ |
| cnraOperator |  | ✓ | ✓ | ✓ | ✓ |
| clientAdmin |  |  |  |  | ✓ |
| clientOperator |  |  |  |  | ✓ |
| linguist |  |  |  |  | ✓ |

### Analytics, linguistique, AIOps, audit

| Rôle | analytics.read | linguistic.validate | aiops.read | aiops.replay | featureflags.manage | audit.read |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| adcAdmin | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| sodexamOperator | ✓ |  |  |  |  |  |
| cnraOperator | ✓ |  |  |  |  |  |
| clientAdmin | ✓ |  |  |  |  |  |
| clientOperator | ✓ |  |  |  |  |  |
| linguist |  | ✓ |  |  |  |  |

Note : `featureflags.manage` garde aussi les registres versionnés (création et
activation de `promptVersions`, `policyVersions`, `modelConfigs` dans
`convex/aiops/registry.ts`), en plus des feature flags. Seul `adcAdmin` la
détient.

## Presets par type d'organisation

`PRESETS_BY_KIND` (`convex/organizations/provisioning.ts`) décide, à
l'activation d'une organisation, quelles politiques de rôle sont provisionnées :

| Type d'organisation (`kind`) | Presets provisionnés |
| --- | --- |
| adc | adcAdmin |
| sodexam | sodexamOperator |
| cnra | cnraOperator |
| cooperative | clientAdmin, clientOperator |
| ngo | clientAdmin, clientOperator |
| other | clientOperator |

Le preset `linguist` n'est provisionné par AUCUN `kind`. Il est ajouté
séparément (par ex. le seed via `ensureLinguistPolicy`, appliqué à
`demo-cnra`). Une organisation ne reçoit jamais de droits implicites :
l'activation (`activateOrganization`, capability `platform.manage`) est une
étape opérateur explicite qui crée le profil et les politiques, puis fait passer
le profil de `provisioning` à `active`.

## Périmètres (scopes)

Toute autorisation est d'abord bornée par l'**organisation**, toujours dérivée
côté serveur (session Better Auth validée, jamais un argument client). En plus :

- `organizationRolePolicies.scopeMode` vaut `organization` (accès à toute
  l'organisation) ou `restricted`.
- Quand une exigence porte un `scope` et que la policy est `restricted`, l'accès
  n'est accordé que si un `membershipScopeGrants` correspond au périmètre
  demandé : `scopeType` zone / crop (culture) / group, `scopeKey` associé, avec
  `expiresAt` optionnel. En mutation, un grant expiré est refusé (horloge
  serveur) ; en query, seul un grant sans expiration compte (une query réactive
  ne peut pas réévaluer une fenêtre temporelle).
- Les presets du seed créent des policies `scopeMode: organization` ; les
  périmètres restreints se posent via `grantMemberScope`.

## Principe fail-closed

`evaluateAuthorization` (`convex/authz/policy.ts`) n'accorde l'accès que si TOUT
est vérifié, dans l'ordre : organisation active, session non expirée, membre
actif, assignation active, policy chargée, permission présente, périmètre requis
satisfait, entitlement encore valide. Le moindre échec renvoie `null`, ce qui
lève un déni `Unauthorized`. Aucune information n'est divulguée : un identifiant
d'une autre organisation ne confirme jamais son existence.

`authorizeResource` renforce l'isolation : après autorisation, il charge la
ressource et vérifie que son `organizationId` correspond à l'organisation
autorisée, sinon déni. Un id deviné appartenant à une autre organisation échoue
fail-closed.

## Tests anti-fuite

`convex/tenancy/isolation.test.ts` prouve l'isolation au niveau de la donnée
(DAT-07 / G03 / G06), indépendamment de la couche session :

- un agriculteur d'une organisation est invisible à une autre organisation ;
- le ciblage d'audience reste borné à l'organisation (un agriculteur d'une autre
  org partageant la même zone n'est jamais ciblé) ;
- une version de source d'une autre organisation n'est pas visible, alors qu'une
  source globale l'est.

Ces tests tournent avec `pnpm convex:test:permissions` (couvre `convex/tenancy`
et `convex/authz`). Ils sont un gate obligatoire avant staging/production, avec
les autres tests négatifs (révocation de membre, périmètre vide, entitlement
expiré, rejeu de callback) listés dans `convex-foundation.md`.
