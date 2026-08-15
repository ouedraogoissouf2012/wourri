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
    RECONNECT_MAX_DELAY,
} = require('./lib/reconnect');
const { createReconnectScheduler, cleanupSocket } = require('./lib/reconnect_scheduler');
const { MessageQueue } = require('./lib/message_queue');
const { CircuitBreaker, CircuitOpenError } = require('./lib/circuit_breaker');
const { createPendingReplayer } = require('./lib/pending_replay');
// Modularisation (2026-08) — sous-systèmes extraits de app-baileys.js (god file → lib/)
const { ExcuseAudio, EXCUSE_MSG } = require('./lib/excuse_audio');
const { HealthReporter } = require('./lib/health');
const { registerStatusRoutes } = require('./lib/status_routes');

// Sprint D.1 — extraction god file : modules locaux
const { extractCity, isValidCity } = require('./lib/city_resolver');
const { MSG, pickMsg, detectChangeCommand } = require('./lib/i18n');
const { AsrClient } = require('./lib/asr_client');

// Sprint D.2 — préférences utilisateurs encapsulées
const { UserPrefs, STEPS, DEFAULT_USER_LANGUAGE } = require('./lib/user_prefs');

// Phase 3 Observabilité — logger structuré pino JSON
const { logger } = require('./lib/logger');
// Issue #257 — pattern Docker secrets *_FILE (miroir de app/config.py côté API)
const { readSecret } = require('./lib/secrets');

// Configuration
const PORT = process.env.PORT || 3001;
const WOURI_API_URL = process.env.WOURI_API_URL || 'http://localhost:8000';
// Priorité WOURI_API_KEY_FILE (secret monté en fichier) puis WOURI_API_KEY (env)
const WOURI_API_KEY = readSecret('WOURI_API_KEY', { logger });
const AUTH_FOLDER = path.join(__dirname, 'auth_baileys');
const TEMP_AUDIO_FOLDER = path.join(__dirname, 'temp_audio');
const AUDIO_CACHE_FOLDER = path.join(__dirname, 'audio_cache');
// Sprint I.b : chemins surchargés via env vars en prod pour pointer vers /app/data
// (volume nommé persistant). Sans override → fallback __dirname comme avant
// (compat dev local + tests : aucun changement de comportement par défaut).
const USER_PREFS_FILE = process.env.USER_PREFS_FILE || path.join(__dirname, 'user_preferences.json');
const PENDING_MESSAGES_FILE = process.env.PENDING_MESSAGES_FILE || path.join(__dirname, 'pending_messages.json');

// [P0-02a] Helper : header X-API-Key pour appels backend Wourri
// Si WOURI_API_KEY vide, retourne objet vide (mode dev backend avec auth desactivee)
function authHeaders() {
    return WOURI_API_KEY ? { 'X-API-Key': WOURI_API_KEY } : {};
}

// Fail-fast : un bot de production sans cle ne peut appeler aucun endpoint
// backend protege. Le laisser demarrer donnerait un container "healthy" mais
// fonctionnellement inutilisable.
if (process.env.NODE_ENV === 'production' && !WOURI_API_KEY) {
    // #257 : nommer la vraie cause — si WOURI_API_KEY_FILE est defini, le
    // probleme est le FICHIER (vide/illisible/absent, cf. warn [SECRETS]
    // au-dessus), pas la variable d'env.
    logger.fatal(
        process.env.WOURI_API_KEY_FILE
            ? `[SECURITY] Cle vide : WOURI_API_KEY_FILE=${process.env.WOURI_API_KEY_FILE} illisible ou vide (voir warn [SECRETS]) — demarrage refuse`
            : '[SECURITY] WOURI_API_KEY non definie en production — demarrage refuse'
    );
    process.exit(1);
}

// Creer le dossier temporaire pour les audios
if (!fs.existsSync(TEMP_AUDIO_FOLDER)) {
    fs.mkdirSync(TEMP_AUDIO_FOLDER, { recursive: true });
}

// Express app pour API de status
const app = express();

// ===== CORS strict (ADR-0012 Sprint A) =====
// Allow-list configurable via env ALLOWED_ORIGINS="https://a.com,https://b.com".
// Si vide → refus de toute origine cross-domain (mode strict par défaut).
// Les routes /health, /qr, /qr-page, /status sont typiquement appelées
// same-origin (dashboard local) ou via curl/monitoring (pas de pre-flight CORS).
const allowedOrigins = (process.env.ALLOWED_ORIGINS || '')
    .split(',')
    .map(s => s.trim())
    .filter(Boolean);
app.use(cors({
    origin: allowedOrigins.length > 0 ? allowedOrigins : false,
    credentials: false,
}));
if (allowedOrigins.length === 0) {
    logger.info('[SECURITY] CORS strict : ALLOWED_ORIGINS non defini, refus de toute origine cross-domain');
} else {
    logger.info(`[SECURITY] CORS allow-list : ${allowedOrigins.join(', ')}`);
}

// ===== Rate limiting (ADR-0012 Sprint A) =====
// Protège les routes publiques contre les abus DoS. 60 req/min/IP est
// généreux pour du monitoring légitime (poll /health toutes les secondes
// = 60/min) tout en bloquant les scans abusifs.
const rateLimit = require('express-rate-limit');
const publicRateLimit = rateLimit({
    windowMs: 60 * 1000,
    max: 60,
    standardHeaders: true,
    legacyHeaders: false,
    message: { error: 'Trop de requêtes, réessayez plus tard' },
});
app.use(publicRateLimit);

app.use(express.json());

// Variables d'etat
let sock = null;
let qrCodeData = null;
let isConnected = false;

// Phase 2 Robustesse — planificateur de reconnexion idempotent (fix #308).
// Garantit UNE seule reconnexion en vol malgré les 'close' rapprochés de Baileys
// (anti fuite de sockets + anti hammering WhatsApp). État (attempt) exposé à /health.
const reconnectScheduler = createReconnectScheduler({
    connect: () => connectWhatsApp(),
    computeDelay: computeBackoffDelay,
    isReconnectable,
    maxAttempts: MAX_ATTEMPTS,
    maxDelay: RECONNECT_MAX_DELAY,
    logger,
});

// Queue persistante des messages reçus (anti-perte si API backend down)
const messageQueue = new MessageQueue({
    filePath: PENDING_MESSAGES_FILE,
    maxAttempts: 5,
    logger,  // Phase 3 : logger pino structuré
});

// Circuit breaker sur les appels à wouri-api
// Ouvre si > 50% d'erreurs sur les 10 derniers appels, ré-essaie après 30s
const apiCircuitBreaker = new CircuitBreaker({
    name: 'wouri-api',
    windowSize: 10,
    failureThreshold: 0.5,
    openDurationMs: 30000,
    halfOpenMaxCalls: 1,
    logger,  // Phase 3 : logger pino structuré
});

// Sprint D.1 — client ASR/STT (Whisper FR + MMS Bambara avec fallback)
const asrClient = new AsrClient({
    apiUrl: WOURI_API_URL,
    authHeaders,
    logger,
});

// Sprint D.2 — préférences utilisateurs (state + persistance débouncée)
const userPrefs = new UserPrefs({
    fs,
    filePath: USER_PREFS_FILE,
    logger,
});

// Sprint D.2 — instanciation responseSender plus bas (après EXCUSE_MSG + getExcuseAudio)
const { ResponseSender } = require('./lib/response_sender');
let responseSender = null;

// Sprint D.3 — state machine onboarding (NEW → WAITING_CITY → WAITING_LANGUAGE → COMPLETE → WAITING_FEEDBACK)
const { OnboardingMachine } = require('./lib/onboarding');
const onboardingMachine = new OnboardingMachine({
    userPrefs,
    axios,
    apiUrl: WOURI_API_URL,
    authHeaders,
    randomDelay: (min, max) => randomDelay(min, max),
    logger,
});

// Sprint 2026-05-28 — extraction du handler messages.upsert vers lib/message_handler.js
// (audit P2 #5 : 260 lignes inline + 5 niveaux d'imbrication factorisees).
// Le handler est cree DANS connectToWhatsApp() apres makeWASocket() pour
// capturer le sock courant (Pattern 11 projet : sock mutable post-init).
const { createMessageHandler } = require('./lib/message_handler');

// ========================================
// FONCTIONS UTILITAIRES
// ========================================

// Fonction pour simuler un delai humain
function randomDelay(min, max) {
    return new Promise(resolve => setTimeout(resolve, Math.floor(Math.random() * (max - min + 1)) + min));
}

// Modularisation — sous-système audio d'excuse (textes EXCUSE_MSG + génération
// TTS best-effort + cache disque). Extrait vers lib/excuse_audio.js.
const excuseAudio = new ExcuseAudio({
    apiUrl: WOURI_API_URL,
    authHeaders,
    cacheDir: AUDIO_CACHE_FOLDER,
    axios,
    logger,
});

// Sprint D.2 — instancier ResponseSender (EXCUSE_MSG + getExcuseAudio fournis par
// excuseAudio). `sock` reste null pour l'instant : il est assigné dans
// connectWhatsApp juste après `sock = makeWASocket(...)`.
responseSender = new ResponseSender({
    axios,
    apiUrl: WOURI_API_URL,
    randomDelay,
    getExcuseAudio: excuseAudio.getExcuseAudio,
    EXCUSE_MSG,
    logger,
});

// Charger les preferences au demarrage
userPrefs.load();

// Phase 2 — Charger la queue persistante au demarrage
messageQueue.load().then((n) => {
    if (n > 0) {
        logger.info(`[QUEUE] ${n} message(s) en attente charges depuis ${PENDING_MESSAGES_FILE}`);
        const dead = messageQueue.getDead();
        if (dead.length > 0) {
            logger.warn(`[QUEUE] ${dead.length} message(s) "morts" (>${messageQueue.maxAttempts} tentatives) - a inspecter manuellement`);
        }
    } else {
        logger.info('[QUEUE] Aucun message en attente');
    }
}).catch((err) => {
    logger.error(`[QUEUE] Erreur chargement initial : ${err.message}`);
});

/**
 * Vérifie si l'API backend wouri-api est joignable.
 *
 * Évite d'envoyer "Je suis de retour" alors que seule la connexion WhatsApp
 * a redémarré (l'API peut être encore down). Test rapide avec timeout court
 * pour ne pas bloquer la reprise de service.
 *
 * @returns {Promise<boolean>}
 */
async function isApiHealthy() {
    try {
        await axios.get(`${WOURI_API_URL}/health`, {
            timeout: 3000,
            headers: authHeaders(),
        });
        return true;
    } catch (err) {
        const code = err.code || err.response?.status || 'UNKNOWN';
        logger.info(`[HEALTHCHECK] wouri-api indisponible (${code})`);
        return false;
    }
}

// Phase 2 / fix #299 — Rejeu de la queue apres reconnexion WhatsApp.
//
// AVANT (bug #299) : on envoyait une excuse "Je suis de retour, repose ta
// question" puis on JETAIT tous les messages en attente (markSuccess) SANS
// jamais rejouer le payload contre /api/chat/. La promesse "aucun message
// perdu" etait donc factuellement fausse : l'utilisateur devait tout retaper.
//
// APRES : chaque message en attente est REJOUE contre le backend et la vraie
// reponse est envoyee a l'utilisateur. Le healthcheck API (ne pas rejouer si
// l'API est encore down) est conserve DANS le replayer. Voir lib/pending_replay.js
// pour les decisions (ordre chrono, feedback dernier message uniquement,
// markSuccess APRES envoi, anti-flood, isolation par utilisateur).
const replayPendingMessages = createPendingReplayer({
    messageQueue,
    userPrefs,
    responseSender,
    apiCircuitBreaker,
    axios,
    apiUrl: WOURI_API_URL,
    authHeaders,
    isApiHealthy,
    randomDelay,
    logger,
    DEFAULT_USER_LANGUAGE,
});

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
    logger.info(`[BAILEYS] Version WhatsApp Web: ${version.join('.')} (latest: ${isLatest})`);

    // fix #308 : détruire l'ancien socket AVANT d'en recréer un (retire les
    // listeners + ferme la WebSocket) pour ne pas accumuler sockets/listeners
    // zombies qui ré-émettraient 'close' → hammering WhatsApp.
    cleanupSocket(sock, logger);

    sock = makeWASocket({
        version,
        auth: state,
        logger: pino({ level: 'silent' }),
        browser: ['WOURI Assistant', 'Chrome', '120.0.0'],
        // Cf. lib/skip_old_messages.js : on ignore les messages recus pendant
        // le downtime serveur. Ces options Baileys reduisent drastiquement le
        // volume de messages anciens pousses par WhatsApp au reconnect
        // (sessions Signal desynchronisees -> erreurs libsignal MessageCounterError
        // / Bad MAC, voir issue #287 contexte ADR-0015 post-deploiement).
        syncFullHistory: false,
        shouldSyncHistoryMessage: () => false,
    });

    // Sprint D.2 — propager le sock au ResponseSender (sock est mutable post-reconnect)
    responseSender.sock = sock;
    // Sprint D.3 — propager le sock à OnboardingMachine (même pattern)
    onboardingMachine.sock = sock;

    // Gestion des evenements de connexion
    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            qrCodeData = qr;
            logger.info('\n========================================');
            logger.info('   SCANNEZ CE QR CODE AVEC WHATSAPP');
            logger.info('========================================\n');
            qrcode.generate(qr, { small: true });
        }

        if (connection === 'close') {
            isConnected = false;
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            const reasonName = describeDisconnectReason(statusCode);

            logger.info(`[RECONNECT] Connexion fermee : ${reasonName} (code=${statusCode})`);

            // fix #308 : le scheduler applique la garde anti-concurrence
            // (une seule reconnexion planifiée), le backoff et l'auto-recovery.
            const decision = reconnectScheduler.onClose(statusCode, reasonName);
            if (decision.action === 'abort') {
                logger.info('[RECONNECT]   - loggedOut/badSession : supprimez auth_baileys/ puis redemarrez');
                logger.info('[RECONNECT]   - forbidden : compte WhatsApp possiblement banni, contactez Meta');
            }
        }

        if (connection === 'open') {
            isConnected = true;
            qrCodeData = null;
            reconnectScheduler.onOpen();  // Reset compteur + annule un timer en attente (fix #308)
            logger.info('\n========================================');
            logger.info('   WOURI CONNECTE A WHATSAPP!');
            logger.info('   Systeme d\'onboarding actif');
            logger.info('========================================\n');

            // Pre-cache des audios d'excuse en arriere-plan (non-bloquant).
            // Gate sur isApiHealthy pour eviter 4x5s de timeouts si l'API est down :
            // dans ce cas on garde simplement le cache disque existant (s'il y en a un).
            isApiHealthy().then(async (apiUp) => {
                if (!apiUp) {
                    logger.info('[AUDIO-CACHE] API down — warmup ignore (cache disque utilise au besoin)');
                    return;
                }
                try {
                    const stats = await excuseAudio.warmup();
                    logger.info({ ...stats }, '[AUDIO-CACHE] Warmup termine');
                } catch (err) {
                    logger.warn({ err }, '[AUDIO-CACHE] Warmup erreur');
                }
            }).catch(() => {});

            // Rejouer les messages en attente (queue Phase 2, fix #299)
            await replayPendingMessages();
        }
    });

    sock.ev.on('creds.update', saveCreds);

    // ========================================
    // GESTION DES MESSAGES ENTRANTS
    // ========================================

    // Sprint 2026-05-28 — handler extrait dans lib/message_handler.js (audit P2 #5).
    // Le handler doit etre cree ici (et non au top) pour capturer le sock courant
    // (Pattern 11 : sock reassigne sur reconnexion via makeWASocket).
    const messageHandler = createMessageHandler({
        sock,
        logger,
        asrClient,
        responseSender,
        userPrefs,
        onboardingMachine,
        messageQueue,
        apiCircuitBreaker,
        apiUrl: WOURI_API_URL,
        MSG,
        STEPS,
        authHeaders,
        isApiHealthy,
        pickMsg,
        randomDelay,
        downloadMediaMessage,
        pino,
        axios,
        CircuitOpenError,
    });
    sock.ev.on('messages.upsert', messageHandler);
}

// ========================================
// ROUTES API EXPRESS (extraites → lib/status_routes.js)
// ========================================

// Timestamp démarrage process pour calculer l'uptime (consommé par /health)
const PROCESS_STARTED_AT = Date.now();

// Version applicative depuis package.json (single source of truth)
const APP_VERSION = (() => {
    try { return require('./package.json').version || 'unknown'; } catch (_) { return 'unknown'; }
})();

// Rapporteur de santé (Phase 3 Observabilité) — logique extraite → lib/health.js.
// L'état mutable (isConnected, attempt de reconnexion) est passé par getters afin
// de rester live : ces valeurs changent après la construction du reporter.
// Note (rebase 2026-08) : l'attempt vient désormais du reconnectScheduler (#308).
const healthReporter = new HealthReporter({
    getIsConnected: () => isConnected,
    getReconnectAttempt: () => reconnectScheduler.getState().attempt,
    apiCircuitBreaker,
    messageQueue,
    userPrefs,
    appVersion: APP_VERSION,
    processStartedAt: PROCESS_STARTED_AT,
    maxAttempts: MAX_ATTEMPTS,
});

// Enregistrement des routes /, /status, /health, /ready, /users, /qr, /qr-page,
// /logout. L'état mutable (isConnected, qrCodeData, sock — réassigné au
// reconnect) est passé par getters pour que les routes lisent l'état live.
registerStatusRoutes(app, {
    getIsConnected: () => isConnected,
    getQrCodeData: () => qrCodeData,
    getSock: () => sock,
    userPrefs,
    authFolder: AUTH_FOLDER,
    fs,
    QRCode,
    health: healthReporter,
});

// ========================================
// GRACEFUL SHUTDOWN — sauvegarder prefs avant SIGTERM/SIGINT
// ========================================

async function gracefulShutdown(signal) {
    logger.info(`\n[SHUTDOWN] Signal ${signal} recu — sauvegarde des préférences...`);
    try {
        // Ecriture synchrone bloquante au shutdown, atomique via tmp+rename
        // (encapsulee dans UserPrefs — meme garantie que save() async)
        userPrefs.saveSync();
        logger.info(`[SHUTDOWN] Préférences sauvegardées (${Object.keys(userPrefs.data).length} utilisateurs)`);
    } catch (err) {
        logger.error(`[SHUTDOWN] Erreur sauvegarde: ${err.message}`);
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
    logger.info('\n========================================');
    logger.info('   WOURI WhatsApp Server');
    logger.info('========================================');
    logger.info(`API: http://localhost:${PORT}`);
    logger.info(`WOURI API: ${WOURI_API_URL}`);
    logger.info(`Utilisateurs: ${Object.keys(userPrefs.data).length}`);
    logger.info('========================================\n');

    connectWhatsApp();

    // Log periodique des messages anciens ignores (downtime serveur).
    // Voir lib/skip_old_messages.js. Intervalle 5min pour eviter le spam.
    const { getIgnoredCount, resetCounter, BOOT_TS } = require('./lib/skip_old_messages');
    setInterval(() => {
        const n = getIgnoredCount();
        if (n > 0) {
            logger.info(
                { ignored: n, bootTimestamp: BOOT_TS },
                `[OLD_MSG] ${n} messages recus pendant downtime ignores`
            );
            resetCounter();
        }
    }, 5 * 60 * 1000);
});
