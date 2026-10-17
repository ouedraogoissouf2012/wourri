/**
 * #477 / ADR-0043 — le baoulé, langue ANNONCÉE.
 *
 * L'agriculteur peut choisir le baoulé ; Wourri ne le comprend pas encore et
 * le sert donc en français, en le disant honnêtement. Ces tests vérifient le
 * contrat de bout en bout côté serveur WhatsApp :
 *   - menu et onboarding (choix « 5 », « baoulé », « bci ») ;
 *   - aucun texte baoulé inventé ;
 *   - appel /api/chat/ dans la langue de repli (l'API ne connaît pas « baoule » :
 *     un 422 polluerait le circuit breaker de TOUS les utilisateurs) ;
 *   - un vocal n'est pas envoyé à Whisper FR (transcription fausse) ;
 *   - réponses et excuses servies en français, jamais en audio dioula ;
 *   - la préférence est comptée sous « bci » (mesure de la demande).
 */
"use strict";

const { test, describe } = require("node:test");
const assert = require("node:assert/strict");

const i18n = require("../lib/i18n");
const { MSG, pickMsg, contentLanguage, isPendingLanguage, LANGUAGE_LABELS } = i18n;
const { OnboardingMachine } = require("../lib/onboarding");
const { UserPrefs, STEPS } = require("../lib/user_prefs");
const { createMessageHandler } = require("../lib/message_handler");
const { ResponseSender } = require("../lib/response_sender");
const { mapLanguage } = require("../lib/ingest_event");
const { silentLogger, noDelay, makeSockMock, makeFsMock } = require("./_helpers");

// ─────────────────────────────────────────────────────────────────────
// i18n
// ─────────────────────────────────────────────────────────────────────

describe("#477 i18n — langue annoncée", () => {
    test("baoule est choisissable mais servi en français", () => {
        assert.ok(i18n.SUPPORTED_LANGUAGES.includes("baoule"));
        assert.equal(isPendingLanguage("baoule"), true);
        assert.equal(contentLanguage("baoule"), "french");
        assert.equal(LANGUAGE_LABELS.baoule, "Baoulé");
    });

    test("les langues servies ne sont pas des langues annoncées", () => {
        for (const lang of ["french", "dioula", "both", "english"]) {
            assert.equal(isPendingLanguage(lang), false, lang);
            assert.equal(contentLanguage(lang), lang, lang);
        }
        assert.equal(isPendingLanguage(undefined), false);
        assert.equal(contentLanguage(undefined), undefined);
    });

    test("baoule n'exige pas de variant propre (emprunte le français)", () => {
        assert.ok(!i18n.LANGUAGES_REQUIRING_VARIANT.includes("baoule"));
        assert.doesNotThrow(() => i18n.validateI18nCompleteness());
        for (const key of i18n.REQUIRED_VARIANT_KEYS) {
            assert.equal(pickMsg(MSG[key], "baoule"), MSG[key].french, key);
        }
    });

    test("les trois menus proposent l'option 5 Baoulé", () => {
        assert.match(MSG.CITY_OK("Abidjan"), /5️⃣ Baoulé/);
        assert.match(MSG.CITY_OK("Abidjan"), /1, 2, 3, 4 wala 5 ci/);
        assert.match(MSG.LANGUAGE_UNKNOWN, /5️⃣ Baoulé/);
        assert.match(MSG.LANGUAGE_UNKNOWN, /Répondez 1, 2, 3, 4 ou 5/);
        for (const variant of ["bilingual", "french", "dioula", "english"]) {
            assert.match(MSG.CHANGE_LANGUAGE[variant], /5️⃣ Baoulé/, variant);
        }
    });

    test("PREFS_SAVED baoule : confirme ET dit honnêtement que ce n'est pas encore servi", () => {
        const text = MSG.PREFS_SAVED("Bouaké", "Baoulé", "baoule");
        assert.match(text, /Préférences enregistrées/);
        assert.match(text, /Langue : Baoulé/);
        assert.match(text, /ne parle pas encore Baoulé/);
        assert.match(text, /je vous réponds en français/);
        // Ni dioula ni texte « en baoulé » : seul le mot « Baoulé » (libellé).
        assert.ok(!text.includes("Dɔ sɔrɔla"));
    });

    test("VOICE_UNAVAILABLE nomme la langue et propose une issue", () => {
        const text = MSG.VOICE_UNAVAILABLE("Baoulé");
        assert.match(text, /messages vocaux en Baoulé/);
        assert.match(text, /Écrivez votre question en français/);
        assert.match(text, /changer langue/);
    });
});

// ─────────────────────────────────────────────────────────────────────
// Onboarding
// ─────────────────────────────────────────────────────────────────────

function makeMachine(sock) {
    const userPrefs = new UserPrefs({ fs: makeFsMock(), filePath: "/tmp/prefs.json", logger: silentLogger });
    return new OnboardingMachine({
        userPrefs,
        axios: { post: async () => ({ status: 200, data: {} }) },
        apiUrl: "http://localhost:8000",
        authHeaders: () => ({}),
        randomDelay: noDelay,
        sock,
        logger: silentLogger,
    });
}

describe("#477 onboarding — choisir le baoulé", () => {
    for (const input of ["5", "baoulé", "Baoule", "bci"]) {
        test(`input '${input}' → language=baoule, step=COMPLETE, confirmation honnête`, async () => {
            const sock = makeSockMock();
            const prefs = { step: STEPS.WAITING_LANGUAGE, city: "Bouaké", language: null, pendingQuestion: null };
            const result = await makeMachine(sock).processStep(prefs, input, "u1", { isAudioMessage: false, isVoiceInput: false });
            assert.equal(result.handled, true);
            assert.equal(prefs.language, "baoule");
            assert.equal(prefs.step, STEPS.COMPLETE);
            assert.match(sock.sent[0].msg.text, /ne parle pas encore Baoulé/);
        });
    }

    test("les choix 1 à 4 restent inchangés", async () => {
        const expected = { 1: "french", 2: "dioula", 3: "both", 4: "english" };
        for (const [input, language] of Object.entries(expected)) {
            const prefs = { step: STEPS.WAITING_LANGUAGE, city: "Abidjan", language: null, pendingQuestion: null };
            await makeMachine(makeSockMock()).processStep(prefs, input, "u1", { isAudioMessage: false, isVoiceInput: false });
            assert.equal(prefs.language, language, input);
        }
    });
});

// ─────────────────────────────────────────────────────────────────────
// message_handler
// ─────────────────────────────────────────────────────────────────────

function makeHandlerDeps(language) {
    const sock = makeSockMock();
    sock.readMessages = async () => {};
    sock.updateMediaMessage = async () => {};
    const asrCalls = [];
    const apiCalls = [];
    const queued = [];
    const deps = {
        sock,
        logger: silentLogger,
        asrClient: {
            transcribeAudio: async () => { asrCalls.push("whisper"); return { text: "bonjour" }; },
            transcribeAudioBambara: async () => { asrCalls.push("bambara"); return { text: "i ni ce" }; },
        },
        responseSender: { sendResponse: async () => {}, sendExcuse: async () => {} },
        userPrefs: { get: () => ({ step: STEPS.COMPLETE, city: "Bouaké", language }), save: () => {} },
        onboardingMachine: { processStep: async () => ({ handled: null }) },
        messageQueue: {
            add: async (e) => { queued.push(e); },
            markSuccess: async () => {},
            markFailure: async () => {},
        },
        apiCircuitBreaker: { execute: async (fn) => fn() },
        apiUrl: "http://localhost:8000",
        MSG,
        STEPS,
        authHeaders: () => ({}),
        isApiHealthy: async () => true,
        pickMsg,
        randomDelay: noDelay,
        downloadMediaMessage: async () => Buffer.from("audio"),
        pino: () => silentLogger,
        axios: { post: async (url, body) => { apiCalls.push({ url, body }); return { data: { response: "ok" } }; } },
        CircuitOpenError: class extends Error {},
    };
    return { deps, asrCalls, apiCalls, queued };
}

function makeMsg({ text, audio } = {}) {
    const message = {};
    if (text) message.conversation = text;
    if (audio) message.audioMessage = audio;
    return { key: { fromMe: false, remoteJid: "u1@s.whatsapp.net", id: "wamsg_477" }, message };
}

describe("#477 message_handler — utilisateur en baoulé", () => {
    test("message texte : /api/chat/ appelé en french, préférence baoule conservée en queue", async () => {
        const { deps, apiCalls, queued } = makeHandlerDeps("baoule");
        await createMessageHandler(deps)({ messages: [makeMsg({ text: "Quand planter le cacao ?" })] });
        assert.equal(apiCalls.length, 1);
        assert.equal(apiCalls[0].body.language, "french");
        assert.equal(queued[0].payload.language, "baoule");
    });

    test("message vocal : ni Whisper ni ASR bambara, message d'attente honnête, pas d'appel API", async () => {
        const { deps, asrCalls, apiCalls } = makeHandlerDeps("baoule");
        await createMessageHandler(deps)({ messages: [makeMsg({ audio: { url: "http://x", mediaKey: "k" } })] });
        assert.deepEqual(asrCalls, []);
        assert.equal(apiCalls.length, 0);
        const texts = deps.sock.sent.map((s) => s.msg.text);
        assert.ok(texts.some((t) => /messages vocaux en Baoulé/.test(t)), texts.join(" | "));
    });

    test("non-régression : un utilisateur french garde Whisper et language=french", async () => {
        const { deps, asrCalls, apiCalls } = makeHandlerDeps("french");
        await createMessageHandler(deps)({ messages: [makeMsg({ audio: { url: "http://x", mediaKey: "k" } })] });
        assert.deepEqual(asrCalls, ["whisper"]);
        assert.equal(apiCalls[0].body.language, "french");
    });
});

// ─────────────────────────────────────────────────────────────────────
// response_sender
// ─────────────────────────────────────────────────────────────────────

const EXCUSE_MSG = {
    UNAVAILABLE_FR: "Problème technique.",
    UNAVAILABLE_DIOULA: "N bɛ baara la sisan.",
    UNAVAILABLE_BILINGUAL: "BILINGUE indispo",
    UNAVAILABLE_EN: "Technical problem.",
    BACK_FR: "De retour.",
    BACK_DIOULA: "N nana segin.",
    BACK_BILINGUAL: "BILINGUE retour",
    BACK_EN: "I'm back.",
};

function makeSender(sock, excuseAudioCalls) {
    return new ResponseSender({
        sock,
        axios: { get: async () => { throw new Error("pas d'audio attendu"); } },
        apiUrl: "http://localhost:8000",
        randomDelay: noDelay,
        getExcuseAudio: async (opts) => { excuseAudioCalls.push(opts); return Buffer.from("audio"); },
        EXCUSE_MSG,
        logger: silentLogger,
    });
}

describe("#477 response_sender — servi en français, jamais en audio dioula", () => {
    test("réponse : texte français, pas de prompt feedback dioula", async () => {
        const sock = makeSockMock();
        const prefs = { language: "baoule", step: STEPS.COMPLETE };
        await makeSender(sock, []).sendResponse({
            data: { response: "Plantez en début de saison des pluies.", meta: { intent: "x" } },
            prefs, isVoiceInput: false, userNumber: "u1", saveFn: () => {},
        });
        assert.equal(sock.sent.length, 1);
        assert.match(sock.sent[0].msg.text, /^🇫🇷 Plantez/);
        assert.equal(prefs.language, "baoule", "la préférence n'est pas réécrite");
        assert.equal(prefs.step, STEPS.COMPLETE, "pas d'attente de feedback 👍/👎 dioula");
    });

    test("excuse baoule : texte français, aucun audio", async () => {
        const sock = makeSockMock();
        const audio = [];
        await makeSender(sock, audio).sendExcuse("u1", { language: "baoule", kind: "unavailable" });
        assert.deepEqual(audio, []);
        assert.match(sock.sent[0].msg.text, /Problème technique/);
    });

    test("excuse english : texte anglais, plus d'audio dioula (bug corrigé)", async () => {
        const sock = makeSockMock();
        const audio = [];
        await makeSender(sock, audio).sendExcuse("u1", { language: "english", kind: "back" });
        assert.deepEqual(audio, []);
        assert.equal(sock.sent.length, 1);
        assert.match(sock.sent[0].msg.text, /^🇬🇧 I'm back\./);
    });

    test("excuse langue inconnue : texte bilingue, jamais l'audio dioula par défaut", async () => {
        const sock = makeSockMock();
        const audio = [];
        await makeSender(sock, audio).sendExcuse("u1", { language: "xx", kind: "unavailable" });
        assert.deepEqual(audio, []);
        assert.equal(sock.sent[0].msg.text, "BILINGUE indispo");
    });

    test("non-régression : excuse dioula garde l'audio dioula", async () => {
        const sock = makeSockMock();
        const audio = [];
        await makeSender(sock, audio).sendExcuse("u1", { language: "dioula", kind: "unavailable" });
        assert.deepEqual(audio, [{ kind: "unavailable", isFrench: false }]);
        assert.ok(sock.sent[0].msg.audio);
    });
});

// ─────────────────────────────────────────────────────────────────────
// ingest_event
// ─────────────────────────────────────────────────────────────────────

describe("#477 ingest_event — mesure de la demande", () => {
    test("baoule est compté sous son code ISO 639-3 bci", () => {
        assert.equal(mapLanguage("baoule"), "bci");
        assert.equal(mapLanguage("dioula"), "dyu");
    });
});
