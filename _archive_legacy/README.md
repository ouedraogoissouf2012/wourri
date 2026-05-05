# `_archive_legacy/` — Fichiers historiques (NE PAS RÉUTILISER)

## Pourquoi ce dossier existe

Ce dossier contient des fichiers hérités du projet **"École Notification"**
(Spring Boot, port 3000, basé sur `whatsapp-web.js`) qui a précédé
**Wourri WhatsApp Server**.

Au démarrage de Wourri, ces fichiers ont été conservés à la racine du repo
mais ils ne sont **pas utilisés** par le serveur Wourri actuel
(`app-baileys.js`, port 3001 par défaut, basé sur `@whiskeysockets/baileys`).

Ils sont archivés ici lors de la **Phase 1 Cleanup + Foundation**
(2026-05-05, [issue #114](https://github.com/ouedraogoissouf2012/wourri/issues/114))
pour préserver l'historique sans polluer la racine du repo.

---

## Pourquoi ils sont obsolètes (factuel)

### Fichiers JavaScript (4)

| Fichier | Pourquoi obsolète |
|---|---|
| `app.js` | Wourri version transitoire utilisant `whatsapp-web.js` (lib remplacée par Baileys) |
| `whatsapp-server.js` | École Notification pure (`LocalAuth name: "ecole-notification"`) |
| `whatsapp-server-simple.js` | Mode simulation sans vraie connexion WhatsApp |
| `test-whatsapp.js` | Tests pour `localhost:3000/send-message` (endpoint inexistant dans `app-baileys.js`) |

### Scripts Windows .bat (4)

| Fichier | Pourquoi obsolète |
|---|---|
| `start-whatsapp.bat` | Path hardcodé `C:\...\sendEmail\sendEmail\notification-service\whatsapp-server` |
| `cleanup.bat` | Idem hardcoded path + supprime `.wwebjs_auth/` (ancienne lib whatsapp-web.js) |
| `monitor.bat` | Référence `test-whatsapp.js` obsolète |
| `health-check.bat` | Path hardcodé École Notification + vérifie `whatsapp-server.js` (obsolète) |

### Documentation et déploiement (5)

| Fichier | Pourquoi obsolète |
|---|---|
| `GUIDE-COMPLET.md` | 100% École Notification (path `sendEmail/notification-service`) |
| `README-AUTONOME.md` | Liste les .bat École Notification comme outils de référence |
| `DEPLOIEMENT-CPANEL.md` | Déploiement cPanel pour l'ancien projet |
| `deploy-guide.md` | Déploiement LWS pour l'ancien projet |
| `deploy.sh` | Script bash de packaging cPanel pour l'ancien projet |

---

## Que faire de ces fichiers ?

**À éviter** :
- ❌ Ne pas les réutiliser tels quels (paths invalides, libs obsolètes)
- ❌ Ne pas s'inspirer de leur configuration (port 3000 + `whatsapp-web.js` ne reflètent plus Wourri)

**Acceptable** :
- ✅ Les consulter à titre de référence historique
- ✅ S'en inspirer pour des décisions design (ex: `deploy.sh` peut suggérer
  des `--exclude` patterns pour un futur Dockerfile Wourri)

---

## Suppression définitive (futur)

Ces fichiers seront supprimés définitivement (`git rm`) à la prochaine
phase de cleanup, après période d'observation d'au moins 1 mois pour
s'assurer qu'aucun environnement externe ne les référençait encore.

À cette occasion, ce `_archive_legacy/` sera lui-même retiré.

---

## Référence Wourri actuelle (le vrai serveur)

- **Fichier prod actif** : `../app-baileys.js` (1155 lignes)
- **Démarrage** : `npm start` (= `node app-baileys.js`)
- **Port** : `process.env.PORT || 3001` (souvent overridé en `3000` via `.env`)
- **Lib WhatsApp** : `@whiskeysockets/baileys` ^6.7.8
- **Documentation** : `../README.md` et `../CLAUDE.md` (réécrits 2026-05-05)
