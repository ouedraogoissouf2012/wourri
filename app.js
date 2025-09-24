const express = require('express');
const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const cors = require('cors');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());
app.use(cors());

let client;
let qrCodeData = null;
let isConnected = false;
let isReady = false;

// Configuration pour la production
const authPath = process.env.NODE_ENV === 'production'
    ? path.join(process.cwd(), 'sessions')
    : '.wwebjs_auth';

// Initialisation WhatsApp
function initializeWhatsApp() {
    client = new Client({
        authStrategy: new LocalAuth({
            name: "ecole-notification",
            dataPath: authPath
        }),
        puppeteer: {
            headless: true,
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--no-zygote',
                '--disable-gpu',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor',
                '--disable-extensions',
                '--disable-default-apps',
                '--disable-sync',
                '--disable-translate',
                '--hide-scrollbars',
                '--mute-audio',
                '--no-default-browser-check',
                '--no-pings'
            ]
        },
        webVersionCache: {
            type: 'remote',
            remotePath: 'https://raw.githubusercontent.com/wppconnect-team/wa-version/main/html/2.2412.54.html',
        }
    });

    // QR Code
    client.on('qr', (qr) => {
        console.log('📱 Scannez ce QR Code avec WhatsApp :');
        qrcode.generate(qr, { small: true });
        qrCodeData = qr;
        isConnected = false;
    });

    // Prêt
    client.on('ready', () => {
        console.log('✅ WhatsApp connecté et prêt !');
        isReady = true;
        isConnected = true;
        qrCodeData = null;
    });

    // Déconnexion
    client.on('disconnected', (reason) => {
        console.log('❌ WhatsApp déconnecté:', reason);
        isConnected = false;
        isReady = false;
        qrCodeData = null;

        // Tentative de reconnexion après 5 secondes
        setTimeout(() => {
            console.log('🔄 Tentative de reconnexion...');
            initializeWhatsApp();
        }, 5000);
    });

    // Gestion des erreurs d'authentification
    client.on('auth_failure', (message) => {
        console.log('❌ Échec d\'authentification:', message);
        isConnected = false;
        isReady = false;
        qrCodeData = null;
    });

    // État de chargement
    client.on('loading_screen', (percent, message) => {
        console.log('⏳ Chargement:', percent, message);
    });

    client.initialize();
}

// Routes API
app.get('/status', (req, res) => {
    res.json({
        connected: isConnected,
        ready: isReady,
        qr_needed: qrCodeData !== null,
        environment: process.env.NODE_ENV || 'development'
    });
});

app.get('/qr', (req, res) => {
    res.json({
        qr: qrCodeData,
        message: qrCodeData ? "Scannez avec WhatsApp" : "Déjà connecté"
    });
});

// Page web pour afficher le QR code
app.get('/qr-page', (req, res) => {
    if (!qrCodeData) {
        res.send(`
            <!DOCTYPE html>
            <html>
            <head>
                <title>WhatsApp QR Code</title>
                <meta http-equiv="refresh" content="5">
                <style>
                    body { font-family: Arial, sans-serif; text-align: center; margin: 50px; }
                    h1 { color: #25d366; }
                </style>
            </head>
            <body>
                <h1>✅ WhatsApp déjà connecté!</h1>
                <p>Aucune authentification nécessaire.</p>
                <p>Le serveur WhatsApp est prêt à envoyer des messages.</p>
                <p><a href="/status">Vérifier le statut</a></p>
            </body>
            </html>
        `);
    } else {
        const qrAscii = generateQRCodeAscii(qrCodeData);
        res.send(`
            <!DOCTYPE html>
            <html>
            <head>
                <title>WhatsApp QR Code</title>
                <meta http-equiv="refresh" content="10">
                <style>
                    body { font-family: Arial, sans-serif; text-align: center; margin: 20px; }
                    h1 { color: #25d366; }
                    .qr-container {
                        background: white;
                        padding: 20px;
                        border-radius: 10px;
                        display: inline-block;
                        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                        margin: 20px;
                    }
                    .qr-code {
                        font-family: monospace;
                        font-size: 6px;
                        line-height: 6px;
                        white-space: pre;
                        background: white;
                        color: black;
                    }
                    .instructions {
                        margin: 20px;
                        padding: 15px;
                        background: #f0f8ff;
                        border-radius: 5px;
                        max-width: 500px;
                        margin: 20px auto;
                    }
                    .status { color: #666; font-size: 14px; margin-top: 10px; }
                </style>
            </head>
            <body>
                <h1>📱 Scanner le QR Code avec WhatsApp</h1>
                <div class="qr-container">
                    <pre class="qr-code">${qrAscii}</pre>
                </div>
                <div class="instructions">
                    <h3>Instructions :</h3>
                    <ol style="text-align: left;">
                        <li>Ouvrez <strong>WhatsApp</strong> sur votre téléphone</li>
                        <li>Allez dans <strong>Menu (⋯)</strong></li>
                        <li>Sélectionnez <strong>Appareils connectés</strong></li>
                        <li>Tapez <strong>Connecter un appareil</strong></li>
                        <li>Scannez le QR code ci-dessus</li>
                    </ol>
                </div>
                <div class="status">
                    Page actualisée automatiquement toutes les 10 secondes
                </div>
            </body>
            </html>
        `);
    }
});

// Fonction pour générer un QR code ASCII simple
function generateQRCodeAscii(data) {
    try {
        const qrcode = require('qrcode-terminal');
        let qrString = '';

        const originalWrite = process.stdout.write;
        process.stdout.write = function(chunk) {
            qrString += chunk;
            return true;
        };

        qrcode.generate(data, { small: true });

        process.stdout.write = originalWrite;

        return qrString || "QR Code en cours de génération...";
    } catch (error) {
        return "Erreur génération QR Code";
    }
}

// Envoyer un message
app.post('/send-message', async (req, res) => {
    try {
        const { number, message } = req.body;

        if (!number || !message) {
            return res.status(400).json({
                success: false,
                error: "Numéro et message requis"
            });
        }

        if (!isReady) {
            return res.status(503).json({
                success: false,
                error: "WhatsApp non connecté",
                qr_needed: qrCodeData !== null
            });
        }

        const chatId = number.includes('@c.us') ? number : `${number}@c.us`;

        console.log(`📤 Envoi vers: ${number}`);
        console.log(`📝 Message: ${message.substring(0, 50)}...`);

        const response = await client.sendMessage(chatId, message);

        console.log('✅ Message WhatsApp envoyé !');

        res.json({
            success: true,
            messageId: response.id.id,
            to: number,
            timestamp: new Date().toISOString()
        });

    } catch (error) {
        console.error('❌ Erreur WhatsApp:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// Route par défaut
app.get('/', (req, res) => {
    res.send(`
        <!DOCTYPE html>
        <html>
        <head>
            <title>Serveur WhatsApp</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 50px; text-align: center; }
                h1 { color: #25d366; }
                .links { margin: 30px 0; }
                .links a {
                    display: inline-block;
                    margin: 10px;
                    padding: 10px 20px;
                    background: #25d366;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
                }
                .links a:hover { background: #1da851; }
            </style>
        </head>
        <body>
            <h1>🚀 Serveur WhatsApp Actif</h1>
            <p>Serveur de notification WhatsApp pour École</p>
            <div class="links">
                <a href="/status">📊 Statut</a>
                <a href="/qr-page">📱 QR Code</a>
            </div>
            <p>Port: ${PORT} | Environnement: ${process.env.NODE_ENV || 'development'}</p>
        </body>
        </html>
    `);
});

// Démarrage du serveur
const server = app.listen(PORT, () => {
    console.log(`🚀 Serveur WhatsApp démarré sur port ${PORT}`);
    console.log(`📍 Environnement: ${process.env.NODE_ENV || 'development'}`);
    initializeWhatsApp();
});

// Gestion propre de l'arrêt
process.on('SIGINT', () => {
    console.log('🛑 Arrêt du serveur...');
    if (client) {
        client.destroy();
    }
    server.close();
    process.exit(0);
});

module.exports = app;