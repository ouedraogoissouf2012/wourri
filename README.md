# Serveur WhatsApp Local

## 🚀 Démarrage

```bash
cd whatsapp-server
npm start
```

## 📱 Configuration

1. Démarrez le serveur
2. Scannez le QR Code avec WhatsApp
3. Le serveur est prêt !

## 🌐 Endpoints

- `GET /health` - Santé du serveur
- `GET /whatsapp/status` - Statut WhatsApp
- `POST /whatsapp/send` - Envoyer message simple
- `POST /whatsapp/send-bulletin` - Notification bulletin
- `POST /whatsapp/send-urgent` - Message urgent

## 🔗 Intégration avec Spring Boot

Le serveur Java utilisera automatiquement ce serveur local sur `http://localhost:3000`