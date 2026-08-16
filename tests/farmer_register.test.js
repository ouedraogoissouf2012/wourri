/**
 * Tests — POST /whatsapp/farmer à la 1re écriture.
 * Exécution : node --test tests/farmer_register.test.js
 */
"use strict";

const { test, describe, afterEach } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { computeContactRef } = require("../lib/contact_ref");
const { createFarmerRegister } = require("../lib/farmer_register");

const SECRET = "s3cr3t-test-vector";
const JID = "2250701020304@s.whatsapp.net";
const REF = computeContactRef(JID, SECRET);

function makeReg(overrides = {}) {
    const storePath = overrides.storePath || path.join(os.tmpdir(), `farmer-${Date.now()}-${Math.random()}.json`);
    const calls = [];
    const axios = overrides.axios || {
        async post(url, body, cfg) {
            calls.push({ url, body, headers: cfg.headers });
            return { status: 200, data: { created: true, farmerId: "fid_1" } };
        },
    };
    const reg = createFarmerRegister({
        axios,
        convexUrl: overrides.convexUrl !== undefined ? overrides.convexUrl : "https://convex.test",
        callbackKey: overrides.callbackKey !== undefined ? overrides.callbackKey : "cb",
        organizationId: overrides.organizationId !== undefined ? overrides.organizationId : "demo-coop-a",
        hmacSecret: overrides.hmacSecret !== undefined ? overrides.hmacSecret : SECRET,
        logger: { info() {}, warn() {}, error() {} },
        storePath,
    });
    return { reg, calls, storePath, axios };
}

describe("farmer_register", () => {
    const temps = [];
    afterEach(() => {
        for (const p of temps) {
            try { fs.unlinkSync(p); } catch (_) { /* */ }
        }
        temps.length = 0;
    });

    test("1er sync → POST sans numéro ni JID", async () => {
        const { reg, calls, storePath } = makeReg();
        temps.push(storePath);
        const r = await reg.sync(JID);
        assert.strictEqual(r.ok, true);
        assert.strictEqual(r.created, true);
        assert.strictEqual(calls.length, 1);
        assert.ok(calls[0].url.endsWith("/whatsapp/farmer"));
        assert.deepStrictEqual(calls[0].body, {
            organizationId: "demo-coop-a",
            contactRef: REF,
        });
        assert.strictEqual(calls[0].headers["X-Callback-Key"], "cb");
        assert.ok(!JSON.stringify(calls[0].body).includes("22507"));
        assert.ok(!JSON.stringify(calls[0].body).includes("@s.whatsapp"));
    });

    test("2e sync → aucun HTTP (déjà vu)", async () => {
        const { reg, calls, storePath } = makeReg();
        temps.push(storePath);
        await reg.sync(JID);
        await reg.sync(JID);
        assert.strictEqual(calls.length, 1);
    });

    test("échec HTTP → pas marqué, retry au suivant", async () => {
        let n = 0;
        const storePath = path.join(os.tmpdir(), `farmer-fail-${Date.now()}.json`);
        temps.push(storePath);
        const axios = {
            async post() {
                n += 1;
                if (n === 1) throw Object.assign(new Error("down"), { code: "ECONNREFUSED" });
                return { status: 200, data: { created: true } };
            },
        };
        const { reg } = makeReg({ axios, storePath });
        assert.strictEqual((await reg.sync(JID)).ok, false);
        assert.strictEqual((await reg.sync(JID)).ok, true);
        assert.strictEqual(n, 2);
    });

    test("sans config → skipped, aucun HTTP", async () => {
        const { reg, calls, storePath } = makeReg({ convexUrl: "" });
        temps.push(storePath);
        const r = await reg.sync(JID);
        assert.strictEqual(r.skipped, "unconfigured");
        assert.strictEqual(calls.length, 0);
    });
});
