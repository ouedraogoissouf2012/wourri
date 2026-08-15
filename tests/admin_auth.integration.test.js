/**
 * Test d'integration — auth entrante admin dans une VRAIE pile Express (L1 #408).
 *
 * Reproduit l'ordre reel de app-baileys.js (express.json -> adminAuth -> routes)
 * sur un serveur HTTP ephemere, sans demarrer Baileys. Verifie les criteres
 * d'acceptation du brief au niveau HTTP.
 *
 * Execution : node --test tests/admin_auth.integration.test.js
 */
"use strict";

const { test } = require("node:test");
const assert = require("node:assert");
const http = require("node:http");
const express = require("express");
const { createAdminAuthMiddleware } = require("../lib/admin_auth");

const KEY = "integration-admin-key-xyz";
const silentLogger = { warn() {} };

function buildServer() {
    const app = express();
    app.use(express.json());
    app.use(createAdminAuthMiddleware({
        adminKey: KEY,
        publicPaths: new Set(["/health", "/ready"]),
        logger: silentLogger,
    }));
    // Routes factices reproduisant les routes reelles protegees/publiques.
    app.get("/health", (req, res) => res.status(200).json({ status: "ok" }));
    app.get("/ready", (req, res) => res.status(200).json({ ready: true }));
    app.get("/qr", (req, res) => res.status(200).json({ qr: "data" }));
    app.post("/logout", (req, res) => res.status(200).json({ loggedOut: true }));
    return app;
}

function request(port, method, path, headers = {}) {
    return new Promise((resolve, reject) => {
        const req = http.request({ port, host: "127.0.0.1", method, path, headers }, (res) => {
            let body = "";
            res.on("data", (c) => { body += c; });
            res.on("end", () => resolve({ status: res.statusCode, body }));
        });
        req.on("error", reject);
        req.end();
    });
}

test("pile Express reelle — criteres d'acceptation L1", async () => {
    const server = buildServer().listen(0, "127.0.0.1");
    await new Promise((r) => server.once("listening", r));
    const port = server.address().port;
    try {
        // POST /logout sans cle -> 401 (session Baileys jamais touchee)
        assert.strictEqual((await request(port, "POST", "/logout")).status, 401);
        // GET /qr sans cle -> 401
        assert.strictEqual((await request(port, "GET", "/qr")).status, 401);
        // GET /health sans cle -> 200 (healthcheck Docker preserve)
        assert.strictEqual((await request(port, "GET", "/health")).status, 200);
        // GET /ready sans cle -> 200
        assert.strictEqual((await request(port, "GET", "/ready")).status, 200);
        // Avec la bonne cle -> comportement normal
        assert.strictEqual((await request(port, "GET", "/qr", { "X-WA-Admin-Key": KEY })).status, 200);
        assert.strictEqual((await request(port, "POST", "/logout", { "X-WA-Admin-Key": KEY })).status, 200);
        // Mauvaise cle -> 401
        assert.strictEqual((await request(port, "POST", "/logout", { "X-WA-Admin-Key": "nope" })).status, 401);
    } finally {
        await new Promise((r) => server.close(r));
    }
});
