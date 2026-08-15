/**
 * Tests de caractérisation pour HealthReporter.
 *
 * Capturent la logique de statut (ok/degraded/unhealthy) et le payload /health
 * tels qu'ils existaient inline dans app-baileys.js avant l'extraction.
 *
 * Exécution : node --test tests/health.test.js
 */
"use strict";

const { test, describe } = require("node:test");
const assert = require("node:assert");
const { HealthReporter } = require("../lib/health");

// Fabrique un reporter avec des dépendances contrôlables par test.
function makeReporter(overrides = {}) {
    const state = {
        connected: true,
        reconnectAttempt: 0,
        circuitState: "CLOSED",
        circuitStats: { state: "CLOSED", failures: 0 },
        queueStats: { dead: 0, pending: 0 },
        users: { u1: {}, u2: {} },
        ...overrides,
    };
    return new HealthReporter({
        getIsConnected: () => state.connected,
        getReconnectAttempt: () => state.reconnectAttempt,
        apiCircuitBreaker: { get state() { return state.circuitState; }, get stats() { return state.circuitStats; } },
        messageQueue: { get stats() { return state.queueStats; } },
        userPrefs: { data: state.users },
        appVersion: "9.9.9",
        processStartedAt: 1000,
        maxAttempts: 10,
        now: () => 6000, // uptime = (6000-1000)/1000 = 5s
    });
}

describe("HealthReporter — construction", () => {
    test("throw si getIsConnected manquant", () => {
        assert.throws(() => new HealthReporter({}), /getIsConnected/);
    });
    test("throw si apiCircuitBreaker manquant", () => {
        assert.throws(() => new HealthReporter({
            getIsConnected: () => true, getReconnectAttempt: () => 0,
        }), /apiCircuitBreaker/);
    });
});

describe("HealthReporter — computeStatus", () => {
    test("tout OK → status ok, aucune raison", () => {
        assert.deepStrictEqual(makeReporter().computeStatus(), { status: "ok", reasons: [] });
    });
    test("WhatsApp déconnecté → unhealthy", () => {
        const r = makeReporter({ connected: false }).computeStatus();
        assert.strictEqual(r.status, "unhealthy");
        assert.ok(r.reasons.includes("whatsapp_disconnected"));
    });
    test("circuit OPEN → unhealthy", () => {
        const r = makeReporter({ circuitState: "OPEN" }).computeStatus();
        assert.strictEqual(r.status, "unhealthy");
        assert.ok(r.reasons.includes("api_circuit_open"));
    });
    test("messages morts en queue → unhealthy avec compte", () => {
        const r = makeReporter({ queueStats: { dead: 3, pending: 0 } }).computeStatus();
        assert.strictEqual(r.status, "unhealthy");
        assert.ok(r.reasons.includes("queue_dead_messages=3"));
    });
    test("reconnexion en cours → degraded avec compte", () => {
        const r = makeReporter({ reconnectAttempt: 2 }).computeStatus();
        assert.strictEqual(r.status, "degraded");
        assert.ok(r.reasons.includes("reconnect_in_progress=2"));
    });
    test("pile de messages en attente > 10 → degraded", () => {
        const r = makeReporter({ queueStats: { dead: 0, pending: 15 } }).computeStatus();
        assert.strictEqual(r.status, "degraded");
        assert.ok(r.reasons.includes("queue_pending_high=15"));
    });
    test("pending exactement 10 → PAS degraded (seuil strict > 10)", () => {
        const r = makeReporter({ queueStats: { dead: 0, pending: 10 } }).computeStatus();
        assert.strictEqual(r.status, "ok");
    });
    test("circuit HALF_OPEN → degraded", () => {
        const r = makeReporter({ circuitState: "HALF_OPEN" }).computeStatus();
        assert.strictEqual(r.status, "degraded");
        assert.ok(r.reasons.includes("api_circuit_half_open"));
    });
    test("unhealthy prime sur degraded", () => {
        const r = makeReporter({ connected: false, reconnectAttempt: 1 }).computeStatus();
        assert.strictEqual(r.status, "unhealthy");
        // les deux raisons doivent apparaître
        assert.ok(r.reasons.includes("whatsapp_disconnected"));
        assert.ok(r.reasons.includes("reconnect_in_progress=1"));
    });
});

describe("HealthReporter — buildPayload", () => {
    test("payload complet cohérent avec le statut ok", () => {
        const p = makeReporter().buildPayload();
        assert.strictEqual(p.status, "ok");
        assert.deepStrictEqual(p.reasons, []);
        assert.strictEqual(p.version, "9.9.9");
        assert.strictEqual(p.uptime_seconds, 5);
        assert.deepStrictEqual(p.whatsapp, { connected: true, reconnectAttempt: 0, maxAttempts: 10 });
        assert.deepStrictEqual(p.queue, { dead: 0, pending: 0 });
        assert.deepStrictEqual(p.apiCircuit, { state: "CLOSED", failures: 0 });
        assert.strictEqual(p.users, 2);
    });
    test("uptime jamais négatif si horloge cohérente, arrondi à l'entier inférieur", () => {
        const r = new HealthReporter({
            getIsConnected: () => true, getReconnectAttempt: () => 0,
            apiCircuitBreaker: { state: "CLOSED", stats: {} },
            messageQueue: { stats: { dead: 0, pending: 0 } },
            userPrefs: { data: {} },
            appVersion: "1.0.0", processStartedAt: 0, maxAttempts: 10,
            now: () => 3999,
        });
        assert.strictEqual(r.buildPayload().uptime_seconds, 3); // floor(3999/1000)
    });
});
