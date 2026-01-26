"""
Script de telechargement des modeles ML pour WOURI
Execute: python telecharger_modeles.py

Modeles disponibles:
- TTS Bambara/Dioula (bam) - par defaut
- TTS Attie (ati)
- TTS Senoufo Djimini (dyi)
- TTS Senoufo Mamara (myk)
- TTS Dida Yocoboue (gud)
- TTS Adioukrou (adj)
- TTS Dan/Yacouba (dnj)
- TTS Wobe (wob)
- Sentence Transformer (RAG)
- NLLB-200 (Traduction FR->Bambara)
"""

import os
import sys

# Langues ivoiriennes TTS disponibles
IVORIAN_TTS_MODELS = {
    "bam": ("Bambara/Dioula", "facebook/mms-tts-bam", 139),
    "ati": ("Attié", "facebook/mms-tts-ati", 139),
    "dyi": ("Sénoufo Djimini", "facebook/mms-tts-dyi", 139),
    "myk": ("Sénoufo Mamara", "facebook/mms-tts-myk", 139),
    "gud": ("Dida Yocoboué", "facebook/mms-tts-gud", 139),
    "adj": ("Adioukrou", "facebook/mms-tts-adj", 139),
    "dnj": ("Dan/Yacouba", "facebook/mms-tts-dnj", 139),
    "wob": ("Wobé", "facebook/mms-tts-wob", 139),
}


def download_tts_model(code: str, name: str, model_id: str, size_mb: int, output_dir: str) -> bool:
    """Telecharge un modele TTS depuis Hugging Face"""
    print(f"\n    Telechargement {name} ({model_id})...")
    print(f"    Taille estimee: ~{size_mb} MB")

    model_dir = os.path.join(output_dir, f"mms-tts-{code}")

    try:
        from huggingface_hub import snapshot_download
        snapshot_download(
            repo_id=model_id,
            local_dir=model_dir,
            local_dir_use_symlinks=False
        )
        print(f"    [OK] {name} telecharge dans {model_dir}")
        return True
    except Exception as e:
        print(f"    [ERREUR] {e}")
        return False


def download_sentence_transformer(output_dir: str) -> bool:
    """Telecharge le modele Sentence Transformer pour RAG"""
    print("\n    Telechargement Sentence Transformer...")
    print("    Taille estimee: ~470 MB")

    model_dir = os.path.join(output_dir, "paraphrase-multilingual-MiniLM-L12-v2")

    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
        model.save(model_dir)
        print(f"    [OK] Sentence Transformer telecharge dans {model_dir}")
        return True
    except Exception as e:
        print(f"    [ERREUR] {e}")
        print("    Installez: pip install sentence-transformers")
        return False


def download_nllb_translator() -> bool:
    """Telecharge le modele NLLB pour la traduction FR->Bambara"""
    print("\n    Telechargement NLLB-200 (traduction)...")
    print("    Taille estimee: ~600 MB")
    print("    Note: Ce modele est telecharge automatiquement au premier usage")

    try:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        model_name = "facebook/nllb-200-distilled-600M"
        print(f"    Chargement de {model_name}...")
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        print("    [OK] NLLB-200 telecharge et mis en cache!")
        return True
    except Exception as e:
        print(f"    [ERREUR] {e}")
        return False


def list_available_models():
    """Affiche la liste des modeles disponibles"""
    print("\n" + "=" * 60)
    print("LANGUES IVOIRIENNES TTS DISPONIBLES")
    print("=" * 60)
    print(f"{'Code':<6} {'Langue':<20} {'Modele HuggingFace':<30}")
    print("-" * 60)
    for code, (name, model_id, size) in IVORIAN_TTS_MODELS.items():
        print(f"{code:<6} {name:<20} {model_id:<30}")
    print("=" * 60)


def main():
    print("=" * 60)
    print("WOURI - Telechargement des Modeles ML")
    print("Assistant Agricole pour Agriculteurs Ivoiriens")
    print("=" * 60)

    # Creer le dossier de sortie
    output_dir = './modeles_manuels'
    os.makedirs(output_dir, exist_ok=True)

    # Afficher les options
    print("\nOptions de telechargement:")
    print("  1. Telecharger tous les modeles (recommande)")
    print("  2. Telecharger uniquement Bambara (minimal)")
    print("  3. Choisir les langues a telecharger")
    print("  4. Afficher la liste des langues disponibles")
    print("  5. Quitter")

    choice = input("\nVotre choix [1-5]: ").strip()

    if choice == "5":
        print("Au revoir!")
        return

    if choice == "4":
        list_available_models()
        return

    results = {"success": [], "failed": []}

    if choice == "1":
        # Telecharger tous les modeles
        print("\n[ETAPE 1/3] Telechargement des modeles TTS ivoiriens...")
        for code, (name, model_id, size) in IVORIAN_TTS_MODELS.items():
            if download_tts_model(code, name, model_id, size, output_dir):
                results["success"].append(name)
            else:
                results["failed"].append(name)

        print("\n[ETAPE 2/3] Telechargement du modele RAG...")
        if download_sentence_transformer(output_dir):
            results["success"].append("Sentence Transformer")
        else:
            results["failed"].append("Sentence Transformer")

        print("\n[ETAPE 3/3] Telechargement du modele de traduction...")
        if download_nllb_translator():
            results["success"].append("NLLB-200")
        else:
            results["failed"].append("NLLB-200")

    elif choice == "2":
        # Bambara uniquement
        print("\n[ETAPE 1/3] Telechargement du modele TTS Bambara...")
        code = "bam"
        name, model_id, size = IVORIAN_TTS_MODELS[code]
        if download_tts_model(code, name, model_id, size, output_dir):
            results["success"].append(name)
        else:
            results["failed"].append(name)

        print("\n[ETAPE 2/3] Telechargement du modele RAG...")
        if download_sentence_transformer(output_dir):
            results["success"].append("Sentence Transformer")
        else:
            results["failed"].append("Sentence Transformer")

        print("\n[ETAPE 3/3] Telechargement du modele de traduction...")
        if download_nllb_translator():
            results["success"].append("NLLB-200")
        else:
            results["failed"].append("NLLB-200")

    elif choice == "3":
        # Choisir les langues
        list_available_models()
        print("\nEntrez les codes des langues a telecharger (separes par des virgules)")
        print("Exemple: bam,ati,dyi")
        codes_input = input("Codes: ").strip()

        codes = [c.strip().lower() for c in codes_input.split(",")]

        print("\nTelechargement des modeles TTS selectionnes...")
        for code in codes:
            if code in IVORIAN_TTS_MODELS:
                name, model_id, size = IVORIAN_TTS_MODELS[code]
                if download_tts_model(code, name, model_id, size, output_dir):
                    results["success"].append(name)
                else:
                    results["failed"].append(name)
            else:
                print(f"    [IGNORE] Code '{code}' non reconnu")

        # Toujours telecharger RAG et NLLB
        print("\nTelechargement des modeles complementaires...")
        if download_sentence_transformer(output_dir):
            results["success"].append("Sentence Transformer")
        else:
            results["failed"].append("Sentence Transformer")

        if download_nllb_translator():
            results["success"].append("NLLB-200")
        else:
            results["failed"].append("NLLB-200")

    else:
        print("Choix invalide")
        return

    # Resume
    print("\n" + "=" * 60)
    print("RESUME DU TELECHARGEMENT")
    print("=" * 60)

    if results["success"]:
        print(f"\n[OK] {len(results['success'])} modele(s) telecharge(s):")
        for name in results["success"]:
            print(f"     - {name}")

    if results["failed"]:
        print(f"\n[ECHEC] {len(results['failed'])} modele(s) non telecharge(s):")
        for name in results["failed"]:
            print(f"     - {name}")

    print("\n" + "=" * 60)
    print("Telechargement termine!")
    print(f"Dossier de sortie: {os.path.abspath(output_dir)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
