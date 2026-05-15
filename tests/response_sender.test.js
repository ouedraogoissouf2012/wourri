/**
 * Tests unitaires pour ResponseSender.
 * Exécution : node --test tests/response_sender.test.js
 *
 * Couvre les 3 modes FRANCAIS/DIOULA/BOTH (sendResponse) + 4 chemins de sendExcuse,
 * avec mock sock (capture des sendMessage) et mock axios (réponses scriptées).
 */
"use strict";

const { test, describe } = require("node:test");
const assert = require("node:assert");
const { ResponseSender } = require("../lib/response_sender");
const { silentLogger, noDelay, makeSockMock } = require("./_helpers");

const STEPS = {
    NEW: "new",
    WAITING_CITY: "waiting_city",
    WAITING_LANGUAGE: "waiting_language",
    COMPLETE: "complete",
    WAITING_FEEDBACK: "waiting_feedback",
};

const EXCUSE_MSG = {
    UNAVAILABLE_FR: "Je suis temporairement indisponible.",
    UNAVAILABLE_DIOULA: "N tɛna se ka jaabi di.",
    UNAVAILABLE_BILINGUAL: "🇫🇷 Indispo. — N tɛna se.",
    BACK_FR: "Je suis de retour.",
    BACK_DIOULA: "N kɔsegira.",
    BACK_BILINGUAL: "🇫🇷 De retour. — N kɔsegira.",
};

// Note : makeAxiosMock reste local — méthode .get spécifique à response_sender.
// Pour la version .post (onboarding), voir tests/onboarding.test.js.
function makeAxiosMock(responses) {
    const calls = [];
    let idx = 0;
    return {
        calls,
        get: async (url, opts) => {
            calls.push({ url, opts });
            const r = responses[idx++];
            if (r instanceof Error) throw r;
            return r;
        },
    };
}

function makeSender({ sock, axios, getExcuseAudio = async () => null } = {}) {
    return new ResponseSender({
        sock: sock || makeSockMock(),
        axios: axios || makeAxiosMock([]),
        apiUrl: "http://localhost:8000",
        randomDelay: noDelay,
        getExcuseAudio,
        EXCUSE_MSG,
        logger: silentLogger,
    });
}

describe("ResponseSender — construction", () => {
    test("sans axios jette", () => {
        assert.throws(
            () => new ResponseSender({ apiUrl: "x", randomDelay: noDelay, getExcuseAudio: () => null, EXCUSE_MSG }),
            /axios requis/,
        );
    });

    test("sans apiUrl jette", () => {
        assert.throws(
            () => new ResponseSender({ axios: {}, randomDelay: noDelay, getExcuseAudio: () => null, EXCUSE_MSG }),
            /apiUrl requis/,
        );
    });

    test("sans randomDelay (fonction) jette", () => {
        assert.throws(
            () => new ResponseSender({ axios: {}, apiUrl: "x", getExcuseAudio: () => null, EXCUSE_MSG }),
            /randomDelay/,
        );
    });

    test("sans getExcuseAudio jette", () => {
        assert.throws(
            () => new ResponseSender({ axios: {}, apiUrl: "x", randomDelay: noDelay, EXCUSE_MSG }),
            /getExcuseAudio/,
        );
    });

    test("sans EXCUSE_MSG jette", () => {
        assert.throws(
            () => new ResponseSender({ axios: {}, apiUrl: "x", randomDelay: noDelay, getExcuseAudio: () => null }),
            /EXCUSE_MSG/,
        );
    });

    test("sock peut être null à la construction (assigné post-makeWASocket)", () => {
        const rs = new ResponseSender({
            axios: {},
            apiUrl: "x",
            randomDelay: noDelay,
            getExcuseAudio: () => null,
            EXCUSE_MSG,
            logger: silentLogger,
        });
        assert.strictEqual(rs.sock, null);
    });
});

describe("ResponseSender — sendResponse (FRANCAIS)", () => {
    test("texte entrant → 1 message texte FR avec préfixe 🇫🇷", async () => {
        const sock = makeSockMock();
        const rs = makeSender({ sock });
        const prefs = { language: "french" };
        await rs.sendResponse({
            data: { response: "Bonjour" },
            prefs,
            isVoiceInput: false,
            userNumber: "u1",
            saveFn: () => {},
        });
        assert.strictEqual(sock.sent.length, 1);
        assert.match(sock.sent[0].msg.text, /🇫🇷 Bonjour/);
    });

    test("vocal entrant + audio_url → audio FR téléchargé et envoyé", async () => {
        const sock = makeSockMock();
        const audioBuf = Buffer.from("fake-audio");
        const axios = makeAxiosMock([{ data: audioBuf }]);
        const rs = makeSender({ sock, axios });
        await rs.sendResponse({
            data: { response: "Bonjour", audio_url: "/tts/abc.ogg" },
            prefs: { language: "french" },
            isVoiceInput: true,
            userNumber: "u1",
            saveFn: () => {},
        });
        assert.strictEqual(axios.calls[0].url, "http://localhost:8000/tts/abc.ogg");
        assert.strictEqual(sock.sent.length, 1);
        assert.ok(sock.sent[0].msg.audio);
    });

    test("vocal entrant + audio_url absent → fallback texte FR", async () => {
        const sock = makeSockMock();
        const rs = makeSender({ sock });
        await rs.sendResponse({
            data: { response: "Bonjour" },
            prefs: { language: "french" },
            isVoiceInput: true,
            userNumber: "u1",
            saveFn: () => {},
        });
        assert.strictEqual(sock.sent.length, 1);
        assert.match(sock.sent[0].msg.text, /🇫🇷 Bonjour/);
    });

    test("vocal entrant + axios.get échoue → fallback texte FR (pas d'exception propagée)", async () => {
        const sock = makeSockMock();
        const axios = makeAxiosMock([new Error("connect ECONNREFUSED")]);
        const rs = makeSender({ sock, axios });
        await rs.sendResponse({
            data: { response: "Bonjour", audio_url: "/tts/abc.ogg" },
            prefs: { language: "french" },
            isVoiceInput: true,
            userNumber: "u1",
            saveFn: () => {},
        });
        assert.strictEqual(sock.sent.length, 1);
        assert.match(sock.sent[0].msg.text, /🇫🇷 Bonjour/);
    });

    test("audio_url absolu (http://...) → utilisé tel quel", async () => {
        const axios = makeAxiosMock([{ data: Buffer.from("a") }]);
        const rs = makeSender({ axios });
        await rs.sendResponse({
            data: { audio_url: "http://cdn.example.com/x.ogg" },
            prefs: { language: "french" },
            isVoiceInput: true,
            userNumber: "u1",
            saveFn: () => {},
        });
        assert.strictEqual(axios.calls[0].url, "http://cdn.example.com/x.ogg");
    });
});

describe("ResponseSender — sendResponse (DIOULA)", () => {
    test("audio_url présent → audio dioula envoyé (ptt=true)", async () => {
        const sock = makeSockMock();
        const axios = makeAxiosMock([{ data: Buffer.from("dioula-audio") }]);
        const rs = makeSender({ sock, axios });
        await rs.sendResponse({
            data: { response: "ignore", audio_url: "/tts/dy.ogg" },
            prefs: { language: "dioula" },
            isVoiceInput: false,
            userNumber: "u1",
            saveFn: () => {},
        });
        assert.strictEqual(sock.sent.length, 1);
        assert.ok(sock.sent[0].msg.audio);
        assert.strictEqual(sock.sent[0].msg.ptt, true);
    });

    test("audio_url absent + data.response → fallback texte FR (alphabétisés)", async () => {
        const sock = makeSockMock();
        const rs = makeSender({ sock });
        await rs.sendResponse({
            data: { response: "Bonjour" },
            prefs: { language: "dioula" },
            isVoiceInput: false,
            userNumber: "u1",
            saveFn: () => {},
        });
        assert.strictEqual(sock.sent.length, 1);
        assert.match(sock.sent[0].msg.text, /🇫🇷 Bonjour/);
    });

    test("axios.get échoue + data.response → fallback texte FR", async () => {
        const sock = makeSockMock();
        const axios = makeAxiosMock([new Error("TTS API down")]);
        const rs = makeSender({ sock, axios });
        await rs.sendResponse({
            data: { response: "Bonjour", audio_url: "/tts/dy.ogg" },
            prefs: { language: "dioula" },
            isVoiceInput: false,
            userNumber: "u1",
            saveFn: () => {},
        });
        assert.strictEqual(sock.sent.length, 1);
        assert.match(sock.sent[0].msg.text, /🇫🇷 Bonjour/);
    });
});

describe("ResponseSender — sendResponse (BOTH)", () => {
    test("texte FR + audio dioula envoyés (2 messages)", async () => {
        const sock = makeSockMock();
        const axios = makeAxiosMock([{ data: Buffer.from("dy-audio") }]);
        const rs = makeSender({ sock, axios });
        await rs.sendResponse({
            data: { response: "Bonjour", audio_url: "/tts/dy.ogg" },
            prefs: { language: "both" },
            isVoiceInput: false,
            userNumber: "u1",
            saveFn: () => {},
        });
        assert.strictEqual(sock.sent.length, 2);
        assert.match(sock.sent[0].msg.text, /🇫🇷 Bonjour/);
        assert.ok(sock.sent[1].msg.audio);
    });

    test("audio_url absent → seul le texte FR est envoyé", async () => {
        const sock = makeSockMock();
        const rs = makeSender({ sock });
        await rs.sendResponse({
            data: { response: "Bonjour" },
            prefs: { language: "both" },
            isVoiceInput: false,
            userNumber: "u1",
            saveFn: () => {},
        });
        assert.strictEqual(sock.sent.length, 1);
        assert.match(sock.sent[0].msg.text, /🇫🇷 Bonjour/);
    });

    test("axios échoue → texte FR déjà envoyé, pas d'exception propagée", async () => {
        const sock = makeSockMock();
        const axios = makeAxiosMock([new Error("audio down")]);
        const rs = makeSender({ sock, axios });
        await rs.sendResponse({
            data: { response: "Bonjour", audio_url: "/x.ogg" },
            prefs: { language: "both" },
            isVoiceInput: false,
            userNumber: "u1",
            saveFn: () => {},
        });
        assert.strictEqual(sock.sent.length, 1);
        assert.match(sock.sent[0].msg.text, /🇫🇷 Bonjour/);
    });
});

describe("ResponseSender — sendResponse feedback C4", () => {
    test("dioula + data.meta → prompt feedback + mutation step=WAITING_FEEDBACK + saveFn appelé", async () => {
        const sock = makeSockMock();
        const axios = makeAxiosMock([{ data: Buffer.from("a") }]);
        let saveCalls = 0;
        const rs = makeSender({ sock, axios });
        const prefs = { language: "dioula", step: STEPS.COMPLETE };
        await rs.sendResponse({
            data: {
                response: "Réponse FR",
                response_dioula: "Réponse DY",
                audio_url: "/tts/x.ogg",
                meta: { intent: "GREETING", cultures: ["maize"], source: "ivr" },
            },
            prefs,
            isVoiceInput: false,
            userNumber: "u1",
            saveFn: () => { saveCalls++; },
        });
        // 1 audio + 1 prompt feedback
        assert.strictEqual(sock.sent.length, 2);
        assert.match(sock.sent[1].msg.text, /jaabi/);
        assert.strictEqual(prefs.step, STEPS.WAITING_FEEDBACK);
        assert.strictEqual(prefs.pendingFeedback.intent, "GREETING");
        assert.deepStrictEqual(prefs.pendingFeedback.cultures, ["maize"]);
        assert.strictEqual(prefs.pendingFeedback.source, "ivr");
        assert.strictEqual(prefs.pendingFeedback.reponse_bambara, "Réponse DY");
        assert.strictEqual(saveCalls, 1);
    });

    test("both + data.meta → prompt feedback aussi", async () => {
        const sock = makeSockMock();
        const axios = makeAxiosMock([{ data: Buffer.from("a") }]);
        let saveCalls = 0;
        const rs = makeSender({ sock, axios });
        const prefs = { language: "both", step: STEPS.COMPLETE };
        await rs.sendResponse({
            data: { response: "R", audio_url: "/x.ogg", meta: { intent: "X" } },
            prefs,
            isVoiceInput: false,
            userNumber: "u1",
            saveFn: () => { saveCalls++; },
        });
        assert.strictEqual(prefs.step, STEPS.WAITING_FEEDBACK);
        assert.strictEqual(saveCalls, 1);
    });

    test("french + data.meta → PAS de prompt feedback, step inchangé", async () => {
        const sock = makeSockMock();
        let saveCalls = 0;
        const rs = makeSender({ sock });
        const prefs = { language: "french", step: STEPS.COMPLETE };
        await rs.sendResponse({
            data: { response: "Bonjour", meta: { intent: "GREETING" } },
            prefs,
            isVoiceInput: false,
            userNumber: "u1",
            saveFn: () => { saveCalls++; },
        });
        assert.strictEqual(prefs.step, STEPS.COMPLETE);
        assert.strictEqual(saveCalls, 0);
        assert.strictEqual(prefs.pendingFeedback, undefined);
    });

    test("dioula sans data.meta → PAS de prompt feedback", async () => {
        const sock = makeSockMock();
        const axios = makeAxiosMock([{ data: Buffer.from("a") }]);
        let saveCalls = 0;
        const rs = makeSender({ sock, axios });
        const prefs = { language: "dioula", step: STEPS.COMPLETE };
        await rs.sendResponse({
            data: { response: "R", audio_url: "/x.ogg" },
            prefs,
            isVoiceInput: false,
            userNumber: "u1",
            saveFn: () => { saveCalls++; },
        });
        assert.strictEqual(saveCalls, 0);
        assert.strictEqual(prefs.step, STEPS.COMPLETE);
    });
});

describe("ResponseSender — sendExcuse", () => {
    test("FRENCH + texte entrant → texte FR avec préfixe 🇫🇷", async () => {
        const sock = makeSockMock();
        const rs = makeSender({ sock });
        await rs.sendExcuse("u1", { language: "french", kind: "unavailable", isVoiceInput: false });
        assert.strictEqual(sock.sent.length, 1);
        assert.match(sock.sent[0].msg.text, /🇫🇷.*indisponible/i);
    });

    test("FRENCH + vocal + audio disponible → audio FR envoyé", async () => {
        const sock = makeSockMock();
        const rs = makeSender({
            sock,
            getExcuseAudio: async () => Buffer.from("french-excuse-audio"),
        });
        await rs.sendExcuse("u1", { language: "french", kind: "back", isVoiceInput: true });
        assert.strictEqual(sock.sent.length, 1);
        assert.ok(sock.sent[0].msg.audio);
        assert.strictEqual(sock.sent[0].msg.ptt, true);
    });

    test("FRENCH + vocal + audio indispo → fallback texte bilingue", async () => {
        const sock = makeSockMock();
        const rs = makeSender({ sock, getExcuseAudio: async () => null });
        await rs.sendExcuse("u1", { language: "french", kind: "unavailable", isVoiceInput: true });
        assert.strictEqual(sock.sent.length, 1);
        assert.strictEqual(sock.sent[0].msg.text, EXCUSE_MSG.UNAVAILABLE_BILINGUAL);
    });

    test("BOTH → 2 messages : texte FR + audio dioula", async () => {
        const sock = makeSockMock();
        const rs = makeSender({
            sock,
            getExcuseAudio: async () => Buffer.from("dioula-excuse-audio"),
        });
        await rs.sendExcuse("u1", { language: "both", kind: "back" });
        assert.strictEqual(sock.sent.length, 2);
        assert.match(sock.sent[0].msg.text, /🇫🇷/);
        assert.ok(sock.sent[1].msg.audio);
    });

    test("BOTH + audio dioula indispo → seul le texte FR envoyé", async () => {
        const sock = makeSockMock();
        const rs = makeSender({ sock, getExcuseAudio: async () => null });
        await rs.sendExcuse("u1", { language: "both", kind: "unavailable" });
        assert.strictEqual(sock.sent.length, 1);
        assert.match(sock.sent[0].msg.text, /🇫🇷/);
    });

    test("DIOULA + audio disponible → audio dioula envoyé", async () => {
        const sock = makeSockMock();
        const rs = makeSender({
            sock,
            getExcuseAudio: async () => Buffer.from("dy-audio"),
        });
        await rs.sendExcuse("u1", { language: "dioula", kind: "back" });
        assert.strictEqual(sock.sent.length, 1);
        assert.ok(sock.sent[0].msg.audio);
    });

    test("DIOULA + audio indispo → fallback texte bilingue", async () => {
        const sock = makeSockMock();
        const rs = makeSender({ sock, getExcuseAudio: async () => null });
        await rs.sendExcuse("u1", { language: "dioula", kind: "unavailable" });
        assert.strictEqual(sock.sent.length, 1);
        assert.strictEqual(sock.sent[0].msg.text, EXCUSE_MSG.UNAVAILABLE_BILINGUAL);
    });
});
