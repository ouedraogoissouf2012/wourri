/**
 * Tests unitaires pour OnboardingMachine.
 * Exécution : node --test tests/onboarding.test.js
 *
 * Couvre les 5 chemins de processStep() :
 *   - STEPS.COMPLETE pass-through
 *   - Commandes city/language/reset (uniquement depuis COMPLETE)
 *   - STEPS.NEW
 *   - STEPS.WAITING_CITY
 *   - STEPS.WAITING_LANGUAGE (avec et sans pendingQuestion)
 *   - STEPS.WAITING_FEEDBACK (texte 👍/👎 ou vocal qui annule)
 *
 * Mocks injectés : sock (capture sendMessage + sendPresenceUpdate), userPrefs
 * (instance réelle avec mock fs minimal), axios (réponses scriptées feedback).
 */
"use strict";

const { test, describe, beforeEach } = require("node:test");
const assert = require("node:assert");
const { OnboardingMachine } = require("../lib/onboarding");
const { UserPrefs, STEPS } = require("../lib/user_prefs");
const { silentLogger, noDelay, makeSockMock, makeFsMock } = require("./_helpers");

// Note : makeAxiosMock reste local — méthode .post spécifique à onboarding (feedback).
// Pour la version .get (response_sender, audio download), voir tests/response_sender.test.js.
function makeAxiosMock(responses = []) {
    const calls = [];
    let idx = 0;
    return {
        calls,
        post: async (url, body, opts) => {
            calls.push({ url, body, opts });
            const r = responses[idx++];
            if (r instanceof Error) throw r;
            return r || { status: 200, data: {} };
        },
    };
}

function makeUserPrefs() {
    const fs = makeFsMock();
    const userPrefs = new UserPrefs({
        fs,
        filePath: "/tmp/prefs.json",
        logger: silentLogger,
    });
    return { userPrefs, fs };
}

function makeMachine({ sock, axios } = {}) {
    const { userPrefs } = makeUserPrefs();
    return new OnboardingMachine({
        userPrefs,
        axios: axios || makeAxiosMock(),
        apiUrl: "http://localhost:8000",
        authHeaders: () => ({ "X-API-Key": "test-key" }),
        randomDelay: noDelay,
        sock: sock || makeSockMock(),
        logger: silentLogger,
    });
}

describe("OnboardingMachine — construction", () => {
    test("sans userPrefs jette", () => {
        assert.throws(
            () => new OnboardingMachine({ axios: {}, apiUrl: "x", authHeaders: () => ({}), randomDelay: noDelay }),
            /userPrefs requis/,
        );
    });
    test("sans axios jette", () => {
        const { userPrefs } = makeUserPrefs();
        assert.throws(
            () => new OnboardingMachine({ userPrefs, apiUrl: "x", authHeaders: () => ({}), randomDelay: noDelay }),
            /axios requis/,
        );
    });
    test("sans apiUrl jette", () => {
        const { userPrefs } = makeUserPrefs();
        assert.throws(
            () => new OnboardingMachine({ userPrefs, axios: {}, authHeaders: () => ({}), randomDelay: noDelay }),
            /apiUrl requis/,
        );
    });
    test("sans authHeaders (function) jette", () => {
        const { userPrefs } = makeUserPrefs();
        assert.throws(
            () => new OnboardingMachine({ userPrefs, axios: {}, apiUrl: "x", randomDelay: noDelay }),
            /authHeaders/,
        );
    });
    test("sans randomDelay jette", () => {
        const { userPrefs } = makeUserPrefs();
        assert.throws(
            () => new OnboardingMachine({ userPrefs, axios: {}, apiUrl: "x", authHeaders: () => ({}) }),
            /randomDelay/,
        );
    });
    test("sock peut être null à la construction", () => {
        const { userPrefs } = makeUserPrefs();
        const m = new OnboardingMachine({
            userPrefs, axios: {}, apiUrl: "x",
            authHeaders: () => ({}), randomDelay: noDelay,
            logger: silentLogger,
        });
        assert.strictEqual(m.sock, null);
    });
});

describe("OnboardingMachine — guard sock null (Pattern 12 review D.3)", () => {
    test("sock=null → handled=true + log warn, aucun appel sock", async () => {
        const { userPrefs } = makeUserPrefs();
        const warnings = [];
        const m = new OnboardingMachine({
            userPrefs,
            axios: makeAxiosMock(),
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({}),
            randomDelay: noDelay,
            sock: null,
            logger: { ...silentLogger, warn: (msg) => warnings.push(msg) },
        });
        const prefs = { step: STEPS.NEW, language: null, city: null, pendingQuestion: null };
        const result = await m.processStep(prefs, "bonjour", "u1", { isAudioMessage: false, isVoiceInput: false });
        assert.strictEqual(result.handled, true);
        assert.strictEqual(warnings.length, 1);
        assert.match(warnings[0], /sock non initialisé/);
        // Step inchangé : la machine n'a pas pu agir
        assert.strictEqual(prefs.step, STEPS.NEW);
    });
});

describe("OnboardingMachine — STEPS.COMPLETE (pass-through)", () => {
    test("retourne { handled: null } sans rien envoyer", async () => {
        const sock = makeSockMock();
        const m = makeMachine({ sock });
        const prefs = { step: STEPS.COMPLETE, language: "french" };
        const result = await m.processStep(prefs, "bonjour", "u1", { isAudioMessage: false, isVoiceInput: false });
        assert.strictEqual(result.handled, null);
        assert.strictEqual(sock.sent.length, 0);
    });
});

describe("OnboardingMachine — STEPS.NEW", () => {
    test("enregistre pendingQuestion + step=WAITING_CITY + envoie WELCOME", async () => {
        const sock = makeSockMock();
        const m = makeMachine({ sock });
        const prefs = { step: STEPS.NEW, language: null, city: null, pendingQuestion: null };
        const result = await m.processStep(prefs, "bonjour comment ça va", "u1", { isAudioMessage: false, isVoiceInput: false });
        assert.strictEqual(result.handled, true);
        assert.strictEqual(prefs.step, STEPS.WAITING_CITY);
        assert.strictEqual(prefs.pendingQuestion, "bonjour comment ça va");
        assert.strictEqual(sock.sent.length, 1);
        assert.match(sock.sent[0].msg.text, /WOURI|Bienvenue/);
    });
});

describe("OnboardingMachine — STEPS.WAITING_CITY", () => {
    test("extrait la ville + step=WAITING_LANGUAGE + envoie CITY_OK", async () => {
        const sock = makeSockMock();
        const m = makeMachine({ sock });
        const prefs = { step: STEPS.WAITING_CITY, city: null, language: null };
        const result = await m.processStep(prefs, "je suis à Abidjan", "u1", { isAudioMessage: false, isVoiceInput: false });
        assert.strictEqual(result.handled, true);
        assert.strictEqual(prefs.city, "Abidjan");
        assert.strictEqual(prefs.step, STEPS.WAITING_LANGUAGE);
        assert.strictEqual(sock.sent.length, 1);
        assert.match(sock.sent[0].msg.text, /Abidjan/);
    });

    test("fallback dernier mot si ville inconnue", async () => {
        const m = makeMachine();
        const prefs = { step: STEPS.WAITING_CITY, city: null, language: null };
        await m.processStep(prefs, "village inconnu", "u1", { isAudioMessage: false, isVoiceInput: false });
        // extractCity fallback : dernier mot >3 chars capitalisé
        assert.strictEqual(prefs.city, "Inconnu");
    });
});

describe("OnboardingMachine — STEPS.WAITING_LANGUAGE", () => {
    test("input '1' → language=french, step=COMPLETE, envoie PREFS_SAVED", async () => {
        const sock = makeSockMock();
        const m = makeMachine({ sock });
        const prefs = { step: STEPS.WAITING_LANGUAGE, city: "Abidjan", language: null, pendingQuestion: null };
        const result = await m.processStep(prefs, "1", "u1", { isAudioMessage: false, isVoiceInput: false });
        assert.strictEqual(result.handled, true);
        assert.strictEqual(prefs.language, "french");
        assert.strictEqual(prefs.step, STEPS.COMPLETE);
        assert.match(sock.sent[0].msg.text, /Faransi/);
    });

    test("input '2' → language=dioula", async () => {
        const m = makeMachine();
        const prefs = { step: STEPS.WAITING_LANGUAGE, city: "Bouake", language: null, pendingQuestion: null };
        const result = await m.processStep(prefs, "2", "u1", { isAudioMessage: false, isVoiceInput: false });
        assert.strictEqual(result.handled, true);
        assert.strictEqual(prefs.language, "dioula");
        assert.strictEqual(prefs.step, STEPS.COMPLETE);
    });

    test("input '3' → language=both", async () => {
        const m = makeMachine();
        const prefs = { step: STEPS.WAITING_LANGUAGE, city: "Divo", language: null, pendingQuestion: null };
        const result = await m.processStep(prefs, "3", "u1", { isAudioMessage: false, isVoiceInput: false });
        assert.strictEqual(result.handled, true);
        assert.strictEqual(prefs.language, "both");
    });

    test("input 'français' (mot complet) → language=french", async () => {
        const m = makeMachine();
        const prefs = { step: STEPS.WAITING_LANGUAGE, city: "Korhogo", language: null, pendingQuestion: null };
        await m.processStep(prefs, "français svp", "u1", { isAudioMessage: false, isVoiceInput: false });
        assert.strictEqual(prefs.language, "french");
    });

    test("input invalide → envoie LANGUAGE_UNKNOWN, step inchangé", async () => {
        const sock = makeSockMock();
        const m = makeMachine({ sock });
        const prefs = { step: STEPS.WAITING_LANGUAGE, city: "Man", language: null, pendingQuestion: null };
        const result = await m.processStep(prefs, "oui peut-être", "u1", { isAudioMessage: false, isVoiceInput: false });
        assert.strictEqual(result.handled, true);
        assert.strictEqual(prefs.step, STEPS.WAITING_LANGUAGE);
        assert.strictEqual(prefs.language, null);
        assert.match(sock.sent[0].msg.text, /faamu|compris/i);
    });

    test("avec pendingQuestion → { handled: false, newMessageText } + pendingQuestion vidée", async () => {
        const sock = makeSockMock();
        const m = makeMachine({ sock });
        const prefs = {
            step: STEPS.WAITING_LANGUAGE,
            city: "Bouake",
            language: null,
            pendingQuestion: "comment planter le maïs en saison sèche ?",
        };
        const result = await m.processStep(prefs, "3", "u1", { isAudioMessage: false, isVoiceInput: false });
        assert.strictEqual(result.handled, false);
        assert.strictEqual(result.newMessageText, "comment planter le maïs en saison sèche ?");
        assert.strictEqual(prefs.pendingQuestion, null);
        assert.strictEqual(prefs.step, STEPS.COMPLETE);
        assert.strictEqual(prefs.language, "both");
        // PREFS_SAVED envoyé
        assert.strictEqual(sock.sent.length, 1);
    });
});

describe("OnboardingMachine — commandes (depuis STEPS.COMPLETE uniquement)", () => {
    test("'changer ville' depuis COMPLETE → step=WAITING_CITY", async () => {
        const sock = makeSockMock();
        const m = makeMachine({ sock });
        const prefs = { step: STEPS.COMPLETE, city: "Abidjan", language: "french" };
        const result = await m.processStep(prefs, "changer ville", "u1", { isAudioMessage: false, isVoiceInput: false });
        assert.strictEqual(result.handled, true);
        assert.strictEqual(prefs.step, STEPS.WAITING_CITY);
        assert.match(sock.sent[0].msg.text, /ville|dugu/i);
    });

    test("'changer langue' depuis COMPLETE → step=WAITING_LANGUAGE", async () => {
        const m = makeMachine();
        const prefs = { step: STEPS.COMPLETE, city: "Divo", language: "dioula" };
        const result = await m.processStep(prefs, "changer langue", "u1", { isAudioMessage: false, isVoiceInput: false });
        assert.strictEqual(result.handled, true);
        assert.strictEqual(prefs.step, STEPS.WAITING_LANGUAGE);
    });

    test("'reset' depuis COMPLETE → tout reset à NEW", async () => {
        // Note : detectChangeCommand attend "reinitialiser" sans accent (comportement
        // pré-existant dans lib/i18n.js, à corriger en sprint futur si besoin).
        const m = makeMachine();
        const prefs = {
            step: STEPS.COMPLETE,
            city: "Korhogo",
            language: "both",
            pendingQuestion: "vieille question",
        };
        const result = await m.processStep(prefs, "reinitialiser", "u1", { isAudioMessage: false, isVoiceInput: false });
        assert.strictEqual(result.handled, true);
        assert.strictEqual(prefs.step, STEPS.NEW);
        assert.strictEqual(prefs.city, null);
        assert.strictEqual(prefs.language, null);
        assert.strictEqual(prefs.pendingQuestion, null);
    });

    test("commande 'changer ville' depuis WAITING_CITY → traité comme nouvelle ville (pas comme commande)", async () => {
        // C'est le comportement attendu : detectChangeCommand ne s'active qu'avec
        // prefs.step === COMPLETE, donc depuis WAITING_CITY, "changer ville" est
        // traité comme un nom de ville (extractCity → fallback dernier mot).
        const m = makeMachine();
        const prefs = { step: STEPS.WAITING_CITY, city: null, language: null };
        const result = await m.processStep(prefs, "changer ville", "u1", { isAudioMessage: false, isVoiceInput: false });
        assert.strictEqual(result.handled, true);
        assert.strictEqual(prefs.step, STEPS.WAITING_LANGUAGE);
        // extractCity sur "changer ville" → fallback = "Ville" (dernier mot >3 chars capitalisé)
        assert.strictEqual(prefs.city, "Ville");
    });
});

describe("OnboardingMachine — STEPS.WAITING_FEEDBACK", () => {
    test("'👍' → axios.post positif + step=COMPLETE + pendingFeedback=null", async () => {
        const sock = makeSockMock();
        const axios = makeAxiosMock([{ status: 200, data: {} }]);
        const m = makeMachine({ sock, axios });
        const prefs = {
            step: STEPS.WAITING_FEEDBACK,
            language: "dioula",
            pendingFeedback: { intent: "SALUTATION", cultures: [], source: "ivr_exact", reponse_bambara: "...", reponse_fr: "..." },
        };
        const result = await m.processStep(prefs, "👍", "u1", { isAudioMessage: false, isVoiceInput: false });
        assert.strictEqual(result.handled, true);
        assert.strictEqual(prefs.step, STEPS.COMPLETE);
        assert.strictEqual(prefs.pendingFeedback, null);
        assert.strictEqual(axios.calls.length, 1);
        assert.match(axios.calls[0].url, /\/feedback\/positif$/);
        assert.match(sock.sent[0].msg.text, /Aw ni ce|🙏/);
    });

    test("'👎' → axios.post negatif + confirmation appropriée", async () => {
        const sock = makeSockMock();
        const axios = makeAxiosMock([{ status: 200, data: {} }]);
        const m = makeMachine({ sock, axios });
        const prefs = {
            step: STEPS.WAITING_FEEDBACK,
            language: "both",
            pendingFeedback: { intent: "CONSEIL", cultures: [], source: "deepseek", reponse_bambara: "", reponse_fr: "" },
        };
        const result = await m.processStep(prefs, "👎", "u1", { isAudioMessage: false, isVoiceInput: false });
        assert.strictEqual(result.handled, true);
        assert.match(axios.calls[0].url, /\/feedback\/negatif$/);
        assert.match(sock.sent[0].msg.text, /faamu|🙏/);
    });

    test("texte invalide → re-demande 'jaabi 👍 wala 👎'", async () => {
        const sock = makeSockMock();
        const m = makeMachine({ sock });
        const prefs = { step: STEPS.WAITING_FEEDBACK, pendingFeedback: { intent: "X" } };
        const result = await m.processStep(prefs, "peut-être", "u1", { isAudioMessage: false, isVoiceInput: false });
        assert.strictEqual(result.handled, true);
        // Le step reste COMPLETE après cette branche (comportement actuel du handler)
        assert.strictEqual(prefs.step, STEPS.COMPLETE);
        assert.match(sock.sent[0].msg.text, /jaabi.*👍.*👎/);
    });

    test("vocal pendant feedback → annule feedback, retourne { handled: false, newMessageText }", async () => {
        const sock = makeSockMock();
        const m = makeMachine({ sock });
        const prefs = {
            step: STEPS.WAITING_FEEDBACK,
            pendingFeedback: { intent: "X" },
        };
        const result = await m.processStep(prefs, "voici ma nouvelle question vocale", "u1", { isAudioMessage: false, isVoiceInput: true });
        assert.strictEqual(result.handled, false);
        assert.strictEqual(result.newMessageText, "voici ma nouvelle question vocale");
        assert.strictEqual(prefs.step, STEPS.COMPLETE);
        assert.strictEqual(prefs.pendingFeedback, null);
        // Aucun message envoyé dans ce cas (le handler poursuit avec STEPS.COMPLETE)
        assert.strictEqual(sock.sent.length, 0);
    });

    test("erreur axios feedback → log warn, poursuit le retour à COMPLETE sans throw", async () => {
        const sock = makeSockMock();
        const axios = makeAxiosMock([new Error("connect ECONNREFUSED")]);
        const warnings = [];
        const m = makeMachine({ sock, axios });
        m.logger = { ...silentLogger, warn: (msg) => warnings.push(msg) };
        const prefs = {
            step: STEPS.WAITING_FEEDBACK,
            pendingFeedback: { intent: "X" },
        };
        const result = await m.processStep(prefs, "👍", "u1", { isAudioMessage: false, isVoiceInput: false });
        // Pas d'exception levée
        assert.strictEqual(result.handled, true);
        assert.strictEqual(prefs.step, STEPS.COMPLETE);
        assert.ok(warnings.length >= 1, "warning émis pour erreur API feedback");
    });

    test("authHeaders() appelé à chaque post (header dynamique)", async () => {
        const sock = makeSockMock();
        const axios = makeAxiosMock([{ status: 200, data: {} }]);
        let authCallCount = 0;
        const { userPrefs } = makeUserPrefs();
        const m = new OnboardingMachine({
            userPrefs,
            axios,
            apiUrl: "http://localhost:8000",
            authHeaders: () => { authCallCount++; return { "X-API-Key": "dyn" }; },
            randomDelay: noDelay,
            sock,
            logger: silentLogger,
        });
        const prefs = {
            step: STEPS.WAITING_FEEDBACK,
            pendingFeedback: { intent: "X" },
        };
        await m.processStep(prefs, "👍", "u1", { isAudioMessage: false, isVoiceInput: false });
        assert.strictEqual(authCallCount, 1);
        assert.strictEqual(axios.calls[0].opts.headers["X-API-Key"], "dyn");
    });
});
