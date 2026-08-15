/**
 * Tests — dispatcher pull des alertes Convex (L2 #409).
 *
 * Critères d'acceptation du brief :
 *   - GET /alerts/pending sans clé → 401 ; avec clé → liste
 *   - livraison envoyée → POST /alerts/dispatched {updated:true}
 *   - rejeu même deliveryId → already_dispatched, UN seul WhatsApp
 *   - 10 livraisons → cadencées (pas de rafale)
 *   - aucun numéro dans les logs ajoutés
 *
 * Convex / sock / prefs injectés (pas de réseau).
 * Exécution : node --test tests/alerts_dispatcher.test.js
 */
"use strict";

const { test, describe } = require("node:test");
const assert = require("node:assert");
const { computeContactRef } = require("../lib/contact_ref");
const { createAlertsDispatcher, assessAlertsConfig } = require("../lib/alerts_dispatcher");

const SECRET = "s3cr3t-test-vector";
const JID = "2250701020304@s.whatsapp.net";
const CONTACT_REF = computeContactRef(JID, SECRET);
const DISPATCH_KEY = "dispatch-key-test";
const CALLBACK_KEY = "callback-key-test";
const CONVEX = "https://convex.test";

function delivery(id, extras = {}) {
    return {
        deliveryId: id,
        contactRef: CONTACT_REF,
        text: "Alerte pluie demain",
        organizationId: "org_adc",
        ...extras,
    };
}

function makeLogger() {
    const entries = [];
    const push = (level) => (a, b) => {
        const obj = typeof a === "object" && a !== null && b !== undefined ? a : {};
        const msg = b !== undefined ? String(b) : (typeof a === "string" ? a : JSON.stringify(a));
        entries.push({ level, obj, msg, raw: JSON.stringify(a) + (b !== undefined ? String(b) : "") });
    };
    return {
        entries,
        info: push("info"),
        warn: push("warn"),
        error: push("error"),
        hasPhoneLeak() {
            return entries.some((e) =>
                e.raw.includes("2250701020304")
                || e.raw.includes("@s.whatsapp.net")
                || e.msg.includes("2250701020304"),
            );
        },
    };
}

function makeAxios({ pending = [], dispatched = { updated: true }, getStatus = 200 } = {}) {
    const calls = [];
    return {
        calls,
        async get(url, cfg) {
            calls.push({ method: "GET", url, headers: cfg?.headers || {} });
            const key = cfg?.headers?.["X-Dispatch-Key"];
            if (!key) {
                const err = new Error("Unauthorized");
                err.response = { status: 401, data: { error: "unauthorized" } };
                throw err;
            }
            if (getStatus !== 200) {
                const err = new Error(`HTTP ${getStatus}`);
                err.response = { status: getStatus };
                throw err;
            }
            return { status: 200, data: pending };
        },
        async post(url, body, cfg) {
            calls.push({ method: "POST", url, body, headers: cfg?.headers || {} });
            if (url.endsWith("/alerts/dispatched")) {
                return { status: 200, data: dispatched };
            }
            return { status: 200, data: { ok: true } };
        },
    };
}

function makeSock() {
    const sent = [];
    return {
        sent,
        async sendPresenceUpdate() {},
        async sendMessage(jid, content) {
            const id = `wamid_${sent.length + 1}`;
            sent.push({ jid, content, id });
            return { key: { id, remoteJid: jid } };
        },
    };
}

function makeDispatcher(overrides = {}) {
    const logger = overrides.logger || makeLogger();
    const axios = overrides.axios || makeAxios({ pending: overrides.pending || [] });
    let sock = overrides.sock === undefined ? makeSock() : overrides.sock;
    const delays = [];
    const dispatcher = createAlertsDispatcher({
        getSock: overrides.getSock || (() => sock),
        userPrefs: overrides.userPrefs || { data: { [JID]: { city: "Bonoua", language: "dioula" } } },
        axios,
        convexUrl: overrides.convexUrl !== undefined ? overrides.convexUrl : CONVEX,
        dispatchKey: overrides.dispatchKey !== undefined ? overrides.dispatchKey : DISPATCH_KEY,
        callbackKey: overrides.callbackKey !== undefined ? overrides.callbackKey : CALLBACK_KEY,
        hmacSecret: overrides.hmacSecret !== undefined ? overrides.hmacSecret : SECRET,
        randomDelay: overrides.randomDelay || (async (min, max) => { delays.push([min, max]); }),
        logger,
        now: overrides.now,
        idempotenceTtlMs: overrides.idempotenceTtlMs,
    });
    return { dispatcher, logger, axios, getSock: () => sock, setSock: (s) => { sock = s; }, delays };
}

describe("alerts_dispatcher — préconditions", () => {
    test("sans CONVEX_URL → aucun appel HTTP", async () => {
        const { dispatcher, axios } = makeDispatcher({ convexUrl: "" });
        const result = await dispatcher.tick();
        assert.strictEqual(axios.calls.length, 0);
        assert.strictEqual(result.skipped, "unconfigured");
    });

    test("sans X-Dispatch-Key → aucun appel (pas d'envoi sans auth)", async () => {
        const { dispatcher, axios } = makeDispatcher({ dispatchKey: "" });
        const result = await dispatcher.tick();
        assert.strictEqual(axios.calls.length, 0);
        assert.strictEqual(result.skipped, "unconfigured");
    });

    test("Convex injoignable → tick réussit, zéro envoi WhatsApp", async () => {
        const axios = {
            calls: [],
            async get() { throw Object.assign(new Error("ECONNREFUSED"), { code: "ECONNREFUSED" }); },
            async post() { throw new Error("should not post"); },
        };
        const sock = makeSock();
        const { dispatcher } = makeDispatcher({ axios, sock, pending: [delivery("d1")] });
        const result = await dispatcher.tick();
        assert.strictEqual(sock.sent.length, 0);
        assert.strictEqual(result.failed, 1);
    });
});

describe("alerts_dispatcher — contrat Convex", () => {
    test("GET /alerts/pending sans clé (côté serveur Convex) → 401, pas d'envoi", async () => {
        const axios = makeAxios({ pending: [delivery("d1")] });
        const sock = makeSock();
        const { dispatcher } = makeDispatcher({
            axios,
            sock,
            dispatchKey: DISPATCH_KEY,
        });
        // Force un GET sans header : le mock axios refuse.
        const naked = createAlertsDispatcher({
            getSock: () => sock,
            userPrefs: { data: { [JID]: {} } },
            axios: {
                calls: axios.calls,
                async get(url, cfg) {
                    return axios.get(url, { headers: {} });
                },
                post: axios.post.bind(axios),
            },
            convexUrl: CONVEX,
            dispatchKey: DISPATCH_KEY,
            callbackKey: CALLBACK_KEY,
            hmacSecret: SECRET,
            randomDelay: async () => {},
            logger: makeLogger(),
        });
        const result = await naked.tick();
        assert.strictEqual(result.failed, 1);
        assert.strictEqual(sock.sent.length, 0);
        assert.strictEqual(axios.calls[0].method, "GET");
    });

    test("GET /alerts/pending avec X-Dispatch-Key → liste traitée", async () => {
        const sock = makeSock();
        const { dispatcher, axios } = makeDispatcher({
            sock,
            pending: [delivery("d1")],
        });
        const result = await dispatcher.tick();
        const get = axios.calls.find((c) => c.method === "GET");
        assert.ok(get.url.endsWith("/alerts/pending"));
        assert.strictEqual(get.headers["X-Dispatch-Key"], DISPATCH_KEY);
        assert.strictEqual(result.sent, 1);
        assert.strictEqual(sock.sent.length, 1);
    });
});

describe("alerts_dispatcher — envoi + rapport", () => {
    test("livraison envoyée → dispatched updated:true + providerMessageId", async () => {
        const sock = makeSock();
        const { dispatcher, axios } = makeDispatcher({
            sock,
            pending: [delivery("deliv_1")],
        });
        const result = await dispatcher.tick();
        assert.strictEqual(result.sent, 1);
        assert.strictEqual(sock.sent[0].jid, JID);
        assert.strictEqual(sock.sent[0].content.text, "Alerte pluie demain");
        const post = axios.calls.find((c) => c.url.endsWith("/alerts/dispatched"));
        assert.ok(post);
        assert.deepStrictEqual(post.body, {
            deliveryId: "deliv_1",
            providerMessageId: "wamid_1",
        });
        assert.strictEqual(post.headers["X-Dispatch-Key"], DISPATCH_KEY);
        assert.strictEqual(result.dispatched[0].updated, true);
    });

    test("contactRef inconnu → skip, zéro WhatsApp, pas de dispatched", async () => {
        const sock = makeSock();
        const { dispatcher, axios } = makeDispatcher({
            sock,
            pending: [delivery("d-unknown", { contactRef: "ff".repeat(32) })],
        });
        const result = await dispatcher.tick();
        assert.strictEqual(result.unresolved, 1);
        assert.strictEqual(sock.sent.length, 0);
        assert.ok(!axios.calls.some((c) => c.url && String(c.url).includes("/dispatched")));
    });

    test("sock null au moment de l'envoi → pas de dispatched (retry au prochain tick)", async () => {
        const { dispatcher, axios } = makeDispatcher({
            getSock: () => null,
            pending: [delivery("d-nosock")],
        });
        const result = await dispatcher.tick();
        assert.strictEqual(result.sent, 0);
        assert.strictEqual(result.deferred, 1);
        assert.ok(!axios.calls.some((c) => c.url && String(c.url).includes("/dispatched")));
    });
});

describe("alerts_dispatcher — idempotence", () => {
    test("rejeu du même deliveryId → already_dispatched, un seul message WhatsApp", async () => {
        const sock = makeSock();
        const { dispatcher } = makeDispatcher({
            sock,
            pending: [delivery("same-id")],
        });
        const first = await dispatcher.tick();
        const second = await dispatcher.tick();
        assert.strictEqual(first.sent, 1);
        assert.strictEqual(second.sent, 0);
        assert.strictEqual(second.alreadyDispatched, 1);
        assert.strictEqual(sock.sent.length, 1);
    });
});

describe("alerts_dispatcher — cadence", () => {
    test("10 livraisons → 9 pauses beforeSend, pas de rafale", async () => {
        const pending = Array.from({ length: 10 }, (_, i) => delivery(`d${i}`));
        const sock = makeSock();
        const { dispatcher, delays } = makeDispatcher({ sock, pending });
        const result = await dispatcher.tick();
        assert.strictEqual(result.sent, 10);
        assert.strictEqual(sock.sent.length, 10);
        assert.strictEqual(delays.length, 9);
        for (const [min, max] of delays) {
            assert.ok(max >= min);
            assert.ok(min >= 0);
        }
    });
});

describe("alerts_dispatcher — PII", () => {
    test("aucun numéro / JID dans les logs", async () => {
        const logger = makeLogger();
        const sock = makeSock();
        const { dispatcher } = makeDispatcher({
            logger,
            sock,
            pending: [delivery("pii-1"), delivery("pii-2", { contactRef: "aa".repeat(32) })],
        });
        await dispatcher.tick();
        assert.strictEqual(logger.hasPhoneLeak(), false);
    });
});

describe("alerts_dispatcher — mutex + plafond", () => {
    test("tick concurrent → in_flight, un seul WhatsApp", async () => {
        let release;
        const gate = new Promise((resolve) => { release = resolve; });
        const sock = makeSock();
        const origSend = sock.sendMessage.bind(sock);
        sock.sendMessage = async (...args) => {
            await gate;
            return origSend(...args);
        };
        const { dispatcher } = makeDispatcher({
            sock,
            pending: [delivery("race-1")],
        });
        const first = dispatcher.tick();
        const second = await dispatcher.tick();
        assert.strictEqual(second.skipped, "in_flight");
        release();
        const done = await first;
        assert.strictEqual(done.sent, 1);
        assert.strictEqual(sock.sent.length, 1);
    });

    test("plus de 10 pending → 10 envoyés, capped, reste au poll suivant", async () => {
        const pending = Array.from({ length: 15 }, (_, i) => delivery(`cap-${i}`));
        const sock = makeSock();
        const { dispatcher } = makeDispatcher({ sock, pending });
        const first = await dispatcher.tick();
        assert.strictEqual(first.sent, 10);
        assert.strictEqual(first.capped, true);
        assert.strictEqual(sock.sent.length, 10);
        const second = await dispatcher.tick();
        assert.strictEqual(second.sent, 5);
        assert.strictEqual(sock.sent.length, 15);
    });
});

describe("assessAlertsConfig", () => {
    test("trio complet → configured", () => {
        const c = assessAlertsConfig({
            convexUrl: CONVEX, dispatchKey: DISPATCH_KEY, hmacSecret: SECRET, pollMs: 90000,
        });
        assert.strictEqual(c.configured, true);
        assert.strictEqual(c.partial, false);
        assert.strictEqual(c.pollInvalid, false);
    });
    test("un secret manquant → partial + missing nom seulement", () => {
        const c = assessAlertsConfig({
            convexUrl: CONVEX, dispatchKey: "", hmacSecret: SECRET, pollMs: 90000,
        });
        assert.strictEqual(c.partial, true);
        assert.deepStrictEqual(c.missing, ["CONVEX_DISPATCH_KEY"]);
    });
    test("ALERTS_POLL_MS invalide → pollInvalid", () => {
        const c = assessAlertsConfig({
            convexUrl: CONVEX, dispatchKey: DISPATCH_KEY, hmacSecret: SECRET, pollMs: NaN,
        });
        assert.strictEqual(c.pollInvalid, true);
    });
});

describe("alerts_dispatcher — messages.update", () => {
    test("statut Baileys connu → POST /whatsapp/callback sans numéro", async () => {
        const sock = makeSock();
        const { dispatcher, axios, logger } = makeDispatcher({
            sock,
            pending: [delivery("cb-1")],
        });
        await dispatcher.tick();
        await dispatcher.onMessageUpdate([
            { key: { id: "wamid_1" }, update: { status: 3 } },
        ]);
        const cb = axios.calls.find((c) => c.url && String(c.url).endsWith("/whatsapp/callback"));
        assert.ok(cb);
        assert.deepStrictEqual(cb.body, { providerMessageId: "wamid_1", state: "delivered" });
        assert.strictEqual(cb.headers["X-Callback-Key"], CALLBACK_KEY);
        assert.strictEqual(logger.hasPhoneLeak(), false);
    });

    test("update pour un id inconnu → aucun callback", async () => {
        const { dispatcher, axios } = makeDispatcher({ pending: [] });
        await dispatcher.onMessageUpdate([{ key: { id: "other" }, update: { status: 2 } }]);
        assert.ok(!axios.calls.some((c) => String(c.url || "").includes("/callback")));
    });
});
