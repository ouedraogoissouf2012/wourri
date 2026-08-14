/**
 * Tests unitaires pour lib/secrets.js (issue #257).
 * Exécution : node --test tests/secrets.test.js
 *
 * Couvre :
 *   - priorité : ${name}_FILE non vide > env brut
 *   - trim du contenu fichier (newline finale des secrets Docker)
 *   - fallback env : _FILE absent, fichier introuvable, fichier vide
 *   - '' quand ni fichier ni env (mode dev)
 *   - warning loggé quand _FILE est défini mais illisible (misconfig visible)
 */
"use strict";

const { test, describe } = require("node:test");
const assert = require("node:assert");
const { readSecret } = require("../lib/secrets");
const { makeFsMock } = require("./_helpers");

describe("readSecret — priorité fichier", () => {
    test("_FILE défini et lisible → contenu du fichier, trim appliqué", () => {
        const fs = makeFsMock({ initial: { "/run/secrets/wouri_api_key": "  cle_fichier  \n" } });
        const env = { WOURI_API_KEY_FILE: "/run/secrets/wouri_api_key", WOURI_API_KEY: "cle_env" };

        assert.strictEqual(readSecret("WOURI_API_KEY", { env, fs }), "cle_fichier");
    });

    test("le fichier gagne même si l'env brut est défini", () => {
        const fs = makeFsMock({ initial: { "/s/k": "du_fichier" } });
        const env = { WOURI_API_KEY_FILE: "/s/k", WOURI_API_KEY: "de_l_env" };

        assert.strictEqual(readSecret("WOURI_API_KEY", { env, fs }), "du_fichier");
    });
});

describe("readSecret — fallbacks env", () => {
    test("_FILE non défini → valeur env brute", () => {
        const fs = makeFsMock();
        const env = { WOURI_API_KEY: "cle_env" };

        assert.strictEqual(readSecret("WOURI_API_KEY", { env, fs }), "cle_env");
    });

    test("fichier introuvable (ENOENT) → fallback env, warning loggé", () => {
        const fs = makeFsMock(); // aucun fichier
        const warns = [];
        const logger = { warn: (...a) => warns.push(a) };
        const env = { WOURI_API_KEY_FILE: "/absent", WOURI_API_KEY: "cle_env" };

        assert.strictEqual(readSecret("WOURI_API_KEY", { env, fs, logger }), "cle_env");
        assert.strictEqual(warns.length, 1);
    });

    test("fichier vide (ou blancs) → fallback env", () => {
        const fs = makeFsMock({ initial: { "/s/vide": "   \n" } });
        const env = { WOURI_API_KEY_FILE: "/s/vide", WOURI_API_KEY: "cle_env" };

        assert.strictEqual(readSecret("WOURI_API_KEY", { env, fs }), "cle_env");
    });

    test("_FILE défini mais chaîne vide → fallback env sans lecture", () => {
        const fs = makeFsMock();
        const env = { WOURI_API_KEY_FILE: "", WOURI_API_KEY: "cle_env" };

        assert.strictEqual(readSecret("WOURI_API_KEY", { env, fs }), "cle_env");
    });

    test("ni fichier ni env → '' (mode dev, auth désactivée)", () => {
        const fs = makeFsMock();

        assert.strictEqual(readSecret("WOURI_API_KEY", { env: {}, fs }), "");
    });

    test("env brut trimé (cohérence avec le contenu fichier)", () => {
        const fs = makeFsMock();
        const env = { WOURI_API_KEY: "  cle_env\n" };

        assert.strictEqual(readSecret("WOURI_API_KEY", { env, fs }), "cle_env");
    });
});

describe("readSecret — défauts d'injection", () => {
    test("sans logger : fichier illisible ne jette pas (fallback silencieux)", () => {
        const fs = makeFsMock();
        const env = { WOURI_API_KEY_FILE: "/absent", WOURI_API_KEY: "x" };

        assert.doesNotThrow(() => readSecret("WOURI_API_KEY", { env, fs }));
    });
});
