# WhatsApp Server - WOURI

## Bot WhatsApp Bilingue - Node.js Baileys

**Version:** 1.0.0
**Langage:** Node.js 16+
**Framework:** Express + Baileys

---

## Description

WhatsApp Server est le composant de messagerie du projet WOURI. Il permet aux agriculteurs ivoiriens d'interagir avec l'assistant IA via WhatsApp, en recevant des réponses bilingues (Français + Dioula) avec support audio.

---

## Architecture

```
whatsapp-server/
├── app-baileys.js          # Serveur principal (UTILISE)
├── app.js                   # Ancienne version (non utilisée)
├── whatsapp-server.js       # Version alternative
├── whatsapp-server-simple.js
├── test-whatsapp.js         # Tests
├── package.json             # Dépendances Node.js
├── auth_baileys/            # Credentials WhatsApp (auto-généré)
└── temp_audio/              # Fichiers audio temporaires
```

---

## Installation

### 1. Prérequis

```bash
node --version  # >= 16.0.0
npm --version
```

### 2. Installer les dépendances

```bash
cd whatsapp-server
npm install
```

### 3. Dépendances principales

| Package | Version | Usage |
|---------|---------|-------|
| @whiskeysockets/baileys | ^7.0.0 | API WhatsApp non-officielle |
| axios | ^1.13.2 | Requêtes HTTP vers WOURI API |
| express | ^4.18.2 | Serveur HTTP/API |
| form-data | ^4.0.5 | Upload fichiers audio |
| qrcode-terminal | ^0.12.0 | QR code dans terminal |
| qrcode | ^1.5.4 | QR code en image |
| pino | ^10.2.1 | Logging |
| cors | ^2.8.5 | Cross-Origin |

---

## Démarrage

```bash
# Mode développement
npm start

# Ou directement
node app-baileys.js
```

**URLs:**
- Serveur: http://localhost:3001
- Page QR Code: http://localhost:3001/qr-page
- Status: http://localhost:3001/status

---

## Connexion WhatsApp

### Première connexion

1. Démarrer le serveur: `npm start`
2. Ouvrir http://localhost:3001/qr-page dans un navigateur
3. Scanner le QR code avec WhatsApp (Paramètres > Appareils liés)
4. Attendre le message "WOURI CONNECTE A WHATSAPP!"

### Reconnexion automatique

Les credentials sont sauvegardés dans `auth_baileys/`. Après la première connexion, le serveur se reconnecte automatiquement.

### Déconnexion

```bash
# Via API
curl -X POST http://localhost:3001/logout

# Ou supprimer le dossier auth_baileys/
rm -rf auth_baileys/
```

---

## Fonctionnalités

### 1. Réception de messages

| Type | Support | Description |
|------|---------|-------------|
| Texte | ✅ Actif | Messages texte standard |
| Audio/Vocal | ✅ Actif | Notes vocales → Transcription STT |
| Images | ❌ Non | Non supporté |
| Documents | ❌ Non | Non supporté |
| Groupes | ❌ Ignoré | Messages de groupe ignorés |

### 2. Envoi de réponses

| Type | Format | Description |
|------|--------|-------------|
| Texte Français | 🇫🇷 | Réponse principale |
| Texte Dioula | 🇲🇱 | Traduction Bambara |
| Audio vocal | OGG Opus | Synthèse vocale Bambara |

### 3. Anti-détection

Le bot simule un comportement humain:

| Fonctionnalité | Description |
|----------------|-------------|
| Marquer comme lu | Coches bleues après réception |
| "En train d'écrire..." | Indicateur de frappe |
| "Enregistrement..." | Avant envoi d'audio |
| Délais aléatoires | 0.5-3s entre actions |

### 4. Gestion des langues

Par défaut, le bot répond en mode bilingue (Français + Dioula).

**Commandes utilisateur:**
| Commande | Action |
|----------|--------|
| "seulement francais" | Mode Français uniquement |
| "seulement dioula" | Mode Dioula uniquement |
| "les deux" | Mode bilingue (défaut) |

---

## Traitement des messages vocaux

### Flux de traitement

```
[Utilisateur envoie audio]
         │
         ▼
[Marquer comme lu ✓✓]
         │
         ▼
[Afficher "en train d'écrire..."]
         │
         ▼
[Télécharger l'audio (Buffer)]
         │
         ▼
[Envoyer à WOURI API /api/stt/transcribe]
         │
         ▼
[Whisper transcrit → Texte]
         │
         ▼
[Traiter comme message texte]
         │
         ▼
[Réponse FR + Dioula + Audio]
```

### Gestion des erreurs audio

| Erreur | Message utilisateur |
|--------|---------------------|
| Téléchargement échoué | "Je n'ai pas pu recevoir votre message vocal" |
| Transcription vide | "Je n'ai pas compris, pouvez-vous répéter?" |
| Erreur API STT | "Essayez d'envoyer un message texte" |

---

## API Endpoints

### GET /

Health check du serveur.

**Response:**
```json
{
  "status": "running",
  "name": "WOURI WhatsApp Server (Baileys)",
  "connected": true,
  "mode": "bilingue"
}
```

### GET /status

Status détaillé de la connexion.

**Response:**
```json
{
  "connected": true,
  "qrCode": null,
  "mode": "bilingue (Francais + Dioula)",
  "users": 5
}
```

### GET /qr

Récupérer le QR code brut.

**Response (non connecté):**
```json
{
  "qr": "2@xxx..."
}
```

**Response (connecté):**
```json
{
  "message": "Deja connecte"
}
```

### GET /qr-page

Page HTML avec QR code visuel et instructions.
- Rafraîchissement automatique toutes les 5 secondes
- Interface utilisateur conviviale

### POST /logout

Déconnecte WhatsApp et supprime les credentials.

**Response:**
```json
{
  "success": true,
  "message": "Deconnecte"
}
```

---

## Communication avec WOURI API

### Endpoint utilisé

```
POST http://localhost:8000/api/chat/
```

### Requête envoyée

```json
{
  "message": "Comment planter du manioc?",
  "city": "Abidjan",
  "language": "both",
  "include_audio": true
}
```

### Réponse attendue

```json
{
  "response": "Pour planter du manioc...",
  "response_dioula": "Manioc siri ka...",
  "audio_url": "/static/audio/bm_xxx.ogg",
  "city": "Abidjan",
  "language": "both"
}
```

### Transcription audio (STT)

```
POST http://localhost:8000/api/stt/transcribe
Content-Type: multipart/form-data

audio: <Buffer>
language: "fr"
```

---

## Variables d'environnement

| Variable | Défaut | Description |
|----------|--------|-------------|
| PORT | 3001 | Port du serveur Express |
| WOURI_API_URL | http://localhost:8000 | URL de l'API Python |

---

## Structure du code

### app-baileys.js

```javascript
// Imports principaux
const { makeWASocket, downloadMediaMessage } = require('@whiskeysockets/baileys');

// Configuration
const PORT = 3001;
const WOURI_API_URL = 'http://localhost:8000';

// État global
let sock = null;           // Socket WhatsApp
let isConnected = false;   // État connexion
let qrCodeData = null;     // QR code actuel

// Préférences utilisateurs
const userLanguagePrefs = new Map();

// Fonctions principales
async function connectWhatsApp() { ... }
async function transcribeAudio(audioBuffer, filename) { ... }
function detectLanguagePreference(message) { ... }
function randomDelay(min, max) { ... }

// Événements Baileys
sock.ev.on('connection.update', ...)  // Connexion/QR
sock.ev.on('messages.upsert', ...)    // Messages entrants
sock.ev.on('creds.update', ...)       // Sauvegarde credentials

// Routes Express
app.get('/', ...)           // Health
app.get('/status', ...)     // Status détaillé
app.get('/qr', ...)         // QR brut
app.get('/qr-page', ...)    // Page QR HTML
app.post('/logout', ...)    // Déconnexion
```

---

## Logs et debugging

### Préfixes de logs

| Préfixe | Description |
|---------|-------------|
| `[MESSAGE]` | Message reçu |
| `[AUDIO]` | Traitement audio |
| `[STT]` | Transcription vocale |
| `[API]` | Appel WOURI API |
| `[ENVOYE]` | Message envoyé |
| `[STATUS]` | Changement de statut |
| `[LANGUE]` | Changement de langue |
| `[ERREUR]` | Erreur |

### Exemple de sortie

```
[MESSAGE] De: 22507xxxxxxxx@s.whatsapp.net
[MESSAGE] Texte: Comment planter du cacao?
[STATUS] Message marque comme lu
[STATUS] En train d'ecrire...
[API] Appel avec langue: both
[API] Reponse recue
[ENVOYE] Reponse francais
[ENVOYE] Traduction dioula
[ENVOYE] Audio vocal
```

---

## Dossiers générés

| Dossier | Contenu | Peut être supprimé |
|---------|---------|-------------------|
| `auth_baileys/` | Credentials WhatsApp | ⚠️ Nécessite rescan QR |
| `temp_audio/` | Audios temporaires | ✅ Oui |
| `node_modules/` | Dépendances | ✅ (npm install) |

---

## Limitations

### Baileys
- API non-officielle (peut casser avec mises à jour WhatsApp)
- Pas de support officiel Meta

### Fonctionnalités non supportées
- Messages de groupe
- Réactions aux messages
- Envoi d'images/documents
- Appels audio/vidéo

### Recommandations
- Ne pas utiliser pour du spam
- Respecter les conditions d'utilisation WhatsApp
- Usage personnel/éducatif recommandé

---

## Dépannage

### QR code ne s'affiche pas

```bash
# Supprimer les anciens credentials
rm -rf auth_baileys/
# Redémarrer
npm start
```

### Erreur "Connection closed"

Le serveur tente une reconnexion automatique. Si persistant:
1. Vérifier la connexion internet
2. Supprimer `auth_baileys/` et rescanner

### Audio non reçu

Vérifier que WOURI API est démarré:
```bash
curl http://localhost:8000/health
```

### Transcription échoue

Vérifier que ffmpeg est installé:
```bash
ffmpeg -version
```

---

## Scripts NPM

```json
{
  "start": "node app-baileys.js",
  "start:old": "node app.js",
  "dev": "node whatsapp-server.js",
  "production": "NODE_ENV=production node app-baileys.js"
}
```

---

## Contact

**Projet:** WOURI - Assistant Agricole IA
**GitHub:** https://github.com/ouedraogoissouf2012/wourri
