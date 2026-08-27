# Étude de faisabilité #0004 — Fine-tune d'Omnilingual ASR (dé-risquage maillon ③)

**Statut** : ✅ **recherche faite 2026-08-27** (avant de collecter la totalité des données esse)
**Décision qu'elle informe** : maillon ③ (#474, fine-tune) — affine [ADR-0036](../adr/0036-choix-modele-asr-baoule.md)
**But** : savoir **AVANT** qu'esse finisse la collecte si fine-tuner Omnilingual 1B est faisable sur notre matériel (GPU gratuit), et sinon quel plan B — pour ne pas découvrir un mur après coup.

---

## 1. Ce qui est officiellement supporté (sources Meta)

- **Le fine-tune est supporté** pour les modèles **CTC** et LLM (pas la variante `Unlimited`). Recette prête :
  `python -m workflows.recipes.wav2vec2.asr $OUT --config-file .../configs/ctc-finetune.yaml`.
- **Low-resource documenté** : CTC 300M/1B/3B, seed depuis le checkpoint OmniASR ; preset compute-contraint **LR 1e-5, 5 000 steps, grad_accumulation 4**.
- **Config par défaut** (`ctc-finetune.yaml`) : `dtype: torch.bfloat16`, `num_steps: 20_000`, `lr: 5e-05`, `freeze_encoder_for_n_steps: 0`, validation/checkpoint tous les 1000 steps. **Pas** de gradient checkpointing dans le défaut.

## 2. Le mur : le GPU

- Meta entraîne avec **« 32 GPU pour le 300M, 64 GPU pour le 1B, 96 GPU pour le 3B »**. C'est le setup **assumé** de la recette (multi-GPU massif).
- **Estimation mémoire** (bf16 poids + grads + états Adam fp32 + master fp32 ; *estimation, non mesurée*) :

  | Modèle | Fine-tune COMPLET (poids+Adam, hors activations) | Tient sur T4 16 Go ? |
  |---|---|---|
  | 300M | ~5 Go | ✅ oui (large) |
  | **1B** | **~14-16 Go** | 🔴 **non** (OOM avant même les activations) |
  | 3B | ~45 Go+ | ❌ non |

- **Levier trouvé** : `freeze_encoder_for_n_steps`. En gelant l'encodeur (n'entraîner que la **tête CTC**), les états d'optimiseur ne portent que sur la tête (minuscule) → le **1B tient alors sur un T4** (seuls ~2 Go de poids en avant + tête entraînable). Contrepartie : **adaptation moindre** qu'un fine-tune complet.

## 3. Voies réalistes (à trancher au maillon ③)

| Voie | GPU | Faisable gratuit | Adaptation | Note |
|---|---|---|---|---|
| **A** — 300M complet | 1× T4 | ✅ | bonne | Le plus simple ; base CER 26 % (benchmark 0003). C'est le **fallback d'ADR-0036**. |
| **B** — 1B encodeur gelé (tête seule) | 1× T4 | ✅ | moyenne | Garde la meilleure base (1B, CER 22 %) mais adapte moins. |
| **C** — 1B complet | A100 40 Go+ | 💰 payant | max | Colab Pro+ / cloud. Meilleur potentiel, coût réel. |

**Non tranché ici** (ce n'est pas l'objet) : le choix A/B/C dépendra du **budget** et de la **qualité visée**, une fois les données d'esse prêtes. Ce document garantit juste qu'**aucune voie n'est un cul-de-sac** et documente le compromis.

## 4. Données : format attendu

- **Parquet** (pas HF dataset direct), colonnes : `text` (transcription normalisée), `audio_bytes` (flac/ogg compressé), `audio_size`, + `corpus`/`split`/`language`. **Audio 16 kHz mono**.
- Carte dataset YAML (`src/omnilingual_asr/cards/datasets/*.yaml`, `dataset_family: mixture_parquet_asr_dataset`) référencée dans la config de recette.
- **Notre export dictée** (ZIP `audio/` + `metadata.csv`, ADR-0035) est **convertible** (intégration HuggingFace documentée dans le dataprep) → un **script de conversion** ZIP→parquet sera le premier livrable du maillon ③.

## 5. Impact sur ADR-0036 (n'annule rien)

ADR-0036 a choisi le **1B** comme *meilleure base* (CER 22,1 % vs 26,0 %) — **toujours vrai**. Ce dé-risquage ajoute la contrainte **matériel d'entraînement** : le fine-tune **complet** du 1B exige un gros GPU. Sur GPU gratuit, le maillon ③ devra donc choisir **300M complet (A)** ou **1B tête-gelée (B)** — sauf accès A100 (C). Le fallback 300M d'ADR-0036 gagne en pertinence (trainable **et** plus léger à servir).

## 6. Prochaines étapes (maillon ③, quand les données esse sont prêtes)
1. Script **export dictée (ZIP) → parquet Omnilingual** (16 kHz, `text`/`audio_bytes`/`audio_size`/`language`).
2. **Test mécanique** sur un mini-échantillon (Kaggle T4, ~100 steps) pour prouver que la recette tourne end-to-end — AVANT le vrai run.
3. **ADR « procédure de fine-tune »** (choix A/B/C + hyperparams) puis run complet + mesure du CER fine-tuné (viser < 15 %).

## Références
- Repo : `facebookresearch/omnilingual-asr` — `workflows/dataprep/README.md`, `workflows/recipes/wav2vec2/asr/README.md` + `configs/ctc-finetune.yaml`.
- Papier : Omnilingual ASR, arXiv:2511.09690.
- Benchmark amont : [0003 résultats](0003-asr-baoule-evaluation-results.md) ; décision : [ADR-0036](../adr/0036-choix-modele-asr-baoule.md).

## Historique
- **2026-08-27** — recherche (repo officiel + config recette). Conclusion : fine-tune faisable sur GPU gratuit via 300M-complet **ou** 1B-tête-gelée ; 1B-complet = A100. Aucun cul-de-sac.
