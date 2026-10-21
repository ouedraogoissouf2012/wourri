# ADR-0044 — Procédure de fine-tune ASR baoulé : Omnilingual 1B, entraînement complet sur GPU loué

**Statut** : proposé
**Date** : 2026-10-19
**Auteur(s)** : Claude (assistant) sous direction de Ouedraogo Issouf
**Valideur** : Ouedraogo Issouf — en attente (voie C et budget de départ de 15 USD choisis en discussion le 2026-10-19)
**ADRs liés** : [ADR-0036](0036-choix-modele-asr-baoule.md) (choix du 1B comme base, **exécuté** ici), [ADR-0035](0035-collecte-dataset-asr-dictee.md) (dataset de dictée), [ADR-0034](0034-atelier-parite-linguistique.md)
**Issue** : #474 (epic #472) — chantier BAO-2 de la feuille de route

---

## Contexte

- **ADR-0036** (accepté) a retenu `omniASR_CTC_1B` comme base de fine-tuning : meilleur CER zero-shot mesuré, 22,1 % contre 26,0 % pour le 300M (benchmark 0003, 290 clips).
- **Étude 0004** : le fine-tune **complet** du 1B demande environ 14 à 16 Go rien que pour les poids et les états d'optimiseur. Il ne tient donc pas sur un T4 gratuit. Les voies gratuites sont « 300M complet » et « 1B encodeur gelé » ; la voie « 1B complet » demande un A100 payant.
- **Test mécanique 0005** :
  - la chaîne complète est prouvée sur Kaggle T4 (essai A, 300M complet) : UER de validation 21,1 → 18,2 % en 100 étapes ;
  - la mémoire était à 96 % : le T4 est déjà plein avec le 300M ;
  - les données sont prêtes et vérifiées : Common Voice `bci` (train 319, dev 267, test 290) et la dictée d'esse (433 phrases, 1,3 h) ;
  - aucun locuteur ni aucune phrase en commun entre train, dev et test.
- **Ce qui a changé** : le projet dispose désormais d'un budget. Le valideur demande la meilleure option et fixe un **premier budget de 15 USD**.
- **Prix** relevés entre mars et août 2026 (à revérifier au moment de louer) : A100 80 GB à environ 1,2–1,8 USD/h chez RunPod, 2–2,8 USD/h chez Lambda.
- **Consentement (QUA-3, #575)** : le locuteur de la dictée (« esse ») est le responsable du projet lui-même. Il autorise l'usage de sa voix pour cet entraînement, y compris sur un serveur loué. Ce point est à consigner dans le dossier de consentement.

## Questions posées avant la décision

1. Gratuit d'abord (Kaggle) ou directement payant ?
2. Comment ne pas dépasser le budget ?
3. Comment mesurer le gain honnêtement ?

Réponses (discussion du 2026-10-19) :

- Q1 → directement payant. Un essai de plus sur Kaggle (1B encodeur gelé) testerait une variante bridée, sans éclairer la décision ; Kaggle a déjà prouvé que la chaîne fonctionne.
- Q2 → deux temps : une MESURE courte qui donne la vitesse, puis un entraînement COMPLET dont le nombre d'étapes est **calculé pour tenir dans le budget restant**.
- Q3 → le split `test` est évalué à chaque validation mais **jamais entraîné**. On compare le modèle avant entraînement (validation au départ) et la meilleure version choisie **sur `dev`**, dans les mêmes conditions.

## Options étudiées

### Option A — 300M complet sur Kaggle (gratuit)
- **Avantages** : coût nul ; chaîne déjà prouvée ; modèle léger à servir sur CPU.
- **Inconvénients** : base moins bonne (26,0 % contre 22,1 %) ; mémoire du T4 saturée (96 %) ; quotas et coupures de session (une session a déjà été perdue pendant l'essai B).

### Option B — 1B encodeur gelé sur Kaggle (gratuit)
- **Avantages** : garde la meilleure base ; tient sur un T4.
- **Inconvénients** : seule la couche de sortie apprend, l'adaptation au baoulé est faible ; non testé.

### Option C — 1B complet sur A100 loué (retenue)
- **Avantages** : meilleure base **et** adaptation maximale. Machine stable, bf16 natif, lots plus grands.
- **Inconvénients** : coût réel. Risque de surapprentissage plus fort avec 2 h de données et 4 voix. Le 1B reste à servir sur un CPU (dette d'ADR-0036).

### Comparatif

| Critère | A | B | C (retenue) |
|---|---|---|---|
| Base de départ (CER zero-shot) | 26,0 % | 22,1 % | 22,1 % |
| Adaptation | complète | faible | complète |
| Coût | 0 | 0 | 15 USD au départ, mesuré avant de continuer |
| Fiabilité de la machine | quotas, coupures | quotas, coupures | stable |
| Service en production | facile (300M) | 1B à quantifier | 1B à quantifier |

## Décision

**Option retenue** : **C** — `omniASR_CTC_1B`, entraînement complet, 1× A100 80 GB loué (RunPod), notebook `finetune/colab/omnilingual_finetune_1b_gpu_loue.ipynb`.

**Procédure** :

1. **Données** :
   - `train` = Common Voice `bci` train + dictée d'esse (corpus pondérés par la recette, β = 0,5) ;
   - `dev` = Common Voice validation ;
   - `test` = Common Voice test (290 clips du benchmark 0003, **jamais entraînés**) ;
   - préparation par `finetune/prepare_bci_dataset.py` (testé, recopié dans le notebook).
2. **Réglages**, dérivés de `ctc-finetune-recommendation.yaml` (omnilingual-asr 0.1.0) :
   - lr 1e-5 (AdamW, tri-stage), bf16 ;
   - accumulation de gradient 1, lots de **240 s d'audio** (moitié de l'amont, pour limiter le surapprentissage) ;
   - `example_shuffle_window: 1000` (la valeur amont 0 est refusée par `asr_task.py`).
3. **MESURE** : 100 étapes, validation aux étapes 0, 50 et 100 sur `dev` et `test`. Donne la vitesse (secondes par étape) et vérifie que tout tourne.
4. **COMPLET** :
   - nombre d'étapes = budget restant × 0,8, moins 30 min, converti en étapes ; au maximum 2 000, par paliers de 200 ;
   - validation toutes les 100 étapes, checkpoint toutes les 200 ;
   - **la meilleure version est choisie sur `dev` (UER) uniquement**.
5. **Résultat** : UER et WER sur `test`, du modèle de départ comparé à la meilleure version. Il est publié **même si le gain est nul ou négatif** (critère BAO-2).
6. **Budget** :
   - plafond de **15 USD** pour ce premier passage ;
   - toute relance ou dépassement demande l'accord du valideur ;
   - la machine est arrêtée et supprimée dès la fin.

## Conséquences

- **Positives** :
  - le meilleur modèle possible est entraîné sur nos données, pour un coût **connu avant d'être engagé** ;
  - la comparaison est honnête : même jeu de test, même normalisation, modèle de départ mesuré dans le même run.
- **Négatives assumées** :
  - **surapprentissage** possible (2 h, 4 voix) : la sélection sur `dev` le limite, sans l'exclure. Le vrai remède est d'avoir plus de voix ;
  - **le chiffre UER de la recette n'est pas exactement le CER du benchmark 0003** (normalisation différente). La comparaison qui fait foi est celle du même run (étape 0 contre meilleure version) ;
  - **le service en production n'est pas réglé** : le 1B sur le CPU de Contabo reste à quantifier (int8/ONNX) et à mesurer. Le 300M reste le repli d'ADR-0036.
- **Travail induit** :
  - `finetune/prepare_bci_dataset.py` et son test ;
  - le notebook GPU loué ;
  - le script `finetune/colab/sync_smoke_test_notebook.py`, étendu aux deux notebooks ;
  - après le run : une fiche de résultats dans `docs/benchmarks/`, et le checkpoint retenu sauvegardé dans un dépôt Hugging Face **privé** (cellule optionnelle), sinon il disparaît avec la machine ;
  - plus tard : un ADR « service ASR baoulé » (quantification, latence, routage vers l'option A d'ADR-0043).
- **Retour arrière** : aucun impact sur la production. Rien n'est déployé par cette décision.

## Références

- Benchmark 0003 (résultats), étude 0004, test mécanique 0005 (essai A, pièges d'exécution, QUA-2).
- `facebookresearch/omnilingual-asr` 0.1.0 : `workflows/recipes/wav2vec2/asr/` (recette, `valid_split` multiple, configs).
- Prix A100 : relevés publics (RunPod, Lambda, Vast.ai), 2026, à revérifier au moment de louer.

## Historique

- 2026-10-19 — proposé (voie C et budget de départ de 15 USD choisis en discussion avec le valideur).
- 2026-10-19 — premier passage exécuté sur RunPod (A100 SXM 80 GB, **4,71 USD** au total). La meilleure version (étape 1 200, choisie sur `dev`) donne sur `test` une UER de 21,94 → **18,70 %** et un WER de 56,45 → **45,34 %**. Le gain plafonne après environ 1 200 étapes, et la cible CER < 15 % d'ADR-0036 n'est pas atteinte : le levier suivant est d'avoir plus de voix. Détails, courbe complète et pièges d'exécution corrigés dans le notebook : [résultats 0006](../benchmarks/0006-omnilingual-1b-finetune-resultats.md).
- 2026-10-21 — CER mesuré avec le protocole exact du benchmark 0003 (mêmes 290 clips, même normalisation, 1B de départ remesuré comme témoin : 22,0 %, conforme aux 22,1 %) : **18,7 %** pour la version retenue (WER 45,2 %). Le critère d'acceptation de BAO-2 est rempli ; la cible < 15 % ne l'est pas. Environ 0,3 USD (RunPod A40). Voir [résultats 0006 §3.5](../benchmarks/0006-omnilingual-1b-finetune-resultats.md).
