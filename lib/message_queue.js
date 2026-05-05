/**
 * Queue de messages persistante pour Wourri WhatsApp Server.
 *
 * Garantit qu'aucun message utilisateur n'est perdu si l'API backend est
 * temporairement indisponible. Les messages sont persistés sur disque
 * (fichier JSON) et retraités au prochain démarrage si besoin.
 *
 * Format du fichier (v1) :
 *   {
 *     "version": 1,
 *     "messages": [
 *       {
 *         "id": "wamsg_3EB0...",
 *         "userNumber": "22541540178@s.whatsapp.net",
 *         "payload": { ... },
 *         "createdAt": "2026-05-05T22:00:00.000Z",
 *         "attemptCount": 0,
 *         "lastError": null,
 *         "lastAttemptAt": null
 *       }
 *     ]
 *   }
 *
 * Sérialisation des écritures via une chaîne de promesses pour éviter
 * les race conditions sur fs.writeFile.
 */
"use strict";

const fsPromises = require("node:fs/promises");

class MessageQueue {
    /**
     * @param {object} options
     * @param {string} options.filePath - Chemin du fichier JSON de persistence
     * @param {number} [options.maxAttempts=5] - Tentatives max avant "mort"
     * @param {object} [options.fs] - Module fs.promises (injectable pour tests)
     * @param {Function} [options.now] - Source de temps (injectable)
     * @param {object} [options.logger] - Logger avec log/error
     */
    constructor(options = {}) {
        if (!options.filePath) {
            throw new Error("MessageQueue: filePath requis");
        }
        this.filePath = options.filePath;
        this.maxAttempts = options.maxAttempts || 5;
        this.fs = options.fs || fsPromises;
        this.now = options.now || (() => new Date().toISOString());
        this.logger = options.logger || console;

        this._messages = [];
        this._loaded = false;
        // Sérialise les writes pour éviter les écritures concurrentes
        this._saveChain = Promise.resolve();
    }

    /**
     * Charge la queue depuis le disque. À appeler une fois au démarrage.
     * @returns {Promise<number>} nombre de messages chargés
     */
    async load() {
        try {
            const data = await this.fs.readFile(this.filePath, "utf-8");
            const parsed = JSON.parse(data);
            if (parsed && Array.isArray(parsed.messages)) {
                this._messages = parsed.messages;
            } else {
                this._messages = [];
            }
        } catch (err) {
            if (err.code === "ENOENT") {
                this._messages = [];
            } else {
                this.logger.error(
                    `[QUEUE] Erreur chargement (${err.code || err.name}): ${err.message}. Démarrage avec queue vide.`
                );
                this._messages = [];
            }
        }
        this._loaded = true;
        return this._messages.length;
    }

    /**
     * Ajoute un message à la queue. Idempotent : si l'id existe déjà,
     * ne rajoute pas et retourne false.
     *
     * @param {object} msg
     * @param {string} msg.id - Identifiant unique du message (Baileys key.id)
     * @param {string} msg.userNumber - Numéro WhatsApp de l'utilisateur
     * @param {object} msg.payload - Données nécessaires au traitement
     * @returns {Promise<boolean>} true si ajouté, false si déjà présent
     */
    async add(msg) {
        if (!msg || !msg.id) {
            throw new Error("MessageQueue.add: msg.id is required");
        }
        if (this._messages.find((m) => m.id === msg.id)) {
            return false;
        }
        this._messages.push({
            id: msg.id,
            userNumber: msg.userNumber || null,
            payload: msg.payload || {},
            createdAt: this.now(),
            attemptCount: 0,
            lastError: null,
            lastAttemptAt: null,
        });
        await this._save();
        return true;
    }

    /**
     * Marque un message comme traité avec succès et le retire de la queue.
     * @param {string} id
     * @returns {Promise<boolean>} true si retiré, false si id inconnu
     */
    async markSuccess(id) {
        const before = this._messages.length;
        this._messages = this._messages.filter((m) => m.id !== id);
        if (this._messages.length === before) {
            return false;
        }
        await this._save();
        return true;
    }

    /**
     * Marque une tentative échouée. Incrémente attemptCount et garde
     * le message dans la queue (pour retry futur).
     * @param {string} id
     * @param {*} error - Erreur (Error, string, ou autre — sera stringify)
     * @returns {Promise<boolean>} true si trouvé, false si id inconnu
     */
    async markFailure(id, error) {
        const msg = this._messages.find((m) => m.id === id);
        if (!msg) return false;
        msg.attemptCount = (msg.attemptCount || 0) + 1;
        msg.lastAttemptAt = this.now();
        msg.lastError = error
            ? String(error.message || error).substring(0, 500)
            : null;
        await this._save();
        return true;
    }

    /**
     * Retourne les messages à retraiter (attemptCount < maxAttempts).
     * @param {object} [options]
     * @param {number} [options.limit=Infinity]
     * @returns {Array<object>} copie des entrées
     */
    getPending(options = {}) {
        const limit = options.limit ?? Infinity;
        return this._messages
            .filter((m) => (m.attemptCount || 0) < this.maxAttempts)
            .slice(0, limit)
            .map((m) => ({ ...m })); // copie défensive
    }

    /**
     * Retourne les messages "morts" (attemptCount >= maxAttempts).
     * À surveiller en observabilité (alerter si non vide).
     */
    getDead() {
        return this._messages
            .filter((m) => (m.attemptCount || 0) >= this.maxAttempts)
            .map((m) => ({ ...m }));
    }

    /**
     * Statistiques (pour /status, monitoring).
     */
    get stats() {
        const total = this._messages.length;
        const dead = this._messages.filter(
            (m) => (m.attemptCount || 0) >= this.maxAttempts
        ).length;
        return {
            total,
            pending: total - dead,
            dead,
            loaded: this._loaded,
        };
    }

    /**
     * Sérialise les writes : chaque appel est mis en queue derrière le précédent.
     * Évite les writes concurrents qui pourraient écraser des modifications.
     */
    _save() {
        const next = this._saveChain.then(() => this._doSave());
        // Ne pas propager les erreurs au prochain save (mais les logger)
        this._saveChain = next.catch(() => {});
        return next;
    }

    async _doSave() {
        const snapshot = JSON.stringify(
            { version: 1, messages: this._messages },
            null,
            2
        );
        try {
            await this.fs.writeFile(this.filePath, snapshot, "utf-8");
        } catch (err) {
            this.logger.error(
                `[QUEUE] Erreur sauvegarde (${err.code || err.name}): ${err.message}`
            );
            throw err;
        }
    }
}

module.exports = { MessageQueue };
