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
 * Backward-compat : fichier introuvable/illisible → fallback env, jamais de
 * throw. Divergence assumée avec l'impl Python (silencieuse) : un warning est
 * loggé quand `${name}_FILE` est défini mais illisible — une misconfiguration
 * de secret en prod doit se voir dans les logs.
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
            const value = fs.readFileSync(filePath, "utf-8").trim();
            if (value) {
                return value;
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
