/**
 * Lecture des secrets — pattern Docker secrets `${NAME}_FILE` (issue #257).
 *
 * Miroir Node de `wouri-api/app/config.py::_read_file_secret` (issue #213,
 * PR #247) pour la cohérence end-to-end du pattern secrets en prod :
 *   1. si `${name}_FILE` est défini → lire le fichier, `.trim()` (newline
 *      finale des fichiers de secrets), et retourner son contenu s'il est
 *      non vide ;
 *   2. sinon → fallback sur la valeur d'env brute `${name}` (trimée), `''`
 *      si absente (mode dev, auth backend désactivée).
 *
 * Backward-compat : fichier introuvable, illisible ou VIDE → fallback env,
 * jamais de throw, avec un warning — une misconfiguration de secret en prod
 * doit se voir dans les logs. Divergences assumées avec l'impl Python :
 * Python est silencieux sur fichier inexistant, et CRASHE (PermissionError
 * non catchée) sur fichier existant mais illisible ; ici on warn + fallback
 * dans les 3 cas (le fail-fast prod d'app-baileys.js reste le filet final).
 *
 * Usage :
 *   const { readSecret } = require('./lib/secrets');
 *   const WOURI_API_KEY = readSecret('WOURI_API_KEY', { logger });
 */
"use strict";

const defaultFs = require("fs");

/**
 * Lit un secret selon la priorité fichier (`${name}_FILE`) puis env (`name`).
 *
 * @param {string} name - Nom de la variable (ex: "WOURI_API_KEY").
 * @param {object} [opts]
 * @param {object} [opts.env=process.env] - Environnement (injectable, tests).
 * @param {object} [opts.fs=require('fs')] - Module fs (injectable, tests).
 * @param {object} [opts.logger=null] - Logger pino-compatible ({warn}) ; null = silencieux.
 * @returns {string} La valeur du secret, '' si introuvable.
 */
function readSecret(name, { env = process.env, fs = defaultFs, logger = null } = {}) {
    const filePath = env[`${name}_FILE`];
    if (filePath) {
        try {
            // .trim() retire la newline finale ET un éventuel BOM UTF-8
            // (U+FEFF est un whitespace ES2015+) — un secret réécrit via un
            // éditeur Windows reste identique à la valeur envoyée.
            const value = fs.readFileSync(filePath, "utf-8").trim();
            if (value) {
                return value;
            }
            if (logger) {
                logger.warn(
                    { filePath },
                    `[SECRETS] ${name}_FILE pointe un fichier VIDE — fallback sur ${name}`,
                );
            }
        } catch (err) {
            if (logger) {
                logger.warn(
                    { err: err.message, filePath },
                    `[SECRETS] ${name}_FILE illisible — fallback sur ${name}`,
                );
            }
        }
    }
    return (env[name] || "").trim();
}

module.exports = { readSecret };
