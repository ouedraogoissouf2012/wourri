/**
 * Tests unitaires pour la logique de reconnexion.
 * Exécution : node --test tests/reconnect.test.js
 */
"use strict";

const { test, describe } = require("node:test");
const assert = require("node:assert");
const {
    computeBackoffDelay,
    isReconnectable,
    describeDisconnectReason,
    MAX_ATTEMPTS,
    RECONNECT_BASE_DELAY,
    RECONNECT_MAX_DELAY,
    DISCONNECT_REASONS,
} = require("../lib/reconnect");

describe("computeBackoffDelay", () => {
    test("attempt 0 → 1s", () => {
        assert.strictEqual(computeBackoffDelay(0), 1000);
    });

    test("attempt 1 → 2s", () => {
        assert.strictEqual(computeBackoffDelay(1), 2000);
    });

    test("attempt 2 → 4s", () => {
        assert.strictEqual(computeBackoffDelay(2), 4000);
    });

    test("attempt 3 → 8s", () => {
        assert.strictEqual(computeBackoffDelay(3), 8000);
    });

    test("attempt 4 → 16s", () => {
        assert.strictEqual(computeBackoffDelay(4), 16000);
    });

    test("attempt 5 → 32s", () => {
        assert.strictEqual(computeBackoffDelay(5), 32000);
    });

    test("attempt 6 → 60s (cap atteint)", () => {
        assert.strictEqual(computeBackoffDelay(6), 60000);
    });

    test("attempt 20 → 60s (cap respecté)", () => {
        assert.strictEqual(computeBackoffDelay(20), 60000);
    });

    test("attempt négatif traité comme 0", () => {
        assert.strictEqual(computeBackoffDelay(-1), 1000);
        assert.strictEqual(computeBackoffDelay(-100), 1000);
    });

    test("attempt non-numérique traité comme 0", () => {
        assert.strictEqual(computeBackoffDelay("foo"), 1000);
        assert.strictEqual(computeBackoffDelay(undefined), 1000);
        assert.strictEqual(computeBackoffDelay(null), 1000);
    });
});

describe("isReconnectable", () => {
    test("loggedOut → false (compte délié)", () => {
        assert.strictEqual(isReconnectable(DISCONNECT_REASONS.loggedOut), false);
    });

    test("badSession → false (corruption auth)", () => {
        assert.strictEqual(isReconnectable(DISCONNECT_REASONS.badSession), false);
    });

    test("multideviceMismatch → false", () => {
        assert.strictEqual(
            isReconnectable(DISCONNECT_REASONS.multideviceMismatch),
            false
        );
    });

    test("forbidden → false (compte banni / restreint)", () => {
        assert.strictEqual(isReconnectable(DISCONNECT_REASONS.forbidden), false);
    });

    test("connectionLost → true", () => {
        assert.strictEqual(
            isReconnectable(DISCONNECT_REASONS.connectionLost),
            true
        );
    });

    test("connectionClosed → true", () => {
        assert.strictEqual(
            isReconnectable(DISCONNECT_REASONS.connectionClosed),
            true
        );
    });

    test("restartRequired → true", () => {
        assert.strictEqual(
            isReconnectable(DISCONNECT_REASONS.restartRequired),
            true
        );
    });

    test("unavailableService → true", () => {
        assert.strictEqual(
            isReconnectable(DISCONNECT_REASONS.unavailableService),
            true
        );
    });

    test("undefined → true (cas inconnu, on tente)", () => {
        assert.strictEqual(isReconnectable(undefined), true);
    });

    test("null → true", () => {
        assert.strictEqual(isReconnectable(null), true);
    });

    test("code arbitraire inconnu → true (default permissif)", () => {
        assert.strictEqual(isReconnectable(999), true);
        assert.strictEqual(isReconnectable(0), true);
    });
});

describe("describeDisconnectReason", () => {
    test("reconnaît loggedOut (401)", () => {
        assert.strictEqual(describeDisconnectReason(401), "loggedOut");
    });

    test("reconnaît restartRequired (515)", () => {
        assert.strictEqual(describeDisconnectReason(515), "restartRequired");
    });

    test("reconnaît connectionClosed (428)", () => {
        assert.strictEqual(describeDisconnectReason(428), "connectionClosed");
    });

    test("code inconnu retourne unknown(N)", () => {
        assert.match(describeDisconnectReason(999), /unknown\(999\)/);
    });

    test("undefined retourne unknown(undefined)", () => {
        assert.strictEqual(
            describeDisconnectReason(undefined),
            "unknown(undefined)"
        );
    });

    test("null retourne unknown(undefined)", () => {
        assert.strictEqual(describeDisconnectReason(null), "unknown(undefined)");
    });
});

describe("Constantes exportées", () => {
    test("MAX_ATTEMPTS = 10", () => {
        assert.strictEqual(MAX_ATTEMPTS, 10);
    });

    test("RECONNECT_BASE_DELAY = 1000ms", () => {
        assert.strictEqual(RECONNECT_BASE_DELAY, 1000);
    });

    test("RECONNECT_MAX_DELAY = 60000ms", () => {
        assert.strictEqual(RECONNECT_MAX_DELAY, 60000);
    });

    test("DISCONNECT_REASONS contient les codes essentiels", () => {
        assert.ok(DISCONNECT_REASONS.loggedOut);
        assert.ok(DISCONNECT_REASONS.connectionLost);
        assert.ok(DISCONNECT_REASONS.restartRequired);
    });
});
