/**
 * contactRef — identifiant opaque d'un agriculteur partagé avec Convex
 * (socle commun de L2 diffusion #409 et L5c opt-out #412).
 *
 * Convention FIGÉE avec Convex (Marcel, 2026-08-15) :
 *   contactRef = HMAC_SHA256(secret, numéro_normalisé), en hex minuscule (64 car.,
 *   non tronqué). numéro_normalisé = partie du JID avant "@" (chiffres + indicatif
 *   225, sans "+" ni "@s.whatsapp.net").
 *
 * Convex NE calcule aucun hash et NE voit jamais de numéro : il stocke le
 * contactRef opaque tel quel. La correspondance repose donc entièrement sur le
 * fait que le serveur WhatsApp utilise CETTE fonction des deux côtés — pour
 * PEUPLER (POST /whatsapp/farmer) ET pour RÉSOUDRE une contactRef reçue de
 * /alerts/pending. Le secret vit uniquement côté WhatsApp (secret Dokploy
 * WOURI_CONTACTREF_HMAC_SECRET), jamais dans Convex ni dans le dépôt.
 */
"use strict";

const crypto = require("node:crypto");

/**
 * Numéro normalisé à partir d'un JID (ou d'un numéro nu).
 * Reproduit exactement la référence : `jid.split("@")[0]`.
 * @param {string} jidOrNumber - ex. "2250701020304@s.whatsapp.net" ou "2250701020304"
 * @returns {string} ex. "2250701020304"
 */
function normalizeNumber(jidOrNumber) {
    return String(jidOrNumber == null ? "" : jidOrNumber).split("@")[0];
}

/**
 * Calcule le contactRef d'un agriculteur.
 * @param {string} jidOrNumber - JID WhatsApp ou numéro nu
 * @param {string} secret - WOURI_CONTACTREF_HMAC_SECRET
 * @returns {string} HMAC-SHA256 en hex minuscule (64 caractères)
 * @throws si le secret est absent ou le numéro vide (fail-closed)
 */
function computeContactRef(jidOrNumber, secret) {
    if (!secret) {
        throw new Error(
            "contactRef: secret HMAC manquant (WOURI_CONTACTREF_HMAC_SECRET)",
        );
    }
    const numero = normalizeNumber(jidOrNumber);
    if (!numero) {
        throw new Error("contactRef: numéro vide (JID invalide)");
    }
    return crypto.createHmac("sha256", secret).update(numero, "utf8").digest("hex");
}

module.exports = { computeContactRef, normalizeNumber };
