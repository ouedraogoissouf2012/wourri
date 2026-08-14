/**
 * Planificateur de reconnexion idempotent + nettoyage de socket (fix #308).
 *
 * ## Problème corrigé
 *
 * `connectWhatsApp` (app-baileys.js) planifiait un `setTimeout(connectWhatsApp)`
 * à CHAQUE event `connection.update` avec `connection==='close'`, sans aucune
 * garde. En instabilité réseau, Baileys émet plusieurs `close` rapprochés pour
 * un même cycle (`connectionClosed` → `connectionLost` → `timedOut`). Chaque
 * close planifiait donc un timer → N `makeWASocket` → N sockets WebSocket +
 * N jeux de listeners. La globale `sock` ne pointait que sur le dernier ; les
 * précédents fuyaient (mémoire + FD) et pouvaient ré-émettre `close` → cascade
 * multiplicative = HAMMERING WhatsApp (risque de ban documenté dans CLAUDE.md).
 *
 * ## Solution
 *
 * - `createReconnectScheduler` : garde d'idempotence (`scheduled`) → une SEULE
 *   reconnexion planifiée à la fois, quel que soit le nombre de `close`. Garde
 *   un handle du timer pour pouvoir l'annuler (`onOpen`).
 * - `cleanupSocket` : `removeAllListeners()` + `end()` de l'ancien socket avant
 *   d'en recréer un (appelé au début de `connectWhatsApp`) → pas de fuite de
 *   listeners ni de sockets zombies qui ré-émettent `close`.
 */
"use strict";

/**
 * Nettoie proprement un socket Baileys avant recréation (fix #308).
 * Défensif : tolère un sock null/partiel et ne propage jamais d'exception —
 * on est dans un chemin de reprise, il ne doit jamais casser la reconnexion.
 *
 * @param {object|null} sock - Socket Baileys (ou null au premier démarrage)
 * @param {object} [logger]
 */
function cleanupSocket(sock, logger = console) {
    if (!sock) return;
    // 1) Retirer TOUS les listeners : évite la fuite et surtout les
    //    ré-émissions 'close' d'un socket zombie qui relanceraient un cycle.
    try {
        if (sock.ev && typeof sock.ev.removeAllListeners === "function") {
            sock.ev.removeAllListeners();
        }
    } catch (err) {
        (logger.warn || logger.info || (() => {})).call(
            logger, `[RECONNECT] removeAllListeners a échoué (ignoré): ${err.message}`
        );
    }
    // 2) Fermer la connexion WebSocket sous-jacente.
    try {
        if (typeof sock.end === "function") {
            sock.end(undefined);
        }
    } catch (err) {
        (logger.warn || logger.info || (() => {})).call(
            logger, `[RECONNECT] sock.end a échoué (ignoré): ${err.message}`
        );
    }
}

/**
 * Crée un planificateur de reconnexion idempotent (fix #308).
 *
 * @param {object} deps
 * @param {Function} deps.connect          () => void — (re)lance connectWhatsApp
 * @param {Function} deps.computeDelay     (attempt:number) => ms (backoff)
 * @param {Function} deps.isReconnectable  (statusCode) => boolean
 * @param {number}   deps.maxAttempts      seuil d'auto-recovery
 * @param {number}   deps.maxDelay         pause d'auto-recovery (ms)
 * @param {object}   [deps.logger]
 * @param {Function} [deps.setTimeoutFn]   injectable (tests)
 * @param {Function} [deps.clearTimeoutFn] injectable (tests)
 * @returns {{ onClose: Function, onOpen: Function, getState: Function }}
 */
function createReconnectScheduler({
    connect,
    computeDelay,
    isReconnectable,
    maxAttempts,
    maxDelay,
    logger = console,
    setTimeoutFn = setTimeout,
    clearTimeoutFn = clearTimeout,
}) {
    if (typeof connect !== "function") {
        throw new Error("createReconnectScheduler: connect (function) requis");
    }
    if (typeof computeDelay !== "function") {
        throw new Error("createReconnectScheduler: computeDelay (function) requis");
    }
    if (typeof isReconnectable !== "function") {
        throw new Error("createReconnectScheduler: isReconnectable (function) requis");
    }

    // État partagé par tous les listeners connection.update (garde global).
    let scheduled = false; // une reconnexion est déjà planifiée
    let timer = null; // handle du setTimeout en attente
    let attempt = 0; // tentatives consécutives (reset après 'open')

    /**
     * À appeler sur chaque event `connection === 'close'`.
     * @param {number|undefined|null} statusCode
     * @param {string} [reasonName] - libellé lisible (log uniquement)
     * @returns {{action:'abort'|'skipped'|'scheduled', delay?:number, recovery?:boolean, attempt?:number}}
     */
    function onClose(statusCode, reasonName = "") {
        if (!isReconnectable(statusCode)) {
            logger.info(
                `[RECONNECT] Raison non-recuperable (${reasonName || statusCode}) — pas de reconnexion auto.`
            );
            return { action: "abort" };
        }

        // GARDE anti-concurrence (#308) : une seule reconnexion planifiée à la
        // fois. Les 'close' supplémentaires d'un même cycle sont ignorés.
        if (scheduled) {
            logger.info(
                `[RECONNECT] Reconnexion déjà planifiée — 'close' (${reasonName || statusCode}) ignoré (garde #308)`
            );
            return { action: "skipped" };
        }

        let delay;
        let recovery = false;
        if (attempt >= maxAttempts) {
            // Auto-recovery : reset compteur + longue pause, puis nouveau cycle.
            // (au lieu d'abandonner définitivement jusqu'à un restart manuel).
            recovery = true;
            attempt = 0;
            delay = maxDelay;
            logger.warn(
                `[RECONNECT] Limite de ${maxAttempts} tentatives atteinte. `
                + `Pause de recuperation ${maxDelay / 1000}s puis nouveau cycle...`
            );
        } else {
            delay = computeDelay(attempt);
            attempt++;
            logger.info(
                `[RECONNECT] Tentative ${attempt}/${maxAttempts} dans ${delay / 1000}s (backoff exponentiel)`
            );
        }

        scheduled = true;
        timer = setTimeoutFn(() => {
            // Relâcher le garde AVANT de relancer : un 'close' pendant la
            // nouvelle tentative pourra planifier à nouveau.
            scheduled = false;
            timer = null;
            connect();
        }, delay);

        return { action: "scheduled", delay, recovery, attempt };
    }

    /**
     * À appeler sur `connection === 'open'` : reset du compteur + annulation
     * d'un éventuel timer de reconnexion encore en attente.
     */
    function onOpen() {
        attempt = 0;
        if (timer) {
            clearTimeoutFn(timer);
            timer = null;
        }
        scheduled = false;
    }

    /** État courant (pour /health et introspection). */
    function getState() {
        return { scheduled, attempt, hasTimer: timer !== null };
    }

    return { onClose, onOpen, getState };
}

module.exports = { createReconnectScheduler, cleanupSocket };
