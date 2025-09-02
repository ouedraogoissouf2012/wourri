@echo off
title WhatsApp - Nettoyage Complet
color 0C
cd /d "C:\Users\USER PC\Documents\propre à moi\sendEmail\sendEmail\notification-service\whatsapp-server"

echo.
echo  =====================================================
echo   🧹 NETTOYAGE COMPLET WHATSAPP
echo  =====================================================
echo.
echo  ⚠️  ATTENTION: Cette opération va:
echo     - Arrêter le serveur WhatsApp
echo     - Supprimer toutes les sessions
echo     - Supprimer le cache
echo     - Nécessiter une nouvelle authentification
echo.
set /p confirm="Continuer? (O/N): "
if /i "%confirm%" neq "O" (
    echo  ❌ Opération annulée
    pause
    exit /b 0
)

echo.
echo  🛑 1. Arrêt du serveur WhatsApp...
npx kill-port 3000 >nul 2>&1
if errorlevel 1 (
    echo     ⚠️  Aucun processus sur port 3000
) else (
    echo     ✅ Serveur arrêté
)

echo  🗑️  2. Suppression des sessions...
if exist ".wwebjs_auth" (
    rmdir /s /q ".wwebjs_auth" >nul 2>&1
    echo     ✅ Sessions supprimées
) else (
    echo     ℹ️  Aucune session à supprimer
)

echo  🗑️  3. Suppression du cache...
if exist ".wwebjs_cache" (
    rmdir /s /q ".wwebjs_cache" >nul 2>&1
    echo     ✅ Cache supprimé
) else (
    echo     ℹ️  Aucun cache à supprimer
)

echo  🧹 4. Nettoyage des logs temporaires...
if exist "debug.log" (
    del /q "debug.log" >nul 2>&1
    echo     ✅ Logs supprimés
)

echo  🔍 5. Vérification des dépendances...
npm list --depth=0 >nul 2>&1
if errorlevel 1 (
    echo     ⚠️  Réinstallation des dépendances...
    npm install >nul 2>&1
    if errorlevel 1 (
        echo     ❌ Erreur installation!
    ) else (
        echo     ✅ Dépendances réinstallées
    )
) else (
    echo     ✅ Dépendances OK
)

echo.
echo  =====================================================
echo   ✅ NETTOYAGE TERMINÉ
echo  =====================================================
echo.
echo  📋 Prochaines étapes:
echo     1. Démarrer: start-whatsapp.bat
echo     2. Scanner QR: http://localhost:3000/qr-page
echo     3. Tester: node test-whatsapp.js --test
echo.

:menu
echo  Que voulez-vous faire maintenant?
echo  [1] Démarrer le serveur
echo  [2] Ouvrir le guide complet
echo  [3] Quitter
echo.
set /p choice="Votre choix (1-3): "

if "%choice%"=="1" (
    echo.
    echo  🚀 Démarrage du serveur...
    npm start
) else if "%choice%"=="2" (
    echo.
    echo  📖 Ouverture du guide...
    start notepad "GUIDE-COMPLET.md"
    goto menu
) else if "%choice%"=="3" (
    echo  👋 Au revoir!
    pause
    exit /b 0
) else (
    echo  ❌ Choix invalide
    goto menu
)

pause