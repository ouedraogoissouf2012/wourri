# ADR-0004 — Intégration corpus AfVoices / African Next Voices avec stratégie multi-variantes Manding

**Statut** : proposé (en attente validation Ruben)
**Date** : 2026-04-23
**Auteur** : Claude (assistant)
**Valideur** : Ruben
**Issue source** : [#96](https://github.com/ouedraogoissouf2012/wourri/issues/96) — [P1-01] du [PLAN_ACTION_2026-04.md](../PLAN_ACTION_2026-04.md)
**ADRs liés** : [ADR-0002](0002-ajout-provider-omnilingual.md) (Omnilingual ASR), [ADR-0003](0003-plan-ajout-omnilingual.md) (plan ajout Omnilingual), [ADR-0005](0005-afrolid-language-detection.md) (AfroLID)

---

## Contexte

### Découverte critique du 2026-04-22

L'exploration du projet a identifié **deux corpus bambara majeurs publiés fin 2025**, **non intégrés** au pipeline Wourri :

- **AfVoices** (RobotsMali, partie bambara du programme African Next Voices Gates Foundation) — **423h segmentées + 612h brutes** de bambara spontané, focus Sud Mali
- **African Next Voices (ANV)** programme Gates Foundation — corpus distribués langue par langue via partenaires (RobotsMali pour bambara → AfVoices)

Le pipeline de fine-tune actuel (`finetune/prepare_dioula_dataset.py`) exploite **5 sources** mais **PAS** AfVoices/ANV :
- `bayelemabaga` (42k paires texte bambara-français)
- `jeli_asr_bam.txt` (67k phrases bambara orales)
- `corpus_ivr.json` (162 réponses bambara agricoles)
- `findora_fr_dioula.json` (20k paires biblique)
- `cv-corpus-24.0-2025-12-05-dyu` (5028 phrases dioula CI)

**AfVoices apporte 5× plus de données que tout l'existant cumulé** + **423h d'audio réel vs presque rien actuellement**.

### Contrainte cruciale identifiée par Ruben (2026-04-23)

Wourri vise **toute l'Afrique francophone**. Le projet doit gérer **3 variantes Manding distinctes** sans nuance pollutive entre elles :

| Variante | Code ISO | Particularités | Statut Wourri |
|---|---|---|---|
| **Dioula CI** | `dyu` | Loanwords français, prononciation CI, vocabulaire commercial CI | Cible P1 (en cours) |
| **Dioula Mali** | proche de `bm`/`dyu` | Variante Mali plus archaïque, vocabulaire marchand traditionnel | Cible P2/P3 (à anticiper) |
| **Bambara Mali** | `bm` | Langue quotidienne Mali, registre littéraire/scolaire | Cible P3+ |

Ces 3 variantes sont **mutuellement intelligibles mais pas identiques**. Mélanger aveuglément les corpus = créer un modèle qui fait des erreurs entre les 3 (transcriptions hybrides, accent maléen sur message dioula CI, etc.).

**Exigence non-négociable Ruben** : *"il faut faire tout pour éviter les nuances avec celle de la côte d'Ivoire"*.

### Pourquoi traiter ça maintenant

L'implémentation effective est **différée** (P2 ou Sprint 3, après stabilisation Omnilingual ASR via [ADR-0003](0003-plan-ajout-omnilingual.md) Phase 3bis). Mais **graver la décision maintenant** permet :

- Au pipeline de fine-tune de prévoir le tagging par variante dès la conception
- À la collecte de données futures (P2 dioula Mali, P3 bambara Mali) de suivre une stratégie cohérente
- D'éviter le piège classique "on ajoute tout puis on régule plus tard" qui crée la dette pollution
- Aux futurs ADRs (P2 dioula Mali, P3 baoulé/bété) de référencer une stratégie multi-variantes claire

---

## Inventaire des corpus par variante linguistique

### Variante 1 — Dioula CI (`dyu_CI`)

| Source | Volume | Format | Statut |
|---|---|---|---|
| `cv-corpus-24.0-dyu` | 5 028 phrases + 295 MP3 | Audio + texte | ✅ téléchargé localement |
| `corpus_ivr_v3_full_draft.json` | 162 entrées | Texte uniquement | ✅ archivé (cf. [P1-07]) |
| `findora_fr_dioula.json` | 20 513 paires | Texte (corpus biblique majoritairement) | ✅ téléchargé |
| `koumankan_dyu_fr.json` | 10 929 paires | Texte (UVCI corpus dyu-fr) | ✅ téléchargé |
| Données vocales WhatsApp Wourri | ~ inconnu | Audio brut | ⚠️ à collecter |

**Total dyu_CI** : ~36 700 phrases texte + 295 audios. **Très limité côté audio.**

### Variante 2 — Dioula Mali (`dyu_ML`)

| Source | Volume estimé | Disponibilité | Statut |
|---|---|---|---|
| Corpus dédié dioula Mali | À identifier | À chercher (Common Voice ? RobotsMali ?) | ❌ pas de source claire identifiée |
| AfVoices (partie commerciale) | Inconnu | Pas distingué dans AfVoices (mélangé bambara) | ⚠️ extraction par tagging à étudier |

**Total dyu_ML** : **vide aujourd'hui**. Collecte spécifique à prévoir en P2.

### Variante 3 — Bambara Mali (`bam_ML`)

| Source | Volume | Format | Statut |
|---|---|---|---|
| **AfVoices `human-corrected`** | 253 290 train + 6 718 test | Audio + texte | ❌ pas téléchargé, **cible principale ADR** |
| AfVoices `model-annotated` | 355 571 train | Audio + texte (auto-labélisé) | Considéré silver, à éviter pour POC |
| AfVoices `short` | 259 183 train | Audio + texte | Phrases courtes, complément possible |
| `bayelemabaga` | 42k paires | Texte parallèle | ✅ téléchargé |
| `jeli_asr_bam.txt` | 67k phrases | Audio + transcription | ✅ téléchargé |
| `RobotsMali/bam-asr-early` | À vérifier | Audio + texte | À évaluer en complément |

**Total bam_ML** : **massif** avec AfVoices (>250k phrases qualité gold + 423h audio).

---

## Options étudiées

### Option A — Multi-modèles isolés par variante (retenue)

Un modèle ASR fine-tuné **par variante** :
- Modèle dyu_CI fine-tuné sur corpus tagués `dyu_CI` uniquement
- Modèle bam_ML fine-tuné sur corpus tagués `bam_ML` uniquement
- Modèle dyu_ML quand corpus disponible

Routage côté production via **AfroLID** ([ADR-0005](0005-afrolid-language-detection.md)) qui détecte la variante et route vers le bon modèle.

**Pour** :
- ✅ **Zéro pollution croisée** — un modèle dyu_CI ne voit JAMAIS de bambara Mali
- ✅ Aligné exigence Ruben "éviter les nuances"
- ✅ Évaluation indépendante par variante (WER chiffré séparément)
- ✅ Rollback granulaire (un modèle peut régresser sans toucher les autres)

**Contre** :
- Plusieurs modèles à maintenir (un par variante active)
- Stockage modèles ×N
- Charge mémoire prod si tous chargés simultanément (à mitiger via lazy loading)

### Option B — Modèle unique multi-tag (rejetée pour P1-P2, à reconsidérer P3+)

Un seul modèle entraîné avec un **token spécial** indiquant la variante cible (multi-task learning).

**Pour** : un seul artefact à maintenir, économie compute.

**Contre pour Wourri actuellement** :
- ❌ Risque élevé de **cross-contamination** sans contrôle fin
- ❌ Nécessite **quantité équilibrée par variante** — aujourd'hui dyu_CI a ~5k audios, bam_ML aurait 423h. Déséquilibre 1:200, modèle écrasé par bam_ML
- ❌ Pas testable proprement avec corpus actuels
- À reconsidérer en P3+ quand chaque variante aura ≥ 50h audio équilibré

### Option C — Modèle unique sans distinction (rejetée fermement)

Mélanger tous les corpus Manding sans tagging.

**Pour** : zéro effort de tri.

**Contre** :
- ❌ **Crée exactement le problème que Ruben veut éviter** : nuances pollutives, accent mali sur dioula CI, vocabulaire mélangé
- ❌ Aucun moyen de mesurer ou contrôler la dérive
- ❌ Anti-pattern industrie ASR multi-dialectal
- **Rejet ferme** — incompatible avec la doctrine qualité du projet

### Comparatif synthétique

| Critère | A. Multi-modèles | B. Multi-tag | C. Mélangé |
|---|---|---|---|
| Évite nuances dyu_CI ↔ bam_ML | ✅ | ⚠️ | ❌ |
| Aligné exigence Ruben | ✅ | partiel | ❌ |
| Effort initial | Modéré | Élevé | Faible |
| Maintenance long terme | Modéré (par modèle) | Faible (un seul) | Trompeur (dette cachée) |
| Évaluation par variante | ✅ trivial | partiel (test sets séparés requis) | ❌ impossible |
| Scale 50+ langues à terme | ✅ ajout linéaire | ✅ idéal | ❌ |
| Dette technique | Faible | Modérée | Élevée |

---

## Décision

**Option A — Multi-modèles isolés par variante**, avec **stratégie d'isolation stricte** sur 3 axes :

1. **Tagging des corpus** : chaque clip de fine-tune porte un champ `variant: "dyu_CI" | "dyu_ML" | "bam_ML"` dans le metadata. Pas de clip sans tag.
2. **Fine-tune isolé par variante** : un job de fine-tune par variante, jamais de mélange dans le même run d'entraînement.
3. **Évaluation séparée** : WER, CER, taux d'hallucination calculés indépendamment sur chaque variante. Aucun score global moyenné.

### Justification

- **Seule option** qui satisfait l'exigence Ruben "éviter les nuances avec dioula CI"
- **Préserve la qualité dyu_CI** quand bam_ML arrivera massivement via AfVoices
- **Anticipe dyu_ML** sans engager de design qui le bloquerait
- **Réversible** : si en P3+ on veut basculer sur Option B (multi-tag), les corpus tagués sont déjà prêts

---

## Plan d'intégration en 3 phases

### Phase A — POC dyu_CI strict (immédiat, 1-2 mois)

**Cible** : modèle ASR dyu_CI pur, fine-tuné sur corpus dyu_CI uniquement.

**Corpus utilisés** :
- `cv-corpus-24.0-dyu` (5 028 phrases + 295 audios)
- `corpus_ivr.json` v2.3 (162 entrées texte)
- (optionnel) sample WhatsApp Wourri si collecté

**Tagging** : tous les clips → `variant: "dyu_CI"`.

**Pas d'AfVoices** dans cette phase — c'est du bam_ML.

**Critère de succès** : WER ≤ 30 % sur set de test dioula CI authentique (cf. [docs/benchmarks/0001-asr-dioula-evaluation.md](../benchmarks/0001-asr-dioula-evaluation.md)).

### Phase B — Intégration AfVoices pour bam_ML (moyen terme, 2-4 mois)

**Cible** : modèle ASR bam_ML séparé, fine-tuné sur AfVoices.

**Corpus utilisés** :
- AfVoices `human-corrected` 10k sample (POC) puis full 253k (validation)
- jeli_asr_bam.txt (67k phrases)
- bayelemabaga (42k paires texte)

**Tagging** : tous les clips → `variant: "bam_ML"`.

**Sous-phase B1 (POC)** : sample 10k clips d'AfVoices `human-corrected` (~2-3 GB), fine-tune, mesure WER bam_ML, évaluation **isolée du modèle dyu_CI**.

**Sous-phase B2 (full)** : si POC validé (WER bam_ML ≤ 25 %), full `human-corrected` 64 GB, stratégie cache HF persistant.

**Garde-fou** : à chaque release du modèle bam_ML, **re-tester le modèle dyu_CI** (qui n'a pas bougé) pour confirmer aucune dérive.

### Phase C — Anticipation dyu_ML (long terme, P2/P3)

**Cible** : identifier ou collecter un corpus dioula Mali distinct, créer un 3ᵉ modèle.

**Actions à mener le moment venu** :
1. Identifier des corpus dyu_ML existants (Common Voice langues maliennes ? autres datasets RobotsMali ?)
2. Si rien n'existe : organiser une **collecte ciblée** (partenariat associations dioula Mali, marchés, communauté commerciale)
3. Étudier l'extraction de la portion commerciale d'AfVoices (clips contenant vocabulaire marchand spécifique dyu_ML) — risqué, peut polluer bam_ML

**Critère de succès** : ≥ 20h audio dyu_ML tagué disponible avant fine-tune Phase C.

---

## Stratégie d'isolation des nuances — détails techniques

### Schéma de tagging dans `prepare_dioula_dataset.py`

Le script existant doit être modifié pour produire un dataset HuggingFace au format :

```python
{
    "audio": {"path": "...", "array": [...], "sampling_rate": 16000},
    "text": "...",  # transcription
    "variant": "dyu_CI",  # OBLIGATOIRE — un de {"dyu_CI", "dyu_ML", "bam_ML"}
    "source": "cv-corpus-24-dyu",  # traçabilité
    "duration": 3.42,
    # autres metadata existantes
}
```

**Fail-fast** : si un clip n'a pas de `variant`, le script lève une erreur avant de l'inclure dans le dataset. Pas d'inclusion silencieuse.

### Splits par variante

```
data/dioula_dataset/
├── dyu_CI/
│   ├── train/metadata.jsonl
│   ├── test/metadata.jsonl
│   └── audio/...
├── bam_ML/
│   ├── train/metadata.jsonl
│   ├── test/metadata.jsonl
│   └── audio/...
└── dyu_ML/  # vide initialement, créé en Phase C
    └── train/  test/
```

Chaque variante a son propre dossier — **aucun fichier partagé entre variantes**.

### Évaluation séparée

Le script `finetune/evaluate_wer.py` doit être modifié pour produire un rapport par variante :

```
=== Evaluation modèle dyu_CI ===
WER : 28.5%
CER : 12.3%
Hallucinations : 1/100

=== Evaluation modèle bam_ML ===
WER : 22.1%
CER : 8.7%
Hallucinations : 0/100
```

Pas de moyenne globale qui masquerait une régression sur dyu_CI.

### Routage production (lien avec ADR-0005 AfroLID)

```
Audio reçu
  → AfroLID détecte variante (dyu_CI / bam_ML / dyu_ML / autre)
  → Si dyu_CI : route vers modèle ASR dyu_CI
  → Si bam_ML : route vers modèle ASR bam_ML
  → Si dyu_ML : route vers modèle ASR dyu_ML
  → Si confiance basse OU autre langue : fallback Omnilingual générique
```

---

## Critères de succès chiffrés (à mesurer en POC)

### Pour Phase A (dyu_CI pur)

| Critère | Cible | Méthode |
|---|---|---|
| WER dyu_CI sur test set authentique | ≤ 30 % | Set test 100 phrases dioula CI réelles |
| Hallucinations grossières | 0 ou 1 sur 20 audios | Évaluation humaine Ruben |
| Préservation cas agricoles (kakawo, kafe, etc.) | 100 % | Set test dédié termes agricoles |

### Pour Phase B (bam_ML via AfVoices)

| Critère | Cible | Méthode |
|---|---|---|
| WER bam_ML sur AfVoices test | ≤ 25 % | Set test natif AfVoices |
| **Aucune régression dyu_CI** | WER dyu_CI inchangé après ajout bam_ML | Re-test modèle dyu_CI séparé |
| Pas de transcription hybride dyu_CI/bam_ML | 0 cas observé sur 50 audios | Évaluation humaine |

### Garde-fou anti-régression

À chaque release d'un nouveau modèle (toute variante), **re-tester systématiquement** les modèles des autres variantes pour s'assurer qu'aucune n'a régressé. Si régression > 5 % WER détectée, **rollback obligatoire**.

---

## Conséquences

### Positives

- **Bond quantitatif majeur pour bam_ML** (+253k phrases human-corrected, +423h audio vs presque rien actuellement)
- **Préservation garantie de la qualité dyu_CI** par isolation stricte
- **Anticipation sereine du dyu_ML** sans bloquer le projet
- **Aligné vision 50+ langues** ([vision.md](../vision.md)) — la stratégie multi-modèles s'étend aux baoulé/bété/agni en P2-P3
- **Aucune dette de pollution** créée
- **Compatible ADR-0005 AfroLID** — le routage par variante détectée est cohérent avec la stratégie

### Négatives assumées

- **Plusieurs modèles à maintenir** (1 par variante active) — coût stockage et mémoire prod
- **Stratégie cache HF** à concevoir pour AfVoices 64 GB (cache persistant ? téléchargement progressif ?)
- **Compute fine-tuning** par variante = coût récurrent (Colab Pro ou GPU dédié)
- **Bénéfice direct sur dyu_CI nul à court terme** — AfVoices renforce bam_ML, pas dyu_CI directement (mais Manding family transfer learning peut aider indirectement)
- **Phase C dyu_ML est aujourd'hui sans corpus identifié** — risque d'avoir à organiser une collecte (effort non chiffré)

### Verrous futurs levés

- Ajout baoulé/bété/agni en P2 — stratégie multi-modèles déjà en place, ajouter une variante = ajouter un modèle
- Routage en prod via AfroLID prêt à fonctionner pour N variantes
- Métriques de qualité chiffrables et comparables d'une variante à l'autre

---

## Risques et mitigations

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| AfVoices Sud Mali ne reflète pas tout le bam_ML | Moyenne | Modéré | Documenter comme limite ; compléter avec jeli-asr (multi-régions) |
| Régression dyu_CI après release bam_ML | Faible (avec isolation) | Haut | Tests cross-variante systématiques avant release ; rollback automatique si > 5 % WER |
| Volume 64 GB AfVoices ingérable sur disque | Moyenne | Modéré | Phase B1 sample 10k d'abord ; cache HF persistant ; si vraiment trop : config `short` (16 GB) |
| Compute fine-tune trop cher (multi-modèles) | Faible | Modéré | Colab Pro temporaire pour POC ; cloud GPU spot pour full ; décision case-by-case |
| dyu_ML sans corpus identifié bloque Phase C | Élevée | Modéré | Phase C est différée ; collecte ciblée à organiser via partenariats Mali |
| Cross-contamination malgré isolation (bug pipeline) | Faible | Haut | Tests automatiques `assert variant in {"dyu_CI", "dyu_ML", "bam_ML"}` à chaque chargement de clip |
| Modification incorrecte du script `prepare_dioula_dataset.py` | Faible | Haut | Une PR dédiée pour le tagging, tests unitaires sur dataset généré |

---

## Plan d'implémentation différé

L'implémentation effective est **hors scope de cet ADR**. Cet ADR documente la décision et la stratégie. L'implémentation viendra dans des PRs futures, déclenchées après stabilisation de l'Omnilingual ASR (cf. ADR-0003 Phase 4).

### Phase A — Implémentation (3-5 jours, après stabilisation Omnilingual)

1. Modifier `finetune/prepare_dioula_dataset.py` pour ajouter le champ `variant`
2. Splitter le dataset existant en `dyu_CI/` (CV dyu + corpus_ivr) et `bam_ML/` (bayelemabaga + jeli_asr) — corpus actuels tagués
3. Tests unitaires sur le tagging (assert chaque clip a variant valide)
4. Modifier `finetune/evaluate_wer.py` pour rapport par variante
5. Premier fine-tune dyu_CI sur Colab T4 / Pro, mesure WER
6. PR dédiée + documentation résultats

### Phase B — Implémentation (5-10 jours)

1. Téléchargement AfVoices `human-corrected` 10k sample (~2-3 GB)
2. Conversion au format projet avec `variant: "bam_ML"`
3. Fine-tune bam_ML séparé
4. Évaluation **indépendante** dyu_CI (re-test, attendre WER inchangé)
5. Si POC validé : full `human-corrected` 64 GB, second fine-tune
6. PR dédiée + comparaison POC vs full

### Phase C — Implémentation (P2/P3, calendrier ouvert)

À planifier quand le besoin dyu_ML émergera (utilisateurs maliens identifiés, partenariat coopérative Mali, etc.).

---

## Références

- [HuggingFace RobotsMali/afvoices](https://huggingface.co/datasets/RobotsMali/afvoices) — dataset card, licence CC-BY-4.0 vérifiée 2026-04-23
- [GitHub RobotsMali-AI/afvoices](https://github.com/RobotsMali-AI/afvoices) — code de processing du corpus
- [arXiv 2511.18557](https://arxiv.org/html/2511.18557) — paper RobotsMali "Dealing with the Hard Facts of Low-Resource African NLP"
- [theconversation African Next Voices](https://theconversation.com/african-languages-for-ai-the-project-thats-gathering-a-huge-new-dataset-266371) — contexte programme Gates Foundation
- [docs/vision.md](../vision.md) — horizon 50+ langues qui justifie la stratégie multi-modèles
- [docs/PLAN_ACTION_2026-04.md](../PLAN_ACTION_2026-04.md) — section [P1-01]
- [ADR-0002](0002-ajout-provider-omnilingual.md) — stack ASR Omnilingual
- [ADR-0003](0003-plan-ajout-omnilingual.md) — plan d'ajout Omnilingual (cet ADR-0004 alimente la Phase 3bis fine-tune)
- [ADR-0005](0005-afrolid-language-detection.md) — détection de langue (sera utilisée pour router vers le bon modèle de variante)
- [docs/benchmarks/0001-asr-dioula-evaluation.md](../benchmarks/0001-asr-dioula-evaluation.md) — protocole benchmark ASR
- Issue [#96](https://github.com/ouedraogoissouf2012/wourri/issues/96) — issue source
- Issue [#101](https://github.com/ouedraogoissouf2012/wourri/issues/101) — archive corpus IVR (chantier voisin)

---

## Historique

- **2026-04-23 (rédaction initiale)** — investigation AfVoices/ANV, identification des limites de l'option mélange, conception stratégie multi-modèles isolés. Statut : proposé.
- **2026-04-23 (révision suite remarque Ruben)** — élargissement scope pour anticiper dyu_ML et bam_ML, intégration de la stratégie d'isolation des nuances entre variantes Manding (tagging strict + fine-tune isolé + évaluation séparée).
