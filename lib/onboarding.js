/**
 * Machine à états d'onboarding Wourri.
 *
 * Encapsule le flux d'inscription d'un nouvel utilisateur WhatsApp :
 *   NEW → WAITING_CITY → WAITING_LANGUAGE → COMPLETE → WAITING_FEEDBACK → COMPLETE
 *
 * Gère également les commandes de changement (city/language/reset) accessibles
 * uniquement depuis l'état COMPLETE, et le bouclage feedback 👍/👎 après une
 * réponse en mode dioula/both.
 *
 * Contrat de retour de `processStep()` :
 *   - { handled: null }                     → step === COMPLETE (pass-through, le handler traite normal)
 *   - { handled: true }                     → onboarding a répondu, le handler doit `continue`
 *   - { handled: false, newMessageText: X } → l'onboarding est terminé/annulé et il y a une question
 *                                              en attente à traiter ; le handler remplace messageText
 *                                              par X et continue vers le bloc STEPS.COMPLETE
 *
 * Toutes les dépendances externes (sock, userPrefs, axios, authHeaders, logger)
 * sont injectées via le constructeur pour permettre les tests unitaires.
 */
"use strict";

const { STEPS } = require("./user_prefs");
const { MSG, pickMsg, detectChangeCommand } = require("./i18n");
const { extractCity } = require("./city_resolver");
const { sendTextWithPause } = require("./sock_helpers");
const { getDelays } = require("./human_delays");

const FEEDBACK_TIMEOUT_MS = 10000;

// ─────────────────────────────────────────────
// Feedback detection patterns (fix bug #260)
// ─────────────────────────────────────────────
// Word boundary regex pour eviter les collisions substring (cf. bug #260) :
//   - Avant : ["bon", ...].some(k => msgLower.includes(k))
//     → "pas bon" matchait "bon" thumbsUp AVANT "pas bon" thumbsDown.
//     → "te ɲuman" matchait "ɲuman" thumbsUp AVANT "te ɲuman" thumbsDown.
//   - Apres : regex `\b` autour de chaque mot-cle + emoji match exact.
//
// Pattern aligne avec city_resolver.js (PR #199, meme correction de collision).
// Le flag `u` (unicode) garantit que `\b` reconnait correctement les
// caracteres dioula ɲ ɔ ɛ comme appartenant aux mots.
//
// ORDRE D'EVALUATION : thumbsDown TESTE EN PREMIER (defense en profondeur)
// pour que "pas bon" gagne sur "bon" meme si les regex etaient mal alignees.
const _FEEDBACK_THUMBS_DOWN_RE = /\b(?:non|no|mauvais|mal|pas\s+bon|te\s+ɲuman)\b|👎/u;
const _FEEDBACK_THUMBS_UP_RE = /\b(?:oui|yes|bien|ok|super|bon|ɲuman|numan)\b|👍/u;

class OnboardingMachine {
    /**
     * @param {object} options
     * @param {object} options.userPrefs - Instance UserPrefs (pour .save())
     * @param {object} options.axios - Module axios (injectable pour tests)
     * @param {string} options.apiUrl - WOURI_API_URL pour appel feedback
     * @param {Function} options.authHeaders - () => object — headers d'auth X-API-Key
     * @param {Function} options.randomDelay - async (min, max) => Promise<void>
     * @param {object} [options.sock] - Socket Baileys (mutable, assigné post-`makeWASocket`)
     * @param {object} [options.logger] - Logger pino (défaut: console)
     */
    constructor(options = {}) {
        if (!options.userPrefs) {
            throw new Error("OnboardingMachine: userPrefs requis");
        }
        if (!options.axios) {
            throw new Error("OnboardingMachine: axios requis");
        }
        if (!options.apiUrl) {
            throw new Error("OnboardingMachine: apiUrl requis");
        }
        if (typeof options.authHeaders !== "function") {
            throw new Error("OnboardingMachine: authHeaders (function) requis");
        }
        if (typeof options.randomDelay !== "function") {
            throw new Error("OnboardingMachine: randomDelay (function) requis");
        }
        this.userPrefs = options.userPrefs;
        this.axios = options.axios;
        this.apiUrl = options.apiUrl;
        this.authHeaders = options.authHeaders;
        this.randomDelay = options.randomDelay;
        this.sock = options.sock || null;
        this.logger = options.logger || console;
    }

    /**
     * Traite l'étape d'onboarding courante selon `prefs.step`.
     *
     * @param {object} prefs - Référence vers les préférences user (mutable)
     * @param {string} messageText - Texte du message (déjà transcrit si vocal)
     * @param {string} userNumber - Numéro WhatsApp destinataire
     * @param {object} ctx
     * @param {boolean} ctx.isAudioMessage - true si entrée audio raw
     * @param {boolean} ctx.isVoiceInput - true si vocal (après transcription)
     * @returns {Promise<{handled: boolean|null, newMessageText?: string}>}
     */
    async processStep(prefs, messageText, userNumber, { isAudioMessage, isVoiceInput }) {
        // Guard sock null (Pattern 12 review D.3) : si sock pas encore propagé
        // par connectWhatsApp (race au boot ou reconnect en cours), on ne peut
        // rien envoyer. Retourner { handled: true } évite que le caller tombe
        // dans la phase STEPS.COMPLETE qui crasherait aussi sur sock.sendMessage.
        if (!this.sock) {
            this.logger.warn("[ONBOARDING] sock non initialisé — message ignoré");
            return { handled: true };
        }

        // Commandes de changement (uniquement depuis STEPS.COMPLETE)
        const changeCommand = detectChangeCommand(messageText);
        if (changeCommand && prefs.step === STEPS.COMPLETE) {
            return await this._handleChangeCommand(prefs, userNumber, changeCommand);
        }

        // STEPS.NEW : premier message d'un nouvel utilisateur
        if (prefs.step === STEPS.NEW) {
            return await this._handleNew(prefs, userNumber, messageText);
        }

        // STEPS.WAITING_CITY : capture de la ville
        if (prefs.step === STEPS.WAITING_CITY) {
            return await this._handleWaitingCity(prefs, userNumber, messageText);
        }

        // STEPS.WAITING_LANGUAGE : capture de la langue + traitement pendingQuestion
        if (prefs.step === STEPS.WAITING_LANGUAGE) {
            return await this._handleWaitingLanguage(prefs, userNumber, messageText);
        }

        // STEPS.WAITING_FEEDBACK : capture du retour 👍/👎 (ou vocal qui annule)
        if (prefs.step === STEPS.WAITING_FEEDBACK) {
            return await this._handleWaitingFeedback(
                prefs,
                userNumber,
                messageText,
                { isAudioMessage, isVoiceInput },
            );
        }

        // STEPS.COMPLETE ou step inconnu : pass-through, le handler traite normal
        return { handled: null };
    }

    // ------------------------------------------------------------------
    // Handlers privés par étape
    // ------------------------------------------------------------------

    async _handleChangeCommand(prefs, userNumber, command) {
        if (command === "city") {
            prefs.step = STEPS.WAITING_CITY;
            this.userPrefs.save();
            await sendTextWithPause(this.sock, userNumber, pickMsg(MSG.CHANGE_CITY, prefs.language));
            return { handled: true };
        }
        if (command === "language") {
            prefs.step = STEPS.WAITING_LANGUAGE;
            this.userPrefs.save();
            await sendTextWithPause(this.sock, userNumber, pickMsg(MSG.CHANGE_LANGUAGE, prefs.language));
            return { handled: true };
        }
        if (command === "reset") {
            prefs.step = STEPS.NEW;
            prefs.city = null;
            prefs.language = null;
            prefs.pendingQuestion = null;
            this.userPrefs.save();
            await sendTextWithPause(this.sock, userNumber, pickMsg(MSG.RESET, prefs.language));
            return { handled: true };
        }
        // Cas impossible (detectChangeCommand retourne null|city|language|reset)
        return { handled: null };
    }

    async _handleNew(prefs, userNumber, messageText) {
        // Sauvegarder le message initial comme question en attente — sera reposé
        // après que l'utilisateur ait terminé l'onboarding.
        prefs.pendingQuestion = messageText;
        prefs.step = STEPS.WAITING_CITY;
        this.userPrefs.save();

        await sendTextWithPause(this.sock, userNumber, MSG.WELCOME);
        return { handled: true };
    }

    async _handleWaitingCity(prefs, userNumber, messageText) {
        const cityName = extractCity(messageText);
        prefs.city = cityName;
        prefs.step = STEPS.WAITING_LANGUAGE;
        this.userPrefs.save();

        await sendTextWithPause(this.sock, userNumber, MSG.CITY_OK(cityName));
        return { handled: true };
    }

    async _handleWaitingLanguage(prefs, userNumber, messageText) {
        const input = messageText.trim().toLowerCase();
        let language = null;

        if (input === "1" || input.includes("francais") || input.includes("français")) {
            language = "french";
        } else if (input === "2" || input.includes("dioula") || input.includes("bambara")) {
            language = "dioula";
        } else if (input === "3" || input.includes("deux") || input.includes("both")) {
            language = "both";
        } else if (input === "4" || input.includes("english") || input.includes("anglais")) {
            // ADR-0015 PR 4/4 : mode anglais (passthrough DeepSeek + Piper TTS EN)
            language = "english";
        }

        if (!language) {
            await sendTextWithPause(this.sock, userNumber, MSG.LANGUAGE_UNKNOWN);
            return { handled: true };
        }

        prefs.language = language;
        prefs.step = STEPS.COMPLETE;

        const langText = language === "french" ? "Français" :
                        language === "dioula" ? "Dioula" :
                        language === "english" ? "English" : "Français + Dioula";

        // Passe `language` à PREFS_SAVED pour qu'il retourne la variante
        // de confirmation localisée (ADR-0015 — mécanisme variants i18n).
        await sendTextWithPause(
            this.sock,
            userNumber,
            MSG.PREFS_SAVED(prefs.city, langText, language)
        );

        // Traiter la question en attente s'il y en a une (fall-through au handler)
        if (prefs.pendingQuestion) {
            const newMessageText = prefs.pendingQuestion;
            prefs.pendingQuestion = null;
            this.userPrefs.save();

            await this.randomDelay(...getDelays().onboarding);
            await this.sock.sendPresenceUpdate("composing", userNumber);
            return { handled: false, newMessageText };
        }

        this.userPrefs.save();
        return { handled: true };
    }

    async _handleWaitingFeedback(prefs, userNumber, messageText, { isAudioMessage, isVoiceInput }) {
        // Si l'utilisateur envoie un nouveau vocal pendant le feedback
        // → ignorer le feedback en cours, traiter directement la nouvelle question
        if (isAudioMessage || isVoiceInput) {
            this.logger.info("[FEEDBACK] Nouveau vocal recu → feedback annulé, traitement direct");
            prefs.step = STEPS.COMPLETE;
            prefs.pendingFeedback = null;
            this.userPrefs.save();
            // Le code STEPS.COMPLETE du handler traite directement le messageText.
            return { handled: false, newMessageText: messageText };
        }

        // Feedback texte
        const fb = prefs.pendingFeedback || {};
        const msgLower = messageText.trim().toLowerCase();

        // Detecter thumbsup / thumbsdown via regex word boundary (fix bug #260)
        // thumbsDown teste en PREMIER : "pas bon" doit gagner sur "bon" tout
        // seul. Si thumbsDown match → on ignore thumbsUp (impossible d'avoir
        // les 2 vrais en meme temps avec le pattern word boundary).
        const isThumbsDown = _FEEDBACK_THUMBS_DOWN_RE.test(msgLower);
        const isThumbsUp = !isThumbsDown && _FEEDBACK_THUMBS_UP_RE.test(msgLower);

        if (isThumbsUp || isThumbsDown) {
            const endpoint = isThumbsUp ? "positif" : "negatif";
            try {
                await this.axios.post(`${this.apiUrl}/api/feedback/${endpoint}`, {
                    user_id: userNumber,
                    reponse_bambara: fb.reponse_bambara || "",
                    reponse_fr: fb.reponse_fr || "",
                    intent: fb.intent || "",
                    cultures: fb.cultures || [],
                    source: fb.source || "unknown",
                }, { timeout: FEEDBACK_TIMEOUT_MS, headers: this.authHeaders() });
                this.logger.info(`[FEEDBACK] ${endpoint} enregistre pour intent=${fb.intent}`);
            } catch (fbErr) {
                this.logger.warn(`[FEEDBACK] Erreur appel API: ${fbErr.message}`);
            }

            const confirm = isThumbsUp
                ? "Aw ni ce! 🙏 I ka ladili nɔgɔya n ma."
                : "N bɛ a faamu. N bɛ jɛ ka ɲɛ. 🙏";
            await this.sock.sendMessage(userNumber, { text: confirm });
        } else {
            // Message invalide → re-demander
            await this.sock.sendMessage(userNumber, { text: "I ka jaabi 👍 wala 👎 di." });
        }

        // Reprendre le mode normal
        prefs.step = STEPS.COMPLETE;
        prefs.pendingFeedback = null;
        this.userPrefs.save();
        // [fix H] le handler doit `continue` (et non return), pour traiter les
        // messages suivants du batch. C'est exactement ce que `{ handled: true }`
        // garantit côté caller.
        return { handled: true };
    }
}

module.exports = { OnboardingMachine };
