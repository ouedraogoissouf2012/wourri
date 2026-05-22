/**
 * Tests unitaires pour AsrClient.
 * Exécution : node --test tests/asr_client.test.js
 *
 * Couvre :
 *   - validation du constructor (apiUrl + authHeaders obligatoires)
 *   - succès et fallbacks de transcribeAudio (Whisper FR)
 *   - succès, priorité NLU et fallback Bambara→FR de transcribeAudioBambara
 *   - appel de authHeaders() à chaque requête (anti-régression cache)
 */
"use strict";

const { test, describe } = require("node:test");
const assert = require("node:assert");
const { AsrClient } = require("../lib/asr_client");

const silentLogger = {
    info: () => {},
    warn: () => {},
    error: () => {},
};

/**
 * Construit un mock axios qui enregistre les appels et retourne une réponse
 * scriptée par index. Permet d'inspecter combien de fois `.post` a été appelé,
 * sur quelle URL, et avec quels headers.
 */
function makeAxiosMock(responses) {
    const calls = [];
    let idx = 0;
    return {
        calls,
        post: async (url, formData, options) => {
            calls.push({ url, headers: options.headers });
            const response = responses[idx++];
            if (response instanceof Error) throw response;
            return response;
        },
    };
}

describe("AsrClient — construction", () => {
    test("constructor sans apiUrl jette une erreur", () => {
        assert.throws(
            () => new AsrClient({ authHeaders: () => ({}) }),
            /apiUrl requis/,
        );
    });

    test("constructor sans authHeaders jette une erreur", () => {
        assert.throws(
            () => new AsrClient({ apiUrl: "http://localhost:8000" }),
            /authHeaders/,
        );
    });

    test("constructor avec authHeaders non-fonction jette une erreur", () => {
        assert.throws(
            () => new AsrClient({
                apiUrl: "http://localhost:8000",
                authHeaders: { "X-API-Key": "static" },
            }),
            /authHeaders/,
        );
    });
});

describe("AsrClient — transcribeAudio (Whisper FR)", () => {
    test("retourne {text, likely_dioula_input, language_probability} sur 200", async () => {
        const axiosMock = makeAxiosMock([
            {
                status: 200,
                data: {
                    text: "Bonjour les agriculteurs",
                    likely_dioula_input: false,
                    language_probability: 0.95,
                },
            },
        ]);
        const client = new AsrClient({
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({ "X-API-Key": "test-key" }),
            logger: silentLogger,
            axios: axiosMock,
        });

        const result = await client.transcribeAudio(Buffer.from("fake-audio"));

        assert.deepStrictEqual(result, {
            text: "Bonjour les agriculteurs",
            likely_dioula_input: false,
            language_probability: 0.95,
        });
        assert.strictEqual(axiosMock.calls.length, 1);
        assert.match(axiosMock.calls[0].url, /\/api\/stt\/transcribe$/);
    });

    test("retourne null si response.data.text est absent (réponse vide)", async () => {
        const axiosMock = makeAxiosMock([{ status: 200, data: {} }]);
        const client = new AsrClient({
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({}),
            logger: silentLogger,
            axios: axiosMock,
        });

        const result = await client.transcribeAudio(Buffer.from("fake"));
        assert.strictEqual(result, null);
    });

    test("retourne null (pas d'exception) sur ECONNREFUSED", async () => {
        const err = new Error("connect ECONNREFUSED");
        err.code = "ECONNREFUSED";
        const axiosMock = makeAxiosMock([err]);
        const client = new AsrClient({
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({}),
            logger: silentLogger,
            axios: axiosMock,
        });

        const result = await client.transcribeAudio(Buffer.from("fake"));
        assert.strictEqual(result, null);
    });

    test("retourne null sur erreur HTTP 422 (réponse axios v1.x avec error.message vide)", async () => {
        const err = new Error("");
        err.response = { status: 422 };
        const axiosMock = makeAxiosMock([err]);
        const client = new AsrClient({
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({}),
            logger: silentLogger,
            axios: axiosMock,
        });

        const result = await client.transcribeAudio(Buffer.from("fake"));
        assert.strictEqual(result, null);
    });
});

describe("AsrClient — transcribeAudioBambara (MMS Dioula)", () => {
    test("priorise nlu_message > french_translation > transcription", async () => {
        const axiosMock = makeAxiosMock([
            {
                status: 200,
                data: {
                    transcription: "Aw ni tile",
                    french_translation: "Bonjour",
                    nlu_message: "Question agricole détectée",
                },
            },
        ]);
        const client = new AsrClient({
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({}),
            logger: silentLogger,
            axios: axiosMock,
        });

        const result = await client.transcribeAudioBambara(Buffer.from("fake"));
        assert.strictEqual(result.text, "Question agricole détectée");
        assert.strictEqual(result.bambara_text, "Aw ni tile");
        assert.strictEqual(result.is_bambara, true);
    });

    test("retombe sur french_translation si nlu_message absent", async () => {
        const axiosMock = makeAxiosMock([
            {
                status: 200,
                data: {
                    transcription: "Aw ni tile",
                    french_translation: "Bonjour",
                },
            },
        ]);
        const client = new AsrClient({
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({}),
            logger: silentLogger,
            axios: axiosMock,
        });

        const result = await client.transcribeAudioBambara(Buffer.from("fake"));
        assert.strictEqual(result.text, "Bonjour");
        assert.strictEqual(result.bambara_text, "Aw ni tile");
    });

    test("retombe sur transcription si nlu_message ET french_translation absents", async () => {
        const axiosMock = makeAxiosMock([
            { status: 200, data: { transcription: "Aw ni tile" } },
        ]);
        const client = new AsrClient({
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({}),
            logger: silentLogger,
            axios: axiosMock,
        });

        const result = await client.transcribeAudioBambara(Buffer.from("fake"));
        assert.strictEqual(result.text, "Aw ni tile");
    });

    test("fallback Bambara→Whisper FR quand l'ASR Bambara échoue (2 appels axios)", async () => {
        // 1er appel (Bambara) → erreur ; 2e appel (Whisper FR) → succès
        const bambaraErr = new Error("MMS model unavailable");
        bambaraErr.code = "ETIMEDOUT";
        const axiosMock = makeAxiosMock([
            bambaraErr,
            { status: 200, data: { text: "Fallback français" } },
        ]);
        const client = new AsrClient({
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({}),
            logger: silentLogger,
            axios: axiosMock,
        });

        const result = await client.transcribeAudioBambara(Buffer.from("fake"));

        assert.strictEqual(axiosMock.calls.length, 2);
        assert.match(axiosMock.calls[0].url, /\/api\/asr\/transcribe-and-translate$/);
        assert.match(axiosMock.calls[1].url, /\/api\/stt\/transcribe$/);
        assert.strictEqual(result.text, "Fallback français");
        assert.strictEqual(result.likely_dioula_input, false);
    });

    test("fallback retourne null si Bambara ET Whisper FR échouent tous deux", async () => {
        const err1 = new Error("Bambara down");
        err1.code = "ECONNREFUSED";
        const err2 = new Error("Whisper down");
        err2.code = "ECONNREFUSED";
        const axiosMock = makeAxiosMock([err1, err2]);
        const client = new AsrClient({
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({}),
            logger: silentLogger,
            axios: axiosMock,
        });

        const result = await client.transcribeAudioBambara(Buffer.from("fake"));
        assert.strictEqual(result, null);
    });
});

/**
 * Logger qui enregistre tous les appels pour inspection.
 *
 * Supporte l'API pino à 2 args : `logger.info(obj, msg)` (Sprint H.2a) ET
 * l'API à 1 arg : `logger.info(msg)`.
 *
 * `calls.{info|warn|error}` : version stringifiée (objet + msg combinés) —
 *   les assertions `.includes(...)` existantes continuent de marcher.
 * `calls.structured.{info|warn|error}` : version structurée (`{ctx, msg}`) —
 *   permet aux nouveaux tests H.2a de vérifier la présence/forme du contexte.
 */
function makeRecordingLogger() {
    const calls = {
        info: [], warn: [], error: [],
        structured: { info: [], warn: [], error: [] },
    };
    const pushFn = (level) => (...args) => {
        // pino convention : logger.info(obj, msg) OU logger.info(msg)
        if (args.length >= 2 && typeof args[0] === "object" && args[0] !== null) {
            calls.structured[level].push({ ctx: args[0], msg: args[1] });
            calls[level].push(JSON.stringify(args[0]) + " " + args[1]);
        } else {
            calls.structured[level].push({ ctx: null, msg: args[0] });
            calls[level].push(String(args[0]));
        }
    };
    return {
        calls,
        info: pushFn("info"),
        warn: pushFn("warn"),
        error: pushFn("error"),
    };
}

describe("AsrClient — Sprint H.1b — sécurité logs (issue #161)", () => {
    test("transcribeAudio : URL backend NE doit PAS être loggée (anti-leak credentials)", async () => {
        // Simule WOURI_API_URL avec credentials embarqués (cas pathologique)
        const axiosMock = makeAxiosMock([
            { status: 200, data: { text: "Bonjour" } },
        ]);
        const logger = makeRecordingLogger();
        const client = new AsrClient({
            apiUrl: "http://user:secret@malicious-host:8000",
            authHeaders: () => ({}),
            logger,
            axios: axiosMock,
        });

        await client.transcribeAudio(Buffer.from("fake"));

        // Aucun log ne doit contenir la base URL avec credentials
        const allLogs = logger.calls.info.join(" | ");
        assert.ok(!allLogs.includes("secret"), `Log fuit le password: ${allLogs}`);
        assert.ok(!allLogs.includes("user:"), `Log fuit le username: ${allLogs}`);
        assert.ok(!allLogs.includes("malicious-host"), `Log fuit le host: ${allLogs}`);
        // Mais on doit garder le path pour debug
        assert.ok(allLogs.includes("/api/stt/transcribe"), "Le path doit rester loggé pour debug");
    });

    test("transcribeAudioBambara : URL backend NE doit PAS être loggée", async () => {
        const axiosMock = makeAxiosMock([
            { status: 200, data: { transcription: "i ni ce", french_translation: "bonjour" } },
        ]);
        const logger = makeRecordingLogger();
        const client = new AsrClient({
            apiUrl: "http://user:secret@host:8000",
            authHeaders: () => ({}),
            logger,
            axios: axiosMock,
        });

        await client.transcribeAudioBambara(Buffer.from("fake"));

        const allLogs = logger.calls.info.join(" | ");
        assert.ok(!allLogs.includes("secret"), `Log fuit le password: ${allLogs}`);
        assert.ok(!allLogs.includes("user:"), `Log fuit le username: ${allLogs}`);
        assert.ok(allLogs.includes("/api/asr/transcribe-and-translate"), "Le path doit rester loggé");
    });

    test("transcribeAudioBambara : transcription longue (>50 chars) tronquée dans les logs (PII)", async () => {
        const longTranscription = "ne be malo senɛ ka ji caman di a ma sanji tuma na, n ko ne be a fɛ ka fɛn caman dɔn";
        const longTranslation = "Je plante du riz et donne beaucoup d eau pendant la saison des pluies, je veux apprendre beaucoup";
        const longNlu = "QUESTION_IRRIGATION + CULTURE_RIZ + TEMPS_SAISON_PLUIE → demande conseil irrigation riz saison pluies";

        assert.ok(longTranscription.length > 50, "setup test : transcription > 50 chars");
        assert.ok(longTranslation.length > 50, "setup test : translation > 50 chars");
        assert.ok(longNlu.length > 50, "setup test : nlu > 50 chars");

        const axiosMock = makeAxiosMock([
            {
                status: 200,
                data: {
                    transcription: longTranscription,
                    french_translation: longTranslation,
                    nlu_message: longNlu,
                },
            },
        ]);
        const logger = makeRecordingLogger();
        const client = new AsrClient({
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({}),
            logger,
            axios: axiosMock,
        });

        await client.transcribeAudioBambara(Buffer.from("fake"));

        const allLogs = logger.calls.info.join(" | ");
        // Aucun log ne contient le contenu COMPLET (PII)
        assert.ok(!allLogs.includes(longTranscription), "Log contient la transcription complète (PII leak)");
        assert.ok(!allLogs.includes(longTranslation), "Log contient la traduction complète (PII leak)");
        assert.ok(!allLogs.includes(longNlu), "Log contient le NLU complet (PII leak)");
        // Mais doit contenir le préfixe + "..." pour debug
        assert.ok(allLogs.includes(longTranscription.slice(0, 50) + "..."), "Log doit tronquer transcription à 50 chars + ...");
        assert.ok(allLogs.includes(longTranslation.slice(0, 50) + "..."), "Log doit tronquer translation à 50 chars + ...");
        assert.ok(allLogs.includes(longNlu.slice(0, 50) + "..."), "Log doit tronquer nluMessage à 50 chars + ...");
    });

    test("Edge case : transcription null/vide → log vide propre (pas 'null')", async () => {
        // Cas où l'API retourne transcription absente ou string vide :
        // le log doit produire "" intact (pas "null" ni "undefined").
        const axiosMock = makeAxiosMock([
            { status: 200, data: { transcription: "", french_translation: "" } },
        ]);
        const logger = makeRecordingLogger();
        const client = new AsrClient({
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({}),
            logger,
            axios: axiosMock,
        });
        await client.transcribeAudioBambara(Buffer.from("fake"));
        const allLogs = logger.calls.info.join(" | ");
        assert.ok(!allLogs.includes('"null"'), `Log ne doit pas contenir "null": ${allLogs}`);
        assert.ok(!allLogs.includes('"undefined"'), `Log ne doit pas contenir "undefined": ${allLogs}`);
    });

    test("catch error : message PII potentiellement dans error.message → tronqué (100 chars)", async () => {
        // Simule une erreur HTTP 422 dont le message inclut la transcription user
        // (ce que axios peut faire si le backend renvoie le body dans error.message)
        const piiInError = "Le bot a recu: ne be malo senɛ ka ji caman di a ma sanji tuma na n ko ne be a fɛ ka fɛn caman dɔn kɔni";
        assert.ok(piiInError.length > 100, "setup test : error message > 100 chars");

        const axiosError = new Error(piiInError);
        axiosError.code = "ERR_BAD_REQUEST";
        axiosError.response = { status: 422 };

        const axiosMock = makeAxiosMock([axiosError, axiosError]); // 2 erreurs (bambara + fallback FR)
        const logger = makeRecordingLogger();
        const client = new AsrClient({
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({}),
            logger,
            axios: axiosMock,
        });

        await client.transcribeAudioBambara(Buffer.from("fake"));

        // Vérifier qu'aucun log d'erreur ne contient la PII complète
        const allErrors = logger.calls.error.join(" | ");
        assert.ok(!allErrors.includes(piiInError), `Log error fuit la PII complète: ${allErrors}`);
        // Mais doit contenir un préfixe tronqué (100 chars)
        assert.ok(allErrors.includes(piiInError.slice(0, 100)), "Log error doit garder préfixe tronqué pour debug");
    });

    test("transcribeAudioBambara : transcription courte (≤50 chars) NON tronquée (debug intact)", async () => {
        const shortText = "i ni ce"; // 7 chars
        const axiosMock = makeAxiosMock([
            {
                status: 200,
                data: { transcription: shortText, french_translation: "bonjour" },
            },
        ]);
        const logger = makeRecordingLogger();
        const client = new AsrClient({
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({}),
            logger,
            axios: axiosMock,
        });

        await client.transcribeAudioBambara(Buffer.from("fake"));

        const allLogs = logger.calls.info.join(" | ");
        // Texte court → loggé intégralement (debug normal)
        assert.ok(allLogs.includes(`"${shortText}"`), `Log doit contenir transcription courte intacte: ${allLogs}`);
        // Pas d'ellipsis ajoutée à tort
        assert.ok(!allLogs.includes("..."), "Log ne doit pas ajouter ... sur texte court");
    });
});

describe("AsrClient — Sprint H.2a — format pino objet-contexte (issue #161)", () => {
    test("transcribeAudio : tous les logs respectent l'API pino (ctx, msg)", async () => {
        const axiosMock = makeAxiosMock([{ status: 200, data: { text: "Bonjour" } }]);
        const logger = makeRecordingLogger();
        const client = new AsrClient({
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({}),
            logger,
            axios: axiosMock,
        });
        await client.transcribeAudio(Buffer.from("fake"));

        // 2 logs info attendus : "Appel API" + "Reponse API recue", chacun avec ctx
        const structured = logger.calls.structured.info;
        assert.ok(structured.length >= 2, `attendu >= 2 logs info, recu ${structured.length}`);
        // Log "Appel API" doit avoir { path: ... }
        const appelLog = structured.find((s) => s.msg === "[STT] Appel API");
        assert.ok(appelLog, "Log '[STT] Appel API' absent");
        assert.deepStrictEqual(appelLog.ctx, { path: "/api/stt/transcribe" });
        // Log "Reponse API recue" doit avoir { status: 200 }
        const reponseLog = structured.find((s) => s.msg === "[STT] Reponse API recue");
        assert.ok(reponseLog, "Log '[STT] Reponse API recue' absent");
        assert.strictEqual(reponseLog.ctx.status, 200);
    });

    test("transcribeAudioBambara erreur : log error utilise { code, errMsg } (pino)", async () => {
        const axiosError = new Error("Network error");
        axiosError.code = "ECONNREFUSED";
        // Mock retourne 2 erreurs (bambara + fallback FR)
        const axiosMock = makeAxiosMock([axiosError, axiosError]);
        const logger = makeRecordingLogger();
        const client = new AsrClient({
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({}),
            logger,
            axios: axiosMock,
        });
        await client.transcribeAudioBambara(Buffer.from("fake"));

        // Log error doit avoir { code, errMsg } — `errMsg` car `msg` est réservé pino
        const errLog = logger.calls.structured.error.find(
            (s) => s.msg === "[ASR-BAMBARA] Erreur transcription",
        );
        assert.ok(errLog, "Log error '[ASR-BAMBARA] Erreur transcription' absent");
        assert.strictEqual(errLog.ctx.code, "ECONNREFUSED");
        assert.ok(typeof errLog.ctx.errMsg === "string", "ctx.errMsg doit être une string");
        assert.ok(errLog.ctx.errMsg.length > 0, "ctx.errMsg ne doit pas être vide");
        // Anti-régression : la clé pino réservée `msg` ne doit PAS apparaître dans le ctx
        assert.ok(!("msg" in errLog.ctx), "ctx ne doit pas contenir la clé réservée pino 'msg'");
    });

    test("transcribeAudio erreur : log error utilise { code, errMsg } (symétrique Bambara)", async () => {
        // Symétrie avec le test Bambara (couverture du contrat pino sur les 2 méthodes).
        const axiosError = new Error("HTTP 422 - body might contain user input");
        axiosError.code = "ERR_BAD_REQUEST";
        axiosError.response = { status: 422 };
        const axiosMock = makeAxiosMock([axiosError]);
        const logger = makeRecordingLogger();
        const client = new AsrClient({
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({}),
            logger,
            axios: axiosMock,
        });
        await client.transcribeAudio(Buffer.from("fake"));

        const errLog = logger.calls.structured.error.find(
            (s) => s.msg === "[STT] Erreur transcription",
        );
        assert.ok(errLog, "Log error '[STT] Erreur transcription' absent");
        // error.code prioritaire sur error.response.status
        assert.strictEqual(errLog.ctx.code, "ERR_BAD_REQUEST");
        assert.ok(typeof errLog.ctx.errMsg === "string");
        assert.ok(!("msg" in errLog.ctx), "ctx ne doit pas contenir la clé réservée pino 'msg'");
    });
});

describe("AsrClient — Sprint H.3 — factorisation _postAudio + _logError (issue #161)", () => {
    test("_postAudio existe et est appele depuis transcribeAudio (anti-regression refactor)", async () => {
        // Verifie via espionnage : axios.post est appele 1 seule fois avec
        // l URL complete (= apiUrl + endpoint passe a _postAudio).
        const axiosMock = makeAxiosMock([{ status: 200, data: { text: "ok" } }]);
        const client = new AsrClient({
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({ "X-API-Key": "abc" }),
            logger: silentLogger,
            axios: axiosMock,
        });
        await client.transcribeAudio(Buffer.from("audio"));
        assert.strictEqual(axiosMock.calls.length, 1);
        assert.strictEqual(axiosMock.calls[0].url, "http://localhost:8000/api/stt/transcribe");
        // Les headers contiennent bien la clé API + form-data multipart
        assert.strictEqual(axiosMock.calls[0].headers["X-API-Key"], "abc");
    });

    test("transcribeAudio exception → null (PAS de fallback, anti-regression)", async () => {
        // Une exception du axios.post DOIT donner null pour transcribeAudio
        // (pas de fallback comme transcribeAudioBambara).
        const networkError = new Error("Network down");
        networkError.code = "ECONNREFUSED";
        const axiosMock = makeAxiosMock([networkError]);
        const client = new AsrClient({
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({}),
            logger: silentLogger,
            axios: axiosMock,
        });
        const result = await client.transcribeAudio(Buffer.from("audio"));
        assert.strictEqual(result, null);
        // Une seule tentative — pas de retry/fallback
        assert.strictEqual(axiosMock.calls.length, 1);
    });

    test("transcribeAudioBambara exception → fallback STT (anti-regression refactor)", async () => {
        // Exception bambara → DOIT appeler transcribeAudio en fallback.
        // Le refactor H.3 doit preserver ce comportement metier critique.
        const bambaraError = new Error("MMS down");
        bambaraError.code = "ETIMEDOUT";
        const axiosMock = makeAxiosMock([
            bambaraError, // 1er appel : ASR-BAMBARA → echec
            { status: 200, data: { text: "fallback ok" } }, // 2e appel : Whisper FR → succes
        ]);
        const client = new AsrClient({
            apiUrl: "http://localhost:8000",
            authHeaders: () => ({}),
            logger: silentLogger,
            axios: axiosMock,
        });
        const result = await client.transcribeAudioBambara(Buffer.from("audio"));
        // 2 appels axios : 1er ASR-BAMBARA, 2e Whisper FR (fallback)
        assert.strictEqual(axiosMock.calls.length, 2);
        assert.ok(axiosMock.calls[0].url.includes("/api/asr/transcribe-and-translate"));
        assert.ok(axiosMock.calls[1].url.includes("/api/stt/transcribe"));
        // Le resultat retourne ce que Whisper FR a produit
        assert.ok(result);
        assert.strictEqual(result.text, "fallback ok");
    });
});

describe("AsrClient — authHeaders dynamique", () => {
    test("authHeaders() est invoqué à chaque requête (pas de cache)", async () => {
        let callCount = 0;
        const authHeaders = () => {
            callCount++;
            return { "X-API-Key": `dynamic-${callCount}` };
        };
        const axiosMock = makeAxiosMock([
            { status: 200, data: { text: "ok-1" } },
            { status: 200, data: { text: "ok-2" } },
        ]);
        const client = new AsrClient({
            apiUrl: "http://localhost:8000",
            authHeaders,
            logger: silentLogger,
            axios: axiosMock,
        });

        await client.transcribeAudio(Buffer.from("a"));
        await client.transcribeAudio(Buffer.from("b"));

        assert.strictEqual(callCount, 2);
        assert.strictEqual(axiosMock.calls[0].headers["X-API-Key"], "dynamic-1");
        assert.strictEqual(axiosMock.calls[1].headers["X-API-Key"], "dynamic-2");
    });
});
