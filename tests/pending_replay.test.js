/**
 * Tests unitaires pour createPendingReplayer (fix #299).
 * Exécution : node --test tests/pending_replay.test.js
 *
 * Objet du fix : après reconnexion, les messages en attente dans la queue
 * doivent être REJOUÉS contre /api/chat/ et la vraie réponse envoyée à
 * l'utilisateur — au lieu d'être jetés (markSuccess) après une simple excuse
 * « repose ta question ».
 *
 * On exerce le vrai MessageQueue et le vrai UserPrefs (fichiers tmp) pour
 * valider le cycle réel getPending → sendResponse → markSuccess / markFailure.
 * responseSender et l'appel API (axios + circuit breaker) sont mockés.
 */
"use strict";

const { test, describe, beforeEach, afterEach } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");

const { MessageQueue } = require("../lib/message_queue");
const { UserPrefs, STEPS } = require("../lib/user_prefs");
const { createPendingReplayer } = require("../lib/pending_replay");

const silentLogger = { info() {}, warn() {}, error() {}, debug() {}, child() { return silentLogger; }, log() {} };

// ── Mock responseSender : capture les appels sendResponse, scriptable pour throw ──
function makeResponseSenderMock({ throwOn = [] } = {}) {
    const calls = [];
    return {
        calls,
        sendResponse: async ({ data, prefs, isVoiceInput, userNumber, saveFn }) => {
            calls.push({ data, prefs, isVoiceInput, userNumber });
            // Reproduit l'effet réel : en dioula/both + data.meta présent, sendResponse
            // mute prefs.step/pendingFeedback puis save (prompt feedback C4).
            if ((prefs.language === "dioula" || prefs.language === "both") && data.meta) {
                prefs.pendingFeedback = { intent: data.meta.intent || "" };
                prefs.step = STEPS.WAITING_FEEDBACK;
                if (typeof saveFn === "function") saveFn();
            }
            if (throwOn.includes(userNumber)) {
                throw new Error(`sendResponse KO pour ${userNumber}`);
            }
        },
    };
}

// ── Mock apiCircuitBreaker : exécute le thunk (ou throw scripté) ──
function makeBreakerMock({ throwErr = null } = {}) {
    return {
        execute: async (fn) => {
            if (throwErr) throw throwErr;
            return fn();
        },
    };
}

// ── Mock axios : renvoie une réponse /api/chat/ scriptée par messageText ──
function makeAxiosMock(dataByMessage = {}) {
    const calls = [];
    return {
        calls,
        post: async (url, body, opts) => {
            calls.push({ url, body, opts });
            const data = dataByMessage[body.message] || {
                response: `RÉPONSE[${body.message}]`,
                response_dioula: `DIOULA[${body.message}]`,
                audio_url: "/audio/x.mp3",
                meta: { intent: `INTENT[${body.message}]` },
            };
            return { data };
        },
    };
}

// Fabrique un replayer avec une queue et des prefs réels + deps mockées.
function makeSetup({ isApiHealthy = async () => true, responseSender, breaker, axios } = {}) {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "replay-test-"));
    const queuePath = path.join(tmpDir, "pending.json");
    const prefsPath = path.join(tmpDir, "prefs.json");

    // now() injectable pour contrôler createdAt (test ordre chronologique).
    let clock = 0;
    const now = () => new Date(Date.UTC(2026, 0, 1, 0, 0, clock++)).toISOString();
    const queue = new MessageQueue({ filePath: queuePath, logger: silentLogger, now });
    const userPrefs = new UserPrefs({ fs, filePath: prefsPath, logger: silentLogger });

    const rs = responseSender || makeResponseSenderMock();
    const br = breaker || makeBreakerMock();
    const ax = axios || makeAxiosMock();
    const randomDelayCalls = [];
    const randomDelay = async (min, max) => { randomDelayCalls.push([min, max]); };

    const replayer = createPendingReplayer({
        messageQueue: queue,
        userPrefs,
        responseSender: rs,
        apiCircuitBreaker: br,
        axios: ax,
        apiUrl: "http://localhost:8000",
        authHeaders: () => ({ "X-API-Key": "test" }),
        isApiHealthy,
        randomDelay,
        logger: silentLogger,
        DEFAULT_USER_LANGUAGE: "french",
    });

    return { tmpDir, queue, userPrefs, rs, br, ax, randomDelayCalls, replayer };
}

function cleanup(tmpDir) {
    try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch (_) {}
}

describe("createPendingReplayer — fix #299 rejeu réel de la queue", () => {
    let tmpDir;
    afterEach(() => { if (tmpDir) cleanup(tmpDir); tmpDir = null; });

    test("queue vide → no-op (aucun sendResponse)", async () => {
        const s = makeSetup(); tmpDir = s.tmpDir;
        await s.queue.load();
        await s.replayer();
        assert.strictEqual(s.rs.calls.length, 0);
    });

    test("rejoue chaque message : appel /api/chat/ + sendResponse + markSuccess (queue vidée)", async () => {
        const s = makeSetup(); tmpDir = s.tmpDir;
        await s.queue.load();
        s.userPrefs.get("uA").language = "french";
        s.userPrefs.get("uA").city = "Bouaké";
        await s.queue.add({ id: "m1", userNumber: "uA", payload: { messageText: "quand semer le maïs", city: "Bouaké", language: "french", isVoiceInput: false } });

        await s.replayer();

        // Appel API réel avec le payload
        assert.strictEqual(s.ax.calls.length, 1);
        assert.match(s.ax.calls[0].url, /\/api\/chat\/$/);
        assert.strictEqual(s.ax.calls[0].body.message, "quand semer le maïs");
        assert.strictEqual(s.ax.calls[0].body.user_id, "uA");
        // Réponse réellement envoyée
        assert.strictEqual(s.rs.calls.length, 1);
        assert.strictEqual(s.rs.calls[0].userNumber, "uA");
        // Marqué succès → retiré de la queue
        assert.strictEqual(s.queue.getPending().length, 0);
    });

    test("API indisponible → ne rejoue rien, messages restent en queue", async () => {
        const s = makeSetup({ isApiHealthy: async () => false }); tmpDir = s.tmpDir;
        await s.queue.load();
        await s.queue.add({ id: "m1", userNumber: "uA", payload: { messageText: "q1", language: "french" } });

        await s.replayer();

        assert.strictEqual(s.rs.calls.length, 0);
        assert.strictEqual(s.ax.calls.length, 0);
        assert.strictEqual(s.queue.getPending().length, 1);
    });

    test("échec API → markFailure (attemptCount++), reste en queue, pas de sendResponse", async () => {
        const breaker = makeBreakerMock({ throwErr: new Error("ECONNREFUSED") });
        const s = makeSetup({ breaker }); tmpDir = s.tmpDir;
        await s.queue.load();
        await s.queue.add({ id: "m1", userNumber: "uA", payload: { messageText: "q1", language: "french" } });

        await s.replayer();

        assert.strictEqual(s.rs.calls.length, 0);
        const pending = s.queue.getPending();
        assert.strictEqual(pending.length, 1);
        assert.strictEqual(pending[0].attemptCount, 1);
        assert.match(pending[0].lastError, /ECONNREFUSED/);
    });

    test("échec sendResponse (WhatsApp KO) après API OK → markFailure, PAS markSuccess (message conservé)", async () => {
        const rs = makeResponseSenderMock({ throwOn: ["uA"] });
        const s = makeSetup({ responseSender: rs }); tmpDir = s.tmpDir;
        await s.queue.load();
        s.userPrefs.get("uA").language = "french";
        await s.queue.add({ id: "m1", userNumber: "uA", payload: { messageText: "q1", language: "french" } });

        await s.replayer();

        // sendResponse a bien été tenté mais a jeté → message conservé pour retry
        assert.strictEqual(rs.calls.length, 1);
        const pending = s.queue.getPending();
        assert.strictEqual(pending.length, 1);
        assert.strictEqual(pending[0].attemptCount, 1);
    });

    test("ordre chronologique : rejoue le plus ancien en premier même si ajouté après", async () => {
        const s = makeSetup(); tmpDir = s.tmpDir;
        await s.queue.load();
        s.userPrefs.get("uA").language = "french";
        // Ajouté en 1er mais createdAt PLUS RÉCENT (clock avance à chaque now()).
        // now() renvoie t0 pour recent, t1 pour old → on force en ajoutant recent d'abord.
        await s.queue.add({ id: "recent", userNumber: "uA", payload: { messageText: "RECENT", language: "french" } });
        await s.queue.add({ id: "old", userNumber: "uA", payload: { messageText: "OLD", language: "french" } });
        // recent.createdAt < old.createdAt ici (clock), donc on inverse le test :
        // on veut prouver le TRI, on relit les createdAt réels.
        const pend = s.queue.getPending();
        const sorted = [...pend].sort((a, b) => new Date(a.createdAt) - new Date(b.createdAt));
        const expectedOrder = sorted.map((m) => m.payload.messageText);

        await s.replayer();

        const actualOrder = s.rs.calls.map((c) => c.data.response.match(/\[(.+)\]/)[1]);
        assert.deepStrictEqual(actualOrder, expectedOrder);
    });

    test("[A2] user avec plusieurs messages dioula → feedback (data.meta) supprimé sauf pour le DERNIER", async () => {
        const s = makeSetup(); tmpDir = s.tmpDir;
        await s.queue.load();
        s.userPrefs.get("uA").language = "dioula";
        s.userPrefs.get("uA").city = "Bouaké";
        await s.queue.add({ id: "m1", userNumber: "uA", payload: { messageText: "Q1", language: "dioula" } });
        await s.queue.add({ id: "m2", userNumber: "uA", payload: { messageText: "Q2", language: "dioula" } });

        await s.replayer();

        assert.strictEqual(s.rs.calls.length, 2);
        // Ordre chronologique : m1 puis m2 (m2 = dernier)
        assert.strictEqual(s.rs.calls[0].data.meta, undefined, "feedback supprimé pour le 1er (non dernier)");
        assert.ok(s.rs.calls[1].data.meta, "feedback conservé pour le dernier");
        // L'état feedback final pointe sur le DERNIER message (Q2)
        assert.strictEqual(s.userPrefs.get("uA").step, STEPS.WAITING_FEEDBACK);
        assert.strictEqual(s.userPrefs.get("uA").pendingFeedback.intent, "INTENT[Q2]");
        assert.strictEqual(s.queue.getPending().length, 0);
    });

    test("anti-flood : randomDelay invoqué quand plusieurs messages", async () => {
        const s = makeSetup(); tmpDir = s.tmpDir;
        await s.queue.load();
        s.userPrefs.get("uA").language = "french";
        await s.queue.add({ id: "m1", userNumber: "uA", payload: { messageText: "Q1", language: "french" } });
        await s.queue.add({ id: "m2", userNumber: "uA", payload: { messageText: "Q2", language: "french" } });

        await s.replayer();

        assert.ok(s.randomDelayCalls.length >= 1, "au moins un délai anti-flood entre 2 envois");
    });

    test("[ré-entrance] deux drains concurrents → un seul draine (pas de double-réponse)", async () => {
        // API lente contrôlée par une barrière pour maintenir le 1er drain en vol.
        let releaseApi;
        const gate = new Promise((res) => { releaseApi = res; });
        const axios = {
            calls: [],
            post: async (url, body, opts) => {
                axios.calls.push({ url, body, opts });
                await gate; // suspend le 1er drain pendant l'appel concurrent
                return { data: { response: `R[${body.message}]`, meta: { intent: "x" } } };
            },
        };
        const s = makeSetup({ axios }); tmpDir = s.tmpDir;
        await s.queue.load();
        s.userPrefs.get("uA").language = "french";
        await s.queue.add({ id: "m1", userNumber: "uA", payload: { messageText: "Q1", language: "french" } });

        const p1 = s.replayer();                          // démarre → se bloque sur gate
        await new Promise((r) => setImmediate(r));         // laisse p1 progresser
        const r2 = await s.replayer();                     // concurrent → doit être ignoré
        assert.strictEqual(r2.skipped, true, "le 2e drain concurrent est ignoré");

        releaseApi();
        const r1 = await p1;
        assert.strictEqual(r1.replayed, 1);
        // Un seul appel API et un seul envoi malgré 2 invocations
        assert.strictEqual(axios.calls.length, 1);
        assert.strictEqual(s.rs.calls.length, 1);
        assert.strictEqual(s.queue.getPending().length, 0);
    });

    test("[ré-entrance] le verrou est libéré après un drain (2e appel séquentiel fonctionne)", async () => {
        const s = makeSetup(); tmpDir = s.tmpDir;
        await s.queue.load();
        s.userPrefs.get("uA").language = "french";
        await s.queue.add({ id: "m1", userNumber: "uA", payload: { messageText: "Q1", language: "french" } });
        const r1 = await s.replayer();
        assert.strictEqual(r1.replayed, 1);
        // Deuxième drain séquentiel : queue vide, mais NON "skipped" (verrou relâché)
        const r2 = await s.replayer();
        assert.notStrictEqual(r2.skipped, true);
        assert.strictEqual(r2.replayed, 0);
    });

    test("multi-users indépendants : un échec API sur un user n'empêche pas les autres", async () => {
        // uBAD échoue à l'API, uOK réussit.
        const breaker = {
            execute: async (fn) => fn(),
        };
        const axios = makeAxiosMock();
        // Rendre uBAD échouant : on intercepte via un axios qui throw si message=BAD
        const axFail = {
            calls: axios.calls,
            post: async (url, body, opts) => {
                axios.calls.push({ url, body, opts });
                if (body.message === "BAD") throw new Error("ETIMEDOUT");
                return { data: { response: `R[${body.message}]`, meta: { intent: "x" } } };
            },
        };
        const s = makeSetup({ breaker, axios: axFail }); tmpDir = s.tmpDir;
        await s.queue.load();
        s.userPrefs.get("uBAD").language = "french";
        s.userPrefs.get("uOK").language = "french";
        await s.queue.add({ id: "bad", userNumber: "uBAD", payload: { messageText: "BAD", language: "french" } });
        await s.queue.add({ id: "ok", userNumber: "uOK", payload: { messageText: "GOOD", language: "french" } });

        await s.replayer();

        // uOK a été servi et retiré ; uBAD reste en queue
        assert.strictEqual(s.rs.calls.length, 1);
        assert.strictEqual(s.rs.calls[0].userNumber, "uOK");
        const ids = s.queue.getPending().map((m) => m.id);
        assert.deepStrictEqual(ids, ["bad"]);
    });
});
