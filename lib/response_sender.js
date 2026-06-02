/**
 * Envoi des réponses WhatsApp Wourri selon la langue choisie par l'utilisateur.
 *
 * Règles de format (révisées 2026-05-06, cf. whatsapp-server/CLAUDE.md) :
 *   - `french` + entrée vocale → audio FR (fallback texte FR si audio indispo)
 *   - `french` + entrée texte → texte FR
 *   - `dioula` (vocal ou écrit) → TOUJOURS audio dioula (fallback texte FR si TTS down)
 *   - `both` (vocal ou écrit) → texte FR systématique + audio dioula si dispo
 *
 * `sendExcuse` gère les messages d'excuse (API down, retour après indisponibilité)
 * via des audios pré-générés (audio_cache), avec fallback texte bilingue.
 *
 * Toutes les dépendances externes (sock, axios, logger, getExcuseAudio, EXCUSE_MSG)
 * sont injectées via le constructeur pour permettre les tests unitaires.
 */
"use strict";

const { STEPS } = require("./user_prefs");
const { sendTextWithPause, sendAudioBuffer, AUDIO_MIMETYPE } = require("./sock_helpers");

const FR_FLAG_PREFIX = "🇫🇷";
const EN_FLAG_PREFIX = "🇬🇧";
const AUDIO_TIMEOUT_MS = 30000;

class ResponseSender {
    /**
     * @param {object} options
     * @param {object} [options.sock] - Socket Baileys (mutable : assigné post-`makeWASocket`)
     * @param {object} options.axios - Module axios (injectable pour tests)
     * @param {string} options.apiUrl - WOURI_API_URL pour construire les URL absolues
     * @param {Function} options.randomDelay - async (min, max) => Promise<void>
     * @param {Function} options.getExcuseAudio - async ({kind, isFrench}) => Buffer|null
     * @param {object} options.EXCUSE_MSG - Constantes des textes d'excuse
     * @param {object} [options.logger] - Logger avec info/warn/error (défaut: console)
     */
    constructor(options = {}) {
        if (!options.axios) {
            throw new Error("ResponseSender: axios requis");
        }
        if (!options.apiUrl) {
            throw new Error("ResponseSender: apiUrl requis");
        }
        if (typeof options.randomDelay !== "function") {
            throw new Error("ResponseSender: randomDelay (function) requis");
        }
        if (typeof options.getExcuseAudio !== "function") {
            throw new Error("ResponseSender: getExcuseAudio (function) requis");
        }
        if (!options.EXCUSE_MSG) {
            throw new Error("ResponseSender: EXCUSE_MSG requis");
        }
        this.sock = options.sock || null;
        this.axios = options.axios;
        this.apiUrl = options.apiUrl;
        this.randomDelay = options.randomDelay;
        this.getExcuseAudio = options.getExcuseAudio;
        this.EXCUSE_MSG = options.EXCUSE_MSG;
        this.logger = options.logger || console;
    }

    /**
     * Résout une `audio_url` venue de l'API : absolue (http://...) ou relative (préfixée par apiUrl).
     * @param {string} url
     * @returns {string} URL absolue
     */
    _resolveAudioUrl(url) {
        return url.startsWith("http") ? url : `${this.apiUrl}${url}`;
    }

    /**
     * Préfixe un texte avec le drapeau français.
     * @param {string} text
     * @returns {string}
     */
    _frText(text) {
        return `${FR_FLAG_PREFIX} ${text}`;
    }

    /**
     * Prefixe un texte avec le drapeau anglais (ADR-0015 PR 4/4).
     * @param {string} text
     * @returns {string}
     */
    _enText(text) {
        return `${EN_FLAG_PREFIX} ${text}`;
    }

    /**
     * Télécharge un audio puis l'envoie en note vocale WhatsApp (ptt=true).
     * Encapsule axios.get + presence updates + sendMessage audio.
     *
     * @param {string} userNumber
     * @param {string} audioUrl - URL déjà résolue (absolue)
     * @returns {Promise<void>}
     * @throws Si axios.get ou sendMessage échoue (caller gère le fallback texte)
     */
    async _downloadAndSendAudio(userNumber, audioUrl) {
        const audioResponse = await this.axios.get(audioUrl, {
            responseType: "arraybuffer",
            timeout: AUDIO_TIMEOUT_MS,
        });
        await sendAudioBuffer(this.sock, userNumber, Buffer.from(audioResponse.data), {
            randomDelay: this.randomDelay,
        });
    }

    /**
     * Envoie la réponse principale au handler `messages.upsert` selon la langue
     * configurée par l'utilisateur et le type d'entrée (vocal/texte).
     *
     * Mute `prefs.step` et `prefs.pendingFeedback` puis invoque `saveFn()`
     * uniquement si la langue est dioula/both ET data.meta est présent
     * (prompt feedback C4).
     *
     * @param {object} params
     * @param {object} params.data - Réponse API : {response, audio_url, meta, response_dioula}
     * @param {object} params.prefs - Préférences user (référence live, mutable)
     * @param {boolean} params.isVoiceInput - true si entrée vocale
     * @param {string} params.userNumber - Numéro WhatsApp destinataire
     * @param {Function} params.saveFn - Callback () => userPrefs.save()
     */
    async sendResponse({ data, prefs, isVoiceInput, userNumber, saveFn }) {
        // FRANCAIS
        if (prefs.language === "french") {
            if (isVoiceInput) {
                // Entree vocale -> Reponse audio francais
                // Note: Pour french, l'audio est dans audio_url (pas audio_url_fr)
                if (data.audio_url) {
                    try {
                        await this._downloadAndSendAudio(userNumber, this._resolveAudioUrl(data.audio_url));
                        this.logger.info("[ENVOYE] Audio francais (reponse a vocal)");
                    } catch (audioErr) {
                        this.logger.warn(`[AUDIO FR] Erreur: ${audioErr.message}`);
                        // Fallback: envoyer le texte si audio echoue
                        if (data.response) {
                            await this.sock.sendMessage(userNumber, {
                                text: this._frText(data.response),
                            });
                        }
                    }
                } else if (data.response) {
                    // Pas d'audio disponible, envoyer le texte
                    await this.sock.sendMessage(userNumber, {
                        text: this._frText(data.response),
                    });
                    this.logger.info("[ENVOYE] Texte francais (audio non disponible)");
                }
            } else {
                // Entree texte -> Reponse texte francais
                if (data.response) {
                    await this.sock.sendMessage(userNumber, {
                        text: this._frText(data.response),
                    });
                    this.logger.info("[ENVOYE] Texte francais (reponse a texte)");
                }
            }
        }

        // DIOULA — Règle "selon langue choisie" (révisée 2026-05-06) :
        //   TOUJOURS audio dioula (peu importe vocal/écrit en entrée).
        //   Justification UX : agriculteurs dioula peu alphabétisés, l'audio
        //   est critique pour qu'ils accèdent au contenu. Le texte dioula leur
        //   sert peu. Fallback texte FR seulement si audio indispo (API TTS down).
        else if (prefs.language === "dioula") {
            if (data.audio_url) {
                try {
                    await this._downloadAndSendAudio(userNumber, this._resolveAudioUrl(data.audio_url));
                    this.logger.info("[ENVOYE] Audio dioula (mode dioula)");
                } catch (audioErr) {
                    this.logger.warn(`[AUDIO DIOULA] Erreur, fallback texte FR: ${audioErr.message}`);
                    if (data.response) {
                        await this.sock.sendMessage(userNumber, { text: this._frText(data.response) });
                    }
                }
            } else if (data.response) {
                // Pas d'audio_url disponible -> fallback texte FR
                await this.sock.sendMessage(userNumber, { text: this._frText(data.response) });
                this.logger.info("[ENVOYE] Texte FR (mode dioula, audio_url indispo)");
            }
        }

        // ENGLISH (ADR-0015 PR 4/4 + hotfix) — Règle équivalente FRANCAIS :
        //   - Entrée vocale → audio EN (Piper en_US-amy-medium) avec fallback texte EN
        //   - Entrée texte → texte EN
        //   Pas de feedback C4 (réservé dioula/both — corpus IVR pas applicable EN).
        //   Mode démo investisseurs : DeepSeek direct EN + Piper TTS EN.
        else if (prefs.language === "english") {
            if (isVoiceInput) {
                if (data.audio_url) {
                    try {
                        await this._downloadAndSendAudio(userNumber, this._resolveAudioUrl(data.audio_url));
                        this.logger.info("[ENVOYE] Audio anglais (reponse a vocal)");
                    } catch (audioErr) {
                        this.logger.warn(`[AUDIO EN] Erreur, fallback texte EN: ${audioErr.message}`);
                        if (data.response) {
                            await this.sock.sendMessage(userNumber, {
                                text: this._enText(data.response),
                            });
                        }
                    }
                } else if (data.response) {
                    // Pas d'audio (modele Piper EN absent, etc.) -> texte EN
                    await this.sock.sendMessage(userNumber, {
                        text: this._enText(data.response),
                    });
                    this.logger.info("[ENVOYE] Texte anglais (audio non disponible)");
                }
            } else {
                // Entree texte -> Reponse texte EN
                if (data.response) {
                    await this.sock.sendMessage(userNumber, {
                        text: this._enText(data.response),
                    });
                    this.logger.info("[ENVOYE] Texte anglais (reponse a texte)");
                }
            }
        }

        // BOTH — Règle "selon langue choisie" (révisée 2026-05-06) :
        //   TOUJOURS texte FR + audio dioula (combo, le meilleur des deux).
        //   Permet aux bilingues de profiter des deux formats sans avoir à
        //   choisir entre lire et écouter.
        else if (prefs.language === "both") {
            // 1. Toujours envoyer le texte FR
            if (data.response) {
                await this.sock.sendMessage(userNumber, { text: this._frText(data.response) });
                this.logger.info("[ENVOYE] Texte FR (mode both)");
            }

            // 2. Toujours envoyer l'audio dioula si disponible
            if (data.audio_url) {
                try {
                    // Petit délai avant l'audio pour laisser le texte FR s'afficher d'abord
                    await this.randomDelay(500, 1000);
                    await this._downloadAndSendAudio(userNumber, this._resolveAudioUrl(data.audio_url));
                    this.logger.info("[ENVOYE] Audio dioula (mode both)");
                } catch (audioErr) {
                    this.logger.warn(`[AUDIO DIOULA] Erreur (mode both, texte FR déjà envoyé): ${audioErr.message}`);
                }
            }
        }

        // PROMPT FEEDBACK C4 (dioula/both uniquement)
        if ((prefs.language === "dioula" || prefs.language === "both") && data.meta) {
            await this.randomDelay(500, 1000);
            await this.sock.sendMessage(userNumber, {
                text: "I ka jaabi ɲuman ye wa? 👍 / 👎",
            });
            prefs.pendingFeedback = {
                reponse_bambara: data.response_dioula || data.response || "",
                reponse_fr: "",
                intent: data.meta.intent || "",
                cultures: data.meta.cultures || [],
                source: data.meta.source || "unknown",
            };
            prefs.step = STEPS.WAITING_FEEDBACK;
            saveFn();
        }
    }

    /**
     * Envoie un message d'excuse (API down ou retour en ligne) selon la langue.
     * Stratégie d'audio : utilise getExcuseAudio (cache disque) qui retombe
     * sur génération online si cache miss. Si l'audio est indispo, fallback
     * texte bilingue garanti.
     *
     * @param {string} userNumber
     * @param {object} options
     * @param {string} options.language - 'french' | 'dioula' | 'both'
     * @param {'unavailable'|'back'} options.kind
     * @param {boolean} [options.isVoiceInput] - Utilisé uniquement pour mode `french`
     */
    async sendExcuse(userNumber, { language, kind, isVoiceInput = false }) {
        const sock = this.sock;
        const logger = this.logger;
        const EXCUSE_MSG = this.EXCUSE_MSG;
        const getExcuseAudio = this.getExcuseAudio;

        const fallbackText = kind === "back"
            ? EXCUSE_MSG.BACK_BILINGUAL
            : EXCUSE_MSG.UNAVAILABLE_BILINGUAL;

        // ---- Mode FRENCH : selon format d'entrée ----
        if (language === "french") {
            if (!isVoiceInput) {
                // Texte entrant -> texte FR seul
                const textFr = kind === "back" ? EXCUSE_MSG.BACK_FR : EXCUSE_MSG.UNAVAILABLE_FR;
                await sock.sendMessage(userNumber, { text: this._frText(textFr) });
                logger.info(`[EXCUSE] Texte FR envoyé (mode french, ecrit, ${kind})`);
                return;
            }
            // Vocal entrant -> audio FR avec fallback texte
            try { await sock.sendPresenceUpdate("recording", userNumber); } catch (_) {}
            const audioBuffer = await getExcuseAudio({ kind, isFrench: true });
            try { await sock.sendPresenceUpdate("paused", userNumber); } catch (_) {}
            if (audioBuffer) {
                await sock.sendMessage(userNumber, {
                    audio: audioBuffer,
                    mimetype: AUDIO_MIMETYPE,
                    ptt: true,
                });
                logger.info(`[EXCUSE] Audio FR envoyé (mode french, vocal, ${kind})`);
                return;
            }
            await sock.sendMessage(userNumber, { text: fallbackText });
            logger.info(`[EXCUSE] Texte bilingue (mode french, audio FR indispo, ${kind})`);
            return;
        }

        // ---- Mode BOTH : texte FR + tenter audio dioula ----
        if (language === "both") {
            const textFr = kind === "back" ? EXCUSE_MSG.BACK_FR : EXCUSE_MSG.UNAVAILABLE_FR;
            await sock.sendMessage(userNumber, { text: this._frText(textFr) });
            logger.info(`[EXCUSE] Texte FR envoyé (mode both, ${kind})`);

            try { await sock.sendPresenceUpdate("recording", userNumber); } catch (_) {}
            const audioBuffer = await getExcuseAudio({ kind, isFrench: false });
            try { await sock.sendPresenceUpdate("paused", userNumber); } catch (_) {}
            if (audioBuffer) {
                await sock.sendMessage(userNumber, {
                    audio: audioBuffer,
                    mimetype: AUDIO_MIMETYPE,
                    ptt: true,
                });
                logger.info(`[EXCUSE] Audio dioula envoyé (mode both, ${kind})`);
            } else {
                logger.info(`[EXCUSE] Audio dioula indispo (mode both, ${kind}) — texte FR seulement`);
            }
            return;
        }

        // ---- Mode DIOULA : audio dioula prioritaire, fallback texte bilingue ----
        try { await sock.sendPresenceUpdate("recording", userNumber); } catch (_) {}
        const audioBuffer = await getExcuseAudio({ kind, isFrench: false });
        try { await sock.sendPresenceUpdate("paused", userNumber); } catch (_) {}
        if (audioBuffer) {
            await sock.sendMessage(userNumber, {
                audio: audioBuffer,
                mimetype: AUDIO_MIMETYPE,
                ptt: true,
            });
            logger.info(`[EXCUSE] Audio dioula envoyé (mode dioula, ${kind})`);
            return;
        }
        // Fallback : texte bilingue (audio TTS dioula indispo, probablement API down)
        await sock.sendMessage(userNumber, { text: fallbackText });
        logger.info(`[EXCUSE] Texte bilingue (mode dioula, audio dioula indispo, ${kind})`);
    }
}

module.exports = { ResponseSender };
