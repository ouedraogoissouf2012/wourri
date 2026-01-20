const express = require('express');
const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const cors = require('cors');
const path = require('path');
const axios = require('axios');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 3000;
const WOURI_API_URL = process.env.WOURI_API_URL || 'http://localhost:8000';
const DEFAULT_CITY = process.env.DEFAULT_CITY || 'Abidjan';

app.use(express.json());
app.use(cors());

let client;
let qrCodeData = null;
let isConnected = false;
let isReady = false;

// Mode bilingue: Français ET Dioula par défaut
// L'utilisateur peut choisir: "both" (les deux), "french" (français seul), "dioula" (dioula seul)
const userLanguagePrefs = new Map();

// Mots-cles pour detecter la langue souhaitee
const BOTH_KEYWORDS = ['les deux', 'both', 'deux langues', 'francais et dioula', 'dioula et francais'];
const DIOULA_ONLY_KEYWORDS = ['seulement dioula', 'dioula seul', 'uniquement dioula', 'only dioula'];
const FRENCH_ONLY_KEYWORDS = ['seulement francais', 'francais seul', 'uniquement francais', 'only french'];

// Fonction pour detecter la langue souhaitee dans un message
function detectLanguagePreference(message) {
    const lowerMessage = message.toLowerCase();

    // Verifier les preferences
    for (const keyword of BOTH_KEYWORDS) {
        if (lowerMessage.includes(keyword)) {
            return 'both';
        }
    }
    for (const keyword of DIOULA_ONLY_KEYWORDS) {
        if (lowerMessage.includes(keyword)) {
            return 'dioula';
        }
    }
    for (const keyword of FRENCH_ONLY_KEYWORDS) {
        if (lowerMessage.includes(keyword)) {
            return 'french';
        }
    }

    return null; // Pas de preference detectee
}

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

    // === WOURI: Réception des messages ===
    client.on('message', async (message) => {
        try {
            // Ignorer les messages de groupe et les messages envoyés par nous
            if (message.from.includes('@g.us') || message.fromMe) {
                return;
            }

            // Ignorer les messages non-texte (images, audio, etc.)
            if (message.type !== 'chat') {
                console.log(`📎 Message non-texte ignoré (type: ${message.type})`);
                return;
            }

            const userMessage = message.body;
            const userNumber = message.from.replace('@c.us', '');

            console.log(`\n📩 Message reçu de ${userNumber}:`);
            console.log(`   "${userMessage}"`);

            // Envoyer un indicateur de saisie
            const chat = await message.getChat();
            chat.sendStateTyping();

            // Detecter si l'utilisateur veut changer de langue
            const detectedLanguage = detectLanguagePreference(userMessage);
            if (detectedLanguage) {
                userLanguagePrefs.set(userNumber, detectedLanguage);
                console.log(`🌍 Langue changée pour ${userNumber}: ${detectedLanguage}`);
            }

            // Obtenir la langue preferee de l'utilisateur (defaut: french)
            const userLanguage = userLanguagePrefs.get(userNumber) || 'french';
            console.log(`🌍 Langue utilisée: ${userLanguage}`);

            // Appeler l'API WOURI
            console.log(`🌾 Envoi à WOURI API...`);

            const response = await axios.post(`${WOURI_API_URL}/api/chat/`, {
                message: userMessage,
                city: DEFAULT_CITY,
                language: userLanguage,
                include_audio: userLanguage === 'dioula' // Audio seulement pour Dioula
            }, {
                timeout: 60000, // Timeout plus long pour la génération audio
                headers: { 'Content-Type': 'application/json' }
            });

            const wouriResponse = response.data.response;
            const audioUrl = response.data.audio_url;

            console.log(`✅ Réponse WOURI: "${wouriResponse.substring(0, 50)}..."`);

            // Envoyer la réponse textuelle à l'utilisateur
            await client.sendMessage(message.from, wouriResponse);

            // Si un audio est disponible (pour Dioula), l'envoyer aussi
            if (audioUrl && userLanguage === 'dioula') {
                try {
                    const fullAudioUrl = `${WOURI_API_URL}${audioUrl}`;
                    console.log(`🔊 Envoi audio: ${fullAudioUrl}`);

                    // Telecharger l'audio et l'envoyer
                    const { MessageMedia } = require('whatsapp-web.js');
                    const media = await MessageMedia.fromUrl(fullAudioUrl);
                    await client.sendMessage(message.from, media, { sendAudioAsVoice: true });
                    console.log(`🔊 Audio envoyé à ${userNumber}`);
                } catch (audioError) {
                    console.log(`⚠️ Impossible d'envoyer l'audio: ${audioError.message}`);
                }
            }

            console.log(`📤 Réponse envoyée à ${userNumber}`);

            // Message d'aide pour changer de langue (première interaction ou changement)
            if (detectedLanguage) {
                const langName = detectedLanguage === 'dioula' ? 'Dioula/Bambara' : 'Français';
                await client.sendMessage(message.from,
                    `✅ Langue changée en ${langName}!\n\n` +
                    `💡 Pour changer de langue, dites:\n` +
                    `• "en français" pour le Français\n` +
                    `• "en dioula" ou "en bambara" pour le Dioula`
                );
            }

        } catch (error) {
            console.error('❌ Erreur traitement message:', error.message);

            // Envoyer un message d'erreur à l'utilisateur
            try {
                await client.sendMessage(
                    message.from,
                    "Désolé, je rencontre des difficultés techniques. Réessayez dans quelques instants. 🌾"
                );
            } catch (e) {
                console.error('❌ Impossible d\'envoyer le message d\'erreur');
            }
        }
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