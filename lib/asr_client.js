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
     * Helper privé : POST audio multipart vers wouri-api. Sprint H.3 (issue #161).
     *
     * Factorise le boilerplate FormData + axios.post + logging Appel/Reponse
     * entre `transcribeAudio` et `transcribeAudioBambara`.
     *
     * **NE catch PAS les exceptions** — propagation au caller qui décide du
     * comportement (return null vs fallback Whisper).
     *
     * @param {object} params
     * @param {string} params.endpoint - path (ex: "/api/stt/transcribe")
     * @param {Buffer} params.audioBuffer
     * @param {string} params.filename
     * @param {string} params.language - "fr" | "bam"
     * @param {string} params.logTag - "[STT]" | "[ASR-BAMBARA]"
     * @returns {Promise<object|null>} response.data (peut être null si réponse vide)
     */
    async _postAudio({ endpoint, audioBuffer, filename, language, logTag }) {
        const formData = new FormData();
        formData.append("audio", audioBuffer, {
            filename,
            contentType: "audio/ogg",
        });
        formData.append("language", language);

        // Sprint H.2a : format pino objet-contexte (cf. CLAUDE.md "Logging structuré").
        // Sprint H.1b : path-only (pas l'URL complète) pour éviter leak credentials.
        this.logger.info({ path: endpoint }, `${logTag} Appel API`);
        const response = await this.axios.post(
            `${this.apiUrl}${endpoint}`,
            formData,
            {
                headers: { ...formData.getHeaders(), ...this.authHeaders() },
                timeout: this.timeoutMs,
            },
        );
        this.logger.info({ status: response.status }, `${logTag} Reponse API recue`);
        return response.data || null;
    }

    /**
     * Helper privé : log d'erreur structuré avec sanitization PII. Sprint H.3.
     *
     * Factorise le catch block (errCode + _truncatePII + logger.error pino).
     */
    _logError(logTag, error) {
        // axios v1.x peut laisser error.message vide ou égal à 'Error'.
        // Le vrai motif est dans error.code (ECONNREFUSED, ETIMEDOUT) ou
        // error.response.status (401, 422...).
        const errCode = error.code || error.response?.status || "UNKNOWN";
        // Sprint H.1b : tronquer error.message (peut contenir le body HTTP 422
        // incl. la transcription PII soumise).
        // Sprint H.2a : `errMsg` (pas `msg`) pour éviter collision clé réservée pino.
        const errMsg = _truncatePII(error.message || error.toString() || "erreur sans message", 100);
        this.logger.error({ code: errCode, errMsg }, `${logTag} Erreur transcription`);
    }

    /**
     * Transcrit un audio via Whisper français.
     * @param {Buffer} audioBuffer
     * @param {string} [filename]
     * @returns {Promise<{text:string, likely_dioula_input:boolean, language_probability:number}|null>}
     */
    async transcribeAudio(audioBuffer, filename = "audio.ogg") {
        try {
            const data = await this._postAudio({
                endpoint: "/api/stt/transcribe",
                audioBuffer, filename,
                language: "fr",
                logTag: "[STT]",
            });
            if (data && data.text) {
                return {
                    text: data.text,
                    likely_dioula_input: data.likely_dioula_input || false,
                    language_probability: data.language_probability || 0,
                };
            }
            return null;
        } catch (error) {
            this._logError("[STT]", error);
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
            const data = await this._postAudio({
                endpoint: "/api/asr/transcribe-and-translate",
                audioBuffer, filename,
                language: "bam",
                logTag: "[ASR-BAMBARA]",
            });
            if (!data) return null;

            const transcription = data.transcription || "";
            const frenchTranslation = data.french_translation || "";
            const nluMessage = data.nlu_message || "";

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
        } catch (error) {
            this._logError("[ASR-BAMBARA]", error);
            this.logger.info("[ASR-BAMBARA] Fallback vers Whisper francais...");
            return await this.transcribeAudio(audioBuffer, filename);
        }
    }
}

module.exports = { AsrClient };
