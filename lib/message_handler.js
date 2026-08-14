/**
 * Wouri WhatsApp — Handler messages.upsert.
 *
 * Sprint 2026-05-28 (audit P2 #5) : extraction du handler ~260 lignes inline
 * dans `app-baileys.js:500-760` (5 niveaux d'imbrication) vers un module
 * factory dedie. Comportement strictement identique au code precedent.
 *
 * Cible Epic #157 atteinte : `app-baileys.js` passe sous 800 lignes.
 *
 * ## Design
 *
 * Factory function `createMessageHandler({deps})` qui retourne un handler
 * `async ({ messages })` attache sur `sock.ev.on('messages.upsert', ...)`.
 *
 * Pattern aligne sur `lib/onboarding.js` (Pattern 11 projet : sock mutable
 * post-makeWASocket). Les dependances sont injectees par closure pour
 * faciliter les tests (mocks complets) et eviter les imports cycliques.
 *
 * ## Sous-fonctions (interne au module, pas exportees)
 *
 * - `_shouldIgnore(msg)`   : filtre self/groupes/statuts
 * - `_extractMessageText(msg)` : 5 formats Baileys (texte/extended/button/list/template)
 * - `_processAudio(msg, ...)`  : pipeline ASR Bambara/Whisper FR + erreurs
 * - `_processComplete(...)`    : pipeline chat (queue + circuit breaker + API + sendResponse)
 *
 * Le handler principal orchestre : filtre → extract → (si audio) processAudio
 * → (si onboarding COMPLETE) processComplete → catch global.
 */

/**
 * @typedef {Object} MessageHandlerDeps
 * @property {Object} sock                 socket Baileys (mutable post-init)
 * @property {Object} logger               pino structure
 * @property {Object} asrClient            client ASR Whisper FR + MMS Bambara
 * @property {Object} responseSender       envoi reponse (text/audio + feedback)
 * @property {Object} userPrefs            preferences utilisateurs persistees
 * @property {Object} onboardingMachine    state machine onboarding
 * @property {Object} messageQueue         queue persistante anti-perte
 * @property {Object} apiCircuitBreaker    circuit breaker sur wouri-api
 * @property {string} apiUrl               URL backend (WOURI_API_URL)
 * @property {Object} MSG                  messages i18n
 * @property {Object} STEPS                etapes onboarding
 * @property {Function} authHeaders        () -> { 'X-API-Key': ... } | {}
 * @property {Function} isApiHealthy       async () -> boolean
 * @property {Function} pickMsg            (msgs, lang) -> string
 * @property {Function} randomDelay        async (min, max) -> Promise<void>
 * @property {Function} downloadMediaMessage   Baileys downloadMediaMessage
 * @property {Object} pino                 module pino (pour silent logger interne Baileys)
 * @property {Object} axios                module axios
 * @property {Error} CircuitOpenError      classe d'erreur du circuit breaker
 */

const { isOldMessage, noteIgnored } = require("./skip_old_messages");
const { getDelays } = require("./human_delays");

/**
 * Cree le handler messages.upsert.
 *
 * @param {MessageHandlerDeps} deps
 * @returns {Function} handler async ({ messages }) -> Promise<void>
 */
function createMessageHandler(deps) {
    const {
        sock,
        logger,
        asrClient,
        responseSender,
        userPrefs,
        onboardingMachine,
        messageQueue,
        apiCircuitBreaker,
        apiUrl,
        MSG,
        STEPS,
        authHeaders,
        isApiHealthy,
        pickMsg,
        randomDelay,
        downloadMediaMessage,
        pino,
        axios,
        CircuitOpenError,
    } = deps;

    // ─────────────────────────────────────────────
    // Sous-fonctions privees (closure capture deps)
    // ─────────────────────────────────────────────

    /** Filtre self-messages, groupes, statuts WhatsApp + messages downtime. */
    function _shouldIgnore(msg) {
        if (msg.key.fromMe) return true;
        if (msg.key.remoteJid.endsWith('@g.us')) return true;
        if (msg.key.remoteJid === 'status@broadcast') return true;
        // Messages reçus pendant le downtime serveur : voir lib/skip_old_messages.js
        if (isOldMessage(msg)) {
            noteIgnored();
            return true;
        }
        return false;
    }

    /** Extrait le texte d'un message Baileys (5 formats supportes). */
    function _extractMessageText(msg) {
        return msg.message?.conversation ||
            msg.message?.extendedTextMessage?.text ||
            msg.message?.buttonsResponseMessage?.selectedButtonId ||
            msg.message?.listResponseMessage?.singleSelectReply?.selectedRowId ||
            msg.message?.templateButtonReplyMessage?.selectedId ||
            '';
    }

    /**
     * Pipeline ASR pour message vocal. Telecharge l'audio, choisit le moteur
     * selon `prefs.language` (Bambara MMS pour dioula/both, Whisper FR sinon),
     * gere les erreurs (API down, transcription vide).
     *
     * @returns {Promise<{text: string, bambaraText: string|null, isVoiceInput: boolean}|null>}
     *   `null` si on doit `continue` (erreur, API down, transcription vide).
     */
    async function _processAudio(msg, userNumber, prefs) {
        const audioMsg = msg.message?.audioMessage;
        logger.info(`\n[AUDIO] Message vocal recu de: ${userNumber}`);

        if (!audioMsg?.mediaKey || !audioMsg?.url) {
            logger.info('[AUDIO] Message sans cle media valide - ignore');
            return null;
        }

        try {
            await sock.readMessages([msg.key]);
            // Message vocal recu -> reponse sera audio -> afficher 'recording'
            await sock.sendPresenceUpdate('recording', userNumber);

            const audioBuffer = await downloadMediaMessage(
                msg,
                'buffer',
                {},
                {
                    logger: pino({ level: 'silent' }),
                    reuploadRequest: sock.updateMediaMessage,
                }
            );

            if (!audioBuffer) {
                await sock.sendPresenceUpdate('paused', userNumber);
                await sock.sendMessage(userNumber, { text: pickMsg(MSG.AUDIO_ERROR, prefs.language) });
                return null;
            }

            logger.info(`[AUDIO] Telecharge: ${audioBuffer.length} bytes`);

            // Choisir le moteur de transcription selon la langue de l'utilisateur :
            //   - dioula ou both -> ASR Bambara (MMS), les "both" parlent souvent
            //     Dioula et Whisper hallucine sur du Dioula
            //   - french        -> Whisper FR
            let transcriptionResult;
            const userLanguage = prefs.language || 'french';

            if (userLanguage === 'dioula' || userLanguage === 'both') {
                logger.info(`[AUDIO] Utilisateur en mode ${userLanguage} -> ASR Bambara`);
                transcriptionResult = await asrClient.transcribeAudioBambara(audioBuffer, 'voice_message.ogg');
            } else {
                logger.info(`[AUDIO] Utilisateur en mode ${userLanguage} -> Whisper francais`);
                transcriptionResult = await asrClient.transcribeAudio(audioBuffer, 'voice_message.ogg');
            }

            if (!transcriptionResult || !transcriptionResult.text || transcriptionResult.text.trim() === '') {
                await sock.sendPresenceUpdate('paused', userNumber);

                // Distinguer la cause de l'echec :
                //   - API down -> message d'indisponibilite (coherent avec autres erreurs API)
                //   - API up mais transcription vide -> vrai cas "audio incomprehensible"
                if (!(await isApiHealthy())) {
                    logger.info(`[AUDIO] API indisponible -> message d'indisponibilite (mode=${prefs.language})`);
                    await responseSender.sendExcuse(userNumber, {
                        language: prefs.language,
                        kind: 'unavailable',
                        isVoiceInput: true,
                    });
                } else {
                    // API up mais transcription a vraiment echoue -> vrai "audio non compris"
                    await sock.sendMessage(userNumber, { text: pickMsg(MSG.AUDIO_FAILED, prefs.language) });
                }
                return null;
            }

            const transcribedText = transcriptionResult.text;
            const likelyDioulaInput = transcriptionResult.likely_dioula_input || false;
            const isBambaraTranscription = transcriptionResult.is_bambara || false;

            logger.info(`[STT] Transcription: "${transcribedText}"`);
            if (isBambaraTranscription) {
                logger.info(`[STT] Transcription Bambara reussie!`);
                if (transcriptionResult.bambara_text) {
                    logger.info(`[STT] Texte Bambara original: "${transcriptionResult.bambara_text}"`);
                }
            } else if (likelyDioulaInput) {
                logger.info(`[STT] ATTENTION: Audio probablement en Dioula - transcription peut etre incorrecte`);
            }

            return {
                text: transcribedText,
                bambaraText: transcriptionResult.bambara_text || null,
                isVoiceInput: true,
            };
        } catch (audioError) {
            logger.error(`[AUDIO] Erreur: ${audioError.message}`);
            await sock.sendPresenceUpdate('paused', userNumber);
            await sock.sendMessage(userNumber, { text: pickMsg(MSG.AUDIO_ERROR, prefs.language) });
            return null;
        }
    }

    /**
     * Pipeline chat pour onboarding COMPLETE : queue le message,
     * appelle wouri-api via circuit breaker, envoie la reponse.
     */
    async function _processComplete(msg, userNumber, prefs, messageText, bambaraText, isVoiceInput) {
        logger.info(`[API] Appel avec ville: ${prefs.city}, langue: ${prefs.language}, voiceInput: ${isVoiceInput}`);

        // Determiner le type de presence selon le contexte :
        //   - entree vocale OU langue dioula/both -> reponse audio probable -> 'recording'
        //   - sinon -> reponse texte -> 'composing'
        const willBeAudio = isVoiceInput || prefs.language === 'dioula' || prefs.language === 'both';
        const presenceType = willBeAudio ? 'recording' : 'composing';

        // Maintenir le statut pendant le traitement
        let keepPresence = true;
        const presenceInterval = setInterval(async () => {
            if (keepPresence) {
                try {
                    await sock.sendPresenceUpdate(presenceType, userNumber);
                } catch (e) {}
            }
        }, 5000);

        // Phase 2 - enregistrer le message dans la queue avant traitement
        // Garantit qu'aucun message n'est perdu silencieusement.
        const queueId = msg.key?.id || `wamsg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
        try {
            await messageQueue.add({
                id: queueId,
                userNumber,
                payload: {
                    messageText,
                    bambaraText,
                    isVoiceInput,
                    city: prefs.city,
                    language: prefs.language,
                },
            });
        } catch (qErr) {
            logger.error(`[QUEUE] Erreur ajout queue : ${qErr.message}`);
        }

        // Etape 1 — appel API SEUL dans le try (ne protege QUE l'appel backend).
        // fix #300 : markSuccess NE DOIT PAS etre dans ce try. S'il jetait (I/O
        // pending_messages.json), le catch le prenait pour une erreur API ->
        // markFailure + throw -> excuse "indisponible" alors que `data` etait
        // deja obtenu mais jamais envoye -> reponse perdue.
        let data;
        try {
            // Wrap l'appel API dans le circuit breaker (Phase 2)
            const response = await apiCircuitBreaker.execute(async () =>
                axios.post(`${apiUrl}/api/chat/`, {
                    message: messageText,
                    city: prefs.city,
                    language: prefs.language,
                    include_audio: true,
                    user_id: userNumber,           // historique de conversation
                    bambara_text: bambaraText,     // NLU preprocessing si vocal bambara
                }, { timeout: 180000, headers: authHeaders() })
            );
            data = response.data;
        } catch (apiErr) {
            // Echec de l'APPEL API : marquer dans la queue (reste en attente pour
            // observabilite et rejeu #299).
            await messageQueue.markFailure(queueId, apiErr);

            // Si circuit ouvert, message d'attente adapte au format du dernier message
            if (apiErr instanceof CircuitOpenError) {
                logger.info(`[CIRCUIT] wouri-api en circuit OPEN — message d'attente envoye (isVoice=${isVoiceInput}, lang=${prefs.language})`);
                keepPresence = false;
                clearInterval(presenceInterval);
                await sock.sendPresenceUpdate('paused', userNumber);
                await responseSender.sendExcuse(userNumber, {
                    isVoiceInput,
                    language: prefs.language,
                    kind: 'unavailable',
                });
                return;
            }
            throw apiErr;  // Re-throw : capture par le try/catch global du handler
        } finally {
            keepPresence = false;
            clearInterval(presenceInterval);
        }

        logger.info(`[API] Reponse recue`);
        await sock.sendPresenceUpdate('paused', userNumber);
        await randomDelay(...getDelays().beforeSend);

        // Etape 2 — ENVOYER la reponse AVANT tout bookkeeping de queue. C'est
        // l'action user-facing critique : elle ne doit jamais etre sacrifiee a
        // une erreur d'I/O de la queue (fix #300). Si sendResponse jette, on ne
        // markSuccess pas -> le message reste en queue -> rejoue (#299), pas de perte.
        // Sprint D.2 - envoi via ResponseSender (3 modes + feedback C4)
        await responseSender.sendResponse({
            data,
            prefs,
            isVoiceInput,
            userNumber,
            saveFn: () => userPrefs.save(),
        });

        // Etape 3 — bookkeeping ISOLE : la reponse est deja delivree. Une erreur
        // d'I/O sur markSuccess ne doit rien casser cote utilisateur. Au pire, le
        // message reste en queue et sera rejoue (#299) -> double-reponse possible,
        // jamais une perte. On log pour observabilite.
        try {
            await messageQueue.markSuccess(queueId);
        } catch (queueErr) {
            logger.error(`[QUEUE] markSuccess a echoue apres reponse delivree (msg=${queueId}) : ${queueErr.message} — message conserve, sera rejoue`);
        }
    }

    // ─────────────────────────────────────────────
    // Handler principal
    // ─────────────────────────────────────────────

    return async function handleMessageUpsert({ messages }) {
        for (const msg of messages) {
            if (_shouldIgnore(msg)) continue;

            const userNumber = msg.key.remoteJid;
            const prefs = userPrefs.get(userNumber);

            let messageText = _extractMessageText(msg);
            const audioMsg = msg.message?.audioMessage;
            const isAudioMessage = audioMsg !== undefined && audioMsg !== null && !messageText;
            let isVoiceInput = false;
            let bambaraText = null;

            if (isAudioMessage) {
                const audioResult = await _processAudio(msg, userNumber, prefs);
                if (!audioResult) continue;
                messageText = audioResult.text;
                bambaraText = audioResult.bambaraText;
                isVoiceInput = audioResult.isVoiceInput;
            }

            if (!messageText) continue;

            logger.info(`\n[MESSAGE] De: ${userNumber}`);
            logger.info(`[MESSAGE] Texte: ${messageText}`);
            logger.info(`[MESSAGE] Etape: ${prefs.step}`);

            try {
                await sock.readMessages([msg.key]);
                await randomDelay(...getDelays().read);
                await sock.sendPresenceUpdate('composing', userNumber);

                // Sprint D.3 - onboarding state machine deleguee
                //   { handled: null }                  -> step=COMPLETE, pass-through
                //   { handled: true }                  -> onboarding traite, continue
                //   { handled: false, newMessageText } -> onboarding termine, question a traiter
                const ob = await onboardingMachine.processStep(prefs, messageText, userNumber, { isAudioMessage, isVoiceInput });
                if (ob.handled === true) continue;
                if (ob.newMessageText) messageText = ob.newMessageText;

                if (prefs.step === STEPS.COMPLETE) {
                    await _processComplete(msg, userNumber, prefs, messageText, bambaraText, isVoiceInput);
                }
            } catch (error) {
                // Format detaille : axios v1.x + erreurs reseau Windows mettent parfois
                // le vrai motif dans error.code (ECONNREFUSED, ETIMEDOUT...) plutot
                // que dans error.message. On expose les deux pour le diagnostic.
                const errCode = error.code || error.response?.status || 'UNKNOWN';
                const errMsg = error.message || error.toString() || 'erreur sans message';
                logger.error(`[ERREUR] ${errCode} - ${errMsg}`);
                await sock.sendPresenceUpdate('paused', userNumber);
                await randomDelay(...getDelays().error);
                // Regle "selon langue choisie" (revisee 2026-05-06) : message d'excuse
                // adapte au mode utilisateur, plus le texte bilingue fixe.
                await responseSender.sendExcuse(userNumber, {
                    language: prefs.language || 'french',
                    kind: 'unavailable',
                    isVoiceInput,
                });
            }
        }
    };
}

module.exports = { createMessageHandler };
