/**
 * Tests — calcul du contactRef (L2 #409 / L5c #412, socle commun).
 *
 * Convention FIGÉE avec Convex (Marcel, 2026-08-15) :
 *   contactRef = HMAC_SHA256(secret, numéro_normalisé) en hex minuscule, 64 car.
 *   numéro_normalisé = JID.split("@")[0]  (chiffres + indicatif 225, sans + ni @…)
 *
 * VERROU DE COHÉRENCE CROISÉE : le vecteur EXPECTED ci-dessous a été calculé avec
 * l'algorithme EXACT de la référence Python de Marcel. Si ce test casse, les
 * contactRef produits ici ne correspondront PAS à ceux stockés côté Convex
 * → diffusion (L2) et opt-out (L5c) muets. Ne jamais "ajuster" EXPECTED sans
 * revalider la convention avec Marcel.
 *
 * Exécution : node --test tests/contact_ref.test.js
 */
"use strict";

const { test, describe } = require("node:test");
const assert = require("node:assert");
const { computeContactRef, normalizeNumber } = require("../lib/contact_ref");

const SECRET = "s3cr3t-test-vector";
const JID = "2250701020304@s.whatsapp.net";
// hmac_sha256("s3cr3t-test-vector", "2250701020304").hexdigest() — réf. Python.
const EXPECTED = "0f71ce3b9b1f092c4f2ab3a67c3d24ebd1d0ffac1976debcb5223c1d0b214333";

describe("contact_ref — normalizeNumber", () => {
    test("extrait le numéro du JID (partie avant @)", () => {
        assert.strictEqual(normalizeNumber("2250701020304@s.whatsapp.net"), "2250701020304");
    });
    test("numéro nu inchangé", () => {
        assert.strictEqual(normalizeNumber("2250701020304"), "2250701020304");
    });
});

describe("contact_ref — computeContactRef", () => {
    test("correspond à la référence Python de Marcel (cohérence croisée)", () => {
        assert.strictEqual(computeContactRef(JID, SECRET), EXPECTED);
    });
    test("même résultat pour le JID complet et le numéro nu", () => {
        assert.strictEqual(computeContactRef("2250701020304", SECRET), EXPECTED);
    });
    test("hex minuscule, 64 caractères", () => {
        assert.match(computeContactRef(JID, SECRET), /^[0-9a-f]{64}$/);
    });
    test("déterministe", () => {
        assert.strictEqual(computeContactRef(JID, SECRET), computeContactRef(JID, SECRET));
    });
    test("secret différent → hash différent", () => {
        assert.notStrictEqual(
            computeContactRef(JID, SECRET),
            computeContactRef(JID, "autre-secret"),
        );
    });
    test("secret manquant → exception (fail-closed)", () => {
        assert.throws(() => computeContactRef(JID, ""), /secret/i);
    });
    test("JID vide → exception", () => {
        assert.throws(() => computeContactRef("", SECRET), /vide|invalide/i);
    });
});
