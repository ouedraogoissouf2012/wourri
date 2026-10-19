# Résultats #0006 — Fine-tune complet d'Omnilingual 1B sur le baoulé (GPU loué)

**Statut** : terminé — premier passage exécuté le 2026-10-19
**Date de rédaction** : 2026-10-19
**Décision exécutée** : [ADR-0044](../adr/0044-procedure-finetune-asr-baoule.md) (voie C : 1B complet sur A100 loué, budget de départ 15 USD)
**Fondations** : [benchmark 0003](0003-asr-baoule-evaluation-results.md) · [étude 0004](0004-omnilingual-finetune-feasibility.md) · [test mécanique 0005](0005-omnilingual-finetune-smoke-test.md) · [ADR-0036](../adr/0036-choix-modele-asr-baoule.md)
**Issue** : #474 (epic #472) — chantier BAO-2

---

## 1. En bref

- Le fine-tune complet de `omniASR_CTC_1B` a tourné **de bout en bout** : 2 000 étapes sur un A100 80 GB loué chez RunPod, pour un **coût total de 4,71 USD** (plafond fixé : 15 USD).
- Sur le split `test` (Common Voice `bci`, **jamais entraîné**, 9 locuteurs absents de l'entraînement) :
  - **UER : 21,94 % → 18,70 %**, soit −3,2 points (−15 % en relatif) ;
  - **WER : 56,45 % → 45,34 %**, soit −11,1 points (−20 % en relatif).
- La meilleure version est celle de l'**étape 1 200**, choisie sur `dev` uniquement.
- Au-delà d'environ 1 200 étapes, le gain **plafonne** : les données manquent, pas le temps de calcul.
- **La cible d'ADR-0036 (CER < 15 % sur `test`) n'est pas atteinte.** Le levier suivant est d'avoir **plus de voix**, pas plus d'étapes.
- Le modèle n'est **pas déployé**. Il est sauvegardé dans un dépôt Hugging Face **privé**.

---

## 2. Conditions

| Élément | Valeur |
|---|---|
| Modèle de départ | `omniASR_CTC_1B` (omnilingual-asr 0.1.0, fairseq2 0.6.0) |
| Entraînement | complet (aucune couche gelée), AdamW, lr 1e-5 tri-stage, bf16 |
| Lots | 240 s d'audio par étape, accumulation de gradient 1 |
| Durée | 2 000 étapes ; validation toutes les 100 étapes et au départ ; checkpoint toutes les 200 |
| Machine | RunPod, 1× A100 SXM 80 GB, 1,80 USD/h |
| Vitesse | environ 0,69 s par étape d'entraînement (mesurée par le run MESURE de 100 étapes) |
| Mémoire GPU | pic de 65,7 Go pendant la MESURE |
| Notebook | `finetune/colab/omnilingual_finetune_1b_gpu_loue.ipynb` |

**Données** (préparées par `finetune/prepare_bci_dataset.py`) :

| Split | Contenu | Rôle |
|---|---|---|
| `train` | Common Voice `bci` train (319 clips) + dictée d'esse (433 phrases, 1,30 h) | entraînement |
| `dev` | Common Voice `bci` validation (267 clips) | choix de la meilleure version |
| `test` | Common Voice `bci` test (290 clips, ceux du benchmark 0003) | chiffre à comparer, **jamais entraîné** |

- Aucun locuteur ni aucune phrase n'est partagé entre les trois splits (vérification QUA-2, fiche 0005).
- Les clips de **moins de 2 s** sont exclus (`min_audio_len: 32000`, voir §5). L'exclusion est **identique** à l'étape 0 et à toutes les étapes suivantes. Le nombre exact de clips exclus n'a pas été relevé.

---

## 3. Résultats

### 3.1 Comparaison qui fait foi

Elle compare le modèle non entraîné (validation au départ) et la meilleure version choisie sur `dev`, **dans le même run et sur les mêmes clips**.

| Split | Métrique | Étape 0 (non entraîné) | Étape 1 200 (retenue) | Écart |
|---|---|---|---|---|
| `test` | UER | 21,94 % | **18,70 %** | −3,24 pts |
| `test` | WER | 56,45 % | **45,34 %** | −11,11 pts |
| `dev` | UER | 16,31 % | 13,75 % | −2,56 pts |
| `dev` | WER | 50,62 % | 40,64 % | −9,98 pts |

- **UER** (taux d'erreur par unité) : l'erreur par caractère selon la normalisation de la recette.
- **WER** : l'erreur par mot.

### 3.2 Courbe complète

| Étape | dev UER | dev WER | test UER | test WER |
|---:|---:|---:|---:|---:|
| 0 | 16,31 | 50,62 | 21,94 | 56,45 |
| 100 | 16,81 | 51,62 | 21,28 | 55,66 |
| 200 | 17,36 | 51,59 | 21,92 | 55,83 |
| 300 | 15,94 | 48,20 | 20,47 | 51,69 |
| 400 | 15,91 | 47,49 | 20,13 | 50,21 |
| 500 | 14,97 | 44,46 | 19,18 | 47,69 |
| 600 | 15,92 | 46,81 | 19,93 | 48,59 |
| 700 | 14,84 | 43,99 | 19,16 | 47,24 |
| 800 | 14,52 | 42,50 | 19,09 | 47,00 |
| 900 | 14,52 | 42,82 | 19,06 | 46,90 |
| 1 000 | 13,90 | 41,03 | 18,75 | 45,45 |
| 1 100 | 14,55 | 42,57 | 19,27 | 47,97 |
| **1 200** | **13,75** | **40,64** | **18,70** | **45,34** |
| 1 300 | 13,70 | 41,00 | 18,35 | 44,97 |
| 1 400 | 14,00 | 41,35 | 18,89 | 45,69 |
| 1 500 | 14,13 | 40,96 | 18,93 | 46,28 |
| 1 600 | 13,88 | 40,46 | 18,50 | 44,93 |
| 1 700 | 13,94 | 40,61 | 18,50 | 44,86 |
| 1 800 | 14,13 | 41,25 | 18,71 | 45,66 |
| 1 900 | 14,00 | 41,03 | 18,65 | 45,21 |
| 2 000 | 14,05 | 40,96 | 18,63 | 45,41 |

### 3.3 Lecture

- **Choix de la version** : parmi les versions sauvegardées (toutes les 200 étapes), l'étape 1 200 a le meilleur UER sur `dev`.
  - L'étape 1 300 est très légèrement meilleure sur `dev` (13,70 contre 13,75), mais elle n'a pas été sauvegardée. L'écart (0,05 point) est inférieur au bruit visible d'une validation à l'autre.
  - Choisir sur `test` (étape 1 300 : 18,35 %) serait de la triche : le chiffre retenu reste **18,70 %**.
- **Plateau** : de l'étape 1 000 à 2 000, l'UER `test` oscille entre 18,35 et 19,27 %, sans tendance. Allonger l'entraînement sur ces données n'apporterait presque rien.
- **Pas de surapprentissage marqué** : `dev` et `test` ne remontent pas en fin de run. Avec seulement 4 voix à l'entraînement, le modèle a appris ce qu'il pouvait, puis s'est arrêté de progresser.
- **Généralisation** : les 9 locuteurs de `test` n'apparaissent ni dans `train` ni dans la dictée. Le gain mesuré porte donc sur des voix **inconnues** du modèle.

### 3.4 Par rapport à la cible

- ADR-0036 vise un **CER < 15 %** sur `test`. Le résultat est **18,70 % d'UER** : **cible non atteinte**.
- L'UER de la recette n'est **pas exactement** le CER du benchmark 0003, car la normalisation diffère (ADR-0044, conséquences). L'ordre de grandeur concorde : 21,94 % d'UER au départ ici, contre 22,1 % de CER zero-shot au benchmark 0003.
- Pour un chiffre strictement comparable au benchmark 0003, il faut réévaluer `step_1200` sur les 290 clips avec la normalisation du benchmark (§6). Ce n'est pas fait ici.

---

## 4. Coût

| Poste | Valeur |
|---|---|
| Total facturé (installation, préparation, MESURE, COMPLET, envoi vers Hugging Face) | **4,71 USD** |
| Plafond ADR-0044 | 15 USD |
| Crédit RunPod restant après le run | 15,29 USD (sur 20 USD versés) |

La procédure en deux temps a fonctionné comme prévu. La MESURE a donné la vitesse, et le nombre d'étapes du COMPLET (2 000, le plafond) tenait largement dans le budget.

---

## 5. Pièges rencontrés pendant le run (corrigés dans le notebook)

Ils s'ajoutent à ceux de la fiche 0005. Chacun est corrigé dans `finetune/colab/omnilingual_finetune_1b_gpu_loue.ipynb`.

| Piège | Symptôme | Correctif |
|---|---|---|
| `pyarrow` récent exige NumPy 2 | import impossible à la préparation des données (le Python 3.12 garde NumPy 1.26) | `pyarrow==20.0.0` à l'installation (minimum demandé par omnilingual-asr) |
| RunPod active `HF_HUB_ENABLE_HF_TRANSFER=1` sans installer `hf_transfer` | échec du téléchargement de Common Voice | `HF_HUB_ENABLE_HF_TRANSFER=0` en cellule 1 |
| **Transcription vide** dans le code de Meta (`wer_calculator.py`, 0.1.0) | plantage de la validation (index 0 sur une longueur nulle) quand le modèle ne sort que des « blancs » sur un clip | la transcription vide est remplacée par 1 symbole de remplissage. L'erreur calculée est identique (n erreurs pour une référence de n unités). Le correctif est appliqué après le clonage, refuse de s'appliquer si le fichier amont a changé, et peut être relancé sans effet. |
| Codes couleur ANSI dans le journal fairseq2 | l'analyse du journal ne trouvait aucun score | codes retirés avant l'analyse |
| Sortie du notebook trop volumineuse | navigateur saturé (« Out of Memory »), page blanche | affichage filtré (scores, erreurs, checkpoints) ; le journal complet reste sur disque |
| `min_audio_len` absent de la config « recommandation » | — | 2 s minimum, comme `ctc-finetune.yaml` amont. Ajouté d'abord comme **première hypothèse, fausse**, sur le plantage de la validation (la vraie cause était la transcription vide). Il est **conservé** parce que le run de référence l'a utilisé et qu'il s'applique à l'identique à toutes les étapes. |

---

## 6. Suite

1. **Plus de voix** : c'est le premier levier. Le modèle plafonne avec 4 voix à l'entraînement. Il faut de nouvelles sessions de dictée par d'autres locuteurs (femmes, hommes, régions différentes), avec un consentement consigné (QUA-3, #575).
2. **Chiffre comparable au benchmark 0003** : réévaluer `step_1200` sur les 290 clips de `test` avec la normalisation du benchmark 0003, pour un CER directement comparable aux 22,1 %.
3. **ADR « service ASR baoulé »** : quantification int8/ONNX du 1B et latence sur le CPU de Contabo. Ensuite, et seulement si le résultat le justifie, passage de l'option W à l'option A d'[ADR-0043](../adr/0043-accueil-baoule-langue-annoncee.md).
4. Toute relance payante demande l'accord du valideur (ADR-0044). Le crédit restant (15,29 USD) couvre largement un deuxième passage quand les nouvelles voix seront là.

---

## 7. Où sont les fichiers

- **Checkpoint retenu** : dépôt Hugging Face **privé** `seven990/omniasr-ctc-1b-bci-wourri`. Il contient `step_1200/` (environ 3,9 Go), `model.yaml` (carte du modèle) et `config_complet.yaml` (configuration exacte du run).
- **Machine** : arrêtée après le run. Elle doit être **supprimée** (Terminate) pour ne plus rien facturer : le volume de stockage reste payant tant que le pod existe.
- Les autres checkpoints (étapes 200 à 2 000) et le journal complet ne sont pas conservés hors de la machine. Le tableau §3.2 en garde les scores.

---

## Historique

- **2026-10-19** : premier passage exécuté (MESURE puis COMPLET 2 000 étapes, 4,71 USD). Meilleure version : étape 1 200, choisie sur `dev`. Le checkpoint est sauvegardé sur Hugging Face (privé). Les pièges du §5 sont corrigés dans le notebook.
