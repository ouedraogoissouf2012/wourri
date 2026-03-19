"""
WOURI — Préparation du dataset Dioula/Bambara pour le fine-tuning MMS

Convertit les données locales en format HuggingFace Dataset prêt pour l'entraînement.

Sources exploitées :
  1. bayelemabaga/  — 42k paires texte bambara-français alignées (RobotsMali)
  2. jeli_asr_bam.txt — 67k phrases bambara orales (jeli-asr, RobotsMali)
  3. corpus_ivr.json — 144 réponses bambara agricoles validées (base Wourri)

Sortie :
  data/dioula_dataset/
    train/   metadata.jsonl  +  audio/  (si audio disponible)
    test/    metadata.jsonl  +  audio/

IMPORTANT : Ce script ne génère PAS d'audio synthétique — il prépare uniquement
les transcriptions textuelles pour le fine-tuning sur données texte-seul (LM) ou
pour être combinées avec des enregistrements terrain réels.

Usage :
    python finetune/prepare_dioula_dataset.py
    python finetune/prepare_dioula_dataset.py --max-samples 5000 --output data/dioula_dataset
"""
import argparse
import json
import random
import re
import unicodedata
from pathlib import Path

# ---------------------------------------------------------------------------
# Chemins
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
API_DIR = REPO_ROOT / "wouri-api"

BAYELEMABAGA_DIR = API_DIR / "data" / "validation_sources" / "bayelemabaga"
JELI_ASR_FILE = API_DIR / "data" / "validation_sources" / "jeli_asr_bam.txt"
CORPUS_IVR_FILE = API_DIR / "dictionnaires" / "corpus_ivr.json"
FINDORA_FILE = API_DIR / "data" / "hf_datasets" / "findora_fr_dioula.json"
CV_DYU_DIR = REPO_ROOT / "cv-corpus-24.0-2025-12-05-dyu" / "cv-corpus-24.0-2025-12-05" / "dyu"
TTS_AUDIO_DIR = API_DIR / "data" / "tts_test_axe1"

DEFAULT_OUTPUT = REPO_ROOT / "data" / "dioula_dataset"

# ---------------------------------------------------------------------------
# Caractères bambara valides à conserver
# ---------------------------------------------------------------------------
BAMBARA_VALID = set(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "àáâäèéêëìíîïòóôöùúûü"
    "ɛɔŋɲɛ̀ɛ́ɔ̀ɔ́ɲɛɔŋ"
    "ƐƆŊƝ"
    " '-"
)


def normalize_bambara(text: str) -> str:
    """
    Normalise un texte bambara pour l'ASR :
    - Minuscules
    - Conserve les caractères spéciaux (ɛ, ɔ, ŋ, ɲ) et tons (à, á...)
    - Supprime la ponctuation non significative
    - Réduit les espaces multiples
    """
    text = text.strip().lower()

    # Supprimer ponctuation terminale et guillemets
    text = re.sub(r'["""«»\(\)\[\]\{\}!?.,;:…]', ' ', text)

    # Conserver les apostrophes dans les contractions bambara (ex: n'a)
    # mais supprimer les guillemets
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def is_valid_bambara(text: str, min_words: int = 2, max_words: int = 40) -> bool:
    """Vérifie qu'une phrase bambara est utilisable pour l'ASR."""
    if not text:
        return False
    words = text.split()
    if not (min_words <= len(words) <= max_words):
        return False
    # Doit contenir au moins un caractère bambara spécifique ou être du texte latin normal
    # (le dioula utilise l'alphabet latin + ɛ, ɔ, ŋ, ɲ)
    bambara_special = set("ɛɔŋɲɛɔŋɲÉÔŊ")
    has_special = any(c in bambara_special for c in text)
    has_latin = any(c.isalpha() for c in text)
    return has_latin or has_special


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_bayelemabaga(max_samples: int = None) -> list[dict]:
    """
    Charge les paires bambara/français depuis le corpus bayelemabaga.
    Format du fichier aligned.tsv : bambara<TAB>français
    """
    records = []
    tsv_file = BAYELEMABAGA_DIR / "aligned.tsv"

    if not tsv_file.exists():
        # Fallback : fichier bambara.clean.txt seul
        clean_file = BAYELEMABAGA_DIR / "bambara.clean.txt"
        if not clean_file.exists():
            print(f"[Bayelemabaga] Fichier non trouvé: {tsv_file}")
            return []

        print(f"[Bayelemabaga] Chargement depuis {clean_file.name}...")
        with open(clean_file, encoding="utf-8") as f:
            for line in f:
                text = normalize_bambara(line.strip())
                if is_valid_bambara(text):
                    records.append({
                        "bambara": text,
                        "french": None,
                        "source": "bayelemabaga"
                    })
                if max_samples and len(records) >= max_samples:
                    break
    else:
        print(f"[Bayelemabaga] Chargement depuis {tsv_file.name}...")
        with open(tsv_file, encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 1:
                    bam = normalize_bambara(parts[0])
                    fr = parts[1].strip() if len(parts) >= 2 else None
                    if is_valid_bambara(bam):
                        records.append({
                            "bambara": bam,
                            "french": fr,
                            "source": "bayelemabaga"
                        })
                if max_samples and len(records) >= max_samples:
                    break

    print(f"[Bayelemabaga] {len(records)} phrases chargées")
    return records


def load_jeli_asr(max_samples: int = None) -> list[dict]:
    """
    Charge les phrases bambara depuis jeli_asr_bam.txt.
    Format : une phrase par ligne (pas de traduction).
    """
    if not JELI_ASR_FILE.exists():
        print(f"[Jeli-ASR] Fichier non trouvé: {JELI_ASR_FILE}")
        return []

    records = []
    print(f"[Jeli-ASR] Chargement depuis {JELI_ASR_FILE.name}...")
    with open(JELI_ASR_FILE, encoding="utf-8") as f:
        for line in f:
            text = normalize_bambara(line.strip())
            if is_valid_bambara(text):
                records.append({
                    "bambara": text,
                    "french": None,
                    "source": "jeli_asr"
                })
            if max_samples and len(records) >= max_samples:
                break

    print(f"[Jeli-ASR] {len(records)} phrases chargées")
    return records


def load_corpus_ivr() -> list[dict]:
    """
    Charge les réponses bambara agricoles depuis corpus_ivr.json.
    Ces phrases sont de haute qualité (validées humainement).
    """
    if not CORPUS_IVR_FILE.exists():
        print(f"[IVR] Fichier non trouvé: {CORPUS_IVR_FILE}")
        return []

    records = []
    with open(CORPUS_IVR_FILE, encoding="utf-8") as f:
        data = json.load(f)

    for entry in data.get("entries", []):
        bam = normalize_bambara(entry.get("reponse_bambara", ""))
        fr = entry.get("reponse_fr", None)
        if is_valid_bambara(bam, min_words=3):
            records.append({
                "bambara": bam,
                "french": fr,
                "source": "corpus_ivr",
                "intent": entry.get("intent", ""),
                "score_validation": entry.get("score_validation", 0.7)
            })

    print(f"[IVR] {len(records)} phrases validées chargées")
    return records


def load_findora(max_samples: int = None) -> list[dict]:
    """
    Charge les phrases dioula CI depuis Findora/hf_fr_dioula_full.
    Format : [{"fr": "...", "dyu": "..."}, ...]
    Texte seul — pas d'audio.
    """
    if not FINDORA_FILE.exists():
        print(f"[Findora] Fichier non trouvé: {FINDORA_FILE}")
        return []

    records = []
    print(f"[Findora] Chargement depuis {FINDORA_FILE.name}...")
    with open(FINDORA_FILE, encoding="utf-8") as f:
        data = json.load(f)

    for item in data:
        dyu = normalize_bambara(item.get("dioula") or item.get("dyu", ""))
        fr = item.get("fr", None)
        if is_valid_bambara(dyu):
            records.append({"bambara": dyu, "french": fr, "source": "findora_dioula"})
        if max_samples and len(records) >= max_samples:
            break

    print(f"[Findora] {len(records)} phrases chargées")
    return records


def load_common_voice_dyu(with_audio: bool = True) -> list[dict]:
    """
    Charge les clips Common Voice dyu validés.
    validated.tsv : client_id | path | sentence_id | sentence | ...
    Retourne les paires (audio_path, sentence) si with_audio=True,
    ou texte seul sinon.
    """
    validated_tsv = CV_DYU_DIR / "validated.tsv"
    clips_dir = CV_DYU_DIR / "clips"

    if not validated_tsv.exists():
        print(f"[CV-dyu] Fichier non trouvé: {validated_tsv}")
        return []

    records = []
    print(f"[CV-dyu] Chargement depuis {validated_tsv.name}...")
    with open(validated_tsv, encoding="utf-8") as f:
        lines = f.readlines()

    header = lines[0].strip().split("\t")
    path_idx = header.index("path")
    sentence_idx = header.index("sentence")

    for line in lines[1:]:
        parts = line.strip().split("\t")
        if len(parts) <= max(path_idx, sentence_idx):
            continue
        mp3_name = parts[path_idx]
        text = normalize_bambara(parts[sentence_idx])
        if not is_valid_bambara(text):
            continue

        audio_path = str(clips_dir / mp3_name) if with_audio else None
        if with_audio and audio_path and not Path(audio_path).exists():
            continue

        records.append({
            "bambara": text,
            "french": None,
            "source": "common_voice_dyu_v24",
            "audio_path": audio_path,
        })

    print(f"[CV-dyu] {len(records)} clips validés chargés")
    return records


def load_tts_ivr_audio() -> list[dict]:
    """
    Charge les WAVs TTS générés depuis corpus IVR (AXE-1).
    Ces fichiers contiennent la synthèse des phrases bambara validées.
    Audio de haute qualité (MMS TTS dyu, 16kHz).
    """
    if not TTS_AUDIO_DIR.exists():
        print(f"[TTS-IVR] Répertoire non trouvé: {TTS_AUDIO_DIR}")
        return []

    rapport_file = TTS_AUDIO_DIR / "rapport_axe1.json"
    if not rapport_file.exists():
        print(f"[TTS-IVR] Rapport non trouvé: {rapport_file}")
        return []

    with open(rapport_file, encoding="utf-8") as f:
        rapport = json.load(f)

    records = []
    for item in rapport.get("resultats", []):
        if item.get("status") != "OK":
            continue
        wav_path = item.get("fichier_wav", "")
        text = normalize_bambara(item.get("phrase_bambara", ""))
        if not wav_path or not Path(wav_path).exists():
            continue
        if not is_valid_bambara(text, min_words=3):
            continue
        records.append({
            "bambara": text,
            "french": item.get("phrase_fr", None),
            "source": "tts_ivr_axe1",
            "audio_path": wav_path,
        })

    print(f"[TTS-IVR] {len(records)} WAVs TTS chargés")
    return records


# ---------------------------------------------------------------------------
# Construction du dataset final
# ---------------------------------------------------------------------------

def build_dataset(
    max_samples: int = None,
    test_ratio: float = 0.1,
    seed: int = 42,
    with_audio: bool = False,
) -> tuple[list[dict], list[dict]]:
    """
    Construit et mélange le dataset complet.
    Retourne (train_records, test_records).

    Si with_audio=True : inclut les paires audio+texte (CV dyu + TTS IVR).
    Les enregistrements audio sont prioritaires dans le split test.
    """
    random.seed(seed)

    # --- Sources texte seul ---
    baye_records = load_bayelemabaga(max_samples=max_samples)
    jeli_records = load_jeli_asr(max_samples=max_samples)
    ivr_records = load_corpus_ivr()
    findora_records = load_findora(max_samples=max_samples)

    # --- Sources audio+texte ---
    cv_records = load_common_voice_dyu(with_audio=with_audio) if with_audio else []
    tts_records = load_tts_ivr_audio() if with_audio else []

    # Corpus IVR dupliqué ×5 (haute qualité agricole validée humainement)
    all_records = (
        baye_records
        + jeli_records
        + findora_records
        + (ivr_records * 5)
        + cv_records
        + tts_records
    )

    # Dédupliquer (sur le texte bambara normalisé)
    seen = set()
    unique_records = []
    for r in all_records:
        key = r["bambara"]
        if key not in seen:
            seen.add(key)
            unique_records.append(r)

    print(f"\n[Dataset] Total unique: {len(unique_records)} phrases")

    # Mélanger
    random.shuffle(unique_records)

    # Appliquer la limite globale
    if max_samples and len(unique_records) > max_samples:
        unique_records = unique_records[:max_samples]
        print(f"[Dataset] Limité à {max_samples} échantillons")

    # Split train/test
    split_idx = max(1, int(len(unique_records) * (1 - test_ratio)))
    train_records = unique_records[:split_idx]
    test_records = unique_records[split_idx:]

    print(f"[Dataset] Train: {len(train_records)} | Test: {len(test_records)}")
    return train_records, test_records


# ---------------------------------------------------------------------------
# Sauvegarde
# ---------------------------------------------------------------------------

def save_split(records: list[dict], output_dir: Path, split: str):
    """Sauvegarde un split en format HuggingFace (metadata.jsonl)."""
    split_dir = output_dir / split
    split_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = split_dir / "metadata.jsonl"
    n_audio = 0
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for i, record in enumerate(records):
            audio_path = record.get("audio_path")
            row = {
                "id": f"{split}_{i:06d}",
                "sentence": record["bambara"],
                "text": record["bambara"],
                "french": record.get("french"),
                "source": record.get("source", "unknown"),
                "audio_path": audio_path,  # None si texte seul
            }
            if "intent" in record:
                row["intent"] = record["intent"]
            if audio_path:
                n_audio += 1
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"[Save] {split}: {len(records)} lignes ({n_audio} avec audio) -> {jsonl_path}")


def save_hf_script(output_dir: Path):
    """Génère un script de chargement HuggingFace Dataset."""
    script = '''"""
Chargement du dataset Dioula/Bambara pour le fine-tuning MMS.

Usage:
    from datasets import load_dataset
    dataset = load_dataset("json",
        data_files={"train": "train/metadata.jsonl", "test": "test/metadata.jsonl"},
        split="train"
    )
"""
from datasets import load_dataset

def load_dioula_dataset(dataset_path: str = "."):
    return load_dataset("json", data_files={
        "train": f"{dataset_path}/train/metadata.jsonl",
        "test":  f"{dataset_path}/test/metadata.jsonl",
    })
'''
    (output_dir / "load_dataset.py").write_text(script, encoding="utf-8")


def print_stats(train: list, test: list):
    """Affiche des statistiques sur le dataset."""
    all_records = train + test
    sources = {}
    total_words = 0

    for r in all_records:
        src = r.get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1
        total_words += len(r["bambara"].split())

    print("\n" + "=" * 50)
    print("STATISTIQUES DU DATASET")
    print("=" * 50)
    print(f"  Total      : {len(all_records)} phrases")
    print(f"  Train      : {len(train)} phrases")
    print(f"  Test       : {len(test)} phrases")
    print(f"  Mots/phrase: {total_words // max(1, len(all_records)):.1f} en moyenne")
    print(f"\n  Par source :")
    for src, count in sorted(sources.items(), key=lambda x: -x[1]):
        pct = 100 * count / max(1, len(all_records))
        print(f"    {src:<20} {count:>6} ({pct:.1f}%)")
    print("=" * 50)


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Prépare le dataset Dioula/Bambara pour le fine-tuning MMS"
    )
    parser.add_argument(
        "--max-samples", type=int, default=None,
        help="Nombre max de phrases (défaut: toutes)"
    )
    parser.add_argument(
        "--output", type=str, default=str(DEFAULT_OUTPUT),
        help=f"Répertoire de sortie (défaut: {DEFAULT_OUTPUT})"
    )
    parser.add_argument(
        "--test-ratio", type=float, default=0.1,
        help="Ratio du split test (défaut: 0.1)"
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Graine aléatoire (défaut: 42)"
    )
    parser.add_argument(
        "--with-audio", action="store_true",
        help="Inclure les paires audio+texte (Common Voice dyu + TTS IVR)"
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nPréparation du dataset Dioula/Bambara")
    print(f"  Sortie: {output_dir}")
    print(f"  Test ratio: {args.test_ratio}")
    print(f"  Audio: {'Oui (CV dyu + TTS IVR)' if args.with_audio else 'Non (texte seul)'}")
    if args.max_samples:
        print(f"  Max samples: {args.max_samples}")
    print()

    train, test = build_dataset(
        max_samples=args.max_samples,
        test_ratio=args.test_ratio,
        seed=args.seed,
        with_audio=args.with_audio,
    )

    save_split(train, output_dir, "train")
    save_split(test, output_dir, "test")
    save_hf_script(output_dir)
    print_stats(train, test)

    print(f"\nDataset prêt dans : {output_dir}")
    print("Prochaine étape   : python finetune/finetune_mms_dioula.py")


if __name__ == "__main__":
    main()
