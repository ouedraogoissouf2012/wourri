# WOURI WhatsApp Server

Serveur Node.js qui connecte les utilisateurs WhatsApp à l'assistant agricole
**Wourri** (bambara/dioula) via [Baileys](https://github.com/WhiskeySockets/Baileys).

- **Stack** : Node.js 16+ · Express · @whiskeysockets/baileys · Pino · Axios
- **Rôle** : passerelle WhatsApp ↔ API Wourri (FastAPI Python)
- **Port** : 3001 (configurable via `.env`)

---

## Démarrage rapide (5 minutes)

### Prérequis

- Node.js 16 ou plus récent (`node --version`)
- Un téléphone WhatsApp pour scanner le QR code
- L'API Wourri (`wouri-api`) accessible (par défaut `http://localhost:8000`)

### Installation

```bash
# 1. Installer les dépendances
npm install

# 2. Créer .env
cp .env.example .env
# Éditer .env :
#   PORT=3001                                 # Port d'écoute Express
#   WOURI_API_URL=http://localhost:8000       # URL de l'API Wourri
#   WOURI_API_KEY=<clé-partagée-avec-backend> # Header X-API-Key
#   NODE_ENV=development

# 3. Démarrer
npm start
```

À la première exécution, un QR code apparaît dans le terminal.
**Scanner avec WhatsApp** sur votre téléphone :
1. Ouvrir WhatsApp → Paramètres
2. Appareils liés → Lier un appareil
3. Scanner le QR code affiché

Une fois connecté, le serveur affiche :
```
========================================
   WOURI CONNECTE A WHATSAPP!
   Systeme d'onboarding actif
========================================
```

### Production

```bash
NODE_ENV=production npm run production
```

En production, `WOURI_API_KEY` est **obligatoire** (warning au démarrage sinon).

---

## Endpoints HTTP

| Méthode | Route | Description |
|---|---|---|
| GET | `/` | Statut général + nombre d'utilisateurs |
| GET | `/status` | Statut connexion + QR code data |
| GET | `/health` | Healthcheck enrichi : `status` + uptime + queue + circuit |
| GET | `/ready` | Kubernetes readiness probe (200 ok / 503 sinon) |
| GET | `/users` | Liste anonymisée des utilisateurs |
| GET | `/qr` | QR code data (JSON) |
| GET | `/qr-page` | Page HTML avec QR code visuel (auto-refresh 5s) |
| POST | `/logout` | Déconnexion + suppression `auth_baileys/` |

---

## Comment ça fonctionne

### Onboarding utilisateur (4 étapes)

1. **Premier message** → bot demande la ville (en dioula + français)
2. **User répond** → bot demande la langue (1=Français, 2=Dioula, 3=Les deux)
3. **User répond** → bot enregistre les préférences (`user_preferences.json`)
4. **Conversation normale** : le bot répond selon la langue choisie

### Pipeline de traitement

```
Message WhatsApp entrant
   ↓
[Filtrage : ignorer groupes, statuts, messages auto]
   ↓
[Si vocal] → Téléchargement → API ASR (Bambara MMS si dioula/both, Whisper si français)
   ↓
POST /api/chat/ (wouri-api)  avec city, language, bambara_text
   ↓
Réception : { response, response_dioula, audio_url, meta }
   ↓
Envoi WhatsApp selon langue + type d'entrée :
   • french + texte    → texte FR
   • french + vocal    → audio FR
   • dioula            → audio dioula uniquement
   • both + texte      → texte FR + audio dioula
   • both + vocal      → texte FR + audio dioula
   ↓
[Si dioula/both] → Prompt feedback 👍/👎 → POST /api/feedback/...
```

### Commandes utilisateur

L'utilisateur peut envoyer ces messages pour ajuster ses préférences :

| Commande | Effet |
|---|---|
| `changer ville` | Re-demande la ville |
| `changer langue` | Re-demande la langue |
| `réinitialiser` (ou `reset`, `recommencer`) | Recommence l'onboarding |

---

## Variables d'environnement

| Variable | Défaut | Obligatoire | Description |
|---|---|---|---|
| `PORT` | `3001` | non | Port Express |
| `WOURI_API_URL` | `http://localhost:8000` | non | URL de l'API backend Wourri |
| `WOURI_API_KEY` | (vide) | **oui en prod** | Clé partagée backend (`X-API-Key`) |
| `NODE_ENV` | `development` | non | `production` active warnings sécurité + force JSON logs |
| `LOG_LEVEL` | `info` | non | Niveau pino : `trace`/`debug`/`info`/`warn`/`error`/`fatal`/`silent` |

⚠️ Le fichier `.env` n'est **jamais committé** (`.gitignore`).
Référer à `.env.example` pour le template (à créer si absent).

---

## Stockage local

| Fichier/Dossier | Contenu | Gitignored |
|---|---|---|
| `auth_baileys/` | Session WhatsApp persistante (multi-fichiers) | ✅ |
| `temp_audio/` | Audios téléchargés temporairement (pour transcription) | ✅ |
| `user_preferences.json` | Préférences utilisateurs (city, language, étape onboarding) | ✅ |
| `pending_messages.json` | Queue persistante des messages en attente (Phase 2) | ✅ |
| `node_modules/` | Dépendances npm | ✅ |
| `.env` | Variables d'environnement (secrets) | ✅ |

---

## Troubleshooting

### Le QR code n'apparaît pas

```bash
# Supprimer la session et redémarrer
rm -rf auth_baileys/
npm start
```

### Port déjà utilisé

```bash
npx kill-port 3001
# ou modifier PORT=... dans .env
```

### Connexion perdue

Le serveur tente une **reconnexion automatique 3 secondes** après une déconnexion non-volontaire.
Vérifier les logs pour le code de déconnexion :

| Code | Signification | Action |
|---|---|---|
| `401` | Logged out (compte délié) | Supprimer `auth_baileys/`, rescanner QR |
| `408`, `428`, `500-503` | Erreur réseau ou serveur | Reconnexion automatique |
| `515` | Update WhatsApp Web requis | `npm install` (Baileys auto-fetch latest) |

### Session expirée (~2 semaines inactivité)

Re-scanner via `http://localhost:3001/qr-page`.

### `WOURI_API_KEY non definie en production`

Définir `WOURI_API_KEY` dans `.env` (la même clé que `API_SECRET_KEY` côté backend).

### L'API backend est down

Les messages utilisateur échouent silencieusement (pas de queue actuellement).
Une queue de messages sera ajoutée dans la **Phase Robustesse** (cf. CLAUDE.md).

---

## Dette technique reconnue

Phases pour atteindre un statut production-ready :

1. ✅ **Cleanup + Foundation** (mergé 2026-05-05, PR #115)
2. ✅ **Robustesse** : reconnexion backoff exponentiel + queue persistante + circuit breaker
3. ⏳ **Observabilité** : logging structuré pino JSON + healthcheck étendu Kubernetes + metrics
4. ⏳ **Sécurité** : CORS strict + validation inputs + rate limiting + `npm audit fix`
5. ⏳ **Tests** : intégration end-to-end + CI GitHub Actions
6. ⏳ **Déploiement** : Dockerfile + PM2/systemd + runbook ops
7. ⏳ **Modularisation** : décomposer `app-baileys.js` en modules

### Phase 2 livrée — modules `lib/`

- `lib/reconnect.js` : backoff 1s → 2s → 4s → ... → 60s (cap), limite 10 tentatives
- `lib/message_queue.js` : queue persistante (`pending_messages.json`), idempotent
- `lib/circuit_breaker.js` : 3 états CLOSED/OPEN/HALF_OPEN, message d'attente utilisateur
- **63 tests unitaires** dans `tests/` (`node --test`, ~270ms)

Voir `CLAUDE.md` pour la liste complète des dettes techniques connues.

---

## Décision projet — Baileys vs WhatsApp Cloud API

Validé par le porteur projet le **2026-05-05** :
- **Maintenant** : Baileys (gratuit, fonctionne, mais lib non-officielle)
- **Plus tard** : migration vers **WhatsApp Cloud API officielle Meta** quand le budget le permettra

À chaque feature future : **préserver la rétrocompatibilité Cloud API**
pour éviter une réécriture lors de la migration.

---

## Liens utiles

- API backend : `../wouri-api/` (FastAPI Python)
- ADRs structurants : `../wouri-api/docs/adr/`
- Documentation interne Claude : [`CLAUDE.md`](CLAUDE.md)
- Issue Phase 1 : [#114](https://github.com/ouedraogoissouf2012/wourri/issues/114)
- Baileys docs : <https://github.com/WhiskeySockets/Baileys>

---

## Licence

Privé / Wourri.
