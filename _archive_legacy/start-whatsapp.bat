@echo off
title Serveur WhatsApp - Démarrage
color 0A
cd /d "C:\Users\USER PC\Documents\propre à moi\sendEmail\sendEmail\notification-service\whatsapp-server"

echo.
echo  =====================================================
echo   📱 SERVEUR WHATSAPP - DEMARRAGE AUTOMATIQUE
echo  =====================================================
echo.
echo  📂 Dossier: %cd%
echo  🌐 Port: 3000
echo  📋 Guide: GUIDE-COMPLET.md
echo.

:check_node
echo  🔍 Vérification Node.js...
node --version >nul 2>&1
if errorlevel 1 (
    echo  ❌ Node.js non installé!
    echo  📥 Téléchargez depuis: https://nodejs.org/
    pause
    exit /b 1
)
echo  ✅ Node.js détecté

:check_npm
echo  🔍 Vérification npm...
npm --version >nul 2>&1
if errorlevel 1 (
    echo  ❌ npm non disponible!
    pause
    exit /b 1
)
echo  ✅ npm détecté

:check_dependencies
echo  🔍 Vérification des dépendances...
if not exist "node_modules" (
    echo  📦 Installation des dépendances...
    npm install
    if errorlevel 1 (
        echo  ❌ Échec installation dépendances!
        pause
        exit /b 1
    )
)
echo  ✅ Dépendances OK

:check_port
echo  🔍 Vérification du port 3000...
netstat -an | findstr ":3000" >nul 2>&1
if not errorlevel 1 (
    echo  ⚠️  Port 3000 occupé! Nettoyage...
    npx kill-port 3000 >nul 2>&1
    timeout /t 2 /nobreak >nul
)
echo  ✅ Port 3000 libre

:start_server
echo.
echo  🚀 Démarrage du serveur WhatsApp...
echo  📋 Après démarrage:
echo      - QR Code: http://localhost:3000/qr-page
echo      - Status:  http://localhost:3000/status
echo      - Tests:   node test-whatsapp.js --test
echo.
echo  ⏹️  Pour arrêter: Ctrl+C
echo.
echo  =====================================================
echo.

npm start

:error_handler
echo.
echo  ❌ Erreur lors du démarrage!
echo  💡 Solutions possibles:
echo     1. Exécuter: cleanup.bat
echo     2. Redémarrer l'ordinateur
echo     3. Consulter: GUIDE-COMPLET.md
echo.
pause