/**
 * ADR-0045 — le baoulé servi par l'API, derrière l'interrupteur WOURI_BAOULE_SERVI.
 *
 *   - interrupteur éteint (défaut) : comportement ADR-0043 inchangé (servi en français) ;
 *   - allumé : /api/chat/ reçoit « baoule » ; la réponse native validée s'affiche en
 *     baoulé puis en français ; sans texte baoulé (repli de l'API), réponse française ;
 *   - les vocaux baoulé restent interceptés (aucun ASR baoulé branché ici).
 */
"use strict";

const { test, describe, afterEach } = require("node:test");
const assert = require("node:assert/strict");

const { MSG, pickMsg, apiLanguage, baouleServi } = require("../lib/i18n");
const { STEPS } = require("../lib/user_prefs");
const { createMessageHandler } = require("../lib/message_handler");
const { ResponseSender } = require("../lib/response_sender");
const { silentLogger, noDelay, makeSockMock } = require("./_helpers");

// Textes de la dictée validée (aucun baoulé inventé).
const REPONSE_BCI = "Ɔ fata kɛ be di fie’n, kɛ nzue tɔlɛ blɛ’n bo i bo’n.";
const REPONSE_FR = "Il faut planter en début de saison des pluies.";

afterEach(() => { delete process.env.WOURI_BAOULE_SERVI; });

describe("ADR-0045 interrupteur", () => {
    test("éteint par défaut : baoule servi en français", () => {
        assert.equal(baouleServi(), false);
        assert.equal(apiLanguage("baoule"), "french");
    });

    test("allumé : baoule part en baoule, les autres langues ne bougent pas", () => {
        process.env.WOURI_BAOULE_SERVI = "1";
        assert.equal(apiLanguage("baoule"), "baoule");
        for (const lang of ["french", "dioula", "both", "english"]) assert.equal(apiLanguage(lang), lang);
    });
});

function makeDeps(language) {
    const sock = makeSockMock();
    sock.readMessages = async () => {};
    const apiCalls = [];
    const asrCalls = [];
    return {
        apiCalls, asrCalls,
        deps: {
            sock,
            logger: silentLogger,
            asrClient: {
                transcribeAudio: async () => { asrCalls.push("whisper"); return { text: "x" }; },
                transcribeAudioBambara: async () => { asrCalls.push("bambara"); return { text: "x" }; },
            },
            responseSender: { sendResponse: async () => {}, sendExcuse: async () => {} },
            userPrefs: { get: () => ({ step: STEPS.COMPLETE, city: "Bouaké", language }), save: () => {} },
            onboardingMachine: { processStep: async () => ({ handled: null }) },
            messageQueue: { add: async () => {}, markSuccess: async () => {}, markFailure: async () => {} },
            apiCircuitBreaker: { execute: async (fn) => fn() },
            apiUrl: "http://localhost:8000",
            MSG, STEPS, pickMsg,
            authHeaders: () => ({}),
            isApiHealthy: async () => true,
            randomDelay: noDelay,
            downloadMediaMessage: async () => Buffer.from("audio"),
            pino: () => silentLogger,
            axios: { post: async (url, body) => { apiCalls.push(body); return { data: { response: "ok" } }; } },
            CircuitOpenError: class extends Error {},
        },
    };
}

const msg = (message) => ({ key: { fromMe: false, remoteJid: "u1@s.whatsapp.net", id: "wamsg_bci" }, message });

describe("ADR-0045 message_handler", () => {
    test("allumé : un texte baoulé part vers /api/chat/ en baoule", async () => {
        process.env.WOURI_BAOULE_SERVI = "1";
        const { deps, apiCalls } = makeDeps("baoule");
        await createMessageHandler(deps)({ messages: [msg({ conversation: "Blɛ benin yɛ be lua kakao ?" })] });
        assert.equal(apiCalls.length, 1);
        assert.equal(apiCalls[0].language, "baoule");
    });

    test("allumé : un vocal baoulé reste intercepté (pas d'ASR baoulé branché)", async () => {
        process.env.WOURI_BAOULE_SERVI = "1";
        const { deps, apiCalls, asrCalls } = makeDeps("baoule");
        await createMessageHandler(deps)({ messages: [msg({ audioMessage: { url: "http://x", mediaKey: "k" } })] });
        assert.deepEqual(asrCalls, []);
        assert.equal(apiCalls.length, 0);
    });
});

function makeSender(sock) {
    return new ResponseSender({
        sock,
        axios: { get: async () => { throw new Error("pas d'audio attendu"); } },
        apiUrl: "http://localhost:8000",
        randomDelay: noDelay,
        getExcuseAudio: async () => Buffer.from("audio"),
        EXCUSE_MSG: {},
        logger: silentLogger,
    });
}

describe("ADR-0045 response_sender", () => {
    test("réponse native : baoulé d'abord, puis la traduction française", async () => {
        const sock = makeSockMock();
        await makeSender(sock).sendResponse({
            data: { response: REPONSE_FR, response_local: REPONSE_BCI, meta: { source: "ivr_bci" } },
            prefs: { language: "baoule", step: STEPS.COMPLETE }, isVoiceInput: false, userNumber: "u1", saveFn: () => {},
        });
        assert.equal(sock.sent.length, 1);
        const text = sock.sent[0].msg.text;
        assert.ok(text.startsWith(REPONSE_BCI), text);
        assert.match(text, /🇫🇷 Il faut planter/);
    });

    test("repli de l'API (pas de texte baoulé) : réponse française seule", async () => {
        const sock = makeSockMock();
        await makeSender(sock).sendResponse({
            data: { response: "Je n'ai pas encore de réponse validée en baoulé pour cette question.", meta: {} },
            prefs: { language: "baoule", step: STEPS.COMPLETE }, isVoiceInput: false, userNumber: "u1", saveFn: () => {},
        });
        assert.equal(sock.sent.length, 1);
        assert.match(sock.sent[0].msg.text, /^🇫🇷 Je n'ai pas encore/);
    });
});

// ─────────────────────────────────────────────────────────────────────
// La voix (ADR-0045) : le paysan parle, il entend le locuteur natif
// ─────────────────────────────────────────────────────────────────────

const { AsrClient } = require("../lib/asr_client");

describe("ADR-0045 voix — transcription", () => {
    test("sans adresse du serveur voix : pas d'appel, null", async () => {
        let appels = 0;
        const c = new AsrClient({ apiUrl: "http://api", authHeaders: () => ({}), logger: silentLogger,
            axios: { post: async () => { appels++; return { data: {} }; } } });
        assert.equal(await c.transcribeAudioBaoule(Buffer.from("ogg")), null);
        assert.equal(appels, 0);
    });

    test("avec adresse : POST /transcribe avec la clé, texte baoulé renvoyé aussi en bambara_text", async () => {
        process.env.WOURI_BAOULE_ASR_URL = "https://voix.example/";
        process.env.WOURI_BAOULE_ASR_KEY = "cle-test";
        try {
            const appels = [];
            const c = new AsrClient({ apiUrl: "http://api", authHeaders: () => ({}), logger: silentLogger,
                axios: { post: async (url, body, opts) => { appels.push({ url, opts }); return { data: { text: "Blɛ benin" } }; } } });
            const r = await c.transcribeAudioBaoule(Buffer.from("ogg"), "v.ogg", "id1");
            assert.deepEqual(r, { text: "Blɛ benin", bambara_text: "Blɛ benin", is_bambara: false });
            assert.equal(appels[0].url, "https://voix.example/transcribe");
            assert.equal(appels[0].opts.headers["X-Api-Key"], "cle-test");
        } finally {
            delete process.env.WOURI_BAOULE_ASR_URL;
            delete process.env.WOURI_BAOULE_ASR_KEY;
        }
    });

    test("erreur du serveur voix : null (pas de repli Whisper)", async () => {
        process.env.WOURI_BAOULE_ASR_URL = "https://voix.example";
        try {
            const c = new AsrClient({ apiUrl: "http://api", authHeaders: () => ({}), logger: silentLogger,
                axios: { post: async () => { throw Object.assign(new Error("down"), { code: "ECONNREFUSED" }); } } });
            assert.equal(await c.transcribeAudioBaoule(Buffer.from("ogg")), null);
        } finally {
            delete process.env.WOURI_BAOULE_ASR_URL;
        }
    });
});

describe("ADR-0045 voix — message vocal", () => {
    test("voix servie : vocal transcrit par le serveur voix, puis /api/chat/ en baoule", async () => {
        process.env.WOURI_BAOULE_SERVI = "1";
        process.env.WOURI_BAOULE_ASR_URL = "https://voix.example";
        try {
            const { deps, apiCalls, asrCalls } = makeDeps("baoule");
            deps.asrClient.transcribeAudioBaoule = async () => {
                asrCalls.push("baoule");
                return { text: "Blɛ benin yɛ be lua kakao", bambara_text: "Blɛ benin yɛ be lua kakao" };
            };
            await createMessageHandler(deps)({ messages: [msg({ audioMessage: { url: "http://x", mediaKey: "k" } })] });
            assert.deepEqual(asrCalls, ["baoule"]);
            assert.equal(apiCalls.length, 1);
            assert.equal(apiCalls[0].language, "baoule");
            assert.equal(apiCalls[0].bambara_text, "Blɛ benin yɛ be lua kakao");
        } finally {
            delete process.env.WOURI_BAOULE_ASR_URL;
        }
    });
});

function makeSenderAudio(sock, audioGets) {
    return new ResponseSender({
        sock,
        axios: { get: async (url) => { audioGets.push(url); return { data: Buffer.from("OggS") }; } },
        apiUrl: "http://localhost:8000",
        randomDelay: noDelay,
        getExcuseAudio: async () => Buffer.from("audio"),
        EXCUSE_MSG: {},
        logger: silentLogger,
    });
}

describe("ADR-0045 voix — réponse", () => {
    test("la voix du locuteur d'abord (note vocale), puis le texte", async () => {
        const sock = makeSockMock();
        const gets = [];
        await makeSenderAudio(sock, gets).sendResponse({
            data: { response: REPONSE_FR, response_local: REPONSE_BCI, audio_url: "https://voix.example/audio/e10c.ogg" },
            prefs: { language: "baoule", step: STEPS.COMPLETE }, isVoiceInput: true, userNumber: "u1", saveFn: () => {},
        });
        assert.deepEqual(gets, ["https://voix.example/audio/e10c.ogg"]);
        assert.equal(sock.sent.length, 2);
        assert.ok(sock.sent[0].msg.audio && sock.sent[0].msg.ptt, "1er envoi : note vocale");
        assert.ok(sock.sent[1].msg.text.startsWith(REPONSE_BCI), "2e envoi : texte");
    });

    test("audio injoignable : le texte part quand même", async () => {
        const sock = makeSockMock();
        await makeSender(sock).sendResponse({
            data: { response: REPONSE_FR, response_local: REPONSE_BCI, audio_url: "https://voix.example/audio/x.ogg" },
            prefs: { language: "baoule", step: STEPS.COMPLETE }, isVoiceInput: true, userNumber: "u1", saveFn: () => {},
        });
        assert.equal(sock.sent.length, 1);
        assert.ok(sock.sent[0].msg.text.startsWith(REPONSE_BCI));
    });

    test("repli honnête : l'enregistrement prévu pour ce cas, puis le texte français", async () => {
        process.env.WOURI_BAOULE_SERVI = "1";
        process.env.WOURI_BAOULE_AUDIO_REPLI = "https://voix.example/audio/repli.ogg";
        try {
            const sock = makeSockMock();
            const gets = [];
            await makeSenderAudio(sock, gets).sendResponse({
                data: { response: "Je n'ai pas encore de réponse validée en baoulé pour cette question.", meta: {} },
                prefs: { language: "baoule", step: STEPS.COMPLETE }, isVoiceInput: true, userNumber: "u1", saveFn: () => {},
            });
            assert.deepEqual(gets, ["https://voix.example/audio/repli.ogg"]);
            assert.ok(sock.sent[0].msg.audio, "enregistrement du locuteur");
            assert.ok(sock.sent.some((s) => /Je n'ai pas encore/.test(s.msg.text || "")), "texte français");
        } finally {
            delete process.env.WOURI_BAOULE_AUDIO_REPLI;
        }
    });
});
