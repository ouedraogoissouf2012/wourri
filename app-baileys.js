/**
 * WOURI WhatsApp Server - Version Baileys
 * Serveur WhatsApp avec onboarding utilisateur
 * Demande ville et langue preferee avant de repondre
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
const USER_PREFS_FILE = path.join(__dirname, 'user_preferences.json');

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

// ========================================
// GESTION DES PREFERENCES UTILISATEURS
// ========================================

// Structure: { "22541540178@s.whatsapp.net": { city: "Bonoua", language: "both", step: "complete", pendingQuestion: null } }
let userPreferences = {};

// Etapes d'onboarding
const STEPS = {
    NEW: 'new',           // Nouvel utilisateur
    WAITING_CITY: 'waiting_city',     // En attente de la ville
    WAITING_LANGUAGE: 'waiting_language', // En attente de la langue
    COMPLETE: 'complete'  // Onboarding termine
};

// Charger les preferences depuis le fichier
function loadUserPreferences() {
    try {
        if (fs.existsSync(USER_PREFS_FILE)) {
            const data = fs.readFileSync(USER_PREFS_FILE, 'utf8');
            userPreferences = JSON.parse(data);
            console.log(`[PREFS] ${Object.keys(userPreferences).length} utilisateurs charges`);
        }
    } catch (error) {
        console.error('[PREFS] Erreur chargement:', error.message);
        userPreferences = {};
    }
}

// Sauvegarder les preferences dans le fichier
function saveUserPreferences() {
    try {
        fs.writeFileSync(USER_PREFS_FILE, JSON.stringify(userPreferences, null, 2));
        console.log('[PREFS] Preferences sauvegardees');
    } catch (error) {
        console.error('[PREFS] Erreur sauvegarde:', error.message);
    }
}

// Obtenir les preferences d'un utilisateur
function getUserPrefs(userNumber) {
    if (!userPreferences[userNumber]) {
        userPreferences[userNumber] = {
            city: null,
            language: null,
            step: STEPS.NEW,
            pendingQuestion: null
        };
    }
    return userPreferences[userNumber];
}

// Liste des villes ivoiriennes connues (pour validation)
const KNOWN_CITIES = [
    'abidjan', 'bouake', 'yamoussoukro', 'korhogo', 'san-pedro', 'san pedro',
    'daloa', 'divo', 'man', 'gagnoa', 'bonoua', 'soubre', 'abengourou',
    'ferkessedougou', 'ferke', 'odienne', 'seguela', 'bondoukou', 'aboisso',
    'danane', 'duekoue', 'guiglo', 'tabou', 'sassandra', 'grand-bassam',
    'jacqueville', 'agboville', 'dabou', 'dimbokro', 'toumodi', 'tiebissou',
    'katiola', 'boundiali', 'tengrela', 'anyama', 'bingerville', 'bouafle',
    'issia', 'lakota', 'sinfra', 'vavoua', 'zuenoula', 'beoumi', 'sakassou',
    'botro', 'daoukro', 'bocanda', 'mbahiakro', 'prikro', 'agnibilekrou',
    'tanda', 'transua', 'nassian', 'bouna', 'doropo', 'tehini', 'kong'
];

// Corrections courantes STT pour les noms de villes
const CITY_CORRECTIONS = {
    // Man
    'main': 'man', 'mane': 'man', 'mens': 'man', 'mang': 'man', 'mont': 'man',
    // Bouake
    'bouaké': 'bouake', 'bouakais': 'bouake', 'bouakay': 'bouake',
    // Korhogo
    'corogo': 'korhogo', 'korogho': 'korhogo', 'korhogho': 'korhogo',
    // San-Pedro
    'sampedro': 'san-pedro', 'san pédro': 'san-pedro', 'saint pedro': 'san-pedro',
    // Yamoussoukro
    'yamoussokro': 'yamoussoukro', 'yamouso': 'yamoussoukro', 'yamoussou': 'yamoussoukro',
    // Daloa
    'dalois': 'daloa', 'dalwa': 'daloa',
    // Gagnoa
    'ganyoa': 'gagnoa', 'ganoa': 'gagnoa',
    // Divo
    'divos': 'divo', 'divot': 'divo',
    // Abidjan
    'abijan': 'abidjan', 'abidjan': 'abidjan',
    // Bonoua
    'bonouat': 'bonoua', 'bonois': 'bonoua',
    // Ferkessedougou
    'ferké': 'ferkessedougou', 'ferke': 'ferkessedougou',
    // Grand-Bassam
    'bassam': 'grand-bassam', 'gran bassam': 'grand-bassam',
    // Kong
    'kong': 'kong', 'con': 'kong', 'quand': 'kong'
};

// Verifier si c'est une ville valide
function isValidCity(text) {
    const normalized = text.toLowerCase().trim();
    // Verifier corrections d'abord
    for (const [wrong, correct] of Object.entries(CITY_CORRECTIONS)) {
        if (normalized.includes(wrong)) return true;
    }
    return KNOWN_CITIES.some(city =>
        normalized.includes(city) || city.includes(normalized)
    );
}

// Extraire le nom de la ville du texte
function extractCity(text) {
    const normalized = text.toLowerCase().trim();

    // Extraire les mots individuels pour mieux matcher
    const words = normalized.split(/\s+/);

    // 1. Chercher d'abord dans les corrections STT (mot par mot)
    for (const word of words) {
        if (CITY_CORRECTIONS[word]) {
            const corrected = CITY_CORRECTIONS[word];
            return corrected.charAt(0).toUpperCase() + corrected.slice(1);
        }
    }

    // 2. Chercher dans la phrase complete (pour noms composes comme "san pedro")
    for (const [wrong, correct] of Object.entries(CITY_CORRECTIONS)) {
        if (normalized.includes(wrong)) {
            return correct.charAt(0).toUpperCase() + correct.slice(1);
        }
    }

    // 3. Chercher dans les villes connues
    for (const city of KNOWN_CITIES) {
        if (normalized.includes(city)) {
            return city.charAt(0).toUpperCase() + city.slice(1);
        }
    }

    // 4. Chercher similarite phonetique (derniere chance)
    for (const word of words) {
        if (word.length >= 3) {
            for (const city of KNOWN_CITIES) {
                // Verifier si le mot ressemble a une ville (debut similaire)
                if (city.startsWith(word.substring(0, 3)) || word.startsWith(city.substring(0, 3))) {
                    return city.charAt(0).toUpperCase() + city.slice(1);
                }
            }
        }
    }

    // Si pas trouve, retourner le dernier mot significatif (probable nom de ville)
    const lastWord = words.filter(w => w.length > 2).pop() || text.trim();
    return lastWord.charAt(0).toUpperCase() + lastWord.slice(1).toLowerCase();
}

// Detecter commande de changement
function detectChangeCommand(text) {
    const lower = text.toLowerCase();
    if (lower.includes('changer') && (lower.includes('ville') || lower.includes('localisation'))) {
        return 'city';
    }
    if (lower.includes('changer') && (lower.includes('langue') || lower.includes('language'))) {
        return 'language';
    }
    if (lower.includes('reinitialiser') || lower.includes('reset') || lower.includes('recommencer')) {
        return 'reset';
    }
    return null;
}

// ========================================
// FONCTIONS UTILITAIRES
// ========================================

// Fonction pour transcrire un audio via l'API STT (Whisper - Français)
// Retourne un objet avec text, likely_dioula_input, etc.
async function transcribeAudio(audioBuffer, filename = 'audio.ogg') {
    try {
        const FormData = require('form-data');
        const formData = new FormData();
        formData.append('audio', audioBuffer, {
            filename: filename,
            contentType: 'audio/ogg'
        });
        formData.append('language', 'fr');

        console.log(`[STT] Appel API: ${WOURI_API_URL}/api/stt/transcribe`);
        const response = await axios.post(`${WOURI_API_URL}/api/stt/transcribe`, formData, {
            headers: {
                ...formData.getHeaders()
            },
            timeout: 180000
        });
        console.log(`[STT] Reponse API recue: ${response.status}`);

        if (response.data && response.data.text) {
            return {
                text: response.data.text,
                likely_dioula_input: response.data.likely_dioula_input || false,
                language_probability: response.data.language_probability || 0
            };
        }
        return null;
    } catch (error) {
        console.log('[STT] Erreur transcription:', error.message);
        return null;
    }
}

// Fonction pour transcrire un audio en Bambara/Dioula via l'API ASR
// Utilise facebook/mms-1b-all pour la reconnaissance vocale Bambara
async function transcribeAudioBambara(audioBuffer, filename = 'audio.ogg') {
    try {
        const FormData = require('form-data');
        const formData = new FormData();
        formData.append('audio', audioBuffer, {
            filename: filename,
            contentType: 'audio/ogg'
        });
        formData.append('language', 'bam');  // Bambara/Dioula

        console.log(`[ASR-BAMBARA] Appel API: ${WOURI_API_URL}/api/asr/transcribe-and-translate`);
        const response = await axios.post(`${WOURI_API_URL}/api/asr/transcribe-and-translate`, formData, {
            headers: {
                ...formData.getHeaders()
            },
            timeout: 180000
        });
        console.log(`[ASR-BAMBARA] Reponse API recue: ${response.status}`);

        if (response.data) {
            const transcription = response.data.transcription || '';
            const frenchTranslation = response.data.french_translation || '';

            console.log(`[ASR-BAMBARA] Transcription Bambara: "${transcription}"`);
            console.log(`[ASR-BAMBARA] Traduction Francais: "${frenchTranslation}"`);

            return {
                text: frenchTranslation || transcription,  // Utiliser la traduction FR si disponible
                bambara_text: transcription,
                is_bambara: true
            };
        }
        return null;
    } catch (error) {
        console.log('[ASR-BAMBARA] Erreur transcription:', error.message);
        // Fallback vers Whisper français si ASR Bambara echoue
        console.log('[ASR-BAMBARA] Fallback vers Whisper francais...');
        return await transcribeAudio(audioBuffer, filename);
    }
}

// Fonction pour simuler un delai humain
function randomDelay(min, max) {
    return new Promise(resolve => setTimeout(resolve, Math.floor(Math.random() * (max - min + 1)) + min));
}

// Charger les preferences au demarrage
loadUserPreferences();

// ========================================
// CONNEXION WHATSAPP
// ========================================

async function connectWhatsApp() {
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
            console.log('   Systeme d\'onboarding actif');
            console.log('========================================\n');
        }
    });

    sock.ev.on('creds.update', saveCreds);

    // ========================================
    // GESTION DES MESSAGES ENTRANTS
    // ========================================

    sock.ev.on('messages.upsert', async ({ messages }) => {
        for (const msg of messages) {
            // Ignorer les messages envoyes par nous-meme
            if (msg.key.fromMe) continue;

            // Ignorer les messages de groupe
            if (msg.key.remoteJid.endsWith('@g.us')) continue;

            // Ignorer les statuts WhatsApp
            if (msg.key.remoteJid === 'status@broadcast') continue;

            const userNumber = msg.key.remoteJid;
            const prefs = getUserPrefs(userNumber);

            // Extraction du texte
            let messageText = msg.message?.conversation ||
                             msg.message?.extendedTextMessage?.text ||
                             msg.message?.buttonsResponseMessage?.selectedButtonId ||
                             msg.message?.listResponseMessage?.singleSelectReply?.selectedRowId ||
                             msg.message?.templateButtonReplyMessage?.selectedId ||
                             '';

            // Detecter si c'est un message vocal (pour adapter la reponse)
            const audioMsg = msg.message?.audioMessage;
            const isAudioMessage = audioMsg !== undefined && audioMsg !== null && !messageText;
            let isVoiceInput = false; // Pour savoir si l'utilisateur a envoye un vocal

            if (isAudioMessage) {
                console.log(`\n[AUDIO] Message vocal recu de: ${userNumber}`);

                if (!audioMsg?.mediaKey || !audioMsg?.url) {
                    console.log('[AUDIO] Message sans cle media valide - ignore');
                    continue;
                }

                try {
                    await sock.readMessages([msg.key]);
                    // Message vocal recu -> reponse sera audio -> afficher 'recording'
                    await sock.sendPresenceUpdate('recording', userNumber);

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
                        await sock.sendPresenceUpdate('paused', userNumber);
                        await sock.sendMessage(userNumber, {
                            text: "Desole, je n'ai pas pu recevoir votre message vocal. Reessayez."
                        });
                        continue;
                    }

                    console.log(`[AUDIO] Telecharge: ${audioBuffer.length} bytes`);

                    // Choisir le moteur de transcription selon la langue de l'utilisateur
                    // - Si langue = dioula -> utiliser ASR Bambara (MMS)
                    // - Sinon -> utiliser Whisper (francais)
                    let transcriptionResult;
                    const userLanguage = prefs.language || 'french';

                    if (userLanguage === 'dioula') {
                        console.log(`[AUDIO] Utilisateur en mode Dioula -> ASR Bambara`);
                        transcriptionResult = await transcribeAudioBambara(audioBuffer, 'voice_message.ogg');
                    } else {
                        console.log(`[AUDIO] Utilisateur en mode ${userLanguage} -> Whisper francais`);
                        transcriptionResult = await transcribeAudio(audioBuffer, 'voice_message.ogg');
                    }

                    if (!transcriptionResult || !transcriptionResult.text || transcriptionResult.text.trim() === '') {
                        await sock.sendPresenceUpdate('paused', userNumber);
                        await sock.sendMessage(userNumber, {
                            text: "Desole, je n'ai pas compris votre message vocal. Pouvez-vous repeter?"
                        });
                        continue;
                    }

                    const transcribedText = transcriptionResult.text;
                    const likelyDioulaInput = transcriptionResult.likely_dioula_input || false;
                    const isBambaraTranscription = transcriptionResult.is_bambara || false;

                    console.log(`[STT] Transcription: "${transcribedText}"`);
                    if (isBambaraTranscription) {
                        console.log(`[STT] Transcription Bambara reussie!`);
                        if (transcriptionResult.bambara_text) {
                            console.log(`[STT] Texte Bambara original: "${transcriptionResult.bambara_text}"`);
                        }
                    } else if (likelyDioulaInput) {
                        console.log(`[STT] ATTENTION: Audio probablement en Dioula - transcription peut etre incorrecte`);
                    }

                    messageText = transcribedText;
                    isVoiceInput = true; // Marquer comme message vocal

                } catch (audioError) {
                    console.error('[AUDIO] Erreur:', audioError.message);
                    await sock.sendPresenceUpdate('paused', userNumber);
                    await sock.sendMessage(userNumber, {
                        text: "Desole, je n'ai pas pu traiter votre message vocal."
                    });
                    continue;
                }
            }

            if (!messageText) continue;

            console.log(`\n[MESSAGE] De: ${userNumber}`);
            console.log(`[MESSAGE] Texte: ${messageText}`);
            console.log(`[MESSAGE] Etape: ${prefs.step}`);

            try {
                await sock.readMessages([msg.key]);
                await randomDelay(500, 1000);
                await sock.sendPresenceUpdate('composing', userNumber);

                // ========================================
                // DETECTER COMMANDES DE CHANGEMENT
                // ========================================
                const changeCommand = detectChangeCommand(messageText);
                if (changeCommand && prefs.step === STEPS.COMPLETE) {
                    if (changeCommand === 'city') {
                        prefs.step = STEPS.WAITING_CITY;
                        saveUserPreferences();
                        await sock.sendPresenceUpdate('paused', userNumber);
                        await sock.sendMessage(userNumber, {
                            text: "📍 D'accord ! Dans quelle ville etes-vous maintenant ?\n\n(Repondez avec le nom de votre ville)"
                        });
                        continue;
                    }
                    if (changeCommand === 'language') {
                        prefs.step = STEPS.WAITING_LANGUAGE;
                        saveUserPreferences();
                        await sock.sendPresenceUpdate('paused', userNumber);
                        await sock.sendMessage(userNumber, {
                            text: "🗣️ Dans quelle langue souhaitez-vous les reponses ?\n\n1️⃣ Francais\n2️⃣ Dioula\n3️⃣ Les deux\n\n(Repondez avec 1, 2 ou 3)"
                        });
                        continue;
                    }
                    if (changeCommand === 'reset') {
                        prefs.step = STEPS.NEW;
                        prefs.city = null;
                        prefs.language = null;
                        prefs.pendingQuestion = null;
                        saveUserPreferences();
                        await sock.sendPresenceUpdate('paused', userNumber);
                        await sock.sendMessage(userNumber, {
                            text: "🔄 Preferences reinitialises ! Envoyez un message pour recommencer."
                        });
                        continue;
                    }
                }

                // ========================================
                // ONBOARDING - ETAPE 1: NOUVEAU UTILISATEUR
                // ========================================
                if (prefs.step === STEPS.NEW) {
                    // Sauvegarder le message initial comme question en attente
                    prefs.pendingQuestion = messageText;
                    prefs.step = STEPS.WAITING_CITY;
                    saveUserPreferences();

                    await sock.sendPresenceUpdate('paused', userNumber);
                    await sock.sendMessage(userNumber, {
                        text: "🌾 *Bienvenue sur WOURI !*\nVotre assistant agricole intelligent.\n\n📍 Dans quelle ville etes-vous ?\n\n(Repondez avec le nom de votre ville : Abidjan, Bouake, Divo, Bonoua, etc.)"
                    });
                    continue;
                }

                // ========================================
                // ONBOARDING - ETAPE 2: ATTENTE VILLE
                // ========================================
                if (prefs.step === STEPS.WAITING_CITY) {
                    const cityName = extractCity(messageText);
                    prefs.city = cityName;
                    prefs.step = STEPS.WAITING_LANGUAGE;
                    saveUserPreferences();

                    await sock.sendPresenceUpdate('paused', userNumber);
                    await sock.sendMessage(userNumber, {
                        text: `✅ Ville enregistree : *${cityName}*\n\n🗣️ Dans quelle langue souhaitez-vous les reponses ?\n\n1️⃣ Francais\n2️⃣ Dioula\n3️⃣ Les deux (Francais ecrit + Dioula audio)\n\n(Repondez avec 1, 2 ou 3)`
                    });
                    continue;
                }

                // ========================================
                // ONBOARDING - ETAPE 3: ATTENTE LANGUE
                // ========================================
                if (prefs.step === STEPS.WAITING_LANGUAGE) {
                    const input = messageText.trim().toLowerCase();
                    let language = null;

                    if (input === '1' || input.includes('francais') || input.includes('français')) {
                        language = 'french';
                    } else if (input === '2' || input.includes('dioula') || input.includes('bambara')) {
                        language = 'dioula';
                    } else if (input === '3' || input.includes('deux') || input.includes('both')) {
                        language = 'both';
                    }

                    if (!language) {
                        await sock.sendPresenceUpdate('paused', userNumber);
                        await sock.sendMessage(userNumber, {
                            text: "❓ Je n'ai pas compris. Repondez avec :\n\n1️⃣ pour Francais\n2️⃣ pour Dioula\n3️⃣ pour Les deux"
                        });
                        continue;
                    }

                    prefs.language = language;
                    prefs.step = STEPS.COMPLETE;

                    const langText = language === 'french' ? 'Francais' :
                                    language === 'dioula' ? 'Dioula' : 'Francais + Dioula';

                    await sock.sendPresenceUpdate('paused', userNumber);
                    await sock.sendMessage(userNumber, {
                        text: `✅ *Preferences enregistrees !*\n\n📍 Ville : ${prefs.city}\n🗣️ Langue : ${langText}\n\n💡 Pour changer : dites "changer ville" ou "changer langue"\n\nPosez-moi vos questions sur l'agriculture ! 🌱`
                    });

                    // Traiter la question en attente s'il y en a une
                    if (prefs.pendingQuestion) {
                        messageText = prefs.pendingQuestion;
                        prefs.pendingQuestion = null;
                        saveUserPreferences();

                        // Continuer le traitement ci-dessous
                        await randomDelay(1000, 2000);
                        await sock.sendPresenceUpdate('composing', userNumber);
                    } else {
                        saveUserPreferences();
                        continue;
                    }
                }

                // ========================================
                // TRAITEMENT DES QUESTIONS (ONBOARDING COMPLETE)
                // ========================================
                if (prefs.step === STEPS.COMPLETE) {
                    console.log(`[API] Appel avec ville: ${prefs.city}, langue: ${prefs.language}, voiceInput: ${isVoiceInput}`);

                    // Determiner le type de presence selon le contexte
                    // - Si entree vocale OU langue dioula/both -> reponse audio probable -> 'recording'
                    // - Sinon -> reponse texte -> 'composing'
                    const willBeAudio = isVoiceInput || prefs.language === 'dioula' || prefs.language === 'both';
                    const presenceType = willBeAudio ? 'recording' : 'composing';

                    // Maintenir le statut pendant le traitement
                    let keepPresence = true;
                    const presenceInterval = setInterval(async () => {
                        if (keepPresence) {
                            try {
                                await sock.sendPresenceUpdate(presenceType, userNumber);
                            } catch (e) {}
                        }
                    }, 5000);

                    let data;
                    try {
                        const response = await axios.post(`${WOURI_API_URL}/api/chat/`, {
                            message: messageText,
                            city: prefs.city,
                            language: prefs.language,
                            include_audio: true,
                            user_id: userNumber  // Pour l'historique de conversation
                        }, { timeout: 180000 });
                        data = response.data;
                    } finally {
                        keepPresence = false;
                        clearInterval(presenceInterval);
                    }

                    console.log(`[API] Reponse recue`);
                    await sock.sendPresenceUpdate('paused', userNumber);
                    await randomDelay(300, 800);

                    // ========================================
                    // ENVOI DES REPONSES SELON LA LANGUE ET LE TYPE D'ENTREE
                    // ========================================
                    // Logique:
                    // - Message texte recu -> Reponse texte
                    // - Message vocal recu -> Reponse audio

                    // FRANCAIS
                    if (prefs.language === 'french') {
                        if (isVoiceInput) {
                            // Entree vocale -> Reponse audio francais
                            // Note: Pour french, l'audio est dans audio_url (pas audio_url_fr)
                            if (data.audio_url) {
                                try {
                                    const audioUrl = data.audio_url.startsWith('http')
                                        ? data.audio_url
                                        : `${WOURI_API_URL}${data.audio_url}`;

                                    const audioResponse = await axios.get(audioUrl, {
                                        responseType: 'arraybuffer',
                                        timeout: 30000
                                    });

                                    await sock.sendPresenceUpdate('recording', userNumber);
                                    await randomDelay(1000, 2000);
                                    await sock.sendPresenceUpdate('paused', userNumber);

                                    await sock.sendMessage(userNumber, {
                                        audio: Buffer.from(audioResponse.data),
                                        mimetype: 'audio/ogg; codecs=opus',
                                        ptt: true
                                    });
                                    console.log('[ENVOYE] Audio francais (reponse a vocal)');
                                } catch (audioErr) {
                                    console.log('[AUDIO FR] Erreur:', audioErr.message);
                                    // Fallback: envoyer le texte si audio echoue
                                    if (data.response) {
                                        await sock.sendMessage(userNumber, {
                                            text: `🇫🇷 ${data.response}`
                                        });
                                    }
                                }
                            } else if (data.response) {
                                // Pas d'audio disponible, envoyer le texte
                                await sock.sendMessage(userNumber, {
                                    text: `🇫🇷 ${data.response}`
                                });
                                console.log('[ENVOYE] Texte francais (audio non disponible)');
                            }
                        } else {
                            // Entree texte -> Reponse texte francais
                            if (data.response) {
                                await sock.sendMessage(userNumber, {
                                    text: `🇫🇷 ${data.response}`
                                });
                                console.log('[ENVOYE] Texte francais (reponse a texte)');
                            }
                        }
                    }

                    // DIOULA: Audio Dioula uniquement (pas de texte)
                    else if (prefs.language === 'dioula') {
                        if (data.audio_url) {
                            try {
                                const audioUrl = data.audio_url.startsWith('http')
                                    ? data.audio_url
                                    : `${WOURI_API_URL}${data.audio_url}`;

                                const audioResponse = await axios.get(audioUrl, {
                                    responseType: 'arraybuffer',
                                    timeout: 30000
                                });

                                await sock.sendPresenceUpdate('recording', userNumber);
                                await randomDelay(1000, 2000);
                                await sock.sendPresenceUpdate('paused', userNumber);

                                await sock.sendMessage(userNumber, {
                                    audio: Buffer.from(audioResponse.data),
                                    mimetype: 'audio/ogg; codecs=opus',
                                    ptt: true
                                });
                                console.log('[ENVOYE] Audio dioula (pas de texte)');
                            } catch (audioErr) {
                                console.log('[AUDIO DIOULA] Erreur:', audioErr.message);
                                // Fallback: envoyer le texte dioula si audio echoue
                                if (data.response_dioula) {
                                    await sock.sendMessage(userNumber, {
                                        text: `🇲🇱 ${data.response_dioula}`
                                    });
                                }
                            }
                        } else if (data.response_dioula) {
                            // Pas d'audio disponible, envoyer le texte
                            await sock.sendMessage(userNumber, {
                                text: `🇲🇱 ${data.response_dioula}`
                            });
                            console.log('[ENVOYE] Texte dioula (audio non disponible)');
                        }
                    }

                    // LES DEUX: Adapte selon le type d'entree
                    // - Texte recu -> Texte FR + Audio Dioula
                    // - Vocal recu -> Audio FR + Audio Dioula (ou juste Audio Dioula)
                    else if (prefs.language === 'both') {
                        if (isVoiceInput) {
                            // Entree vocale -> Reponse audio (Texte FR + Audio Dioula)
                            // On envoie le texte FR pour qu'il puisse lire aussi
                            if (data.response) {
                                await sock.sendMessage(userNumber, {
                                    text: `🇫🇷 ${data.response}`
                                });
                                console.log('[ENVOYE] Texte francais');
                            }

                            // Audio dioula
                            if (data.audio_url) {
                                try {
                                    await randomDelay(500, 1000);
                                    const audioUrl = data.audio_url.startsWith('http')
                                        ? data.audio_url
                                        : `${WOURI_API_URL}${data.audio_url}`;

                                    const audioResponse = await axios.get(audioUrl, {
                                        responseType: 'arraybuffer',
                                        timeout: 30000
                                    });

                                    await sock.sendPresenceUpdate('recording', userNumber);
                                    await randomDelay(1000, 2000);
                                    await sock.sendPresenceUpdate('paused', userNumber);

                                    await sock.sendMessage(userNumber, {
                                        audio: Buffer.from(audioResponse.data),
                                        mimetype: 'audio/ogg; codecs=opus',
                                        ptt: true
                                    });
                                    console.log('[ENVOYE] Audio dioula (reponse a vocal)');
                                } catch (audioErr) {
                                    console.log('[AUDIO DIOULA] Erreur:', audioErr.message);
                                }
                            }
                        } else {
                            // Entree texte -> Texte FR + Audio Dioula
                            if (data.response) {
                                await sock.sendMessage(userNumber, {
                                    text: `🇫🇷 ${data.response}`
                                });
                                console.log('[ENVOYE] Texte francais (reponse a texte)');
                            }

                            // Audio dioula
                            if (data.audio_url) {
                                try {
                                    await randomDelay(500, 1000);
                                    const audioUrl = data.audio_url.startsWith('http')
                                        ? data.audio_url
                                        : `${WOURI_API_URL}${data.audio_url}`;

                                    const audioResponse = await axios.get(audioUrl, {
                                        responseType: 'arraybuffer',
                                        timeout: 30000
                                    });

                                    await sock.sendPresenceUpdate('recording', userNumber);
                                    await randomDelay(1000, 2000);
                                    await sock.sendPresenceUpdate('paused', userNumber);

                                    await sock.sendMessage(userNumber, {
                                        audio: Buffer.from(audioResponse.data),
                                        mimetype: 'audio/ogg; codecs=opus',
                                        ptt: true
                                    });
                                    console.log('[ENVOYE] Audio dioula');
                                } catch (audioErr) {
                                    console.log('[AUDIO DIOULA] Erreur:', audioErr.message);
                                }
                            }
                        }
                    }
                }

            } catch (error) {
                console.error('[ERREUR]', error.message);
                await sock.sendPresenceUpdate('paused', userNumber);
                await randomDelay(500, 1000);
                await sock.sendMessage(userNumber, {
                    text: "Desole, je rencontre un probleme technique. Reessayez dans quelques instants."
                });
            }
        }
    });
}

// ========================================
// ROUTES API EXPRESS
// ========================================

app.get('/', (req, res) => {
    res.json({
        status: 'running',
        name: 'WOURI WhatsApp Server',
        connected: isConnected,
        users: Object.keys(userPreferences).length
    });
});

app.get('/status', (req, res) => {
    res.json({
        connected: isConnected,
        qrCode: qrCodeData,
        users: Object.keys(userPreferences).length
    });
});

app.get('/users', (req, res) => {
    // Retourne les preferences de tous les utilisateurs (sans numero complet pour confidentialite)
    const users = Object.entries(userPreferences).map(([number, prefs]) => ({
        number: number.substring(0, 8) + '***',
        city: prefs.city,
        language: prefs.language,
        step: prefs.step
    }));
    res.json(users);
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
            h1 { color: #075E54; margin-bottom: 10px; }
            h2 { color: #666; font-weight: normal; margin-top: 0; }
            .qr-container { margin: 20px 0; }
            .instructions { color: #666; margin-top: 20px; text-align: left; }
            .instructions ol { padding-left: 20px; }
            .refresh-note { color: #999; font-size: 12px; margin-top: 15px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🌾 WOURI</h1>
            <h2>Assistant Agricole WhatsApp</h2>
            <div class="qr-container">${qrImageHtml}</div>
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
            <div class="refresh-note">Page auto-refresh toutes les 5 secondes</div>
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
        if (fs.existsSync(AUTH_FOLDER)) {
            fs.rmSync(AUTH_FOLDER, { recursive: true });
        }
        res.json({ success: true, message: 'Deconnecte' });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// ========================================
// DEMARRAGE DU SERVEUR
// ========================================

app.listen(PORT, () => {
    console.log('\n========================================');
    console.log('   WOURI WhatsApp Server');
    console.log('========================================');
    console.log(`API: http://localhost:${PORT}`);
    console.log(`WOURI API: ${WOURI_API_URL}`);
    console.log(`Utilisateurs: ${Object.keys(userPreferences).length}`);
    console.log('========================================\n');

    connectWhatsApp();
});
