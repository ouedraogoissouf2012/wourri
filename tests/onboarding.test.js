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

    test("ville non reconnue → redemande sans avancer (CITY_UNKNOWN)", async () => {
        const sock = makeSockMock();
        const m = makeMachine({ sock });
        const prefs = { step: STEPS.WAITING_CITY, city: null, language: null };
        const result = await m.processStep(prefs, "village inconnu", "u1", { isAudioMessage: false, isVoiceInput: false });
        // Fix cafard démo : on n'accepte plus un mot au hasard comme ville.
        // La ville n'est pas validée → on reste à WAITING_CITY et on redemande.
        assert.strictEqual(result.handled, true);
        assert.strictEqual(prefs.city, null, "ville non reconnue ne doit pas etre enregistree");
        assert.strictEqual(prefs.step, STEPS.WAITING_CITY, "reste a l'etape ville");
        assert.match(sock.sent[0].msg.text, /reconnais pas|dɔn/i);
    });

    test("emoji seul → redemande sans accepter comme ville", async () => {
        const sock = makeSockMock();
        const m = makeMachine({ sock });
        const prefs = { step: STEPS.WAITING_CITY, city: null, language: null };
        await m.processStep(prefs, "👍", "u1", { isAudioMessage: false, isVoiceInput: false });
        assert.strictEqual(prefs.city, null);
        assert.strictEqual(prefs.step, STEPS.WAITING_CITY);
    });
});

describe("OnboardingMachine — STEPS.WAITING_LANGUAGE", () => {
    test("input '1' → language=french, step=COMPLETE, envoie PREFS_SAVED en FR pur", async () => {
        const sock = makeSockMock();
        const m = makeMachine({ sock });
        const prefs = { step: STEPS.WAITING_LANGUAGE, city: "Abidjan", language: null, pendingQuestion: null };
        const result = await m.processStep(prefs, "1", "u1", { isAudioMessage: false, isVoiceInput: false });
        assert.strictEqual(result.handled, true);
        assert.strictEqual(prefs.language, "french");
        assert.strictEqual(prefs.step, STEPS.COMPLETE);
        // ADR-0015 + i18n variants : mode FR pur affiche "Préférences enregistrées"
        // (le mot "Faransi" qui apparaissait avant etait du dioula — incoherent)
        assert.match(sock.sent[0].msg.text, /Préférences enregistrées/);
        assert.match(sock.sent[0].msg.text, /Ville : Abidjan/);
        // Ne doit PAS contenir le dioula (mode FR pur, pas bilingue)
        assert.ok(!sock.sent[0].msg.text.includes("Dɔ sɔrɔla"),
            "Mode FR pur ne doit pas contenir du dioula");
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

    test("[ADR-0015 PR 4/4] input '4' → language=english", async () => {
        const m = makeMachine();
        const prefs = { step: STEPS.WAITING_LANGUAGE, city: "Abidjan", language: null, pendingQuestion: null };
        const result = await m.processStep(prefs, "4", "u1", { isAudioMessage: false, isVoiceInput: false });
        assert.strictEqual(result.handled, true);
        assert.strictEqual(prefs.language, "english");
        assert.strictEqual(prefs.step, STEPS.COMPLETE);
    });

    test("[i18n english variants] input '4' → confirmation PREFS_SAVED en EN pur", async () => {
        const sock = makeSockMock();
        const m = makeMachine({ sock });
        const prefs = { step: STEPS.WAITING_LANGUAGE, city: "Bouake", language: null, pendingQuestion: null };
        await m.processStep(prefs, "4", "u1", { isAudioMessage: false, isVoiceInput: false });
        assert.match(sock.sent[0].msg.text, /Preferences saved/);
        assert.match(sock.sent[0].msg.text, /City: Bouake/);
        assert.match(sock.sent[0].msg.text, /Language: English/);
        // Ne doit PAS contenir le dioula ou le francais (mode EN pur)
        assert.ok(!sock.sent[0].msg.text.includes("Dɔ sɔrɔla"),
            "Mode EN pur ne doit pas contenir du dioula");
        assert.ok(!sock.sent[0].msg.text.includes("Préférences enregistrées"),
            "Mode EN pur ne doit pas contenir du francais");
    });

    test("[ADR-0015 PR 4/4] input 'english' (mot complet) → language=english", async () => {
        const m = makeMachine();
        const prefs = { step: STEPS.WAITING_LANGUAGE, city: "Bouake", language: null, pendingQuestion: null };
        await m.processStep(prefs, "english please", "u1", { isAudioMessage: false, isVoiceInput: false });
        assert.strictEqual(prefs.language, "english");
    });

    test("[ADR-0015 PR 4/4] input 'anglais' (mot FR) → language=english", async () => {
        const m = makeMachine();
        const prefs = { step: STEPS.WAITING_LANGUAGE, city: "Korhogo", language: null, pendingQuestion: null };
        await m.processStep(prefs, "anglais", "u1", { isAudioMessage: false, isVoiceInput: false });
        assert.strictEqual(prefs.language, "english");
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

    test("'changer ville' depuis WAITING_CITY → non reconnu comme ville, redemande", async () => {
        // detectChangeCommand ne s'active qu'en COMPLETE. Depuis WAITING_CITY,
        // "changer ville" n'est pas une ville valide (fix cafard démo) → on
        // redemande au lieu d'enregistrer une ville="Ville" absurde.
        const m = makeMachine();
        const prefs = { step: STEPS.WAITING_CITY, city: null, language: null };
        const result = await m.processStep(prefs, "changer ville", "u1", { isAudioMessage: false, isVoiceInput: false });
        assert.strictEqual(result.handled, true);
        assert.strictEqual(prefs.step, STEPS.WAITING_CITY, "reste a l'etape ville");
        assert.strictEqual(prefs.city, null, "aucune ville absurde enregistree");
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


// ─────────────────────────────────────────────
// Fix bug #260 — substring collision feedback (word boundary regex)
//
// Avant fix : ["bon", "ɲuman", ...].some(k => msgLower.includes(k))
//   - "pas bon" matchait "bon" thumbsUp en premier → classe POSITIF (bug)
//   - "te ɲuman" matchait "ɲuman" thumbsUp en premier → classe POSITIF (bug)
//
// Apres fix : regex \b word boundary + thumbsDown teste EN PREMIER.
// Ces 4 tests garantissent le comportement correct + anti-regression
// sur les cas simples.
// ─────────────────────────────────────────────

describe("OnboardingMachine — fix bug #260 substring collision feedback", () => {
    test("[fix #260] 'te ɲuman' (bambara negation) → endpoint negatif", async () => {
        const sock = makeSockMock();
        const axios = makeAxiosMock([{ status: 200, data: {} }]);
        const { userPrefs } = makeUserPrefs();
        const m = new OnboardingMachine({
            userPrefs,
            axios,
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({ "X-API-Key": "test" }),
            randomDelay: noDelay,
            sock,
            logger: silentLogger,
        });
        const prefs = {
            step: STEPS.WAITING_FEEDBACK,
            pendingFeedback: { intent: "CULTURE_MAIS" },
        };

        const result = await m.processStep(prefs, "te ɲuman", "u1", {
            isAudioMessage: false,
            isVoiceInput: false,
        });
        assert.strictEqual(result.handled, true);
        assert.strictEqual(axios.calls.length, 1);
        assert.match(axios.calls[0].url, /\/api\/feedback\/negatif$/);
    });

    test("[fix #260] 'pas bon' (FR negation 2 mots) → endpoint negatif", async () => {
        const sock = makeSockMock();
        const axios = makeAxiosMock([{ status: 200, data: {} }]);
        const { userPrefs } = makeUserPrefs();
        const m = new OnboardingMachine({
            userPrefs,
            axios,
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({ "X-API-Key": "test" }),
            randomDelay: noDelay,
            sock,
            logger: silentLogger,
        });
        const prefs = {
            step: STEPS.WAITING_FEEDBACK,
            pendingFeedback: { intent: "CULTURE_RIZ" },
        };

        const result = await m.processStep(prefs, "C'est pas bon du tout", "u1", {
            isAudioMessage: false,
            isVoiceInput: false,
        });
        assert.strictEqual(result.handled, true);
        assert.match(axios.calls[0].url, /\/api\/feedback\/negatif$/);
    });

    test("[fix #260 anti-reg] 'je trouve ça bien' (FR positif simple) → endpoint positif", async () => {
        // Verifie que le fix word boundary n'a PAS casse le cas simple positif.
        const sock = makeSockMock();
        const axios = makeAxiosMock([{ status: 200, data: {} }]);
        const { userPrefs } = makeUserPrefs();
        const m = new OnboardingMachine({
            userPrefs,
            axios,
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({ "X-API-Key": "test" }),
            randomDelay: noDelay,
            sock,
            logger: silentLogger,
        });
        const prefs = {
            step: STEPS.WAITING_FEEDBACK,
            pendingFeedback: { intent: "X" },
        };

        const result = await m.processStep(prefs, "je trouve ça bien", "u1", {
            isAudioMessage: false,
            isVoiceInput: false,
        });
        assert.strictEqual(result.handled, true);
        assert.match(axios.calls[0].url, /\/api\/feedback\/positif$/);
    });

    test("[fix #260 anti-reg] 'bonjour' ne matche PAS thumbsUp (collision 'bon' bloquee)", async () => {
        // Avant fix : "bonjour" contenait "bon" → matchait thumbsUp.
        // Apres fix : word boundary `\b(?:bon)\b` rejette "bonjour" (continuation).
        // Resultat attendu : message invalide → re-demande 'jaabi 👍 wala 👎'.
        const sock = makeSockMock();
        const axios = makeAxiosMock();
        const { userPrefs } = makeUserPrefs();
        const m = new OnboardingMachine({
            userPrefs,
            axios,
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({ "X-API-Key": "test" }),
            randomDelay: noDelay,
            sock,
            logger: silentLogger,
        });
        const prefs = {
            step: STEPS.WAITING_FEEDBACK,
            pendingFeedback: { intent: "X" },
        };

        const result = await m.processStep(prefs, "bonjour", "u1", {
            isAudioMessage: false,
            isVoiceInput: false,
        });
        assert.strictEqual(result.handled, true);
        // Aucun POST API (message invalide, pas de feedback envoye)
        assert.strictEqual(axios.calls.length, 0);
        // Sock a envoye la re-demande
        assert.ok(
            sock.sent.some(s => /jaabi|👍|👎/.test(s.msg.text)),
            "Message re-demande envoye"
        );
    });
});


// ─────────────────────────────────────────────
// Fix bug #269 — frontiere de mot Unicode (lettres dioula ɲ ɔ ɛ)
//
// `\b` en JS reste ASCII-only meme avec le flag `u` : `\bɲuman\b` ne matchait
// jamais car ɲ (U+0272) n'est pas dans [A-Za-z0-9_]. Un agriculteur envoyant
// "ɲuman" seul (= "bien") n'etait plus reconnu comme thumbsUp (regression
// silencieuse vs PR #264). Fix : lookarounds negatifs sur [\p{L}\p{N}_].
//
// Ce bloc couvre les criteres de done de l'issue + la desambiguisation
// DOWN-avant-UP sur messages mixtes (defense en profondeur preservee).
// ─────────────────────────────────────────────

describe("OnboardingMachine — fix bug #269 frontiere Unicode dioula", () => {
    // Helper : joue un message en WAITING_FEEDBACK, renvoie { result, axios, sock }.
    async function runFeedback(messageText) {
        const sock = makeSockMock();
        const axios = makeAxiosMock([{ status: 200, data: {} }]);
        const m = makeMachine({ sock, axios });
        const prefs = {
            step: STEPS.WAITING_FEEDBACK,
            pendingFeedback: { intent: "CULTURE_MAIS" },
        };
        const result = await m.processStep(prefs, messageText, "u1", {
            isAudioMessage: false,
            isVoiceInput: false,
        });
        return { result, axios, sock };
    }

    test("[fix #269] 'ɲuman' seul (dioula = bien) → endpoint positif", async () => {
        const { result, axios } = await runFeedback("ɲuman");
        assert.strictEqual(result.handled, true);
        assert.strictEqual(axios.calls.length, 1);
        assert.match(axios.calls[0].url, /\/api\/feedback\/positif$/);
    });

    test("[fix #269] 'numan' seul (variante sans ɲ) → endpoint positif", async () => {
        const { result, axios } = await runFeedback("numan");
        assert.strictEqual(result.handled, true);
        assert.match(axios.calls[0].url, /\/api\/feedback\/positif$/);
    });

    test("[fix #269] 'ɲuman' entoure de ponctuation → endpoint positif", async () => {
        // Frontiere Unicode : la ponctuation n'est ni \p{L} ni \p{N}, donc borne OK.
        const { result, axios } = await runFeedback("ɲuman!");
        assert.strictEqual(result.handled, true);
        assert.match(axios.calls[0].url, /\/api\/feedback\/positif$/);
    });

    test("[fix #269 anti-reg] 'te ɲuman' (negation dioula) → endpoint negatif", async () => {
        const { result, axios } = await runFeedback("te ɲuman");
        assert.strictEqual(result.handled, true);
        assert.match(axios.calls[0].url, /\/api\/feedback\/negatif$/);
    });

    test("[fix #269 anti-reg] 'pas bon' (negation FR 2 mots) → endpoint negatif", async () => {
        const { result, axios } = await runFeedback("pas bon");
        assert.strictEqual(result.handled, true);
        assert.match(axios.calls[0].url, /\/api\/feedback\/negatif$/);
    });

    test("[fix #269 anti-reg] 'bonjour' ne matche PAS thumbsUp (collision 'bon')", async () => {
        // Parite avec l'ancien \b : la continuation 'jour' (lettres) bloque la borne.
        const { result, axios, sock } = await runFeedback("bonjour");
        assert.strictEqual(result.handled, true);
        assert.strictEqual(axios.calls.length, 0);
        assert.ok(
            sock.sent.some(s => /jaabi|👍|👎/.test(s.msg.text)),
            "Message re-demande envoye"
        );
    });

    // ── Desambiguisation DOWN-avant-UP (messages mixtes) ──
    // processStep teste thumbsDown EN PREMIER (onboarding.js). Un message
    // contenant a la fois un mot positif et un mot negatif doit tomber en NEGATIF.

    test("[fix #269 desambig] 'oui mais c'est pas bon' (mixte) → NEGATIF", async () => {
        const { result, axios } = await runFeedback("oui mais c'est pas bon");
        assert.strictEqual(result.handled, true);
        assert.strictEqual(axios.calls.length, 1);
        assert.match(axios.calls[0].url, /\/api\/feedback\/negatif$/);
    });

    test("[fix #269 desambig] 'bien mais te ɲuman' (mixte dioula) → NEGATIF", async () => {
        const { result, axios } = await runFeedback("bien mais te ɲuman");
        assert.strictEqual(result.handled, true);
        assert.match(axios.calls[0].url, /\/api\/feedback\/negatif$/);
    });

    test("[fix #269 desambig] 'ɲuman' pur reste POSITIF (pas de mot negatif)", async () => {
        // Contre-preuve : sans mot negatif, la desambiguisation laisse passer POSITIF.
        const { result, axios } = await runFeedback("ɲuman kosɛbɛ");
        assert.strictEqual(result.handled, true);
        assert.match(axios.calls[0].url, /\/api\/feedback\/positif$/);
    });
});


// ─────────────────────────────────────────────
// Edge cases coverage — followup session 2026-05-30
// Note : 2 tests "te ɲuman" et "pas bon" → endpoint negatif deja
// inclus dans PR #264 (fix bug #260). Ce bloc ajoute 6 tests
// complementaires sur d'autres branches non couvertes.
// ─────────────────────────────────────────────

describe("OnboardingMachine — edge cases coverage (followup)", () => {
    test("processStep : step inconnu (typo) → { handled: null } pass-through defensif", async () => {
        const sock = makeSockMock();
        const m = makeMachine({ sock });
        const prefs = { step: "TYPO_INEXISTANT_STEP", language: "french" };

        const result = await m.processStep(prefs, "hello", "u1", {
            isAudioMessage: false,
            isVoiceInput: false,
        });
        assert.strictEqual(result.handled, null);
        assert.strictEqual(sock.sent.length, 0);
    });

    test("_handleWaitingLanguage : input '  1  ' (avec espaces) → trim ok → french", async () => {
        const sock = makeSockMock();
        const m = makeMachine({ sock });
        const prefs = {
            step: STEPS.WAITING_LANGUAGE,
            city: "Abidjan",
            pendingQuestion: null,
        };

        const result = await m.processStep(prefs, "  1  ", "u1", {
            isAudioMessage: false,
            isVoiceInput: false,
        });
        assert.strictEqual(result.handled, true);
        assert.strictEqual(prefs.language, "french");
        assert.strictEqual(prefs.step, STEPS.COMPLETE);
    });

    test("_handleWaitingFeedback : 'mauvais' (FR negatif sans collision) → endpoint negatif", async () => {
        const sock = makeSockMock();
        const axios = makeAxiosMock([{ status: 200, data: {} }]);
        const { userPrefs } = makeUserPrefs();
        const m = new OnboardingMachine({
            userPrefs,
            axios,
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({ "X-API-Key": "test" }),
            randomDelay: noDelay,
            sock,
            logger: silentLogger,
        });
        const prefs = {
            step: STEPS.WAITING_FEEDBACK,
            pendingFeedback: { intent: "X" },
        };

        const result = await m.processStep(prefs, "C'est mauvais", "u1", {
            isAudioMessage: false,
            isVoiceInput: false,
        });
        assert.strictEqual(result.handled, true);
        assert.match(axios.calls[0].url, /\/api\/feedback\/negatif$/);
    });

    test("_handleWaitingFeedback : 'super' (FR positif) → endpoint positif", async () => {
        const sock = makeSockMock();
        const axios = makeAxiosMock([{ status: 200, data: {} }]);
        const { userPrefs } = makeUserPrefs();
        const m = new OnboardingMachine({
            userPrefs,
            axios,
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({ "X-API-Key": "test" }),
            randomDelay: noDelay,
            sock,
            logger: silentLogger,
        });
        const prefs = {
            step: STEPS.WAITING_FEEDBACK,
            pendingFeedback: { intent: "X" },
        };

        const result = await m.processStep(prefs, "Super merci !", "u1", {
            isAudioMessage: false,
            isVoiceInput: false,
        });
        assert.strictEqual(result.handled, true);
        assert.match(axios.calls[0].url, /\/api\/feedback\/positif$/);
    });

    test("_handleNew : messageText vide → pendingQuestion='' + WELCOME envoye sans crash", async () => {
        const sock = makeSockMock();
        const m = makeMachine({ sock });
        const prefs = { step: STEPS.NEW };

        const result = await m.processStep(prefs, "", "u1", {
            isAudioMessage: false,
            isVoiceInput: false,
        });
        assert.strictEqual(result.handled, true);
        assert.strictEqual(prefs.step, STEPS.WAITING_CITY);
        assert.strictEqual(prefs.pendingQuestion, "");
        assert.strictEqual(sock.sent.length, 1);
    });
});
