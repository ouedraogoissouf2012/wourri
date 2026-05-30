/**
 * Tests unitaires pour lib/message_handler.js (issue #237).
 *
 * Le module exporte une factory `createMessageHandler(deps)` qui retourne
 * un handler `async ({ messages })`. Les 4 sous-fonctions internes
 * (`_shouldIgnore`, `_extractMessageText`, `_processAudio`, `_processComplete`)
 * sont en closure → on les teste indirectement via le handler public et
 * l'observation des effets sur les mocks injectes.
 *
 * Pattern aligne sur `tests/onboarding.test.js` (factory + mocks complets).
 */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const { createMessageHandler } = require("../lib/message_handler");
const { silentLogger, makeSockMock } = require("./_helpers");

// ─────────────────────────────────────────────────────────────────────
// Constantes minimales reproduisant celles d'app-baileys.js
// ─────────────────────────────────────────────────────────────────────
const STEPS = {
    NEW: "NEW",
    WAITING_CITY: "WAITING_CITY",
    WAITING_LANGUAGE: "WAITING_LANGUAGE",
    COMPLETE: "COMPLETE",
};

const MSG = {
    AUDIO_ERROR: { french: "Erreur audio", dioula: "Audio fɔli ma se" },
    AUDIO_FAILED: { french: "Audio incompris", dioula: "Audio fɔli ma se" },
};

class CircuitOpenError extends Error {
    constructor(name) {
        super(`Circuit open for ${name}`);
        this.name = "CircuitOpenError";
    }
}

// pino mock minimal (renvoie un logger silencieux quand instancie)
const pinoMock = () => silentLogger;

// ─────────────────────────────────────────────────────────────────────
// Helper : construire un set de deps par defaut, surchargeable
// ─────────────────────────────────────────────────────────────────────

function makeDefaultDeps(overrides = {}) {
    const sock = overrides.sock ?? makeSockMock();
    sock.readMessages = sock.readMessages ?? (async () => {});
    sock.updateMediaMessage = sock.updateMediaMessage ?? (async () => {});

    const asrCalls = [];
    const asrClient = overrides.asrClient ?? {
        transcribeAudio: async (buf, name) => {
            asrCalls.push({ method: "transcribeAudio", buf, name });
            return { text: "hello world", is_bambara: false };
        },
        transcribeAudioBambara: async (buf, name) => {
            asrCalls.push({ method: "transcribeAudioBambara", buf, name });
            return { text: "I ni ce", is_bambara: true, bambara_text: "I ni ce" };
        },
    };
    asrClient._calls = asrCalls;

    const responseSenderCalls = [];
    const responseSender = overrides.responseSender ?? {
        sendResponse: async (args) => {
            responseSenderCalls.push({ method: "sendResponse", args });
        },
        sendExcuse: async (num, opts) => {
            responseSenderCalls.push({ method: "sendExcuse", num, opts });
        },
    };
    responseSender._calls = responseSenderCalls;

    const userPrefsState = overrides.userPrefsState ?? {
        step: STEPS.COMPLETE,
        city: "Abidjan",
        language: "french",
    };
    const userPrefs = overrides.userPrefs ?? {
        get: () => userPrefsState,
        save: () => {},
    };

    const onboardingMachine = overrides.onboardingMachine ?? {
        processStep: async () => ({ handled: null }),  // pass-through par defaut
    };

    const queueCalls = [];
    const messageQueue = overrides.messageQueue ?? {
        add: async (e) => { queueCalls.push({ method: "add", e }); },
        markSuccess: async (id) => { queueCalls.push({ method: "markSuccess", id }); },
        markFailure: async (id, err) => { queueCalls.push({ method: "markFailure", id, err }); },
    };
    messageQueue._calls = queueCalls;

    const apiCircuitBreaker = overrides.apiCircuitBreaker ?? {
        execute: async (fn) => fn(),  // pas de circuit, execute directement
    };

    const downloadMediaMessage = overrides.downloadMediaMessage ?? (async () => Buffer.from("fake-audio"));

    const axiosInstance = overrides.axios ?? {
        post: async () => ({ data: { reply: "ok", audio_url: null } }),
    };

    return {
        sock,
        logger: silentLogger,
        asrClient,
        responseSender,
        userPrefs,
        onboardingMachine,
        messageQueue,
        apiCircuitBreaker,
        apiUrl: "http://localhost:8000",
        MSG,
        STEPS,
        authHeaders: () => ({}),
        isApiHealthy: overrides.isApiHealthy ?? (async () => true),
        pickMsg: overrides.pickMsg ?? ((msgs, lang) => msgs[lang] ?? msgs.french),
        randomDelay: async () => {},
        downloadMediaMessage,
        pino: pinoMock,
        axios: axiosInstance,
        CircuitOpenError,
    };
}

// ─────────────────────────────────────────────────────────────────────
// Helper : fabriquer un message Baileys minimaliste
// ─────────────────────────────────────────────────────────────────────

function makeMsg({ text, fromMe = false, remoteJid = "u1@s.whatsapp.net", audio = null } = {}) {
    const message = {};
    if (text) message.conversation = text;
    if (audio) message.audioMessage = audio;
    return {
        key: { fromMe, remoteJid, id: "wamsg_test_" + Math.random().toString(36).slice(2, 8) },
        message,
    };
}

// ─────────────────────────────────────────────────────────────────────
// 1. Filtrage initial (`_shouldIgnore` indirect)
// ─────────────────────────────────────────────────────────────────────

test("ignore les messages fromMe (self)", async () => {
    const deps = makeDefaultDeps();
    const handler = createMessageHandler(deps);
    await handler({ messages: [makeMsg({ text: "hello", fromMe: true })] });

    assert.equal(deps.sock.sent.length, 0);
    assert.equal(deps.responseSender._calls.length, 0);
    assert.equal(deps.messageQueue._calls.length, 0);
});

test("ignore les messages de groupe (@g.us)", async () => {
    const deps = makeDefaultDeps();
    const handler = createMessageHandler(deps);
    await handler({ messages: [makeMsg({ text: "hello", remoteJid: "1234@g.us" })] });

    assert.equal(deps.sock.sent.length, 0);
    assert.equal(deps.responseSender._calls.length, 0);
});

test("ignore les statuts WhatsApp (status@broadcast)", async () => {
    const deps = makeDefaultDeps();
    const handler = createMessageHandler(deps);
    await handler({ messages: [makeMsg({ text: "ignore", remoteJid: "status@broadcast" })] });

    assert.equal(deps.sock.sent.length, 0);
    assert.equal(deps.responseSender._calls.length, 0);
});

test("message texte normal: flux complet declenche jusqu'a sendResponse", async () => {
    const deps = makeDefaultDeps();
    const handler = createMessageHandler(deps);
    await handler({ messages: [makeMsg({ text: "Comment cultiver le riz ?" })] });

    // sendResponse appele apres l'API success
    const sendResponseCalls = deps.responseSender._calls.filter((c) => c.method === "sendResponse");
    assert.equal(sendResponseCalls.length, 1);
    // Queue : 1 add + 1 markSuccess
    assert.equal(deps.messageQueue._calls.filter((c) => c.method === "add").length, 1);
    assert.equal(deps.messageQueue._calls.filter((c) => c.method === "markSuccess").length, 1);
});

// ─────────────────────────────────────────────────────────────────────
// 2. Pipeline audio (`_processAudio` indirect)
// ─────────────────────────────────────────────────────────────────────

test("audio sans mediaKey: ignore (pas d'appel ASR)", async () => {
    const deps = makeDefaultDeps();
    const handler = createMessageHandler(deps);
    const msg = makeMsg({ audio: { url: "http://x", /* mediaKey absent */ } });
    await handler({ messages: [msg] });

    assert.equal(deps.asrClient._calls.length, 0);
});

test("mode dioula: appelle asrClient.transcribeAudioBambara (pas Whisper)", async () => {
    const deps = makeDefaultDeps({
        userPrefsState: { step: STEPS.COMPLETE, city: "Bouake", language: "dioula" },
    });
    const handler = createMessageHandler(deps);
    const msg = makeMsg({ audio: { url: "http://x", mediaKey: "k" } });
    await handler({ messages: [msg] });

    const bambaraCalls = deps.asrClient._calls.filter((c) => c.method === "transcribeAudioBambara");
    const whisperCalls = deps.asrClient._calls.filter((c) => c.method === "transcribeAudio");
    assert.equal(bambaraCalls.length, 1, "transcribeAudioBambara doit etre appele");
    assert.equal(whisperCalls.length, 0, "Whisper FR ne doit PAS etre appele");
});

test("mode french: appelle asrClient.transcribeAudio (Whisper)", async () => {
    const deps = makeDefaultDeps({
        userPrefsState: { step: STEPS.COMPLETE, city: "Abidjan", language: "french" },
    });
    const handler = createMessageHandler(deps);
    const msg = makeMsg({ audio: { url: "http://x", mediaKey: "k" } });
    await handler({ messages: [msg] });

    const bambaraCalls = deps.asrClient._calls.filter((c) => c.method === "transcribeAudioBambara");
    const whisperCalls = deps.asrClient._calls.filter((c) => c.method === "transcribeAudio");
    assert.equal(whisperCalls.length, 1, "Whisper FR doit etre appele");
    assert.equal(bambaraCalls.length, 0, "transcribeAudioBambara ne doit PAS etre appele");
});

test("transcription vide + API down: envoie sendExcuse(unavailable)", async () => {
    const deps = makeDefaultDeps({
        asrClient: {
            transcribeAudio: async () => ({ text: "" }),  // transcription vide
            transcribeAudioBambara: async () => ({ text: "" }),
        },
        isApiHealthy: async () => false,  // API down
    });
    const handler = createMessageHandler(deps);
    const msg = makeMsg({ audio: { url: "http://x", mediaKey: "k" } });
    await handler({ messages: [msg] });

    const excuseCalls = deps.responseSender._calls.filter((c) => c.method === "sendExcuse");
    assert.equal(excuseCalls.length, 1);
    assert.equal(excuseCalls[0].opts.kind, "unavailable");
});

test("transcription vide + API up: envoie AUDIO_FAILED", async () => {
    const deps = makeDefaultDeps({
        asrClient: {
            transcribeAudio: async () => ({ text: "" }),
            transcribeAudioBambara: async () => ({ text: "" }),
        },
        isApiHealthy: async () => true,  // API up
    });
    const handler = createMessageHandler(deps);
    const msg = makeMsg({ audio: { url: "http://x", mediaKey: "k" } });
    await handler({ messages: [msg] });

    // AUDIO_FAILED envoye via sock.sendMessage (text)
    const audioFailedSent = deps.sock.sent.some((s) =>
        typeof s.msg === "object" && s.msg.text === MSG.AUDIO_FAILED.french
    );
    assert.equal(audioFailedSent, true);
    // Pas de sendExcuse car API est up
    assert.equal(deps.responseSender._calls.filter((c) => c.method === "sendExcuse").length, 0);
});

test("transcription OK: messageText setté, flux continue vers chat", async () => {
    const deps = makeDefaultDeps({
        userPrefsState: { step: STEPS.COMPLETE, city: "Korhogo", language: "dioula" },
    });
    const handler = createMessageHandler(deps);
    const msg = makeMsg({ audio: { url: "http://x", mediaKey: "k" } });
    await handler({ messages: [msg] });

    // Le flux complete doit avoir appele sendResponse
    const sendResponseCalls = deps.responseSender._calls.filter((c) => c.method === "sendResponse");
    assert.equal(sendResponseCalls.length, 1);
    // isVoiceInput doit etre true (vu que c'etait un audio)
    assert.equal(sendResponseCalls[0].args.isVoiceInput, true);
});

// ─────────────────────────────────────────────────────────────────────
// 3. Pipeline chat (`_processComplete` indirect)
// ─────────────────────────────────────────────────────────────────────

test("step COMPLETE + API success: markSuccess + sendResponse", async () => {
    const deps = makeDefaultDeps();
    const handler = createMessageHandler(deps);
    await handler({ messages: [makeMsg({ text: "Comment planter ?" })] });

    const markSuccessCalls = deps.messageQueue._calls.filter((c) => c.method === "markSuccess");
    const sendResponseCalls = deps.responseSender._calls.filter((c) => c.method === "sendResponse");
    assert.equal(markSuccessCalls.length, 1);
    assert.equal(sendResponseCalls.length, 1);
});

test("API CircuitOpenError: markFailure + sendExcuse(unavailable), pas de sendResponse", async () => {
    const circuitErr = new CircuitOpenError("wouri-api");
    const deps = makeDefaultDeps({
        apiCircuitBreaker: {
            execute: async () => { throw circuitErr; },
        },
    });
    const handler = createMessageHandler(deps);
    await handler({ messages: [makeMsg({ text: "test" })] });

    const markFailureCalls = deps.messageQueue._calls.filter((c) => c.method === "markFailure");
    const sendExcuseCalls = deps.responseSender._calls.filter((c) => c.method === "sendExcuse");
    const sendResponseCalls = deps.responseSender._calls.filter((c) => c.method === "sendResponse");
    assert.equal(markFailureCalls.length, 1);
    assert.equal(sendExcuseCalls.length, 1);
    assert.equal(sendExcuseCalls[0].opts.kind, "unavailable");
    assert.equal(sendResponseCalls.length, 0, "sendResponse ne doit PAS etre appele");
});

test("API erreur generique: catch global declenche sendExcuse", async () => {
    const genericErr = new Error("Connection timeout");
    const deps = makeDefaultDeps({
        apiCircuitBreaker: {
            execute: async () => { throw genericErr; },
        },
    });
    const handler = createMessageHandler(deps);
    await handler({ messages: [makeMsg({ text: "test" })] });

    // Le catch global doit envoyer un sendExcuse
    const sendExcuseCalls = deps.responseSender._calls.filter((c) => c.method === "sendExcuse");
    assert.equal(sendExcuseCalls.length, 1);
    assert.equal(sendExcuseCalls[0].opts.kind, "unavailable");
});

// ─────────────────────────────────────────────────────────────────────
// 4. Onboarding delegation
// ─────────────────────────────────────────────────────────────────────

test("onboarding.handled=true: handler stop, pas de sendResponse", async () => {
    const deps = makeDefaultDeps({
        onboardingMachine: {
            processStep: async () => ({ handled: true }),  // onboarding a tout gere
        },
    });
    const handler = createMessageHandler(deps);
    await handler({ messages: [makeMsg({ text: "Abidjan" })] });

    // Onboarding a "consomme" le message → pas de pipeline chat
    const sendResponseCalls = deps.responseSender._calls.filter((c) => c.method === "sendResponse");
    assert.equal(sendResponseCalls.length, 0);
    const addCalls = deps.messageQueue._calls.filter((c) => c.method === "add");
    assert.equal(addCalls.length, 0);
});

test("onboarding.newMessageText: remplace messageText avant pipeline chat", async () => {
    let capturedMessageText = null;
    const deps = makeDefaultDeps({
        onboardingMachine: {
            // Onboarding termine et fournit un nouveau message a traiter
            processStep: async () => ({ handled: false, newMessageText: "Question reformulee" }),
        },
        apiCircuitBreaker: {
            // Capturer le message text effectif passe a l'API
            execute: async (fn) => {
                // L'execute est appele par _processComplete avec un async wrapper
                // qui appelle axios.post. On execute pour declencher l'appel.
                const result = await fn();
                return result;
            },
        },
        axios: {
            post: async (url, body) => {
                capturedMessageText = body.message;
                return { data: { reply: "ok" } };
            },
        },
    });
    const handler = createMessageHandler(deps);
    await handler({ messages: [makeMsg({ text: "Question originale" })] });

    assert.equal(capturedMessageText, "Question reformulee");
});
