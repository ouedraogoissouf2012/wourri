# Runbook Convex WOURI

Commandes reproductibles pour opérer le socle Convex, sans aucun secret. Toutes
les valeurs de secrets (clés, tokens) restent hors de Git, des tickets et de
cette documentation : seuls leurs NOMS de variable apparaissent ici.

Package manager : `pnpm` exclusivement. Les scripts sont définis dans
`package.json`.

## 1. Développement local

```powershell
pnpm install --frozen-lockfile
pnpm convex:dev            # convex dev : sync schéma + fonctions, tail logs
```

`convex dev` crée ou met à jour `.env.local` (ignoré par Git) avec
`CONVEX_DEPLOYMENT`, `CONVEX_URL`, `CONVEX_SITE_URL`.

Vérifier un changement sans processus long :

```powershell
pnpm convex:check         # convex dev --once (sync unique)
pnpm convex:codegen       # convex codegen : régénère convex/_generated
pnpm typecheck            # tsc --noEmit -p convex/tsconfig.json
```

Après une modification des plugins ou des champs Better Auth, régénérer le
schéma Better Auth local puis resynchroniser :

```powershell
pnpm dlx @better-auth/cli@latest generate --config ./convex/betterAuth/auth.ts --output ./convex/betterAuth/schema.ts --yes
pnpm convex:check
```

## 2. Sélection staging vs production

### Environnements provisionnés (team `djedjelipatrick`)

Isolation stricte par PROJET Convex (DAT-01) :

| Environnement | Projet Convex (slug) | Déploiement ciblé | URL |
| --- | --- | --- | --- |
| Développement local | `wouri` | `dev:avid-badger-569` | (dev, par développeur) |
| Staging | `wouri-staging-75d3f` | prod du projet staging | `https://spotted-chickadee-971.convex.cloud` |
| Production | `wouri-prod` | prod du projet production | `https://grand-alligator-409.convex.cloud` |

Chaque environnement est un **projet Convex distinct** : schéma, données et
secrets totalement isolés (DAT-01). Le `BETTER_AUTH_SECRET` est différent dans
chacun. `SITE_URL` reste à poser dans chaque environnement quand les frontends
correspondants existeront.

| Environnement | `WOURI_ENV` | Données |
| --- | --- | --- |
| Staging | `staging` | seed de démonstration chargé (6 organisations, sources, fixture météo) |
| Production | `production` | **vide** — aucune donnée de démonstration (§38) |

`WOURI_ENV=production` **arme le garde-fou** : `seedStaging` y échoue avec
« Seed refuse en production » (vérifié). Ne jamais changer cette valeur pour
contourner le garde-fou.

Attention au **slug** du projet : celui du staging porte un suffixe
(`wouri-staging-75d3f`). Utiliser le slug exact, sinon la CLI crée un nouveau
projet au lieu de lier l'existant.

```powershell
# Sélectionner un environnement (remplacer <slug> par le slug exact)
npx convex dev --configure existing --team djedjelipatrick --project <slug> --dev-deployment cloud --once
npx convex deploy --yes     # déploie vers la prod du projet sélectionné

# TOUJOURS revenir sur le dev après une opération staging/production
npx convex dev --configure existing --team djedjelipatrick --project wouri --dev-deployment cloud --once
```

Poser un secret : passer la valeur **sans guillemets** (des guillemets autour de
la valeur seraient stockés dans le secret lui-même). Préférer une valeur
hexadécimale, sans caractère à échapper :

```powershell
npx convex env set --prod BETTER_AUTH_SECRET <valeur_hex_64>
```

### Mécanique de sélection

Le déploiement ciblé dépend du contexte Convex (variable `CONVEX_DEPLOYMENT`) et
du flag `--prod`. Chaque environnement a ses variables d'environnement propres,
posées côté Convex (jamais dans un `.env` commité).

```powershell
# Staging (déploiement non-prod configuré pour wouri-staging)
pnpm convex:deploy:staging          # convex deploy vers le déploiement courant

# Production (déploiement prod du projet)
pnpm exec convex deploy --prod
```

Poser une variable par environnement (exemples de NOMS uniquement) :

```powershell
# Staging : agit sur le déploiement non-prod courant
pnpm exec convex env set SITE_URL https://staging.example
pnpm exec convex env set WOURI_ENV staging

# Production : le flag --prod cible le déploiement de production
pnpm exec convex env set --prod SITE_URL https://app.example
pnpm exec convex env set --prod WOURI_ENV production
pnpm exec convex env set --prod BETTER_AUTH_SECRET <valeur-generee-hors-git>
```

Lister/lire les variables d'un environnement :

```powershell
pnpm exec convex env list            # non-prod
pnpm exec convex env list --prod     # production
```

## 3. Variables d'environnement attendues

Deux périmètres distincts. Ne pas les confondre.

### Réellement utilisées aujourd'hui par le socle Convex

Le code Convex ne référence, à ce jour, que ces variables (vérifié dans
`convex/`) :

- `SITE_URL` : origine de confiance de Better Auth (`convex/auth.ts`, via
  `baseURL`/`trustedOrigins`). En dev, l'email/mot de passe n'est activé que si
  `SITE_URL` vaut `http://localhost:3000`.
- `BETTER_AUTH_SECRET` : secret Better Auth. Configuré par déploiement, jamais
  commité.
- `WOURI_ENV` : garde-fou du seed. Le seed refuse de s'exécuter quand
  `WOURI_ENV === "production"` (`convex/testing/orgHelpers.guardNotProduction`).
- `CONVEX_DEPLOYMENT`, `CONVEX_URL`, `CONVEX_SITE_URL` : posées automatiquement
  par `convex dev` dans `.env.local`.

### Préparées pour plus tard (pas encore lues par le code Convex)

Ces NOMS sont anticipés par l'architecture cible mais **ne sont référencés nulle
part dans `convex/` aujourd'hui**. Ne pas les poser tant que le code qui les
consomme n'existe pas :

- `OPENROUTER_API_KEY` : fournisseur LLM/embedding de production. Aujourd'hui le
  RAG utilise un modèle d'embedding local déterministe (`rag/embeddingModel.ts`),
  aucune clé requise.
- `WHATSAPP_*` : passerelle de livraison. La publication d'alerte matérialise les
  livraisons en `created` sans appel externe ; le mapping WhatsApp -> agriculteur
  et le callback sont des gates non franchis.
- `SODEXAM_*` : ingestion météo live. Aujourd'hui la météo vient de fixtures de
  staging (`dataOrigin: staging_fixture`) ou d'une publication manuelle.
- `LANGFUSE_*` : télémétrie externe. Le champ `externalTelemetryId` de
  `executionTraces` est prévu, mais aucune intégration n'est branchée.

Note : les fichiers `.env.example`, `.env.staging.template`, `.env.prod.template`
à la racine concernent le service FastAPI/Python et son infrastructure Docker
(par ex. `POSTGRES_*`, `WOURI_API_KEY`, `DEEPSEEK_API_KEY`, `NEMO_MODEL_PATH`,
`PIPER_*`, `ENABLE_MMS_DYU`, `ALLOWED_ORIGINS`). Ce ne sont PAS des variables
Convex : le socle Convex ne les lit pas.

## 4. Smoke tests

```powershell
pnpm test:convex                     # vitest run : toute la suite Convex
pnpm convex:test:permissions         # convex/tenancy + convex/authz (RBAC + anti-fuite)
pnpm convex:test:alerts              # convex/alerts (flux alerte -> livraison -> réponse)
pnpm convex:test:knowledge           # convex/knowledge + convex/rag + convex/weather
```

`convex:test:permissions` couvre notamment `convex/tenancy/isolation.test.ts`
(tests négatifs inter-organisations : un agriculteur invisible à une autre org,
audience bornée à l'org, source d'une autre org non visible mais globale
visible) et la logique de `authz/policy`.

## 5. Seed staging

Le seed est une internal mutation `internal.testing.seed.seedStaging`. Il
construit un jeu de démo idempotent (organisations `demo-*`, membres/rôles,
entitlements manuels, agriculteurs, sources de provenance globales SODEXAM/CNRA,
une fixture météo `abidjan-nord`). Chaque entité se cale sur un identifiant
stable, donc une réexécution ne duplique rien.

Garde-fou : `seedStaging` appelle `guardNotProduction()`, qui **lève une erreur
quand `WOURI_ENV === "production"`**. Le seed ne doit JAMAIS tourner en
production.

Aperçu sans écriture (dry-run) puis exécution, depuis le dashboard Convex ou en
CLI (jamais avec `--prod`) :

```powershell
# Dry-run : exécute seulement le garde-fou et renvoie le plan
pnpm exec convex run testing:seed:seedStaging '{"dryRun": true}'

# Exécution réelle sur staging (déploiement non-prod courant)
pnpm exec convex run testing:seed:seedStaging
```

Via le dashboard Convex : ouvrir le déploiement staging, section Functions,
exécuter `testing/seed:seedStaging` (option `dryRun` d'abord). Ne jamais lancer
cette fonction sur le déploiement de production.

## 6. Inspection des logs

```powershell
pnpm exec convex logs                # flux de logs, déploiement non-prod
pnpm exec convex logs --prod         # flux de logs, production
```

Le dashboard Convex expose aussi Logs, Data (tables), Functions et History par
déploiement. Pour l'observabilité applicative, les tables `executionTraces`,
`executionTraceSteps`, `errorReports` et `auditLogs` sont lisibles via les
queries AIOPS (`aiops.read`, `audit.read`) sans accès brut à la base.

## 7. Retour en arrière (rollback)

Le schéma WOURI est **additif** : les évolutions ajoutent des tables, des index
ou des champs optionnels, sans suppression destructive. Un redéploiement d'une
version antérieure du code reste donc compatible avec les données existantes.

```powershell
# Revenir à une version antérieure : re-checkout du code visé puis redeploy
git checkout <commit-ou-tag>
pnpm convex:deploy:staging           # staging
# ou
pnpm exec convex deploy --prod       # production
```

Règles de sécurité :

- Ne JAMAIS exécuter le seed en production.
- Ne PAS copier les données de production vers staging (aucun export prod ->
  staging).
- Migrations non destructives uniquement : pas de suppression de table ni de
  champ requis ajouté sans valeur par défaut. En cas de doute, ajouter un champ
  optionnel et migrer les données par mutation idempotente, plutôt que de
  recréer la table.
- Les gates de mise en staging/production (résidence des données, facturation,
  mapping WhatsApp, rétention, tests négatifs verts, runbook de migration par
  agrégat) sont détaillés dans `convex-foundation.md` et restent obligatoires.
