@echo off
echo 🔍 Surveillance WhatsApp - Demarrage...
echo.
echo Commands disponibles:
echo   1. Status simple:     curl -s http://localhost:3000/status
echo   2. Surveillance:      node test-whatsapp.js --monitor
echo   3. Test complet:      node test-whatsapp.js --test
echo.

:menu
echo Choisissez une option:
echo [1] Verifier le statut
echo [2] Surveillance continue (30s)
echo [3] Test d'envoi
echo [4] Voir les logs serveur
echo [5] Quitter
echo.
set /p choice="Votre choix (1-5): "

if "%choice%"=="1" goto status
if "%choice%"=="2" goto monitor
if "%choice%"=="3" goto test
if "%choice%"=="4" goto logs
if "%choice%"=="5" goto end
goto menu

:status
echo.
echo 📊 Status WhatsApp:
curl -s http://localhost:3000/status
echo.
echo.
pause
goto menu

:monitor
echo.
echo 👀 Surveillance demarree (Ctrl+C pour arreter)
node test-whatsapp.js --monitor
pause
goto menu

:test
echo.
echo 🧪 Test d'envoi de message...
node test-whatsapp.js --test
echo.
pause
goto menu

:logs
echo.
echo 📋 Pour voir les logs en direct:
echo   - Ouvrez un nouveau terminal
echo   - Executez: npm start
echo   - Ou surveillez les logs du processus en cours
echo.
pause
goto menu

:end
echo 👋 Au revoir!
pause