/**
 * Wouri WhatsApp — Filtre des messages reçus pendant le downtime serveur.
 *
 * ## Problème résolu
 *
 * Quand le bot redémarre, WhatsApp re-pousse les messages reçus pendant le
 * downtime. Ces messages :
 *   1. Sont chiffrés avec d'anciennes sessions Signal aux compteurs
 *      désynchronisés → libsignal logue `MessageCounterError` / `Bad MAC`
 *      (pollution stderr non-filtrable car bypasse le pino Baileys silencieux)
 *   2. Sont retraités par le bot comme s'ils venaient d'arriver, alors qu'ils
 *      sont obsolètes (l'utilisateur a peut-être renvoyé entre-temps)
 *
 * ## Solution
 *
 * Capture le timestamp de démarrage du serveur. Tout message Baileys dont
 * `messageTimestamp` est antérieur à `BOOT_TS - GRACE_SECONDS` est considéré
 * comme "ancien" et silencieusement ignoré dans `_shouldIgnore` du
 * `message_handler.js`.
 *
 * Combiné aux options Baileys `syncFullHistory: false` et
 * `shouldSyncHistoryMessage: () => false` (cf. `app-baileys.js`), cela élimine
 * le retraitement des messages downtime.
 *
 * ## Configuration via env vars
 *
 *   IGNORE_OLD_MESSAGES_ENABLED        : "true" (défaut) | "false"
 *   IGNORE_OLD_MESSAGES_GRACE_SECONDS  : "30" (défaut, en secondes)
 *
 * Une marge `GRACE_SECONDS` (défaut 30s) avant le boot évite d'ignorer un
 * message légitime arrivé juste avant le démarrage du handler.
 */
"use strict";

// Boot timestamp en secondes Unix, capturé une seule fois à l'import du module.
// Baileys donne `messageTimestamp` en secondes Unix (Long ou number) — on
// compare dans la même unité.
const BOOT_TS = Math.floor(Date.now() / 1000);

const ENABLED = (process.env.IGNORE_OLD_MESSAGES_ENABLED || "true").toLowerCase() !== "false";
const GRACE_SECONDS = Number(process.env.IGNORE_OLD_MESSAGES_GRACE_SECONDS || 30);

let ignoredCount = 0;

/**
 * Indique si un message Baileys est antérieur au démarrage du serveur
 * (à la marge GRACE_SECONDS près).
 *
 * Retourne false si :
 *   - Le filtre est désactivé via env var
 *   - Le message n'a pas de timestamp utilisable (graceful : on traite)
 *   - Le timestamp est >= BOOT_TS - GRACE_SECONDS (message frais)
 *
 * @param {Object} msg - Message Baileys (avec `messageTimestamp`)
 * @param {number} [graceSeconds] - Surcharge optionnelle de la marge (tests)
 * @returns {boolean}
 */
function isOldMessage(msg, graceSeconds) {
    if (!ENABLED) return false;
    if (!msg || msg.messageTimestamp === undefined || msg.messageTimestamp === null) {
        return false;
    }
    const ts = Number(msg.messageTimestamp);
    if (!Number.isFinite(ts) || ts <= 0) return false;
    const grace = graceSeconds !== undefined ? graceSeconds : GRACE_SECONDS;
    return ts < (BOOT_TS - grace);
}

/**
 * Incrémente le compteur de messages anciens ignorés (appelé par
 * `_shouldIgnore` quand `isOldMessage` retourne true).
 */
function noteIgnored() {
    ignoredCount++;
}

/**
 * Compteur cumulé depuis le dernier `resetCounter()`. Utilisé pour le log
 * périodique dans `app-baileys.js`.
 *
 * @returns {number}
 */
function getIgnoredCount() {
    return ignoredCount;
}

/**
 * Remet le compteur à 0 (après un log périodique, et utile pour les tests).
 */
function resetCounter() {
    ignoredCount = 0;
}

module.exports = {
    isOldMessage,
    noteIgnored,
    getIgnoredCount,
    resetCounter,
    BOOT_TS,
    GRACE_SECONDS,
    ENABLED,
};
