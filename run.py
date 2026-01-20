"""
WOURI - Script de démarrage
"""
import uvicorn
import os

if __name__ == "__main__":
    # S'assurer que le dossier static/audio existe
    os.makedirs("static/audio", exist_ok=True)

    print("=" * 50)
    print("WOURI - Démarrage du serveur")
    print("=" * 50)
    print("Interface web: http://localhost:8000")
    print("Documentation: http://localhost:8000/docs")
    print("=" * 50)

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
