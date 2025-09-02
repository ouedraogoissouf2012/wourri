# 📱 Guide Complet - Serveur WhatsApp
## Configuration, Maintenance et Dépannage Autonome

### 📋 Table des matières
1. [Installation et Configuration](#installation-et-configuration)
2. [Démarrage et Arrêt](#démarrage-et-arrêt)
3. [Authentification WhatsApp](#authentification-whatsapp)
4. [Tests et Surveillance](#tests-et-surveillance)
5. [Maintenance et Nettoyage](#maintenance-et-nettoyage)
6. [Dépannage](#dépannage)
7. [Scripts Utilitaires](#scripts-utilitaires)
8. [Configuration Avancée](#configuration-avancée)

---

## 🚀 Installation et Configuration

### Prérequis
- Node.js (version 18+)
- npm (inclus avec Node.js)
- Compte WhatsApp Business ou personnel

### Installation initiale
```bash
# 1. Navigation vers le dossier
cd "C:\Users\USER PC\Documents\propre à moi\sendEmail\sendEmail\notification-service\whatsapp-server"

# 2. Installation des dépendances
npm install

# 3. Vérification de l'installation
npm list
```

### Structure des fichiers
```
whatsapp-server/
├── whatsapp-server.js      # Serveur principal
├── test-whatsapp.js        # Script de tests
├── monitor.bat             # Script de surveillance Windows
├── package.json            # Configuration npm
├── GUIDE-COMPLET.md        # Ce guide
├── .wwebjs_auth/           # Sessions WhatsApp (auto-généré)
└── .wwebjs_cache/          # Cache temporaire (auto-généré)
```

---

## ▶️ Démarrage et Arrêt

### Démarrer le serveur
```bash
# Méthode 1: Démarrage normal
npm start

# Méthode 2: Démarrage en arrière-plan (Windows)
start /B npm start

# Méthode 3: Avec PM2 (recommandé pour production)
npm install -g pm2
pm2 start whatsapp-server.js --name "whatsapp-service"
pm2 startup
pm2 save
```

### Arrêter le serveur
```bash
# Méthode 1: Ctrl+C dans le terminal

# Méthode 2: Tuer le processus par port
npx kill-port 3000

# Méthode 3: Avec PM2
pm2 stop whatsapp-service
pm2 delete whatsapp-service
```

### Redémarrer le serveur
```bash
# Redémarrage rapide
npx kill-port 3000 && npm start

# Avec PM2
pm2 restart whatsapp-service
```

---

## 🔐 Authentification WhatsApp

### Première connexion
1. **Démarrer le serveur**: `npm start`
2. **Ouvrir la page QR**: `http://localhost:3000/qr-page`
3. **Sur WhatsApp mobile**:
   - Menu (⋯) → Appareils connectés
   - Connecter un appareil
   - Scanner le QR code
4. **Attendre la confirmation**: "✅ WhatsApp connecté et prêt !"

### Re-authentification (si nécessaire)
```bash
# 1. Arrêter le serveur
npx kill-port 3000

# 2. Supprimer les sessions corrompues
rmdir /s /q .wwebjs_auth
rmdir /s /q .wwebjs_cache

# 3. Redémarrer et re-scanner
npm start
# Puis aller sur http://localhost:3000/qr-page
```

### Vérifier l'état de connexion
```bash
# Via API
curl http://localhost:3000/status

# Via script de test
node test-whatsapp.js --test
```

---

## 🧪 Tests et Surveillance

### Test rapide de statut
```bash
curl http://localhost:3000/status
```

### Test complet avec message
```bash
node test-whatsapp.js --test
```

### Surveillance continue
```bash
# Surveillance toutes les 30 secondes
node test-whatsapp.js --monitor

# Surveillance personnalisée (60 secondes)
node test-whatsapp.js --monitor --interval 60
```

### Interface de surveillance Windows
```bash
# Ouvrir le menu interactif
monitor.bat
```

### Test d'envoi de message manuel
```bash
# Exemple avec curl
curl -X POST http://localhost:3000/send-message \
  -H "Content-Type: application/json" \
  -d '{
    "number": "22544210112",
    "message": "Test de connexion"
  }'
```

---

## 🧹 Maintenance et Nettoyage

### Nettoyage des sessions corrompues
```bash
# Windows
rmdir /s /q .wwebjs_auth .wwebjs_cache

# Linux/Mac
rm -rf .wwebjs_auth .wwebjs_cache
```

### Nettoyage des logs (si implémenté)
```bash
# Vider les logs de débogage
echo. > debug.log 2>nul
```

### Mise à jour des dépendances
```bash
# Vérifier les versions
npm outdated

# Mettre à jour
npm update

# Mettre à jour whatsapp-web.js spécifiquement
npm install whatsapp-web.js@latest
```

### Maintenance préventive (hebdomadaire)
```bash
# 1. Tester la connexion
node test-whatsapp.js --test

# 2. Redémarrer proprement
npx kill-port 3000 && npm start

# 3. Vérifier les vulnérabilités
npm audit

# 4. Nettoyer si nécessaire
npm audit fix
```

---

## 🔧 Dépannage

### Problème: Port 3000 déjà utilisé
```bash
# Solution 1: Tuer le processus
npx kill-port 3000

# Solution 2: Identifier le processus (Windows)
netstat -ano | findstr :3000
taskkill /PID [PID_NUMBER] /F

# Solution 3: Changer le port dans whatsapp-server.js
# Ligne 7: const PORT = 3001;
```

### Problème: QR Code ne s'affiche pas
```bash
# 1. Vérifier que le serveur tourne
curl http://localhost:3000/status

# 2. Accéder à la page QR
http://localhost:3000/qr-page

# 3. Redémarrer si nécessaire
npx kill-port 3000 && npm start
```

### Problème: WhatsApp ne se connecte pas
```bash
# 1. Supprimer les sessions
rmdir /s /q .wwebjs_auth .wwebjs_cache

# 2. Redémarrer
npm start

# 3. Re-scanner le QR code
```

### Problème: Messages ne s'envoient pas
```bash
# 1. Vérifier le statut
curl http://localhost:3000/status

# 2. Tester avec un numéro valide
node test-whatsapp.js --test

# 3. Vérifier les logs pour erreurs
# Consulter la console où npm start s'exécute
```

### Problème: Erreur "Protocol Error"
```bash
# 1. Configuration Puppeteer corrompue
rmdir /s /q .wwebjs_auth .wwebjs_cache

# 2. Redémarrer complètement
npx kill-port 3000
npm start
```

### Problème: Déconnexion fréquente
```bash
# 1. Vérifier la stabilité internet
ping google.com

# 2. Éviter les sessions multiples WhatsApp Web
# Déconnecter autres appareils dans WhatsApp

# 3. Redémarrer le serveur régulièrement
# Utiliser PM2 pour la gestion automatique
```

---

## 🛠️ Scripts Utilitaires

### Script de démarrage automatique (Windows)
Créer `start-whatsapp.bat`:
```batch
@echo off
cd /d "C:\Users\USER PC\Documents\propre à moi\sendEmail\sendEmail\notification-service\whatsapp-server"
echo Démarrage du serveur WhatsApp...
npm start
pause
```

### Script de nettoyage complet
Créer `cleanup.bat`:
```batch
@echo off
cd /d "C:\Users\USER PC\Documents\propre à moi\sendEmail\sendEmail\notification-service\whatsapp-server"
echo Nettoyage des sessions WhatsApp...
npx kill-port 3000
rmdir /s /q .wwebjs_auth 2>nul
rmdir /s /q .wwebjs_cache 2>nul
echo Sessions supprimées. Redémarrage...
npm start
```

### Script de santé quotidien
Créer `health-check.bat`:
```batch
@echo off
cd /d "C:\Users\USER PC\Documents\propre à moi\sendEmail\sendEmail\notification-service\whatsapp-server"
echo === VÉRIFICATION SANTÉ WHATSAPP ===
echo.
echo 1. Test de statut...
curl -s http://localhost:3000/status
echo.
echo.
echo 2. Test d'envoi...
node test-whatsapp.js --test
echo.
echo === FIN DE VÉRIFICATION ===
pause
```

---

## ⚙️ Configuration Avancée

### Modifier le port du serveur
Dans `whatsapp-server.js`, ligne 7:
```javascript
const PORT = 3000; // Changer vers 3001, 8080, etc.
```

### Personnaliser les messages de log
Dans `whatsapp-server.js`, modifier les emojis/messages:
```javascript
console.log('🚀 Serveur WhatsApp démarré sur http://localhost:${PORT}');
console.log('✅ WhatsApp connecté et prêt !');
console.log('📤 Envoi vers: ${number}');
```

### Configurer les timeouts
Dans `whatsapp-server.js`, section Puppeteer:
```javascript
puppeteer: { 
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
    timeout: 60000 // Augmenter si connexion lente
}
```

### Ajouter des numéros de test
Dans `test-whatsapp.js`, ligne 64:
```javascript
const testNumber = '22544210112'; // Votre numéro de test
```

### Configuration des intervalles de surveillance
```javascript
// Dans test-whatsapp.js, fonction monitorWhatsApp:
setInterval(async () => {
    // Code de surveillance
}, intervalSeconds * 1000);
```

---

## 📞 Endpoints API Disponibles

### GET /status
Retourne l'état de connexion WhatsApp
```json
{
  "connected": true,
  "ready": true,
  "qr_needed": false
}
```

### GET /qr
Retourne les données du QR code
```json
{
  "qr": "données_qr_code",
  "message": "Scannez avec WhatsApp"
}
```

### GET /qr-page
Page web avec QR code visuel et instructions

### POST /send-message
Envoi de message WhatsApp
```json
{
  "number": "22544210112",
  "message": "Votre message ici"
}
```

---

## 🔄 Routine de Maintenance Recommandée

### Quotidienne
- [ ] Tester l'envoi d'un message: `node test-whatsapp.js --test`
- [ ] Vérifier le statut: `curl http://localhost:3000/status`

### Hebdomadaire  
- [ ] Redémarrer le serveur: `npx kill-port 3000 && npm start`
- [ ] Vérifier les mises à jour: `npm outdated`
- [ ] Test de surveillance: `node test-whatsapp.js --monitor` (2-3 minutes)

### Mensuelle
- [ ] Nettoyage complet: `cleanup.bat`
- [ ] Mise à jour des dépendances: `npm update`
- [ ] Vérification sécurité: `npm audit`

### En cas de problème
1. **Consulter ce guide** section Dépannage
2. **Tester le statut**: `curl http://localhost:3000/status`
3. **Nettoyer les sessions**: `cleanup.bat`
4. **Re-authentifier**: Aller sur `http://localhost:3000/qr-page`

---

## 📱 Contacts Utiles

### URLs importantes
- **Page QR Code**: http://localhost:3000/qr-page
- **API Status**: http://localhost:3000/status
- **Test API**: http://localhost:3000/qr

### Commandes d'urgence
```bash
# Arrêt d'urgence
npx kill-port 3000

# Nettoyage d'urgence  
rmdir /s /q .wwebjs_auth .wwebjs_cache

# Redémarrage d'urgence
npm start
```

### Fichiers de configuration
- **Serveur principal**: `whatsapp-server.js`
- **Tests**: `test-whatsapp.js` 
- **Surveillance**: `monitor.bat`
- **Ce guide**: `GUIDE-COMPLET.md`

---

## ✅ Checklist de Vérification

### Installation complète
- [ ] Node.js installé
- [ ] Dépendances npm installées (`npm install`)
- [ ] Serveur démarre sans erreur (`npm start`)
- [ ] Page QR accessible (http://localhost:3000/qr-page)

### Connexion WhatsApp
- [ ] QR code scanné avec succès
- [ ] Message "✅ WhatsApp connecté et prêt !" affiché
- [ ] Test d'envoi réussi (`node test-whatsapp.js --test`)
- [ ] API status retourne `"ready": true`

### Tests fonctionnels
- [ ] Envoi de message test réussi
- [ ] Réception du message sur téléphone
- [ ] Surveillance fonctionne (`monitor.bat`)
- [ ] Scripts utilitaires exécutables

---

*📝 Guide créé le 02/09/2025 - Version 1.0*
*🔧 Pour support technique, consulter la section Dépannage de ce guide*