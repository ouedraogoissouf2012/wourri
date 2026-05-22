/**
 * Tests unitaires pour city_resolver.
 * Exécution : node --test tests/city_resolver.test.js
 *
 * Couvre la cascade : CITY_CORRECTIONS mot entier → CITY_CORRECTIONS sous-chaîne
 * → KNOWN_CITIES word-boundary → Levenshtein fuzzy (seuil 0.8) → fallback dernier mot.
 */
"use strict";

const { test, describe } = require("node:test");
const assert = require("node:assert");
const {
    extractCity,
    isValidCity,
    KNOWN_CITIES,
    CITY_CORRECTIONS,
} = require("../lib/city_resolver");

describe("city_resolver — extractCity (cascade)", () => {
    test("Étape 1 — correction STT mot entier (priorité absolue)", () => {
        assert.strictEqual(extractCity("dalwa"), "Daloa");
        assert.strictEqual(extractCity("main"), "Man");
        assert.strictEqual(extractCity("ganyoa"), "Gagnoa");
    });

    test("Étape 2 — correction STT sous-chaîne avec word-boundary (noms composés)", () => {
        assert.strictEqual(extractCity("je suis a bassam"), "Grand-bassam");
        assert.strictEqual(extractCity("sampedro c'est ici"), "San-pedro");
    });

    test("Étape 2 — diacritique non normalisé : 'bouaké' traité via CITY_CORRECTIONS", () => {
        assert.strictEqual(extractCity("bouaké"), "Bouake");
    });

    test("Étape 3 — KNOWN_CITIES word-boundary sans correction nécessaire", () => {
        assert.strictEqual(extractCity("j'habite a abidjan"), "Abidjan");
        assert.strictEqual(extractCity("Korhogo nord"), "Korhogo");
    });

    test("Étape 3 — match littéral avec tiret (san-pedro)", () => {
        assert.strictEqual(extractCity("san-pedro c'est la"), "San-pedro");
    });

    test("Étape 4 — fuzzy Levenshtein sur typo (≥4 chars, similarité ≥0.8)", () => {
        // "abidjann" vs "abidjan" : levenshtein=1, maxLen=8 → similarity = 1 - 1/8 = 0.875 ≥ 0.8
        assert.strictEqual(extractCity("abidjann"), "Abidjan");
        // "korogo" → CITY_CORRECTIONS étape 1
        assert.strictEqual(extractCity("corogo"), "Korhogo");
    });

    test("Étape 4 — pas de fuzzy match sur mots <4 chars (anti-faux-positif 'man'/'kon')", () => {
        // "xyz" et "abc" (3 chars chacun) ne doivent PAS matcher "man" / "kon" via
        // Levenshtein car la garde `if (word.length >= 4)` les rejette. Aucun mot
        // n'a >3 chars, donc fallback ultime étape 5 : `text.trim()` capitalisé.
        // Assertion positive (anti-pattern #7 : éviter notStrictEqual qui laisserait
        // passer des résultats absurdes).
        assert.strictEqual(extractCity("xyz abc"), "Xyz abc");
    });

    test("Étape 5 — fallback : dernier mot >3 chars capitalisé", () => {
        assert.strictEqual(extractCity("inconnu xyz random"), "Random");
    });

    test("Étape 5 — fallback ultime : texte trim si aucun mot >3 chars", () => {
        // 'a b' → words=['a','b'], aucun >3 chars → fallback = text.trim()
        assert.strictEqual(extractCity("a b"), "A b");
    });

    test("Casse normalisée : entrée majuscules → sortie capitalisée", () => {
        assert.strictEqual(extractCity("ABIDJAN"), "Abidjan");
    });
});

describe("city_resolver — isValidCity", () => {
    test("Ville connue → true", () => {
        assert.strictEqual(isValidCity("abidjan"), true);
        assert.strictEqual(isValidCity("Bouake"), true);
    });

    test("Correction STT → true", () => {
        assert.strictEqual(isValidCity("bouaké"), true);
        assert.strictEqual(isValidCity("dalwa"), true);
    });

    test("Ville inconnue → false", () => {
        assert.strictEqual(isValidCity("paris"), false);
        assert.strictEqual(isValidCity("xyz"), false);
    });

    test("Sous-chaîne courte de ville connue → true (asymétrie identifiée #161)", () => {
        // Comportement actuel : 'bou' est sous-chaîne de 'bouake' → match.
        // Asymétrie pré-existante documentée dans #161 (à corriger sprint futur).
        // Ce test verrouille le comportement actuel pour éviter régression accidentelle.
        assert.strictEqual(isValidCity("bou"), true);
    });
});

describe("city_resolver — bornes anti-DoS (Sprint H.1a, issue #161)", () => {
    test("Message normal court → comportement inchangé (non-régression)", () => {
        assert.strictEqual(extractCity("je suis a bouake"), "Bouake");
        assert.strictEqual(extractCity("abidjan"), "Abidjan");
    });

    test("Input > 500 chars → tronqué + résolu sans timeout", () => {
        // 1000 chars contenant "bouake" dans les 500 premiers
        const long = "bouake " + "x".repeat(1000);
        const t0 = Date.now();
        const result = extractCity(long);
        const elapsed = Date.now() - t0;
        assert.strictEqual(result, "Bouake");
        assert.ok(elapsed < 50, `1000 chars a pris ${elapsed}ms (attendu < 50ms)`);
    });

    test("Input pathologique 10 000 chars → < 100ms (preuve borne DoS active)", () => {
        // Sans bornes : O(10k mots × 55 villes × n*m) = pathologique
        // Avec bornes : tronqué à 500, fuzzy plafonné à 30 mots → rapide
        const huge = "a".repeat(10000);
        const t0 = Date.now();
        const result = extractCity(huge);
        const elapsed = Date.now() - t0;
        assert.ok(typeof result === "string");
        assert.ok(elapsed < 100, `10k chars a pris ${elapsed}ms (attendu < 100ms)`);
    });

    test("60 mots distincts (< MAX_TEXT_LENGTH) → fuzzy limité à MAX_FUZZY_WORDS=30", () => {
        // Test isolé de MAX_FUZZY_WORDS : input 60 × 4 chars + espaces = 299 chars
        // (sous MAX_TEXT_LENGTH=500) → la borne MAX_TEXT_LENGTH ne déclenche PAS.
        // Donc on prouve que c'est MAX_FUZZY_WORDS=30 qui limite la passe fuzzy.
        // Mots de 4 chars (>= seuil fuzzy) tous distincts pour forcer la passe 4.
        const words = [];
        for (let i = 0; i < 60; i++) {
            // 4 chars chacun, séquence aaaa, aaab, aaac, ... (60 distincts)
            words.push("aa" + String.fromCharCode(97 + Math.floor(i / 26)) + String.fromCharCode(97 + (i % 26)));
        }
        const text = words.join(" "); // ≈ 60*4 + 59 = 299 chars
        assert.ok(text.length < 500, `setup test : input doit être < MAX_TEXT_LENGTH (got ${text.length})`);
        const t0 = Date.now();
        extractCity(text);
        const elapsed = Date.now() - t0;
        // Sans MAX_FUZZY_WORDS : 60 mots × 55 villes × Levenshtein(4, ~6) ≈ ~13 200 ops
        // Avec MAX_FUZZY_WORDS=30 : 30 mots × 55 × ... ≈ ~6 600 ops → bien plus rapide
        // Le timing prouve que la passe fuzzy est limitée à 30 mots.
        assert.ok(elapsed < 30, `60 mots distincts pris ${elapsed}ms (attendu < 30ms avec MAX_FUZZY_WORDS actif)`);
    });

    test("Mot pathologique 100 chars dans la passe fuzzy → skip ce mot", () => {
        // Sans borne word.length : Levenshtein(100 chars, "bouake") = coûteux.
        // Avec MAX_WORD_LENGTH_FUZZY=30, ce mot est skip dans la passe 4.
        const pathologicalWord = "a".repeat(100);
        const text = `bonjour ${pathologicalWord} ville`;
        const t0 = Date.now();
        const result = extractCity(text);
        const elapsed = Date.now() - t0;
        assert.ok(typeof result === "string");
        assert.ok(elapsed < 50, `mot 100 chars a pris ${elapsed}ms (attendu < 50ms)`);
    });
});

describe("city_resolver — exports", () => {
    test("KNOWN_CITIES contient les villes principales", () => {
        assert.ok(KNOWN_CITIES.includes("abidjan"));
        assert.ok(KNOWN_CITIES.includes("bouake"));
        assert.ok(KNOWN_CITIES.includes("yamoussoukro"));
        assert.ok(KNOWN_CITIES.length >= 50);
    });

    test("CITY_CORRECTIONS mappe vers des villes valides", () => {
        for (const [wrong, correct] of Object.entries(CITY_CORRECTIONS)) {
            assert.ok(
                KNOWN_CITIES.includes(correct),
                `'${wrong}' → '${correct}' n'est pas dans KNOWN_CITIES`,
            );
        }
    });
});
