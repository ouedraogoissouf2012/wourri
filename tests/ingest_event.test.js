/**
 * Tests — L5b POST /ingest/event.
 * node --test tests/ingest_event.test.js
 */
"use strict";

const { test, describe } = require("node:test");
const assert = require("node:assert");
const { reportIngest, mapLanguage } = require("../lib/ingest_event");

describe("mapLanguage", () => {
    test("dioula → dyu, french → fr", () => {
        assert.strictEqual(mapLanguage("dioula"), "dyu");
        assert.strictEqual(mapLanguage("french"), "fr");
        assert.strictEqual(mapLanguage("english"), "en");
        assert.strictEqual(mapLanguage("both"), "both");
    });
});

describe("reportIngest", () => {
    test("sans config → skipped, aucun HTTP", async () => {
        const calls = [];
        const r = await reportIngest({
            axios: { post: async (...a) => { calls.push(a); } },
            convexUrl: "",
            ingestKey: "k",
            requestId: "req1",
            status: "succeeded",
        });
        assert.strictEqual(r.skipped, "unconfigured");
        assert.strictEqual(calls.length, 0);
    });

    test("POST body sans numéro ni texte utilisateur", async () => {
        const calls = [];
        const r = await reportIngest({
            axios: {
                async post(url, body, cfg) {
                    calls.push({ url, body, headers: cfg.headers });
                    return { status: 200, data: { traceId: "t1" } };
                },
            },
            convexUrl: "https://convex.test/",
            ingestKey: "ik_test",
            requestId: "3EB0abc",
            language: "dioula",
            intent: "CONSEIL_PRODUCTION",
            source: "ivr_exact",
            latencyMs: 842,
            status: "succeeded",
        });
        assert.strictEqual(r.ok, true);
        assert.strictEqual(calls[0].url, "https://convex.test/ingest/event");
        assert.strictEqual(calls[0].headers["X-Ingest-Key"], "ik_test");
        assert.deepStrictEqual(calls[0].body, {
            requestId: "3EB0abc",
            channel: "whatsapp",
            language: "dyu",
            intent: "CONSEIL_PRODUCTION",
            source: "ivr_exact",
            latencyMs: 842,
            status: "succeeded",
        });
        const dumped = JSON.stringify(calls[0].body);
        assert.ok(!dumped.includes("@s.whatsapp"));
        assert.ok(!dumped.includes("225"));
    });

    test("Convex down → ok false, pas de throw", async () => {
        const r = await reportIngest({
            axios: { async post() { throw Object.assign(new Error("down"), { code: "ECONNREFUSED" }); } },
            convexUrl: "https://convex.test",
            ingestKey: "k",
            requestId: "r1",
            status: "failed",
            logger: { warn() {} },
        });
        assert.strictEqual(r.ok, false);
    });
});
