# Guide de Déploiement - Serveur WhatsApp

## Déploiement sur LWS (web44.lws-hosting.com)

### Prérequis
- Accès au panel LWS
- Support Node.js sur l'hébergement
- Sous-domaine configuré

### Option 1: Si Node.js est supporté

1. **Préparer les fichiers**
   ```bash
   # Créer un package de déploiement
   npm run build  # si applicable
   zip -r whatsapp-server.zip . -x "node_modules/*" ".wwebjs_*"
   ```

2. **Configuration production**
   - Modifier le port (souvent 8080 ou variable d'environnement)
   - Ajuster les chemins pour l'environnement de production

### Option 2: Hébergement via proxy reverse

1. **Serveur local + tunnel**
   - Utiliser ngrok ou cloudflare tunnel
   - Pointer le sous-domaine vers le tunnel

### Option 3: Migration vers un VPS

Si LWS ne supporte pas Node.js natif:
- Migrer vers un VPS
- Utiliser Docker pour l'isolation
- Configurer nginx comme proxy

### Variables d'environnement à configurer

```env
PORT=8080
NODE_ENV=production
WHATSAPP_SESSION_PATH=/path/to/sessions
```

### Structure de déploiement

```
/public_html/votre-sous-domaine/
├── whatsapp-server.js
├── package.json
├── node_modules/
└── .wwebjs_auth/
```