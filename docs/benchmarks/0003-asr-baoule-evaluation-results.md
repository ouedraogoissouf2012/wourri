# Benchmark #0003 — Résultats : Évaluation ASR baoulé (bci)

**Statut** : ✅ **exécuté 2026-08-27** (Kaggle, 2× Tesla T4, Python 3.12.13)
**Protocole** : [0003-asr-baoule-evaluation.md](0003-asr-baoule-evaluation.md)
**Décision qu'il informe** : [ADR-0036 — choix du modèle ASR baoulé](../adr/0036-choix-modele-asr-baoule.md)

---

## 1. Résultats mesurés (split `test` Common Voice bci, 290 clips)

| # | Modèle | Params | **CER** | WER | n | Verdict |
|---|---|---|---|---|---|---|
| M1 | Omnilingual ASR CTC 300M | 300M | 26,0 % | 67,6 % | 290 | viable |
| **M2** | **Omnilingual ASR CTC 1B** | **1B** | **22,1 %** | 56,7 % | 290 | ✅ **meilleur** |
| M3 | Simba-S | 2,3B | — | — | — | non exécuté (témoin optionnel) |

- **Métrique principale = CER** (langue peu écrite, orthographe variable — cf. protocole §4.1).
- Modèle 1B : chargement 83 s, inférence 113 s sur les 290 clips (T4).
- **Aucun token HF requis** (dataset `Klayt/baoule-common-voice`, CC0, révision épinglée).
- M3 (Simba, témoin « sort-il du français ? ») non lancé : le résultat Omnilingual étant clair et positif, le témoin n'était pas nécessaire à la décision. Reste exécutable si besoin.

## 2. Lecture (seuils a priori du protocole §5)

Le meilleur modèle (**Omnilingual 1B, CER 22,1 %**) tombe dans la tranche **15–40 % = « base de fine-tuning viable »** — le cas attendu et espéré. **Omnilingual comprend déjà substantiellement le baoulé en zero-shot** (jamais fine-tuné sur du baoulé Wourri). Ce n'est pas exploitable tel quel en production (22 % de caractères erronés), mais c'est une **excellente base** que le fine-tuning (#474) sur la voix native d'esse fera baisser.

## 3. Qualitatif — les transcriptions sont du VRAI baoulé

Ce ne sont ni du charabia ni du français : le modèle capte la structure, le lexique et les phonèmes propres (`ɛ`, `ɔ`, `ʼ`). Le **1B est nettement meilleur** que le 300M (mots mieux segmentés, moins de fusions).

| Réf. baoulé | Omnilingual 1B |
|---|---|
| E kwla yo ninnge mun likawlɛ naan sran kwlaa wʼa yo kpa. | e kwla yo ninge mun likawlɛ nan sran kwlaa wa yokpa |
| Ye wa kɔ lika mmuammua ainman. | ye wa kolika mwamwa ayima |
| Blaʼm be nian fieʼn nun nnɛnʼm be lika, be man be aliɛ… | blaʼm be niamfieʼ nu nnɛʼm be lika be mam be aliɛ… |

Écarts typiques : fusions/segmentation de mots (`ninnge`→`ninge`, `yo kpa`→`yokpa`), simplification de diacritiques et de la gémination (`nnɛn`→`nnɛ`), apostrophes tonales parfois perdues — exactement le genre d'erreurs qu'un fine-tuning corrige.

## 4. Observations / limites

- **Clips vides** : quelques audios produisent une transcription vide (ex. exemples [5][6][7] des 10 échantillons affichés) — probablement des audios courts ou difficiles. Ces cas sont **déjà comptés comme erreurs** dans le CER de 22,1 % (donc le vrai potentiel « hors clips ratés » est meilleur encore).
- **Dataset restreint** : 290 clips (miroir public), pas le bucket `validated` complet (~11 h). Suffisant pour comparer ; le fine-tuning puisera dans un corpus plus large + la collecte esse.
- **Zero-shot** : aucun des deux modèles n'a vu de baoulé Wourri — le fine-tuning est la suite logique (#474).

## 5. Recommandation

Le **modèle au plus faible CER produisant réellement du baoulé** est **Omnilingual ASR CTC 1B** (22,1 %). C'est la **base recommandée pour le fine-tuning** — formalisée dans [ADR-0036](../adr/0036-choix-modele-asr-baoule.md), qui arbitre aussi le compromis **1B (précision) vs 300M (légèreté de déploiement)**.

## Historique
- **2026-08-27** — exécution sur Kaggle (2× T4, Python 3.12.13). Notebook `finetune/colab/asr_baoule_benchmark.ipynb` (portable Colab/Kaggle après le passage de Colab en Python 3.13). Résultats bruts : `asr_baoule_results.json`.
