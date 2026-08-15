# ADR-0030 — Plateforme API Wourri (produit API + SaaS multi-tenant) sur socle Convex

**Statut** : accepté
**Date** : 2026-08-14 (rédaction) · **Accepté le** : 2026-08-15
**Auteur(s)** : Claude (assistant IA)
**Valideur** : Issouf (ouedraogoissouf2012)

> Renuméroté depuis **0026** à l'acceptation (le n° 0026 était en collision avec
> `0026-perimetre-langues-pilote`, branche non mergée). Voir « Note de numérotation ».

---

## Contexte

L'API Wourri (`wouri-api`, FastAPI) est aujourd'hui **interne** : un seul client légitime
(le `whatsapp-server`) l'appelle via une **unique clé partagée `X-API-Key`**, sans notion
d'utilisateur, d'organisation, de rôle, de scope ni de quota. Elle n'est **pas exposée**
publiquement (décision « interne seulement » du déploiement — cf. ADR-0024 déploiement Dokploy,
`docs/RAPPORT_DEPLOIEMENT_PROD_2026-08-14.md`).

L'utilisateur souhaite en faire une **plateforme en ligne** : APIs **exposées** et accessibles
**par authentification** et **par degrés de permission**, avec un **portail développeur web
complet**, selon l'**architecture la plus robuste et prévoyante**.

**Fait déterminant** : le chantier **Convex #372 / PR #373** (branche
`feat/372-convex-foundation`, draft) construit déjà un socle multi-tenant complet — **Better Auth**
(users/sessions/organisations), **RBAC** (`convex/authz/capabilities.ts`, 23 capacités, 6 rôles),
**scopes fins** (zone/culture/groupe) et **quotas/entitlements par plan** (`schema/billing.ts`).
L'ADR **`transition-convex-multitenant`** (accepté 2026-08-11, présent sur cette branche)
acte : **Convex = plan de données + plan d'autorisation ; FastAPI = plan de calcul**. Ce socle
sécurise cependant, à ce jour, **ses propres fonctions métier** — pas encore un gateway exposant
l'API ML de FastAPI comme produit.

**Contraintes projet pertinentes** (`docs/constraints.md`) : qualité > vitesse ; pas de raccourci ;
ADR avant tout code structurant ; conformité **ARTCI** (données CI). État actuel vérifié (3
explorations) : `app/security.py:49` (clé unique), rate limiting piloté par `RATE_LIMIT`
(ADR-0018 accepté 2026-08-14), CORS absent en prod, `/docs` ouvert partout, aucune table
users/rôles/tenants/clés.

> **Note de numérotation (corrigée à l'acceptation, vérifiée sur les refs `origin`)** :
> - **0024** est en collision entre `0024-deploiement-wourri-dokploy` (**mergé sur `APIPy`**,
>   canonique) et `0024-transition-convex-multitenant` (branche `feat/372`, **non mergée**). C'est
>   ce **dernier** qui devra prendre un numéro libre à son merge — **le déploiement conserve 0024**.
> - **0025** est déjà `retention-logs-pii-artci` (mergé). *(L'ancienne note « renuméroter le
>   déploiement en 0025 » était erronée et est annulée.)*
> - **0026** était revendiqué par le présent ADR **et** par `0026-perimetre-langues-pilote` (non
>   mergé) → le présent ADR est renuméroté **0030** (prochain numéro libre sur prod après 0029).

## Questions posées avant la décision

1. Périmètre : exposer les APIs ML comme produit, la plateforme métier multi-tenant, ou les deux ?
2. Degrés de permission : rôles, scopes, quotas — lequel / lesquels ?
3. Positionnement vis-à-vis du socle Convex #372 (bâtir dessus vs couche autonome) ?
4. Interface : API sécurisée seule vs portail développeur complet ?

Réponses obtenues (transcript session 2026-08-14) :

- Q1 → **Les deux** : produit API (ASR/TTS/traduction/chat dioula) **et** SaaS métier multi-tenant.
- Q2 → **Mix des trois** : rôles (RBAC) **+** scopes par fonctionnalité **+** quotas/paliers.
- Q3 → **Bâtir sur Convex #372** (recommandé, validé).
- Q4 → **Plateforme web complète** (portail développeur : login, gestion clés/quotas, docs).

## Options étudiées

### Option A — Plateforme greffée sur le socle Convex #372 (retenue)

- **Description** : Convex reste le **plan identité + autorisation + tenancy + quotas**. On y ajoute
  un **domaine `apiKeys`** (émission/révocation, scoppées par org, liées au plan) + une fonction
  **`verifyApiKey`**. FastAPI reste le **plan de calcul**, **exposé publiquement** (Traefik + TLS)
  via un routeur **`/v1`** ; une nouvelle dépendance « clé produit » **valide chaque appel contre
  Convex** et applique **scopes + quotas** (rate-limit à magasin partagé). Le portail développeur
  (front Better Auth) sert la gestion des clés/usage/docs **et** les surfaces du SaaS métier.
- **Avantages** : réutilise l'auth/RBAC/scopes/quotas **déjà construits** (23 capacités, 6 rôles,
  entitlements) ; **une seule source de vérité d'identité** ; cohérent avec l'ADR convex-multitenant ;
  le plus **robuste et prévoyant** (multi-tenant natif, anti-fuite cross-tenant testé).
- **Inconvénients** : **dépend d'une PR draft** (#372) non mergée/non déployée, portée par un autre
  contributeur → coordination + prod-readiness (provider email, gates conformité) préalables.
- **Coût** : moyen-élevé (intégration FastAPI↔Convex + expo + portail), mais **zéro duplication d'auth**.
- **Compatibilité contraintes** : ✅ pas de duplication, aligné vision Convex, conforme « prévoyant ».

### Option B — Couche auth/RBAC autonome sur FastAPI

- **Description** : implémenter dans FastAPI un système propre — tables `users`/`roles`/`api_keys`
  en PostgreSQL, JWT/OAuth2, scopes, quotas, + un portail séparé — **indépendamment de Convex**.
- **Avantages** : indépendant de la PR draft ; **time-to-market** plus court pour une v1 ; maîtrise
  bout-en-bout dans un seul langage/stack.
- **Inconvénients** : **duplique** l'auth/RBAC/tenancy que Convex construit déjà → **deux systèmes
  d'identité** à maintenir et à réconcilier ; contredit l'ADR convex-multitenant (Convex = plan d'autz) ;
  dette et risque de divergence.
- **Coût** : moyen à court terme, **élevé à long terme** (double maintenance, migration ultérieure).
- **Compatibilité contraintes** : ⚠️ va à l'encontre de la trajectoire Convex ; « prévoyant » discutable.

### Option C — Gateway/API-management tiers devant FastAPI

- **Description** : placer un gateway (Kong, Tyk, ou un SaaS type Zuplo/Apigee) devant FastAPI pour
  gérer clés, scopes, quotas et portail développeur, avec sa propre base d'identité.
- **Avantages** : portail + quotas + clés « clés en main » ; découplé du code applicatif.
- **Inconvénients** : **3ᵉ système d'identité** (gateway) à réconcilier avec Convex **et** FastAPI ;
  verrou vendor (SaaS) ou surcoût ops (self-host Kong) ; multi-tenant métier (orgs/rôles projet)
  **hors périmètre** du gateway → il faudrait quand même Convex pour le SaaS.
- **Coût** : licence/ops + intégration ; **redondant** avec Convex.
- **Compatibilité contraintes** : ⚠️ souveraineté/verrou vendor ; redondance avec l'existant.

### Comparatif

| Critère | A (sur Convex) | B (FastAPI autonome) | C (gateway tiers) |
|---|---|---|---|
| Réutilise l'auth/RBAC/quotas existants | ✅ | ❌ (réécrit) | ❌ (3ᵉ système) |
| Duplication d'identité | Aucune | 2 systèmes | 3 systèmes |
| Cohérence ADR convex-multitenant | ✅ | ❌ | ⚠️ |
| Multi-tenant métier (orgs/rôles) | ✅ natif | à construire | hors périmètre |
| Time-to-market v1 | Moyen (dépend #372) | **Court** | Moyen |
| Robustesse / « prévoyant » | **Élevée** | Moyenne | Moyenne |
| Verrou / souveraineté | Faible | Faible | Élevé (vendor) |
| Dépendance externe | PR draft #372 | Aucune | Produit tiers |

## Décision

**Option retenue** : **A — plateforme greffée sur le socle Convex #372** (validée par l'utilisateur
le 2026-08-14, acceptée le 2026-08-15).

**Justification** : c'est la seule option qui satisfait « les deux périmètres » (produit API **et**
SaaS métier) **et** le « mix rôles+scopes+quotas » **sans dupliquer** l'auth/RBAC/tenancy que Convex
construit déjà, tout en restant aligné sur l'ADR convex-multitenant (Convex = plan d'autorisation,
FastAPI = plan de calcul). C'est le choix le plus **robuste et prévoyant** demandé. Le principal
risque — la dépendance à une PR draft — est traité par un **séquencement en phases** (Phase 1 =
rendre le socle Convex prod-ready avant d'exposer quoi que ce soit).

**Périmètre d'acceptation (précision)** : cet ADR acte la **direction** (plateforme produit + SaaS
sur Convex). La mise en œuvre est **en phases**. En particulier, l'**exposition du moteur pour la
démo** (Traefik + TLS ; `/api/tts/`, `/api/chat/`, `/health`, `/static/audio/` derrière l'actuel
`X-API-Key`) est une **première tranche minimale** qui **peut précéder** le portail développeur et
le socle Convex prod-ready — elle ne dépend ni de l'un ni de l'autre. Le produit complet (`/v1`,
clés produit scoppées, quotas, portail) suit les phases ci-dessous.

## Conséquences

- **Positives** :
  - Une seule source de vérité d'identité/permissions ; multi-tenant natif et anti-fuite testé.
  - `X-API-Key` WhatsApp **inchangé** (auth de *service*), distinct des **clés produit** (org/user).
  - Exposition durcie en une fois (Traefik+TLS, CORS, en-têtes/HSTS, `/v1`, rate-limit partagé).

- **Négatives assumées** :
  - **Dépendance dure** à la PR draft #372 (non mergée/déployée, dev-only) → Phase 1 préalable +
    coordination avec l'auteur.
  - Latence ajoutée par la vérification de clé côté Convex (mitigée par cache court + jeton signé).
  - Nouveau front (portail) à construire et maintenir.

- **Migration / travail induit** (en phases) :
  1. Convex : domaine `apiKeys` + `verifyApiKey` (réutilise `authz/*`, `entitlements`).
  2. FastAPI : dépendance `require_product_key`, routeur `/v1`, enforcement scopes+quotas,
     rate-limit à magasin partagé, CORS + en-têtes, `--forwarded-allow-ips`, gating `/docs`
     (s'appuie sur ADR-0018 rate limiting, déjà accepté).
  3. Infra Dokploy : domaine public + Traefik + TLS pour `wouri-api` (+ magasin rate-limit partagé).
     La **tranche démo** (expo TLS des chemins ci-dessus derrière `X-API-Key`) peut se faire ici en premier.
  4. Portail développeur (front Better Auth) : clés, usage/quotas, docs, surfaces SaaS.
  5. **Hygiène de numérotation ADR** : le présent ADR passe de 0026 à **0030** (collision 0026) ;
     l'ADR `transition-convex-multitenant` (#372) prendra un numéro libre à son merge (collision 0024,
     le déploiement conservant 0024).

- **Verrous futurs** :
  - L'API produit devient un **contrat public** (`/v1`) → versionnage et compat ascendante à tenir.
  - Couplage FastAPI→Convex pour l'autorisation (réversible mais structurant).

- **Souveraineté / conformité** : PII/tenants dans Convex → **résidence & rétention** à valider
  (ARTCI, issue #215) **avant** toute donnée de production (**gate go-live bloquant**, Phase 5).

## Références

- Transcript session 2026-08-14 (questions/réponses de cadrage).
- Convex #372 / PR #373, branche `feat/372-convex-foundation` ; `docs/wouri/convex-*.md` ;
  ADR **`transition-convex-multitenant`**.
- `docs/adr/0018-strategie-rate-limiting-api.md` (rate limiting, accepté) ; issue #307.
- `docs/adr/0012-securite-whatsapp-server.md` (contrat X-API-Key, CORS) ; ADR-0017 (dashboard) ;
  ADR-0024 (déploiement Dokploy, « interne only » que le présent ADR lève pour le périmètre exposé) ;
  ADR-0025 (rétention logs PII / ARTCI).
- `wourri/openapi.json` (spec de référence produit : `/v1`+`/v2`, `x-api-key`, portail).
- État actuel : `app/security.py`, `app/config.py`, `app/main.py`, `app/routers/*`.

## Historique

- 2026-08-14 — rédaction initiale (proposé, sous le n° 0026).
- 2026-08-15 — **accepté** (Issouf). Renuméroté **0026 → 0030** (collision avec
  `0026-perimetre-langues-pilote`). Note de numérotation corrigée (le déploiement conserve 0024 ;
  `transition-convex-multitenant` à renuméroter à son merge ; l'ancienne mention « déploiement → 0025 »
  était erronée, 0025 = rétention logs PII). Précision de périmètre ajoutée (démo = tranche minimale).
