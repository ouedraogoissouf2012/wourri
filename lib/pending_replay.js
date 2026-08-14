/**
 * Rejeu de la queue de messages après reconnexion WhatsApp (fix #299).
 *
 * ## Problème corrigé
 *
 * Avant : `notifyPendingUsers` (app-baileys.js) envoyait une excuse « Je suis
 * de retour, repose ta question » puis JETAIT tous les messages en attente via
 * `markSuccess`, sans jamais rejouer le payload (question/ville/langue) contre
 * `/api/chat/`. La promesse « aucun message perdu » de message_queue.js était
 * donc factuellement fausse : l'utilisateur devait tout retaper.
 *
 * Après : chaque message en attente est REJOUÉ contre le backend et la vraie
 * réponse est envoyée à l'utilisateur, exactement comme s'il venait de la poser.
 *
 * ## Cycle de vie d'un message dans la queue
 *
 * Un message est ajouté à la queue AVANT son traitement (message_handler
 * `_processComplete`) et retiré (markSuccess) seulement APRÈS l'envoi réussi de
 * la réponse. Il reste donc en queue — et sera rejoué — dans trois cas :
 *   1. l'appel /api/chat/ a échoué (API down / circuit ouvert) → aucune réponse
 *      n'a été envoyée : le rejeu la délivre (cas nominal du fix #299) ;
 *   2. l'envoi (sendResponse) a levé APRÈS avoir déjà délivré la réponse
 *      principale (ex. envoi du prompt feedback 👍/👎) ;
 *   3. markSuccess a échoué en I/O APRÈS que la réponse a été délivrée.
 *
 * Dans les cas 2 et 3 (rares), le rejeu produit une DOUBLE réponse (+ un
 * re-appel /api/chat/ facturé, réponse potentiellement différente car le LLM
 * n'est pas déterministe). Compromis ASSUMÉ, cohérent avec message_handler
 * (« double-reponse possible, jamais une perte », fix #300) : pour un public
 * souvent peu alphabétisé, une réponse en double vaut mieux qu'une réponse
 * perdue. L'idempotence stricte (ne rejouer que le jamais-délivré) est une
 * amélioration future tracée (#398), non retenue ici.
 *
 * ## Décisions
 *
 * - **Ordre chronologique par utilisateur** : les messages d'un même user sont
 *   rejoués du plus ancien au plus récent (cohérence de l'historique backend
 *   indexé par user_id).
 * - **markSuccess APRÈS sendResponse** : on ne retire un message de la queue
 *   qu'une fois la réponse réellement délivrée. Si l'envoi échoue → markFailure
 *   (conservé pour retry). Évite par construction la classe de bug #300.
 * - **Feedback C4 : seul le DERNIER message d'un user déclenche le prompt 👍/👎**
 *   (issue #299, option A2). Raison : `sendResponse` mute `prefs.pendingFeedback`
 *   à chaque appel ; sans cette règle, le feedback de l'utilisateur serait
 *   rattaché au mauvais message → signal corrompu envoyé au corpus. `data.meta`
 *   ne sert QU'au bloc feedback de sendResponse : le retirer supprime le prompt
 *   sans altérer la réponse elle-même (branches réponse : audio_url / response
 *   uniquement).
 * - **Contexte de réponse = prefs COURANTS** (ville/langue actuelles, fallback
 *   payload puis défaut). Cohérent avec `sendResponse` qui formate selon
 *   `prefs.language`, et aligné sur la logique historique de notifyPendingUsers.
 * - **Anti-flood** : délai « humain » entre deux envois (risque ban Baileys).
 * - **Isolation par utilisateur** : un échec API sur un user stoppe uniquement
 *   sa propre chaîne (le reste de ses messages reste en queue, retry au prochain
 *   reconnect) et n'empêche pas les autres utilisateurs d'être servis.
 */
"use strict";

const { getDelays } = require("./human_delays");

// Aligné sur message_handler._processComplete (traitement chat backend).
const CHAT_TIMEOUT_MS = 180000;

/**
 * @param {object} deps
 * @param {object} deps.messageQueue       Queue persistante (getPending/markSuccess/markFailure)
 * @param {object} deps.userPrefs          Préférences utilisateurs (get live/save)
 * @param {object} deps.responseSender     Envoi réponse (sendResponse)
 * @param {object} deps.apiCircuitBreaker  Circuit breaker sur wouri-api (execute)
 * @param {object} deps.axios              Module axios
 * @param {string} deps.apiUrl             URL backend (WOURI_API_URL)
 * @param {Function} deps.authHeaders      () -> { 'X-API-Key': ... } | {}
 * @param {Function} deps.isApiHealthy     async () -> boolean
 * @param {Function} deps.randomDelay      async (min, max) -> Promise<void>
 * @param {object} [deps.logger]           Logger (défaut console)
 * @param {string} deps.DEFAULT_USER_LANGUAGE  Langue par défaut si absente
 * @returns {Function} replayPending: async () -> { replayed, users, failed }
 */
function createPendingReplayer(deps) {
    const {
        messageQueue,
        userPrefs,
        responseSender,
        apiCircuitBreaker,
        axios,
        apiUrl,
        authHeaders,
        isApiHealthy,
        randomDelay,
        DEFAULT_USER_LANGUAGE,
    } = deps;
    const logger = deps.logger || console;

    // Validation des dépendances critiques (échec rapide au câblage).
    for (const [name, val] of Object.entries({
        messageQueue, userPrefs, responseSender, apiCircuitBreaker, axios,
        apiUrl, authHeaders, isApiHealthy, randomDelay, DEFAULT_USER_LANGUAGE,
    })) {
        if (val === undefined || val === null) {
            throw new Error(`createPendingReplayer: dépendance requise manquante: ${name}`);
        }
    }

    // Garde de ré-entrance : un drain de queue peut être long (appels /api/chat/
    // jusqu'à 180s chacun). Avant le fix #308, une rafale de reconnexions peut
    // déclencher plusieurs `connection.open` → plusieurs replayPending() concurrents
    // qui verraient les mêmes messages via getPending() (avant tout markSuccess)
    // et enverraient des réponses EN DOUBLE. Ce verrou garantit un seul drain à la
    // fois (défense en profondeur, indépendante de #308).
    let replaying = false;

    return async function replayPending() {
        if (replaying) {
            logger.info("[QUEUE][REPLAY] Drain déjà en cours — appel concurrent ignoré");
            return { replayed: 0, users: 0, failed: 0, skipped: true };
        }
        replaying = true;
        try {
            return await _drain();
        } finally {
            replaying = false;
        }
    };

    async function _drain() {
        const pending = messageQueue.getPending();
        if (pending.length === 0) {
            return { replayed: 0, users: 0, failed: 0 };
        }

        // Ne pas rejouer si l'API est encore down : laisser en queue, retenter au
        // prochain reconnect (évite de vider la queue en pure perte).
        if (!(await isApiHealthy())) {
            logger.info(
                `[QUEUE][REPLAY] API indisponible — ${pending.length} message(s) restent en queue`
            );
            return { replayed: 0, users: 0, failed: 0 };
        }

        // Grouper par utilisateur, trier chaque groupe par createdAt croissant.
        const byUser = new Map();
        for (const msg of pending) {
            if (!msg.userNumber) continue;
            if (!byUser.has(msg.userNumber)) byUser.set(msg.userNumber, []);
            byUser.get(msg.userNumber).push(msg);
        }
        for (const list of byUser.values()) {
            list.sort((a, b) => new Date(a.createdAt) - new Date(b.createdAt));
        }

        logger.info(
            `[QUEUE][REPLAY] Rejeu de ${pending.length} message(s) pour ${byUser.size} utilisateur(s)`
        );

        let replayed = 0;
        let failed = 0;
        let sentCount = 0; // pour l'espacement anti-flood entre envois réels

        for (const [userNumber, list] of byUser) {
            // prefs COURANTS (référence live, mutable par sendResponse + persistée
            // via saveFn). Accès direct à .data SANS side-effect : userPrefs.get()
            // RECRÉE une entrée par défaut pour un user absent → entrée fantôme
            // persistée + réonboarding surprise (régression #398 ; le code pré-#299
            // lisait .data justement pour éviter ça). En pratique tout user en queue
            // a une entrée ; s'il a disparu, on sert quand même sa réponse via un
            // prefs ÉPHÉMÈRE (langue/ville reprises du payload, jamais réinjecté
            // dans .data) → aucun fantôme persisté.
            const prefs = userPrefs.data[userNumber] || {
                city: list[0].payload?.city || null,
                language: list[0].payload?.language || DEFAULT_USER_LANGUAGE,
                pendingFeedback: null,
            };

            for (let i = 0; i < list.length; i++) {
                const msg = list[i];
                const isLastForUser = i === list.length - 1;
                const payload = msg.payload || {};

                const city = prefs.city || payload.city || null;
                const language = prefs.language || payload.language || DEFAULT_USER_LANGUAGE;
                const isVoiceInput = payload.isVoiceInput === true;

                // Espacement humain entre deux envois réels (anti-ban Baileys).
                if (sentCount > 0) {
                    await randomDelay(...getDelays().beforeSend);
                }

                // 1) Rejouer contre le backend (via circuit breaker).
                let data;
                try {
                    const response = await apiCircuitBreaker.execute(async () =>
                        axios.post(
                            `${apiUrl}/api/chat/`,
                            {
                                message: payload.messageText,
                                city,
                                language,
                                include_audio: true,
                                user_id: userNumber,
                                bambara_text: payload.bambaraText || null,
                            },
                            { timeout: CHAT_TIMEOUT_MS, headers: authHeaders() }
                        )
                    );
                    data = response.data;
                } catch (apiErr) {
                    // API KO → conserver le message, stopper la chaîne de CET
                    // utilisateur (préserve l'ordre ; retry au prochain reconnect).
                    await messageQueue.markFailure(msg.id, apiErr);
                    failed++;
                    logger.warn(
                        `[QUEUE][REPLAY] Échec API ${userNumber} msg=${msg.id}: ${apiErr.message} — reste en queue`
                    );
                    break;
                }

                // A2 : supprimer le prompt feedback C4 sauf pour le dernier message
                // de l'utilisateur (data.meta ne sert QU'au bloc feedback).
                const effectiveData = isLastForUser ? data : { ...data, meta: undefined };

                // 2) Délivrer la réponse. markSuccess seulement APRÈS (fix classe #300).
                try {
                    await responseSender.sendResponse({
                        data: effectiveData,
                        prefs,
                        isVoiceInput,
                        userNumber,
                        saveFn: () => userPrefs.save(),
                    });
                } catch (sendErr) {
                    // Réponse non délivrée → NE PAS markSuccess. Conserver pour retry.
                    await messageQueue.markFailure(msg.id, sendErr);
                    failed++;
                    logger.warn(
                        `[QUEUE][REPLAY] Échec envoi ${userNumber} msg=${msg.id}: ${sendErr.message} — reste en queue`
                    );
                    break;
                }

                await messageQueue.markSuccess(msg.id);
                replayed++;
                sentCount++;
            }
        }

        logger.info(
            `[QUEUE][REPLAY] Terminé : ${replayed} rejoué(s), ${failed} échec(s)`
        );
        return { replayed, users: byUser.size, failed };
    };
}

module.exports = { createPendingReplayer };
