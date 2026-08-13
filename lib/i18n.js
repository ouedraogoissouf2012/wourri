/**
 * Messages multi-langues Wourri (Dioula CI v1.9 + Français + Anglais + Bilingue).
 *
 * ## Format des messages
 *
 * - **String fixe** : message non-localisé (WELCOME, ASK_CITY, LANGUAGE_UNKNOWN
 *   — affichés avant que l'utilisateur ait choisi sa langue, donc bilingues
 *   par nature).
 * - **Fonction `(args, language)`** : message localisé paramétré (PREFS_SAVED,
 *   CITY_OK). Le caller passe `language` en dernier argument.
 * - **Objet `{bilingual, french, dioula, english, ...}`** : message localisé
 *   sans paramètres (CHANGE_*, RESET, AUDIO_*). Le helper `pickMsg(msg, lang)`
 *   choisit la variante. Fallback : `bilingual` puis ordre déclaration.
 *
 * ## Garde-fou — `validateI18nCompleteness()`
 *
 * Appelée au require du module. Vérifie que CHAQUE langue listée dans
 * `SUPPORTED_LANGUAGES` a une variante dans CHAQUE clé de
 * `REQUIRED_VARIANT_KEYS`. Si une variante manque, throw immédiatement avec
 * un message clair indiquant la clé et la langue manquantes.
 *
 * **Bénéfice** : quand on ajoutera une 5e langue (espagnol, swahili...), il
 * sera **impossible** d'oublier un variant — le serveur refusera de démarrer
 * et les tests parametrize échoueront en CI avant tout merge.
 *
 * ## Pour ajouter une nouvelle langue
 *
 *   1. Ajouter la valeur dans `SUPPORTED_LANGUAGES`
 *   2. Ajouter le variant correspondant dans CHAQUE message de
 *      `REQUIRED_VARIANT_KEYS`
 *   3. Étendre `PREFS_SAVED` avec une nouvelle branche if (language === ...)
 *   4. Étendre `pickMsg` avec une nouvelle ligne (4-5 lignes max)
 *
 * Le test `tests/i18n.test.js::TestI18nCompleteness` itère sur toutes les
 * langues et garantit qu'aucune n'est oubliée.
 *
 * Aucune dépendance externe.
 */
"use strict";

/**
 * Langues supportées par le système i18n. Ajouter ici déclenche la validation
 * pour toutes les `REQUIRED_VARIANT_KEYS`.
 *
 * `bilingual` n'est PAS dans cette liste car ce n'est pas une langue
 * utilisateur — c'est le fallback affiché avant choix langue ou en mode `both`.
 */
const SUPPORTED_LANGUAGES = ["french", "dioula", "both", "english"];

/**
 * Messages qui DOIVENT avoir un variant pour chaque langue de
 * `SUPPORTED_LANGUAGES`. `validateI18nCompleteness()` vérifie au démarrage.
 *
 * Note `both` : ce mode utilise par convention `bilingual` (le caller détecte
 * et fallback). C'est pourquoi `both` n'a pas besoin de son propre variant.
 *
 * Note `english` (ajouté ADR-0015) : chaque message ici doit avoir une clé
 * `english` distincte des autres variants.
 */
const REQUIRED_VARIANT_KEYS = [
    "CHANGE_CITY",
    "CHANGE_LANGUAGE",
    "RESET",
    "AUDIO_FAILED",
    "AUDIO_ERROR",
];

/**
 * Langues qui doivent avoir un variant explicite dans chaque message de
 * `REQUIRED_VARIANT_KEYS`. `both` est exclu car il utilise `bilingual`
 * comme fallback (convention historique pre-ADR-0015).
 */
const LANGUAGES_REQUIRING_VARIANT = SUPPORTED_LANGUAGES.filter(
    (lang) => lang !== "both"
);


const MSG = {
    WELCOME:
        `🌾 *Aw ni tile ! N tɔgɔ ye WOURI ye.*\nSɛnnɛkɛlaw ka dɛmɛbaga — Côte d'Ivoire ni Mali.\n\n📍 Aw bɛ min dugu la ?\n(Aw ka dugu tɔgɔ ci : Abidjan, Bouaké, Divo, Bonoua...)\n\n---\n🌾 *Bienvenue sur WOURI !*\nVotre assistant agricole.\n📍 Dans quelle ville êtes-vous ?`,

    ASK_CITY:
        `📍 Aw bɛ min dugu la sisan ?\n(Aw ka dugu tɔgɔ ci)\n\n---\nDans quelle ville êtes-vous maintenant ?`,

    CITY_UNKNOWN:
        `❓ N ma dugu tɔgɔ dɔn. Aw ka dugu tɔgɔ ci kokura.\n(Misali : Abidjan, Bouaké, Divo, Bonoua, San Pédro...)\n\n---\nJe ne reconnais pas cette ville. Réessayez svp.\n(Ex : Abidjan, Bouaké, Divo, Bonoua, San Pédro...)`,

    CITY_OK: (city) =>
        `✅ Dugu tɔgɔ : *${city}*\n\n🗣️ Aw bɛ kuma jaki la ?\n\n1️⃣ Faransi\n2️⃣ Dioula\n3️⃣ Fila fila (Faransi + Dioula audio)\n4️⃣ 🇬🇧 English\n\n(1, 2, 3 wala 4 ci)\n\n---\nVille : *${city}*\n🗣️ Langue préférée ?\n1️⃣ Français  2️⃣ Dioula  3️⃣ Les deux  4️⃣ 🇬🇧 English`,

    LANGUAGE_UNKNOWN:
        `❓ N ma faamu. 1, 2, 3 wala 4 ci.\n\n1️⃣ Faransi\n2️⃣ Dioula\n3️⃣ Fila fila\n4️⃣ 🇬🇧 English\n\n---\nI didn't understand. Reply 1, 2, 3 or 4.\nJe n'ai pas compris. Répondez 1, 2, 3 ou 4.`,

    // PREFS_SAVED : message de confirmation post-onboarding, localise selon
    // la langue choisie. Si `language` est undefined ou 'both', retourne le
    // contenu bilingue historique (compat).
    PREFS_SAVED: (city, lang, language) => {
        if (language === "english") {
            return `✅ *Preferences saved!*\n📍 City: ${city}\n🗣️ Language: ${lang}\n\n💡 To change: type "change language" or "change city"\n\nAsk me your farming question! 🌱`;
        }
        if (language === "french") {
            return `✅ *Préférences enregistrées !*\n📍 Ville : ${city}\n🗣️ Langue : ${lang}\n\n💡 Pour changer : dites "changer ville" ou "changer langue"\n\nPosez-moi votre question agricole ! 🌱`;
        }
        if (language === "dioula") {
            return `✅ *Dɔ sɔrɔla !*\n📍 Dugu : ${city}\n🗣️ Kuma : ${lang}\n\n💡 Aw b'a fɛ ka yɛlɛma : "changer ville" wala "changer langue"\n\nAw ka ɲinini ci sɛnnɛ koo la ! 🌱`;
        }
        // both / undefined → bilingue (compat historique)
        return `✅ *Dɔ sɔrɔla !*\n📍 Dugu : ${city}\n🗣️ Kuma : ${lang}\n\n💡 Aw b'a fɛ ka yɛlɛma : "changer ville" wala "changer langue"\n\nAw ka ɲinini ci sɛnnɛ koo la ! 🌱\n\n---\n✅ *Préférences enregistrées !*\n💡 Pour changer : dites "changer ville" ou "changer langue"`;
    },

    CHANGE_CITY: {
        bilingual: `📍 Dugu wɛrɛ tɔgɔ ci.\n\n---\nDans quelle ville êtes-vous maintenant ?`,
        french: `📍 Dans quelle ville êtes-vous maintenant ?`,
        dioula: `📍 Dugu wɛrɛ tɔgɔ ci.`,
        english: `📍 Which city are you in now?`,
    },

    CHANGE_LANGUAGE: {
        bilingual: `🗣️ Kuma jaki la ?\n\n1️⃣ Faransi\n2️⃣ Dioula\n3️⃣ Fila fila\n4️⃣ 🇬🇧 English\n\n---\nQuelle langue préférée ? (1, 2, 3 ou 4)`,
        french: `🗣️ Quelle langue préférée ?\n\n1️⃣ Français\n2️⃣ Dioula\n3️⃣ Les deux\n4️⃣ 🇬🇧 English\n\n(Répondez 1, 2, 3 ou 4)`,
        dioula: `🗣️ Kuma jaki la ?\n\n1️⃣ Faransi\n2️⃣ Dioula\n3️⃣ Fila fila\n4️⃣ 🇬🇧 English\n\n(1, 2, 3 wala 4 ci)`,
        english: `🗣️ Which language do you prefer?\n\n1️⃣ Français\n2️⃣ Dioula\n3️⃣ Both\n4️⃣ 🇬🇧 English\n\n(Reply 1, 2, 3 or 4)`,
    },

    RESET: {
        bilingual: `🔄 Dɔ bɛɛ kɛra kura. Kumakan dɔ ci.\n\n---\nPréférences réinitialisées. Envoyez un message pour recommencer.`,
        french: `🔄 Préférences réinitialisées. Envoyez un message pour recommencer.`,
        dioula: `🔄 Dɔ bɛɛ kɛra kura. Kumakan dɔ ci.`,
        english: `🔄 Preferences reset. Send a message to start over.`,
    },

    AUDIO_FAILED: {
        bilingual: `🎤 N ma i ka kumakan faamu. I ka a lasɔgɔ tugu.\n\n---\nJe n'ai pas compris votre message vocal. Pouvez-vous répéter ?`,
        french: `🎤 Je n'ai pas compris votre message vocal. Pouvez-vous répéter ?`,
        dioula: `🎤 N ma i ka kumakan faamu. I ka a lasɔgɔ tugu.`,
        english: `🎤 I didn't understand your voice message. Could you repeat?`,
    },

    AUDIO_ERROR: {
        bilingual: `⚠️ Kumakan in ma se ka bɔ. I ka sɛbɛn fɛ ɲinini ci.\n\n---\nImpossible de traiter ce message vocal. Écrivez votre question.`,
        french: `⚠️ Impossible de traiter ce message vocal. Écrivez votre question.`,
        dioula: `⚠️ Kumakan in ma se ka bɔ. I ka sɛbɛn fɛ ɲinini ci.`,
        english: `⚠️ Cannot process this voice message. Please type your question.`,
    },
};


/**
 * Vérifie que CHAQUE langue de `LANGUAGES_REQUIRING_VARIANT` a une variante
 * dans CHAQUE clé de `REQUIRED_VARIANT_KEYS`. Si une variante manque, throw
 * une erreur claire au démarrage du serveur.
 *
 * Garde-fou contre l'oubli de variant quand on ajoute une nouvelle langue.
 * Appelé automatiquement au require du module (fail-fast).
 *
 * @throws {Error} avec le détail des variants manquants
 */
function validateI18nCompleteness() {
    const missing = [];
    for (const key of REQUIRED_VARIANT_KEYS) {
        const msg = MSG[key];
        if (!msg || typeof msg !== "object") {
            missing.push(`${key} : message inexistant ou pas un objet variants`);
            continue;
        }
        for (const lang of LANGUAGES_REQUIRING_VARIANT) {
            if (typeof msg[lang] !== "string" || msg[lang].length === 0) {
                missing.push(`MSG.${key}.${lang} (variant manquant ou vide)`);
            }
        }
    }
    if (missing.length > 0) {
        throw new Error(
            `[i18n] Variants manquants détectés au chargement :\n` +
            missing.map((m) => `  - ${m}`).join("\n") +
            `\n\nPour ajouter une langue : voir docstring lib/i18n.js section ` +
            `"Pour ajouter une nouvelle langue".`
        );
    }
}


/**
 * Retourne la variante de message adaptée à la langue de l'utilisateur.
 *
 * @param {string|object} msg - String fixe OU objet {bilingual, french, dioula, english}
 * @param {string} [language] - 'french' | 'dioula' | 'both' | 'english' | undefined
 * @returns {string} Le texte adapté (mode 'both' ou inconnu → bilingual)
 */
function pickMsg(msg, language) {
    if (typeof msg === "string") return msg;
    if (!msg || typeof msg !== "object") return "";
    if (language === "french" && msg.french) return msg.french;
    if (language === "dioula" && msg.dioula) return msg.dioula;
    if (language === "english" && msg.english) return msg.english;
    return msg.bilingual || msg.french || msg.dioula || msg.english || "";
}

/**
 * Détecte une commande de changement (ville / langue / reset) dans un texte FR.
 * @returns {'city'|'language'|'reset'|null}
 */
function detectChangeCommand(text) {
    const lower = text.toLowerCase();
    if (lower.includes("changer") && (lower.includes("ville") || lower.includes("localisation"))) {
        return "city";
    }
    if (lower.includes("changer") && (lower.includes("langue") || lower.includes("language"))) {
        return "language";
    }
    if (lower.includes("reinitialiser") || lower.includes("reset") || lower.includes("recommencer")) {
        return "reset";
    }
    return null;
}


// FAIL-FAST : si une variante manque pour une langue supportée, le serveur
// refuse de démarrer. C'est intentionnel — mieux vaut un crash clair qu'un
// utilisateur qui reçoit du dioula alors qu'il a demandé l'anglais.
validateI18nCompleteness();


module.exports = {
    MSG,
    pickMsg,
    detectChangeCommand,
    // Exporté pour les tests parametrize qui itèrent sur toutes les langues
    SUPPORTED_LANGUAGES,
    LANGUAGES_REQUIRING_VARIANT,
    REQUIRED_VARIANT_KEYS,
    validateI18nCompleteness,
};
