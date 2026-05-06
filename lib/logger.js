/**
 * Logger structuré pino pour Wourri WhatsApp Server.
 *
 * Format JSON ligne par ligne (parsable Loki/Datadog/Elastic/CloudWatch).
 * En dev, fallback automatique sur pino-pretty si installé pour lisibilité console.
 *
 * Variables d'environnement :
 *   - LOG_LEVEL : trace | debug | info | warn | error | fatal (default: info)
 *   - NODE_ENV  : 'production' force JSON pur même si pino-pretty est dispo
 *
 * Usage :
 *   const { logger } = require('./lib/logger');
 *   logger.info({ userNumber, queueId }, '[QUEUE] Message ajouté');
 *   logger.error({ err }, 'Erreur API backend');
 */
"use strict";

const pino = require("pino");

const VALID_LEVELS = new Set(["trace", "debug", "info", "warn", "error", "fatal", "silent"]);

/**
 * Construit l'instance pino. Exporté en factory pour faciliter les tests.
 *
 * @param {object} [opts]
 * @param {string} [opts.level] - Override de LOG_LEVEL (utile pour tests)
 * @param {boolean} [opts.forceJson] - Force le format JSON même hors prod
 * @param {object} [opts.destination] - Destination personnalisée (stream/sonic)
 * @returns {import('pino').Logger}
 */
function createLogger(opts = {}) {
    const envLevel = (process.env.LOG_LEVEL || "").toLowerCase();
    let level = opts.level || envLevel || "info";
    if (!VALID_LEVELS.has(level)) {
        level = "info";
    }

    const isProduction = process.env.NODE_ENV === "production";
    const wantPretty = !opts.forceJson && !isProduction;

    let transport;
    if (wantPretty) {
        try {
            require.resolve("pino-pretty");
            transport = {
                target: "pino-pretty",
                options: {
                    colorize: true,
                    translateTime: "HH:MM:ss.l",
                    ignore: "pid,hostname,service",
                    messageFormat: "{msg}",
                },
            };
        } catch (_) {
            // pino-pretty pas installé : fallback JSON même en dev
        }
    }

    const pinoOpts = {
        level,
        base: { service: "wouri-whatsapp" },
        timestamp: pino.stdTimeFunctions.isoTime,
    };
    if (transport) pinoOpts.transport = transport;

    return opts.destination ? pino(pinoOpts, opts.destination) : pino(pinoOpts);
}

// Instance singleton par défaut (utilisable directement)
const logger = createLogger();

module.exports = { logger, createLogger };
