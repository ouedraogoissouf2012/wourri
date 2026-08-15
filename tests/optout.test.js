/**
 * Tests — opt-out STOP (L5c #412).
 * Exécution : node --test tests/optout.test.js
 */
"use strict";

const { test, describe } = require("node:test");
const assert = require("node:assert");
const { isOptOut, reportOptOut } = require("../lib/optout");

describe("isOptOut", () => {
    test("STOP / ARRET / ARRÊT reconnus (casse, espaces, accent)", () => {
        assert.strictEqual(isOptOut("STOP"), true);
        assert.strictEqual(isOptOut("stop"), true);
        assert.strictEqual(isOptOut("  Stop  "), true);
        assert.strictEqual(isOptOut("ARRET"), true);
        assert.strictEqual(isOptOut("arrêt"), true);
        assert.strictEqual(isOptOut("Arrêt"), true);
    });
    test("ne matche pas un sous-mot ni une phrase", () => {
        assert.strictEqual(isOptOut("STOPPEZ"), false);
        assert.strictEqual(isOptOut("je veux arreter"), false);
        assert.strictEqual(isOptOut("comment planter"), false);
        assert.strictEqual(isOptOut(""), false);
        assert.strictEqual(isOptOut(null), false);
    });
});

describe("reportOptOut", () => {
    test("sans config → skipped, aucun HTTP", async () => {
        const calls = [];
        const r = await reportOptOut({
            axios: { post: async (...a) => { calls.push(a); } },
            convexUrl: "",
            callbackKey: "k",
            organizationId: "org",
            contactRef: "abc",
        });
        assert.strictEqual(r.skipped, "unconfigured");
        assert.strictEqual(calls.length, 0);
    });

    test("POST /whatsapp/optout sans numéro ni texte", async () => {
        const calls = [];
        const r = await reportOptOut({
            axios: {
                async post(url, body, cfg) {
                    calls.push({ url, body, headers: cfg.headers });
                    return { status: 200 };
                },
            },
            convexUrl: "https://convex.test/",
            callbackKey: "cb-key",
            organizationId: "org_adc",
            contactRef: "0f71ce3b",
        });
        assert.strictEqual(r.ok, true);
        assert.strictEqual(calls[0].url, "https://convex.test/whatsapp/optout");
        assert.deepStrictEqual(calls[0].body, {
            organizationId: "org_adc",
            contactRef: "0f71ce3b",
        });
        assert.strictEqual(calls[0].headers["X-Callback-Key"], "cb-key");
        assert.ok(!JSON.stringify(calls[0].body).includes("@s.whatsapp"));
    });

    test("Convex down → ok false, pas de throw", async () => {
        const r = await reportOptOut({
            axios: { async post() { throw Object.assign(new Error("down"), { code: "ECONNREFUSED" }); } },
            convexUrl: "https://convex.test",
            callbackKey: "k",
            organizationId: "org",
            contactRef: "abc",
            logger: { warn() {} },
        });
        assert.strictEqual(r.ok, false);
    });
});
