const axios = require('axios');

const WHATSAPP_SERVER = 'http://localhost:3000';

// Test de statut
async function testStatus() {
    try {
        console.log('🔍 Test du statut du serveur WhatsApp...');
        const response = await axios.get(`${WHATSAPP_SERVER}/status`);
        
        console.log('📊 Statut:', {
            connected: response.data.connected ? '✅ Connecté' : '❌ Déconnecté',
            ready: response.data.ready ? '✅ Prêt' : '❌ Non prêt',
            qr_needed: response.data.qr_needed ? '📱 QR requis' : '✅ Authentifié'
        });
        
        return response.data;
    } catch (error) {
        console.error('❌ Erreur lors du test de statut:', error.message);
        return null;
    }
}

// Test d'envoi de message
async function testMessageFunction(number, message) {
    try {
        console.log(`📤 Test d'envoi vers: ${number}`);
        console.log(`💬 Message: ${message.substring(0, 50)}...`);
        
        const response = await axios.post(`${WHATSAPP_SERVER}/send-message`, {
            number: number,
            message: message
        });
        
        if (response.data.success) {
            console.log('✅ Message envoyé avec succès !');
            console.log(`📧 ID: ${response.data.messageId}`);
            console.log(`⏰ Timestamp: ${response.data.timestamp}`);
        } else {
            console.log('❌ Échec d\'envoi:', response.data.error);
        }
        
        return response.data;
    } catch (error) {
        console.error('❌ Erreur lors de l\'envoi:', error.response?.data || error.message);
        return null;
    }
}

// Test complet
async function runTests() {
    console.log('🚀 Début des tests WhatsApp...\n');
    
    // Test 1: Statut
    const status = await testStatus();
    console.log('\n' + '='.repeat(50) + '\n');
    
    if (!status || !status.ready) {
        console.log('❌ Serveur non prêt. Tests d\'envoi annulés.');
        return;
    }
    
    // Test 2: Message de test (remplacez par votre numéro)
    const testNumber = '22544210112'; // Remplacez par votre numéro de test
    const testMessage = `🧪 Test de connexion WhatsApp\n⏰ ${new Date().toLocaleString()}\n✅ Serveur opérationnel !`;
    
    await testMessageFunction(testNumber, testMessage);
    
    console.log('\n🏁 Tests terminés !');
}

// Surveillance continue (optionnel)
async function monitorWhatsApp(intervalSeconds = 30) {
    console.log(`👀 Surveillance WhatsApp démarrée (intervalle: ${intervalSeconds}s)`);
    console.log('Appuyez sur Ctrl+C pour arrêter\n');
    
    setInterval(async () => {
        const status = await testStatus();
        const timestamp = new Date().toLocaleString();
        
        if (status) {
            if (status.connected && status.ready) {
                console.log(`[${timestamp}] ✅ WhatsApp opérationnel`);
            } else {
                console.log(`[${timestamp}] ⚠️  WhatsApp déconnecté ou non prêt`);
            }
        } else {
            console.log(`[${timestamp}] ❌ Serveur WhatsApp inaccessible`);
        }
    }, intervalSeconds * 1000);
}

// Gestion des arguments de ligne de commande
const args = process.argv.slice(2);

if (args.includes('--monitor')) {
    const interval = args.includes('--interval') ? 
        parseInt(args[args.indexOf('--interval') + 1]) || 30 : 30;
    monitorWhatsApp(interval);
} else if (args.includes('--test')) {
    runTests();
} else {
    console.log(`
📋 Script de test WhatsApp

Usage:
  node test-whatsapp.js --test          # Exécuter les tests
  node test-whatsapp.js --monitor       # Surveillance continue
  node test-whatsapp.js --monitor --interval 60  # Surveillance toutes les 60s

🔧 Configuration:
  - Modifiez la variable 'testNumber' pour vos tests
  - Serveur WhatsApp: ${WHATSAPP_SERVER}
    `);
}