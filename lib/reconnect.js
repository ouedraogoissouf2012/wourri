/**
 * Logique de reconnexion robuste pour Baileys WhatsApp.
 *
 * Backoff exponentiel : 1s → 2s → 4s → 8s → 16s → 32s → 60s (cap),
 * pour éviter de hammer WhatsApp et risquer un ban du compte business.
 *
 * Décision par code de déconnexion : certaines déconnexions sont "récupérables"
 * (réseau, restart), d'autres exigent une intervention humaine (loggedOut,
 * badSession). On distingue les deux.
 *
 * Référence Baileys DisconnectReason :
 * https://github.com/WhiskeySockets/Baileys/blob/master/src/Defaults/index.ts
 */
"use strict";

const RECONNECT_BASE_DELAY = 1000; // 1 seconde
const RECONNECT_MAX_DELAY = 60000; // 60 secondes (cap)
const MAX_ATTEMPTS = 10;

/**
 * Codes de déconnexion Baileys (HTTP-like).
 * Redéclarés ici pour ne pas dépendre de l'import baileys dans les tests.
 *
 * Les valeurs reflètent @whiskeysockets/baileys 6.7.x DisconnectReason.
 */
const DISCONNECT_REASONS = Object.freeze({
    badSession: 500,
    connectionClosed: 428,
    connectionLost: 408,
    connectionReplaced: 440,
    loggedOut: 401,
    multideviceMismatch: 411,
    restartRequired: 515,
    timedOut: 408, // alias historique de connectionLost dans certaines versions
    unavailableService: 503,
    forbidden: 403,
});

const RECONNECTABLE_CODES = Object.freeze(
    new Set([
        DISCONNECT_REASONS.connectionClosed,
        DISCONNECT_REASONS.connectionLost,
        DISCONNECT_REASONS.connectionReplaced,
        DISCONNECT_REASONS.timedOut,
        DISCONNECT_REASONS.restartRequired,
        DISCONNECT_REASONS.unavailableService,
    ])
);

const NON_RECONNECTABLE_CODES = Object.freeze(
    new Set([
        DISCONNECT_REASONS.loggedOut,
        DISCONNECT_REASONS.badSession,
        DISCONNECT_REASONS.multideviceMismatch,
        DISCONNECT_REASONS.forbidden,
    ])
);

/**
 * Calcule le délai de reconnexion en millisecondes pour la tentative N.
 *
 * Backoff exponentiel cappé à RECONNECT_MAX_DELAY :
 *   attempt 0 → 1000 ms (1s)
 *   attempt 1 → 2000 ms (2s)
 *   attempt 2 → 4000 ms (4s)
 *   attempt 3 → 8000 ms (8s)
 *   attempt 4 → 16000 ms (16s)
 *   attempt 5 → 32000 ms (32s)
 *   attempt 6+ → 60000 ms (cap)
 *
 * @param {number} attempt - Numéro de tentative (0-indexed)
 * @returns {number} délai en millisecondes
 */
function computeBackoffDelay(attempt) {
    if (typeof attempt !== "number" || attempt < 0) attempt = 0;
    const delay = RECONNECT_BASE_DELAY * Math.pow(2, attempt);
    return Math.min(delay, RECONNECT_MAX_DELAY);
}

/**
 * Indique si un code de déconnexion justifie une reconnexion automatique.
 *
 * - Codes connus reconnectables → true
 * - Codes connus non-reconnectables (loggedOut, badSession, etc.) → false
 * - undefined/null → true (cas inconnu, on tente prudemment)
 * - Code arbitraire inconnu → true (default permissif, mais loggé en amont)
 *
 * @param {number|undefined|null} statusCode
 * @returns {boolean}
 */
function isReconnectable(statusCode) {
    if (statusCode === undefined || statusCode === null) {
        return true;
    }
    if (NON_RECONNECTABLE_CODES.has(statusCode)) {
        return false;
    }
    if (RECONNECTABLE_CODES.has(statusCode)) {
        return true;
    }
    return true;
}

/**
 * Décrit un code de déconnexion en texte lisible (pour les logs).
 * @param {number|undefined|null} statusCode
 * @returns {string}
 */
function describeDisconnectReason(statusCode) {
    if (statusCode === undefined || statusCode === null) {
        return "unknown(undefined)";
    }
    const entry = Object.entries(DISCONNECT_REASONS).find(
        ([, code]) => code === statusCode
    );
    return entry ? entry[0] : `unknown(${statusCode})`;
}

module.exports = {
    computeBackoffDelay,
    isReconnectable,
    describeDisconnectReason,
    MAX_ATTEMPTS,
    RECONNECT_BASE_DELAY,
    RECONNECT_MAX_DELAY,
    DISCONNECT_REASONS,
    RECONNECTABLE_CODES,
    NON_RECONNECTABLE_CODES,
};
