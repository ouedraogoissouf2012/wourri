# ADR-0003 — Plan d'ajout d'Omnilingual à la chain ASR

**Statut** : proposé (attend validation Ruben)
**Date** : 2026-04-22 (révisé après exploration réelle)
**Auteur** : Claude (assistant)
**Valideur** : Ruben
**Exécute** : [ADR-0002](0002-ajout-provider-omnilingual.md)
**Remplace** : version initiale "Plan migration ASR → Omnilingual" (mal cadrée)

---

## Contexte

[ADR-0002](0002-ajout-provider-omnilingual.md) ne demande pas une migration, mais un **ajout d'un nouveau provider** à la chain ASR existante. Ce plan est donc plus léger que la version initiale.

Objectif : ajouter `OmnilingualProvider` à la chain `app/services/asr/` en respectant l'interface `ASRProvider` existante, sans régression, avec benchmark empirique pour déterminer son rang dans la chain.

---

## Principes directeurs

1. **Zéro refonte** : on ajoute, on ne remplace pas. L'architecture existante est saine.
2. **Zéro régression** : NeMo et MMS-dyu restent opérationnels à chaque instant.
3. **Mesurer avant de placer en tête** : le rang d'Omnilingual dans la chain est déterminé par benchmark, pas supposé.
4. **Une phase = un livrable + un critère de sortie**.
5. **Isolation branche** : tout le travail sur `feat/omnilingual-asr-provider` (à créer depuis la branche courante `fix/94-asr-improvements-colab` ou depuis main selon choix Ruben).

---

## Phase 1 — Stabilisation environnement + smoke test Colab (2-4 jours)

### Objectif

Obtenir Omnilingual ASR 300M qui charge et transcrit 1 audio sans crash, reproductiblement, dans un environnement Colab versionné.

### Tâches

1. Création branche `feat/omnilingual-asr-provider` dans `wouri-api/.git`
2. Notebook `wouri-api/finetune/colab/omnilingual_smoke_test.ipynb`
   - Cellules versionnées : install omnilingual-asr + fairseq2 → vérifier versions → charger modèle 300M → transcrire 1 MP3 Common Voice dyu → afficher output
3. Documentation install reproductible dans `docs/benchmarks/0002-omnilingual-env-setup.md` (version Python, PyTorch, fairseq2, résolution issue #61 si applicable)

### Critère de sortie

- [ ] Notebook exécute complètement sans crash sur Colab T4
- [ ] Omnilingual 300M charge en < 60 s
- [ ] 1 audio dioula est transcrit (output non vide)
- [ ] Doc install reproduit par Ruben sur une 2ème session Colab

**Si échec** : ré-ouverture ADR-0002, basculer sur Plan B (Djelia).

---

## Phase 2 — Création `omnilingual_provider.py` (2-3 jours)

### Objectif

Implémenter un `OmnilingualProvider` respectant strictement l'interface `ASRProvider`, testable en isolation, prêt à être injecté dans la chain.

### Tâches

1. Création `wouri-api/app/services/asr/omnilingual_provider.py`
   - Hérite de `ASRProvider` ([base.py](../../wouri-api/app/services/asr/base.py))
   - Méthodes : `name`, `is_available`, `transcribe(audio_bytes, file_extension)`
   - Singleton pattern cohérent avec `nemo_provider.py` / `mms_dyu_provider.py`
   - Chargement lazy du modèle (au premier appel)
   - Langue paramétrable par constructeur (`dyu_Latn` par défaut, extensible vers `bam`, `bci`, etc.)
   - Gestion graceful si fairseq2 non installé → `is_available()` retourne False
2. Tests unitaires `wouri-api/tests/unit/test_omnilingual_provider.py`
   - Test `is_available()` retourne True/False selon env
   - Test `name` retourne la bonne valeur
   - Test `transcribe()` sur un mock audio retourne un string non vide
   - Tests d'erreurs (audio invalide, modèle non chargé)
3. Ajout dépendances dans `wouri-api/requirements.txt`
4. Ajout settings dans `wouri-api/app/config.py` :
   - `omnilingual_enabled: bool = False` (feature flag par défaut off)
   - `omnilingual_model_size: Literal["300m", "1b"] = "300m"`
   - `omnilingual_default_lang: str = "dyu_Latn"`

### Critère de sortie

- [ ] Tests unitaires passent (`pytest tests/unit/test_omnilingual_provider.py`)
- [ ] `python -c "from app.services.asr.omnilingual_provider import OmnilingualASR; p = OmnilingualASR(); print(p.is_available())"` retourne True
- [ ] Aucune régression sur tests existants ASR (`pytest tests/unit/test_asr_*.py`)

---

## Phase 3 — Benchmark empirique vs chain actuelle (2-3 jours)

### Objectif

Mesurer la performance d'Omnilingual face à NeMo Soloni et MMS-dyu sur des audios Wourri réels, pour décider de son rang dans la chain.

### Tâches

1. Mise à jour du protocole [docs/benchmarks/0001-asr-dioula-evaluation.md](../benchmarks/0001-asr-dioula-evaluation.md) :
   - Scope réduit : Omnilingual 300M + 1B vs NeMo Soloni (baseline) vs MMS-dyu adapter (baseline 2)
   - Retrait de Djelia / Soloba (utiles seulement si Omnilingual FAIL)
2. Constitution du corpus de test par Ruben :
   - 10-15 vocaux WhatsApp réels dioula CI (cas nominal + cas hallucination NeMo)
   - 5 clips Common Voice dyu v24
   - Transcriptions de référence (ground truth)
3. Notebook `wouri-api/finetune/colab/omnilingual_benchmark.ipynb` : exécute les 4 modèles sur les mêmes 15-20 audios, mesure WER, CER, RAM, RTF
4. Évaluation humaine (Ruben) sur 3 axes : intelligibilité, fidélité, utilisabilité NLU
5. Rapport `docs/benchmarks/0001-asr-dioula-evaluation-results.md`

### Critère de décision (détermine le rang dans la chain)

- **Omnilingual meilleur que NeMo de ≥ 10 points WER** → Omnilingual en rang 1 (tête de chain)
- **Omnilingual proche de NeMo (±5 points)** → Omnilingual en rang 2, NeMo en rang 1 (inertie, moins de risque)
- **Omnilingual dégrade vs NeMo** → Omnilingual en rang 3-4 (utilisé seulement en dernier recours)
- **Omnilingual échoue (crashes, WER > 70%)** → non inséré, ré-ouverture ADR-0002

---

## Phase 4 — Insertion dans la chain (1 jour)

### Objectif

Intégrer le provider dans la chain ASR en production sans régression.

### Tâches

1. Modification `wouri-api/app/services/asr/__init__.py` :
   - Import `OmnilingualASR`
   - Insertion dans la liste `providers=[...]` au rang décidé en Phase 3
   - `agri_fallback` inchangé (reste MMS-dyu)
2. Test d'intégration pipeline end-to-end :
   - Pipeline WhatsApp voice → ASR (chain) → NLU → IVR → TTS
   - Vérifier qu'aucune fonctionnalité existante ne régresse
   - Mesurer latence totale end-to-end
3. Activation progressive via feature flag `omnilingual_enabled` dans config :
   - `false` par défaut (chain sans Omnilingual = état actuel)
   - `true` après validation Ruben sur env de dev

### Critère de sortie

- [ ] Pipeline end-to-end fonctionne avec Omnilingual activé
- [ ] Tous les tests existants passent (`pytest tests/`)
- [ ] Latence end-to-end ≤ baseline actuelle + 20%
- [ ] Feature flag permet le rollback instantané

---

## Phase 5 — Nettoyage `asr_quality/` (1 jour)

### Objectif

Supprimer le code mort identifié dans ADR-0002 (dupliquait le normalizer existant).

### Tâches (uniquement après Phase 4 stable ≥ 3 jours)

1. Suppression de :
   - `wouri-api/app/services/asr_quality/` (lexicon.py, models.py, __init__.py)
   - `wouri-api/data/asr_hallucinations_dyu.json`
   - `wouri-api/tests/unit/test_asr_quality_lexicon.py`
   - `wouri-api/tests/unit/test_asr_quality_models.py`
   - Settings `asr_vocab_sources`, `asr_hallucinations_path`, `asr_language` dans `app/config.py` (si ajoutés)
2. Grep confirmation : aucune référence résiduelle à `asr_quality`
3. Tests complets : `pytest tests/`

### Critère de sortie

- [ ] `grep -r "asr_quality" wouri-api/` retourne zéro résultat (hors docs historiques)
- [ ] Tous les tests passent
- [ ] Pipeline reste opérationnel

---

## Risques et mitigations

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| Fairseq2 install casse (issue #61) | Moyenne | Haut | Time-box Phase 1 à 5 j ; escalade Plan B Djelia si FAIL |
| Omnilingual WER > 50% sur dioula | Faible-Moyenne | Moyen | Rang final adapté en chain (pas forcément tête) |
| Régression pipeline en Phase 4 | Faible | Haut | Feature flag `omnilingual_enabled=false` par défaut ; rollback instantané |
| Tests unitaires impossibles sans GPU | Moyenne | Faible | Mocks pour les tests unitaires ; tests d'intégration uniquement avec GPU |
| Conflit deps Python (fairseq2 vs nemo, torch versions) | Moyenne | Moyen | Test pré-install en worktree isolé avant de modifier `requirements.txt` principal |

---

## Rollback

- **Phase 2** : provider créé mais non intégré → rollback = delete du fichier + revert requirements
- **Phase 4** : provider intégré → rollback = flip `omnilingual_enabled=false` OU retirer la ligne dans la chain
- **Phase 5** : code mort supprimé → rollback via `git revert`

**Point de non-retour** : Phase 5 terminée + 2 semaines de prod stable. Avant cela, tout est réversible.

---

## Livrables

- [ ] `wouri-api/finetune/colab/omnilingual_smoke_test.ipynb` (Phase 1)
- [ ] `docs/benchmarks/0002-omnilingual-env-setup.md` (Phase 1)
- [ ] `wouri-api/app/services/asr/omnilingual_provider.py` (Phase 2)
- [ ] `wouri-api/tests/unit/test_omnilingual_provider.py` (Phase 2)
- [ ] Update `wouri-api/requirements.txt` (Phase 2)
- [ ] Update `wouri-api/app/config.py` (Phase 2)
- [ ] `wouri-api/finetune/colab/omnilingual_benchmark.ipynb` (Phase 3)
- [ ] `data/benchmarks/asr_dioula_eval_v1.jsonl` (Phase 3)
- [ ] `docs/benchmarks/0001-asr-dioula-evaluation-results.md` (Phase 3)
- [ ] Update `wouri-api/app/services/asr/__init__.py` (Phase 4)
- [ ] Suppression `wouri-api/app/services/asr_quality/` (Phase 5)
- [ ] ADR-0003 statut `complété`

---

## Estimation totale

- **Optimiste** (toolchain OK, WER bon) : 8-10 jours calendaires
- **Réaliste** : 12-15 jours
- **Pessimiste** (toolchain bloque Phase 1, fine-tune nécessaire) : 20-25 jours → escalade Plan B

---

## Hors scope de cet ADR

- Fine-tuning Omnilingual sur dioula CI → ADR futur si benchmark Phase 3 le justifie
- Ajout baoulé/bété/agni → ADR-0004 futur (P2)
- Question licence MMS-dyu (CC-BY-NC vs produit payant) → ADR séparé
- Migration ChromaDB → pgvector ([ADR-0001 accepté](0001-choix-stockage-donnees.md)) → ADR de plan dédié après la migration ASR

---

## Historique

- **2026-04-22 (première rédaction)** : plan de migration complète avec feature flag + phases lourdes. Cadrage incorrect.
- **2026-04-22 (révision)** : après exploration réelle du projet, reconnaissance de l'architecture multi-provider existante. Plan recadré en "ajout de provider". Phases allégées, suppression de la notion de "migration complète". Statut proposé, attend validation Ruben.
