/**
 * Tests unitaires pour UserPrefs.
 * Exécution : node --test tests/user_prefs.test.js
 *
 * Couvre :
 *   - validation du constructor (fs + filePath obligatoires)
 *   - load() : fichier absent, JSON valide, JSON corrompu
 *   - save() : appel simple, concurrent (verrou débounce)
 *   - get() : lazy-init avec STEPS.NEW, idempotence
 *   - data : référence live (mutations visibles)
 *   - exports : STEPS, DEFAULT_USER_LANGUAGE
 */
"use strict";

const { test, describe } = require("node:test");
const assert = require("node:assert");
const { UserPrefs, STEPS, DEFAULT_USER_LANGUAGE } = require("../lib/user_prefs");
const { silentLogger, makeFsMock } = require("./_helpers");

describe("UserPrefs — construction", () => {
    test("constructor sans fs jette une erreur", () => {
        assert.throws(
            () => new UserPrefs({ filePath: "/tmp/x.json" }),
            /fs requis/,
        );
    });

    test("constructor sans filePath jette une erreur", () => {
        assert.throws(
            () => new UserPrefs({ fs: makeFsMock() }),
            /filePath requis/,
        );
    });

    test("constructor OK avec fs + filePath, state vide par défaut", () => {
        const prefs = new UserPrefs({
            fs: makeFsMock(),
            filePath: "/tmp/prefs.json",
            logger: silentLogger,
        });
        assert.deepStrictEqual(prefs.data, {});
        assert.strictEqual(prefs.filePath, "/tmp/prefs.json");
    });
});

describe("UserPrefs — load()", () => {
    test("fichier absent → data === {} sans exception", () => {
        const prefs = new UserPrefs({
            fs: makeFsMock(),
            filePath: "/tmp/prefs.json",
            logger: silentLogger,
        });
        prefs.load();
        assert.deepStrictEqual(prefs.data, {});
    });

    test("JSON valide → data peuplé", () => {
        const payload = {
            "user1@s.whatsapp.net": { city: "Abidjan", language: "french", step: "complete" },
            "user2@s.whatsapp.net": { city: "Bouake", language: "dioula", step: "complete" },
        };
        const fs = makeFsMock({
            initial: { "/tmp/prefs.json": JSON.stringify(payload) },
        });
        const prefs = new UserPrefs({ fs, filePath: "/tmp/prefs.json", logger: silentLogger });
        prefs.load();
        assert.deepStrictEqual(prefs.data, payload);
        assert.strictEqual(Object.keys(prefs.data).length, 2);
    });

    test("JSON corrompu → data === {} sans exception (résilience)", () => {
        const fs = makeFsMock({
            initial: { "/tmp/prefs.json": "{ pas du tout du json" },
        });
        const prefs = new UserPrefs({ fs, filePath: "/tmp/prefs.json", logger: silentLogger });
        prefs.load();
        assert.deepStrictEqual(prefs.data, {});
    });
});

describe("UserPrefs — get()", () => {
    test("entrée absente → crée avec step=STEPS.NEW + champs null", () => {
        const prefs = new UserPrefs({
            fs: makeFsMock(),
            filePath: "/tmp/prefs.json",
            logger: silentLogger,
        });
        const entry = prefs.get("user1@s.whatsapp.net");
        assert.strictEqual(entry.city, null);
        assert.strictEqual(entry.language, null);
        assert.strictEqual(entry.step, STEPS.NEW);
        assert.strictEqual(entry.pendingQuestion, null);
        assert.strictEqual(entry.pendingFeedback, null);
    });

    test("appel répété → retourne la même référence (mutations visibles)", () => {
        const prefs = new UserPrefs({
            fs: makeFsMock(),
            filePath: "/tmp/prefs.json",
            logger: silentLogger,
        });
        const e1 = prefs.get("user1");
        e1.city = "Divo";
        e1.step = STEPS.COMPLETE;
        const e2 = prefs.get("user1");
        assert.strictEqual(e1, e2);
        assert.strictEqual(e2.city, "Divo");
        assert.strictEqual(e2.step, STEPS.COMPLETE);
    });

    test("get() crée l'entrée dans data (visible via getter)", () => {
        const prefs = new UserPrefs({
            fs: makeFsMock(),
            filePath: "/tmp/prefs.json",
            logger: silentLogger,
        });
        prefs.get("user1");
        prefs.get("user2");
        assert.strictEqual(Object.keys(prefs.data).length, 2);
    });
});

/** Attend n ticks setImmediate (chaque save = write + rename = 2 hops async). */
async function flushAsync(n = 6) {
    for (let i = 0; i < n; i++) {
        await new Promise((resolve) => setImmediate(resolve));
    }
}

describe("UserPrefs — save() (verrou débounce)", () => {
    test("save() simple écrit une fois le JSON", async () => {
        const fs = makeFsMock();
        const prefs = new UserPrefs({ fs, filePath: "/tmp/prefs.json", logger: silentLogger });
        prefs.get("user1").city = "Abidjan";
        prefs.save();
        await flushAsync();
        assert.strictEqual(fs.writeCalls.length, 1);
        assert.match(fs.writeCalls[0].content, /Abidjan/);
    });

    test("save() concurrent (2 appels rapides) → 2 écritures total via _savePending", async () => {
        const fs = makeFsMock();
        const prefs = new UserPrefs({ fs, filePath: "/tmp/prefs.json", logger: silentLogger });
        prefs.get("user1").city = "Abidjan";
        prefs.save(); // 1er appel → _saveInProgress = true
        prefs.get("user1").city = "Bouake"; // mutation entre les 2 appels
        prefs.save(); // 2e appel → _savePending = true (pas d'écriture immédiate)
        await flushAsync();
        assert.strictEqual(fs.writeCalls.length, 2);
        // Le 2e write doit contenir la mutation "Bouake"
        assert.match(fs.writeCalls[1].content, /Bouake/);
    });

    test("save() concurrent (3 appels rapides) → 2 écritures (3e dédupliqué via _savePending)", async () => {
        const fs = makeFsMock();
        const prefs = new UserPrefs({ fs, filePath: "/tmp/prefs.json", logger: silentLogger });
        prefs.get("user1").city = "A";
        prefs.save();
        prefs.save();
        prefs.save();
        await flushAsync();
        // 1er = exécuté direct, 2e et 3e → _savePending=true (déduplication), donc 2 writes total
        assert.strictEqual(fs.writeCalls.length, 2);
    });

    test("save() avec erreur writeFile → log error, état reset (peut sauvegarder à nouveau)", async () => {
        const fs = makeFsMock({ writeFailsWith: new Error("disk full") });
        const errors = [];
        const prefs = new UserPrefs({
            fs,
            filePath: "/tmp/prefs.json",
            logger: { ...silentLogger, error: (msg) => errors.push(msg) },
        });
        prefs.save();
        await flushAsync();
        assert.strictEqual(errors.length, 1);
        assert.match(errors[0], /disk full/);
        assert.strictEqual(prefs._saveInProgress, false);
    });
});

describe("UserPrefs — save() atomique (tmp + rename)", () => {
    test("save() écrit vers .tmp puis rename vers le fichier final", async () => {
        const fs = makeFsMock();
        const prefs = new UserPrefs({ fs, filePath: "/tmp/prefs.json", logger: silentLogger });
        prefs.get("user1").city = "Abidjan";
        prefs.save();
        await flushAsync();
        // L'écriture cible le .tmp, jamais directement le fichier final
        assert.strictEqual(fs.writeCalls[0].path, "/tmp/prefs.json.tmp");
        // Le rename déplace .tmp → final
        assert.strictEqual(fs.renameCalls.length, 1);
        assert.deepStrictEqual(fs.renameCalls[0], {
            from: "/tmp/prefs.json.tmp",
            to: "/tmp/prefs.json",
        });
        // Résultat : contenu dans le fichier final, pas de .tmp résiduel
        assert.match(fs.files["/tmp/prefs.json"], /Abidjan/);
        assert.strictEqual("/tmp/prefs.json.tmp" in fs.files, false);
    });

    test("échec writeFile → fichier final JAMAIS touché (pas de corruption)", async () => {
        const initial = { "/tmp/prefs.json": '{"user1":{"city":"Abidjan"}}' };
        const fs = makeFsMock({ initial, writeFailsWith: new Error("disk full") });
        const prefs = new UserPrefs({ fs, filePath: "/tmp/prefs.json", logger: silentLogger });
        prefs.load();
        prefs.get("user1").city = "Bouake";
        prefs.save();
        await flushAsync();
        // Le fichier final garde son contenu d'origine intact
        assert.strictEqual(fs.files["/tmp/prefs.json"], '{"user1":{"city":"Abidjan"}}');
        assert.strictEqual(fs.renameCalls.length, 0);
    });

    test("échec rename → log error, état reset, fichier final intact", async () => {
        const initial = { "/tmp/prefs.json": '{"user1":{"city":"Abidjan"}}' };
        const fs = makeFsMock({ initial, renameFailsWith: new Error("EPERM") });
        const errors = [];
        const prefs = new UserPrefs({
            fs,
            filePath: "/tmp/prefs.json",
            logger: { ...silentLogger, error: (msg) => errors.push(msg) },
        });
        prefs.load();
        prefs.save();
        await flushAsync();
        assert.strictEqual(errors.length, 1);
        assert.match(errors[0], /EPERM/);
        assert.strictEqual(prefs._saveInProgress, false);
        assert.strictEqual(fs.files["/tmp/prefs.json"], '{"user1":{"city":"Abidjan"}}');
    });

    test("saveSync() atomique : writeFileSync .tmp + renameSync final (shutdown path)", () => {
        const fs = makeFsMock();
        const prefs = new UserPrefs({ fs, filePath: "/tmp/prefs.json", logger: silentLogger });
        prefs.get("user1").city = "Divo";
        prefs.saveSync();
        assert.strictEqual(fs.writeCalls[0].path, "/tmp/prefs.json.tmp");
        assert.deepStrictEqual(fs.renameCalls[0], {
            from: "/tmp/prefs.json.tmp",
            to: "/tmp/prefs.json",
        });
        assert.match(fs.files["/tmp/prefs.json"], /Divo/);
        assert.strictEqual("/tmp/prefs.json.tmp" in fs.files, false);
    });
});

describe("UserPrefs — data (référence live)", () => {
    test("data est une référence live (Object.entries voit les nouvelles entrées)", () => {
        const prefs = new UserPrefs({
            fs: makeFsMock(),
            filePath: "/tmp/prefs.json",
            logger: silentLogger,
        });
        const dataRef = prefs.data;
        prefs.get("user1").city = "Divo";
        assert.strictEqual(dataRef["user1"].city, "Divo");
    });
});

describe("UserPrefs — exports", () => {
    test("STEPS contient les 5 étapes attendues", () => {
        assert.strictEqual(STEPS.NEW, "new");
        assert.strictEqual(STEPS.WAITING_CITY, "waiting_city");
        assert.strictEqual(STEPS.WAITING_LANGUAGE, "waiting_language");
        assert.strictEqual(STEPS.COMPLETE, "complete");
        assert.strictEqual(STEPS.WAITING_FEEDBACK, "waiting_feedback");
    });

    test("DEFAULT_USER_LANGUAGE === 'french'", () => {
        assert.strictEqual(DEFAULT_USER_LANGUAGE, "french");
    });
});
