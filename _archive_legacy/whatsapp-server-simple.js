const express = require('express');
const cors = require('cors');

const app = express();
const PORT = 3000;

app.use(express.json());
app.use(cors());

// Variables d'état
let isConnected = false;
let isReady = false;
let qrCodeData = null;

// Simulation d'état WhatsApp pour éviter les erreurs Puppeteer
let simulatedConnection = false;

console.log('🚀 Serveur WhatsApp simple démarré sur http://localhost:3000');
console.log('⚠️  Mode simulation - pas de vraie connexion WhatsApp');

// Simuler la connexion après quelques secondes
setTimeout(() => {
    simulatedConnection = true;
    isConnected = true;
    isReady = true;
    qrCodeData = null;
    console.log('✅ Mode simulation activé - serveur prêt pour les tests');
}, 3000);

// API Routes
app.get('/status', (req, res) => {
    res.json({
        connected: isConnected,
        ready: isReady,
        qr_needed: qrCodeData !== null,
        mode: 'simulation'
    });
});

app.get('/qr', (req, res) => {
    if (simulatedConnection) {
        res.json({
            qr: null,
            message: "Mode simulation - pas de QR code nécessaire"
        });
    } else {
        res.json({
            qr: "simulation_qr_code",
            message: "Mode simulation - scannez ce QR fictif"
        });
    }
});

// Envoyer un message (simulation)
app.post('/send-message', async (req, res) => {
    try {
        const { number, message } = req.body;

        if (!number || !message) {
            return res.status(400).json({
                success: false,
                error: "Numéro et message requis"
            });
        }

        if (!isReady) {
            return res.status(503).json({
                success: false,
                error: "Service non prêt",
                mode: 'simulation'
            });
        }

        console.log(`📤 SIMULATION - Envoi vers: ${number}`);
        console.log(`📝 SIMULATION - Message: ${message.substring(0, 50)}...`);

        // Simulation d'envoi réussi
        const messageId = 'sim_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        
        console.log('✅ SIMULATION - Message WhatsApp "envoyé" !');

        res.json({
            success: true,
            messageId: messageId,
            to: number,
            timestamp: new Date().toISOString(),
            mode: 'simulation'
        });

    } catch (error) {
        console.error('❌ Erreur simulation:', error);
        res.status(500).json({
            success: false,
            error: error.message,
            mode: 'simulation'
        });
    }
});

// Route de test
app.get('/', (req, res) => {
    res.json({
        status: 'running',
        mode: 'simulation',
        message: 'Serveur WhatsApp en mode simulation',
        endpoints: {
            status: 'GET /status',
            qr: 'GET /qr',
            sendMessage: 'POST /send-message'
        }
    });
});

// Démarrage
app.listen(PORT, () => {
    console.log(`🌐 Serveur disponible sur http://localhost:${PORT}`);
    console.log('📋 Endpoints disponibles:');
    console.log('   GET  /status     - État de la connexion');
    console.log('   GET  /qr         - Code QR si nécessaire');
    console.log('   POST /send-message - Envoyer un message');
    console.log('');
    console.log('💡 Ce serveur simule l\'envoi WhatsApp pour éviter les erreurs Puppeteer');
    console.log('💡 Pour une vraie connexion WhatsApp, installez Node.js 20 LTS');
});