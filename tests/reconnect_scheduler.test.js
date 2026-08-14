/**
 * Tests unitaires pour lib/reconnect_scheduler.js (fix #308 + #310 item 5).
 * Exécution : node --test tests/reconnect_scheduler.test.js
 *
 * Le scheduler garantit qu'UNE SEULE reconnexion est planifiée à la fois, quel
 * que soit le nombre d'events 'close' rapprochés émis par Baileys pour un même
 * cycle. Sans ce garde : N timers → N makeWASocket → N sockets (fuite +
 * hammering WhatsApp → risque de ban).
 *
 * setTimeout/clearTimeout sont injectés (fakes) pour piloter le temps sans délai
 * réel et compter les planifications.
 */
"use strict";

const { test, describe } = require("node:test");
const assert = require("node:assert");
const { createReconnectScheduler, cleanupSocket } = require("../lib/reconnect_scheduler");

const silentLogger = { info() {}, warn() {}, error() {} };

// Fake timers : capture chaque setTimeout (callback + delay), pilotage manuel.
function makeFakeTimers() {
    const scheduled = [];
    let nextId = 1;
    return {
        scheduled,
        setTimeoutFn: (cb, delay) => {
            const id = nextId++;
            scheduled.push({ id, cb, delay, cleared: false });
            return id;
        },
        clearTimeoutFn: (id) => {
            const entry = scheduled.find((s) => s.id === id);
            if (entry) entry.cleared = true;
        },
        // Déclenche le dernier timer non-annulé encore en vol.
        fireLast() {
            const pending = scheduled.filter((s) => !s.cleared && !s.fired);
            const entry = pending[pending.length - 1];
            if (!entry) throw new Error("aucun timer en vol");
            entry.fired = true;
            entry.cb();
        },
        activeCount() {
            return scheduled.filter((s) => !s.cleared && !s.fired).length;
        },
    };
}

function makeScheduler(overrides = {}) {
    const timers = makeFakeTimers();
    let connectCalls = 0;
    const scheduler = createReconnectScheduler({
        connect: () => { connectCalls++; },
        computeDelay: (attempt) => 1000 * Math.pow(2, attempt),
        isReconnectable: (code) => code !== 401, // 401 = loggedOut (non-recuperable)
        maxAttempts: 3,
        maxDelay: 60000,
        logger: silentLogger,
        setTimeoutFn: timers.setTimeoutFn,
        clearTimeoutFn: timers.clearTimeoutFn,
        ...overrides,
    });
    return { scheduler, timers, getConnectCalls: () => connectCalls };
}

describe("createReconnectScheduler — garde anti-concurrence (#308 / #310 item5)", () => {
    test("[#310-5] rafale de 'close' rapprochés → UNE SEULE reconnexion planifiée, UN SEUL connect()", () => {
        const { scheduler, timers, getConnectCalls } = makeScheduler();

        // Baileys émet 5 close rapprochés pour un même cycle réseau.
        const results = [408, 408, 408, 428, 408].map((code) => scheduler.onClose(code));

        // Une seule planification ; les 4 suivantes sont ignorées (garde).
        assert.strictEqual(timers.activeCount(), 1, "un seul timer en vol");
        assert.strictEqual(results.filter((r) => r.action === "scheduled").length, 1);
        assert.strictEqual(results.filter((r) => r.action === "skipped").length, 4);
        assert.strictEqual(getConnectCalls(), 0, "connect pas encore appelé (timer pas déclenché)");

        // Le timer se déclenche → UN SEUL connect() (donc un seul makeWASocket).
        timers.fireLast();
        assert.strictEqual(getConnectCalls(), 1, "exactement un connect() → une seule socket");
    });

    test("après déclenchement, une nouvelle rafale planifie à nouveau (garde relâché)", () => {
        const { scheduler, timers, getConnectCalls } = makeScheduler();
        scheduler.onClose(408);
        timers.fireLast();
        assert.strictEqual(getConnectCalls(), 1);
        // Nouvelle instabilité après la tentative
        scheduler.onClose(408);
        scheduler.onClose(408);
        assert.strictEqual(timers.activeCount(), 1, "une seule nouvelle planification");
        timers.fireLast();
        assert.strictEqual(getConnectCalls(), 2);
    });

    test("code non-recuperable (401 loggedOut) → abort, aucune planification", () => {
        const { scheduler, timers, getConnectCalls } = makeScheduler();
        const res = scheduler.onClose(401);
        assert.strictEqual(res.action, "abort");
        assert.strictEqual(timers.activeCount(), 0);
        assert.strictEqual(getConnectCalls(), 0);
    });

    test("[#398] abort (401) purge un timer de reconnexion DÉJÀ armé", () => {
        const { scheduler, timers, getConnectCalls } = makeScheduler();
        // 408 (récupérable) arme un timer...
        scheduler.onClose(408);
        assert.strictEqual(scheduler.getState().scheduled, true);
        assert.strictEqual(timers.activeCount(), 1);
        // ...puis 401 (loggedOut) arrive AVANT son tir → doit purger le timer.
        const res = scheduler.onClose(401);
        assert.strictEqual(res.action, "abort");
        assert.strictEqual(scheduler.getState().scheduled, false, "garde relâché");
        assert.strictEqual(scheduler.getState().hasTimer, false, "timer purgé");
        assert.strictEqual(timers.scheduled[0].cleared, true, "clearTimeout appelé");
        assert.strictEqual(timers.activeCount(), 0, "plus aucun timer en vol");
        assert.strictEqual(getConnectCalls(), 0, "aucune reconnexion lancée");
    });

    test("backoff exponentiel : le délai suit computeDelay(attempt) et attempt s'incrémente", () => {
        const { scheduler, timers } = makeScheduler();
        scheduler.onClose(408);
        assert.strictEqual(timers.scheduled[0].delay, 1000); // attempt 0 → 1s
        timers.fireLast();
        scheduler.onClose(408);
        assert.strictEqual(timers.scheduled[1].delay, 2000); // attempt 1 → 2s
        timers.fireLast();
        scheduler.onClose(408);
        assert.strictEqual(timers.scheduled[2].delay, 4000); // attempt 2 → 4s
    });

    test("auto-recovery : au-delà de maxAttempts → reset compteur + pause maxDelay", () => {
        const { scheduler, timers } = makeScheduler();
        // 3 tentatives (attempt 0,1,2) → attempt devient 3 == maxAttempts
        for (let i = 0; i < 3; i++) { scheduler.onClose(408); timers.fireLast(); }
        assert.strictEqual(scheduler.getState().attempt, 3);
        // 4e close → auto-recovery
        const res = scheduler.onClose(408);
        assert.strictEqual(res.recovery, true);
        assert.strictEqual(res.delay, 60000, "pause de récupération = maxDelay");
        assert.strictEqual(scheduler.getState().attempt, 0, "compteur réinitialisé");
    });

    test("onOpen : reset attempt + annule un timer de reconnexion en attente", () => {
        const { scheduler, timers, getConnectCalls } = makeScheduler();
        scheduler.onClose(408);
        assert.strictEqual(scheduler.getState().scheduled, true);
        scheduler.onOpen();
        assert.strictEqual(scheduler.getState().attempt, 0);
        assert.strictEqual(scheduler.getState().scheduled, false);
        assert.strictEqual(timers.scheduled[0].cleared, true, "timer annulé");
        // Même si le timer annulé se déclenchait, il ne devrait pas rappeler connect
        // (mais on a clearTimeout, donc il ne se déclenche pas dans la vraie vie).
        assert.strictEqual(getConnectCalls(), 0);
    });

    test("getState expose attempt/scheduled pour /health", () => {
        const { scheduler } = makeScheduler();
        assert.deepStrictEqual(scheduler.getState(), { scheduled: false, attempt: 0, hasTimer: false });
        scheduler.onClose(408);
        const st = scheduler.getState();
        assert.strictEqual(st.scheduled, true);
        assert.strictEqual(st.attempt, 1);
        assert.strictEqual(st.hasTimer, true);
    });

    test("validation deps : connect/computeDelay/isReconnectable requis", () => {
        assert.throws(() => createReconnectScheduler({ computeDelay: () => 0, isReconnectable: () => true }), /connect/);
        assert.throws(() => createReconnectScheduler({ connect: () => {}, isReconnectable: () => true }), /computeDelay/);
        assert.throws(() => createReconnectScheduler({ connect: () => {}, computeDelay: () => 0 }), /isReconnectable/);
    });
});

describe("cleanupSocket — anti-fuite (#308)", () => {
    test("appelle removeAllListeners() + end() sur le socket", () => {
        const calls = [];
        const sock = {
            ev: { removeAllListeners: () => calls.push("removeAllListeners") },
            end: () => calls.push("end"),
        };
        cleanupSocket(sock, silentLogger);
        assert.deepStrictEqual(calls, ["removeAllListeners", "end"]);
    });

    test("sock null → no-op (pas d'exception)", () => {
        assert.doesNotThrow(() => cleanupSocket(null, silentLogger));
        assert.doesNotThrow(() => cleanupSocket(undefined, silentLogger));
    });

    test("défensif : removeAllListeners qui jette n'empêche pas end() ni ne propage", () => {
        const calls = [];
        const sock = {
            ev: { removeAllListeners: () => { throw new Error("boom"); } },
            end: () => calls.push("end"),
        };
        assert.doesNotThrow(() => cleanupSocket(sock, silentLogger));
        assert.deepStrictEqual(calls, ["end"], "end() est quand même appelé");
    });

    test("défensif : socket sans ev ni end → no-op silencieux", () => {
        assert.doesNotThrow(() => cleanupSocket({}, silentLogger));
    });
});
