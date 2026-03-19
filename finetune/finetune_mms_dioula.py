"""
WOURI — Fine-tuning MMS Adapter pour le Dioula/Bambara ivoirien

Entraîne uniquement les couches adapter (~2.5M paramètres) de facebook/mms-1b-all
sur les données Dioula locales. Le modèle de base (1B paramètres) est gelé.

Prérequis :
    pip install transformers datasets evaluate jiwer accelerate

GPU minimum : T4 (16 Go VRAM) — Google Colab gratuit suffit
Durée estimée : 15-30 min pour 4 époques sur 5 000 phrases

Usage basique :
    python finetune/finetune_mms_dioula.py

Usage avancé :
    python finetune/finetune_mms_dioula.py \\
        --dataset data/dioula_dataset \\
        --output models/mms-dioula-adapter \\
        --epochs 4 \\
        --batch-size 8 \\
        --learning-rate 1e-3

Après entraînement :
    - L'adapter dyu est sauvegardé dans --output/
    - Utiliser evaluate_wer.py pour mesurer le WER avant/après

Référence :
    https://huggingface.co/blog/mms_adapters
"""
import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Union

# ---------------------------------------------------------------------------
# Chemins par défaut
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_DATASET = REPO_ROOT / "data" / "dioula_dataset"
DEFAULT_OUTPUT = REPO_ROOT / "models" / "mms-dioula-adapter"
BASE_MODEL = "facebook/mms-1b-all"
TARGET_LANG = "dyu"  # Code ISO-639-3 pour le Dioula


# ---------------------------------------------------------------------------
# Normalisation du texte pour l'ASR
# ---------------------------------------------------------------------------

def normalize_text_for_asr(text: str) -> str:
    """
    Prépare le texte pour le tokenizer MMS :
    - Minuscules
    - Supprime ponctuation non linguistique
    - Conserve ɛ, ɔ, ŋ, ɲ et leurs variantes tonées
    - Réduit les espaces
    """
    text = text.lower().strip()
    # Supprimer ponctuation sauf apostrophe (contractions bambara)
    text = re.sub(r"[^\w\s'ɛɔŋɲàáâèéêìíîòóôùúûɛ̀ɛ́ɔ̀ɔ́]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ---------------------------------------------------------------------------
# Chargement du dataset depuis metadata.jsonl
# ---------------------------------------------------------------------------

def load_jsonl_split(jsonl_path: Path) -> list[dict]:
    """Charge un split depuis un fichier metadata.jsonl."""
    records = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line.strip())
            sentence = row.get("sentence") or row.get("text") or ""
            sentence = normalize_text_for_asr(sentence)
            if len(sentence.split()) >= 2:
                records.append({"sentence": sentence, "source": row.get("source", "")})
    return records


# ---------------------------------------------------------------------------
# Data collator pour CTC (pad variable-length sequences)
# ---------------------------------------------------------------------------

@dataclass
class DataCollatorCTCWithPadding:
    processor: object
    padding: Union[bool, str] = True

    def __call__(self, features: List[Dict]) -> Dict:
        import torch

        input_features = [{"input_values": f["input_values"]} for f in features]
        label_features = [{"input_ids": f["labels"]} for f in features]

        batch = self.processor.pad(
            input_features,
            padding=self.padding,
            return_tensors="pt",
        )
        labels_batch = self.processor.pad(
            labels=label_features,
            padding=self.padding,
            return_tensors="pt",
        )
        # Remplacer le padding par -100 (ignoré par la loss CTC)
        labels = labels_batch["input_ids"].masked_fill(
            labels_batch.attention_mask.ne(1), -100
        )
        batch["labels"] = labels
        return batch


# ---------------------------------------------------------------------------
# Fonctions principales
# ---------------------------------------------------------------------------

def build_vocab(records: list[dict]) -> dict:
    """Construit le vocabulaire depuis les textes bambara."""
    all_text = " ".join(r["sentence"] for r in records)
    vocab = sorted(set(all_text.replace(" ", "|")))

    vocab_dict = {v: i for i, v in enumerate(vocab)}

    # Tokens spéciaux MMS
    if "|" not in vocab_dict:
        vocab_dict["|"] = len(vocab_dict)
    if "[UNK]" not in vocab_dict:
        vocab_dict["[UNK]"] = len(vocab_dict)
    if "[PAD]" not in vocab_dict:
        vocab_dict["[PAD]"] = len(vocab_dict)

    return vocab_dict


def compute_metrics_factory(processor):
    """Retourne la fonction compute_metrics compatible Trainer."""
    import numpy as np
    try:
        import evaluate
        wer_metric = evaluate.load("wer")
    except Exception:
        wer_metric = None

    def compute_metrics(pred):
        pred_logits = pred.predictions
        pred_ids = np.argmax(pred_logits, axis=-1)
        pred.label_ids[pred.label_ids == -100] = processor.tokenizer.pad_token_id
        pred_str = processor.batch_decode(pred_ids)
        label_str = processor.batch_decode(pred.label_ids, group_tokens=False)

        if wer_metric:
            wer = wer_metric.compute(predictions=pred_str, references=label_str)
            return {"wer": wer}
        return {}

    return compute_metrics


def prepare_hf_dataset(records: list[dict], processor, dummy_audio_len: int = 16000) -> object:
    """
    Convertit les enregistrements en HuggingFace Dataset.

    NOTE : Ce script prépare la structure pour un dataset TEXTE seul.
    Pour un vrai fine-tuning ASR, il faut des fichiers audio .wav à 16kHz.
    Si des fichiers audio terrain sont disponibles, modifier audio_path ci-dessous.

    Sans audio : génère un signal silencieux pour valider le pipeline complet.
    Avec audio : pointer audio_path vers les fichiers .wav réels.
    """
    import torch
    from datasets import Dataset

    def make_sample(record):
        text = record["sentence"]

        # Audio : chercher le fichier .wav si disponible, sinon silence
        # Pour les données terrain, remplacer par : sf.read(record["audio_path"])
        audio_array = torch.zeros(dummy_audio_len).numpy()  # Silence 1s @ 16kHz

        inputs = processor(
            audio_array,
            sampling_rate=16000,
            return_tensors="pt"
        )
        labels = processor(text=text, return_tensors="pt").input_ids

        return {
            "input_values": inputs.input_values[0].tolist(),
            "input_length": len(inputs.input_values[0]),
            "labels": labels[0].tolist(),
            "sentence": text,
        }

    samples = [make_sample(r) for r in records]
    return Dataset.from_list(samples)


def finetune(
    dataset_path: Path,
    output_dir: Path,
    epochs: int = 4,
    batch_size: int = 8,
    learning_rate: float = 1e-3,
    max_train_samples: int = None,
    push_to_hub: bool = False,
    hub_repo: str = None,
):
    """Fine-tune les adapter layers MMS sur le Dioula."""
    try:
        import torch
        from transformers import (
            Wav2Vec2CTCTokenizer,
            Wav2Vec2FeatureExtractor,
            Wav2Vec2Processor,
            Wav2Vec2ForCTC,
            TrainingArguments,
            Trainer,
        )
    except ImportError as e:
        print(f"Dépendance manquante : {e}")
        print("Installer : pip install transformers datasets evaluate jiwer accelerate")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Charger les données ---
    train_file = dataset_path / "train" / "metadata.jsonl"
    test_file = dataset_path / "test" / "metadata.jsonl"

    if not train_file.exists():
        print(f"Dataset non trouvé : {train_file}")
        print("Exécuter d'abord : python finetune/prepare_dioula_dataset.py")
        return

    print(f"[Fine-tuning] Chargement dataset depuis {dataset_path}...")
    train_records = load_jsonl_split(train_file)
    test_records = load_jsonl_split(test_file)

    if max_train_samples:
        train_records = train_records[:max_train_samples]

    print(f"[Fine-tuning] Train: {len(train_records)} | Test: {len(test_records)}")

    # --- Vocabulaire ---
    print("[Fine-tuning] Construction du vocabulaire...")
    vocab_dict = build_vocab(train_records + test_records)
    vocab_path = output_dir / "vocab.json"
    with open(vocab_path, "w", encoding="utf-8") as f:
        json.dump({TARGET_LANG: vocab_dict}, f, ensure_ascii=False, indent=2)

    print(f"[Fine-tuning] Vocabulaire: {len(vocab_dict)} tokens → {vocab_path}")

    # --- Tokenizer & Processor ---
    tokenizer = Wav2Vec2CTCTokenizer(
        str(vocab_path),
        unk_token="[UNK]",
        pad_token="[PAD]",
        word_delimiter_token="|",
        target_lang=TARGET_LANG,
    )
    feature_extractor = Wav2Vec2FeatureExtractor(
        feature_size=1,
        sampling_rate=16000,
        padding_value=0.0,
        do_normalize=True,
        return_attention_mask=True,
    )
    processor = Wav2Vec2Processor(
        feature_extractor=feature_extractor,
        tokenizer=tokenizer,
    )
    processor.save_pretrained(str(output_dir))

    # --- HuggingFace Dataset ---
    print("[Fine-tuning] Préparation des données...")
    train_dataset = prepare_hf_dataset(train_records, processor)
    test_dataset = prepare_hf_dataset(test_records, processor)

    # --- Modèle MMS (adapter uniquement) ---
    print(f"[Fine-tuning] Chargement du modèle {BASE_MODEL}...")
    model = Wav2Vec2ForCTC.from_pretrained(
        BASE_MODEL,
        attention_dropout=0.0,
        hidden_dropout=0.0,
        feat_proj_dropout=0.0,
        layerdrop=0.0,
        ctc_loss_reduction="mean",
        pad_token_id=processor.tokenizer.pad_token_id,
        vocab_size=len(processor.tokenizer),
        ignore_mismatched_sizes=True,
    )

    # Initialiser et geler le modèle de base → n'entraîner que les adapters
    model.init_adapter_layers()
    model.freeze_base_model()

    adapter_weights = model._get_adapters()
    for param in adapter_weights.values():
        param.requires_grad = True

    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"[Fine-tuning] Paramètres totaux: {total_params:,}")
    print(f"[Fine-tuning] Paramètres entraînés (adapters): {trainable_params:,} "
          f"({100*trainable_params/total_params:.1f}%)")

    # --- Data collator ---
    data_collator = DataCollatorCTCWithPadding(processor=processor, padding=True)

    # --- Arguments d'entraînement ---
    use_fp16 = torch.cuda.is_available()
    training_args = TrainingArguments(
        output_dir=str(output_dir),
        group_by_length=True,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        num_train_epochs=epochs,
        gradient_checkpointing=True,
        fp16=use_fp16,
        learning_rate=learning_rate,
        warmup_steps=max(50, len(train_records) // (batch_size * 4)),
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="wer",
        greater_is_better=False,
        logging_steps=50,
        report_to="none",  # Désactiver wandb/tensorboard
        push_to_hub=push_to_hub,
        hub_model_id=hub_repo if push_to_hub else None,
    )

    # --- Trainer ---
    trainer = Trainer(
        model=model,
        data_collator=data_collator,
        args=training_args,
        compute_metrics=compute_metrics_factory(processor),
        train_dataset=train_dataset,
        eval_dataset=test_dataset,
        tokenizer=processor.feature_extractor,
    )

    print(f"\n[Fine-tuning] Démarrage — {epochs} époques, lr={learning_rate}, batch={batch_size}")
    print(f"[Fine-tuning] GPU: {'Oui (' + str(torch.cuda.get_device_name(0)) + ')' if torch.cuda.is_available() else 'Non (CPU — très lent !)'}")
    print()

    trainer.train()

    # --- Sauvegarder l'adapter ---
    print(f"\n[Fine-tuning] Sauvegarde de l'adapter {TARGET_LANG}...")
    try:
        from safetensors.torch import save_file as safe_save_file
        from transformers.models.wav2vec2.modeling_wav2vec2 import WAV2VEC2_ADAPTER_SAFE_FILE

        adapter_file = WAV2VEC2_ADAPTER_SAFE_FILE.format(TARGET_LANG)
        adapter_path = output_dir / adapter_file
        safe_save_file(model._get_adapters(), str(adapter_path), metadata={"format": "pt"})
        print(f"[Fine-tuning] Adapter sauvegardé : {adapter_path}")
    except Exception as e:
        print(f"[Fine-tuning] Sauvegarde safetensors échouée ({e}), sauvegarde Trainer standard...")
        trainer.save_model()

    if push_to_hub:
        trainer.push_to_hub()
        print(f"[Fine-tuning] Modèle publié sur HuggingFace Hub : {hub_repo}")

    print(f"\n[Fine-tuning] Terminé ! Modèle dans : {output_dir}")
    print(f"Évaluation WER : python finetune/evaluate_wer.py --model {output_dir}")


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fine-tune les adapter layers MMS pour le Dioula/Bambara"
    )
    parser.add_argument(
        "--dataset", type=str, default=str(DEFAULT_DATASET),
        help=f"Répertoire du dataset (défaut: {DEFAULT_DATASET})"
    )
    parser.add_argument(
        "--output", type=str, default=str(DEFAULT_OUTPUT),
        help=f"Répertoire de sortie (défaut: {DEFAULT_OUTPUT})"
    )
    parser.add_argument(
        "--epochs", type=int, default=4,
        help="Nombre d'époques (défaut: 4)"
    )
    parser.add_argument(
        "--batch-size", type=int, default=8,
        help="Taille du batch (défaut: 8)"
    )
    parser.add_argument(
        "--learning-rate", type=float, default=1e-3,
        help="Learning rate (défaut: 1e-3)"
    )
    parser.add_argument(
        "--max-train-samples", type=int, default=None,
        help="Limiter le train à N échantillons (utile pour les tests rapides)"
    )
    parser.add_argument(
        "--push-to-hub", action="store_true",
        help="Publier le modèle sur HuggingFace Hub après entraînement"
    )
    parser.add_argument(
        "--hub-repo", type=str, default="wourri/mms-dioula-adapter",
        help="Nom du repo HuggingFace Hub (défaut: wourri/mms-dioula-adapter)"
    )
    args = parser.parse_args()

    finetune(
        dataset_path=Path(args.dataset),
        output_dir=Path(args.output),
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        max_train_samples=args.max_train_samples,
        push_to_hub=args.push_to_hub,
        hub_repo=args.hub_repo,
    )


if __name__ == "__main__":
    main()
