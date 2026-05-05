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
├── package.json           # Dépendances figées (versions exactes, pas de ^)
├── .env                   # Secrets (gitignored)
├── .gitignore
├── auth_baileys/          # Session WhatsApp persistante (gitignored)
├── temp_audio/            # Audios téléchargés temporairement (gitignored)
├── user_preferences.json  # Préférences users (gitignored)
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
| GET | `/users` | Liste anonymisée des utilisateurs (numéros tronqués) |
| GET | `/qr` | QR code data brut (JSON) |
| GET | `/qr-page` | Page HTML avec QR code visuel auto-refresh 5s |
| POST | `/logout` | Déconnexion + suppression `auth_baileys/` |

## Pipeline de traitement d'un message entrant

1. **Filtrage** : ignorer messages auto, groupes, statuts
2. **Onboarding** (étapes `NEW` → `WAITING_CITY` → `WAITING_LANGUAGE` → `COMPLETE`)
3. **Détection commande** : "changer ville", "changer langue", "réinitialiser"
4. **Si vocal** : téléchargement → transcription via API backend
   - Si user en mode `dioula` ou `both` → `/api/asr/transcribe-and-translate` (MMS Bambara)
   - Si user en mode `french` → `/api/stt/transcribe` (Whisper français)
5. **Appel backend** : `POST /api/chat/` avec `{message, city, language, bambara_text, user_id, include_audio: true}`
6. **Envoi réponse** selon langue + type d'entrée :
   - `french` + entrée vocale → audio FR
   - `french` + entrée texte → texte FR
   - `dioula` → audio dioula uniquement (pas de texte)
   - `both` + entrée vocale → texte FR + audio dioula
   - `both` + entrée texte → texte FR + audio dioula
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

- **God file** : `app-baileys.js` 1155 lignes — à décomposer (Phase Modularisation)
- **Logging non structuré** : `console.log` partout — à migrer vers pino JSON
  (Phase Observabilité)
- **Pas de healthcheck étendu** : `/status` minimal
- **Reconnexion simpliste** : `setTimeout 3000ms` sans backoff exponentiel
- **CORS permissif** : `app.use(cors())` sans restriction
- **Pas de rate limiting**
- **Pas de queue de messages** : si l'API backend est down, messages perdus
- **Nested folder pourri** : `whatsapp-server/whatsapp-server/` (issue P2-04, séparée)

Ces points seront traités dans des phases dédiées :
1. ✅ **Cleanup + Foundation** (cette phase, en cours)
2. Robustesse : reconnexion exponentielle + circuit breaker + queue
3. Observabilité : pino JSON + healthcheck étendu + metrics
4. Sécurité : CORS strict + validation inputs + rate limiting
5. Tests : unit + integration + CI GitHub Actions
6. Déploiement : Dockerfile + PM2/systemd + runbook
7. Modularisation : décomposer `app-baileys.js`

## Variables d'environnement attendues

| Variable | Défaut | Obligatoire | Description |
|---|---|---|---|
| `PORT` | `3001` | non | Port d'écoute Express |
| `WOURI_API_URL` | `http://localhost:8000` | non | URL de l'API backend |
| `WOURI_API_KEY` | (vide) | **oui en prod** | Clé partagée avec backend (header `X-API-Key`) |
| `NODE_ENV` | `development` | non | `production` active certains warnings sécurité |

## Troubleshooting

| Problème | Solution |
|---|---|
| QR code n'apparaît pas | Supprimer `auth_baileys/` puis redémarrer |
| Port déjà utilisé | `npx kill-port 3001` (ou modifier `.env` `PORT=...`) |
| Connexion perdue | Auto-reconnexion 3s après déconnexion. Vérifier les logs |
| Session expirée (~2 semaines inactivité) | Re-scan QR via `/qr-page` |
| Backend `wouri-api` down | Messages échoués (pas de queue actuellement, à corriger Phase Robustesse) |
| `WOURI_API_KEY non definie en production` | Définir `WOURI_API_KEY` dans `.env` |
