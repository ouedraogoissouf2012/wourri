/**
 * Wouri WhatsApp — Profils de délais "simulation humaine".
 *
 * ## Problème résolu
 *
 * Les délais `randomDelay(min, max)` étaient hardcodés à 7 endroits
 * (message_handler, sock_helpers, response_sender, onboarding) avec des
 * valeurs historiques cumulant 1,8 à 3,8 s de latence artificielle par
 * réponse audio — en plus du temps réel de l'API.
 *
 * Ce module centralise ces valeurs en profils sélectionnables via env var,
 * sans toucher à la fonction `randomDelay` elle-même ni à son injection.
 *
 * ## Configuration via env var
 *
 *   HUMAN_DELAY_PROFILE : "fast" (défaut) | "natural" | "off"
 *
 *   - fast    : délais courts (~0,3-0,65 s cumulés) — réactivité prioritaire
 *   - natural : valeurs historiques anti-ban (~1,8-3,8 s cumulés) — rollback
 *               en 1 env var si suspicion de détection/ban Baileys
 *   - off     : aucun délai artificiel (comportement le plus "robotique")
 *
 * ## Usage
 *
 *   const { getDelays } = require("./human_delays");
 *   await randomDelay(...getDelays().beforeAudio);
 *
 * `getDelays()` relit l'env var à chaque appel : coût négligeable (lookup
 * d'objet) et surchargeable dans les tests sans re-require du module.
 *
 * Note : les indicateurs de présence (composing/recording) ne sont PAS
 * concernés — ils tournent pendant l'appel API et ne coûtent aucune latence.
 * C'est le signal "humain" gratuit qu'on conserve dans tous les profils.
 */
"use strict";

const DEFAULT_PROFILE = "fast";

// [min, max] en millisecondes pour chaque délai nommé.
// `textToAudio` et `feedback` restent plus hauts en "fast" : ce sont des
// délais UX (laisser le texte s'afficher avant l'audio), pas de la simulation.
const PROFILES = {
    // Valeurs historiques (avant 2026-07-21) — profil anti-ban conservateur.
    natural: {
        read: [500, 1000],
        beforeSend: [300, 800],
        beforeAudio: [1000, 2000],
        textToAudio: [500, 1000],
        feedback: [500, 1000],
        error: [500, 1000],
        onboarding: [1000, 2000],
    },
    fast: {
        read: [100, 200],
        beforeSend: [50, 150],
        beforeAudio: [150, 300],
        textToAudio: [300, 500],
        feedback: [300, 500],
        error: [100, 200],
        onboarding: [200, 400],
    },
    off: {
        read: [0, 0],
        beforeSend: [0, 0],
        beforeAudio: [0, 0],
        textToAudio: [0, 0],
        feedback: [0, 0],
        error: [0, 0],
        onboarding: [0, 0],
    },
};

// Warning "profil inconnu" émis une seule fois par valeur invalide
// (évite de spammer les logs à chaque message traité).
const _warnedProfiles = new Set();

/**
 * Retourne la table de délais du profil actif.
 *
 * @param {string} [profileName] - Surcharge optionnelle (tests) ; sinon
 *                                 lit HUMAN_DELAY_PROFILE (défaut: "fast")
 * @param {object} [logger] - Logger avec .warn (défaut: console)
 * @returns {{read: number[], beforeSend: number[], beforeAudio: number[],
 *            textToAudio: number[], feedback: number[], error: number[],
 *            onboarding: number[]}}
 */
function getDelays(profileName, logger) {
    const raw = profileName !== undefined
        ? profileName
        : (process.env.HUMAN_DELAY_PROFILE || DEFAULT_PROFILE);
    const name = String(raw).toLowerCase().trim();

    if (!PROFILES[name]) {
        if (!_warnedProfiles.has(name)) {
            _warnedProfiles.add(name);
            (logger || console).warn(
                `[DELAYS] Profil inconnu "${name}" — fallback "${DEFAULT_PROFILE}"`
            );
        }
        return PROFILES[DEFAULT_PROFILE];
    }
    return PROFILES[name];
}

module.exports = { getDelays, PROFILES, DEFAULT_PROFILE };
