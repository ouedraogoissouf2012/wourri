# Guide de Déploiement cPanel - Serveur WhatsApp

## 📋 Prérequis

- **cPanel avec support Node.js** (vérifier dans "Software" → "Node.js")
- **Accès SSH** (optionnel mais recommandé)
- **Sous-domaine configuré** (ex: whatsapp.mondomaine.com)

## 🚀 Étapes de Déploiement

### 1. Vérification du Support Node.js

Dans cPanel :
1. Aller dans **"Software" → "Node.js"**
2. Si disponible → continuer avec cette méthode
3. Si non disponible → voir "Alternative sans Node.js"

### 2. Préparation des Fichiers

Sur votre machine locale :

```bash
# Créer un package de déploiement (exclure node_modules et sessions)
tar -czf whatsapp-server.tar.gz --exclude=node_modules --exclude=.wwebjs_* --exclude=.git .
```

### 3. Upload via cPanel

1. **File Manager** → Aller dans le dossier de votre sous-domaine
2. **Upload** → Sélectionner `whatsapp-server.tar.gz`
3. **Extract** → Décompresser l'archive
4. **Delete** → Supprimer l'archive après extraction

Structure attendue :
```
/public_html/whatsapp/
├── app.js              # ← Point d'entrée principal
├── whatsapp-server.js  # ← Fichier original (backup)
├── package.json
├── .htaccess          # ← Configuration Apache
├── .env.example       # ← Modèle de configuration
└── sessions/          # ← Créer ce dossier pour les sessions WhatsApp
```

### 4. Configuration Node.js dans cPanel

1. **Software** → **Node.js**
2. **Create Application** :
   - **Node.js version** : 18.x ou supérieur
   - **Application root** : `public_html/whatsapp`
   - **Application startup file** : `app.js`
   - **Environment** : `production`

3. **Ajouter les variables d'environnement** :
   ```
   NODE_ENV=production
   PORT=3000
   WHATSAPP_SESSION_PATH=/home/votre-username/whatsapp_sessions
   ```

### 5. Installation des Dépendances

Via l'interface Node.js de cPanel :
1. **Open Terminal** ou **Run NPM Install**
2. Ou manuellement via SSH :
   ```bash
   cd public_html/whatsapp
   npm install --production
   ```

### 6. Démarrage de l'Application

1. Dans cPanel Node.js : **Start Application**
2. Ou via SSH :
   ```bash
   node app.js
   ```

### 7. Configuration du Domaine

1. **Subdomains** → Créer `whatsapp.mondomaine.com`
2. **Document Root** : `/public_html/whatsapp`
3. Attendre propagation DNS (15-30 minutes)

## 🔧 Configuration Post-Déploiement

### Test de Fonctionnement

Accédez à :
- `https://whatsapp.mondomaine.com/` → Page d'accueil
- `https://whatsapp.mondomaine.com/status` → Status API
- `https://whatsapp.mondomaine.com/qr-page` → QR Code pour connection

### Authentification WhatsApp

1. Aller sur `/qr-page`
2. Scanner le QR code avec WhatsApp
3. Les sessions seront sauvegardées dans le dossier `sessions/`

## ⚠️ Points Importants

### Sécurité

1. **Protéger le dossier sessions** :
   ```apache
   # Dans .htaccess du dossier sessions
   Deny from all
   ```

2. **Limiter l'accès API** (optionnel) :
   ```javascript
   // Dans app.js, ajouter middleware d'authentification
   const allowedIPs = ['votre.ip.spring.boot'];
   ```

### Logs et Monitoring

1. **Logs d'application** : Vérifier dans cPanel → "Error Logs"
2. **Monitoring** : Utiliser `test-whatsapp.js` depuis votre serveur Spring Boot

### Persistence des Sessions

- **Important** : Le dossier `sessions/` doit être **en dehors** de `public_html` pour la sécurité
- Path recommandé : `/home/username/whatsapp_sessions/`
- Configurer dans les variables d'environnement

## 🔄 Alternative sans Node.js Natif

Si votre hébergeur ne supporte pas Node.js :

### Option 1: Proxy Tunnel
```bash
# Sur votre serveur local
npm install -g ngrok
ngrok http 3000

# Dans cPanel, créer une redirection :
# whatsapp.mondomaine.com → https://abc123.ngrok.io
```

### Option 2: Migration VPS
Recommandé pour une solution production stable.

## 📝 Scripts de Maintenance

### Restart automatique (cron)
```bash
# Ajouter dans cPanel → Cron Jobs (toutes les 5 minutes)
*/5 * * * * cd /home/username/public_html/whatsapp && npm start > /dev/null 2>&1
```

### Monitoring de santé
```bash
# Script de vérification (health-check-cpanel.sh)
#!/bin/bash
curl -f https://whatsapp.mondomaine.com/status || systemctl restart whatsapp-server
```

## 🐛 Dépannage

### Erreurs Courantes

1. **"Module not found"** → `npm install` pas exécuté
2. **"Port already in use"** → Redémarrer l'application Node.js
3. **"QR code timeout"** → Vérifier les logs, redémarrer l'app
4. **"503 Service Unavailable"** → Vérifier que l'app Node.js est démarrée

### Logs à Consulter

1. **cPanel Error Logs** → Erreurs Apache/Node.js
2. **Application Console** → Logs de l'app WhatsApp
3. **Access Logs** → Requêtes HTTP

## 📞 Support

En cas de problème :
1. Vérifier les logs dans cPanel
2. Tester localement d'abord
3. Contacter le support de votre hébergeur pour le support Node.js

---

**✅ Une fois déployé**, votre application sera accessible via :
- **API Status** : `https://whatsapp.mondomaine.com/status`
- **QR Authentication** : `https://whatsapp.mondomaine.com/qr-page`
- **Send Message API** : `POST https://whatsapp.mondomaine.com/send-message`