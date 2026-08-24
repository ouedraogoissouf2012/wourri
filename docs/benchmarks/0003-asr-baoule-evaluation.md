# Benchmark #0003 — Évaluation ASR baoulé (bci)

**Statut** : proposé, en attente de validation avant exécution
**Date de rédaction** : 2026-08-24
**Décision qu'il informe** : futur ADR « choix du modèle ASR baoulé » (epic #472, issue #473)
**Fondations** : setup validé [benchmark 0002](0002-omnilingual-env-setup.md) · méthodologie [benchmark 0001](0001-asr-dioula-evaluation.md) · [ADR-0002](../adr/0002-ajout-provider-omnilingual.md)

---

## 1. Objectif

Mesurer empiriquement, sur du **vrai baoulé**, la qualité de transcription de modèles ASR candidats — pour répondre à : **un ASR comprend-il le baoulé aujourd'hui, et lequel prendre comme base de fine-tuning ?** Décider sur chiffres, pas sur annonces.

Ce benchmark est de l'**investigation** : il produit les données ; la **décision** d'adoption fera l'objet d'un ADR (règle projet). Il ne touche à **aucun code de production**, aucun fichier gelé.

---

## 2. Modèles testés

| # | Modèle | Params | Ciblage baoulé | Licence | Model card / source |
|---|---|---|---|---|---|
| M1 | Omnilingual ASR CTC 300M | 300M | **`bci_Latn` explicite** | Apache-2.0 | `omniASR_CTC_300M` |
| M2 | Omnilingual ASR CTC 1B | 1B | **`bci_Latn` explicite** | Apache-2.0 | `omniASR_CTC_1B` |
| M3 | Simba-S (UBC-NLP) | 2.3B | ⚠️ **aucun** (voir note) | CC-BY-4.0 | `UBC-NLP/Simba-S` |

**Note M1/M2 (Omnilingual)** : API validée en [0002 §7](0002-omnilingual-env-setup.md). `bci_Latn` ∈ `supported_langs` (vérifié). Ciblage de langue **explicite** à l'inférence (`lang=["bci_Latn"]`).

**Note M3 (Simba-S) — vérifié 2026-08-24 (fichiers réels du dépôt)** : le modèle s'invoque via `pipeline('automatic-speech-recognition', 'UBC-NLP/Simba-S')` (architecture `SeamlessM4Tv2ForSpeechToText`), **mais** son tokenizer SeamlessM4T standard **ne contient aucun token de langue baoulé** (`__bau__`/`__bci__` absents de `special_tokens_map.json` ; défaut `__fra__`). Il n'existe **aucun moyen documenté de cibler le baoulé**, et `generate(tgt_lang='bau'/'bci')` lèverait une `KeyError`. **Risque réel : sortie en français.** → M3 est testé **avec un garde-fou « langue de sortie »** (§4.2) ; s'il transcrit du français, il est **écarté** pour le baoulé (ce qui confirmerait la recherche : support baoulé de Simba non substantié).

**Omnilingual LLM 7B écarté** : nécessite A100 (hors T4 gratuit). Réévaluer si M1/M2 insuffisants.

---

## 3. Dataset d'évaluation

**Source — vérifié 2026-08-24** : Mozilla a retiré Common Voice de Hugging Face (oct. 2025). `mozilla-foundation/common_voice_*` config `bci` **n'existe plus** sur HF. On utilise le **miroir tiers public** :

- **`Klayt/baoule-common-voice`** (CC0, **non gated → aucun token HF requis**, parquet, **audio déjà 16 kHz mono**).
- Splits officiels : train 319 / dev 267 / **test 290** = 876 clips. Colonnes : `audio` (16 kHz), `sentence` (référence), `path`, `locale`, `client_id`.
- **Set d'évaluation = le split `test` (290 clips)** ; référence = `sentence`.
- **Révision épinglée** (dépôt tiers, peut évoluer) : `176d5f8ad6c04e5ca1a0e66770866709bcbb338b`.

**Limite assumée** : ce miroir ne contient que 876 clips (**pas** le bucket `validated` ~11 h du corpus officiel). Suffisant pour un **benchmark comparatif** ; le fine-tuning (#474) puisera dans le corpus complet (Mozilla Data Collective, compte requis).

---

## 4. Métriques

### 4.1 Quantitatives
- **CER** (Character Error Rate) — **métrique principale** (langue peu écrite, orthographe variable → le CER est plus juste que le WER).
- **WER** (Word Error Rate) — secondaire.
- Calcul via `jiwer` (`wer(reference, hypothesis)` / `cer(...)`). **Normalisation tolérante** : NFC + minuscules + ponctuation ASCII retirée + espaces réduits. **Les caractères propres au baoulé (ɛ, ɔ, ʼ, tons) sont CONSERVÉS** — ils portent le sens (langue tonale) ; les retirer fausserait la mesure.
- **RTF** (temps d'inférence / durée audio) · **temps de chargement** du modèle.

### 4.2 Garde-fou « langue de sortie » (spécifique M3)
Pour Simba, un échantillon de sorties est inspecté : si les transcriptions ressemblent au **français** (mots-outils français fréquents : `le, la, les, de, et, un, une, est…`) plutôt qu'au baoulé, M3 est marqué **inexploitable pour le baoulé**, indépendamment de son CER.

### 4.3 Qualitatif
Pour ~10 clips : afficher `référence | M1 | M2 | M3` côte à côte (un francophone repère immédiatement si Simba sort du français).

---

## 5. Lecture des résultats (seuils indicatifs, fixés a priori)

Le baoulé est **bas-ressource** ; en zero-shot on attend un CER élevé. Ces seuils orientent la **base de fine-tuning**, pas un go/no-go produit :

| CER (meilleur modèle) | Lecture |
|---|---|
| < 15 % | Exploitable quasi tel quel (peu probable en zero-shot) |
| 15–40 % | **Base de fine-tuning viable** (#474) — cas attendu |
| 40–60 % | Fine-tuning lourd ; réévaluer volume/qualité des données |
| > 60 % | Modèle inadapté au baoulé |

Le **modèle au plus faible CER parmi ceux qui produisent réellement du baoulé** devient la **base recommandée** pour l'ADR de fine-tuning.

---

## 6. Procédure

- **Environnement** : Google Colab **T4** (gratuit), notebook `finetune/colab/asr_baoule_benchmark.ipynb`.
- **Aucun token HF requis** (dataset Klayt public).
- Setup Omnilingual : reprend le [benchmark 0002](0002-omnilingual-env-setup.md) (versions figées `torch==2.8.0`/`fairseq2` + **restart de session obligatoire**).
- ⚠️ **Conflit de stacks possible** : Omnilingual force `torch==2.8.0`/`fairseq2` ; Simba utilise `transformers`. Le notebook exécute **Omnilingual d'abord** et **sauvegarde ses résultats sur disque**, **puis** Simba ; en cas de conflit, Simba se relance dans un **runtime neuf** (résultats Omnilingual déjà sauvés).
- Durée estimée : ~30–45 min.

---

## 7. Livrables

- `finetune/colab/asr_baoule_benchmark.ipynb` — notebook reproductible (ce livrable).
- `asr_baoule_results.json` — résultats bruts (généré sur Colab, `/content`).
- `docs/benchmarks/0003-asr-baoule-evaluation-results.md` — rapport final (tableau CER/WER + verdict).
- Sur cette base : **ADR « choix du modèle ASR baoulé »** (dont dépend #474).

---

## 8. Hors périmètre

- **Fine-tuning** → issue #474 (ADR séparé). **NLU / TTS** → #475 / #476.
- **Intégration au moteur** → après l'ADR.
- **Décision définitive** → l'ADR, pas ce benchmark (0001 §9 : « le benchmark produit les données, l'ADR produit la décision »).

---

## 9. Validation avant exécution

- [ ] Modèles M1–M3 acceptés (Omnilingual 300M/1B + Simba-S en contrôle).
- [ ] Dataset Klayt (876 clips, split `test`) accepté comme set d'évaluation de départ.
- [ ] CER métrique principale + diacritiques baoulé conservés : OK.
- [ ] Budget Colab (~30–45 min T4) acceptable.

**Après validation → exécution du notebook sur Colab, puis rédaction du rapport `0003-...-results.md`.**

---

## Historique
- **2026-08-24** : rédaction. Fondée sur la vérification web des API (Simba-S sans ciblage baoulé — tokenizer sans token `bci` ; Common Voice `bci` retiré de HF → miroir `Klayt/baoule-common-voice` ; Omnilingual `bci_Latn` validé en 0002).
