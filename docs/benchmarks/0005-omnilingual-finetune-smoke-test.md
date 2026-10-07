# Test mécanique #0005 — Fine-tune Omnilingual sur le baoulé (étape 2 de l'étude 0004)

**Statut** : outillé, en attente d'exécution sur Kaggle
**Date de rédaction** : 2026-10-07
**Décision qu'il informe** : futur ADR « procédure de fine-tune » (#474) — choix A / B / C de l'[étude 0004](0004-omnilingual-finetune-feasibility.md)
**Fondations** : [étude 0004](0004-omnilingual-finetune-feasibility.md) · [benchmark 0003](0003-asr-baoule-evaluation-results.md) · [ADR-0036](../adr/0036-choix-modele-asr-baoule.md)

---

## 1. Objectif

Prouver que la **recette officielle de fine-tune** d'Omnilingual (`workflows.recipes.wav2vec2.asr`) tourne **de bout en bout** sur des données baoulé, sur un **GPU gratuit (T4)**, **avant** le vrai run sur la dictée d'esse — pour ne pas découvrir un mur le jour J.

Ce test **ne mesure pas** la qualité finale : 100 étapes ne suffisent pas à entraîner un modèle. Il mesure ce qui manque pour écrire l'ADR : **quelles voies tiennent sur un T4, en combien de temps, avec quel pic mémoire**.

Il ne touche à aucun code de production. Il n'a pas besoin des données d'esse : il tourne sur Common Voice `bci`, et la dictée peut être ajoutée en option.

---

## 2. Écarts trouvés en préparant le test (vérifiés dans le code amont)

Lecture du code d'`omnilingual-asr` **0.1.0** (version épinglée depuis le benchmark 0003) et de `fairseq2` **0.6.0**. Le pont livré en #506 n'était **pas** lisible par la recette. Il est corrigé dans `finetune/dictee_to_parquet.py`.

| Point | Avant (#506) | Attendu par la recette | Source amont |
|---|---|---|---|
| Rangement | un fichier parquet « à plat » | dataset **partitionné** `corpus=…/split=…/language=…/` : la recette découvre splits et partitions **par les noms de dossiers** | `datasets/storage/mixture_parquet_storage.py` |
| Code langue | `bci` | `bci_Latn` (ISO 639-3 + écriture) | `workflows/dataprep/README.md` §2.1 |
| `audio_bytes` | `binary` | `list<int8>` | idem |
| Texte cible | brut | normalisé : minuscules, ponctuation et mots uniquement numériques retirés ; `ʼ` (U+02BC) **conservé** | `workflows/dataprep/text_tools.py` |
| Statistiques | absentes | TSV `corpus / language / hours` (`dataset_summary_path`) | `hf_dataset_ingestion_example.py` |
| Carte dataset | absente | YAML `mixture_parquet_asr_dataset` dans le répertoire d'assets fairseq2 (`FAIRSEQ2_USER_ASSET_DIR`) | `workflows/dataprep/README.md` §4.3 · `fairseq2/assets/dirs.py` |

Deux autres contraintes, gérées dans le notebook :
- la recette (`workflows/`) **n'est pas livrée par `pip`** : le dépôt est cloné **au même tag** (`0.1.0`) que le paquet installé ;
- la recette entraîne par défaut en **bfloat16**, que le T4 (Turing) ne gère pas en matériel : les essais tournent en **float32** (`mixed_precision.mode: off`).

Garde-fous : `finetune/test_dictee_to_parquet.py` reproduit, avec pyarrow seul, la découverte des splits et des partitions de la recette (fairseq2 ne s'installe pas sous Windows), et vérifie que le notebook embarque la version à jour du convertisseur.

---

## 3. Essais

Données : Common Voice `bci`, miroir `Klayt/baoule-common-voice` (révision épinglée du benchmark 0003). Le split `train` (319 clips) sert à l'entraînement et le split `dev` (267 clips) à la validation. Le split **`test` (290 clips) reste hors entraînement** : c'est le set du benchmark 0003, réservé à la comparaison du CER fine-tuné avec le CER zero-shot.

| Essai | Modèle | Encodeur | Voie (étude 0004) |
|---|---|---|---|
| **A** | `omniASR_CTC_300M` | entraîné (fine-tune complet) | A |
| **B** | `omniASR_CTC_1B` | **gelé** pendant les 100 étapes (`freeze_encoder_for_n_steps: 100`) | B |

Réglages communs, dérivés de `configs/ctc-finetune-recommendation.yaml` (amont) :

- 100 étapes ;
- lr 1e-5, avec un échauffement proportionnel au nombre d'étapes (10 % / 40 % / 50 %) ;
- 60 s d'audio par lot (`max_num_elements: 960_000`, contre 7,68 M en amont sur gros GPU) ;
- accumulation de gradient sur 4 lots ;
- précision float32 ;
- validation au départ (`validate_at_start`), puis aux étapes 50 et 100 ;
- un checkpoint à l'étape 100.

La voie C (1B complet) n'est pas testée : l'étude 0004 l'estime hors d'un T4 (environ 14 à 16 Go en poids et états d'optimiseur, avant même les activations).

---

## 4. Critères de réussite (fixés a priori)

Un essai est **réussi** si les quatre conditions sont remplies :
1. le processus se termine avec le code de sortie 0 ;
2. le checkpoint `checkpoints/step_100` est écrit ;
3. aucune erreur de mémoire GPU (OOM) n'apparaît ;
4. la validation (UER, WER) s'affiche au départ, puis à l'étape 100.

Une baisse de la perte ou de l'UER est **un bon signe, pas un critère** : 100 étapes ne permettent pas de conclure sur la qualité. L'UER de la recette est un taux d'erreur par unité du tokenizer. Ce tokenizer travaille au caractère (`char_tokenizer`), l'UER est donc l'équivalent du CER, mais sur la normalisation de la recette, pas sur celle du benchmark 0003.

---

## 5. Procédure

- **Notebook** : `finetune/colab/omnilingual_finetune_smoke_test.ipynb`. Il est autonome : la cellule 3 recopie `finetune/dictee_to_parquet.py`.
- **Environnement** : Kaggle, *GPU T4 x2* (un seul GPU utilisé) avec *Internet on*. Python 3.12 maximum (voir le benchmark 0003 : Colab est passé en 3.13).
- **Installation** : mêmes versions que le benchmark 0003 (`omnilingual-asr==0.1.0`, `fairseq2[arrow]==0.6`, `torch==2.8.0`), puis redémarrage de la session.
- **Validation de la config** : avant chaque essai, `--dump-config` fait vérifier la config par fairseq2.
- **Option** : l'export de la dictée (ZIP de l'atelier, téléversé comme dataset Kaggle) s'ajoute en `corpus=wourri_dictee/split=train` (cellule 5).
- **Durée** : non estimée. Elle fait partie de ce que le test mesure.

---

## 6. Résultats

*À remplir après exécution, à partir de la cellule 11 et de `finetune_smoke_results.json`.*

| Essai | Réussi ? | Durée | Pic mémoire GPU | UER départ → étape 100 | WER départ → étape 100 | Remarques |
|---|---|---|---|---|---|---|
| A — 300M complet | | | | | | |
| B — 1B encodeur gelé | | | | | | |

---

## 7. Suite

1. Reporter les résultats ci-dessus.
2. Écrire l'**ADR « procédure de fine-tune »** : le choix A / B / C, les hyperparamètres, le jeu de validation et la cible (CER < 15 % sur le split `test`, voir ADR-0036).
3. Lancer le vrai run sur la dictée d'esse et Common Voice, puis mesurer le CER fine-tuné sur le split `test` avec la normalisation du benchmark 0003.

## 8. Hors périmètre

- La qualité finale et le CER fine-tuné : c'est l'objet du vrai run, après l'ADR.
- La quantification int8/ONNX et la latence de service CPU : ce sont des dettes d'ADR-0036.
- Le multi-GPU : la recette amont le suppose (32 à 96 GPU chez Meta), mais ce test vise un seul T4.

---

## Historique
- **2026-10-07** : rédaction. Écarts du pont #506 trouvés en lisant le code amont (`omnilingual-asr` 0.1.0, `fairseq2` 0.6.0) et corrigés ; notebook Kaggle prêt à exécuter.
