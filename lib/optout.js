/**
 * Opt-out STOP (L5c #412).
 *
 * Détection + rapport Convex. Convex = autorité du consentement.
 * Aucun numéro dans les corps HTTP ni dans les logs.
 */
"use strict";

const HTTP_TIMEOUT_MS = 2000;

/**
 * STOP / ARRET / ARRÊT — casse et espaces ignorés, accents NFD.
 * Correspondance exacte du message (pas un sous-mot).
 */
function isOptOut(text) {
    const normalized = String(text == null ? "" : text)
        .normalize("NFD")
        .replace(/\p{M}/gu, "")
        .replace(/\s+/g, " ")
        .trim()
        .toUpperCase();
    return normalized === "STOP" || normalized === "ARRET";
}

/**
 * POST /whatsapp/optout. Fire-and-forget sémantique : n'explose jamais.
 * @returns {Promise<{ok: boolean, skipped?: string}>}
 */
async function reportOptOut({
    axios,
    convexUrl,
    callbackKey,
    organizationId,
    contactRef,
    logger = console,
}) {
    if (!convexUrl || !callbackKey || !organizationId || !contactRef) {
        return { ok: false, skipped: "unconfigured" };
    }
    try {
        await axios.post(
            `${String(convexUrl).replace(/\/$/, "")}/whatsapp/optout`,
            { organizationId, contactRef },
            {
                timeout: HTTP_TIMEOUT_MS,
                headers: { "X-Callback-Key": callbackKey },
            },
        );
        return { ok: true };
    } catch (err) {
        logger.warn(
            { status: err.response?.status || err.code || "UNKNOWN" },
            "[OPTOUT] Convex injoignable — confirmation quand même envoyée",
        );
        return { ok: false };
    }
}

module.exports = { isOptOut, reportOptOut };
