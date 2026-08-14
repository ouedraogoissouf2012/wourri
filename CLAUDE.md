# CLAUDE.md — `whatsapp-server/` (Wourri)

Guide pour Claude Code (claude.ai/code) lors de modifications de ce dossier.

## Vue d'ensemble

Ce dossier est le **serveur WhatsApp de Wourri**, un bot agricole bambara/dioula
pour la Côte d'Ivoire et le Mali.

- **Technologie** : Node.js + Express + [@whiskeysockets/baileys](https://github.com/WhiskeySockets/Baileys) (lib non-officielle WhatsApp Web)
- **Rôle** : passerelle entre les utilisateurs WhatsApp et l'API Wourri (FastAPI Python, voisin)
- **Fichier prod actif** : [`app-baileys.js`](app-baileys.js) (1155 lignes, à refactorer en phase ultérieure)
- **Port par défaut** : `3001` (override possible via `.env` `PORT=...`)

## Décision projet — pourquoi Baileys et pas WhatsApp Cloud API officielle

Validé par Ruben le **2026-05-05** :

- **Maintenant** : Baileys (lib non-officielle, gratuite, fonctionne)
- **Plus tard** : migration vers WhatsApp Cloud API officielle Meta quand le budget le permettra (compte Business vérifié, BSP, conformité)

Mission immédiate : **rendre Baileys production-ready, robuste, sans problème**.
Risque connu : Baileys peut entraîner un ban du compte business à grande échelle.
À chaque feature WhatsApp future, penser **rétrocompatibilité Cloud API** pour
éviter une réécriture lors de la migration éventuelle.

## Démarrage

```bash
# 1. Installation
npm install

# 2. Configurer les variables d'environnement
cp .env.example .env
# Éditer .env :
#   PORT=3001
#   WOURI_API_URL=http://localhost:8000
#   WOURI_API_KEY=<clé secrète backend>
#   NODE_ENV=development

# 3. Démarrage
npm start
# → Affiche un QR code à scanner avec WhatsApp mobile (Paramètres → Appareils liés)

# 4. Production
NODE_ENV=production npm run production
```

## Architecture

```
whatsapp-server/
├── app-baileys.js         # Serveur principal (Baileys + onboarding 4 étapes)
├── lib/                   # Modules locaux
│   ├── reconnect.js       # Backoff exponentiel + decision logic (Phase 2)
│   ├── message_queue.js   # Queue persistante anti-perte (Phase 2)
│   ├── circuit_breaker.js # Circuit breaker pour API backend (Phase 2)
│   ├── logger.js          # Logger structuré pino JSON (Phase 3)
│   └── audio_cache.js     # Cache disque des audios d'excuse (fallback API down)
├── tests/                 # Tests unitaires (node:test natif)
│   ├── reconnect.test.js
│   ├── message_queue.test.js
│   ├── circuit_breaker.test.js
│   ├── logger.test.js
│   └── audio_cache.test.js
├── package.json           # Dépendances figées (versions exactes, pas de ^)
├── .env                   # Secrets (gitignored)
├── .gitignore
├── auth_baileys/          # Session WhatsApp persistante (gitignored)
├── temp_audio/            # Audios téléchargés temporairement (gitignored)
├── audio_cache/           # Cache local audios d'excuse pré-générés (gitignored)
├── user_preferences.json  # Préférences users (gitignored)
├── pending_messages.json  # Queue persistante messages (gitignored)
├── README.md              # Documentation utilisateur
└── CLAUDE.md              # Ce fichier
```

> **Note historique** : 13 fichiers hérités du projet "École Notification"
> Spring Boot ont été supprimés du repo en 2026-05-05 (PR [#115](https://github.com/ouedraogoissouf2012/wourri/pull/115)).
> L'historique reste disponible via `git log` si besoin de référence.

## Endpoints exposés

| Méthode | Route | Description |
|---|---|---|
| GET | `/` | Statut général + nombre d'utilisateurs |
| GET | `/status` | Statut connexion + QR code si nécessaire |
| GET | `/health` | Healthcheck enrichi : `status` + `reasons` + uptime + queue + circuit + version |
| GET | `/ready` | Kubernetes readiness probe : 200 si `status=ok`, 503 sinon |
| GET | `/users` | Liste anonymisée des utilisateurs (numéros tronqués) |
| GET | `/qr` | QR code data brut (JSON) |
| GET | `/qr-page` | Page HTML avec QR code visuel auto-refresh 5s |
| POST | `/logout` | Déconnexion + suppression `auth_baileys/` |

### Statut global `/health`

| Statut | Conditions |
|---|---|
| `unhealthy` | WhatsApp déconnecté OU circuit OPEN OU `queue.dead > 0` |
| `degraded` | Reconnexion en cours OU `queue.pending > 10` OU circuit HALF_OPEN |
| `ok` | Sinon |

Le champ `reasons[]` liste les causes (ex: `["api_circuit_open", "queue_pending_high=15"]`).

## Pipeline de traitement d'un message entrant

1. **Filtrage** : ignorer messages auto, groupes, statuts
2. **Onboarding** (étapes `NEW` → `WAITING_CITY` → `WAITING_LANGUAGE` → `COMPLETE`)
3. **Détection commande** : "changer ville", "changer langue", "réinitialiser"
4. **Si vocal** : téléchargement → transcription via API backend
   - Si user en mode `dioula` ou `both` → `/api/asr/transcribe-and-translate` (MMS Bambara)
   - Si user en mode `french` → `/api/stt/transcribe` (Whisper français)
5. **Appel backend** : `POST /api/chat/` avec `{message, city, language, bambara_text, user_id, include_audio: true}`
6. **Envoi réponse — règle "selon langue choisie"** (révisée 2026-05-06) :
   - `french` + entrée vocale → audio FR
   - `french` + entrée texte → texte FR
   - `dioula` (vocal ou écrit) → **TOUJOURS audio dioula** (fallback texte FR si TTS API down)
   - `both` (vocal ou écrit) → **texte FR + audio dioula** (combo, le meilleur des deux)

   **Justification UX** : les agriculteurs dioula sont souvent peu alphabétisés.
   L'audio est critique pour qu'ils accèdent au contenu. Le mode `both` envoie
   texte FR en bonus pour les bilingues qui veulent lire ET écouter.

   **Cette règle remplace la règle "selon format d'entrée" de PR #119** (qui supposait
   à tort qu'écrire = savoir lire). Tracé dans `memory/project_whatsapp_strategy_2026-05.md`.
7. **Feedback C4** (uniquement dioula/both) : prompt 👍/👎 → `POST /api/feedback/{positif|negatif}`

## Authentification backend

Le serveur signe ses appels à `wouri-api` (port 8000) avec un header `X-API-Key` :

```js
function authHeaders() {
    return WOURI_API_KEY ? { 'X-API-Key': WOURI_API_KEY } : {};
}
```

Si `NODE_ENV=production` et `WOURI_API_KEY` vide → warning au démarrage.

## Gestion de la session

- **Persistance** : `useMultiFileAuthState('./auth_baileys')` — sauvegarde
  automatique des credentials à chaque update via `creds.update`
- **Reconnexion** : automatique 3 secondes après une déconnexion non-volontaire
- **Logout** : supprimer `auth_baileys/` pour forcer un nouveau scan QR
- **Graceful shutdown** : SIGINT/SIGTERM sauvegardent `user_preferences.json`
  de manière synchrone avant exit

## Connaître l'écosystème Wourri

- API backend : `../wouri-api/` (FastAPI Python, port 8000)
- ADRs structurants : `../wouri-api/docs/adr/`
- Vision projet : `../wouri-api/docs/vision.md`
- Plan d'action : `../wouri-api/docs/PLAN_ACTION_2026-04.md`

## Règles de travail

### Plan-and-confirm strict

Toute modification non-triviale (refactor, ajout endpoint, changement deps)
passe par un plan validé explicitement avant code.

### Pas de raccourci

- ❌ Ne pas réintroduire `whatsapp-web.js` (remplacé par Baileys)
- ❌ Ne pas changer le port sans mettre à jour `.env.example` + ce CLAUDE.md
- ❌ Ne pas ajouter de fonctionnalité incompatible WhatsApp Cloud API
  (pour préserver la voie de migration future)

### Tests

- Tests unitaires Node : à créer dans une phase dédiée (Phase Tests, hors scope Phase 1)
- Tests manuels : envoyer un message à WhatsApp lié et vérifier les logs

### Dette technique connue

- **God file** : `app-baileys.js` ~1300 lignes — à décomposer (Phase Modularisation)
- **Pas de metrics Prometheus** : `/health` riche mais pas de `/metrics` scrape format
- ~~**Pas de retry automatique** des messages en queue~~ : **résolu #299** — après
  reconnexion, `lib/pending_replay.js` rejoue chaque message en attente contre
  `/api/chat/` et envoie la vraie réponse (au lieu d'une excuse « repose ta question »).
- **Nested folder pourri** : `whatsapp-server/whatsapp-server/` (issue P2-04, séparée)
- ~~`npm audit`~~ : **résolu Sprint A** (0 vulnérabilité, PR #141 + #142)
- ~~CORS permissif~~ : **résolu Sprint A** (allow-list via `ALLOWED_ORIGINS`, ADR-0012)
- ~~Pas de rate limiting~~ : **résolu Sprint A** (60 req/min/IP, ADR-0012)

Phases prévues / réalisées :
1. ✅ **Cleanup + Foundation** (mergé 2026-05-05, PR #115)
2. ✅ **Robustesse** : backoff exponentiel + queue persistante + circuit breaker (PR #117)
3. ✅ **UX Format adaptatif** : vocal→audio langue / écrit→texte FR (PR #119)
4. ✅ **Observabilité** : pino JSON + `/health` enrichi + `/ready`
5. ✅ **Sécurité** Sprint A : CORS strict + rate limiting + npm audit clean (ADR-0012, PRs #141/#142/#143)
6. ⏳ Tests d'intégration end-to-end + CI GitHub Actions
7. ⏳ Déploiement : Dockerfile + PM2/systemd + runbook
8. ⏳ Modularisation : décomposer `app-baileys.js`

### Sécurité — CORS et rate limiting (ADR-0012)

**CORS** : configurable via env `ALLOWED_ORIGINS` (liste séparée par virgules).
Si vide → mode strict (refus de toute origine cross-domain). Les routes
restent accessibles same-origin (curl, navigation directe, monitoring qui
n'envoie pas de header `Origin`).

```bash
# Exemple
ALLOWED_ORIGINS=https://dashboard.example.com,https://admin.wourri.ci
```

**Rate limiting** : 60 requêtes / minute / IP sur l'ensemble des routes
publiques (`/health`, `/qr`, `/qr-page`, `/status`, `/users`, etc.).
Dépassement → HTTP 429 avec `Retry-After` header. Headers `RateLimit-*`
standard exposés.

## Logging structuré (Phase 3)

### Configuration

Variables d'environnement :
- `LOG_LEVEL` : `trace | debug | info | warn | error | fatal | silent` (default `info`)
- `NODE_ENV=production` : force JSON pur (sinon pino-pretty si dispo)

### Usage dans le code

```js
const { logger } = require('./lib/logger');

// Simple message
logger.info('Démarrage serveur');

// Avec contexte structuré (préféré pour les events critiques)
logger.info({ userNumber, queueId }, '[QUEUE] Message ajouté');

// Erreur avec serialiser pino natif
logger.error({ err }, 'Erreur traitement message');

// Child logger (hérite du contexte)
const queueLogger = logger.child({ component: 'queue' });
queueLogger.info('event');  // contient component=queue
```

### Format de sortie (JSON ligne par ligne)

```json
{"level":30,"time":"2026-05-06T00:25:30.123Z","service":"wouri-whatsapp","userNumber":"u1","queueId":"m1","msg":"[QUEUE] Message ajouté"}
```

Parsable par Loki, Datadog, Elastic, CloudWatch, etc.

### En dev

Si `pino-pretty` est installé (devDependency optionnelle), l'output est colorisé et lisible.

```bash
npm install --save-dev pino-pretty
```

## Modules Phase 2 (lib/)

### `lib/reconnect.js`
Backoff exponentiel pour la reconnexion WhatsApp :
- Délais : 1s → 2s → 4s → 8s → 16s → 32s → 60s (cap)
- Limite : 10 tentatives consécutives (évite ban WhatsApp)
- Distinction codes récupérables vs non-récupérables (`loggedOut`, `badSession` → action humaine)

### `lib/message_queue.js`
Queue persistante anti-perte pour les messages utilisateurs :
- Persistence JSON (`pending_messages.json`)
- Sérialisation des writes (anti-race)
- Idempotent sur l'id Baileys (pas de duplicate)
- Limite 5 tentatives, au-delà → "morts" (à inspecter manuellement)
- Au démarrage : envoie un message d'excuse aux utilisateurs en attente

### `lib/circuit_breaker.js`
Circuit breaker classique 3 états (CLOSED → OPEN → HALF_OPEN) :
- Ouvre si > 50% d'erreurs sur les 10 derniers appels
- Reste OPEN 30s puis tente une sentinelle (HALF_OPEN)
- Si la sentinelle réussit → CLOSED. Sinon → OPEN (durée doublée)
- Pendant CIRCUIT OPEN : message d'attente bilingue à l'utilisateur

### `lib/audio_cache.js`
Cache disque des audios d'excuse fixes (4 entrées : `unavailable_dioula`,
`unavailable_french`, `back_dioula`, `back_french`) :
- **Pourquoi** : quand l'API TTS est down, le mode `dioula` perdait son audio
  et tombait sur du texte bilingue. Pour des utilisateurs souvent peu
  alphabétisés, c'est dégradant. Le cache permet de servir un audio
  pré-généré même en cas d'API down.
- **Warmup** au démarrage (event `connection.open`, en arrière-plan,
  gated par `isApiHealthy()` pour ne pas bloquer 4×5s si API down).
- **Stratégie de lecture** dans `getExcuseAudio` : cache disque d'abord
  (rapide), fallback online si cache miss, fallback texte bilingue si
  les deux échouent.
- Idempotent : warmup ne re-génère pas les entrées déjà en cache disque.
- Le dossier `audio_cache/` est gitignored (regénérable à chaque démarrage).

## Tests

```bash
# Tous les tests
node --test tests/circuit_breaker.test.js tests/message_queue.test.js tests/reconnect.test.js tests/logger.test.js tests/audio_cache.test.js

# Total : 87 tests, ~330ms
```

## Variables d'environnement attendues

| Variable | Défaut | Obligatoire | Description |
|---|---|---|---|
| `PORT` | `3001` | non | Port d'écoute Express |
| `WOURI_API_URL` | `http://localhost:8000` | non | URL de l'API backend |
| `WOURI_API_KEY` | (vide) | **oui en prod** | Clé partagée avec backend (header `X-API-Key`) — fallback si `WOURI_API_KEY_FILE` absent/illisible |
| `WOURI_API_KEY_FILE` | (vide) | non | #257 : fichier secret contenant la clé (**prioritaire** sur `WOURI_API_KEY` — `lib/secrets.js`) |
| `NODE_ENV` | `development` | non | `production` active certains warnings sécurité |
| `HUMAN_DELAY_PROFILE` | `fast` | non | Profil des délais "simulation humaine" (`fast` \| `natural` \| `off`, cf. `lib/human_delays.js`). `natural` = valeurs historiques anti-ban, rollback en 1 env var |

## Troubleshooting

| Problème | Solution |
|---|---|
| QR code n'apparaît pas | Supprimer `auth_baileys/` puis redémarrer |
| Port déjà utilisé | `npx kill-port 3001` (ou modifier `.env` `PORT=...`) |
| Connexion perdue | Auto-reconnexion 3s après déconnexion. Vérifier les logs |
| Session expirée (~2 semaines inactivité) | Re-scan QR via `/qr-page` |
| Backend `wouri-api` down | Messages échoués (pas de queue actuellement, à corriger Phase Robustesse) |
| `WOURI_API_KEY non definie en production` | Prod #257 : vérifier le fichier `WOURI_API_KEY_FILE` (non vide, lisible uid 1000) — prioritaire sur l'env. Dev : définir `WOURI_API_KEY` dans `.env` |
