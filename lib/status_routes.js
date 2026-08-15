/**
 * Routes HTTP de statut / administration du serveur Wourri WhatsApp.
 *
 * Extrait de app-baileys.js (modularisation) : regroupe les routes /, /status,
 * /health, /ready, /users, /qr, /qr-page, /logout et sort le template HTML de
 * la page QR (~54 lignes statiques) hors du fichier d'entrée.
 *
 * L'état mutable du serveur (sock, connexion, QR courant) est passé via des
 * getters : les routes doivent lire l'état LIVE, pas un snapshot figé au
 * moment de l'enregistrement (sock est réassigné à chaque reconnexion).
 */
"use strict";

/**
 * Rend la page HTML du QR code (auto-refresh 5s).
 * @param {object} args
 * @param {boolean} args.isConnected
 * @param {string|null} args.qrCodeData - payload QR courant (ou null)
 * @param {object} args.QRCode - lib `qrcode` (toDataURL)
 * @returns {Promise<string>} HTML complet
 */
async function renderQrPage({ isConnected, qrCodeData, QRCode }) {
    let qrImageHtml = "";
    let statusMessage = "";

    if (isConnected) {
        statusMessage = '<div style="color: #4CAF50; font-size: 24px;">✅ CONNECTE A WHATSAPP!</div>';
    } else if (qrCodeData) {
        try {
            const qrDataUrl = await QRCode.toDataURL(qrCodeData, { width: 300 });
            qrImageHtml = `<img src="${qrDataUrl}" alt="QR Code" style="border: 4px solid #25D366; border-radius: 10px;">`;
            statusMessage = '<div style="color: #FFA500;">⏳ En attente de scan...</div>';
        } catch (err) {
            statusMessage = '<div style="color: red;">Erreur generation QR</div>';
        }
    } else {
        statusMessage = '<div style="color: #888;">QR code en cours de generation...</div>';
    }

    return `
    <!DOCTYPE html>
    <html>
    <head>
        <title>WOURI - Connexion WhatsApp</title>
        <meta charset="UTF-8">
        <meta http-equiv="refresh" content="5">
        <style>
            body {
                font-family: Arial, sans-serif;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #075E54 0%, #128C7E 100%);
                color: white;
            }
            .container {
                background: white;
                padding: 40px;
                border-radius: 20px;
                text-align: center;
                box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            }
            h1 { color: #075E54; margin-bottom: 10px; }
            h2 { color: #666; font-weight: normal; margin-top: 0; }
            .qr-container { margin: 20px 0; }
            .instructions { color: #666; margin-top: 20px; text-align: left; }
            .instructions ol { padding-left: 20px; }
            .refresh-note { color: #999; font-size: 12px; margin-top: 15px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🌾 WOURI</h1>
            <h2>Assistant Agricole WhatsApp</h2>
            <div class="qr-container">${qrImageHtml}</div>
            ${statusMessage}
            <div class="instructions">
                <strong>Pour connecter WhatsApp:</strong>
                <ol>
                    <li>Ouvrez WhatsApp sur votre telephone</li>
                    <li>Allez dans Parametres > Appareils lies</li>
                    <li>Appuyez sur "Lier un appareil"</li>
                    <li>Scannez ce QR code</li>
                </ol>
            </div>
            <div class="refresh-note">Page auto-refresh toutes les 5 secondes</div>
        </div>
    </body>
    </html>
    `;
}

/**
 * Enregistre les routes de statut/administration sur l'app Express.
 *
 * @param {object} app - Application Express
 * @param {object} ctx
 * @param {Function} ctx.getIsConnected - () => boolean (état live)
 * @param {Function} ctx.getQrCodeData - () => string|null (QR courant)
 * @param {Function} ctx.getSock - () => socket Baileys|null (réassigné au reconnect)
 * @param {object} ctx.userPrefs - expose .data
 * @param {string} ctx.authFolder - chemin du dossier auth_baileys (pour /logout)
 * @param {object} ctx.fs - module fs (existsSync/rmSync, injectable)
 * @param {object} ctx.QRCode - lib qrcode (toDataURL)
 * @param {object} ctx.health - HealthReporter (buildPayload)
 */
function registerStatusRoutes(app, ctx) {
    const {
        getIsConnected,
        getQrCodeData,
        getSock,
        userPrefs,
        authFolder,
        fs,
        QRCode,
        health,
    } = ctx;

    if (typeof getIsConnected !== "function") {
        throw new Error("registerStatusRoutes: ctx.getIsConnected (function) requis");
    }
    if (!health || typeof health.buildPayload !== "function") {
        throw new Error("registerStatusRoutes: ctx.health.buildPayload requis");
    }

    app.get("/", (req, res) => {
        res.json({
            status: "running",
            name: "WOURI WhatsApp Server",
            connected: getIsConnected(),
            users: Object.keys(userPrefs.data).length,
        });
    });

    app.get("/status", (req, res) => {
        res.json({
            connected: getIsConnected(),
            qrCode: getQrCodeData(),
            users: Object.keys(userPrefs.data).length,
        });
    });

    // /health : healthcheck riche, toujours 200 (le statut est dans le body)
    app.get("/health", (req, res) => {
        res.json(health.buildPayload());
    });

    // /ready : Kubernetes readiness probe — 200 si prêt, 503 sinon
    app.get("/ready", (req, res) => {
        const payload = health.buildPayload();
        const ready = payload.status === "ok";
        res.status(ready ? 200 : 503).json({
            status: payload.status,
            ready,
            reasons: payload.reasons,
        });
    });

    app.get("/users", (req, res) => {
        // Retourne les preferences de tous les utilisateurs (numero tronque pour confidentialite)
        const users = Object.entries(userPrefs.data).map(([number, prefs]) => ({
            number: number.substring(0, 8) + "***",
            city: prefs.city,
            language: prefs.language,
            step: prefs.step,
        }));
        res.json(users);
    });

    app.get("/qr", (req, res) => {
        const qrCodeData = getQrCodeData();
        if (qrCodeData) {
            res.json({ qr: qrCodeData });
        } else if (getIsConnected()) {
            res.json({ message: "Deja connecte" });
        } else {
            res.json({ message: "QR code pas encore genere" });
        }
    });

    app.get("/qr-page", async (req, res) => {
        res.send(await renderQrPage({
            isConnected: getIsConnected(),
            qrCodeData: getQrCodeData(),
            QRCode,
        }));
    });

    app.post("/logout", async (req, res) => {
        try {
            const sock = getSock();
            if (sock) {
                await sock.logout();
            }
            if (fs.existsSync(authFolder)) {
                fs.rmSync(authFolder, { recursive: true });
            }
            res.json({ success: true, message: "Deconnecte" });
        } catch (error) {
            res.status(500).json({ error: error.message });
        }
    });
}

module.exports = { registerStatusRoutes, renderQrPage };
