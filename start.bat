@echo off
echo ==========================================
echo WOURI - Assistant Agricole
echo ==========================================
echo.

REM Verifier si Python est installe
python --version >nul 2>&1
if errorlevel 1 (
    echo ERREUR: Python n'est pas installe!
    echo Telecharger: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Creer l'environnement virtuel si necessaire
if not exist "venv" (
    echo Creation de l'environnement virtuel...
    python -m venv venv
)

REM Activer l'environnement virtuel
call venv\Scripts\activate.bat

REM Installer les dependances
echo Installation des dependances...
pip install -q -r requirements.txt

REM Creer le fichier .env si necessaire
if not exist ".env" (
    echo.
    echo ATTENTION: Fichier .env non trouve!
    echo Copiez .env.example vers .env et ajoutez votre cle DeepSeek
    echo.
    copy .env.example .env
)

REM Creer le dossier audio
if not exist "static\audio" mkdir static\audio

REM Demarrer le serveur
echo.
echo ==========================================
echo Demarrage du serveur...
echo Interface: http://localhost:8000
echo Swagger:   http://localhost:8000/docs
echo ==========================================
echo.

python run.py
