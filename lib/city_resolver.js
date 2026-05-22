/**
 * Résolution et extraction de noms de villes ivoiriennes depuis du texte libre
 * (issu de STT vocal ou de saisie utilisateur).
 *
 * Stratégie :
 *   1. Lookup dans CITY_CORRECTIONS (mot entier puis sous-chaîne avec word-boundary)
 *   2. Lookup dans KNOWN_CITIES avec word-boundary
 *   3. Fuzzy match Levenshtein (seuil 0.8, uniquement mots >= 4 chars pour éviter
 *      les faux positifs sur "man" / "kon")
 *   4. Fallback : dernier mot significatif (probable nom de ville)
 *
 * Aucune dépendance externe.
 */
"use strict";

const KNOWN_CITIES = [
    "abidjan", "bouake", "yamoussoukro", "korhogo", "san-pedro", "san pedro",
    "daloa", "divo", "man", "gagnoa", "bonoua", "soubre", "abengourou",
    "ferkessedougou", "ferke", "odienne", "seguela", "bondoukou", "aboisso",
    "danane", "duekoue", "guiglo", "tabou", "sassandra", "grand-bassam",
    "jacqueville", "agboville", "dabou", "dimbokro", "toumodi", "tiebissou",
    "katiola", "boundiali", "tengrela", "anyama", "bingerville", "bouafle",
    "issia", "lakota", "sinfra", "vavoua", "zuenoula", "beoumi", "sakassou",
    "botro", "daoukro", "bocanda", "mbahiakro", "prikro", "agnibilekrou",
    "tanda", "transua", "nassian", "bouna", "doropo", "tehini", "kong",
];

const CITY_CORRECTIONS = {
    // Man
    "main": "man", "mane": "man", "mens": "man", "mang": "man", "mont": "man",
    // Bouake
    "bouaké": "bouake", "bouakais": "bouake", "bouakay": "bouake",
    // Korhogo
    "corogo": "korhogo", "korogho": "korhogo", "korhogho": "korhogo",
    // San-Pedro
    "sampedro": "san-pedro", "san pédro": "san-pedro", "saint pedro": "san-pedro",
    // Yamoussoukro
    "yamoussokro": "yamoussoukro", "yamouso": "yamoussoukro", "yamoussou": "yamoussoukro",
    // Daloa
    "dalois": "daloa", "dalwa": "daloa",
    // Gagnoa
    "ganyoa": "gagnoa", "ganoa": "gagnoa",
    // Divo
    "divos": "divo", "divot": "divo",
    // Abidjan
    "abijan": "abidjan", "abidjan": "abidjan",
    // Bonoua
    "bonouat": "bonoua", "bonois": "bonoua",
    // Ferkessedougou
    "ferké": "ferkessedougou", "ferke": "ferkessedougou",
    // Grand-Bassam
    "bassam": "grand-bassam", "gran bassam": "grand-bassam",
    // Kong
    "kong": "kong", "con": "kong", "quand": "kong",
};

// Sprint H.2b — Regex pré-compilées au niveau module pour `isValidCity` étape 3.
// Évite ~55 instanciations `new RegExp(...)` à chaque message WhatsApp entrant
// (régression perf détectée par reviewer multi-axes H.2b, confidence 82 %).
//
// Filtre ASCII-only : `\b...\b` n'est pas fiable autour de caractères non-ASCII
// (`é`, accentués) en regex JavaScript. Les clés contenant des diacritiques
// sont déjà couvertes par l'étape 2 (split + exact match), donc on les exclut
// ici pour éviter un comportement indéfini.
//
// Note : `extractCity` (lignes ~136 + ~144) compile aussi ses regex inline.
// Dette pré-existante hors scope H.2b — sera traitée dans un sprint dédié si
// la perf devient critique.
const _ASCII_REGEX = /^[a-z\s-]+$/;
const _CITY_CORRECTION_PATTERNS = Object.keys(CITY_CORRECTIONS)
    .filter((wrong) => _ASCII_REGEX.test(wrong))
    .map((wrong) => new RegExp("\\b" + wrong.replace(/[-]/g, "\\-") + "\\b"));
const _KNOWN_CITIES_PATTERNS = KNOWN_CITIES
    .filter((city) => _ASCII_REGEX.test(city))
    .map((city) => new RegExp("\\b" + city.replace(/[-]/g, "\\-") + "\\b"));


function isValidCity(text) {
    // Sprint H.2b (issue #161) — borne anti-DoS (cohérent avec extractCity H.1a).
    // Sans cette borne, un input pathologique 10k+ chars provoque ~55 scans
    // String.prototype.includes coûteux + N regex pour CITY_CORRECTIONS.
    const safeText = text.length > MAX_TEXT_LENGTH ? text.slice(0, MAX_TEXT_LENGTH) : text;
    const normalized = safeText.toLowerCase().trim();

    // Sprint H.2b — aligner sur extractCity (cascade exact-match → word-boundary).
    //
    // Étape 1 : exact match dictionnaire (mot entier OU phrase entière).
    // Nécessaire pour les clés CITY_CORRECTIONS contenant des diacritiques
    // (`bouaké`, `ferké`, `san pédro`) car `\b...\b` regex ne traite pas
    // correctement les caractères non-ASCII en bordure de mot.
    if (CITY_CORRECTIONS[normalized]) return true;
    if (KNOWN_CITIES.includes(normalized)) return true;

    // Étape 2 : exact match sur chaque mot (split whitespace).
    // Couvre "je suis a bouaké" → mot "bouaké" trouve la correction.
    // Étape filet diacritiques (cf. NICE-1 review H.2b).
    const words = normalized.split(/\s+/);
    for (const word of words) {
        if (CITY_CORRECTIONS[word]) return true;
        if (KNOWN_CITIES.includes(word)) return true;
    }

    // Étape 3 : word-boundary regex (ASCII only — patterns pré-compilés).
    // Élimine les faux positifs où une sous-chaîne courte de ville
    // (ex. "bou", "ko", "da") renvoyait true. Asymétrie avec extractCity
    // (qui utilise word-boundary étapes 2-3) corrigée.
    for (const pattern of _CITY_CORRECTION_PATTERNS) {
        if (pattern.test(normalized)) return true;
    }
    return _KNOWN_CITIES_PATTERNS.some((pattern) => pattern.test(normalized));
}

/** Distance d'édition de Levenshtein entre deux chaînes. */
function levenshtein(a, b) {
    const m = a.length;
    const n = b.length;
    const dp = Array.from({ length: m + 1 }, (_, i) => [i, ...Array(n).fill(0)]);
    for (let j = 0; j <= n; j++) dp[0][j] = j;
    for (let i = 1; i <= m; i++) {
        for (let j = 1; j <= n; j++) {
            dp[i][j] = a[i - 1] === b[j - 1]
                ? dp[i - 1][j - 1]
                : 1 + Math.min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]);
        }
    }
    return dp[m][n];
}

// Sprint H.1a (issue #161) — bornes anti-DoS sur la passe Levenshtein O(n*m).
// Un message d'agriculteur normal fait 10-100 chars. Limite WhatsApp = 4096.
// Sans ces bornes, un input attaquant (10k+ chars) bloque le CPU pendant
// plusieurs secondes (cf. agent_security_rules.md §1 DoS).
const MAX_TEXT_LENGTH = 500;        // borne dure d'entrée (message > 500 chars = anormal)
const MAX_FUZZY_WORDS = 30;         // boucle fuzzy plafonnée à 30 mots
const MAX_WORD_LENGTH_FUZZY = 30;   // mots > 30 chars suspects, skip dans fuzzy

function extractCity(text) {
    // Sprint H.1a — borne d'entrée anti-DoS. Tronque les input anormalement longs
    // avant tout traitement. 500 chars couvre 99.9 % des messages réels d'utilisateurs.
    const safeText = text.length > MAX_TEXT_LENGTH ? text.slice(0, MAX_TEXT_LENGTH) : text;
    const normalized = safeText.toLowerCase().trim();
    const words = normalized.split(/\s+/);

    // 1. Corrections STT — mot entier
    for (const word of words) {
        if (CITY_CORRECTIONS[word]) {
            const corrected = CITY_CORRECTIONS[word];
            return corrected.charAt(0).toUpperCase() + corrected.slice(1);
        }
    }

    // 2. Corrections STT — sous-chaîne avec word-boundary (noms composés)
    for (const [wrong, correct] of Object.entries(CITY_CORRECTIONS)) {
        const pattern = new RegExp("\\b" + wrong.replace(/[-]/g, "\\-") + "\\b");
        if (pattern.test(normalized)) {
            return correct.charAt(0).toUpperCase() + correct.slice(1);
        }
    }

    // 3. KNOWN_CITIES — word-boundary
    for (const city of KNOWN_CITIES) {
        const pattern = new RegExp("\\b" + city.replace(/[-]/g, "\\-") + "\\b");
        if (pattern.test(normalized)) {
            return city.charAt(0).toUpperCase() + city.slice(1);
        }
    }

    // 4. Levenshtein fuzzy match (seuil 0.8, mots >= 4 chars)
    // Sprint H.1a — bornes anti-DoS : limite nombre de mots évalués + longueur max.
    // Levenshtein(word, city) est O(word.length * city.length), donc on cap pour
    // éviter qu'un mot pathologique (>30 chars) ne fasse exploser le temps de calcul.
    for (const word of words.slice(0, MAX_FUZZY_WORDS)) {
        if (word.length < 4 || word.length > MAX_WORD_LENGTH_FUZZY) continue;
        for (const city of KNOWN_CITIES) {
            if (city.length < 4) continue;
            const maxLen = Math.max(word.length, city.length);
            const similarity = 1 - levenshtein(word, city) / maxLen;
            if (similarity >= 0.8) {
                return city.charAt(0).toUpperCase() + city.slice(1);
            }
        }
    }

    // 5. Fallback : dernier mot significatif
    const lastWord = words.filter((w) => w.length > 3).pop() || safeText.trim();
    return lastWord.charAt(0).toUpperCase() + lastWord.slice(1).toLowerCase();
}

module.exports = { extractCity, isValidCity, KNOWN_CITIES, CITY_CORRECTIONS };
