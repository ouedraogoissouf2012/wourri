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

    test("[#309] Bruit trop court → false ; mot plausible (même hors CI) → true (garde tolérant)", () => {
        // #309 : le garde n'est plus une liste blanche stricte des ~60 villes.
        // Un mot alphabétique plausible est accepté (petites communes CI hors
        // KNOWN_CITIES) — au prix d'accepter aussi des mots plausibles non-CI
        // (tradeoff explicitement assumé par l'issue #309).
        assert.strictEqual(isValidCity("xyz"), false);   // 3 lettres → trop court
        assert.strictEqual(isValidCity("paris"), true);  // plausible (non-CI accepté, tradeoff #309)
    });

    test("Sous-chaîne courte de ville connue → false (Sprint H.2b correctif #161)", () => {
        // **Changement de spécification** : avant H.2b, ce test asserait `true`
        // (comportement buggé jugé incorrect — issue #161). Sprint H.2b a corrigé
        // l'asymétrie API : `isValidCity` utilise maintenant
        // word-boundary regex (comme `extractCity` étapes 2-3). Les sous-chaînes
        // courtes ne matchent plus :
        // - 'bou' n'est plus matché comme sous-chaîne de 'bouake'
        // - 'ko' n'est plus matché comme sous-chaîne de 'korhogo' ou 'yamoussoukro'
        // - 'da' n'est plus matché comme sous-chaîne de 'daloa' ou 'yopougon'
        assert.strictEqual(isValidCity("bou"), false);
        assert.strictEqual(isValidCity("ko"), false);
        assert.strictEqual(isValidCity("da"), false);
        assert.strictEqual(isValidCity("be"), false);
    });
});

describe("city_resolver — isValidCity fix #309 (NFD accents + garde tolérant)", () => {
    test("villes KNOWN accentuées correctement écrites → true (normalisation NFD)", () => {
        for (const city of [
            "Odienné", "Séguéla", "Ferkessédougou", "Duékoué", "Danané",
            "Agnibilékrou", "Zuénoula", "Béoumi", "Soubré", "M'Bahiakro",
        ]) {
            assert.strictEqual(isValidCity(city), true, `${city} doit être acceptée`);
        }
    });

    test("petites communes CI hors KNOWN_CITIES → true (garde tolérant)", () => {
        for (const city of [
            "Adzopé", "Tiassalé", "Bongouanou", "Oumé", "Sikensi",
            "Akoupé", "Guitry", "Zoukougbeu",
        ]) {
            assert.strictEqual(isValidCity(city), true, `${city} doit être acceptée`);
        }
    });

    test("bruit évident → false (salutations, confirmations, politesse, emoji, trop court)", () => {
        for (const noise of [
            "Salut", "salut", "ok", "OK", "merci", "Merci", "bonjour",
            "oui", "non", "👍", "😀", "🌾", "", "  ", "ab", "ko",
        ]) {
            assert.strictEqual(isValidCity(noise), false, `${JSON.stringify(noise)} doit être rejeté`);
        }
    });

    test("normalisation accents : casse + diacritiques insensibles", () => {
        assert.strictEqual(isValidCity("ODIENNÉ"), true);
        assert.strictEqual(isValidCity("odienne"), true);
        assert.strictEqual(isValidCity("Odienné"), true);
    });

    test("saisie avec préposition → true (mot ville plausible présent)", () => {
        assert.strictEqual(isValidCity("je suis à Adzopé"), true);
        assert.strictEqual(isValidCity("ville de Oumé"), true);
    });

    test("phrase 100% parasites → false", () => {
        assert.strictEqual(isValidCity("salut merci"), false);
        assert.strictEqual(isValidCity("ok merci bonjour"), false);
    });
});

describe("city_resolver — Sprint H.2b — isValidCity DoS + faux positifs (issue #161)", () => {
    test("DoS borne : input 10 000 chars → < 50ms (preuve MAX_TEXT_LENGTH active)", () => {
        // Sans borne : ~55 regex word-boundary sur 10k chars + ~N substring includes
        // → potentiellement plusieurs centaines de ms. Avec borne 500 chars → rapide.
        const huge = "a".repeat(10000);
        const t0 = Date.now();
        const result = isValidCity(huge);
        const elapsed = Date.now() - t0;
        assert.ok(typeof result === "boolean"); // ne plante pas
        assert.ok(elapsed < 50, `isValidCity 10k chars a pris ${elapsed}ms (attendu < 50ms)`);
    });

    test("Ville complète valide non-régression : 'bouake' → true", () => {
        // Vérifie que le fix word-boundary ne casse pas le golden path.
        assert.strictEqual(isValidCity("bouake"), true);
        assert.strictEqual(isValidCity("abidjan"), true);
        assert.strictEqual(isValidCity("yamoussoukro"), true);
    });

    test("Ville dans une phrase → true (word-boundary fonctionne)", () => {
        // Word-boundary matche au milieu de phrase mais pas en sous-chaîne arbitraire.
        assert.strictEqual(isValidCity("je suis a bouake"), true);
        assert.strictEqual(isValidCity("bonjour abidjan ca va"), true);
        assert.strictEqual(isValidCity("daloa est ma ville"), true);
    });

    test("Correction STT 'main' → true (Man) ; word-boundary ne matche pas 'mainstream' comme ville", () => {
        // CITY_CORRECTIONS contient "main" → "man". Word-boundary matche "main"
        // mot entier mais pas "main" en préfixe de "mainstream".
        assert.strictEqual(isValidCity("main"), true);
        // #309 : "mainstream" n'est PAS reconnu comme la ville Man (word-boundary),
        // mais le garde tolérant l'accepte comme mot alphabétique plausible.
        assert.strictEqual(isValidCity("mainstream"), true);
    });

    test("[#309] Vide/emoji/parasite → false ; phrase avec un mot plausible → true (tradeoff)", () => {
        assert.strictEqual(isValidCity(""), false);       // vide
        assert.strictEqual(isValidCity("👍"), false);      // emoji seul
        assert.strictEqual(isValidCity("salut"), false);  // salutation (parasite)
        // Le bruit ciblé = salutations/emoji/trop court, pas les phrases quelconques :
        // une phrase contenant un mot alphabétique plausible passe le garde.
        assert.strictEqual(isValidCity("paris est belle"), true);
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
