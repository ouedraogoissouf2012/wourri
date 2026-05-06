/**
 * WOURI WhatsApp Server - Version Baileys
 * Serveur WhatsApp avec onboarding utilisateur
 * Demande ville et langue preferee avant de repondre
 */

// Charger les variables d'environnement depuis .env AVANT toute lecture de process.env
require('dotenv').config();

const { default: makeWASocket, DisconnectReason, useMultiFileAuthState, downloadMediaMessage, fetchLatestBaileysVersion } = require('@whiskeysockets/baileys');
const pino = require('pino');
const axios = require('axios');
const fs = require('fs');
const path = require('path');
const express = require('express');
const cors = require('cors');
const qrcode = require('qrcode-terminal');
const QRCode = require('qrcode');

// Phase 2 Robustesse — modules locaux (lib/)
const {
    computeBackoffDelay,
    isReconnectable,
    describeDisconnectReason,
    MAX_ATTEMPTS,
} = require('./lib/reconnect');
const { MessageQueue } = require('./lib/message_queue');
const { CircuitBreaker, CircuitOpenError } = require('./lib/circuit_breaker');

// Configuration
const PORT = process.env.PORT || 3001;
const WOURI_API_URL = process.env.WOURI_API_URL || 'http://localhost:8000';
const WOURI_API_KEY = process.env.WOURI_API_KEY || '';
const AUTH_FOLDER = path.join(__dirname, 'auth_baileys');
const TEMP_AUDIO_FOLDER = path.join(__dirname, 'temp_audio');
const USER_PREFS_FILE = path.join(__dirname, 'user_preferences.json');
const PENDING_MESSAGES_FILE = path.join(__dirname, 'pending_messages.json');

// [P0-02a] Helper : header X-API-Key pour appels backend Wourri
// Si WOURI_API_KEY vide, retourne objet vide (mode dev backend avec auth desactivee)
function authHeaders() {
    return WOURI_API_KEY ? { 'X-API-Key': WOURI_API_KEY } : {};
}

// Avertissement demarrage si API_KEY manquante en production
if (process.env.NODE_ENV === 'production' && !WOURI_API_KEY) {
    console.warn('[SECURITY] WOURI_API_KEY non definie en production — les appels backend echoueront si API_SECRET_KEY y est configuree');
}

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

// Phase 2 Robustesse
let reconnectAttempt = 0;  // Compteur de tentatives consécutives, reset à 0 après connexion réussie

// Queue persistante des messages reçus (anti-perte si API backend down)
const messageQueue = new MessageQueue({
    filePath: PENDING_MESSAGES_FILE,
    maxAttempts: 5,
});

// Circuit breaker sur les appels à wouri-api
// Ouvre si > 50% d'erreurs sur les 10 derniers appels, ré-essaie après 30s
const apiCircuitBreaker = new CircuitBreaker({
    name: 'wouri-api',
    windowSize: 10,
    failureThreshold: 0.5,
    openDurationMs: 30000,
    halfOpenMaxCalls: 1,
});

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
    COMPLETE: 'complete',          // Onboarding termine
    WAITING_FEEDBACK: 'waiting_feedback' // En attente du feedback 👍/👎
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

// Verrou d'ecriture pour eviter les race conditions
let _saveInProgress = false;
let _savePending = false;

// Sauvegarder les preferences dans le fichier (debounced, sans race condition)
function saveUserPreferences() {
    if (_saveInProgress) {
        _savePending = true;  // une autre sauvegarde est en cours, on rejoue apres
        return;
    }
    _saveInProgress = true;
    const snapshot = JSON.stringify(userPreferences, null, 2);
    fs.writeFile(USER_PREFS_FILE, snapshot, 'utf8', (err) => {
        _saveInProgress = false;
        if (err) {
            console.error('[PREFS] Erreur sauvegarde:', err.message);
        }
        if (_savePending) {
            _savePending = false;
            saveUserPreferences();  // rejouer la sauvegarde en attente
        }
    });
}

// Obtenir les preferences d'un utilisateur
function getUserPrefs(userNumber) {
    if (!userPreferences[userNumber]) {
        userPreferences[userNumber] = {
            city: null,
            language: null,
            step: STEPS.NEW,
            pendingQuestion: null,
            pendingFeedback: null
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

// Distance de Levenshtein entre deux chaînes
function levenshtein(a, b) {
    const m = a.length, n = b.length;
    const dp = Array.from({ length: m + 1 }, (_, i) => [i, ...Array(n).fill(0)]);
    for (let j = 0; j <= n; j++) dp[0][j] = j;
    for (let i = 1; i <= m; i++) {
        for (let j = 1; j <= n; j++) {
            dp[i][j] = a[i-1] === b[j-1]
                ? dp[i-1][j-1]
                : 1 + Math.min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1]);
        }
    }
    return dp[m][n];
}

// Extraire le nom de la ville du texte
function extractCity(text) {
    const normalized = text.toLowerCase().trim();

    // Extraire les mots individuels pour mieux matcher
    const words = normalized.split(/\s+/);

    // 1. Chercher d'abord dans les corrections STT (mot entier uniquement)
    for (const word of words) {
        if (CITY_CORRECTIONS[word]) {
            const corrected = CITY_CORRECTIONS[word];
            return corrected.charAt(0).toUpperCase() + corrected.slice(1);
        }
    }

    // 2. Chercher dans la phrase complete (pour noms composes comme "san pedro")
    for (const [wrong, correct] of Object.entries(CITY_CORRECTIONS)) {
        // Mot entier via regex pour eviter "con" dans "conseil"
        const pattern = new RegExp('\\b' + wrong.replace(/[-]/g, '\\-') + '\\b');
        if (pattern.test(normalized)) {
            return correct.charAt(0).toUpperCase() + correct.slice(1);
        }
    }

    // 3. Chercher dans les villes connues (mot entier)
    for (const city of KNOWN_CITIES) {
        const pattern = new RegExp('\\b' + city.replace(/[-]/g, '\\-') + '\\b');
        if (pattern.test(normalized)) {
            return city.charAt(0).toUpperCase() + city.slice(1);
        }
    }

    // 4. Similarite Levenshtein (seuil 0.8) — uniquement pour mots >= 4 chars
    for (const word of words) {
        if (word.length >= 4) {
            for (const city of KNOWN_CITIES) {
                if (city.length < 4) continue;  // eviter "man", "kon"
                const maxLen = Math.max(word.length, city.length);
                const similarity = 1 - levenshtein(word, city) / maxLen;
                if (similarity >= 0.8) {
                    return city.charAt(0).toUpperCase() + city.slice(1);
                }
            }
        }
    }

    // Si pas trouve, retourner le dernier mot significatif (probable nom de ville)
    const lastWord = words.filter(w => w.length > 3).pop() || text.trim();
    return lastWord.charAt(0).toUpperCase() + lastWord.slice(1).toLowerCase();
}

// ========================================
// MESSAGES BILINGUES — Dioula CI + Français
// Syntaxe CI v1.9 : Aw ye / aw ta / caman / filɛ
// ========================================
const MSG = {
    WELCOME:
        `🌾 *Aw ni tile ! N tɔgɔ ye WOURI ye.*\nSɛnnɛkɛlaw ka dɛmɛbaga — Côte d'Ivoire ni Mali.\n\n📍 Aw bɛ min dugu la ?\n(Aw ka dugu tɔgɔ ci : Abidjan, Bouaké, Divo, Bonoua...)\n\n---\n🌾 *Bienvenue sur WOURI !*\nVotre assistant agricole.\n📍 Dans quelle ville êtes-vous ?`,

    ASK_CITY:
        `📍 Aw bɛ min dugu la sisan ?\n(Aw ka dugu tɔgɔ ci)\n\n---\nDans quelle ville êtes-vous maintenant ?`,

    CITY_OK: (city) =>
        `✅ Dugu tɔgɔ : *${city}*\n\n🗣️ Aw bɛ kuma jaki la ?\n\n1️⃣ Faransi\n2️⃣ Dioula\n3️⃣ Fila fila (Faransi + Dioula audio)\n\n(1, 2 wala 3 ci)\n\n---\nVille : *${city}*\n🗣️ Langue préférée ?\n1️⃣ Français  2️⃣ Dioula  3️⃣ Les deux`,

    LANGUAGE_UNKNOWN:
        `❓ N ma faamu. 1, 2 wala 3 ci.\n\n1️⃣ Faransi\n2️⃣ Dioula\n3️⃣ Fila fila\n\n---\nJe n'ai pas compris. Répondez 1, 2 ou 3.`,

    PREFS_SAVED: (city, lang) =>
        `✅ *Dɔ sɔrɔla !*\n📍 Dugu : ${city}\n🗣️ Kuma : ${lang}\n\n💡 Aw b'a fɛ ka yɛlɛma : "changer ville" wala "changer langue"\n\nAw ka ɲinini ci sɛnnɛ koo la ! 🌱\n\n---\n✅ *Préférences enregistrées !*\n💡 Pour changer : dites "changer ville" ou "changer langue"`,

    CHANGE_CITY:
        `📍 Dugu wɛrɛ tɔgɔ ci.\n\n---\nDans quelle ville êtes-vous maintenant ?`,

    CHANGE_LANGUAGE:
        `🗣️ Kuma jaki la ?\n\n1️⃣ Faransi\n2️⃣ Dioula\n3️⃣ Fila fila\n\n---\nQuelle langue préférée ? (1, 2 ou 3)`,

    RESET:
        `🔄 Dɔ bɛɛ kɛra kura. Kumakan dɔ ci.\n\n---\nPréférences réinitialisées. Envoyez un message pour recommencer.`,

    AUDIO_FAILED:
        `🎤 N ma i ka kumakan faamu. I ka a lasɔgɔ tugu.\n\n---\nJe n'ai pas compris votre message vocal. Pouvez-vous répéter ?`,

    AUDIO_ERROR:
        `⚠️ Kumakan in ma se ka bɔ. I ka sɛbɛn fɛ ɲinini ci.\n\n---\nImpossible de traiter ce message vocal. Écrivez votre question.`,
};

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
                ...formData.getHeaders(),
                ...authHeaders()
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
                ...formData.getHeaders(),
                ...authHeaders()
            },
            timeout: 180000
        });
        console.log(`[ASR-BAMBARA] Reponse API recue: ${response.status}`);

        if (response.data) {
            const transcription = response.data.transcription || '';
            const frenchTranslation = response.data.french_translation || '';
            const nluMessage = response.data.nlu_message || '';

            console.log(`[ASR-BAMBARA] Transcription Bambara: "${transcription}"`);
            console.log(`[ASR-BAMBARA] Traduction Francais: "${frenchTranslation}"`);
            if (nluMessage) {
                console.log(`[ASR-BAMBARA] Message NLU (prioritaire): "${nluMessage}"`);
            }

            return {
                text: nluMessage || frenchTranslation || transcription,  // NLU en priorité
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

/**
 * Génère un audio TTS à partir d'un texte fixe (best-effort).
 *
 * Utilisé pour les messages d'indisponibilité audio quand l'utilisateur
 * a envoyé un vocal. Si l'API TTS est down ou prend trop de temps,
 * retourne null et le caller doit fallback sur du texte.
 *
 * Endpoints utilisés (côté wouri-api) :
 *   - français : POST /api/tts/?text=...
 *   - dioula   : POST /api/tts/bambara?text=...&is_french=false
 *
 * @param {string} text - Texte à synthétiser
 * @param {boolean} isFrench - true → Edge-TTS français, false → MMS dioula
 * @param {number} [timeoutMs=5000] - Timeout court pour ne pas bloquer
 * @returns {Promise<Buffer|null>} Buffer audio OGG/Opus, ou null si échec
 */
async function tryGenerateAudioFromText(text, isFrench, timeoutMs = 5000) {
    if (!text) return null;
    const endpoint = isFrench ? '/api/tts/' : '/api/tts/bambara';
    const params = isFrench ? { text } : { text, is_french: false };
    try {
        const ttsResponse = await axios.post(
            `${WOURI_API_URL}${endpoint}`,
            null,
            { params, timeout: timeoutMs, headers: authHeaders() }
        );
        const audioUrl = ttsResponse.data?.audio_url;
        if (!audioUrl) return null;
        const fullUrl = audioUrl.startsWith('http')
            ? audioUrl
            : `${WOURI_API_URL}${audioUrl}`;
        const audioResp = await axios.get(fullUrl, {
            responseType: 'arraybuffer',
            timeout: timeoutMs,
        });
        return Buffer.from(audioResp.data);
    } catch (err) {
        console.log(
            `[EXCUSE-AUDIO] Génération ${isFrench ? 'FR' : 'dioula'} échouée (${err.code || (err.message || '').substring(0, 80)}) — fallback texte`
        );
        return null;
    }
}

// Textes des messages d'indisponibilité (utilisés pour TTS si vocal, sinon texte)
const EXCUSE_MSG = {
    // Circuit OPEN : "je rencontre un problème"
    UNAVAILABLE_FR: "Je rencontre un problème technique temporaire. Je te répondrai dès que possible.",
    UNAVAILABLE_DIOULA: "N bɛ baara la sisan. N bɛna jaabi i ma joona.",
    UNAVAILABLE_BILINGUAL:
        '🌾 N bɛ baara la sisan. N bɛna jaabi i ma joona.\n\n---\n🌾 Je rencontre un problème technique temporaire. Je te répondrai dès que possible.',
    // Reconnexion WA : "je suis de retour"
    BACK_FR: "Je suis de retour. Pose-moi à nouveau ta question.",
    BACK_DIOULA: "N nana segin. I ka ɲinini ci tugu n ma.",
    BACK_BILINGUAL:
        '🌾 Aw ni ce, n nana segin. Aw ka ɲinini ci tugu n ma.\n\n---\n🌾 Je suis de retour. Pose-moi à nouveau ta question.',
};

/**
 * Envoie un message d'excuse adapté au format du dernier message utilisateur.
 *
 * Règle uniforme :
 *   - Si le dernier message était vocal → tente d'envoyer un audio dans la langue
 *     (dioula si mode dioula/both, français si mode french)
 *   - Si écrit OU si génération audio échoue → texte bilingue (fallback)
 *
 * @param {string} userNumber - Numéro WhatsApp destinataire
 * @param {object} options
 * @param {boolean} options.isVoiceInput - Le dernier message était-il vocal ?
 * @param {string} options.language - 'french' | 'dioula' | 'both'
 * @param {'unavailable'|'back'} options.kind - Type de message
 */
async function sendExcuseMessage(userNumber, { isVoiceInput, language, kind }) {
    const isFrench = language === 'french';
    const audioText = kind === 'back'
        ? (isFrench ? EXCUSE_MSG.BACK_FR : EXCUSE_MSG.BACK_DIOULA)
        : (isFrench ? EXCUSE_MSG.UNAVAILABLE_FR : EXCUSE_MSG.UNAVAILABLE_DIOULA);
    const fallbackText = kind === 'back'
        ? EXCUSE_MSG.BACK_BILINGUAL
        : EXCUSE_MSG.UNAVAILABLE_BILINGUAL;

    let audioSent = false;
    if (isVoiceInput) {
        try { await sock.sendPresenceUpdate('recording', userNumber); } catch (_) {}
        const audioBuffer = await tryGenerateAudioFromText(audioText, isFrench);
        if (audioBuffer) {
            await sock.sendMessage(userNumber, {
                audio: audioBuffer,
                mimetype: 'audio/ogg; codecs=opus',
                ptt: true,
            });
            audioSent = true;
            console.log(`[EXCUSE] Audio ${isFrench ? 'FR' : 'dioula'} envoyé (${kind})`);
        }
        try { await sock.sendPresenceUpdate('paused', userNumber); } catch (_) {}
    }

    if (!audioSent) {
        await sock.sendMessage(userNumber, { text: fallbackText });
        console.log(`[EXCUSE] Texte bilingue envoyé (${kind}, isVoice=${isVoiceInput})`);
    }
}

// Charger les preferences au demarrage
loadUserPreferences();

// Phase 2 — Charger la queue persistante au demarrage
messageQueue.load().then((n) => {
    if (n > 0) {
        console.log(`[QUEUE] ${n} message(s) en attente charges depuis ${PENDING_MESSAGES_FILE}`);
        const dead = messageQueue.getDead();
        if (dead.length > 0) {
            console.warn(`[QUEUE] ${dead.length} message(s) "morts" (>${messageQueue.maxAttempts} tentatives) - a inspecter manuellement`);
        }
    } else {
        console.log('[QUEUE] Aucun message en attente');
    }
}).catch((err) => {
    console.error('[QUEUE] Erreur chargement initial :', err.message);
});

// Phase 2 — Notifier les utilisateurs ayant des messages en attente apres reconnexion WhatsApp
// Le format (audio/texte) s'adapte au format du DERNIER message reçu de chaque utilisateur.
async function notifyPendingUsers() {
    const pending = messageQueue.getPending();
    if (pending.length === 0) return;

    // Pour chaque utilisateur : retenir le DERNIER message reçu (pour adapter le format)
    const lastMessageByUser = new Map();
    for (const msg of pending) {
        if (!msg.userNumber) continue;
        const existing = lastMessageByUser.get(msg.userNumber);
        if (!existing || new Date(msg.createdAt) > new Date(existing.createdAt)) {
            lastMessageByUser.set(msg.userNumber, msg);
        }
    }

    console.log(`[QUEUE] Notification de ${lastMessageByUser.size} utilisateur(s) ayant des messages en attente`);

    for (const [userNumber, lastMsg] of lastMessageByUser) {
        try {
            const isVoiceInput = lastMsg.payload?.isVoiceInput === true;
            const language = lastMsg.payload?.language || 'french';
            await sendExcuseMessage(userNumber, {
                isVoiceInput,
                language,
                kind: 'back',
            });
            // Retirer les messages en attente de cet utilisateur (deja repondus avec excuse)
            const userMessages = pending.filter((m) => m.userNumber === userNumber);
            for (const m of userMessages) {
                await messageQueue.markSuccess(m.id);
            }
        } catch (err) {
            console.error(`[QUEUE] Erreur notification ${userNumber} :`, err.message);
        }
    }
}

// ========================================
// CONNEXION WHATSAPP
// ========================================

async function connectWhatsApp() {
    if (!fs.existsSync(AUTH_FOLDER)) {
        fs.mkdirSync(AUTH_FOLDER, { recursive: true });
    }

    const { state, saveCreds } = await useMultiFileAuthState(AUTH_FOLDER);

    // Récupérer la dernière version WhatsApp Web compatible
    const { version, isLatest } = await fetchLatestBaileysVersion();
    console.log(`[BAILEYS] Version WhatsApp Web: ${version.join('.')} (latest: ${isLatest})`);

    sock = makeWASocket({
        version,
        auth: state,
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
            const reasonName = describeDisconnectReason(statusCode);
            const reconnectable = isReconnectable(statusCode);

            console.log(`[RECONNECT] Connexion fermee : ${reasonName} (code=${statusCode})`);

            if (!reconnectable) {
                console.log(`[RECONNECT] Raison non-recuperable (${reasonName}). Action manuelle requise :`);
                console.log('[RECONNECT]   - loggedOut/badSession : supprimez auth_baileys/ puis redemarrez');
                console.log('[RECONNECT]   - forbidden : compte WhatsApp possiblement banni, contactez Meta');
                return;
            }

            if (reconnectAttempt >= MAX_ATTEMPTS) {
                console.error(`[RECONNECT] Limite de ${MAX_ATTEMPTS} tentatives atteinte. Arret automatique.`);
                console.error('[RECONNECT] Verifiez la connexion reseau et redemarrez le serveur manuellement.');
                return;
            }

            const delay = computeBackoffDelay(reconnectAttempt);
            reconnectAttempt++;
            console.log(`[RECONNECT] Tentative ${reconnectAttempt}/${MAX_ATTEMPTS} dans ${delay / 1000}s (backoff exponentiel)`);
            setTimeout(connectWhatsApp, delay);
        }

        if (connection === 'open') {
            isConnected = true;
            qrCodeData = null;
            reconnectAttempt = 0;  // Reset apres connexion reussie
            console.log('\n========================================');
            console.log('   WOURI CONNECTE A WHATSAPP!');
            console.log('   Systeme d\'onboarding actif');
            console.log('========================================\n');

            // Notifier les utilisateurs en attente (queue Phase 2)
            await notifyPendingUsers();
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
            let bambaraText = null;   // Transcription bambara brute (pour NLU preprocessing)

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
                        await sock.sendMessage(userNumber, { text: MSG.AUDIO_ERROR });
                        continue;
                    }

                    console.log(`[AUDIO] Telecharge: ${audioBuffer.length} bytes`);

                    // Choisir le moteur de transcription selon la langue de l'utilisateur
                    // - Si langue = dioula ou both -> utiliser ASR Bambara (MMS)
                    //   (les utilisateurs "both" parlent souvent en Dioula, Whisper hallucine sur du Dioula)
                    // - Si langue = french -> utiliser Whisper (francais)
                    let transcriptionResult;
                    const userLanguage = prefs.language || 'french';

                    if (userLanguage === 'dioula' || userLanguage === 'both') {
                        console.log(`[AUDIO] Utilisateur en mode ${userLanguage} -> ASR Bambara`);
                        transcriptionResult = await transcribeAudioBambara(audioBuffer, 'voice_message.ogg');
                    } else {
                        console.log(`[AUDIO] Utilisateur en mode ${userLanguage} -> Whisper francais`);
                        transcriptionResult = await transcribeAudio(audioBuffer, 'voice_message.ogg');
                    }

                    if (!transcriptionResult || !transcriptionResult.text || transcriptionResult.text.trim() === '') {
                        await sock.sendPresenceUpdate('paused', userNumber);
                        await sock.sendMessage(userNumber, { text: MSG.AUDIO_FAILED });
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
                    // Conserver le bambara brut pour le NLU preprocessing dans chat.py
                    if (transcriptionResult.bambara_text) {
                        bambaraText = transcriptionResult.bambara_text;
                    }

                } catch (audioError) {
                    console.error('[AUDIO] Erreur:', audioError.message);
                    await sock.sendPresenceUpdate('paused', userNumber);
                    await sock.sendMessage(userNumber, { text: MSG.AUDIO_ERROR });
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
                        await sock.sendMessage(userNumber, { text: MSG.CHANGE_CITY });
                        continue;
                    }
                    if (changeCommand === 'language') {
                        prefs.step = STEPS.WAITING_LANGUAGE;
                        saveUserPreferences();
                        await sock.sendPresenceUpdate('paused', userNumber);
                        await sock.sendMessage(userNumber, { text: MSG.CHANGE_LANGUAGE });
                        continue;
                    }
                    if (changeCommand === 'reset') {
                        prefs.step = STEPS.NEW;
                        prefs.city = null;
                        prefs.language = null;
                        prefs.pendingQuestion = null;
                        saveUserPreferences();
                        await sock.sendPresenceUpdate('paused', userNumber);
                        await sock.sendMessage(userNumber, { text: MSG.RESET });
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
                    await sock.sendMessage(userNumber, { text: MSG.WELCOME });
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
                    await sock.sendMessage(userNumber, { text: MSG.CITY_OK(cityName) });
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
                        await sock.sendMessage(userNumber, { text: MSG.LANGUAGE_UNKNOWN });
                        continue;
                    }

                    prefs.language = language;
                    prefs.step = STEPS.COMPLETE;

                    const langText = language === 'french' ? 'Faransi' :
                                    language === 'dioula' ? 'Dioula' : 'Faransi + Dioula';

                    await sock.sendPresenceUpdate('paused', userNumber);
                    await sock.sendMessage(userNumber, { text: MSG.PREFS_SAVED(prefs.city, langText) });

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
                // FEEDBACK 👍/👎 (C4)
                // ========================================
                if (prefs.step === STEPS.WAITING_FEEDBACK) {
                    const fb = prefs.pendingFeedback || {};
                    const msgLower = messageText.trim().toLowerCase();

                    // Si l'utilisateur envoie un nouveau vocal pendant le feedback
                    // → ignorer le feedback en cours, traiter directement la nouvelle question
                    if (isAudioMessage || isVoiceInput) {
                        console.log('[FEEDBACK] Nouveau vocal recu → feedback annulé, traitement direct');
                        prefs.step = STEPS.COMPLETE;
                        prefs.pendingFeedback = null;
                        saveUserPreferences();
                        // Ne pas return → le code STEPS.COMPLETE ci-dessous traite le message
                    } else {

                    // Detecter thumbsup / thumbsdown
                    const isThumbsUp   = ['👍','oui','yes','bien','ok','super','bon','ɲuman','numan'].some(k => msgLower.includes(k));
                    const isThumbsDown = ['👎','non','no','mauvais','mal','pas bon','te ɲuman'].some(k => msgLower.includes(k));

                    if (isThumbsUp || isThumbsDown) {
                        const endpoint = isThumbsUp ? 'positif' : 'negatif';
                        try {
                            await axios.post(`${WOURI_API_URL}/api/feedback/${endpoint}`, {
                                user_id: userNumber,
                                reponse_bambara: fb.reponse_bambara || '',
                                reponse_fr: fb.reponse_fr || '',
                                intent: fb.intent || '',
                                cultures: fb.cultures || [],
                                source: fb.source || 'unknown'
                            }, { timeout: 10000, headers: authHeaders() });
                            console.log(`[FEEDBACK] ${endpoint} enregistre pour intent=${fb.intent}`);
                        } catch (fbErr) {
                            console.log('[FEEDBACK] Erreur appel API:', fbErr.message);
                        }

                        // Confirmer et reprendre le mode normal
                        const confirm = isThumbsUp
                            ? 'Aw ni ce! 🙏 I ka ladili nɔgɔya n ma.'
                            : 'N bɛ a faamu. N bɛ jɛ ka ɲɛ. 🙏';
                        await sock.sendMessage(userNumber, { text: confirm });
                    } else {
                        // Message invalide → re-demander
                        await sock.sendMessage(userNumber, { text: 'I ka jaabi 👍 wala 👎 di.' });
                    }

                    // Reprendre le mode normal
                    prefs.step = STEPS.COMPLETE;
                    prefs.pendingFeedback = null;
                    saveUserPreferences();
                    continue; // [fix H] return sortait du handler entier — les msgs suivants du batch étaient perdus
                    } // fin else (feedback texte)
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

                    // Phase 2 — enregistrer le message dans la queue avant traitement
                    // Permet de garantir qu'aucun message n'est perdu silencieusement
                    const queueId = msg.key?.id || `wamsg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
                    try {
                        await messageQueue.add({
                            id: queueId,
                            userNumber,
                            payload: {
                                messageText,
                                bambaraText,
                                isVoiceInput,
                                city: prefs.city,
                                language: prefs.language,
                            },
                        });
                    } catch (qErr) {
                        console.error('[QUEUE] Erreur ajout queue :', qErr.message);
                    }

                    let data;
                    try {
                        // Wrap l'appel API dans le circuit breaker (Phase 2)
                        const response = await apiCircuitBreaker.execute(async () =>
                            axios.post(`${WOURI_API_URL}/api/chat/`, {
                                message: messageText,
                                city: prefs.city,
                                language: prefs.language,
                                include_audio: true,
                                user_id: userNumber,           // Pour l'historique de conversation
                                bambara_text: bambaraText      // Pour le NLU preprocessing (si message vocal bambara)
                            }, { timeout: 180000, headers: authHeaders() })
                        );
                        data = response.data;
                        // Succes : retirer de la queue
                        await messageQueue.markSuccess(queueId);
                    } catch (apiErr) {
                        // Echec : marquer dans la queue (reste en attente pour observabilité)
                        await messageQueue.markFailure(queueId, apiErr);

                        // Si circuit ouvert, message d'attente adapté au format du dernier message
                        if (apiErr instanceof CircuitOpenError) {
                            console.log(`[CIRCUIT] wouri-api en circuit OPEN — message d'attente envoyé (isVoice=${isVoiceInput}, lang=${prefs.language})`);
                            keepPresence = false;
                            clearInterval(presenceInterval);
                            await sock.sendPresenceUpdate('paused', userNumber);
                            await sendExcuseMessage(userNumber, {
                                isVoiceInput,
                                language: prefs.language,
                                kind: 'unavailable',
                            });
                            continue;  // Passer au message suivant du batch
                        }
                        throw apiErr;  // Re-throw : capturé par le try/catch global du handler
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

                    // DIOULA — Règle adaptative (issue #118) :
                    //   Vocal entrant  -> audio dioula
                    //   Texte entrant  -> texte FR (pas d'audio dioula généré pour rien)
                    else if (prefs.language === 'dioula') {
                        if (isVoiceInput && data.audio_url) {
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
                                console.log('[ENVOYE] Audio dioula (reponse a vocal)');
                            } catch (audioErr) {
                                console.log('[AUDIO DIOULA] Erreur, fallback texte FR:', audioErr.message);
                                if (data.response) {
                                    await sock.sendMessage(userNumber, { text: `🇫🇷 ${data.response}` });
                                }
                            }
                        } else {
                            // Entrée texte (ou audio_url manquant) -> texte FR
                            if (data.response) {
                                await sock.sendMessage(userNumber, { text: `🇫🇷 ${data.response}` });
                                console.log('[ENVOYE] Texte FR (mode dioula, entree texte ou audio indispo)');
                            }
                        }
                    }

                    // BOTH — Règle adaptative Hypothèse A (issue #118, validée Ruben) :
                    //   Vocal entrant  -> audio dioula seul (langue locale)
                    //   Texte entrant  -> texte FR seul
                    else if (prefs.language === 'both') {
                        if (isVoiceInput && data.audio_url) {
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
                                console.log('[ENVOYE] Audio dioula (mode both, reponse a vocal)');
                            } catch (audioErr) {
                                console.log('[AUDIO DIOULA] Erreur, fallback texte FR:', audioErr.message);
                                if (data.response) {
                                    await sock.sendMessage(userNumber, { text: `🇫🇷 ${data.response}` });
                                }
                            }
                        } else {
                            // Entrée texte (ou audio_url manquant) -> texte FR seul
                            if (data.response) {
                                await sock.sendMessage(userNumber, { text: `🇫🇷 ${data.response}` });
                                console.log('[ENVOYE] Texte FR (mode both, entree texte)');
                            }
                        }
                    }

                    // ========================================
                    // PROMPT FEEDBACK C4 (dioula/both uniquement)
                    // ========================================
                    if ((prefs.language === 'dioula' || prefs.language === 'both') && data.meta) {
                        await randomDelay(500, 1000);
                        await sock.sendMessage(userNumber, {
                            text: 'I ka jaabi ɲuman ye wa? 👍 / 👎'
                        });
                        prefs.pendingFeedback = {
                            reponse_bambara: data.response_dioula || data.response || '',
                            reponse_fr: '',
                            intent: data.meta.intent || '',
                            cultures: data.meta.cultures || [],
                            source: data.meta.source || 'unknown'
                        };
                        prefs.step = STEPS.WAITING_FEEDBACK;
                        saveUserPreferences();
                    }
                }

            } catch (error) {
                console.error('[ERREUR]', error.message);
                await sock.sendPresenceUpdate('paused', userNumber);
                await randomDelay(500, 1000);
                await sock.sendMessage(userNumber, {
                    text: "⚠️ Fɛɛrɛ dɔ kɛra. I ka a lasɔgɔ tugu.\n\n---\nProblème technique. Réessayez dans quelques instants."
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

// Phase 2 — Healthcheck étendu (statut WhatsApp + queue + circuit breaker)
app.get('/health', (req, res) => {
    res.json({
        whatsapp: {
            connected: isConnected,
            reconnectAttempt,
            maxAttempts: MAX_ATTEMPTS,
        },
        queue: messageQueue.stats,
        apiCircuit: apiCircuitBreaker.stats,
        users: Object.keys(userPreferences).length,
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
// GRACEFUL SHUTDOWN — sauvegarder prefs avant SIGTERM/SIGINT
// ========================================

async function gracefulShutdown(signal) {
    console.log(`\n[SHUTDOWN] Signal ${signal} recu — sauvegarde des préférences...`);
    try {
        // Ecriture synchrone bloquante au shutdown (pas de race condition possible ici)
        fs.writeFileSync(USER_PREFS_FILE, JSON.stringify(userPreferences, null, 2));
        console.log(`[SHUTDOWN] Préférences sauvegardées (${Object.keys(userPreferences).length} utilisateurs)`);
    } catch (err) {
        console.error('[SHUTDOWN] Erreur sauvegarde:', err.message);
    }
    try {
        if (sock) await sock.end();
    } catch (_) {}
    process.exit(0);
}

process.on('SIGINT',  () => gracefulShutdown('SIGINT'));
process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));

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
