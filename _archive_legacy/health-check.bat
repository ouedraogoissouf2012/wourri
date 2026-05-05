@echo off
title WhatsApp - Vérification Santé
color 0B
cd /d "C:\Users\USER PC\Documents\propre à moi\sendEmail\sendEmail\notification-service\whatsapp-server"

echo.
echo  =====================================================
echo   🏥 VÉRIFICATION SANTÉ WHATSAPP
echo  =====================================================
echo.
echo  📅 Date: %date% %time%
echo  📂 Dossier: %cd%
echo.

:check_server
echo  🔍 1. Vérification serveur...
curl -s http://localhost:3000/status >nul 2>&1
if errorlevel 1 (
    echo     ❌ Serveur non accessible
    echo     💡 Solution: Exécuter start-whatsapp.bat
    set server_ok=false
) else (
    echo     ✅ Serveur accessible
    set server_ok=true
)

:check_status
if "%server_ok%"=="true" (
    echo  📊 2. Statut de connexion...
    curl -s http://localhost:3000/status
    echo.
) else (
    echo  ⏭️  2. Statut ignoré (serveur non accessible)
)

:check_files
echo  📁 3. Vérification fichiers...
if exist "whatsapp-server.js" (
    echo     ✅ whatsapp-server.js
) else (
    echo     ❌ whatsapp-server.js manquant
)

if exist "test-whatsapp.js" (
    echo     ✅ test-whatsapp.js
) else (
    echo     ❌ test-whatsapp.js manquant
)

if exist "package.json" (
    echo     ✅ package.json
) else (
    echo     ❌ package.json manquant
)

if exist "node_modules" (
    echo     ✅ node_modules (dépendances)
) else (
    echo     ❌ node_modules manquant
    echo     💡 Solution: npm install
)

:check_sessions
echo  🔐 4. Sessions WhatsApp...
if exist ".wwebjs_auth" (
    echo     ✅ Sessions sauvegardées
    for /d %%d in (.wwebjs_auth\*) do (
        echo        📁 %%~nxd
    )
) else (
    echo     ℹ️  Aucune session (première utilisation)
)

:check_dependencies
echo  📦 5. Dépendances critiques...
node -e "console.log('Node.js: ' + process.version)" 2>nul
if errorlevel 1 (
    echo     ❌ Node.js non installé
) else (
    echo     ✅ Node.js installé
)

npm --version >nul 2>&1
if errorlevel 1 (
    echo     ❌ npm non disponible
) else (
    echo     ✅ npm disponible
)

:performance_test
if "%server_ok%"=="true" (
    echo  ⚡ 6. Test de performance...
    echo     🧪 Envoi d'un message de test...
    
    node test-whatsapp.js --test >test_result.tmp 2>&1
    
    findstr /i "envoyé avec succès" test_result.tmp >nul
    if not errorlevel 1 (
        echo     ✅ Test d'envoi réussi
    ) else (
        echo     ❌ Test d'envoi échoué
        echo     💡 Vérifiez l'authentification
    )
    
    del test_result.tmp >nul 2>&1
) else (
    echo  ⏭️  6. Test de performance ignoré
)

:security_check
echo  🔒 7. Vérification sécurité...
npm audit --audit-level=high >nul 2>&1
if errorlevel 1 (
    echo     ⚠️  Vulnérabilités détectées
    echo     💡 Solution: npm audit fix
) else (
    echo     ✅ Aucune vulnérabilité critique
)

:summary
echo.
echo  =====================================================
echo   📋 RÉSUMÉ DE SANTÉ
echo  =====================================================
echo.

if "%server_ok%"=="true" (
    echo  ✅ Serveur WhatsApp: OPÉRATIONNEL
) else (
    echo  ❌ Serveur WhatsApp: ARRÊTÉ
)

echo.
echo  🔧 Actions disponibles:
echo     [1] Redémarrer le serveur
echo     [2] Nettoyer complètement  
echo     [3] Surveillance continue
echo     [4] Ouvrir le guide
echo     [5] Test manuel
echo     [6] Quitter
echo.

:menu
set /p choice="Votre choix (1-6): "

if "%choice%"=="1" (
    echo  🚀 Redémarrage du serveur...
    start-whatsapp.bat
) else if "%choice%"=="2" (
    echo  🧹 Nettoyage complet...
    cleanup.bat
) else if "%choice%"=="3" (
    echo  👀 Surveillance continue...
    node test-whatsapp.js --monitor
) else if "%choice%"=="4" (
    echo  📖 Ouverture du guide...
    start notepad "GUIDE-COMPLET.md"
    goto menu
) else if "%choice%"=="5" (
    echo  🧪 Test manuel...
    node test-whatsapp.js --test
    pause
    goto menu
) else if "%choice%"=="6" (
    echo  👋 Vérification terminée!
) else (
    echo  ❌ Choix invalide
    goto menu
)

echo.
pause