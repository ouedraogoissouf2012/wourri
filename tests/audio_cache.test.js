/**
 * Tests unitaires pour AudioCache.
 * Exécution : node --test tests/audio_cache.test.js
 */
"use strict";

const { test, describe, beforeEach, afterEach } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { AudioCache } = require("../lib/audio_cache");

const silentLogger = {
    info: () => {},
    warn: () => {},
    error: () => {},
};

describe("AudioCache — construction", () => {
    test("constructor sans cacheDir jette une erreur", () => {
        assert.throws(
            () => new AudioCache({ generateAudio: async () => null }),
            /cacheDir requis/
        );
    });

    test("constructor sans generateAudio jette une erreur", () => {
        assert.throws(
            () => new AudioCache({ cacheDir: "/tmp/x" }),
            /generateAudio/
        );
    });

    test("constructor avec generateAudio non-fonction jette une erreur", () => {
        assert.throws(
            () => new AudioCache({ cacheDir: "/tmp/x", generateAudio: "pas une fonction" }),
            /generateAudio/
        );
    });
});

describe("AudioCache — get/save", () => {
    let tmpDir;
    let cacheDir;

    beforeEach(() => {
        tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "audio-cache-test-"));
        cacheDir = path.join(tmpDir, "audio_cache");
    });

    afterEach(() => {
        try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch (_) {}
    });

    test("get() sur clé absente retourne null (pas d'erreur)", async () => {
        const cache = new AudioCache({
            cacheDir,
            generateAudio: async () => null,
            logger: silentLogger,
        });
        const result = await cache.get("inexistant");
        assert.strictEqual(result, null);
    });

    test("save() puis get() retourne le buffer original", async () => {
        const cache = new AudioCache({
            cacheDir,
            generateAudio: async () => null,
            logger: silentLogger,
        });
        const buffer = Buffer.from("contenu audio fictif", "utf-8");
        await cache.save("test_key", buffer);
        const retrieved = await cache.get("test_key");
        assert.ok(retrieved);
        assert.strictEqual(retrieved.toString("utf-8"), "contenu audio fictif");
    });

    test("save() crée le dossier de cache si absent", async () => {
        assert.strictEqual(fs.existsSync(cacheDir), false);
        const cache = new AudioCache({
            cacheDir,
            generateAudio: async () => null,
            logger: silentLogger,
        });
        await cache.save("test", Buffer.from("xyz"));
        assert.strictEqual(fs.existsSync(cacheDir), true);
        assert.strictEqual(fs.existsSync(path.join(cacheDir, "test.ogg")), true);
    });

    test("get() sur fichier vide retourne null (audio corrompu)", async () => {
        fs.mkdirSync(cacheDir, { recursive: true });
        fs.writeFileSync(path.join(cacheDir, "vide.ogg"), Buffer.alloc(0));
        const cache = new AudioCache({
            cacheDir,
            generateAudio: async () => null,
            logger: silentLogger,
        });
        const result = await cache.get("vide");
        assert.strictEqual(result, null);
    });

    test("save() écrase une entrée existante", async () => {
        const cache = new AudioCache({
            cacheDir,
            generateAudio: async () => null,
            logger: silentLogger,
        });
        await cache.save("k", Buffer.from("v1"));
        await cache.save("k", Buffer.from("v2-plus-long"));
        const retrieved = await cache.get("k");
        assert.strictEqual(retrieved.toString("utf-8"), "v2-plus-long");
    });
});

describe("AudioCache — warmup", () => {
    let tmpDir;
    let cacheDir;

    beforeEach(() => {
        tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "audio-cache-test-"));
        cacheDir = path.join(tmpDir, "audio_cache");
    });

    afterEach(() => {
        try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch (_) {}
    });

    test("warmup() génère et sauvegarde les entrées manquantes", async () => {
        let calls = 0;
        const cache = new AudioCache({
            cacheDir,
            generateAudio: async (text, isFrench) => {
                calls++;
                return Buffer.from(`audio:${text}:${isFrench}`);
            },
            logger: silentLogger,
        });
        const stats = await cache.warmup([
            { key: "a", text: "alpha", isFrench: true },
            { key: "b", text: "beta", isFrench: false },
        ]);
        assert.strictEqual(calls, 2);
        assert.strictEqual(stats.generated, 2);
        assert.strictEqual(stats.cached, 0);
        assert.strictEqual(stats.failed, 0);
        const got = await cache.get("a");
        assert.strictEqual(got.toString("utf-8"), "audio:alpha:true");
    });

    test("warmup() ne re-génère pas les entrées déjà cachées", async () => {
        let calls = 0;
        const cache = new AudioCache({
            cacheDir,
            generateAudio: async (text) => {
                calls++;
                return Buffer.from(`audio:${text}`);
            },
            logger: silentLogger,
        });
        // Première passe : remplit le cache
        await cache.warmup([{ key: "a", text: "alpha", isFrench: true }]);
        assert.strictEqual(calls, 1);
        // Seconde passe : cache déjà rempli, pas de nouvel appel
        const stats = await cache.warmup([{ key: "a", text: "alpha", isFrench: true }]);
        assert.strictEqual(calls, 1);
        assert.strictEqual(stats.generated, 0);
        assert.strictEqual(stats.cached, 1);
    });

    test("warmup() compte les échecs si generateAudio renvoie null", async () => {
        const cache = new AudioCache({
            cacheDir,
            generateAudio: async () => null, // simule API down
            logger: silentLogger,
        });
        const stats = await cache.warmup([
            { key: "a", text: "alpha", isFrench: true },
            { key: "b", text: "beta", isFrench: false },
        ]);
        assert.strictEqual(stats.generated, 0);
        assert.strictEqual(stats.failed, 2);
        assert.strictEqual(await cache.get("a"), null);
    });

    test("warmup() continue malgré une erreur ponctuelle", async () => {
        let n = 0;
        const cache = new AudioCache({
            cacheDir,
            generateAudio: async (text) => {
                n++;
                if (n === 1) throw new Error("API timeout");
                return Buffer.from(`audio:${text}`);
            },
            logger: silentLogger,
        });
        const stats = await cache.warmup([
            { key: "a", text: "alpha", isFrench: true },
            { key: "b", text: "beta", isFrench: false },
        ]);
        assert.strictEqual(stats.failed, 1);
        assert.strictEqual(stats.generated, 1);
        assert.strictEqual(await cache.get("a"), null);
        assert.ok(await cache.get("b"));
    });

    test("warmup() retourne stats générés/cachés mixés", async () => {
        const cache = new AudioCache({
            cacheDir,
            generateAudio: async (text) => Buffer.from(text),
            logger: silentLogger,
        });
        // Pré-remplir une entrée
        await cache.save("a", Buffer.from("pre-existing"));
        const stats = await cache.warmup([
            { key: "a", text: "alpha", isFrench: true }, // déjà cache
            { key: "b", text: "beta", isFrench: false },  // à générer
        ]);
        assert.strictEqual(stats.cached, 1);
        assert.strictEqual(stats.generated, 1);
        assert.strictEqual(stats.failed, 0);
        // L'entrée pré-existante n'a pas été écrasée
        const a = await cache.get("a");
        assert.strictEqual(a.toString("utf-8"), "pre-existing");
    });
});

describe("AudioCache — persistance disque entre instances", () => {
    let tmpDir;
    let cacheDir;

    beforeEach(() => {
        tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "audio-cache-test-"));
        cacheDir = path.join(tmpDir, "audio_cache");
    });

    afterEach(() => {
        try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch (_) {}
    });

    test("une nouvelle instance retrouve les fichiers de la précédente", async () => {
        const c1 = new AudioCache({
            cacheDir,
            generateAudio: async () => null,
            logger: silentLogger,
        });
        await c1.save("persist", Buffer.from("hello"));

        const c2 = new AudioCache({
            cacheDir,
            generateAudio: async () => null,
            logger: silentLogger,
        });
        const got = await c2.get("persist");
        assert.ok(got);
        assert.strictEqual(got.toString("utf-8"), "hello");
    });
});
