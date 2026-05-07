/**
 * Cache local des audios d'excuse pour Wourri WhatsApp Server.
 *
 * Problème résolu : quand l'API TTS est down (cas circuit OPEN), le serveur
 * ne peut plus générer d'audio dioula et tombait sur un fallback texte
 * bilingue. Pour des utilisateurs dioula souvent peu alphabétisés, recevoir
 * du texte au lieu d'un audio est une mauvaise expérience.
 *
 * Solution : pré-générer une fois pour toutes les audios des messages
 * d'excuse (textes fixes) quand l'API est UP, et les rejouer telles quelles
 * quand l'API est DOWN.
 *
 * Format du dossier :
 *   audio_cache/
 *     unavailable_dioula.ogg
 *     unavailable_french.ogg
 *     back_dioula.ogg
 *     back_french.ogg
 *
 * Le cache est sur disque pour survivre aux redémarrages. Si l'API est
 * down dès le tout premier démarrage et que rien n'est en cache, on
 * retombe sur le fallback texte bilingue (comportement avant cette PR).
 */
"use strict";

const fsPromises = require("node:fs/promises");
const path = require("node:path");

// Clés autorisées pour le cache (alphanumeric + underscore + dash).
// Empêche path traversal (`../`, `/`) si une clé venait d'une source non
// contrôlée à l'avenir. Aujourd'hui les clés sont hardcodées mais le module
// est conçu pour être réutilisé (Cloud API future, autres caches).
const KEY_PATTERN = /^[a-zA-Z0-9_-]+$/;

class InvalidKeyError extends Error {
    constructor(key) {
        super(`AudioCache: clé invalide '${key}' (attendu : ${KEY_PATTERN})`);
        this.name = "InvalidKeyError";
    }
}

class AudioCache {
    /**
     * @param {object} options
     * @param {string} options.cacheDir - Dossier de stockage des fichiers .ogg
     * @param {Function} options.generateAudio - async (text, isFrench) => Buffer|null
     * @param {object} [options.fs] - Module fs.promises (injectable pour tests)
     * @param {object} [options.logger] - Logger avec info/warn/error
     */
    constructor(options = {}) {
        if (!options.cacheDir) {
            throw new Error("AudioCache: cacheDir requis");
        }
        if (typeof options.generateAudio !== "function") {
            throw new Error("AudioCache: generateAudio (function) requis");
        }
        this.cacheDir = options.cacheDir;
        this.generateAudio = options.generateAudio;
        this.fs = options.fs || fsPromises;
        this.logger = options.logger || console;
    }

    /**
     * Chemin absolu du fichier pour une clé donnée.
     * @throws {InvalidKeyError} si la clé contient des caractères non autorisés
     */
    _pathFor(key) {
        if (typeof key !== "string" || !KEY_PATTERN.test(key)) {
            throw new InvalidKeyError(key);
        }
        return path.join(this.cacheDir, `${key}.ogg`);
    }

    /** Crée le dossier de cache s'il n'existe pas. */
    async _ensureDir() {
        await this.fs.mkdir(this.cacheDir, { recursive: true });
    }

    /**
     * Lit un audio depuis le cache disque.
     *
     * Retourne null si le fichier est absent OU vide (cas d'un .ogg corrompu
     * ou d'une écriture interrompue) — l'appelant retombera sur génération
     * online ou fallback texte au lieu d'envoyer un audio invalide.
     *
     * @param {string} key - ex: "unavailable_dioula"
     * @returns {Promise<Buffer|null>} Buffer audio ou null si absent/vide
     */
    async get(key) {
        // Validation hors du try/catch : une clé invalide est un bug du caller
        // (fail-fast), pas une "absence" silencieuse.
        const filePath = this._pathFor(key);
        try {
            const buf = await this.fs.readFile(filePath);
            if (!buf || buf.length === 0) return null;
            return buf;
        } catch (err) {
            if (err.code !== "ENOENT") {
                this.logger.warn(
                    { err, key },
                    "[AUDIO-CACHE] Erreur lecture cache"
                );
            }
            return null;
        }
    }

    /**
     * Écrit un buffer audio dans le cache disque, de manière atomique.
     *
     * On écrit d'abord dans `<key>.ogg.tmp` puis on `rename` vers `<key>.ogg`.
     * `rename` sur le même filesystem est atomique sur Windows comme sur POSIX,
     * donc un `get()` concurrent verra soit l'ancien fichier complet, soit le
     * nouveau, jamais un fichier tronqué (utile au boot où le warmup et
     * notifyPendingUsers peuvent toucher le même cache en parallèle).
     *
     * @param {string} key - ex: "unavailable_dioula"
     * @param {Buffer} buffer - Contenu OGG/Opus
     */
    async save(key, buffer) {
        await this._ensureDir();
        const finalPath = this._pathFor(key);
        const tmpPath = `${finalPath}.tmp`;
        await this.fs.writeFile(tmpPath, buffer);
        try {
            await this.fs.rename(tmpPath, finalPath);
        } catch (err) {
            // Best-effort cleanup du tmp orphelin (ne masque pas l'erreur originale)
            try { await this.fs.unlink(tmpPath); } catch (_) {}
            throw err;
        }
    }

    /**
     * Pré-génère les 4 audios d'excuse fixes en appelant generateAudio.
     * À appeler au démarrage seulement si l'API est healthy.
     *
     * Stratégie : pour chaque entrée, si déjà en cache disque on ne refait
     * rien (économie d'appels TTS et latence démarrage). Sinon on génère
     * et on sauve. Les échecs sont loggués mais non-bloquants : le cache
     * peut rester partiel sans casser le serveur.
     *
     * @param {Array<{key: string, text: string, isFrench: boolean}>} entries
     * @returns {Promise<{generated: number, cached: number, failed: number}>}
     */
    async warmup(entries) {
        await this._ensureDir();
        let generated = 0;
        let cached = 0;
        let failed = 0;

        for (const { key, text, isFrench } of entries) {
            const existing = await this.get(key);
            if (existing) {
                cached++;
                continue;
            }
            try {
                const buffer = await this.generateAudio(text, isFrench);
                if (!buffer) {
                    failed++;
                    this.logger.warn(
                        { key },
                        "[AUDIO-CACHE] Génération a renvoyé null — cache non rempli"
                    );
                    continue;
                }
                await this.save(key, buffer);
                generated++;
                this.logger.info(
                    { key, bytes: buffer.length },
                    "[AUDIO-CACHE] Audio généré et caché"
                );
            } catch (err) {
                failed++;
                this.logger.warn(
                    { err, key },
                    "[AUDIO-CACHE] Échec génération/sauvegarde"
                );
            }
        }

        return { generated, cached, failed };
    }
}

module.exports = { AudioCache, InvalidKeyError };
