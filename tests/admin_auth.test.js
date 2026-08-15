/**
 * Tests unitaires — authentification entrante admin (L1, issue #408).
 *
 * Couvre le middleware `createAdminAuthMiddleware` (X-WA-Admin-Key, comparaison
 * a temps constant, chemins publics /health + /ready, fail-closed si cle absente)
 * et le garde-fou de demarrage `adminKeyStartupError` (refus de demarrer en prod
 * sans cle, sur le modele du garde-fou WOURI_API_KEY existant).
 *
 * On invoque le middleware avec des faux req/res — pas de vrai serveur Express.
 *
 * Execution : node --test tests/admin_auth.test.js
 */
"use strict";

const { test, describe } = require("node:test");
const assert = require("node:assert");
const {
    createAdminAuthMiddleware,
    adminKeyStartupError,
} = require("../lib/admin_auth");

const KEY = "s3cr3t-admin-key-0123456789";

function makeRes() {
    const res = { statusCode: 200, body: undefined };
    res.status = (c) => { res.statusCode = c; return res; };
    res.json = (b) => { res.body = b; return res; };
    return res;
}

function makeReq(path, headers = {}, ip = "10.0.0.9") {
    const lower = {};
    for (const k of Object.keys(headers)) lower[k.toLowerCase()] = headers[k];
    return { path, ip, get: (h) => lower[String(h).toLowerCase()] };
}

const silentLogger = { warn() {}, info() {}, fatal() {} };

function mw(adminKey = KEY) {
    return createAdminAuthMiddleware({
        adminKey,
        publicPaths: new Set(["/health", "/ready"]),
        logger: silentLogger,
    });
}

describe("createAdminAuthMiddleware — chemins publics", () => {
    for (const p of ["/health", "/ready"]) {
        test(`${p} passe sans cle (healthcheck preserve)`, () => {
            const req = makeReq(p);
            const res = makeRes();
            let nexted = false;
            mw()(req, res, () => { nexted = true; });
            assert.strictEqual(nexted, true);
            assert.strictEqual(res.statusCode, 200);
        });
    }
});

describe("createAdminAuthMiddleware — routes protegees", () => {
    test("sans cle -> 401 unauthorized, next non appele", () => {
        const req = makeReq("/logout");
        const res = makeRes();
        let nexted = false;
        mw()(req, res, () => { nexted = true; });
        assert.strictEqual(res.statusCode, 401);
        assert.deepStrictEqual(res.body, { error: "unauthorized" });
        assert.strictEqual(nexted, false);
    });

    test("mauvaise cle -> 401", () => {
        const req = makeReq("/logout", { "X-WA-Admin-Key": "mauvaise-cle" });
        const res = makeRes();
        let nexted = false;
        mw()(req, res, () => { nexted = true; });
        assert.strictEqual(res.statusCode, 401);
        assert.strictEqual(nexted, false);
    });

    test("cle de mauvaise longueur -> 401 sans exception (compare temps constant)", () => {
        const req = makeReq("/qr", { "X-WA-Admin-Key": "court" });
        const res = makeRes();
        assert.doesNotThrow(() => mw()(req, res, () => {}));
        assert.strictEqual(res.statusCode, 401);
    });

    test("bonne cle -> next appele, pas de 401", () => {
        const req = makeReq("/qr", { "X-WA-Admin-Key": KEY });
        const res = makeRes();
        let nexted = false;
        mw()(req, res, () => { nexted = true; });
        assert.strictEqual(nexted, true);
        assert.strictEqual(res.statusCode, 200);
    });
});

describe("createAdminAuthMiddleware — cle serveur absente (fail-closed)", () => {
    test("adminKey vide -> route protegee refusee meme avec un header", () => {
        const req = makeReq("/qr", { "X-WA-Admin-Key": "quoiquecesoit" });
        const res = makeRes();
        let nexted = false;
        mw("")(req, res, () => { nexted = true; });
        assert.strictEqual(res.statusCode, 401);
        assert.strictEqual(nexted, false);
    });

    test("adminKey vide -> /health reste public", () => {
        const req = makeReq("/health");
        const res = makeRes();
        let nexted = false;
        mw("")(req, res, () => { nexted = true; });
        assert.strictEqual(nexted, true);
    });
});

describe("adminKeyStartupError — fail-closed demarrage", () => {
    test("prod + cle vide -> message fatal (refus de demarrage)", () => {
        const err = adminKeyStartupError({ adminKey: "", nodeEnv: "production" });
        assert.match(err, /WA_ADMIN_KEY/);
    });

    test("prod + cle vide + WA_ADMIN_KEY_FILE -> message nomme le fichier", () => {
        const err = adminKeyStartupError({
            adminKey: "",
            nodeEnv: "production",
            keyFile: "/run/secrets/wa_admin_key",
        });
        assert.match(err, /WA_ADMIN_KEY_FILE/);
    });

    test("prod + cle presente -> null (demarrage autorise)", () => {
        assert.strictEqual(
            adminKeyStartupError({ adminKey: KEY, nodeEnv: "production" }),
            null,
        );
    });

    test("dev + cle vide -> null (le serveur demarre ; le middleware reste fail-closed)", () => {
        assert.strictEqual(
            adminKeyStartupError({ adminKey: "", nodeEnv: "development" }),
            null,
        );
    });
});
