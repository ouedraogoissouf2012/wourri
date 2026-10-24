# Résultats #0007 — 2e fine-tune d'Omnilingual 1B sur le baoulé : Common Voice 27 + Zenodo + dictée

**Statut** : terminé — exécuté le 2026-10-24 sur RunPod
**Décision exécutée** : [ADR-0044](../adr/0044-procedure-finetune-asr-baoule.md), révision du 2026-10-24 (plafond 15 USD accordé par le valideur)
**Fondations** : [résultats 0006](0006-omnilingual-1b-finetune-resultats.md) (1er fine-tune) · [registre des sources](../REGISTRE_SOURCES_BAOULE.md)
**Notebook** : `finetune/colab/omnilingual_finetune_1b_cv27.ipynb` · **Issue** : #474

---

## 1. En bref

- Sur le **même test** (623 clips, 7 voix jamais entraînées, phrases jamais lues à l'entraînement), avec le **protocole du benchmark 0003** :

| Modèle | CER | WER | Transcriptions vides |
|---|---|---|---|
| Départ (`omniASR_CTC_1B`, non entraîné) | 19,4 % | 52,6 % | 12 |
| Actuel (1er fine-tune, `step_1200`, fiche 0006) | 16,6 % | 43,2 % | 14 |
| **Nouveau (2e fine-tune, `step_3000`)** | **13,4 %** | **34,8 %** | 12 |

- **Gain par rapport au modèle actuel** : −3,2 points de CER et −8,4 points de WER, soit **environ −19 %** d'erreurs en relatif dans les deux cas.
- **Gain par rapport au départ** : −31 % de CER, −34 % de WER.
- **La cible d'ADR-0036 (CER < 15 %) est atteinte** sur ce test. Ce n'est pas le test du benchmark 0003 (voir §4), mais les trois modèles y sont mesurés dans la même session.
- **Coût** : l'estimation du notebook s'arrête à 2,24 USD à la synthèse. L'évaluation, la sauvegarde et la mise en route s'y ajoutent ; le relevé RunPod fait foi.
- **Le levier était bien le nombre de voix**, comme l'annonçait la fiche 0006 : même recette, 4 fois plus de données (2 h → 8,1 h, 4 → 14 voix).

## 2. Données

Répartition par `finetune/cv27_split.py` (règle et choix détaillés dans la révision d'ADR-0044). Aucune voix ni phrase du test n'est apprise, vérification bloquante comprise.

| Split | Contenu | Clips | Heures | Voix |
|---|---|---|---|---|
| train | Common Voice 27, hors voix et phrases du test | 3 019 | 5,93 | 9 |
| train | Zenodo 6705861 (numéros de verset non prononcés, retirés) | 565 | 0,85 | 4 |
| train | Dictée d'esse | 433 | 1,30 | 1 |
| dev | Common Voice 27 : 2 voix jamais entraînées × autres phrases | 738 | 1,49 | 2 |
| test | Common Voice 27 : 7 voix jamais entraînées × les 290 phrases du test officiel | 623 | 1,25 | 7 |

## 3. Entraînement

| Élément | Valeur |
|---|---|
| Recette | identique au 1er fine-tune : complet, AdamW lr 1e-5 tri-stage, bf16, lots de 240 s |
| Machine | RunPod, 1× A100 SXM 80 GB, 1,81 USD/h, disque 120 Go |
| MESURE | 100 étapes, 3,3 min, 0,8 s/étape, pic GPU 57 Go |
| COMPLET | 3 000 étapes (plafond du notebook), 40 min, 0,78 s/étape, pic GPU 80,1 Go |
| Choix de la version | sur `dev` uniquement : `step_3000` (UER dev 8,99) |

UER de la recette (normalisation de la recette, différente de celle du benchmark 0003), une ligne sur 500 :

| Étape | dev | test |
|---|---|---|
| 0 | 17,48 | 19,25 |
| 500 | 14,25 | 16,15 |
| 1 000 | 12,27 | 14,79 |
| 1 500 | 10,83 | 14,07 |
| 2 000 | 9,69 | 13,50 |
| 2 500 | 9,21 | 13,42 |
| 3 000 | 8,99 | 13,31 |

- **Plateau sur le test après environ 2 000 étapes** : 13,5 → 13,3. La perte de validation du test remonte légèrement (31,6 à l'étape 1 900, 32,6 à 3 000), alors que le dev continue de baisser : le dev partage des phrases avec l'entraînement.
- Allonger l'entraînement n'apporterait presque rien. Le levier suivant reste les données : plus de voix, et des voix de paysans au téléphone (BAO-6).

## 4. Limites

- **Ce n'est pas le test du benchmark 0003** : 3 des 9 voix de l'ancien test sont maintenant à l'entraînement. Le modèle actuel obtient 16,6 % ici contre 18,7 % sur l'ancien test : ce test est un peu plus facile. **La comparaison qui fait foi est celle des trois modèles côte à côte**, pas avec les chiffres de 0006.
- **11 clips sont vides pour les trois modèles**, des fichiers consécutifs d'une même voix. Ce sont probablement les enregistrements quasi muets déjà relevés en 0006 §3.6 (non vérifié à l'écoute). Analyse **a posteriori**, sans ces 11 clips (612 clips) : départ 18,0 %, actuel 15,1 %, **nouveau 11,9 %** de CER.
- **7 voix au test** : mieux que 4, mais la robustesse sur des voix d'agriculteurs au téléphone reste à mesurer sur le terrain (BAO-6).
- **Erreurs restantes** (exemples du test) : mots collés ou coupés (« nansran » pour « naan sran », « mmua mua » pour « mmuammua »), quelques tons et voyelles (« kwlɔʼn » pour « kwla »), mots étrangers (« si loɛ » pour « silhouette »). Un modèle de langue construit avec les textes du registre (7 millions de mots) vise précisément les coupures de mots : à mesurer séparément.

## 5. Ce qui est conservé

- **Checkpoint** : dépôt Hugging Face **privé** `seven990/omniasr-ctc-1b-bci-wourri-cv27`, dossier `step_3000/` (3,9 Go) et `finetune_1b_cv27_results.json`.
- **Chiffres** : `0007-eval-cv27-results.json`. Il ne garde que les mesures : pas de transcription, car Common Voice interdit de republier ses données.
- **Notebook avec ses sorties** et répartition (`split_cv27.json`) : conservés par le chef de projet, hors dépôt (le manifeste contient les phrases du test Common Voice).
- **Serveur voix** (`finetune/colab/serveur_voix_baoule_runpod.ipynb`) : pointe désormais vers ce modèle.
