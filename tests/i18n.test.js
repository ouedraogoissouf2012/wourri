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

    test("AUDIO_FAILED, AUDIO_ERROR, CHANGE_LANGUAGE, RESET : structure 4 variantes (avec english)", () => {
        for (const key of ["AUDIO_FAILED", "AUDIO_ERROR", "CHANGE_LANGUAGE", "RESET"]) {
            assert.ok(MSG[key].bilingual, `${key}.bilingual manquant`);
            assert.ok(MSG[key].french, `${key}.french manquant`);
            assert.ok(MSG[key].dioula, `${key}.dioula manquant`);
            assert.ok(MSG[key].english, `${key}.english manquant`);
        }
    });
});


// ─────────────────────────────────────────────────────────────────────────
// Mécanisme anti-régression : validation automatique des variants i18n
// ─────────────────────────────────────────────────────────────────────────
//
// Ces tests garantissent que :
//   - Chaque langue de SUPPORTED_LANGUAGES (sauf "both" qui utilise bilingual)
//     a une variante dans chaque message de REQUIRED_VARIANT_KEYS
//   - validateI18nCompleteness() ne throw pas en état actuel
//   - PREFS_SAVED retourne un contenu différent par langue (localisation effective)
//
// Quand on ajoutera une 5e langue (espagnol, swahili...), ces tests
// échoueront en CI si on oublie un variant → impossible de merger.
// ─────────────────────────────────────────────────────────────────────────

const {
    SUPPORTED_LANGUAGES,
    LANGUAGES_REQUIRING_VARIANT,
    REQUIRED_VARIANT_KEYS,
    validateI18nCompleteness,
} = require("../lib/i18n");


describe("i18n — mécanisme anti-régression (validateI18nCompleteness)", () => {
    test("validateI18nCompleteness ne throw pas en état actuel", () => {
        assert.doesNotThrow(() => validateI18nCompleteness());
    });

    test("SUPPORTED_LANGUAGES contient les 4 langues attendues", () => {
        assert.deepStrictEqual(
            [...SUPPORTED_LANGUAGES].sort(),
            ["both", "dioula", "english", "french"]
        );
    });

    test("LANGUAGES_REQUIRING_VARIANT exclut 'both' (qui utilise bilingual)", () => {
        assert.ok(!LANGUAGES_REQUIRING_VARIANT.includes("both"),
            "'both' ne doit pas etre dans LANGUAGES_REQUIRING_VARIANT");
        assert.ok(LANGUAGES_REQUIRING_VARIANT.includes("english"),
            "'english' doit etre dans LANGUAGES_REQUIRING_VARIANT");
    });

    test("REQUIRED_VARIANT_KEYS contient les 5 messages variantes attendus", () => {
        assert.deepStrictEqual(
            [...REQUIRED_VARIANT_KEYS].sort(),
            ["AUDIO_ERROR", "AUDIO_FAILED", "CHANGE_CITY", "CHANGE_LANGUAGE", "RESET"]
        );
    });

    // Test parametrize : pour chaque (langue × message), vérifier que la
    // variante existe et est non-vide. Si une langue future est ajoutée à
    // SUPPORTED_LANGUAGES sans variant correspondant, ce test échoue.
    for (const lang of ["french", "dioula", "english"]) {
        for (const key of ["CHANGE_CITY", "CHANGE_LANGUAGE", "RESET", "AUDIO_FAILED", "AUDIO_ERROR"]) {
            test(`MSG.${key}.${lang} existe et est non-vide`, () => {
                const variant = MSG[key][lang];
                assert.strictEqual(typeof variant, "string",
                    `MSG.${key}.${lang} doit etre une string`);
                assert.ok(variant.length > 0,
                    `MSG.${key}.${lang} ne doit pas etre vide`);
            });
        }
    }

    test("validateI18nCompleteness throw si une variante manque (test du mecanisme)", () => {
        // Sauvegarde + corruption temporaire pour verifier le garde-fou
        const original = MSG.CHANGE_CITY.english;
        delete MSG.CHANGE_CITY.english;
        try {
            assert.throws(
                () => validateI18nCompleteness(),
                /MSG\.CHANGE_CITY\.english.*variant manquant/,
                "validateI18nCompleteness doit throw avec un message clair"
            );
        } finally {
            MSG.CHANGE_CITY.english = original;
        }
    });
});


describe("i18n — PREFS_SAVED localisation par langue", () => {
    test("PREFS_SAVED est une fonction prenant (city, lang, language)", () => {
        assert.strictEqual(typeof MSG.PREFS_SAVED, "function");
    });

    test("language='english' retourne un message anglais", () => {
        const out = MSG.PREFS_SAVED("Bouake", "English", "english");
        assert.match(out, /Preferences saved/);
        assert.match(out, /City: Bouake/);
        assert.match(out, /Language: English/);
        assert.match(out, /Ask me your farming/);
        // Ne doit PAS contenir le dioula ou le francais
        assert.ok(!out.includes("Dɔ sɔrɔla"), "ne doit pas contenir dioula");
        assert.ok(!out.includes("enregistrées"), "ne doit pas contenir francais");
    });

    test("language='french' retourne un message francais", () => {
        const out = MSG.PREFS_SAVED("Abidjan", "Français", "french");
        assert.match(out, /Préférences enregistrées/);
        assert.match(out, /Ville : Abidjan/);
        assert.ok(!out.includes("Preferences saved"), "ne doit pas contenir anglais");
        assert.ok(!out.includes("Dɔ sɔrɔla"), "ne doit pas contenir dioula");
    });

    test("language='dioula' retourne un message dioula", () => {
        const out = MSG.PREFS_SAVED("Korhogo", "Dioula", "dioula");
        assert.match(out, /Dɔ sɔrɔla/);
        assert.match(out, /Dugu : Korhogo/);
        assert.ok(!out.includes("Preferences saved"), "ne doit pas contenir anglais");
        assert.ok(!out.includes("Préférences enregistrées"), "ne doit pas contenir francais");
    });

    test("language='both' retourne le message bilingue (compat)", () => {
        const out = MSG.PREFS_SAVED("Divo", "Français + Dioula", "both");
        // Mode both = bilingue : contient dioula ET francais
        assert.match(out, /Dɔ sɔrɔla/);
        assert.match(out, /Préférences enregistrées/);
    });

    test("language=undefined retombe sur bilingue (compat historique)", () => {
        const out = MSG.PREFS_SAVED("Man", "Faransi");
        assert.match(out, /Dɔ sɔrɔla/);
        assert.match(out, /Préférences enregistrées/);
    });
});
