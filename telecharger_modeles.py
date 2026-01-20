"""
Script de telechargement des modeles ML pour WOURI
Execute: python telecharger_modeles.py
"""

import os

def main():
    print("=" * 50)
    print("WOURI - Telechargement des Modeles ML")
    print("=" * 50)

    # Creer le dossier
    os.makedirs('modeles_manuels', exist_ok=True)

    # 1. Modele TTS Bambara
    print("\n[1/2] Telechargement du modele TTS Bambara (facebook/mms-tts-bam)...")
    print("      Taille: ~139 MB")

    try:
        from huggingface_hub import snapshot_download
        snapshot_download(
            repo_id='facebook/mms-tts-bam',
            local_dir='./modeles_manuels',
            local_dir_use_symlinks=False
        )
        print("      [OK] TTS Bambara telecharge!")
    except Exception as e:
        print(f"      [ERREUR] {e}")
        print("      Installez: pip install huggingface_hub")

    # 2. Modele Sentence Transformer pour RAG
    print("\n[2/2] Telechargement du modele Sentence Transformer...")
    print("      Taille: ~470 MB")

    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
        model.save('./modeles_manuels/paraphrase-multilingual-MiniLM-L12-v2')
        print("      [OK] Sentence Transformer telecharge!")
    except Exception as e:
        print(f"      [ERREUR] {e}")
        print("      Installez: pip install sentence-transformers")

    print("\n" + "=" * 50)
    print("Telechargement termine!")
    print("=" * 50)

if __name__ == "__main__":
    main()
