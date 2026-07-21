/**
 * Helpers de bas niveau pour les interactions répétées avec le socket Baileys.
 *
 * Factorise deux patterns dupliqués 11 fois entre `lib/onboarding.js` et
 * `lib/response_sender.js` (cf. issue #170 — review DRY/SOLID Sprint D.3) :
 *
 *   - `sendTextWithPause` : présence "paused" → sendMessage texte
 *   - `sendAudioBuffer`   : présence "recording" → délai humain → "paused" → sendMessage audio
 *
 * Module pure functions sans état (pattern cohérent avec `reconnect.js` et
 * `city_resolver.js`). Le `sock` et le `randomDelay` sont passés en paramètres,
 * il n'y a rien à mémoriser entre deux appels.
 *
 * Note : les blocs `try { sock.sendPresenceUpdate("recording") } catch (_) {}`
 * de `sendExcuse` (lib/response_sender.js) ne sont PAS extraits ici car ils
 * encapsulent les presence updates dans des try/catch silencieux séparés —
 * sémantique défensive différente, à préserver tel quel.
 */
"use strict";

const { getDelays } = require("./human_delays");

const AUDIO_MIMETYPE = "audio/ogg; codecs=opus";

/**
 * Envoie un message texte précédé d'une présence "paused".
 *
 * @param {object} sock - Socket Baileys
 * @param {string} userNumber - Destinataire WhatsApp
 * @param {string} text - Texte du message
 * @returns {Promise<void>}
 */
async function sendTextWithPause(sock, userNumber, text) {
    await sock.sendPresenceUpdate("paused", userNumber);
    await sock.sendMessage(userNumber, { text });
}

/**
 * Envoie une note vocale (audio, ptt=true) encapsulée dans la séquence
 * "recording → délai humain → paused → envoi".
 *
 * Le caller est responsable d'avoir téléchargé l'audio (axios.get) en amont.
 *
 * @param {object} sock - Socket Baileys
 * @param {string} userNumber - Destinataire WhatsApp
 * @param {Buffer} audioBuffer - Buffer audio déjà téléchargé
 * @param {object} options
 * @param {Function} options.randomDelay - async (min, max) => Promise<void>
 * @returns {Promise<void>}
 */
async function sendAudioBuffer(sock, userNumber, audioBuffer, { randomDelay }) {
    await sock.sendPresenceUpdate("recording", userNumber);
    await randomDelay(...getDelays().beforeAudio);
    await sock.sendPresenceUpdate("paused", userNumber);
    await sock.sendMessage(userNumber, {
        audio: audioBuffer,
        mimetype: AUDIO_MIMETYPE,
        ptt: true,
    });
}

module.exports = { sendTextWithPause, sendAudioBuffer, AUDIO_MIMETYPE };
