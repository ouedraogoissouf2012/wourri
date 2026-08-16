/**
 * Peuplement Convex POST /whatsapp/farmer (Marcel 2026-08-15).
 *
 * Convex ne calcule aucun hash et ne voit jamais de numéro. On envoie
 * uniquement { organizationId, contactRef }. Idempotent côté Convex.
 * Fichier local = contactRefs déjà envoyés (hashes, pas de JID).
 *
 * Convex down : skip, retry au prochain message. Le chat continue.
 */
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { computeContactRef } = require("./contact_ref");

const HTTP_TIMEOUT_MS = 2000;
const DEFAULT_STORE = path.join(__dirname, "..", "farmer_registered.json");

function _loadSeen(storePath) {
    try {
        const raw = fs.readFileSync(storePath, "utf8");
        const data = JSON.parse(raw);
        return new Set(Array.isArray(data) ? data : []);
    } catch (_) {
        return new Set();
    }
}

function _saveSeen(storePath, seen) {
    fs.writeFileSync(storePath, JSON.stringify([...seen], null, 0), "utf8");
}

/**
 * @param {object} deps
 * @param {object} deps.axios
 * @param {string} deps.convexUrl
 * @param {string} deps.callbackKey
 * @param {string} deps.organizationId
 * @param {string} deps.hmacSecret
 * @param {object} [deps.logger]
 * @param {string} [deps.storePath]
 */
function createFarmerRegister(deps) {
    const {
        axios,
        convexUrl,
        callbackKey,
        organizationId,
        hmacSecret,
        logger = console,
        storePath = DEFAULT_STORE,
    } = deps;

    const seen = _loadSeen(storePath);

    function _configured() {
        return Boolean(convexUrl && callbackKey && organizationId && hmacSecret);
    }

    async function sync(jid) {
        if (!_configured()) return { skipped: "unconfigured" };

        let contactRef;
        try {
            contactRef = computeContactRef(jid, hmacSecret);
        } catch (_) {
            return { skipped: "bad_jid" };
        }

        if (seen.has(contactRef)) return { skipped: "already" };

        try {
            const response = await axios.post(
                `${String(convexUrl).replace(/\/$/, "")}/whatsapp/farmer`,
                { organizationId, contactRef },
                {
                    timeout: HTTP_TIMEOUT_MS,
                    headers: { "X-Callback-Key": callbackKey },
                },
            );
            seen.add(contactRef);
            try {
                _saveSeen(storePath, seen);
            } catch (err) {
                logger.warn({ err: err.message }, "[FARMER] persist local échoué");
            }
            logger.info(
                { created: response.data?.created === true },
                "[FARMER] sync Convex",
            );
            return { ok: true, created: response.data?.created === true };
        } catch (err) {
            logger.warn(
                { status: err.response?.status || err.code || "UNKNOWN" },
                "[FARMER] POST /whatsapp/farmer échoué — retry au prochain message",
            );
            return { ok: false };
        }
    }

    return { sync };
}

module.exports = { createFarmerRegister };
