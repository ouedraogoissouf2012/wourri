/**
 * L5b #412 — POST /ingest/event (Convex).
 * Fire-and-forget : n'attend pas pour répondre à l'agriculteur.
 * Aucun numéro / texte de question dans le body.
 */
"use strict";

const HTTP_TIMEOUT_MS = 2000;

const LANG = {
    dioula: "dyu",
    french: "fr",
    english: "en",
    both: "both",
};

function mapLanguage(language) {
    return LANG[language] || String(language || "unknown");
}

/**
 * @returns {Promise<{ok: boolean, skipped?: string}>}
 */
async function reportIngest({
    axios,
    convexUrl,
    ingestKey,
    logger = console,
    requestId,
    language,
    intent,
    source,
    latencyMs,
    status,
    errorType,
}) {
    if (!convexUrl || !ingestKey || !requestId) {
        return { ok: false, skipped: "unconfigured" };
    }
    const body = {
        requestId,
        channel: "whatsapp",
        language: mapLanguage(language),
        intent: intent || "unknown",
        source: source || "unknown",
        latencyMs: Number.isFinite(latencyMs) ? Math.max(0, Math.round(latencyMs)) : 0,
        status,
    };
    if (errorType) body.errorType = errorType;
    try {
        await axios.post(
            `${String(convexUrl).replace(/\/$/, "")}/ingest/event`,
            body,
            {
                timeout: HTTP_TIMEOUT_MS,
                headers: { "X-Ingest-Key": ingestKey },
            },
        );
        return { ok: true };
    } catch (err) {
        logger.warn(
            { status: err.response?.status || err.code || "UNKNOWN" },
            "[INGEST] POST /ingest/event échoué — ignoré",
        );
        return { ok: false };
    }
}

module.exports = { reportIngest, mapLanguage };
