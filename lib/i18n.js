/**
 * Messages bilingues Wourri (Dioula CI v1.9 + Français).
 *
 * Format des messages post-onboarding (CHANGE_*, RESET, AUDIO_*) :
 *   { bilingual, french, dioula } — 3 variantes selon prefs.language
 *   mode 'both' / langue inconnue → bilingual
 *
 * Les messages d'onboarding initial (WELCOME, ASK_CITY, etc.) restent
 * bilingues (l'utilisateur n'a pas encore choisi sa langue).
 *
 * Aucune dépendance externe.
 */
"use strict";

const MSG = {
    WELCOME:
        `🌾 *Aw ni tile ! N tɔgɔ ye WOURI ye.*\nSɛnnɛkɛlaw ka dɛmɛbaga — Côte d'Ivoire ni Mali.\n\n📍 Aw bɛ min dugu la ?\n(Aw ka dugu tɔgɔ ci : Abidjan, Bouaké, Divo, Bonoua...)\n\n---\n🌾 *Bienvenue sur WOURI !*\nVotre assistant agricole.\n📍 Dans quelle ville êtes-vous ?`,

    ASK_CITY:
        `📍 Aw bɛ min dugu la sisan ?\n(Aw ka dugu tɔgɔ ci)\n\n---\nDans quelle ville êtes-vous maintenant ?`,

    CITY_OK: (city) =>
        `✅ Dugu tɔgɔ : *${city}*\n\n🗣️ Aw bɛ kuma jaki la ?\n\n1️⃣ Faransi\n2️⃣ Dioula\n3️⃣ Fila fila (Faransi + Dioula audio)\n\n(1, 2 wala 3 ci)\n\n---\nVille : *${city}*\n🗣️ Langue préférée ?\n1️⃣ Français  2️⃣ Dioula  3️⃣ Les deux`,

    LANGUAGE_UNKNOWN:
        `❓ N ma faamu. 1, 2 wala 3 ci.\n\n1️⃣ Faransi\n2️⃣ Dioula\n3️⃣ Fila fila\n\n---\nJe n'ai pas compris. Répondez 1, 2 ou 3.`,

    PREFS_SAVED: (city, lang) =>
        `✅ *Dɔ sɔrɔla !*\n📍 Dugu : ${city}\n🗣️ Kuma : ${lang}\n\n💡 Aw b'a fɛ ka yɛlɛma : "changer ville" wala "changer langue"\n\nAw ka ɲinini ci sɛnnɛ koo la ! 🌱\n\n---\n✅ *Préférences enregistrées !*\n💡 Pour changer : dites "changer ville" ou "changer langue"`,

    CHANGE_CITY: {
        bilingual: `📍 Dugu wɛrɛ tɔgɔ ci.\n\n---\nDans quelle ville êtes-vous maintenant ?`,
        french: `📍 Dans quelle ville êtes-vous maintenant ?`,
        dioula: `📍 Dugu wɛrɛ tɔgɔ ci.`,
    },

    CHANGE_LANGUAGE: {
        bilingual: `🗣️ Kuma jaki la ?\n\n1️⃣ Faransi\n2️⃣ Dioula\n3️⃣ Fila fila\n\n---\nQuelle langue préférée ? (1, 2 ou 3)`,
        french: `🗣️ Quelle langue préférée ?\n\n1️⃣ Français\n2️⃣ Dioula\n3️⃣ Les deux\n\n(Répondez 1, 2 ou 3)`,
        dioula: `🗣️ Kuma jaki la ?\n\n1️⃣ Faransi\n2️⃣ Dioula\n3️⃣ Fila fila\n\n(1, 2 wala 3 ci)`,
    },

    RESET: {
        bilingual: `🔄 Dɔ bɛɛ kɛra kura. Kumakan dɔ ci.\n\n---\nPréférences réinitialisées. Envoyez un message pour recommencer.`,
        french: `🔄 Préférences réinitialisées. Envoyez un message pour recommencer.`,
        dioula: `🔄 Dɔ bɛɛ kɛra kura. Kumakan dɔ ci.`,
    },

    AUDIO_FAILED: {
        bilingual: `🎤 N ma i ka kumakan faamu. I ka a lasɔgɔ tugu.\n\n---\nJe n'ai pas compris votre message vocal. Pouvez-vous répéter ?`,
        french: `🎤 Je n'ai pas compris votre message vocal. Pouvez-vous répéter ?`,
        dioula: `🎤 N ma i ka kumakan faamu. I ka a lasɔgɔ tugu.`,
    },

    AUDIO_ERROR: {
        bilingual: `⚠️ Kumakan in ma se ka bɔ. I ka sɛbɛn fɛ ɲinini ci.\n\n---\nImpossible de traiter ce message vocal. Écrivez votre question.`,
        french: `⚠️ Impossible de traiter ce message vocal. Écrivez votre question.`,
        dioula: `⚠️ Kumakan in ma se ka bɔ. I ka sɛbɛn fɛ ɲinini ci.`,
    },
};

/**
 * Retourne la variante de message adaptée à la langue de l'utilisateur.
 *
 * @param {string|object} msg - String fixe OU objet {bilingual, french, dioula}
 * @param {string} [language] - 'french' | 'dioula' | 'both' | undefined
 * @returns {string} Le texte adapté (mode 'both' ou inconnu → bilingual)
 */
function pickMsg(msg, language) {
    if (typeof msg === "string") return msg;
    if (!msg || typeof msg !== "object") return "";
    if (language === "french" && msg.french) return msg.french;
    if (language === "dioula" && msg.dioula) return msg.dioula;
    return msg.bilingual || msg.french || msg.dioula || "";
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

module.exports = { MSG, pickMsg, detectChangeCommand };
