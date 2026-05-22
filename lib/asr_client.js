/**
 * Client ASR/STT pour Wourri WhatsApp Server.
 *
 * Encapsule les appels à l'API backend (wouri-api) pour :
 *   - `/api/stt/transcribe`           — Whisper français
 *   - `/api/asr/transcribe-and-translate` — MMS Bambara/Dioula (+ traduction FR + NLU)
 *
 * Le fallback est interne : `transcribeAudioBambara` retombe sur
 * `transcribeAudio` (Whisper FR) si l'ASR Bambara échoue, ce qui préserve
 * la sortie utilisateur même en cas d'indisponibilité du modèle MMS.
 *
 * Toutes les dépendances externes (axios, headers d'auth, logger) sont
 * injectées via le constructeur pour permettre des tests unitaires sans
 * réseau ni filesystem.
 */
"use strict";

const FormData = require("form-data");

// Sprint H.1b (issue #161) — helper local de troncature PII pour les logs.
// Conserve la trace utile (préfixe lisible pour debug) sans exposer le message
// vocal complet de l'utilisateur (PII = données personnelles RGPD/ARTCI).
// Seuil 50 chars : suffisant pour identifier visuellement le contenu, mais
// trop court pour reconstituer un message agricole entier.
function _truncatePII(text, maxLen = 50) {
    // null/undefined/string vide → "" (évite "null" dans les logs et fail-soft
    // pour tout appelant futur qui ne sait pas que l'input peut être absent).
    if (text == null || text === "") return "";
    return text.length > maxLen ? text.slice(0, maxLen) + "..." : text;
}

class AsrClient {
    /**
     * @param {object} options
     * @param {string} options.apiUrl - Base URL de wouri-api (ex: http://localhost:8000)
     * @param {Function} options.authHeaders - () => object, headers d'auth (X-API-Key)
     * @param {object} [options.logger] - Logger avec info/error (défaut: console)
     * @param {object} [options.axios] - Instance axios injectable pour tests
     * @param {number} [options.timeoutMs] - Timeout par requête (défaut: 180000)
     */
    constructor(options = {}) {
        if (!options.apiUrl) {
            throw new Error("AsrClient: apiUrl requis");
        }
        if (typeof options.authHeaders !== "function") {
            throw new Error("AsrClient: authHeaders (function) requis");
        }
        this.apiUrl = options.apiUrl;
        this.authHeaders = options.authHeaders;
        this.logger = options.logger || console;
        this.axios = options.axios || require("axios");
        this.timeoutMs = options.timeoutMs || 180000;
    }

    /**
     * Transcrit un audio via Whisper français.
     * @param {Buffer} audioBuffer
     * @param {string} [filename]
     * @returns {Promise<{text:string, likely_dioula_input:boolean, language_probability:number}|null>}
     */
    async transcribeAudio(audioBuffer, filename = "audio.ogg") {
        try {
            const formData = new FormData();
            formData.append("audio", audioBuffer, {
                filename,
                contentType: "audio/ogg",
            });
            formData.append("language", "fr");

            // Sprint H.2a : format pino objet-contexte (cf. CLAUDE.md "Logging structuré").
            // Sprint H.1b : path-only (pas l'URL complète) pour éviter leak credentials.
            this.logger.info({ path: "/api/stt/transcribe" }, "[STT] Appel API");
            const response = await this.axios.post(
                `${this.apiUrl}/api/stt/transcribe`,
                formData,
                {
                    headers: { ...formData.getHeaders(), ...this.authHeaders() },
                    timeout: this.timeoutMs,
                },
            );
            this.logger.info({ status: response.status }, "[STT] Reponse API recue");

            if (response.data && response.data.text) {
                return {
                    text: response.data.text,
                    likely_dioula_input: response.data.likely_dioula_input || false,
                    language_probability: response.data.language_probability || 0,
                };
            }
            return null;
        } catch (error) {
            // axios v1.x peut laisser error.message vide ou égal à 'Error'.
            // Le vrai motif est dans error.code (ECONNREFUSED, ETIMEDOUT) ou
            // error.response.status (401, 422...).
            const errCode = error.code || error.response?.status || "UNKNOWN";
            // Sprint H.1b : tronquer aussi error.message (peut contenir le body
            // HTTP de l'erreur 422 incl. la transcription PII soumise).
            const errMsg = _truncatePII(error.message || error.toString() || "erreur sans message", 100);
            // Sprint H.2a : format pino objet-contexte.
            // Pino réserve la clé `msg` pour le message de log → utiliser `errMsg`
            // (shorthand `{errMsg}`) pour éviter une collision JSON en sortie.
            this.logger.error({ code: errCode, errMsg }, "[STT] Erreur transcription");
            return null;
        }
    }

    /**
     * Transcrit un audio en Bambara/Dioula via MMS, avec traduction FR + NLU.
     * Fallback automatique vers `transcribeAudio` (Whisper FR) si l'ASR Bambara échoue.
     *
     * @param {Buffer} audioBuffer
     * @param {string} [filename]
     * @returns {Promise<{text:string, bambara_text:string, is_bambara:boolean}|null>}
     */
    async transcribeAudioBambara(audioBuffer, filename = "audio.ogg") {
        try {
            const formData = new FormData();
            formData.append("audio", audioBuffer, {
                filename,
                contentType: "audio/ogg",
            });
            formData.append("language", "bam");

            // Sprint H.2a : format pino objet-contexte. H.1b : path-only.
            this.logger.info(
                { path: "/api/asr/transcribe-and-translate" },
                "[ASR-BAMBARA] Appel API",
            );
            const response = await this.axios.post(
                `${this.apiUrl}/api/asr/transcribe-and-translate`,
                formData,
                {
                    headers: { ...formData.getHeaders(), ...this.authHeaders() },
                    timeout: this.timeoutMs,
                },
            );
            this.logger.info({ status: response.status }, "[ASR-BAMBARA] Reponse API recue");

            if (response.data) {
                const transcription = response.data.transcription || "";
                const frenchTranslation = response.data.french_translation || "";
                const nluMessage = response.data.nlu_message || "";

                // Sprint H.2a : format pino objet-contexte. H.1b : PII tronquée.
                // Le préfixe tronqué reste dans le champ objet (transcription/translation/nlu)
                // pour traçabilité Loki/Datadog ; le msg reste invariant pour les alertes.
                this.logger.info(
                    { transcription: _truncatePII(transcription) },
                    "[ASR-BAMBARA] Transcription Bambara",
                );
                this.logger.info(
                    { translation: _truncatePII(frenchTranslation) },
                    "[ASR-BAMBARA] Traduction Francais",
                );
                if (nluMessage) {
                    this.logger.info(
                        { nlu: _truncatePII(nluMessage) },
                        "[ASR-BAMBARA] Message NLU (prioritaire)",
                    );
                }

                return {
                    text: nluMessage || frenchTranslation || transcription,
                    bambara_text: transcription,
                    is_bambara: true,
                };
            }
            return null;
        } catch (error) {
            const errCode = error.code || error.response?.status || "UNKNOWN";
            // Sprint H.1b : tronquer error.message (cf. catch STT ci-dessus).
            const errMsg = _truncatePII(error.message || error.toString() || "erreur sans message", 100);
            // Sprint H.2a : format pino objet-contexte.
            // Pino réserve `msg` — `errMsg` shorthand pour éviter collision (cf. STT).
            this.logger.error({ code: errCode, errMsg }, "[ASR-BAMBARA] Erreur transcription");
            this.logger.info("[ASR-BAMBARA] Fallback vers Whisper francais...");
            return await this.transcribeAudio(audioBuffer, filename);
        }
    }
}

module.exports = { AsrClient };
