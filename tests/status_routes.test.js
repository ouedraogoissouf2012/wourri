/**
 * Tests de caractérisation pour les routes de statut (registerStatusRoutes).
 *
 * Capturent le comportement des routes /, /status, /health, /ready, /users,
 * /qr, /qr-page, /logout telles qu'elles existaient inline dans app-baileys.js.
 * On enregistre les handlers sur un faux `app` puis on les invoque avec des
 * faux req/res — pas de vrai serveur Express.
 *
 * Exécution : node --test tests/status_routes.test.js
 */
"use strict";

const { test, describe } = require("node:test");
const assert = require("node:assert");
const { registerStatusRoutes, renderQrPage } = require("../lib/status_routes");

function makeApp() {
    const handlers = { get: {}, post: {} };
    return {
        handlers,
        get(path, h) { handlers.get[path] = h; },
        post(path, h) { handlers.post[path] = h; },
    };
}

function makeRes() {
    const res = { statusCode: 200, body: undefined, sent: undefined };
    res.status = (c) => { res.statusCode = c; return res; };
    res.json = (b) => { res.body = b; return res; };
    res.send = (s) => { res.sent = s; return res; };
    return res;
}

const fakeHealth = {
    _payload: { status: "ok", reasons: [], version: "1.0.0" },
    buildPayload() { return this._payload; },
};

function baseCtx(overrides = {}) {
    return {
        getIsConnected: () => true,
        getQrCodeData: () => null,
        getSock: () => null,
        userPrefs: { data: {} },
        authFolder: "/tmp/auth",
        fs: { existsSync: () => false, rmSync: () => {} },
        QRCode: { toDataURL: async () => "data:image/png;base64,ZZZ" },
        health: fakeHealth,
        ...overrides,
    };
}

async function invoke(app, method, path, res = makeRes()) {
    await app.handlers[method][path]({}, res);
    return res;
}

describe("registerStatusRoutes — validation", () => {
    test("throw si getIsConnected manquant", () => {
        assert.throws(() => registerStatusRoutes(makeApp(), { health: fakeHealth }), /getIsConnected/);
    });
    test("throw si health.buildPayload manquant", () => {
        assert.throws(() => registerStatusRoutes(makeApp(), { getIsConnected: () => true }), /health\.buildPayload/);
    });
});

describe("registerStatusRoutes — routes info", () => {
    test("GET / → status running + compte users", async () => {
        const app = makeApp();
        registerStatusRoutes(app, baseCtx({ userPrefs: { data: { a: {}, b: {} } } }));
        const res = await invoke(app, "get", "/");
        assert.strictEqual(res.body.status, "running");
        assert.strictEqual(res.body.name, "WOURI WhatsApp Server");
        assert.strictEqual(res.body.connected, true);
        assert.strictEqual(res.body.users, 2);
    });

    test("GET /status → connected + qrCode live + users", async () => {
        const app = makeApp();
        registerStatusRoutes(app, baseCtx({ getIsConnected: () => false, getQrCodeData: () => "QR123" }));
        const res = await invoke(app, "get", "/status");
        assert.deepStrictEqual(res.body, { connected: false, qrCode: "QR123", users: 0 });
    });

    test("GET /users → numéros tronqués + ***", async () => {
        const app = makeApp();
        registerStatusRoutes(app, baseCtx({
            userPrefs: { data: { "22501234567": { city: "Bouake", language: "dioula", step: "COMPLETE" } } },
        }));
        const res = await invoke(app, "get", "/users");
        assert.strictEqual(res.body.length, 1);
        assert.strictEqual(res.body[0].number, "22501234***");
        assert.strictEqual(res.body[0].city, "Bouake");
        assert.strictEqual(res.body[0].language, "dioula");
    });
});

describe("registerStatusRoutes — /health et /ready", () => {
    test("GET /health → renvoie le payload du HealthReporter (toujours 200)", async () => {
        const app = makeApp();
        registerStatusRoutes(app, baseCtx());
        const res = await invoke(app, "get", "/health");
        assert.strictEqual(res.statusCode, 200);
        assert.strictEqual(res.body.status, "ok");
    });

    test("GET /ready → 200 quand status ok", async () => {
        const app = makeApp();
        registerStatusRoutes(app, baseCtx());
        const res = await invoke(app, "get", "/ready");
        assert.strictEqual(res.statusCode, 200);
        assert.strictEqual(res.body.ready, true);
    });

    test("GET /ready → 503 quand status non-ok", async () => {
        const app = makeApp();
        const degradedHealth = { buildPayload: () => ({ status: "degraded", reasons: ["x"] }) };
        registerStatusRoutes(app, baseCtx({ health: degradedHealth }));
        const res = await invoke(app, "get", "/ready");
        assert.strictEqual(res.statusCode, 503);
        assert.strictEqual(res.body.ready, false);
        assert.deepStrictEqual(res.body.reasons, ["x"]);
    });
});

describe("registerStatusRoutes — /qr", () => {
    test("qrCode présent → {qr}", async () => {
        const app = makeApp();
        registerStatusRoutes(app, baseCtx({ getQrCodeData: () => "ABC" }));
        assert.deepStrictEqual((await invoke(app, "get", "/qr")).body, { qr: "ABC" });
    });
    test("connecté sans QR → 'Deja connecte'", async () => {
        const app = makeApp();
        registerStatusRoutes(app, baseCtx({ getQrCodeData: () => null, getIsConnected: () => true }));
        assert.deepStrictEqual((await invoke(app, "get", "/qr")).body, { message: "Deja connecte" });
    });
    test("ni QR ni connecté → 'pas encore genere'", async () => {
        const app = makeApp();
        registerStatusRoutes(app, baseCtx({ getQrCodeData: () => null, getIsConnected: () => false }));
        assert.deepStrictEqual((await invoke(app, "get", "/qr")).body, { message: "QR code pas encore genere" });
    });
});

describe("registerStatusRoutes — /logout", () => {
    test("logout appelle sock.logout puis supprime auth_baileys", async () => {
        let loggedOut = false;
        let removed = false;
        const app = makeApp();
        registerStatusRoutes(app, baseCtx({
            getSock: () => ({ logout: async () => { loggedOut = true; } }),
            fs: { existsSync: () => true, rmSync: () => { removed = true; } },
        }));
        const res = await invoke(app, "post", "/logout");
        assert.strictEqual(loggedOut, true);
        assert.strictEqual(removed, true);
        assert.deepStrictEqual(res.body, { success: true, message: "Deconnecte" });
    });

    test("logout sans sock ne throw pas", async () => {
        const app = makeApp();
        registerStatusRoutes(app, baseCtx({ getSock: () => null, fs: { existsSync: () => false, rmSync: () => {} } }));
        const res = await invoke(app, "post", "/logout");
        assert.strictEqual(res.body.success, true);
    });

    test("erreur durant logout → 500 avec message", async () => {
        const app = makeApp();
        registerStatusRoutes(app, baseCtx({
            getSock: () => ({ logout: async () => { throw new Error("boom logout"); } }),
        }));
        const res = await invoke(app, "post", "/logout");
        assert.strictEqual(res.statusCode, 500);
        assert.strictEqual(res.body.error, "boom logout");
    });
});

describe("renderQrPage", () => {
    test("connecté → message CONNECTE, pas d'image", async () => {
        const html = await renderQrPage({ isConnected: true, qrCodeData: null, QRCode: null });
        assert.match(html, /CONNECTE A WHATSAPP/);
        assert.doesNotMatch(html, /<img/);
    });
    test("QR présent → image data-url + attente scan", async () => {
        const html = await renderQrPage({
            isConnected: false, qrCodeData: "QR",
            QRCode: { toDataURL: async () => "data:image/png;base64,ZZZ" },
        });
        assert.match(html, /data:image\/png;base64,ZZZ/);
        assert.match(html, /En attente de scan/);
    });
    test("erreur de génération QR → message d'erreur, pas de crash", async () => {
        const html = await renderQrPage({
            isConnected: false, qrCodeData: "QR",
            QRCode: { toDataURL: async () => { throw new Error("qr fail"); } },
        });
        assert.match(html, /Erreur generation QR/);
    });
    test("ni connecté ni QR → génération en cours", async () => {
        const html = await renderQrPage({ isConnected: false, qrCodeData: null, QRCode: null });
        assert.match(html, /QR code en cours de generation/);
    });
});
