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


// Fix #309 — mots-parasites : le garde tolérant accepte tout mot alphabétique
// plausible (petites communes CI hors KNOWN_CITIES), il faut donc rejeter
// explicitement le bruit courant en onboarding (salutations, confirmations,
// politesse). Formes NORMALISÉES (accents retirés, minuscules). Aucune n'est
// un nom de ville CI. Externalisé en constante (pas de hardcoding inline).
const _PARASITE_WORDS = new Set([
    // Salutations
    "salut", "slt", "bonjour", "bjr", "bonsoir", "bsr", "coucou", "allo",
    "hello", "hey", "yo", "cc",
    // Confirmations / réponses
    "ok", "oki", "okay", "oui", "non", "yes", "no", "ouais", "daccord", "dacc",
    // Politesse
    "merci", "svp", "stp", "bienvenue",
    // Filler / hors-sujet fréquents
    "comment", "pourquoi", "quoi", "test", "aide", "help", "stop", "rien",
    "bien", "super", "cool", "voila", "cava", "nickel",
    // Mots génériques FR (non-ville) fréquents à l'étape ville : commandes,
    // termes géographiques génériques, négations. Aucun n'est une commune CI.
    "ville", "village", "commune", "quartier", "changer", "modifier",
    "inconnu", "inconnue", "region", "pays", "zone", "endroit", "lieu",
    "sais", "connais",
]);

// Longueur minimale (en lettres) d'un mot pour être considéré comme une ville
// plausible. Aligné sur extractCity (étape 5 : `w.length > 3`), c.-à-d. le mot
// qui serait RÉELLEMENT extrait et stocké. Rejette les fragments courts
// ("bou", "ko", "xyz") tout en acceptant les communes CI ("Oumé" = 4 lettres).
const _MIN_PLAUSIBLE_CITY_LETTERS = 4;

/**
 * Normalise une saisie pour matching insensible aux accents et à la casse :
 * décomposition NFD + suppression des diacritiques + minuscules + suppression
 * des apostrophes (M'Bahiakro → mbahiakro) + trim. Corrige #309 (les villes
 * KNOWN sont en ASCII : `Odienné` doit matcher `odienne`).
 *
 * @param {string} s
 * @returns {string}
 */
function _normalizeForMatch(s) {
    return s
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "") // retire les diacritiques combinants
        .toLowerCase()
        .replace(/['’]/g, "") // apostrophes droite (') + typographique (’)
        .trim();
}

/**
 * Vrai si `norm` (déjà normalisé, ASCII) correspond à une ville connue
 * (KNOWN_CITIES ou CITY_CORRECTIONS), en exact-match puis word-boundary.
 * @param {string} norm
 * @returns {boolean}
 */
function _matchesKnownCity(norm) {
    if (KNOWN_CITIES.includes(norm) || CITY_CORRECTIONS[norm]) return true;

    const words = norm.split(/\s+/);
    for (const word of words) {
        if (KNOWN_CITIES.includes(word) || CITY_CORRECTIONS[word]) return true;
    }

    // Word-boundary (patterns ASCII pré-compilés) : `norm` est désormais ASCII
    // après normalisation NFD, donc `\b...\b` matche aussi les saisies accentuées.
    for (const pattern of _CITY_CORRECTION_PATTERNS) {
        if (pattern.test(norm)) return true;
    }
    return _KNOWN_CITIES_PATTERNS.some((pattern) => pattern.test(norm));
}

/**
 * Garde tolérant (#309) : accepte une saisie PLAUSIBLE hors KNOWN_CITIES
 * (petites communes CI). Vrai s'il existe au moins un mot alphabétique
 * suffisamment long qui n'est pas un parasite connu. Rejette le bruit évident
 * (emoji, salutations, confirmations, mots trop courts).
 * @param {string} norm
 * @returns {boolean}
 */
function _isPlausibleCityInput(norm) {
    const words = norm.split(/\s+/).filter(Boolean);
    return words.some((word) => {
        const letters = word.replace(/[^a-z]/g, "");
        return letters.length >= _MIN_PLAUSIBLE_CITY_LETTERS && !_PARASITE_WORDS.has(word);
    });
}

function isValidCity(text) {
    if (typeof text !== "string") return false;

    // Sprint H.2b (issue #161) — borne anti-DoS (cohérent avec extractCity H.1a).
    const safeText = text.length > MAX_TEXT_LENGTH ? text.slice(0, MAX_TEXT_LENGTH) : text;
    // Fix #309 — normalisation NFD (accents/casse/apostrophes) AVANT tout match :
    // `Odienné`, `Séguéla`, `M'Bahiakro` doivent matcher les entrées ASCII.
    const norm = _normalizeForMatch(safeText);
    if (!norm) return false;

    // 1) Ville connue (désormais accent-insensible).
    if (_matchesKnownCity(norm)) return true;

    // 2) Garde tolérant (#309) : accepter une saisie plausible hors des ~60
    //    KNOWN_CITIES (les agriculteurs de petites communes CI doivent pouvoir
    //    terminer l'onboarding), rejeter uniquement le bruit évident.
    return _isPlausibleCityInput(norm);
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
