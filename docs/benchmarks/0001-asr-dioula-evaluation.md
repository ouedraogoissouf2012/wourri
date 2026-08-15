# Benchmark #0001 — Évaluation ASR dioula CI (avril 2026)

**Statut** : proposé, en attente de validation Ruben avant exécution
**Date de rédaction** : 2026-04-22
**Décision qu'il informe** : ADR-0002 (remplacement NeMo Soloni → modèle ASR cible)

---

## 1. Objectif

Mesurer empiriquement, sur des audios dioula CI réels, la performance de 4 modèles ASR
candidats pour remplacer NeMo Soloni (actuel, entraîné bambara Mali, hallucine sur
dioula CI). Décider sur chiffres, pas sur papers.

**Question à trancher** : **quel modèle ASR Wourri adopte pour P1 (dioula CI) ?**

---

## 2. Modèles testés

| # | Modèle | Paramètres | Licence | Source |
|---|---|---|---|---|
| M1 | Omnilingual ASR CTC 300M | 300M | Apache 2.0 | `facebook/omnilingual-asr-ctc-300m` |
| M2 | Omnilingual ASR CTC 1B | 1B | Apache 2.0 | `facebook/omnilingual-asr-ctc-1b` |
| M3 | Omnilingual ASR LLM 1.2B | 1.2B | Apache 2.0 | `facebook/omniasr-llm-1_2b` |
| M4 | Bambara-ASR-v2 (sudoping01 / Djelia MALIBA-AI) | ~1.5B (Whisper-large-v2 fine-tuné) | Apache 2.0 | `sudoping01/bambara-asr-v2` |
| M5 | RobotsMali Soloba-ctc-0.6B-v3 | 0.6B | CC-BY-4.0 | `RobotsMali/soloba-ctc-0.6b-v3` |
| M6 | NeMo Soloni TDT (baseline actuel) | 114M | CC-BY-4.0 | `RobotsMali/soloni-114m-tdt-ctc-v0` |

**Note** : M4 et M5 sont entraînés **bambara Mali**. Inclus comme Plan B et comme base de
comparaison (si Omnilingual n'apporte rien vs un modèle bambara mature, la décision change).

**Omnilingual 7B écarté** : nécessite A100 24 GB → hors budget Colab gratuit. Réévaluer si
M1/M2/M3 donnent des résultats insuffisants.

**Note sur M4 (Bambara-ASR-v2)** : ce modèle présente une capacité de
**code-switching bambara-français natif**, testée et documentée par Djelia/MALIBA-AI.
Critique pour le cas d'usage Wourri où les utilisateurs mélangent fréquemment les
deux langues dans un même vocal. À surveiller particulièrement dans l'évaluation
humaine (métriques Fidélité et Utilisabilité NLU). Source :
[huggingface.co/sudoping01/bambara-asr-v2](https://huggingface.co/sudoping01/bambara-asr-v2).

> **P1-02 (issue #206) — validation Ruben requise.** L'inclusion de M4 dans ce
> benchmark satisfait l'action P1-02 du [PLAN_ACTION_2026-04.md](../PLAN_ACTION_2026-04.md)
> et l'addendum d'[ADR-0003](../adr/0003-plan-ajout-omnilingual.md). Comme tout ce
> protocole (cf. statut en-tête et §10), M4 reste **soumis à la validation de Ruben
> avant exécution** du benchmark.

---

## 3. Dataset d'évaluation

### 3.1 Corpus de test — 20 audios minimum

À constituer par Ruben avant exécution :

**Groupe A — Audios existants du projet (10 minimum)** :
- Vocaux WhatsApp réels envoyés au bot (issues récentes ou logs `debug_audio/`)
- Transcription de référence (ground truth) rédigée à la main par Ruben, en dioula CI correct
- Inclure explicitement des cas où NeMo actuel hallucine (kakawo → ka ka aw, kafe → kafitinin, etc.)

**Groupe B — Common Voice dyu v24 (5 clips)** :
- 5 MP3 tirés au hasard de `cv-corpus-24.0-2025-12-05-dyu/clips/`
- Transcription déjà fournie par Common Voice (TSV `validated.tsv`)

**Groupe C — Test 8 kHz simulé (5 audios)** :
- 5 audios du Groupe A ré-échantillonnés à 8 kHz (via `sox` ou `librosa`)
- Préfigure le canal IVR téléphonique futur

### 3.2 Format référence

Fichier `data/benchmarks/asr_dioula_eval_v1.jsonl` (un audio par ligne) :

```json
{"id": "wa_001", "audio_path": "data/benchmarks/audio/wa_001.wav", "groupe": "A",
 "reference": "n bɛ fɛ ka kakawo sɛnɛ", "hallucinations_attendues": ["ka ka aw"],
 "sample_rate": 16000}
```

---

## 4. Métriques

### 4.1 Métriques quantitatives (automatiques)

- **WER (Word Error Rate)** — métrique principale, calculée via `jiwer`
- **CER (Character Error Rate)** — secondaire, plus tolérante aux diacritiques (ɛ, ɔ, ɲ)
- **RAM peak** (GB) — mesuré via `psutil` pendant l'inférence
- **Latence RTF** (Real-Time Factor) — durée inférence / durée audio
- **Temps de chargement initial** (cold start, secondes)
- **Temps total d'installation** (modèle + dépendances, minutes)

### 4.2 Métriques qualitatives (humaines, Ruben)

Pour chaque transcription produite, noter sur échelle 1-5 :

- **Intelligibilité** (un locuteur dioula comprendrait-il ?) : 1=absurde, 5=parfait
- **Fidélité** (est-ce bien ce que dit l'audio ?) : 1=hallucination totale, 5=exact
- **Utilisabilité NLU** (les concepts agricoles sont-ils reconnaissables ?) : 1=non, 5=oui

### 4.3 Métriques de robustesse

- **Taux d'hallucinations** : nombre de transcriptions contenant une hallucination manifeste, sur les 20 audios
- **Dégradation 8 kHz vs 16 kHz** : delta WER entre Groupe A audios 16 kHz et leurs versions 8 kHz

---

## 5. Critères de décision a priori

Ces seuils sont **fixés maintenant**, avant de voir les résultats. Aucune renégociation
après mesure pour éviter le biais de confirmation.

### 5.1 Critères PASS (modèle adoptable en P1)

Un modèle passe si **TOUS** ces critères sont remplis :

- WER moyen Groupe A ≤ **30 %**
- 0 ou 1 hallucination grossière sur les 20 audios
- RAM peak ≤ **10 GB** (compatible VPS startup raisonnable)
- Latence RTF ≤ **0.5** sur CPU ou ≤ **0.1** sur GPU T4
- Installation réussie en < 4 h de travail sysadmin
- Licence compatible usage commercial payant

### 5.2 Critères CONDITIONAL (adoptable après fine-tuning)

Si un modèle a :
- WER 30-50 %
- Hallucinations 2-4 sur 20
- Autres critères PASS

→ candidat fine-tune sur corpus dyu CI à constituer. Acceptable si meilleur par ≥ 10 points
WER que la baseline NeMo Soloni actuelle.

### 5.3 Critères FAIL (rejeté)

- WER > 50 %, OU
- > 4 hallucinations sur 20, OU
- Installation impossible après 4 h, OU
- Licence non-commerciale, OU
- RAM > 16 GB en inférence

---

## 6. Procédure d'exécution

### 6.1 Environnement

- **Primary** : Google Colab (T4 gratuit, accès GPU indispensable pour M1/M2/M3/M4)
- **Secondary** : Colab Pro (A100) uniquement si M2 ou M3 saturent le T4
- **Notebook unique** : `finetune/colab/asr_benchmark_v1.ipynb`

### 6.2 Étapes

1. **Préparation** (Ruben, ~2 h)
   - Constituer le corpus de test (20 audios + transcriptions)
   - Uploader sur HuggingFace Datasets privé OU Google Drive dédié
   - Générer le fichier `asr_dioula_eval_v1.jsonl`

2. **Benchmark par modèle** (Colab, ~30 min par modèle, 6 modèles = 3 h)
   - Charger le modèle
   - Transcrire les 20 audios
   - Mesurer WER/CER/RAM/latence
   - Sauvegarder résultats dans `benchmark_results_<model_id>.json`

3. **Évaluation humaine** (Ruben, ~1 h)
   - Lire chaque transcription, noter les 3 métriques qualitatives 1-5
   - Enregistrer dans `benchmark_human_eval.csv`

4. **Consolidation** (Claude + Ruben, ~1 h)
   - Générer rapport final markdown avec tables comparatives
   - Décision PASS / CONDITIONAL / FAIL pour chaque modèle
   - Recommandation finale avec chiffres à l'appui

**Durée totale estimée** : 1-2 jours calendaires (surtout limité par préparation corpus + évaluation humaine).

### 6.3 Livrables

- `data/benchmarks/asr_dioula_eval_v1.jsonl` — dataset référence versionné
- `data/benchmarks/audio/*.wav` — audios de test (hors git, trop gros ; upload Google Drive)
- `finetune/colab/asr_benchmark_v1.ipynb` — notebook d'exécution reproductible
- `data/benchmarks/results/benchmark_results_<model>.json` — résultats bruts par modèle
- `data/benchmarks/results/benchmark_human_eval.csv` — scores humains
- `docs/benchmarks/0001-asr-dioula-evaluation-results.md` — rapport final synthétique
- Sur la base de ce rapport : **ADR-0002 rédigé** avec décision tranchée

---

## 7. Tableau de synthèse attendu (template)

À remplir à l'issue du benchmark :

| Modèle | WER A | WER B | WER C (8kHz) | Hallu | RAM | RTF | Humain moy. | Verdict |
|---|---|---|---|---|---|---|---|---|
| M1 Omnilingual 300M | ? | ? | ? | ? | ? | ? | ? | ? |
| M2 Omnilingual 1B | ? | ? | ? | ? | ? | ? | ? | ? |
| M3 Omnilingual LLM 1.2B | ? | ? | ? | ? | ? | ? | ? | ? |
| M4 Bambara-ASR-v2 (sudoping01) | ? | ? | ? | ? | ? | ? | ? | ? |
| M5 RobotsMali Soloba v3 | ? | ? | ? | ? | ? | ? | ? | ? |
| M6 NeMo Soloni (baseline) | ? | ? | ? | ? | ? | ? | ? | ? |

---

## 8. Risques et mitigations

- **Fairseq2 install cassé** (issue #61 Omnilingual ouverte depuis déc 2025)
  → Mitigation : si install échoue après 4 h, marquer FAIL install et passer au modèle suivant
- **Corpus trop petit (20 audios)** pour significativité statistique
  → Accepté comme première évaluation. Si un modèle est clairement gagnant, confirmé.
  Si résultats ambigus, élargir à 50-100 audios en phase 2.
- **Biais transcription référence**
  → Ruben transcrit en dioula CI "correct", pas phonétique. Cohérent avec l'usage produit.
- **Pas de GPU Colab disponible**
  → M1 (300M) tourne sur CPU Colab en ~2-3x temps réel, acceptable. Autres reportés.
- **Licence models cards modifiée** entre rédaction et exécution
  → Re-vérifier licence au moment du `transformers.from_pretrained()`
- **Résultats inconcluants** (aucun modèle ne PASS)
  → Déclencher un second ADR sur stratégie alternative : fine-tuning Whisper-large-v3 sur
  corpus dyu ou achat accès Intron Sahara v2. Ne pas forcer une décision sur données faibles.

---

## 9. Zones hors périmètre (NE PAS faire dans ce benchmark)

- **Fine-tuning** — c'est un benchmark zero-shot. Le fine-tuning fait l'objet d'un ADR séparé
- **TTS** — pas concerné
- **Intégration au pipeline Wourri** — on ne touche pas au code production
- **Décision architecturale définitive** — le benchmark produit les données, l'ADR-0002 produit la décision

---

## 10. Validation avant exécution

Avant de créer le notebook et de lancer le benchmark, Ruben valide :

- [ ] La liste de modèles est complète (M1 à M6)
- [ ] Les critères PASS / CONDITIONAL / FAIL sont acceptables
- [ ] Les 3 groupes d'audios A/B/C couvrent les cas importants
- [ ] Les métriques qualitatives 1-5 sont claires
- [ ] Le budget temps (~1-2 jours) est acceptable
- [ ] Il a les audios de test disponibles ou peut les constituer

**Si l'un de ces points pose problème → ajustement du protocole avant exécution.**

---

**Prochaine action après validation** : création du notebook Colab `asr_benchmark_v1.ipynb`.
