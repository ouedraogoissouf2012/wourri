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
