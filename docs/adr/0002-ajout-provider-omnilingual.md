# ADR-0002 — Ajout d'un provider Omnilingual ASR en tête de chain

**Statut** : accepté
**Date** : 2026-04-22 (révisé après exploration réelle du projet)
**Auteur** : Claude (assistant) + deux recherches sourcées
**Valideur** : Ruben (validé le 2026-04-22)
**Remplace** : la version initiale "Remplacement ASR → Omnilingual" (mal cadrée, ignorait l'architecture existante)

---

## Contexte

### Architecture ASR existante (découverte par exploration du projet, pas initiale)

Le projet dispose déjà d'une **architecture multi-provider modulaire**, pas d'un modèle monolithique :

```
wouri-api/app/services/asr/
├── base.py              # Interface ASRProvider (Liskov)
├── chain.py             # ASRChain avec fallback automatique
├── nemo_provider.py     # NeMo Soloni (bambara Mali)
├── mms_dyu_provider.py  # MMS-dyu adapter fine-tuné (dioula CI)
├── mms_generic_provider.py  # MMS 8 langues (fallback)
└── audio_utils.py
```

Chain actuelle ([app/services/asr/__init__.py](../../wouri-api/app/services/asr/__init__.py)) :
1. NeMo Soloni (TDT)
2. MMS-dyu adapter (fine-tuné AXE-4 sur 295 clips Common Voice dyu v24)
3. MMS-generic (fallback universel)
4. + `agri_fallback=MMS-dyu` si aucun mot-clé agricole détecté par NeMo

**L'architecture est ouverte à l'extension** (principe Open/Closed) : ajouter un provider = le créer et l'ajouter dans la chain, sans modifier la logique.

### Problème persistant malgré cette architecture

Les deux providers spécialisés (NeMo Soloni bambara Mali, MMS-dyu adapter) **ne couvrent pas nativement** :
- Dioula CI → MMS-dyu est fine-tuné dessus mais la licence MMS base est **CC-BY-NC-4.0** (incompatible produit payant). NeMo hallucine.
- **Baoulé, bété, agni** → aucun provider ne les couvre. Pas d'extension possible sans nouveau modèle.

### Ce que le projet demande ([docs/vision.md](../vision.md))

- 50+ langues africaines à horizon 2-5 ans
- Phasage : P1 dioula CI → P2 +baoulé/bété/agni → P5 50+
- Modèle commercial payant → **licence permissive obligatoire**

### Ce qui manque à la chain

**Un provider de fondation multilingue couvrant nativement les langues cibles, sous licence commerciale.**

---

## Options étudiées

### Option A — Ajouter OmnilingualProvider en tête de chain (retenue)

- Meta Omnilingual ASR (nov 2025, Apache 2.0) — couvre 1 672 langues dont `dyu_Latn` (CER 6,5% auto-reporté), `bam_Latn` (1,0%), `bci_Latn`/baoulé (10,7%), `ann_Latn` (proche agni, 3,1%)
- **`bet_Latn`/bété absent** → géré par zero-shot in-context ou fine-tune custom futur
- S'insère comme nouveau provider **sans toucher aux existants**
- Chaîne cible : `[Omnilingual, NeMo, MMS-dyu, MMS-generic]` avec rang final déterminé par benchmark
- Risque infrastructure : toolchain fairseq2 instable ([issue #61](https://github.com/facebookresearch/omnilingual-asr/issues/61) ouverte depuis déc 2025)

### Option B — Rester sur NeMo + MMS-dyu (rejetée)

- NeMo hallucine sur dioula CI (problème de fond non résolu)
- MMS-dyu fine-tuné adapter hérite de la licence **CC-BY-NC** du modèle base → **bloquant pour produit payant**
- Ne scale pas aux langues hors Manding (baoulé, bété, agni impossibles)

### Option C — Whisper fine-tuné (rejetée)

- Licence MIT OK
- Hallucinations >100% WER documentées sur bambara ([arXiv 2602.09785](https://arxiv.org/html/2602.09785))
- Tons mal gérés (critique pour dioula, baoulé)

### Option D — Djelia asr-v2 / RobotsMali Soloba (rejetée comme principal, retenue comme Plan B)

- Apache 2.0, bambara uniquement (WER 47%)
- Ne couvre pas baoulé/bété/agni
- **Retenue comme fallback** si Omnilingual s'avère inexploitable

---

## Décision

**Ajouter un nouveau provider `OmnilingualProvider` à la chain ASR existante**, placé en rang à déterminer par benchmark empirique.

**Variante par défaut** : **Omnilingual CTC 1B** (licence Apache 2.0, ~5 GiB VRAM, viable VPS startup avec GPU T4).

**Ne sont PAS remplacés** :
- `nemo_provider.py` (gardé pour bambara Mali + fallback)
- `mms_dyu_provider.py` (gardé tant que l'aspect licence commerciale n'est pas tranché — ADR futur dédié)
- `mms_generic_provider.py` (fallback multi-langues)
- `asr_normalizer.py` (normalisation post-ASR, utile pour tout provider)
- Chain, base, dictionnaires, routeur ASR

**Est supprimé** :
- `app/services/asr_quality/` (lexicon.py, models.py) + `data/asr_hallucinations_dyu.json` + tests associés
  → dupliquent les étapes 1-4 du normalizer existant. Code mort résolvant le mauvais problème.

**Justification** :

1. **Respecte l'architecture existante** (chain de providers avec interface ASRProvider). Pas de refonte.
2. **Couverture native des langues cibles** dyu, bam, bci, ann sous licence Apache 2.0 compatible produit payant.
3. **Scale** naturellement vers baoulé (présent), agni (ann proche), puis bété (par fine-tune ou zero-shot).
4. **Fallback robuste** : si Omnilingual est indisponible/échec, la chain continue sur NeMo puis MMS-dyu. Aucune régression possible.
5. **Rollback trivial** : retirer une ligne dans `app/services/asr/__init__.py`.

---

## Conséquences

### Positives

- Nouveau provider = nouvelle capacité sans toucher à l'existant
- Chaîne de fallback renforcée (4 providers au lieu de 3)
- Compatible audacity commerciale (Apache 2.0 sur code + modèles)
- Préparé pour P2 (baoulé, bété, agni) sans refonte architecturale
- Suppression de code mort (`asr_quality/`)

### Négatives assumées

- **Toolchain fairseq2 instable** (issue #61) : 20-40h sysadmin à prévoir pour stabiliser install/inference
- **Chiffres Meta non reproduits indépendamment** : benchmark empirique sur audios Wourri obligatoire avant de placer Omnilingual en tête de chain
- **bété absent** : géré séparément en P2
- **Compute** : inférence GPU nécessaire. VPS cible doit disposer d'un GPU (T4 suffit pour 300M/1B)
- **Question licence MMS-dyu non tranchée** : le fine-tuning MMS actuel hérite CC-BY-NC. Si on commercialise sans le régler, risque juridique. À adresser par un ADR séparé (proposition : désactiver mms_dyu_provider quand Omnilingual sera en tête, ou obtenir dérogation Meta)

### Code impacté (scope réel, minimal)

**À créer** (Phase 2 du plan ADR-0003) :
- `wouri-api/app/services/asr/omnilingual_provider.py` (~120-180 lignes, respecte `ASRProvider`)
- `wouri-api/tests/unit/test_omnilingual_provider.py`

**À modifier** :
- `wouri-api/app/services/asr/__init__.py` : ajouter import + instantiation `OmnilingualASR()` dans la chain
- `wouri-api/requirements.txt` : ajouter `omnilingual-asr` (+ dépendances fairseq2)
- `wouri-api/app/config.py` : ajouter settings Omnilingual (chemin modèle, langue par défaut)

**À supprimer** (après validation benchmark Phase 3) :
- `wouri-api/app/services/asr_quality/` (3 fichiers)
- `wouri-api/data/asr_hallucinations_dyu.json`
- `wouri-api/tests/unit/test_asr_quality_lexicon.py`
- `wouri-api/tests/unit/test_asr_quality_models.py`

**Non touché** :
- Toute la chain existante (nemo, mms_dyu, mms_generic)
- `asr_normalizer.py`, `asr_corrections.json`
- Pipeline vocal end-to-end (WhatsApp → ASR → NLU → IVR → TTS)
- Router, config NLU, VDB

---

## Plan d'exécution

Détaillé dans [ADR-0003](0003-plan-ajout-omnilingual.md). Résumé :

1. **Phase 1** (3-5 j) : stabilisation env Omnilingual, smoke test Colab
2. **Phase 2** (2-3 j) : création `omnilingual_provider.py` + tests
3. **Phase 3** (2-3 j) : benchmark empirique sur audios Wourri réels vs NeMo + MMS-dyu → détermine rang dans la chain
4. **Phase 4** (1 j) : insertion dans la chain + tests d'intégration
5. **Phase 5** (1 j) : suppression `asr_quality/` + cleanup

---

## Références

- [GitHub facebookresearch/omnilingual-asr](https://github.com/facebookresearch/omnilingual-asr) — code Apache 2.0, 1672 codes ISO dans lang_ids.py
- [HuggingFace facebook/omniASR-CTC-7B](https://huggingface.co/facebook/omniASR-CTC-7B) — model card
- [arXiv 2511.09690 — Omnilingual ASR](https://arxiv.org/abs/2511.09690) — paper Meta FAIR
- [arXiv 2602.09785 — Benchmark bambara 37 modèles](https://arxiv.org/html/2602.09785) — contexte limites Whisper
- [app/services/asr/__init__.py](../../wouri-api/app/services/asr/__init__.py) — chain actuelle
- [app/services/asr/base.py](../../wouri-api/app/services/asr/base.py) — interface ASRProvider

---

## Historique

- **2026-04-22 (première rédaction)** : cadrée comme "Remplacement NeMo → Omnilingual". Ignorait l'architecture multi-provider existante.
- **2026-04-22 (révision)** : après exploration réelle du projet, recadrée en "Ajout d'un provider à la chain existante". Scope réduit, risque réduit, plan simplifié. Statut accepté par Ruben.
