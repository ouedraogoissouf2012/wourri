/**
 * Tests de caractérisation pour ExcuseAudio.
 *
 * Ces tests capturent le comportement de la logique d'excuse audio telle
 * qu'elle existait inline dans app-baileys.js avant l'extraction, pour
 * garantir qu'aucune régression n'est introduite par la modularisation.
 *
 * Exécution : node --test tests/excuse_audio.test.js
 */
"use strict";

const { test, describe } = require("node:test");
const assert = require("node:assert");
const { ExcuseAudio, EXCUSE_MSG } = require("../lib/excuse_audio");

const silentLogger = {
    info: () => {},
    warn: () => {},
    error: () => {},
};

const authHeaders = () => ({ "X-API-Key": "test-key" });

// Fake AudioCache : enregistre les appels get/save/warmup sans toucher au disque.
function makeFakeCache({ getReturns = null } = {}) {
    const calls = { get: [], save: [], warmup: [] };
    return {
        calls,
        async get(key) { calls.get.push(key); return getReturns; },
        async save(key, buf) { calls.save.push({ key, buf }); },
        async warmup(entries) { calls.warmup.push(entries); return { generated: entries.length, cached: 0, failed: 0 }; },
    };
}

// Fake axios : post renvoie {data:{audio_url}}, get renvoie un arraybuffer.
function makeFakeAxios({ audioUrl = "/audio/x.ogg", audioBytes = "AUDIO", postThrows = false, getThrows = false } = {}) {
    const calls = { post: [], get: [] };
    return {
        calls,
        async post(url, body, config) {
            calls.post.push({ url, body, config });
            if (postThrows) { const e = new Error("boom"); e.code = "ECONNREFUSED"; throw e; }
            return { data: audioUrl === null ? {} : { audio_url: audioUrl } };
        },
        async get(url, config) {
            calls.get.push({ url, config });
            if (getThrows) { const e = new Error("boom"); e.code = "ETIMEDOUT"; throw e; }
            return { data: Buffer.from(audioBytes) };
        },
    };
}

describe("ExcuseAudio — construction", () => {
    test("throw si apiUrl manquant", () => {
        assert.throws(() => new ExcuseAudio({ authHeaders, cacheDir: "/tmp/x" }), /apiUrl requis/);
    });
    test("throw si authHeaders n'est pas une fonction", () => {
        assert.throws(() => new ExcuseAudio({ apiUrl: "http://x", authHeaders: "no", cacheDir: "/tmp/x" }), /authHeaders/);
    });
    test("throw si ni cacheDir ni audioCache fournis", () => {
        assert.throws(() => new ExcuseAudio({ apiUrl: "http://x", authHeaders }), /cacheDir/);
    });
    test("construit avec audioCache injecté (sans cacheDir)", () => {
        const ea = new ExcuseAudio({ apiUrl: "http://x", authHeaders, audioCache: makeFakeCache(), logger: silentLogger });
        assert.ok(ea);
    });
});

describe("ExcuseAudio — EXCUSE_MSG", () => {
    test("expose les 6 textes attendus", () => {
        for (const k of ["UNAVAILABLE_FR", "UNAVAILABLE_DIOULA", "UNAVAILABLE_BILINGUAL", "BACK_FR", "BACK_DIOULA", "BACK_BILINGUAL"]) {
            assert.strictEqual(typeof EXCUSE_MSG[k], "string");
            assert.ok(EXCUSE_MSG[k].length > 0);
        }
    });
    test("le dioula n'a pas de diacritiques fantaisistes (règle projet: malo pas màlo)", () => {
        // Les textes valides contiennent ɛ/ɔ/ɲ mais pas d'accents graves/aigus latins.
        assert.match(EXCUSE_MSG.UNAVAILABLE_DIOULA, /bɛ/);
    });
});

describe("ExcuseAudio — tryGenerateAudioFromText", () => {
    test("text vide → null (pas d'appel réseau)", async () => {
        const axios = makeFakeAxios();
        const ea = new ExcuseAudio({ apiUrl: "http://api", authHeaders, audioCache: makeFakeCache(), axios, logger: silentLogger });
        assert.strictEqual(await ea.tryGenerateAudioFromText("", false), null);
        assert.strictEqual(axios.calls.post.length, 0);
    });
    test("dioula → endpoint /api/tts/dioula avec is_french:false (ADR-0023 #362)", async () => {
        const axios = makeFakeAxios();
        const ea = new ExcuseAudio({ apiUrl: "http://api", authHeaders, audioCache: makeFakeCache(), axios, logger: silentLogger });
        const buf = await ea.tryGenerateAudioFromText("salut", false);
        assert.ok(Buffer.isBuffer(buf));
        assert.strictEqual(buf.toString(), "AUDIO");
        assert.strictEqual(axios.calls.post[0].url, "http://api/api/tts/dioula");
        assert.deepStrictEqual(axios.calls.post[0].config.params, { text: "salut", is_french: false });
        assert.deepStrictEqual(axios.calls.post[0].config.headers, { "X-API-Key": "test-key" });
    });
    test("français → endpoint /api/tts/french avec params {text}", async () => {
        const axios = makeFakeAxios();
        const ea = new ExcuseAudio({ apiUrl: "http://api", authHeaders, audioCache: makeFakeCache(), axios, logger: silentLogger });
        await ea.tryGenerateAudioFromText("hello", true);
        assert.strictEqual(axios.calls.post[0].url, "http://api/api/tts/french");
        assert.deepStrictEqual(axios.calls.post[0].config.params, { text: "hello" });
    });
    test("audio_url absolue → utilisée telle quelle pour le GET", async () => {
        const axios = makeFakeAxios({ audioUrl: "http://cdn/x.ogg" });
        const ea = new ExcuseAudio({ apiUrl: "http://api", authHeaders, audioCache: makeFakeCache(), axios, logger: silentLogger });
        await ea.tryGenerateAudioFromText("t", false);
        assert.strictEqual(axios.calls.get[0].url, "http://cdn/x.ogg");
    });
    test("audio_url relative → préfixée par apiUrl", async () => {
        const axios = makeFakeAxios({ audioUrl: "/audio/y.ogg" });
        const ea = new ExcuseAudio({ apiUrl: "http://api", authHeaders, audioCache: makeFakeCache(), axios, logger: silentLogger });
        await ea.tryGenerateAudioFromText("t", false);
        assert.strictEqual(axios.calls.get[0].url, "http://api/audio/y.ogg");
    });
    test("pas d'audio_url dans la réponse → null", async () => {
        const axios = makeFakeAxios({ audioUrl: null });
        const ea = new ExcuseAudio({ apiUrl: "http://api", authHeaders, audioCache: makeFakeCache(), axios, logger: silentLogger });
        assert.strictEqual(await ea.tryGenerateAudioFromText("t", false), null);
        assert.strictEqual(axios.calls.get.length, 0);
    });
    test("axios.post throw → null (fallback texte)", async () => {
        const axios = makeFakeAxios({ postThrows: true });
        const ea = new ExcuseAudio({ apiUrl: "http://api", authHeaders, audioCache: makeFakeCache(), axios, logger: silentLogger });
        assert.strictEqual(await ea.tryGenerateAudioFromText("t", false), null);
    });
    test("axios.get throw → null (fallback texte)", async () => {
        const axios = makeFakeAxios({ getThrows: true });
        const ea = new ExcuseAudio({ apiUrl: "http://api", authHeaders, audioCache: makeFakeCache(), axios, logger: silentLogger });
        assert.strictEqual(await ea.tryGenerateAudioFromText("t", false), null);
    });
});

describe("ExcuseAudio — getExcuseAudio", () => {
    test("cache hit → renvoie le buffer caché, ne génère pas", async () => {
        const cached = Buffer.from("CACHED");
        const cache = makeFakeCache({ getReturns: cached });
        const axios = makeFakeAxios();
        const ea = new ExcuseAudio({ apiUrl: "http://api", authHeaders, audioCache: cache, axios, logger: silentLogger });
        const buf = await ea.getExcuseAudio({ kind: "unavailable", isFrench: false });
        assert.strictEqual(buf, cached);
        assert.strictEqual(axios.calls.post.length, 0);
        assert.deepStrictEqual(cache.calls.get, ["unavailable_dioula"]);
    });
    test("construit la clé selon kind/isFrench", async () => {
        const cache = makeFakeCache({ getReturns: Buffer.from("x") });
        const ea = new ExcuseAudio({ apiUrl: "http://api", authHeaders, audioCache: cache, axios: makeFakeAxios(), logger: silentLogger });
        await ea.getExcuseAudio({ kind: "back", isFrench: true });
        await ea.getExcuseAudio({ kind: "unavailable", isFrench: true });
        await ea.getExcuseAudio({ kind: "back", isFrench: false });
        await ea.getExcuseAudio({ kind: "unavailable", isFrench: false });
        assert.deepStrictEqual(cache.calls.get, [
            "back_french", "unavailable_french", "back_dioula", "unavailable_dioula",
        ]);
    });
    test("cache miss + génération OK → renvoie fresh et sauve en cache", async () => {
        const cache = makeFakeCache({ getReturns: null });
        const axios = makeFakeAxios({ audioBytes: "FRESH" });
        const ea = new ExcuseAudio({ apiUrl: "http://api", authHeaders, audioCache: cache, axios, logger: silentLogger });
        const buf = await ea.getExcuseAudio({ kind: "unavailable", isFrench: false });
        assert.strictEqual(buf.toString(), "FRESH");
        // save best-effort (non attendu par getExcuseAudio) — laisser la microtask tourner
        await new Promise((r) => setImmediate(r));
        assert.strictEqual(cache.calls.save.length, 1);
        assert.strictEqual(cache.calls.save[0].key, "unavailable_dioula");
    });
    test("cache miss + génération échoue → null", async () => {
        const cache = makeFakeCache({ getReturns: null });
        const axios = makeFakeAxios({ postThrows: true });
        const ea = new ExcuseAudio({ apiUrl: "http://api", authHeaders, audioCache: cache, axios, logger: silentLogger });
        assert.strictEqual(await ea.getExcuseAudio({ kind: "back", isFrench: true }), null);
        assert.strictEqual(cache.calls.save.length, 0);
    });
    test("getExcuseAudio est bindé (appelable détaché, comme injecté à ResponseSender)", async () => {
        const cache = makeFakeCache({ getReturns: Buffer.from("B") });
        const ea = new ExcuseAudio({ apiUrl: "http://api", authHeaders, audioCache: cache, axios: makeFakeAxios(), logger: silentLogger });
        const detached = ea.getExcuseAudio;
        const buf = await detached({ kind: "unavailable", isFrench: false });
        assert.ok(Buffer.isBuffer(buf));
    });
});

describe("ExcuseAudio — buildCacheEntries / warmup", () => {
    test("buildCacheEntries retourne les 4 entrées fixes", () => {
        const ea = new ExcuseAudio({ apiUrl: "http://api", authHeaders, audioCache: makeFakeCache(), logger: silentLogger });
        const entries = ea.buildCacheEntries();
        assert.strictEqual(entries.length, 4);
        assert.deepStrictEqual(entries.map((e) => e.key), [
            "unavailable_dioula", "unavailable_french", "back_dioula", "back_french",
        ]);
        assert.deepStrictEqual(entries.map((e) => e.isFrench), [false, true, false, true]);
    });
    test("warmup délègue à audioCache.warmup avec les 4 entrées", async () => {
        const cache = makeFakeCache();
        const ea = new ExcuseAudio({ apiUrl: "http://api", authHeaders, audioCache: cache, logger: silentLogger });
        const stats = await ea.warmup();
        assert.strictEqual(cache.calls.warmup.length, 1);
        assert.strictEqual(cache.calls.warmup[0].length, 4);
        assert.strictEqual(stats.generated, 4);
    });
});
