/**
 * Tests pour lib/human_delays.js — profils de délais "simulation humaine".
 *
 * Couvre :
 *   - Les 3 profils (natural / fast / off) résolvent les bonnes bornes
 *   - Défaut sans env var → profil "fast"
 *   - Sélection via HUMAN_DELAY_PROFILE (y compris casse/espaces)
 *   - Surcharge par paramètre (prioritaire sur l'env var)
 *   - Profil inconnu → fallback "fast" + warning loggé (une seule fois)
 *   - Invariants structurels : mêmes clés dans tous les profils, min <= max,
 *     "off" strictement à zéro, "fast" strictement plus court que "natural"
 */
"use strict";

const { test, describe, beforeEach, afterEach } = require("node:test");
const assert = require("node:assert/strict");

const { getDelays, PROFILES, DEFAULT_PROFILE } = require("../lib/human_delays");

const DELAY_KEYS = [
    "read",
    "beforeSend",
    "beforeAudio",
    "textToAudio",
    "feedback",
    "error",
    "onboarding",
];

// Sauvegarde/restauration de l'env var entre les tests
let savedEnv;
beforeEach(() => {
    savedEnv = process.env.HUMAN_DELAY_PROFILE;
    delete process.env.HUMAN_DELAY_PROFILE;
});
afterEach(() => {
    if (savedEnv === undefined) {
        delete process.env.HUMAN_DELAY_PROFILE;
    } else {
        process.env.HUMAN_DELAY_PROFILE = savedEnv;
    }
});

describe("human_delays — sélection de profil", () => {
    test("sans env var → profil par défaut (fast)", () => {
        assert.strictEqual(DEFAULT_PROFILE, "fast");
        assert.deepStrictEqual(getDelays(), PROFILES.fast);
    });

    test("HUMAN_DELAY_PROFILE=natural → valeurs historiques", () => {
        process.env.HUMAN_DELAY_PROFILE = "natural";
        const d = getDelays();
        assert.deepStrictEqual(d.read, [500, 1000]);
        assert.deepStrictEqual(d.beforeSend, [300, 800]);
        assert.deepStrictEqual(d.beforeAudio, [1000, 2000]);
        assert.deepStrictEqual(d.textToAudio, [500, 1000]);
        assert.deepStrictEqual(d.feedback, [500, 1000]);
        assert.deepStrictEqual(d.error, [500, 1000]);
        assert.deepStrictEqual(d.onboarding, [1000, 2000]);
    });

    test("HUMAN_DELAY_PROFILE=off → tout à [0, 0]", () => {
        process.env.HUMAN_DELAY_PROFILE = "off";
        const d = getDelays();
        for (const key of DELAY_KEYS) {
            assert.deepStrictEqual(d[key], [0, 0], `off.${key} doit etre [0,0]`);
        }
    });

    test("casse et espaces tolérés (\" Natural \" → natural)", () => {
        process.env.HUMAN_DELAY_PROFILE = " Natural ";
        assert.deepStrictEqual(getDelays(), PROFILES.natural);
    });

    test("paramètre explicite prioritaire sur l'env var", () => {
        process.env.HUMAN_DELAY_PROFILE = "natural";
        assert.deepStrictEqual(getDelays("off"), PROFILES.off);
    });
});

describe("human_delays — profil inconnu", () => {
    test("profil inconnu → fallback fast + warning une seule fois", () => {
        const warnings = [];
        const fakeLogger = { warn: (msg) => warnings.push(msg) };

        const d1 = getDelays("profil_inexistant", fakeLogger);
        const d2 = getDelays("profil_inexistant", fakeLogger);

        assert.deepStrictEqual(d1, PROFILES.fast);
        assert.deepStrictEqual(d2, PROFILES.fast);
        // Warning dédupliqué : 1 seule entrée malgré 2 appels
        assert.strictEqual(warnings.length, 1);
        assert.match(warnings[0], /profil_inexistant/i);
    });
});

describe("human_delays — invariants structurels", () => {
    test("tous les profils exposent les mêmes clés de délai", () => {
        for (const [profileName, table] of Object.entries(PROFILES)) {
            assert.deepStrictEqual(
                Object.keys(table).sort(),
                [...DELAY_KEYS].sort(),
                `profil "${profileName}" doit avoir exactement les cles standard`
            );
        }
    });

    test("chaque délai est [min, max] avec 0 <= min <= max", () => {
        for (const [profileName, table] of Object.entries(PROFILES)) {
            for (const [key, range] of Object.entries(table)) {
                assert.strictEqual(range.length, 2, `${profileName}.${key} doit etre une paire`);
                const [min, max] = range;
                assert.ok(min >= 0, `${profileName}.${key} min >= 0`);
                assert.ok(min <= max, `${profileName}.${key} min <= max`);
            }
        }
    });

    test("fast est strictement plus court que natural sur chaque délai", () => {
        for (const key of DELAY_KEYS) {
            const [, fastMax] = PROFILES.fast[key];
            const [naturalMin] = PROFILES.natural[key];
            assert.ok(
                fastMax <= naturalMin,
                `fast.${key} max (${fastMax}) doit etre <= natural.${key} min (${naturalMin})`
            );
        }
    });
});
