/**
 * Gestion des préférences utilisateurs Wourri (city, language, step, pendingQuestion).
 *
 * Structure d'une entrée :
 *   "22541540178@s.whatsapp.net": {
 *     city: "Bonoua",
 *     language: "both" | "french" | "dioula",
 *     step: "new" | "waiting_city" | "waiting_language" | "complete" | "waiting_feedback",
 *     pendingQuestion: string | null,
 *     pendingFeedback: object | null
 *   }
 *
 * Persistance : fichier JSON unique (`user_preferences.json` en prod).
 * Le verrou `_saveInProgress` / `_savePending` débounce les écritures concurrentes :
 * si une sauvegarde est en cours, la suivante est mise en attente et rejouée une
 * fois la première terminée. Évite les pertes de mutations rapprochées.
 */
"use strict";

const DEFAULT_USER_LANGUAGE = "french";

const STEPS = {
    NEW: "new",
    WAITING_CITY: "waiting_city",
    WAITING_LANGUAGE: "waiting_language",
    COMPLETE: "complete",
    WAITING_FEEDBACK: "waiting_feedback",
};

class UserPrefs {
    /**
     * @param {object} options
     * @param {object} options.fs - Module fs natif (injectable pour tests)
     * @param {string} options.filePath - Chemin absolu du fichier JSON
     * @param {object} [options.logger] - Logger avec info/error (défaut: console)
     */
    constructor(options = {}) {
        if (!options.fs) {
            throw new Error("UserPrefs: fs requis");
        }
        if (!options.filePath) {
            throw new Error("UserPrefs: filePath requis");
        }
        this.fs = options.fs;
        this.filePath = options.filePath;
        this.logger = options.logger || console;

        this._data = {};
        this._saveInProgress = false;
        this._savePending = false;
    }

    /** Référence live vers l'objet des préférences (mutations visibles depuis get()). */
    get data() {
        return this._data;
    }

    /** Charge synchrone le fichier JSON. Si erreur, conserve un état vide sans throw. */
    load() {
        try {
            if (this.fs.existsSync(this.filePath)) {
                const raw = this.fs.readFileSync(this.filePath, "utf8");
                this._data = JSON.parse(raw);
                this.logger.info(`[PREFS] ${Object.keys(this._data).length} utilisateurs charges`);
            }
        } catch (error) {
            this.logger.error(`[PREFS] Erreur chargement: ${error.message}`);
            this._data = {};
        }
    }

    /**
     * Sauvegarde async débouncée ET atomique (tmp + rename).
     *
     * Écrit d'abord `<filePath>.tmp` puis `rename` vers `filePath` — le
     * rename est atomique sur le même filesystem (Windows comme POSIX).
     * Un crash pendant l'écriture laisse au pire un `.tmp` orphelin :
     * le fichier des préférences de TOUS les utilisateurs n'est jamais
     * tronqué/corrompu (avant ce fix, un crash mid-write = perte totale
     * au prochain `load()`). Même idiome que `audio_cache.js::save`.
     *
     * Si une écriture est déjà en cours, marque `_savePending` et rejoue
     * à la fin de l'écriture courante.
     */
    save() {
        if (this._saveInProgress) {
            this._savePending = true;
            return;
        }
        this._saveInProgress = true;
        const snapshot = JSON.stringify(this._data, null, 2);
        const tmpPath = `${this.filePath}.tmp`;
        this.fs.writeFile(tmpPath, snapshot, "utf8", (err) => {
            if (err) {
                this._saveInProgress = false;
                this.logger.error(`[PREFS] Erreur sauvegarde: ${err.message}`);
                this._replayPendingSave();
                return;
            }
            this.fs.rename(tmpPath, this.filePath, (renameErr) => {
                this._saveInProgress = false;
                if (renameErr) {
                    this.logger.error(`[PREFS] Erreur rename: ${renameErr.message}`);
                }
                this._replayPendingSave();
            });
        });
    }

    /** Rejoue une sauvegarde mise en attente pendant l'écriture courante. */
    _replayPendingSave() {
        if (this._savePending) {
            this._savePending = false;
            this.save();
        }
    }

    /**
     * Sauvegarde synchrone atomique — réservée au graceful shutdown
     * (SIGINT/SIGTERM dans app-baileys.js) où l'event loop va s'arrêter.
     * Même garantie tmp+rename que `save()`.
     */
    saveSync() {
        const snapshot = JSON.stringify(this._data, null, 2);
        const tmpPath = `${this.filePath}.tmp`;
        this.fs.writeFileSync(tmpPath, snapshot, "utf8");
        this.fs.renameSync(tmpPath, this.filePath);
    }

    /**
     * Retourne la référence vers l'entrée de l'utilisateur. Crée une entrée
     * par défaut (step=NEW) si absente. Les mutations sur l'objet retourné
     * sont visibles dans this._data (référence partagée).
     */
    get(userNumber) {
        if (!this._data[userNumber]) {
            this._data[userNumber] = {
                city: null,
                language: null,
                step: STEPS.NEW,
                pendingQuestion: null,
                pendingFeedback: null,
            };
        }
        return this._data[userNumber];
    }
}

module.exports = { UserPrefs, STEPS, DEFAULT_USER_LANGUAGE };
