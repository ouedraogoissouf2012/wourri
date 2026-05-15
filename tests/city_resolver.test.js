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
