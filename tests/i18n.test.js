/**
 * Tests unitaires pour i18n.
 * Exécution : node --test tests/i18n.test.js
 *
 * Couvre :
 *   - pickMsg : sélection bilingual/french/dioula selon prefs.language
 *   - detectChangeCommand : détection commandes "changer ville/langue/reset"
 *   - MSG : présence et structure des messages clés
 */
"use strict";

const { test, describe } = require("node:test");
const assert = require("node:assert");
const { MSG, pickMsg, detectChangeCommand } = require("../lib/i18n");

describe("i18n — pickMsg (sélection de variante)", () => {
    const sample = {
        bilingual: "BILINGUE",
        french: "FRANCAIS",
        dioula: "DIOULA",
    };

    test("string fixe retournée telle quelle (peu importe la langue)", () => {
        assert.strictEqual(pickMsg("texte fixe", "french"), "texte fixe");
        assert.strictEqual(pickMsg("texte fixe", "dioula"), "texte fixe");
        assert.strictEqual(pickMsg("texte fixe", undefined), "texte fixe");
    });

    test("language='french' retourne la variante française", () => {
        assert.strictEqual(pickMsg(sample, "french"), "FRANCAIS");
    });

    test("language='dioula' retourne la variante dioula", () => {
        assert.strictEqual(pickMsg(sample, "dioula"), "DIOULA");
    });

    test("language='both' retombe sur bilingual", () => {
        assert.strictEqual(pickMsg(sample, "both"), "BILINGUE");
    });

    test("language=undefined retombe sur bilingual (mode inconnu)", () => {
        assert.strictEqual(pickMsg(sample, undefined), "BILINGUE");
    });

    test("language='french' mais sans variante .french → fallback bilingual", () => {
        const partial = { bilingual: "BILINGUE", dioula: "DIOULA" };
        assert.strictEqual(pickMsg(partial, "french"), "BILINGUE");
    });

    test("language='dioula' mais sans variante .dioula → fallback bilingual", () => {
        const partial = { bilingual: "BILINGUE", french: "FRANCAIS" };
        assert.strictEqual(pickMsg(partial, "dioula"), "BILINGUE");
    });

    test("objet null/non-objet → chaîne vide", () => {
        assert.strictEqual(pickMsg(null, "french"), "");
        assert.strictEqual(pickMsg(undefined, "french"), "");
        assert.strictEqual(pickMsg(42, "french"), "");
    });
});

describe("i18n — detectChangeCommand", () => {
    test("'changer ville' → 'city'", () => {
        assert.strictEqual(detectChangeCommand("changer ville"), "city");
        assert.strictEqual(detectChangeCommand("Je veux changer ville stp"), "city");
    });

    test("'changer localisation' → 'city' (synonyme)", () => {
        assert.strictEqual(detectChangeCommand("changer localisation"), "city");
    });

    test("'changer langue' → 'language'", () => {
        assert.strictEqual(detectChangeCommand("changer langue"), "language");
        assert.strictEqual(detectChangeCommand("CHANGER LANGUE"), "language");
    });

    test("'changer language' (anglais) → 'language' (synonyme)", () => {
        assert.strictEqual(detectChangeCommand("changer language please"), "language");
    });

    test("'reset' → 'reset'", () => {
        assert.strictEqual(detectChangeCommand("reset"), "reset");
    });

    test("'reinitialiser' → 'reset'", () => {
        assert.strictEqual(detectChangeCommand("je veux reinitialiser"), "reset");
    });

    test("'recommencer' → 'reset'", () => {
        assert.strictEqual(detectChangeCommand("recommencer"), "reset");
    });

    test("texte hors commande → null", () => {
        assert.strictEqual(detectChangeCommand("bonjour"), null);
        assert.strictEqual(detectChangeCommand("changer"), null); // 'changer' seul sans cible
    });
});

describe("i18n — MSG (présence et structure)", () => {
    test("WELCOME contient FR + dioula (bilingue d'onboarding)", () => {
        assert.match(MSG.WELCOME, /WOURI/);
        assert.match(MSG.WELCOME, /Bienvenue/);
    });

    test("CITY_OK est une fonction qui interpole la ville", () => {
        const result = MSG.CITY_OK("Abidjan");
        assert.match(result, /Abidjan/);
        assert.ok(result.includes("Dugu") || result.includes("Ville"));
    });

    test("PREFS_SAVED est une fonction qui interpole city + lang", () => {
        const result = MSG.PREFS_SAVED("Bonoua", "français");
        assert.match(result, /Bonoua/);
        assert.match(result, /français/);
    });

    test("CHANGE_CITY a les 3 variantes (bilingual/french/dioula)", () => {
        assert.ok(MSG.CHANGE_CITY.bilingual);
        assert.ok(MSG.CHANGE_CITY.french);
        assert.ok(MSG.CHANGE_CITY.dioula);
    });

    test("AUDIO_FAILED, AUDIO_ERROR, CHANGE_LANGUAGE, RESET : structure 3 variantes", () => {
        for (const key of ["AUDIO_FAILED", "AUDIO_ERROR", "CHANGE_LANGUAGE", "RESET"]) {
            assert.ok(MSG[key].bilingual, `${key}.bilingual manquant`);
            assert.ok(MSG[key].french, `${key}.french manquant`);
            assert.ok(MSG[key].dioula, `${key}.dioula manquant`);
        }
    });
});
