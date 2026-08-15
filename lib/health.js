/**
 * Calcul du statut de santé du serveur Wourri WhatsApp (Phase 3 Observabilité).
 *
 * Extrait de app-baileys.js (modularisation) : `computeStatus` et `buildPayload`
 * étaient des fonctions quasi-pures noyées dans l'entrypoint. Isolées ici, elles
 * deviennent testables sans démarrer le serveur (matrice ok/degraded/unhealthy).
 *
 * L'état mutable du serveur (connexion, tentative de reconnexion) est passé via
 * des getters (`getIsConnected`, `getReconnectAttempt`) et non par valeur : sinon
 * le reporter servirait un état figé au moment de sa construction.
 */
"use strict";

class HealthReporter {
    /**
     * @param {object} options
     * @param {Function} options.getIsConnected - () => boolean (état live)
     * @param {Function} options.getReconnectAttempt - () => number (état live)
     * @param {object} options.apiCircuitBreaker - expose .state et .stats
     * @param {object} options.messageQueue - expose .stats {dead, pending}
     * @param {object} options.userPrefs - expose .data (map userNumber → prefs)
     * @param {string} options.appVersion - version applicative (package.json)
     * @param {number} options.processStartedAt - timestamp ms de démarrage process
     * @param {number} options.maxAttempts - plafond de tentatives de reconnexion
     * @param {Function} [options.now] - () => timestamp ms (injectable pour tests)
     */
    constructor(options = {}) {
        if (typeof options.getIsConnected !== "function") {
            throw new Error("HealthReporter: getIsConnected (function) requis");
        }
        if (typeof options.getReconnectAttempt !== "function") {
            throw new Error("HealthReporter: getReconnectAttempt (function) requis");
        }
        if (!options.apiCircuitBreaker) {
            throw new Error("HealthReporter: apiCircuitBreaker requis");
        }
        if (!options.messageQueue) {
            throw new Error("HealthReporter: messageQueue requis");
        }
        if (!options.userPrefs) {
            throw new Error("HealthReporter: userPrefs requis");
        }
        this.getIsConnected = options.getIsConnected;
        this.getReconnectAttempt = options.getReconnectAttempt;
        this.apiCircuitBreaker = options.apiCircuitBreaker;
        this.messageQueue = options.messageQueue;
        this.userPrefs = options.userPrefs;
        this.appVersion = options.appVersion || "unknown";
        this.processStartedAt = options.processStartedAt || 0;
        this.maxAttempts = options.maxAttempts;
        this.now = options.now || (() => Date.now());
    }

    /**
     * Calcule le statut global.
     *
     * - unhealthy : WhatsApp déconnecté OU circuit OPEN OU messages morts en queue
     * - degraded  : reconnexion en cours OU pile de messages en attente > 10 OU circuit HALF_OPEN
     * - ok        : sinon
     *
     * @returns {{status: 'ok'|'degraded'|'unhealthy', reasons: string[]}}
     */
    computeStatus() {
        const reasons = [];
        let unhealthy = false;
        let degraded = false;

        if (!this.getIsConnected()) {
            reasons.push("whatsapp_disconnected");
            unhealthy = true;
        }
        const circuitState = this.apiCircuitBreaker.state;
        if (circuitState === "OPEN") {
            reasons.push("api_circuit_open");
            unhealthy = true;
        }
        const qstats = this.messageQueue.stats;
        if (qstats.dead > 0) {
            reasons.push(`queue_dead_messages=${qstats.dead}`);
            unhealthy = true;
        }

        if (this.getReconnectAttempt() > 0) {
            reasons.push(`reconnect_in_progress=${this.getReconnectAttempt()}`);
            degraded = true;
        }
        if (qstats.pending > 10) {
            reasons.push(`queue_pending_high=${qstats.pending}`);
            degraded = true;
        }
        if (circuitState === "HALF_OPEN") {
            reasons.push("api_circuit_half_open");
            degraded = true;
        }

        let status = "ok";
        if (unhealthy) status = "unhealthy";
        else if (degraded) status = "degraded";

        return { status, reasons };
    }

    /**
     * Construit le payload complet de /health avec toutes les stats.
     */
    buildPayload() {
        const { status, reasons } = this.computeStatus();
        return {
            status,
            reasons,
            version: this.appVersion,
            uptime_seconds: Math.floor((this.now() - this.processStartedAt) / 1000),
            whatsapp: {
                connected: this.getIsConnected(),
                reconnectAttempt: this.getReconnectAttempt(),
                maxAttempts: this.maxAttempts,
            },
            queue: this.messageQueue.stats,
            apiCircuit: this.apiCircuitBreaker.stats,
            users: Object.keys(this.userPrefs.data).length,
        };
    }
}

module.exports = { HealthReporter };
