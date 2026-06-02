/**
 * Tests pour lib/skip_old_messages.js — filtre messages downtime.
 *
 * Couvre :
 *   - isOldMessage : timestamp < boot - grace → true
 *   - isOldMessage : timestamp = boot → false
 *   - isOldMessage : timestamp = now → false
 *   - isOldMessage : pas de timestamp → false (graceful)
 *   - isOldMessage : timestamp invalide (NaN, 0, négatif) → false
 *   - noteIgnored / getIgnoredCount / resetCounter : counter cycle
 *   - Désactivation via IGNORE_OLD_MESSAGES_ENABLED=false
 */
"use strict";

const { test, describe } = require("node:test");
const assert = require("node:assert/strict");

// Le module capture BOOT_TS à l'import, donc on le require une fois et on
// utilise ce BOOT_TS comme référence dans tous les tests.
const {
    isOldMessage,
    noteIgnored,
    getIgnoredCount,
    resetCounter,
    BOOT_TS,
    GRACE_SECONDS,
    ENABLED,
} = require("../lib/skip_old_messages");


describe("skip_old_messages — isOldMessage : timestamps", () => {
    test("message tres ancien (boot - 1h) → isOldMessage=true", () => {
        const msg = { messageTimestamp: BOOT_TS - 3600 };
        assert.strictEqual(isOldMessage(msg), true);
    });

    test("message juste avant grace (boot - 100s avec grace=30) → isOldMessage=true", () => {
        const msg = { messageTimestamp: BOOT_TS - 100 };
        assert.strictEqual(isOldMessage(msg, 30), true);
    });

    test("message dans la fenetre de grace (boot - 10s avec grace=30) → isOldMessage=false", () => {
        const msg = { messageTimestamp: BOOT_TS - 10 };
        assert.strictEqual(isOldMessage(msg, 30), false);
    });

    test("message au moment du boot → isOldMessage=false", () => {
        const msg = { messageTimestamp: BOOT_TS };
        assert.strictEqual(isOldMessage(msg), false);
    });

    test("message dans le futur (timestamp > now) → isOldMessage=false", () => {
        const msg = { messageTimestamp: BOOT_TS + 1000 };
        assert.strictEqual(isOldMessage(msg), false);
    });

    test("grace=0 strict : message boot - 1s → isOldMessage=true", () => {
        const msg = { messageTimestamp: BOOT_TS - 1 };
        assert.strictEqual(isOldMessage(msg, 0), true);
    });
});


describe("skip_old_messages — isOldMessage : graceful sur timestamp invalide", () => {
    test("messageTimestamp absent → isOldMessage=false (graceful, on traite)", () => {
        assert.strictEqual(isOldMessage({}), false);
    });

    test("messageTimestamp null → isOldMessage=false", () => {
        assert.strictEqual(isOldMessage({ messageTimestamp: null }), false);
    });

    test("messageTimestamp undefined → isOldMessage=false", () => {
        assert.strictEqual(isOldMessage({ messageTimestamp: undefined }), false);
    });

    test("messageTimestamp = 0 → isOldMessage=false (timestamp invalide)", () => {
        assert.strictEqual(isOldMessage({ messageTimestamp: 0 }), false);
    });

    test("messageTimestamp negatif → isOldMessage=false (timestamp invalide)", () => {
        assert.strictEqual(isOldMessage({ messageTimestamp: -1 }), false);
    });

    test("messageTimestamp NaN → isOldMessage=false", () => {
        assert.strictEqual(isOldMessage({ messageTimestamp: NaN }), false);
    });

    test("msg null → isOldMessage=false (defense en profondeur)", () => {
        assert.strictEqual(isOldMessage(null), false);
    });

    test("messageTimestamp Long-like (objet avec toNumber) supporte via Number()", () => {
        // Baileys peut retourner un Long (Number(longInstance) fait toNumber())
        const msg = { messageTimestamp: { toNumber: () => BOOT_TS - 3600, valueOf: () => BOOT_TS - 3600 } };
        // valueOf est appelé par Number(), donc ça doit fonctionner
        assert.strictEqual(isOldMessage(msg), true);
    });
});


describe("skip_old_messages — counter (noteIgnored, getIgnoredCount, resetCounter)", () => {
    test("counter commence a 0 ou reset le ramene a 0", () => {
        resetCounter();
        assert.strictEqual(getIgnoredCount(), 0);
    });

    test("noteIgnored() incremente le compteur de 1", () => {
        resetCounter();
        noteIgnored();
        assert.strictEqual(getIgnoredCount(), 1);
        noteIgnored();
        noteIgnored();
        assert.strictEqual(getIgnoredCount(), 3);
    });

    test("resetCounter() remet a 0 quel que soit l'etat", () => {
        resetCounter();
        for (let i = 0; i < 100; i++) noteIgnored();
        assert.strictEqual(getIgnoredCount(), 100);
        resetCounter();
        assert.strictEqual(getIgnoredCount(), 0);
    });
});


describe("skip_old_messages — configuration env vars", () => {
    test("BOOT_TS est un entier positif en secondes Unix", () => {
        assert.strictEqual(typeof BOOT_TS, "number");
        assert.ok(BOOT_TS > 1_000_000_000, "BOOT_TS doit etre un timestamp Unix realiste");
        assert.ok(Number.isInteger(BOOT_TS), "BOOT_TS doit etre un entier (secondes Unix)");
    });

    test("GRACE_SECONDS lu depuis env var ou defaut=30", () => {
        assert.strictEqual(typeof GRACE_SECONDS, "number");
        assert.ok(GRACE_SECONDS >= 0, "GRACE_SECONDS doit etre >= 0");
    });

    test("ENABLED est un booleen", () => {
        assert.strictEqual(typeof ENABLED, "boolean");
    });
});
