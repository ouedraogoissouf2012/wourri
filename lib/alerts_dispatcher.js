/**
 * Dispatcher pull des alertes Convex → WhatsApp (L2 #409).
 *
 * Convex Cloud ne peut pas joindre le serveur WA privé : on va chercher
 * les livraisons (`GET /alerts/pending`) et on rapporte
 * (`POST /alerts/dispatched`, `POST /whatsapp/callback`).
 *
 * Extension OCP : module nouveau + câblage. Ne touche pas message_queue,
 * circuit_breaker, user_prefs, onboarding, ni messages.upsert.
 *
 * sock lu AU MOMENT de l'envoi (reconnexion = nouvelle ref).
 * Aucun numéro / JID dans les logs.
 */
"use strict";

const { resolveJid } = require("./contact_ref");
const { sendTextWithPause } = require("./sock_helpers");
const { getDelays } = require("./human_delays");

const DEFAULT_TTL_MS = 24 * 60 * 60 * 1000;
const HTTP_TIMEOUT_MS = 10000;
const DEFAULT_MAX_SENDS_PER_TICK = 10;

const BAILEYS_STATUS = {
    2: "sent",
    3: "delivered",
    4: "read",
    5: "read",
};

function _normalizePending(data) {
    if (Array.isArray(data)) return data;
    if (!data || typeof data !== "object") return [];
    for (const key of ["deliveries", "pending", "items"]) {
        if (Array.isArray(data[key])) return data[key];
    }
    return [];
}

/**
 * Diagnostic de config (noms seulement, jamais les valeurs).
 * @returns {{ configured: boolean, partial: boolean, missing: string[], pollInvalid: boolean }}
 */
function assessAlertsConfig({ convexUrl, dispatchKey, hmacSecret, pollMs } = {}) {
    const missing = [];
    if (!convexUrl) missing.push("CONVEX_URL");
    if (!dispatchKey) missing.push("CONVEX_DISPATCH_KEY");
    if (!hmacSecret) missing.push("WOURI_CONTACTREF_HMAC_SECRET");
    return {
        configured: missing.length === 0,
        partial: missing.length > 0 && missing.length < 3,
        missing,
        pollInvalid: !(Number.isFinite(pollMs) && pollMs > 0),
    };
}

/**
 * @param {object} deps
 * @param {Function} deps.getSock
 * @param {object} deps.userPrefs
 * @param {object} deps.axios
 * @param {string} deps.convexUrl
 * @param {string} deps.dispatchKey
 * @param {string} deps.callbackKey
 * @param {string} deps.hmacSecret
 * @param {Function} [deps.randomDelay]
 * @param {object} [deps.logger]
 * @param {Function} [deps.now]
 * @param {number} [deps.idempotenceTtlMs]
 */
function createAlertsDispatcher(deps) {
    const {
        getSock,
        userPrefs,
        axios,
        convexUrl,
        dispatchKey,
        callbackKey,
        hmacSecret,
        randomDelay = async () => {},
        logger = console,
        now = () => Date.now(),
        idempotenceTtlMs = DEFAULT_TTL_MS,
        maxSendsPerTick = DEFAULT_MAX_SENDS_PER_TICK,
    } = deps;

    const seen = new Map();
    const providerToDelivery = new Map();
    let inFlight = false;

    function _purge(ts) {
        for (const [id, rec] of seen) {
            if (ts - rec.at > idempotenceTtlMs) {
                seen.delete(id);
                if (rec.providerMessageId) providerToDelivery.delete(rec.providerMessageId);
            }
        }
    }

    function _configured() {
        return Boolean(convexUrl && dispatchKey && hmacSecret);
    }

    function _baseUrl() {
        return String(convexUrl).replace(/\/$/, "");
    }

    function _dispatchReq(extra = {}) {
        return {
            timeout: HTTP_TIMEOUT_MS,
            headers: { "X-Dispatch-Key": dispatchKey },
            ...extra,
        };
    }

    async function _reportDispatched(deliveryId, providerMessageId) {
        const response = await axios.post(
            `${_baseUrl()}/alerts/dispatched`,
            { deliveryId, providerMessageId },
            _dispatchReq(),
        );
        return response.data || { updated: true };
    }

    function logStartup(pollMs) {
        const cfg = assessAlertsConfig({
            convexUrl, dispatchKey, hmacSecret, pollMs,
        });
        if (cfg.configured) {
            logger.info("[ALERTS] dispatcher configuré");
        } else if (cfg.partial) {
            logger.warn({ missing: cfg.missing }, "[ALERTS] config partielle — diffusion inactive");
        }
        if (cfg.pollInvalid) {
            logger.warn({ pollMs }, "[ALERTS] ALERTS_POLL_MS invalide — intervalle désactivé");
        }
    }

    async function tick() {
        const result = {
            sent: 0,
            alreadyDispatched: 0,
            unresolved: 0,
            deferred: 0,
            failed: 0,
            skipped: null,
            dispatched: [],
            capped: false,
        };

        if (!_configured()) {
            result.skipped = "unconfigured";
            return result;
        }

        if (inFlight) {
            result.skipped = "in_flight";
            return result;
        }
        inFlight = true;

        try {
            return await _runTick(result);
        } finally {
            inFlight = false;
        }
    }

    async function _runTick(result) {
        const ts = now();
        _purge(ts);

        let pending;
        try {
            const response = await axios.get(`${_baseUrl()}/alerts/pending`, _dispatchReq());
            pending = _normalizePending(response.data);
        } catch (err) {
            const status = err.response?.status;
            logger.warn(
                { status: status || err.code || "UNKNOWN" },
                "[ALERTS] GET /alerts/pending échoué",
            );
            result.failed = 1;
            return result;
        }

        const jids = Object.keys(userPrefs.data || {});

        for (let i = 0; i < pending.length; i++) {
            if (result.sent >= maxSendsPerTick) {
                result.capped = true;
                logger.info(
                    { sent: result.sent, maxSendsPerTick },
                    "[ALERTS] plafond par tick — reste au prochain poll",
                );
                break;
            }

            const item = pending[i] || {};
            const deliveryId = item.deliveryId;
            if (!deliveryId) continue;

            const existing = seen.get(deliveryId);
            if (existing) {
                result.alreadyDispatched += 1;
                if (existing.providerMessageId) {
                    try {
                        await _reportDispatched(deliveryId, existing.providerMessageId);
                    } catch (_) { /* déjà envoyé côté WA — ne pas rejouer */ }
                }
                logger.info({ deliveryId }, "[ALERTS] already_dispatched");
                continue;
            }

            const jid = resolveJid(item.contactRef, jids, hmacSecret);
            if (!jid) {
                result.unresolved += 1;
                logger.warn({ deliveryId }, "[ALERTS] contactRef non résolu — skip");
                continue;
            }

            const sock = getSock();
            if (!sock) {
                result.deferred += 1;
                logger.warn({ deliveryId }, "[ALERTS] sock absent — reporté au prochain tick");
                continue;
            }

            if (result.sent > 0) {
                const [min, max] = getDelays().beforeSend;
                await randomDelay(min, max);
            }

            seen.set(deliveryId, { at: now(), providerMessageId: null });

            let sentMsg;
            try {
                sentMsg = await sendTextWithPause(sock, jid, item.text || "");
            } catch (err) {
                seen.delete(deliveryId);
                result.failed += 1;
                logger.error({ deliveryId, err: err.message }, "[ALERTS] envoi WhatsApp échoué");
                continue;
            }

            const providerMessageId = sentMsg?.key?.id || `local_${deliveryId}`;
            seen.set(deliveryId, { at: now(), providerMessageId });
            providerToDelivery.set(providerMessageId, deliveryId);
            result.sent += 1;

            try {
                result.dispatched.push(await _reportDispatched(deliveryId, providerMessageId));
            } catch (err) {
                logger.warn(
                    { deliveryId, status: err.response?.status || err.code || "UNKNOWN" },
                    "[ALERTS] POST /alerts/dispatched échoué — idempotence locale conservée",
                );
                result.dispatched.push({ updated: false });
            }

            logger.info({ deliveryId, providerMessageId }, "[ALERTS] dispatched");
        }

        return result;
    }

    async function onMessageUpdate(updates) {
        if (!_configured() || !callbackKey) return;
        const list = Array.isArray(updates) ? updates : [];
        for (const item of list) {
            const providerMessageId = item?.key?.id;
            if (!providerMessageId || !providerToDelivery.has(providerMessageId)) continue;
            const raw = item?.update?.status ?? item?.status;
            const state = BAILEYS_STATUS[raw];
            if (!state) continue;
            try {
                await axios.post(
                    `${_baseUrl()}/whatsapp/callback`,
                    { providerMessageId, state },
                    { timeout: HTTP_TIMEOUT_MS, headers: { "X-Callback-Key": callbackKey } },
                );
                logger.info({ providerMessageId, state }, "[ALERTS] callback");
            } catch (err) {
                logger.warn(
                    { providerMessageId, status: err.response?.status || err.code || "UNKNOWN" },
                    "[ALERTS] POST /whatsapp/callback échoué",
                );
            }
        }
    }

    return { tick, onMessageUpdate, logStartup };
}

module.exports = {
    createAlertsDispatcher,
    assessAlertsConfig,
    DEFAULT_MAX_SENDS_PER_TICK,
};
