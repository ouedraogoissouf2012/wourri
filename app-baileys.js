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
const { AudioCache } = require('./lib/audio_cache');

// Sprint D.1 — extraction god file : modules locaux
const { extractCity, isValidCity } = require('./lib/city_resolver');
const { MSG, pickMsg, detectChangeCommand } = require('./lib/i18n');
const { AsrClient } = require('./lib/asr_client');

// Sprint D.2 — préférences utilisateurs encapsulées
const { UserPrefs, STEPS, DEFAULT_USER_LANGUAGE } = require('./lib/user_prefs');

// Phase 3 Observabilité — logger structuré pino JSON
const { logger } = require('./lib/logger');

// Configuration
const PORT = process.env.PORT || 3001;
const WOURI_API_URL = process.env.WOURI_API_URL || 'http://localhost:8000';
const WOURI_API_KEY = process.env.WOURI_API_KEY || '';
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
    logger.fatal('[SECURITY] WOURI_API_KEY non definie en production — demarrage refuse');
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

// Phase 2 Robustesse
let reconnectAttempt = 0;  // Compteur de tentatives consécutives, reset à 0 après connexion réussie

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

/**
 * Génère un audio TTS à partir d'un texte fixe (best-effort).
 *
 * Utilisé pour les messages d'indisponibilité audio quand l'utilisateur
 * a envoyé un vocal. Si l'API TTS est down ou prend trop de temps,
 * retourne null et le caller doit fallback sur du texte.
 *
 * Endpoints utilisés (côté wouri-api) :
 *   - français : POST /api/tts/french?text=...
 *   - dioula   : POST /api/tts/bambara?text=...&is_french=false
 *
 * Note : on utilise /api/tts/french (et non /api/tts/) car ce dernier attend
 * un body JSON Pydantic TTSRequest, alors que /api/tts/french accepte le
 * texte en query param — cohérent avec /api/tts/bambara. Sans ça, l'appel
 * échoue en 422 (cas reproduit lors du warmup audio_cache).
 *
 * @param {string} text - Texte à synthétiser
 * @param {boolean} isFrench - true → Edge-TTS français, false → MMS dioula
 * @param {number} [timeoutMs=5000] - Timeout court pour ne pas bloquer
 * @returns {Promise<Buffer|null>} Buffer audio OGG/Opus, ou null si échec
 */
async function tryGenerateAudioFromText(text, isFrench, timeoutMs = 5000) {
    if (!text) return null;
    const endpoint = isFrench ? '/api/tts/french' : '/api/tts/bambara';
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
        logger.info(
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

// Cache disque des 4 audios d'excuse fixes (kind × langue).
// Permet d'envoyer un audio dioula même quand l'API TTS est down, en
// rejouant un fichier pré-généré quand l'API était UP.
const audioCache = new AudioCache({
    cacheDir: AUDIO_CACHE_FOLDER,
    generateAudio: tryGenerateAudioFromText,
    logger,
});

/** Liste des 4 entrées d'excuse à pré-générer au démarrage. */
function buildExcuseCacheEntries() {
    return [
        { key: 'unavailable_dioula', text: EXCUSE_MSG.UNAVAILABLE_DIOULA, isFrench: false },
        { key: 'unavailable_french', text: EXCUSE_MSG.UNAVAILABLE_FR, isFrench: true },
        { key: 'back_dioula', text: EXCUSE_MSG.BACK_DIOULA, isFrench: false },
        { key: 'back_french', text: EXCUSE_MSG.BACK_FR, isFrench: true },
    ];
}

/**
 * Récupère l'audio d'excuse pour {kind, isFrench}.
 *
 * Stratégie : cache disque d'abord (rapide, fonctionne même si API down).
 * Cache miss → tentative online via tryGenerateAudioFromText. En cas de
 * succès online, on remplit le cache pour la prochaine fois (best-effort,
 * non-bloquant).
 *
 * @returns {Promise<Buffer|null>} Buffer audio OGG/Opus, ou null si échec total
 */
async function getExcuseAudio({ kind, isFrench }) {
    const key = `${kind === 'back' ? 'back' : 'unavailable'}_${isFrench ? 'french' : 'dioula'}`;
    const cached = await audioCache.get(key);
    if (cached) {
        logger.info({ key, bytes: cached.length }, '[EXCUSE-AUDIO] Cache hit');
        return cached;
    }
    const text = isFrench
        ? (kind === 'back' ? EXCUSE_MSG.BACK_FR : EXCUSE_MSG.UNAVAILABLE_FR)
        : (kind === 'back' ? EXCUSE_MSG.BACK_DIOULA : EXCUSE_MSG.UNAVAILABLE_DIOULA);
    const fresh = await tryGenerateAudioFromText(text, isFrench);
    if (fresh) {
        audioCache.save(key, fresh).catch((err) =>
            logger.warn({ err, key }, '[EXCUSE-AUDIO] Save cache fail (non-bloquant)')
        );
        return fresh;
    }
    return null;
}

// Sprint D.2 — instancier ResponseSender maintenant que EXCUSE_MSG + getExcuseAudio
// sont définis. `sock` reste null pour l'instant : il est assigné dans connectWhatsApp
// juste après `sock = makeWASocket(...)`.
responseSender = new ResponseSender({
    axios,
    apiUrl: WOURI_API_URL,
    randomDelay,
    getExcuseAudio,
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

// Phase 2 — Notifier les utilisateurs ayant des messages en attente apres reconnexion WhatsApp
// Le format (audio/texte) s'adapte au format du DERNIER message reçu de chaque utilisateur.
//
// IMPORTANT (correction 2026-05-07) : on vérifie d'abord que l'API backend est UP.
// Sinon on envoie "Je suis de retour" alors que seul WhatsApp a reconnecté
// (l'API peut être encore down). Les messages restent en queue, on retentera à la
// prochaine reconnexion WhatsApp.
async function notifyPendingUsers() {
    const pending = messageQueue.getPending();
    if (pending.length === 0) return;

    // Healthcheck API : ne pas mentir à l'utilisateur sur le retour du service
    if (!(await isApiHealthy())) {
        logger.info(`[QUEUE] API encore indisponible, ${pending.length} message(s) restent en queue (pas de notification "back")`);
        return;
    }

    // Pour chaque utilisateur : retenir le DERNIER message reçu (pour adapter le format)
    const lastMessageByUser = new Map();
    for (const msg of pending) {
        if (!msg.userNumber) continue;
        const existing = lastMessageByUser.get(msg.userNumber);
        if (!existing || new Date(msg.createdAt) > new Date(existing.createdAt)) {
            lastMessageByUser.set(msg.userNumber, msg);
        }
    }

    logger.info(`[QUEUE] Notification de ${lastMessageByUser.size} utilisateur(s) ayant des messages en attente`);

    for (const [userNumber, lastMsg] of lastMessageByUser) {
        try {
            const isVoiceInput = lastMsg.payload?.isVoiceInput === true;
            // Langue ACTUELLE de l'utilisateur (peut avoir changé depuis l'ajout en queue).
            // Justification : le message "back" dit "Je suis de retour, pose-moi à nouveau
            // ta question". L'utilisateur va re-poser dans sa langue actuelle, donc on lui
            // répond dans sa langue actuelle (et non figée au moment de l'ajout en queue).
            //
            // Lecture directe de userPrefs.data[userNumber] au lieu de userPrefs.get(),
            // pour éviter le side effect de création d'entrée par défaut pour un
            // utilisateur disparu du fichier user_preferences.json.
            const language =
                userPrefs.data[userNumber]?.language
                || lastMsg.payload?.language
                || DEFAULT_USER_LANGUAGE;
            await responseSender.sendExcuse(userNumber, {
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
            logger.error(`[QUEUE] Erreur notification ${userNumber} : ${err.message}`);
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
    logger.info(`[BAILEYS] Version WhatsApp Web: ${version.join('.')} (latest: ${isLatest})`);

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
            const reconnectable = isReconnectable(statusCode);

            logger.info(`[RECONNECT] Connexion fermee : ${reasonName} (code=${statusCode})`);

            if (!reconnectable) {
                logger.info(`[RECONNECT] Raison non-recuperable (${reasonName}). Action manuelle requise :`);
                logger.info('[RECONNECT]   - loggedOut/badSession : supprimez auth_baileys/ puis redemarrez');
                logger.info('[RECONNECT]   - forbidden : compte WhatsApp possiblement banni, contactez Meta');
                return;
            }

            if (reconnectAttempt >= MAX_ATTEMPTS) {
                logger.error(`[RECONNECT] Limite de ${MAX_ATTEMPTS} tentatives atteinte. Arret automatique.`);
                logger.error('[RECONNECT] Verifiez la connexion reseau et redemarrez le serveur manuellement.');
                return;
            }

            const delay = computeBackoffDelay(reconnectAttempt);
            reconnectAttempt++;
            logger.info(`[RECONNECT] Tentative ${reconnectAttempt}/${MAX_ATTEMPTS} dans ${delay / 1000}s (backoff exponentiel)`);
            setTimeout(connectWhatsApp, delay);
        }

        if (connection === 'open') {
            isConnected = true;
            qrCodeData = null;
            reconnectAttempt = 0;  // Reset apres connexion reussie
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
                    const stats = await audioCache.warmup(buildExcuseCacheEntries());
                    logger.info({ ...stats }, '[AUDIO-CACHE] Warmup termine');
                } catch (err) {
                    logger.warn({ err }, '[AUDIO-CACHE] Warmup erreur');
                }
            }).catch(() => {});

            // Notifier les utilisateurs en attente (queue Phase 2)
            await notifyPendingUsers();
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
// ROUTES API EXPRESS
// ========================================

app.get('/', (req, res) => {
    res.json({
        status: 'running',
        name: 'WOURI WhatsApp Server',
        connected: isConnected,
        users: Object.keys(userPrefs.data).length
    });
});

app.get('/status', (req, res) => {
    res.json({
        connected: isConnected,
        qrCode: qrCodeData,
        users: Object.keys(userPrefs.data).length
    });
});

// ========================================
// HEALTHCHECK & READINESS (Phase 3 Observabilité)
// ========================================

// Timestamp démarrage process pour calculer l'uptime
const PROCESS_STARTED_AT = Date.now();

// Charge la version applicative depuis package.json (single source of truth)
const APP_VERSION = (() => {
    try { return require('./package.json').version || 'unknown'; } catch (_) { return 'unknown'; }
})();

/**
 * Calcule le statut global du serveur Wourri WhatsApp.
 *
 * - unhealthy : WhatsApp déconnecté OU circuit OPEN OU messages morts dans la queue
 * - degraded  : reconnexion en cours OU pile de messages en attente > 10
 * - ok        : tout va bien
 *
 * @returns {{status: 'ok'|'degraded'|'unhealthy', reasons: string[]}}
 */
function computeHealthStatus() {
    const reasons = [];
    let unhealthy = false;
    let degraded = false;

    if (!isConnected) {
        reasons.push('whatsapp_disconnected');
        unhealthy = true;
    }
    const circuitState = apiCircuitBreaker.state;
    if (circuitState === 'OPEN') {
        reasons.push('api_circuit_open');
        unhealthy = true;
    }
    const qstats = messageQueue.stats;
    if (qstats.dead > 0) {
        reasons.push(`queue_dead_messages=${qstats.dead}`);
        unhealthy = true;
    }

    if (reconnectAttempt > 0) {
        reasons.push(`reconnect_in_progress=${reconnectAttempt}`);
        degraded = true;
    }
    if (qstats.pending > 10) {
        reasons.push(`queue_pending_high=${qstats.pending}`);
        degraded = true;
    }
    if (circuitState === 'HALF_OPEN') {
        reasons.push('api_circuit_half_open');
        degraded = true;
    }

    let status = 'ok';
    if (unhealthy) status = 'unhealthy';
    else if (degraded) status = 'degraded';

    return { status, reasons };
}

/**
 * Construit le payload complet de /health avec toutes les stats.
 */
function buildHealthPayload() {
    const { status, reasons } = computeHealthStatus();
    return {
        status,
        reasons,
        version: APP_VERSION,
        uptime_seconds: Math.floor((Date.now() - PROCESS_STARTED_AT) / 1000),
        whatsapp: {
            connected: isConnected,
            reconnectAttempt,
            maxAttempts: MAX_ATTEMPTS,
        },
        queue: messageQueue.stats,
        apiCircuit: apiCircuitBreaker.stats,
        users: Object.keys(userPrefs.data).length,
    };
}

// /health : healthcheck riche, toujours 200 (le statut est dans le body)
app.get('/health', (req, res) => {
    res.json(buildHealthPayload());
});

// /ready : Kubernetes readiness probe — 200 si prêt, 503 sinon
app.get('/ready', (req, res) => {
    const payload = buildHealthPayload();
    const ready = payload.status === 'ok';
    res.status(ready ? 200 : 503).json({
        status: payload.status,
        ready,
        reasons: payload.reasons,
    });
});

app.get('/users', (req, res) => {
    // Retourne les preferences de tous les utilisateurs (sans numero complet pour confidentialite)
    const users = Object.entries(userPrefs.data).map(([number, prefs]) => ({
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
