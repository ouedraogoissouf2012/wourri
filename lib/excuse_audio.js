/**
 * Sous-système audio des messages d'excuse pour Wourri WhatsApp Server.
 *
 * Extrait de app-baileys.js (modularisation) : regroupe les textes d'excuse
 * fixes (EXCUSE_MSG), la génération TTS best-effort via wouri-api, et le
 * cache disque (AudioCache) avec stratégie cache-d'abord/fallback-online.
 *
 * Le pattern DI (dépendances injectées au constructeur) est cohérent avec
 * les autres modules lib/ (AsrClient, ResponseSender, AudioCache) et rend le
 * module testable sans réseau ni filesystem réel.
 *
 * `getExcuseAudio` est bindé dans le constructeur car ResponseSender le reçoit
 * comme fonction injectée et l'appelle hors du contexte de l'instance.
 */
"use strict";

const { AudioCache } = require("./audio_cache");

// Timeout court par défaut : ne pas bloquer l'envoi si l'API TTS traîne.
const DEFAULT_TTS_TIMEOUT_MS = 5000;

// Textes des messages d'indisponibilité (utilisés pour TTS si vocal, sinon texte).
const EXCUSE_MSG = {
    // Circuit OPEN : "je rencontre un problème"
    UNAVAILABLE_FR: "Je rencontre un problème technique temporaire. Je te répondrai dès que possible.",
    UNAVAILABLE_DIOULA: "N bɛ baara la sisan. N bɛna jaabi i ma joona.",
    UNAVAILABLE_BILINGUAL:
        '🌾 N bɛ baara la sisan. N bɛna jaabi i ma joona.\n\n---\n🌾 Je rencontre un problème technique temporaire. Je te répondrai dès que possible.',
    // Reconnexion WA : "je suis de retour"
    BACK_FR: "Je suis de retour. Pose-moi à nouveau ta question.",
    BACK_DIOULA: "N nana segin. I ka ɲinini ci tugu n ma.",
    BACK_BILINGUAL:
        '🌾 Aw ni ce, n nana segin. Aw ka ɲinini ci tugu n ma.\n\n---\n🌾 Je suis de retour. Pose-moi à nouveau ta question.',
};

class ExcuseAudio {
    /**
     * @param {object} options
     * @param {string} options.apiUrl - Base URL wouri-api (ex: http://localhost:8000)
     * @param {Function} options.authHeaders - () => object, headers d'auth (X-API-Key)
     * @param {string} [options.cacheDir] - Dossier du cache disque (requis si audioCache absent)
     * @param {object} [options.audioCache] - Instance AudioCache injectable (tests)
     * @param {object} [options.axios] - Module axios injectable (tests)
     * @param {object} [options.logger] - Logger avec info/warn/error (défaut: console)
     */
    constructor(options = {}) {
        if (!options.apiUrl) {
            throw new Error("ExcuseAudio: apiUrl requis");
        }
        if (typeof options.authHeaders !== "function") {
            throw new Error("ExcuseAudio: authHeaders (function) requis");
        }
        if (!options.cacheDir && !options.audioCache) {
            throw new Error("ExcuseAudio: cacheDir (ou audioCache) requis");
        }
        this.apiUrl = options.apiUrl;
        this.authHeaders = options.authHeaders;
        this.logger = options.logger || console;
        this.axios = options.axios || require("axios");
        this.audioCache = options.audioCache || new AudioCache({
            cacheDir: options.cacheDir,
            generateAudio: (text, isFrench) => this.tryGenerateAudioFromText(text, isFrench),
            logger: this.logger,
        });
        // ResponseSender reçoit getExcuseAudio comme fonction et l'appelle sans
        // le `this` de ExcuseAudio → bind indispensable pour préserver le contexte.
        this.getExcuseAudio = this.getExcuseAudio.bind(this);
    }

    /**
     * Génère un audio TTS à partir d'un texte fixe (best-effort).
     *
     * Utilisé pour les messages d'indisponibilité audio quand l'utilisateur a
     * envoyé un vocal. Si l'API TTS est down ou trop lente, retourne null et le
     * caller fallback sur du texte.
     *
     * Endpoints (côté wouri-api) :
     *   - français : POST /api/tts/french?text=...
     *   - dioula   : POST /api/tts/dioula?text=...&is_french=false
     *     (ADR-0023 #362 : voix mms-tts-dyu — avant, /api/tts/bambara servait la
     *      voix bambara MALIENNE pour les messages système alors que les réponses
     *      du bot sortaient en voix dioula : deux voix pour le même utilisateur.)
     *
     * Note : /api/tts/french (et non /api/tts/) car ce dernier attend un body
     * JSON Pydantic TTSRequest, alors que /api/tts/french accepte le texte en
     * query param — sinon 422 (cas reproduit lors du warmup audio_cache).
     *
     * @param {string} text - Texte à synthétiser
     * @param {boolean} isFrench - true → Edge-TTS français, false → MMS dioula
     * @param {number} [timeoutMs=5000] - Timeout court pour ne pas bloquer
     * @returns {Promise<Buffer|null>} Buffer audio OGG/Opus, ou null si échec
     */
    async tryGenerateAudioFromText(text, isFrench, timeoutMs = DEFAULT_TTS_TIMEOUT_MS) {
        if (!text) return null;
        const endpoint = isFrench ? "/api/tts/french" : "/api/tts/dioula";
        const params = isFrench ? { text } : { text, is_french: false };
        try {
            const ttsResponse = await this.axios.post(
                `${this.apiUrl}${endpoint}`,
                null,
                { params, timeout: timeoutMs, headers: this.authHeaders() }
            );
            const audioUrl = ttsResponse.data?.audio_url;
            if (!audioUrl) return null;
            const fullUrl = audioUrl.startsWith("http")
                ? audioUrl
                : `${this.apiUrl}${audioUrl}`;
            const audioResp = await this.axios.get(fullUrl, {
                responseType: "arraybuffer",
                timeout: timeoutMs,
            });
            return Buffer.from(audioResp.data);
        } catch (err) {
            this.logger.info(
                `[EXCUSE-AUDIO] Génération ${isFrench ? "FR" : "dioula"} échouée (${err.code || (err.message || "").substring(0, 80)}) — fallback texte`
            );
            return null;
        }
    }

    /** Liste des 4 entrées d'excuse à pré-générer au démarrage. */
    buildCacheEntries() {
        return [
            { key: "unavailable_dioula", text: EXCUSE_MSG.UNAVAILABLE_DIOULA, isFrench: false },
            { key: "unavailable_french", text: EXCUSE_MSG.UNAVAILABLE_FR, isFrench: true },
            { key: "back_dioula", text: EXCUSE_MSG.BACK_DIOULA, isFrench: false },
            { key: "back_french", text: EXCUSE_MSG.BACK_FR, isFrench: true },
        ];
    }

    /**
     * Récupère l'audio d'excuse pour {kind, isFrench}.
     *
     * Stratégie : cache disque d'abord (rapide, fonctionne même si API down).
     * Cache miss → tentative online via tryGenerateAudioFromText. En cas de
     * succès online, on remplit le cache pour la prochaine fois (best-effort,
     * non-bloquant).
     *
     * @param {object} args
     * @param {'unavailable'|'back'} args.kind
     * @param {boolean} args.isFrench
     * @returns {Promise<Buffer|null>} Buffer audio OGG/Opus, ou null si échec total
     */
    async getExcuseAudio({ kind, isFrench }) {
        const key = `${kind === "back" ? "back" : "unavailable"}_${isFrench ? "french" : "dioula"}`;
        const cached = await this.audioCache.get(key);
        if (cached) {
            this.logger.info({ key, bytes: cached.length }, "[EXCUSE-AUDIO] Cache hit");
            return cached;
        }
        const text = isFrench
            ? (kind === "back" ? EXCUSE_MSG.BACK_FR : EXCUSE_MSG.UNAVAILABLE_FR)
            : (kind === "back" ? EXCUSE_MSG.BACK_DIOULA : EXCUSE_MSG.UNAVAILABLE_DIOULA);
        const fresh = await this.tryGenerateAudioFromText(text, isFrench);
        if (fresh) {
            this.audioCache.save(key, fresh).catch((err) =>
                this.logger.warn({ err, key }, "[EXCUSE-AUDIO] Save cache fail (non-bloquant)")
            );
            return fresh;
        }
        return null;
    }

    /**
     * Pré-génère les audios d'excuse (warmup démarrage, si API healthy).
     * @returns {Promise<{generated: number, cached: number, failed: number}>}
     */
    async warmup() {
        return this.audioCache.warmup(this.buildCacheEntries());
    }
}

module.exports = { ExcuseAudio, EXCUSE_MSG };
