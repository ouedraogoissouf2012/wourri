/**
 * Helpers partagés pour les tests node:test de whatsapp-server.
 *
 * Ce fichier NE contient PAS de tests — il ne doit jamais être passé en
 * argument à `node --test`. La commande de test du projet liste les fichiers
 * explicitement (cf. CLAUDE.md "Tests") donc `_helpers.js` est naturellement
 * exclu. Le préfixe `_` est une convention défensive pour signaler le statut
 * de support et exclure le fichier des éventuels globs `*.test.js`.
 *
 * Note : `makeAxiosMock` n'est intentionnellement PAS partagé ici. Les deux
 * consommateurs (response_sender.test.js et onboarding.test.js) exposent des
 * méthodes HTTP différentes (.get vs .post) ; unifier serait sur-engineering.
 *
 * Issue origine : #173 (suite review TESTS #170 — seuil 4 consommateurs).
 */
"use strict";

/**
 * Logger pino-compatible silencieux pour les tests.
 * Accepte les 3 méthodes utilisées par les modules (info/warn/error).
 */
const silentLogger = {
    info: () => {},
    warn: () => {},
    error: () => {},
};

/**
 * Fonction `randomDelay` no-op pour court-circuiter les délais humains
 * dans les tests (signature compatible : async (min, max) => Promise<void>).
 */
const noDelay = async () => {};

/**
 * Crée un mock de socket Baileys qui capture les appels.
 *
 * Capture les deux interactions principales :
 *   - sock.sendMessage(num, msg) → push dans `sent[]`
 *   - sock.sendPresenceUpdate(state, num) → push dans `presence[]`
 *
 * La version riche (avec `presence[]`) est compatible avec les tests qui
 * n'asserent pas sur la présence — les appels sont juste capturés sans
 * casser le contrat.
 *
 * @returns {{sent: Array, presence: Array, sendMessage: Function, sendPresenceUpdate: Function}}
 */
function makeSockMock() {
    const sent = [];
    const presence = [];
    return {
        sent,
        presence,
        sendMessage: async (num, msg) => { sent.push({ num, msg }); },
        sendPresenceUpdate: async (state, num) => { presence.push({ state, num }); },
    };
}

/**
 * Crée un mock de module `fs` minimal pour les tests qui manipulent
 * `user_preferences.json` ou autres fichiers JSON.
 *
 * @param {object} [options]
 * @param {object} [options.initial] - Contenu initial du "filesystem" virtuel ({ "/path": "content" })
 * @param {Error}  [options.writeFailsWith] - Si fourni, `writeFile` rappelle son callback avec cette erreur
 * @param {Error}  [options.renameFailsWith] - Si fourni, `rename` rappelle son callback avec cette erreur
 * @returns Mock avec existsSync, readFileSync, writeFile (async), writeFileSync, rename, renameSync
 */
function makeFsMock({ initial = {}, writeFailsWith = null, renameFailsWith = null } = {}) {
    const files = { ...initial };
    const writeCalls = [];
    const renameCalls = [];
    return {
        files,
        writeCalls,
        renameCalls,
        existsSync: (p) => p in files,
        readFileSync: (p) => {
            if (!(p in files)) {
                const err = new Error("ENOENT");
                err.code = "ENOENT";
                throw err;
            }
            return files[p];
        },
        writeFile: (p, content, enc, cb) => {
            writeCalls.push({ path: p, content });
            setImmediate(() => {
                if (writeFailsWith) {
                    cb(writeFailsWith);
                    return;
                }
                files[p] = content;
                cb(null);
            });
        },
        writeFileSync: (p, content) => {
            writeCalls.push({ path: p, content });
            files[p] = content;
        },
        rename: (from, to, cb) => {
            renameCalls.push({ from, to });
            setImmediate(() => {
                if (renameFailsWith) {
                    cb(renameFailsWith);
                    return;
                }
                files[to] = files[from];
                delete files[from];
                cb(null);
            });
        },
        renameSync: (from, to) => {
            renameCalls.push({ from, to });
            files[to] = files[from];
            delete files[from];
        },
    };
}

module.exports = { silentLogger, noDelay, makeSockMock, makeFsMock };
