/**
 * Circuit Breaker pour protéger les appels à un service externe (API backend).
 *
 * Pattern classique 3 états :
 *   CLOSED ──[X% erreurs]──> OPEN ──[durée]──> HALF_OPEN ──[succès]──> CLOSED
 *                                                          │
 *                                                          [échec]──> OPEN
 *
 * En CLOSED : appels passent normalement, erreurs comptées sur fenêtre glissante.
 * En OPEN : appels échouent immédiatement avec CircuitOpenError (sans appeler fn).
 * En HALF_OPEN : un seul appel sentinelle autorisé pour tester si le service revient.
 *
 * Référence : https://martinfowler.com/bliki/CircuitBreaker.html
 */
"use strict";

const STATE = Object.freeze({
    CLOSED: "CLOSED",
    OPEN: "OPEN",
    HALF_OPEN: "HALF_OPEN",
});

class CircuitOpenError extends Error {
    constructor(name) {
        super(`Circuit '${name}' est OPEN`);
        this.name = "CircuitOpenError";
        this.circuitName = name;
    }
}

class CircuitBreaker {
    /**
     * @param {object} options
     * @param {string} [options.name="circuit"] - Nom (pour les logs)
     * @param {number} [options.windowSize=10] - Taille de la fenêtre glissante
     * @param {number} [options.failureThreshold=0.5] - Ratio min pour ouvrir (0..1)
     * @param {number} [options.openDurationMs=30000] - Durée OPEN avant HALF_OPEN
     * @param {number} [options.halfOpenMaxCalls=1] - Appels simultanés en HALF_OPEN
     * @param {Function} [options.now] - Source de temps (injectable pour tests)
     * @param {object} [options.logger] - Logger avec méthode log()
     */
    constructor(options = {}) {
        this.name = options.name || "circuit";
        this.windowSize = options.windowSize || 10;
        this.failureThreshold = options.failureThreshold ?? 0.5;
        this.openDurationMs = options.openDurationMs || 30000;
        this.halfOpenMaxCalls = options.halfOpenMaxCalls || 1;
        this.now = options.now || (() => Date.now());
        this.logger = options.logger || console;

        this._state = STATE.CLOSED;
        this._results = []; // ring buffer : 'success' | 'failure'
        this._openedAt = null;
        this._halfOpenInFlight = 0;
    }

    get state() {
        return this._state;
    }

    /** Statistiques courantes (debug / observabilité) */
    get stats() {
        const failures = this._results.filter((r) => r === "failure").length;
        return {
            state: this._state,
            samples: this._results.length,
            failures,
            successes: this._results.length - failures,
            failureRatio: this._results.length === 0 ? 0 : failures / this._results.length,
            openedAt: this._openedAt,
        };
    }

    /**
     * Exécute fn sous protection du circuit breaker.
     * @param {Function} fn - Fonction async à exécuter
     * @returns {Promise<*>} résultat de fn
     * @throws {CircuitOpenError} si le circuit est OPEN ou si HALF_OPEN saturé
     */
    async execute(fn) {
        // Transition automatique OPEN → HALF_OPEN si la durée est écoulée
        if (this._state === STATE.OPEN) {
            const elapsed = this.now() - (this._openedAt ?? 0);
            if (elapsed >= this.openDurationMs) {
                this._transitionTo(STATE.HALF_OPEN);
            } else {
                throw new CircuitOpenError(this.name);
            }
        }

        // En HALF_OPEN, limiter le nombre de sentinelles simultanées
        if (this._state === STATE.HALF_OPEN) {
            if (this._halfOpenInFlight >= this.halfOpenMaxCalls) {
                throw new CircuitOpenError(this.name);
            }
            this._halfOpenInFlight++;
        }

        const wasHalfOpen = this._state === STATE.HALF_OPEN;
        try {
            const result = await fn();
            this._onSuccess(wasHalfOpen);
            return result;
        } catch (err) {
            this._onFailure(wasHalfOpen);
            throw err;
        } finally {
            if (wasHalfOpen) {
                this._halfOpenInFlight = Math.max(0, this._halfOpenInFlight - 1);
            }
        }
    }

    _onSuccess(wasHalfOpen) {
        if (wasHalfOpen) {
            this._transitionTo(STATE.CLOSED);
            return;
        }
        this._recordResult("success");
    }

    _onFailure(wasHalfOpen) {
        if (wasHalfOpen) {
            this._transitionTo(STATE.OPEN);
            return;
        }
        this._recordResult("failure");
        this._maybeOpen();
    }

    _recordResult(result) {
        this._results.push(result);
        if (this._results.length > this.windowSize) {
            this._results.shift();
        }
    }

    _maybeOpen() {
        if (this._results.length < this.windowSize) {
            return; // pas assez de données pour décider
        }
        const failures = this._results.filter((r) => r === "failure").length;
        const ratio = failures / this._results.length;
        if (ratio >= this.failureThreshold) {
            this._transitionTo(STATE.OPEN);
        }
    }

    _transitionTo(newState) {
        const oldState = this._state;
        if (oldState === newState) return;
        this._state = newState;
        if (newState === STATE.OPEN) {
            this._openedAt = this.now();
            this._halfOpenInFlight = 0;
        } else if (newState === STATE.CLOSED) {
            this._results = [];
            this._openedAt = null;
            this._halfOpenInFlight = 0;
        } else if (newState === STATE.HALF_OPEN) {
            this._halfOpenInFlight = 0;
        }
        // Compatibilité console (.log) ET pino (.info) — préfère .info si dispo
        const logFn = (this.logger && typeof this.logger.info === "function")
            ? this.logger.info.bind(this.logger)
            : (this.logger && typeof this.logger.log === "function"
                ? this.logger.log.bind(this.logger)
                : null);
        if (logFn) {
            logFn(`[CIRCUIT-${this.name}] ${oldState} → ${newState}`);
        }
    }

    /** Reset manuel (tests, ou intervention ops) */
    reset() {
        this._transitionTo(STATE.CLOSED);
    }
}

module.exports = { CircuitBreaker, CircuitOpenError, STATE };
