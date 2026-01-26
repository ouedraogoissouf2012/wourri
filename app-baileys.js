/**
 * WOURI WhatsApp Server - Version Baileys
 * Serveur WhatsApp plus stable et leger utilisant Baileys
 * Support bilingue: Francais ET Dioula
 */

const { default: makeWASocket, DisconnectReason, useMultiFileAuthState, downloadMediaMessage } = require('@whiskeysockets/baileys');
const pino = require('pino');
const axios = require('axios');
const fs = require('fs');
const path = require('path');
const express = require('express');
const cors = require('cors');
const qrcode = require('qrcode-terminal');
const QRCode = require('qrcode');

// Configuration
const PORT = process.env.PORT || 3001;
const WOURI_API_URL = process.env.WOURI_API_URL || 'http://localhost:8000';
const AUTH_FOLDER = path.join(__dirname, 'auth_baileys');
const TEMP_AUDIO_FOLDER = path.join(__dirname, 'temp_audio');

// Creer le dossier temporaire pour les audios
if (!fs.existsSync(TEMP_AUDIO_FOLDER)) {
    fs.mkdirSync(TEMP_AUDIO_FOLDER, { recursive: true });
}

// Express app pour API de status
const app = express();
app.use(cors());
app.use(express.json());

// Variables d'etat
let sock = null;
let qrCodeData = null;
let isConnected = false;

// Mode bilingue: Francais ET Dioula par defaut
const userLanguagePrefs = new Map();

// Mots-cles pour detecter la langue souhaitee
const BOTH_KEYWORDS = ['les deux', 'both', 'deux langues', 'francais et dioula', 'dioula et francais'];
const DIOULA_ONLY_KEYWORDS = ['seulement dioula', 'dioula seul', 'uniquement dioula', 'only dioula'];
const FRENCH_ONLY_KEYWORDS = ['seulement francais', 'francais seul', 'uniquement francais', 'only french'];

// Fonction pour transcrire un audio via l'API STT
async function transcribeAudio(audioBuffer, filename = 'audio.ogg') {
    try {
        const FormData = require('form-data');
        const formData = new FormData();
        formData.append('audio', audioBuffer, {
            filename: filename,
            contentType: 'audio/ogg'
        });
        formData.append('language', 'fr'); // Francais par defaut

        console.log(`[STT] Appel API: ${WOURI_API_URL}/api/stt/transcribe`);
        const response = await axios.post(`${WOURI_API_URL}/api/stt/transcribe`, formData, {
            headers: {
                ...formData.getHeaders()
            },
            timeout: 180000 // 3 minutes pour la transcription (Whisper peut etre lent au premier chargement)
        });
        console.log(`[STT] Reponse API recue: ${response.status}`);

        if (response.data && response.data.text) {
            return response.data.text;
        }
        return null;
    } catch (error) {
        console.log('[STT] Erreur transcription:', error.message);
        return null;
    }
}

// Fonction pour detecter la langue souhaitee
function detectLanguagePreference(message) {
    const lowerMessage = message.toLowerCase();

    for (const keyword of BOTH_KEYWORDS) {
        if (lowerMessage.includes(keyword)) return 'both';
    }
    for (const keyword of DIOULA_ONLY_KEYWORDS) {
        if (lowerMessage.includes(keyword)) return 'dioula';
    }
    for (const keyword of FRENCH_ONLY_KEYWORDS) {
        if (lowerMessage.includes(keyword)) return 'french';
    }
    return null;
}

// Connexion WhatsApp avec Baileys
async function connectWhatsApp() {
    // Creer le dossier d'authentification s'il n'existe pas
    if (!fs.existsSync(AUTH_FOLDER)) {
        fs.mkdirSync(AUTH_FOLDER, { recursive: true });
    }

    const { state, saveCreds } = await useMultiFileAuthState(AUTH_FOLDER);

    sock = makeWASocket({
        auth: state,
        printQRInTerminal: true,
        logger: pino({ level: 'silent' }),
        browser: ['WOURI Assistant', 'Chrome', '120.0.0'],
    });

    // Gestion des evenements de connexion
    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            qrCodeData = qr;
            console.log('\n========================================');
            console.log('   SCANNEZ CE QR CODE AVEC WHATSAPP');
            console.log('========================================\n');
            qrcode.generate(qr, { small: true });
        }

        if (connection === 'close') {
            isConnected = false;
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

            console.log('Connexion fermee. Code:', statusCode);

            if (shouldReconnect) {
                console.log('Reconnexion en cours...');
                setTimeout(connectWhatsApp, 3000);
            } else {
                console.log('Deconnecte. Supprimez le dossier auth_baileys pour vous reconnecter.');
            }
        }

        if (connection === 'open') {
            isConnected = true;
            qrCodeData = null;
            console.log('\n========================================');
            console.log('   WOURI CONNECTE A WHATSAPP!');
            console.log('   Mode: Bilingue (Francais + Dioula)');
            console.log('========================================\n');
        }
    });

    // Sauvegarder les credentials
    sock.ev.on('creds.update', saveCreds);

    // Fonction pour simuler un delai humain (entre min et max ms)
    function randomDelay(min, max) {
        return new Promise(resolve => setTimeout(resolve, Math.floor(Math.random() * (max - min + 1)) + min));
    }

    // Gestion des messages entrants
    sock.ev.on('messages.upsert', async ({ messages }) => {
        console.log(`\n[DEBUG] messages.upsert recu: ${messages.length} message(s)`);

        for (const msg of messages) {
            // Log complet du message pour debug
            console.log(`[DEBUG] Message brut:`, JSON.stringify(msg, null, 2).substring(0, 500));

            // Ignorer les messages envoyes par nous-meme
            if (msg.key.fromMe) {
                console.log('[DEBUG] Message ignore: fromMe=true');
                continue;
            }

            // Ignorer les messages de groupe (optionnel)
            if (msg.key.remoteJid.endsWith('@g.us')) {
                console.log('[DEBUG] Message ignore: groupe');
                continue;
            }

            // Ignorer les statuts WhatsApp (stories)
            if (msg.key.remoteJid === 'status@broadcast') {
                console.log('[DEBUG] Message ignore: status broadcast');
                continue;
            }

            const userNumber = msg.key.remoteJid;
            console.log(`[DEBUG] Message de: ${userNumber}`);
            console.log(`[DEBUG] Type de msg.message:`, Object.keys(msg.message || {}));

            // Extraction du texte - couvrir tous les types possibles (AVANT de verifier l'audio)
            let messageText = msg.message?.conversation ||
                             msg.message?.extendedTextMessage?.text ||
                             msg.message?.buttonsResponseMessage?.selectedButtonId ||
                             msg.message?.listResponseMessage?.singleSelectReply?.selectedRowId ||
                             msg.message?.templateButtonReplyMessage?.selectedId ||
                             '';

            console.log(`[DEBUG] Texte extrait: "${messageText}"`);

            // Detecter le type de message - SEULEMENT si pas de texte
            const audioMsg = msg.message?.audioMessage;
            const isAudioMessage = audioMsg !== undefined && audioMsg !== null && !messageText;
            const isPttMessage = audioMsg?.ptt === true;

            console.log(`[DEBUG] isAudioMessage: ${isAudioMessage}, audioMsg existe: ${audioMsg !== undefined}`);

            // Si c'est un message vocal (et PAS un message texte), le transcrire
            if (isAudioMessage) {
                console.log(`\n[AUDIO] Message vocal recu de: ${userNumber}`);
                console.log(`[AUDIO] Type: ${isPttMessage ? 'Note vocale' : 'Fichier audio'}`);

                // Verifier que le message a une cle media valide
                if (!audioMsg?.mediaKey || !audioMsg?.url) {
                    console.log('[AUDIO] Message sans cle media valide - ignore');
                    continue;
                }

                try {
                    // Marquer comme lu
                    await sock.readMessages([msg.key]);
                    console.log('[STATUS] Audio marque comme lu');

                    // Afficher "en train d'ecrire" pendant la transcription
                    await sock.sendPresenceUpdate('composing', userNumber);

                    // Telecharger l'audio
                    console.log('[AUDIO] Telechargement en cours...');
                    console.log(`[AUDIO] URL: ${audioMsg.url ? 'presente' : 'absente'}, MediaKey: ${audioMsg.mediaKey ? 'presente' : 'absente'}`);

                    const audioBuffer = await downloadMediaMessage(
                        msg,
                        'buffer',
                        {},
                        {
                            logger: pino({ level: 'silent' }),
                            reuploadRequest: sock.updateMediaMessage
                        }
                    );

                    if (!audioBuffer) {
                        console.log('[AUDIO] Erreur: impossible de telecharger');
                        await sock.sendPresenceUpdate('paused', userNumber);
                        await sock.sendMessage(userNumber, {
                            text: "Desole, je n'ai pas pu recevoir votre message vocal. Reessayez."
                        });
                        continue;
                    }

                    console.log(`[AUDIO] Telecharge: ${audioBuffer.length} bytes`);

                    // Transcrire l'audio
                    console.log('[STT] Transcription en cours...');
                    const transcribedText = await transcribeAudio(audioBuffer, 'voice_message.ogg');

                    if (!transcribedText || transcribedText.trim() === '') {
                        console.log('[STT] Erreur: transcription vide ou echec');
                        await sock.sendPresenceUpdate('paused', userNumber);
                        await sock.sendMessage(userNumber, {
                            text: "Desole, je n'ai pas compris votre message vocal. Pouvez-vous repeter ou ecrire votre question?"
                        });
                        continue;
                    }

                    console.log(`[STT] Transcription: "${transcribedText}"`);
                    messageText = transcribedText;

                    // NE PAS envoyer de message de confirmation ici
                    // Le traitement continue directement avec le texte transcrit
                    console.log('[AUDIO] Transcription reussie, traitement du message...');

                } catch (audioError) {
                    console.error('[AUDIO] Erreur:', audioError.message);
                    await sock.sendPresenceUpdate('paused', userNumber);
                    await sock.sendMessage(userNumber, {
                        text: "Desole, je n'ai pas pu traiter votre message vocal. Essayez d'envoyer un message texte."
                    });
                    continue;
                }
            }

            if (!messageText) {
                console.log('[DEBUG] Message ignore: texte vide apres extraction');
                console.log('[DEBUG] msg.message complet:', JSON.stringify(msg.message, null, 2));
                continue;
            }

            console.log(`\n[MESSAGE] De: ${userNumber}`);
            console.log(`[MESSAGE] Texte: ${messageText}`);

            try {
                // 1. Marquer le message comme lu (coches bleues)
                await sock.readMessages([msg.key]);
                console.log('[STATUS] Message marque comme lu');

                // 2. Petit delai avant de commencer a "ecrire" (plus naturel)
                await randomDelay(500, 1500);

                // 3. Afficher "en train d'ecrire..."
                await sock.sendPresenceUpdate('composing', userNumber);
                console.log('[STATUS] En train d\'ecrire...');

                // Detecter si l'utilisateur veut changer de langue
                const detectedPref = detectLanguagePreference(messageText);
                if (detectedPref) {
                    // Simuler un temps de lecture/ecriture
                    await randomDelay(1000, 2000);

                    userLanguagePrefs.set(userNumber, detectedPref);
                    const prefMsg = detectedPref === 'both'
                        ? "Mode bilingue active (Francais + Dioula)"
                        : detectedPref === 'dioula'
                            ? "Mode Dioula uniquement active"
                            : "Mode Francais uniquement active";

                    // Arreter "en train d'ecrire" avant d'envoyer
                    await sock.sendPresenceUpdate('paused', userNumber);
                    await sock.sendMessage(userNumber, { text: prefMsg });
                    console.log(`[LANGUE] Preference mise a jour: ${detectedPref}`);
                    continue;
                }

                // Langue par defaut: both (les deux)
                const userLanguage = userLanguagePrefs.get(userNumber) || 'both';

                // Appeler l'API WOURI avec maintien du statut "composing"
                console.log(`[API] Appel avec langue: ${userLanguage}`);

                // Maintenir "en train d'ecrire" pendant l'appel API
                // Envoyer un signal toutes les 5 secondes pour maintenir le statut actif
                let keepTyping = true;
                const typingInterval = setInterval(async () => {
                    if (keepTyping) {
                        try {
                            await sock.sendPresenceUpdate('composing', userNumber);
                            console.log('[STATUS] Refresh typing...');
                        } catch (e) {
                            // Ignorer les erreurs
                        }
                    }
                }, 5000); // Toutes les 5 secondes (WhatsApp expire le statut après ~10-15s)

                let data;
                try {
                    const response = await axios.post(`${WOURI_API_URL}/api/chat/`, {
                        message: messageText,
                        city: 'Abidjan',
                        language: userLanguage,
                        include_audio: true
                    }, { timeout: 180000 }); // 3 minutes timeout
                    data = response.data;
                } finally {
                    // Arreter l'intervalle de "typing"
                    keepTyping = false;
                    clearInterval(typingInterval);
                }

                console.log(`[API] Reponse recue`);

                // Arreter "en train d'ecrire" avant d'envoyer
                await sock.sendPresenceUpdate('paused', userNumber);

                // Petit delai avant le premier message (naturel)
                await randomDelay(300, 800);

                // Envoyer la reponse en francais
                if (data.response) {
                    await sock.sendMessage(userNumber, {
                        text: `🇫🇷 *Français:*\n${data.response}`
                    });
                    console.log('[ENVOYE] Reponse francais');
                }

                // Envoyer la traduction Dioula si disponible
                if (data.response_dioula && userLanguage !== 'french') {
                    // Simuler "en train d'ecrire" entre les messages
                    await sock.sendPresenceUpdate('composing', userNumber);
                    await randomDelay(1500, 3000); // Delai naturel pour "taper" le Dioula
                    await sock.sendPresenceUpdate('paused', userNumber);

                    await sock.sendMessage(userNumber, {
                        text: `🇲🇱 *Dioula:*\n${data.response_dioula}`
                    });
                    console.log('[ENVOYE] Traduction dioula');
                }

                // Envoyer l'audio si disponible
                if (data.audio_url) {
                    try {
                        // Petit delai avant l'audio
                        await randomDelay(500, 1000);

                        const audioUrl = data.audio_url.startsWith('http')
                            ? data.audio_url
                            : `${WOURI_API_URL}${data.audio_url}`;

                        const audioResponse = await axios.get(audioUrl, {
                            responseType: 'arraybuffer',
                            timeout: 30000
                        });

                        // Detecter le type MIME selon l'extension
                        const isOgg = audioUrl.endsWith('.ogg');
                        const mimetype = isOgg ? 'audio/ogg; codecs=opus' : 'audio/wav';

                        // Simuler "enregistrement vocal" avant d'envoyer l'audio
                        await sock.sendPresenceUpdate('recording', userNumber);
                        await randomDelay(1000, 2000);
                        await sock.sendPresenceUpdate('paused', userNumber);

                        await sock.sendMessage(userNumber, {
                            audio: Buffer.from(audioResponse.data),
                            mimetype: mimetype,
                            ptt: true // Voice message
                        });
                        console.log('[ENVOYE] Audio vocal');
                    } catch (audioErr) {
                        console.log('[AUDIO] Erreur:', audioErr.message);
                    }
                }

            } catch (error) {
                console.error('[ERREUR]', error.message);
                // Arreter le statut "en train d'ecrire" en cas d'erreur
                await sock.sendPresenceUpdate('paused', userNumber);
                await randomDelay(500, 1000);
                await sock.sendMessage(userNumber, {
                    text: "Desole, je rencontre un probleme technique. Reessayez dans quelques instants."
                });
            }
        }
    });
}

// Routes API Express
app.get('/', (req, res) => {
    res.json({
        status: 'running',
        name: 'WOURI WhatsApp Server (Baileys)',
        connected: isConnected,
        mode: 'bilingue'
    });
});

app.get('/status', (req, res) => {
    res.json({
        connected: isConnected,
        qrCode: qrCodeData,
        mode: 'bilingue (Francais + Dioula)',
        users: userLanguagePrefs.size
    });
});

app.get('/qr', (req, res) => {
    if (qrCodeData) {
        res.json({ qr: qrCodeData });
    } else if (isConnected) {
        res.json({ message: 'Deja connecte' });
    } else {
        res.json({ message: 'QR code pas encore genere' });
    }
});

// Page web pour scanner le QR code
app.get('/qr-page', async (req, res) => {
    let qrImageHtml = '';
    let statusMessage = '';

    if (isConnected) {
        statusMessage = '<div style="color: #4CAF50; font-size: 24px;">✅ CONNECTE A WHATSAPP!</div>';
    } else if (qrCodeData) {
        try {
            const qrDataUrl = await QRCode.toDataURL(qrCodeData, { width: 300 });
            qrImageHtml = `<img src="${qrDataUrl}" alt="QR Code" style="border: 4px solid #25D366; border-radius: 10px;">`;
            statusMessage = '<div style="color: #FFA500;">⏳ En attente de scan...</div>';
        } catch (err) {
            statusMessage = '<div style="color: red;">Erreur generation QR</div>';
        }
    } else {
        statusMessage = '<div style="color: #888;">QR code en cours de generation...</div>';
    }

    res.send(`
    <!DOCTYPE html>
    <html>
    <head>
        <title>WOURI - Connexion WhatsApp</title>
        <meta charset="UTF-8">
        <meta http-equiv="refresh" content="5">
        <style>
            body {
                font-family: Arial, sans-serif;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #075E54 0%, #128C7E 100%);
                color: white;
            }
            .container {
                background: white;
                padding: 40px;
                border-radius: 20px;
                text-align: center;
                box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            }
            h1 {
                color: #075E54;
                margin-bottom: 10px;
            }
            h2 {
                color: #666;
                font-weight: normal;
                margin-top: 0;
            }
            .qr-container {
                margin: 20px 0;
            }
            .instructions {
                color: #666;
                margin-top: 20px;
                text-align: left;
            }
            .instructions ol {
                padding-left: 20px;
            }
            .refresh-note {
                color: #999;
                font-size: 12px;
                margin-top: 15px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🌾 WOURI</h1>
            <h2>Assistant Agricole WhatsApp</h2>

            <div class="qr-container">
                ${qrImageHtml}
            </div>

            ${statusMessage}

            <div class="instructions">
                <strong>Pour connecter WhatsApp:</strong>
                <ol>
                    <li>Ouvrez WhatsApp sur votre telephone</li>
                    <li>Allez dans Parametres > Appareils lies</li>
                    <li>Appuyez sur "Lier un appareil"</li>
                    <li>Scannez ce QR code</li>
                </ol>
            </div>

            <div class="refresh-note">
                Cette page se rafraichit automatiquement toutes les 5 secondes
            </div>
        </div>
    </body>
    </html>
    `);
});

app.post('/logout', async (req, res) => {
    try {
        if (sock) {
            await sock.logout();
        }
        // Supprimer les fichiers d'auth
        if (fs.existsSync(AUTH_FOLDER)) {
            fs.rmSync(AUTH_FOLDER, { recursive: true });
        }
        res.json({ success: true, message: 'Deconnecte' });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// Demarrer le serveur
app.listen(PORT, () => {
    console.log('\n========================================');
    console.log('   WOURI WhatsApp Server (Baileys)');
    console.log('========================================');
    console.log(`API: http://localhost:${PORT}`);
    console.log(`WOURI API: ${WOURI_API_URL}`);
    console.log('Mode: Bilingue (Francais + Dioula)');
    console.log('========================================\n');

    // Demarrer la connexion WhatsApp
    connectWhatsApp();
});
