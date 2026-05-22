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

function isValidCity(text) {
    const normalized = text.toLowerCase().trim();
    for (const wrong of Object.keys(CITY_CORRECTIONS)) {
        if (normalized.includes(wrong)) return true;
    }
    return KNOWN_CITIES.some((city) =>
        normalized.includes(city) || city.includes(normalized)
    );
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
