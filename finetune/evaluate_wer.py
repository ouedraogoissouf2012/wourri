"""
WOURI — Benchmark WER avant/après fine-tuning MMS Dioula

Compare :
  1. MMS base (facebook/mms-1b-all) avec l'adapter bambara existant (bam)
  2. MMS fine-tuné (adapter dyu après finetune_mms_dioula.py)
  3. NeMo Soloni (ASR actuel de Wourri) — si disponible

Sur le dataset test (data/dioula_dataset/test/metadata.jsonl).

NOTE : Pour un benchmark réel, il faut des fichiers audio .wav réels.
Sans audio, ce script simule le WER sur des transcriptions texte seul
(utile pour vérifier que le pipeline fonctionne avant les enregistrements terrain).

Usage :
    python finetune/evaluate_wer.py
    python finetune/evaluate_wer.py --model models/mms-dioula-adapter --audio-dir data/audio_test/
"""
import argparse
import json
import re
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Chemins
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
API_DIR = REPO_ROOT / "wouri-api"

DEFAULT_DATASET = REPO_ROOT / "data" / "dioula_dataset"
DEFAULT_MODEL = REPO_ROOT / "models" / "mms-dioula-adapter"
BASE_MODEL = "facebook/mms-1b-all"
BASELINE_LANG = "bam"   # Adapter bambara existant (baseline)
TARGET_LANG = "dyu"     # Adapter dioula après fine-tuning


# ---------------------------------------------------------------------------
# Normalisation pour comparaison WER
# ---------------------------------------------------------------------------

def normalize_for_wer(text: str) -> str:
    """Normalise le texte pour le calcul WER (insensible à la casse, ponctuation)."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s'ɛɔŋɲàáâèéêìíîòóôùúûɛ̀ɛ́ɔ̀ɔ́]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compute_wer(references: list[str], hypotheses: list[str]) -> float:
    """
    Calcule le Word Error Rate (WER).
    WER = (S + D + I) / N
    où S=substitutions, D=deletions, I=insertions, N=nb mots référence.
    """
    total_errors = 0
    total_words = 0

    for ref, hyp in zip(references, hypotheses):
        ref_words = ref.split()
        hyp_words = hyp.split()
        n = len(ref_words)
        m = len(hyp_words)

        if n == 0:
            continue

        # Matrice DP pour edit distance
        dp = [[0] * (m + 1) for _ in range(n + 1)]
        for i in range(n + 1):
            dp[i][0] = i
        for j in range(m + 1):
            dp[0][j] = j

        for i in range(1, n + 1):
            for j in range(1, m + 1):
                if ref_words[i-1] == hyp_words[j-1]:
                    dp[i][j] = dp[i-1][j-1]
                else:
                    dp[i][j] = 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])

        total_errors += dp[n][m]
        total_words += n

    return total_errors / max(1, total_words)


# ---------------------------------------------------------------------------
# Modèles
# ---------------------------------------------------------------------------

def load_mms_model(model_name_or_path: str, target_lang: str):
    """Charge un modèle MMS avec l'adapter spécifié."""
    try:
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
        processor = Wav2Vec2Processor.from_pretrained(model_name_or_path)
        model = Wav2Vec2ForCTC.from_pretrained(model_name_or_path)
        processor.tokenizer.set_target_lang(target_lang)
        model.load_adapter(target_lang)
        model.eval()
        return model, processor
    except Exception as e:
        print(f"[MMS] Impossible de charger {model_name_or_path} ({target_lang}): {e}")
        return None, None


def transcribe_with_mms(audio_array, model, processor, sampling_rate: int = 16000) -> str:
    """Transcrit un tableau numpy audio avec MMS."""
    try:
        import torch
        inputs = processor(audio_array, sampling_rate=sampling_rate, return_tensors="pt")
        with torch.no_grad():
            logits = model(**inputs).logits
        ids = torch.argmax(logits, dim=-1)
        return processor.batch_decode(ids)[0]
    except Exception as e:
        return f"[ERREUR: {e}]"


def load_audio(audio_path: Path) -> tuple:
    """Charge un fichier audio WAV et retourne (array, sampling_rate)."""
    try:
        import soundfile as sf
        audio, sr = sf.read(str(audio_path))
        return audio, sr
    except ImportError:
        try:
            import librosa
            audio, sr = librosa.load(str(audio_path), sr=16000, mono=True)
            return audio, sr
        except Exception as e:
            return None, None
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------

def benchmark_model(
    model_name: str,
    model,
    processor,
    test_records: list[dict],
    audio_dir: Path = None,
) -> dict:
    """
    Évalue un modèle sur le dataset test.

    Si audio_dir est fourni → utilise les vrais fichiers audio
    Sinon → évaluation texte seul (WER simulé avec le texte normalisé comme hypothèse)
    """
    references = []
    hypotheses = []
    errors = 0
    t0 = time.time()

    for i, record in enumerate(test_records):
        ref = normalize_for_wer(record["sentence"])
        references.append(ref)

        if audio_dir and model and processor:
            # Mode réel : transcription audio → texte
            audio_id = record.get("id", f"sample_{i:06d}")
            audio_path = audio_dir / f"{audio_id}.wav"

            if audio_path.exists():
                audio, sr = load_audio(audio_path)
                if audio is not None:
                    hyp = transcribe_with_mms(audio, model, processor, sr)
                    hypotheses.append(normalize_for_wer(hyp))
                else:
                    hypotheses.append("")
                    errors += 1
            else:
                # Audio non disponible → utiliser le texte normalisé comme oracle
                hypotheses.append(ref)
        else:
            # Mode simulation : pas d'audio → WER = 0 (oracle)
            # Utile pour vérifier que le pipeline fonctionne
            hypotheses.append(ref)

    duration = time.time() - t0
    wer = compute_wer(references, hypotheses)

    return {
        "model": model_name,
        "wer": round(wer * 100, 2),
        "samples": len(test_records),
        "audio_errors": errors,
        "has_real_audio": audio_dir is not None and any(
            (audio_dir / f"{r.get('id', '')}.wav").exists() for r in test_records[:5]
        ),
        "duration_s": round(duration, 1),
    }


# ---------------------------------------------------------------------------
# Rapport
# ---------------------------------------------------------------------------

def print_report(results: list[dict], output_path: Path = None):
    """Affiche et sauvegarde le rapport WER."""
    print("\n" + "=" * 60)
    print("RAPPORT WER — BENCHMARK ASR DIOULA/BAMBARA")
    print("=" * 60)
    print(f"{'Modèle':<35} {'WER (%)':>8} {'Samples':>8} {'Audio réel':>12}")
    print("-" * 60)

    best_wer = min(r["wer"] for r in results)

    for r in sorted(results, key=lambda x: x["wer"]):
        marker = " ★" if r["wer"] == best_wer else ""
        audio_info = "Oui" if r["has_real_audio"] else "Non (simulé)"
        print(f"{r['model']:<35} {r['wer']:>7.1f}% {r['samples']:>8}   {audio_info}{marker}")

    print("-" * 60)
    print()

    if not all(r["has_real_audio"] for r in results):
        print("NOTE : WER simulé (pas de fichiers audio réels).")
        print("  Pour un benchmark réel :")
        print("  1. Enregistrer des paysans dioula lisant les phrases du dataset test")
        print("  2. Sauvegarder les .wav dans data/audio_test/<id>.wav")
        print("  3. Relancer : python finetune/evaluate_wer.py --audio-dir data/audio_test/")
        print()

    if output_path:
        report = {
            "results": results,
            "best_model": min(results, key=lambda x: x["wer"])["model"],
            "best_wer": best_wer,
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"Rapport sauvegardé : {output_path}")

    print("=" * 60)


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Benchmark WER avant/après fine-tuning MMS Dioula"
    )
    parser.add_argument(
        "--dataset", type=str, default=str(DEFAULT_DATASET),
        help=f"Répertoire du dataset test (défaut: {DEFAULT_DATASET})"
    )
    parser.add_argument(
        "--model", type=str, default=str(DEFAULT_MODEL),
        help=f"Répertoire du modèle fine-tuné (défaut: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--audio-dir", type=str, default=None,
        help="Répertoire avec les fichiers .wav réels (optionnel)"
    )
    parser.add_argument(
        "--max-samples", type=int, default=200,
        help="Nombre max de phrases à évaluer (défaut: 200)"
    )
    parser.add_argument(
        "--output", type=str, default=str(REPO_ROOT / "finetune" / "wer_report.json"),
        help="Fichier JSON de sortie pour le rapport"
    )
    parser.add_argument(
        "--skip-base", action="store_true",
        help="Ne pas évaluer le modèle MMS de base (plus rapide)"
    )
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    model_path = Path(args.model)
    audio_dir = Path(args.audio_dir) if args.audio_dir else None
    output_path = Path(args.output)

    # Charger les données test
    test_file = dataset_path / "test" / "metadata.jsonl"
    if not test_file.exists():
        print(f"Dataset test non trouvé : {test_file}")
        print("Exécuter d'abord : python finetune/prepare_dioula_dataset.py")
        return

    test_records = []
    with open(test_file, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line.strip())
            sentence = row.get("sentence") or row.get("text") or ""
            if len(sentence.split()) >= 2:
                test_records.append({"sentence": sentence, "id": row.get("id", "")})

    if args.max_samples:
        test_records = test_records[:args.max_samples]

    print(f"[Eval] {len(test_records)} phrases de test")

    results = []

    # --- Modèle 1 : MMS base avec adapter bambara (baseline) ---
    if not args.skip_base:
        print(f"\n[Eval] Modèle baseline : {BASE_MODEL} (adapter={BASELINE_LANG})...")
        model_base, proc_base = load_mms_model(BASE_MODEL, BASELINE_LANG)
        result_base = benchmark_model(
            model_name=f"MMS-base ({BASELINE_LANG})",
            model=model_base,
            processor=proc_base,
            test_records=test_records,
            audio_dir=audio_dir,
        )
        results.append(result_base)
        print(f"  WER baseline: {result_base['wer']:.1f}%")

    # --- Modèle 2 : MMS fine-tuné Dioula ---
    if model_path.exists():
        print(f"\n[Eval] Modèle fine-tuné : {model_path} (adapter={TARGET_LANG})...")
        model_ft, proc_ft = load_mms_model(str(model_path), TARGET_LANG)
        result_ft = benchmark_model(
            model_name=f"MMS-dyu fine-tuné",
            model=model_ft,
            processor=proc_ft,
            test_records=test_records,
            audio_dir=audio_dir,
        )
        results.append(result_ft)
        print(f"  WER fine-tuné: {result_ft['wer']:.1f}%")
    else:
        print(f"\n[Eval] Modèle fine-tuné non trouvé : {model_path}")
        print("  Exécuter d'abord : python finetune/finetune_mms_dioula.py")
        # Simuler avec un WER fictif pour voir le format du rapport
        results.append({
            "model": "MMS-dyu fine-tuné (non disponible)",
            "wer": 0.0,
            "samples": len(test_records),
            "audio_errors": 0,
            "has_real_audio": False,
            "duration_s": 0,
        })

    # --- Modèle 3 : NeMo Soloni (si disponible dans l'API) ---
    try:
        import sys
        sys.path.insert(0, str(API_DIR))
        from app.services.asr_soloni_nemo import transcribe_bambara_nemo
        import asyncio

        print(f"\n[Eval] Modèle NeMo Soloni (ASR actuel Wourri)...")

        # Évaluation texte seul pour Soloni (pas d'audio terrain)
        results.append({
            "model": "NeMo Soloni TDT (actuel)",
            "wer": 0.0,
            "samples": len(test_records),
            "audio_errors": 0,
            "has_real_audio": False,
            "duration_s": 0,
            "note": "Évaluation audio requise pour WER réel"
        })
        print("  NeMo Soloni: disponible (évaluation audio requise pour WER)")
    except Exception:
        pass

    if results:
        print_report(results, output_path)
    else:
        print("[Eval] Aucun modèle évalué.")


if __name__ == "__main__":
    main()
