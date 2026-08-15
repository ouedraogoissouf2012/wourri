/**
 * Authentification entrante du serveur WhatsApp (L1, issue #408).
 *
 * Le serveur Express n'exposait ses routes (`/logout`, `/qr`, `/users`, ...) que
 * derriere CORS + rate limiting : tout conteneur du reseau Docker pouvait
 * atteindre `/logout` et detruire la session Baileys (re-scan QR manuel).
 *
 * Ce module fournit, en EXTENSION (aucune modification du flux Baileys) :
 *   - `createAdminAuthMiddleware` : middleware Express exigeant le header
 *     `X-WA-Admin-Key`, avec comparaison a TEMPS CONSTANT (un `===` fuiterait
 *     la longueur du prefixe). Les chemins publics (`/health`, `/ready`) sont
 *     laisses ouverts pour les healthchecks Docker.
 *   - `adminKeyStartupError` : garde-fou fail-closed calque sur celui de
 *     `WOURI_API_KEY` (app-baileys.js) — en production sans cle, le serveur
 *     doit refuser de demarrer.
 *
 * Fail-closed : si `adminKey` est vide, TOUTES les routes protegees renvoient
 * 401 (on ne laisse jamais passer par defaut).
 */
"use strict";

const crypto = require("node:crypto");

/**
 * Comparaison a temps constant de deux chaines. Retourne false si l'une est
 * absente ou si les longueurs different (timingSafeEqual exige des buffers de
 * meme taille — le test de longueur est volontairement non constant, il ne
 * fuit rien de plus que la longueur, deja observable).
 */
function timingSafeEqualStr(a, b) {
    const bufA = Buffer.from(typeof a === "string" ? a : "", "utf8");
    const bufB = Buffer.from(typeof b === "string" ? b : "", "utf8");
    if (bufA.length !== bufB.length) return false;
    return crypto.timingSafeEqual(bufA, bufB);
}

/**
 * Cree le middleware d'authentification admin.
 * @param {object} opts
 * @param {string} opts.adminKey - cle attendue (vide => tout refuse sauf publics)
 * @param {Set<string>|string[]} opts.publicPaths - chemins laisses publics
 * @param {object} [opts.logger] - logger pino-like (.warn)
 * @returns {(req, res, next) => void}
 */
function createAdminAuthMiddleware({ adminKey, publicPaths, logger } = {}) {
    const publics = publicPaths instanceof Set
        ? publicPaths
        : new Set(publicPaths || []);
    const log = logger || { warn() {} };

    return function adminAuth(req, res, next) {
        if (publics.has(req.path)) return next();

        const provided = req.get("X-WA-Admin-Key");
        if (!adminKey || !timingSafeEqualStr(provided, adminKey)) {
            log.warn({ path: req.path, ip: req.ip }, "[AUTH] refus");
            return res.status(401).json({ error: "unauthorized" });
        }
        return next();
    };
}

/**
 * Garde-fou de demarrage (fail-closed) : en production, une cle admin absente
 * doit empecher le demarrage. Retourne le message fatal a logger, ou null si
 * le demarrage est autorise. Calque sur le garde-fou WOURI_API_KEY (#257 :
 * nommer WA_ADMIN_KEY_FILE si c'est le fichier secret qui est vide/illisible).
 * @param {object} opts
 * @param {string} opts.adminKey
 * @param {string} opts.nodeEnv
 * @param {string} [opts.keyFile] - valeur de WA_ADMIN_KEY_FILE si definie
 * @returns {string|null}
 */
function adminKeyStartupError({ adminKey, nodeEnv, keyFile } = {}) {
    if (nodeEnv === "production" && !adminKey) {
        return keyFile
            ? `[SECURITY] Cle vide : WA_ADMIN_KEY_FILE=${keyFile} illisible ou vide — demarrage refuse`
            : "[SECURITY] WA_ADMIN_KEY non definie en production — demarrage refuse";
    }
    return null;
}

module.exports = {
    createAdminAuthMiddleware,
    adminKeyStartupError,
    timingSafeEqualStr,
};
