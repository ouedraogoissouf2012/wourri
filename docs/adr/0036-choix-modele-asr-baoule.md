# ADR-0036 — Choix du modèle ASR baoulé (base de fine-tuning)

**Statut** : **accepté**
**Date** : 2026-08-27
**Auteur(s)** : Issouf Ouédraogo + assistance agent
**Valideur** : Issouf — « Omnilingual 1B (recommandé) » 2026-08-27

---

## Contexte

- Chantier « comprendre le baoulé (bci) », **phase #474 (fine-tune ASR)**, epic #472. Il faut choisir la **base** que le fine-tuning entraînera sur la voix native collectée (dictée d'esse, [ADR-0035](0035-collecte-dataset-asr-dictee.md)) + Common Voice bci.
- **Le benchmark [0003](../benchmarks/0003-asr-baoule-evaluation-results.md) a été exécuté (2026-08-27, Kaggle 2× T4)** et a mesuré, en zero-shot sur 290 clips baoulé réels :

  | Modèle | Params | **CER** | WER | Licence | Ciblage bci |
  |---|---|---|---|---|---|
  | Omnilingual CTC 300M | 300M | 26,0 % | 67,6 % | Apache-2.0 | `bci_Latn` explicite |
  | **Omnilingual CTC 1B** | 1B | **22,1 %** | 56,7 % | Apache-2.0 | `bci_Latn` explicite |

- Les deux produisent du **vrai baoulé reconnaissable** (pas de français, pas de charabia). Le 1B est nettement meilleur.
- **Simba-S écarté** : recherche 2026-08-24 (tokenizer sans token baoulé, défaut `__fra__`) — cf. ADR-0034 / benchmark 0003 §2.
- **Contrainte de service** : l'ASR du moteur (`wouri-api`) tourne sur **Contabo en CPU** (pas de GPU). Un modèle 1B en CPU est lent ; un 300M l'est moins. **Mais** : aucun canal WhatsApp baoulé n'existe encore en prod → le service baoulé n'est **pas** immédiat, et une **quantification int8/ONNX** est disponible (Omnilingual 1B CTC int8 existe déjà en `sherpa-onnx`).

## Questions posées avant la décision

1. Quelle base de fine-tuning : 300M ou 1B ?
2. Comment arbitrer **précision (1B)** vs **coût de service CPU (300M plus léger)** ?
3. Le choix ferme-t-il des portes (déploiement) ?

Réponses (discussion 2026-08-27, sur chiffres) :
- Q1 → le **1B** a le meilleur CER (22,1 % vs 26,0 %) et le meilleur plafond après fine-tuning.
- Q2 → la précision prime pour la **base d'entraînement** ; le coût de service se traite **plus tard** par quantification (int8/ONNX) — et le service baoulé n'est pas encore en prod.
- Q3 → non : la quantification post-fine-tune et un fallback 300M restent ouverts.

## Options étudiées

### Option A — Omnilingual ASR CTC **1B** (retenue proposée)
- **Description** : fine-tuner le 1B sur dictée esse + Common Voice bci.
- **Avantages** : **meilleur CER mesuré** (22,1 %) → meilleur plafond ; même famille/licence (Apache-2.0) ; ciblage `bci_Latn` natif ; chemin de service par **int8/ONNX** documenté (sherpa-onnx).
- **Inconvénients** : plus lourd (fine-tune + service) ; latence CPU élevée sans quantification.
- **Coût** : GPU de fine-tuning (Colab/Kaggle) plus gourmand qu'avec le 300M ; quantification à prévoir pour la prod.

### Option B — Omnilingual ASR CTC **300M**
- **Description** : fine-tuner le 300M.
- **Avantages** : **3× plus léger** → service CPU plus réaliste, fine-tune moins gourmand.
- **Inconvénients** : CER de départ **plus haut** (26,0 %) → plafond a priori moindre.
- **Quand** : si la latence CPU du 1B (même quantifié) s'avère rédhibitoire.

### Option C — Autre modèle (Simba-S / MMS / Whisper)
- **Rejetée** : Simba ne cible pas le baoulé (français par défaut) ; MMS = LID only pour bci ; Whisper ne couvre pas bci. Aucun ne bat Omnilingual sur bci.

### Comparatif

| Critère | A — 1B (retenue) | B — 300M | C — autre |
|---|---|---|---|
| CER zero-shot mesuré | **22,1 %** | 26,0 % | non viable (bci absent) |
| Plafond après fine-tune | ✅ meilleur | correct | — |
| Coût service CPU (Contabo) | ⚠️ lourd (quantif requise) | ✅ plus léger | — |
| Licence | Apache-2.0 | Apache-2.0 | variable |
| Ciblage bci natif | ✅ | ✅ | ❌ |

## Décision

**Option retenue** : **A — Omnilingual ASR CTC 1B** comme base de fine-tuning (#474).

**Justification** : le 1B a le **meilleur CER mesuré** (22,1 %, tranche « base viable ») et le meilleur plafond ; la contrainte de service CPU n'est **pas bloquante à ce stade** (pas de canal baoulé en prod) et se traitera par **quantification int8/ONNX** (chemin existant). L'Option B (300M) reste le **fallback explicite** si la latence de service devient rédhibitoire.

## Conséquences

- **Positives** : on part de la meilleure base mesurée ; licence permissive ; suite (#474) débloquée.
- **Négatives assumées** : fine-tune + service plus gourmands ; **quantification à faire** avant prod CPU (dette tracée).
- **Migration / travail induit** : notebook de fine-tune (#474) sur `omniASR_CTC_1B` + dataset dictée (export ADR-0035) + Common Voice bci ; mesurer le **CER fine-tuné** (viser < 15 %) ; plus tard : export int8/ONNX + mesure de latence CPU.
- **Verrous futurs** : dépendance à la toolchain Omnilingual (fairseq2, Python ≤ 3.12 — cf. piège benchmark). Réversible : re-fine-tuner le 300M (Option B) sans changer de famille.
- **Dettes tracées** : (1) quantification service CPU ; (2) latence de service non mesurée ; (3) clips vides observés au benchmark (audios courts/difficiles) à investiguer si le CER fine-tuné stagne.

## Références

- Benchmark : [0003 protocole](../benchmarks/0003-asr-baoule-evaluation.md) + [0003 résultats](../benchmarks/0003-asr-baoule-evaluation-results.md).
- ADR liés : [ADR-0034](0034-atelier-parite-linguistique.md) (atelier / audio natif) ; [ADR-0035](0035-collecte-dataset-asr-dictee.md) (dataset dictée) ; [ADR-0003](0003-plan-ajout-omnilingual.md) (ajout Omnilingual) ; [ADR-0002](0002-ajout-provider-omnilingual.md).

## Historique
- 2026-08-27 — **proposé** (Option A), sur la base du benchmark 0003 exécuté le jour même.
- 2026-08-27 — **accepté** (Option A — Omnilingual 1B) par Issouf. Le 300M reste le fallback tracé si la latence de service CPU l'impose.
- 2026-08-27 — **dé-risquage fine-tune** ([étude 0004](../benchmarks/0004-omnilingual-finetune-feasibility.md)) : le fine-tune COMPLET du 1B exige un gros GPU (32-96 GPU chez Meta ; ~14-16 Go rien qu'en poids+Adam → hors T4 gratuit). Voies gratuites : **300M complet** ou **1B encodeur gelé** (`freeze_encoder_for_n_steps`) ; 1B complet = A100 payant. N'annule pas le choix (1B = meilleure base mesurée) ; le maillon ③ tranchera A/B/C selon budget + qualité visée.
