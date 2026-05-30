# ADR-0014 — Promotion corpus v3 dioula CI vers production

**Statut** : proposé
**Date** : 2026-05-30
**Auteur** : Claude (sous direction Ruben)
**Valideur** : Ruben (en attente — cet ADR documente l'analyse pour décision)

---

## Contexte

### Situation actuelle

Le projet Wourri utilise un corpus de **162 entrées agricoles bambara/dioula**
(`dictionnaires/corpus_ivr.json`, **version 2.3**, source de vérité production).

En **avril 2026**, Ruben a entrepris une réécriture manuelle complète du corpus
en **dioula CI naturel** avec grammaire SOV authentique et vocabulaire validé
multi-sources (cf. issue [#49](https://github.com/ouedraogoissouf2012/wourri/issues/49)).

Le résultat de ce travail est figé dans **`dictionnaires/archive/corpus_ivr_v3_full_draft.json`** :
- 162 entrées entièrement réécrites en dioula CI SOV naturel
- 4 passes de validation linguistique
- Score validation : **84,9%** (cf. issue [#89](https://github.com/ouedraogoissouf2012/wourri/issues/89))
- Cible : ≥ 95% requis pour promotion en prod

### 14 Pull Requests ouvertes en suspens (avril 2026)

Sur la branche WIP `fix/p3-feedback-deepseek-finetune`, **14 PRs ouvertes**
proposent des enrichissements/corrections par culture sur ce draft v3 :

| PR | Issue | Culture | Entrées |
|---|---|---|---:|
| [#69](https://github.com/ouedraogoissouf2012/wourri/pull/69) | #50 | (correction) `karo` → `kalo` (mois) | — |
| [#70](https://github.com/ouedraogoissouf2012/wourri/pull/70) | #51 | arachide | 5 |
| [#71](https://github.com/ouedraogoissouf2012/wourri/pull/71) | #52 | igname | 8 |
| [#72](https://github.com/ouedraogoissouf2012/wourri/pull/72) | #53 | manioc | 8 |
| [#73](https://github.com/ouedraogoissouf2012/wourri/pull/73) | #54 | cacao | 8 |
| [#74](https://github.com/ouedraogoissouf2012/wourri/pull/74) | #55 | mil | 8 |
| [#75](https://github.com/ouedraogoissouf2012/wourri/pull/75) | #56 | coton | 8 |
| [#76](https://github.com/ouedraogoissouf2012/wourri/pull/76) | #57 | banane | 8 |
| [#77](https://github.com/ouedraogoissouf2012/wourri/pull/77) | #58 | tomate | 4 |
| [#78](https://github.com/ouedraogoissouf2012/wourri/pull/78) | #59 | haricot/niébé | 8 |
| [#79](https://github.com/ouedraogoissouf2012/wourri/pull/79) | #60 | gombo | 8 |
| [#80](https://github.com/ouedraogoissouf2012/wourri/pull/80) | #61 | oignon | 8 |
| [#82](https://github.com/ouedraogoissouf2012/wourri/pull/82) | #63-#68 | sésame, café, ananas, mangue, néré, agrumes | **35** |
| [#84](https://github.com/ouedraogoissouf2012/wourri/pull/84) | #83 | TTS format mois | — |

**Total** : ~120 entrées cumulées de corrections/enrichissements en attente.

### Comparaison concrète v2.3 prod vs v3 draft

Exemple `riz_conseil_001` :

**v2.3 prod** :
```
"reponse_bambara": "Aw ye màlo sɛnɛ mɛ kalo la sanji tuma na. Aw ye dugukolo lèmùna ɲini, jì ka se ka don a la. Aw ye sɛnɛ santimɛtiri mugan mugan."
```

**v3 draft** :
```
"reponse_bambara": "Aw ye maa loo sɛnɛ mɛɛɛ karo la sanjiii tuma na. Aw ye dugukoloo jiman ɲini, ji ka se ka don a la. Aw ye sɛnɛ santimɛtiri mugan mugan."
```

**Différences observables** :
- **Allongement de voyelles TTS-friendly** : `maa loo` (vs `màlo`), `mɛɛɛ` (vs `mɛ`), `sanjiii` (vs `sanji`), `dugukoloo` (vs `dugukolo`) — améliore la prononciation audio MMS-dyu
- **Suppression diacritiques fantaisistes** : `ji` (vs `jì`), `jiman` (vs `lèmùna` qui est du Mali)
- **Vocabulaire dioula CI naturel** : `jiman` (humide en dioula CI) vs `lèmùna` (forme Mali)

### Ce que ce plan PRODUIT

Une décision formalisée sur **comment promouvoir le corpus v3 dioula CI en
production**, avec critères d'acceptation stricts et plan d'exécution en
phases pour éviter une régression du pipeline ASR → NLU → IVR → TTS sur
les utilisateurs réels.

---

## Questions à trancher

1. **Faut-il promouvoir le draft v3 entièrement (162 entrées) ou cherry-pick par culture ?**
2. **Quel niveau de validation linguistique exiger avant promotion ?** (84,9% actuel → cible 95% ?)
3. **Faut-il un locuteur natif dioula CI pour valider ?** (sans ça : risque d'erreurs subtiles invisibles depuis l'extérieur de la communauté)
4. **Comment mesurer la non-régression du pipeline avant bascule ?** (besoin staging Sprint J + métriques TTS WER/qualité audio)
5. **Faut-il merger les 14 PRs séparément ou en bloc ?**

---

## Options étudiées

### Option A — Promotion globale v3 après validation rigoureuse

**Description** : Merger les 14 PRs sur `fix/p3-feedback-deepseek-finetune`,
faire évoluer le score validation 84,9% → ≥ 95% via les corrections en
attente, puis promouvoir le fichier draft complet en `corpus_ivr.json` v3.0
en production.

**Prérequis stricts** :
1. Validation locuteur natif dioula CI sur échantillon ≥ 50 entrées
2. Score validation linguistique ≥ 95%
3. Tests E2E pipeline ASR → NLU → IVR → TTS sur staging (Sprint J #202)
4. Comparaison métriques avant/après : WER ASR, latence TTS, qualité audio
5. Évaluation humaine native sur 162 entrées (au moins échantillonnage)
6. Tag git `backup/corpus-v2.3-pre-v3-promotion` créé AVANT la bascule

**Avantages** :
- **Cohérence linguistique globale** : tous les utilisateurs entendent un
  dioula CI naturel uniforme (pas un mélange v2.3 + corrections v3)
- **TTS optimisé** : allongement voyelles → prononciation MMS-dyu plus claire
- **Vocabulaire validé multi-sources** : `jiman` (dioula CI) au lieu de
  `lèmùna` (Mali), `kalo` au lieu de `karo`, etc.
- **Travail Ruben capitalisé** : les 6 semaines de réécriture manuelle
  servent vraiment à quelque chose en prod

**Inconvénients** :
- **Bloqué sur locuteur natif** : sans validation humaine native, on ne peut
  garantir l'absence d'erreurs subtiles
- **Bloqué sur staging** : sans VM staging déployée (Sprint J), impossible
  de mesurer la non-régression pipeline en conditions réelles
- **Big-bang risqué** : si régression sur 1 culture, tous les utilisateurs
  impactés simultanément (pas de feature flag par culture actuellement)

**Coût** :
- **Temps locuteur natif** : 2-5 jours d'évaluation (162 entrées × 3 phrases)
- **Temps Ruben coord** : 1-2 jours (suivi validation + analyse retours)
- **Temps staging déploiement** : Sprint J #202 (~1-2 jours toi seul)
- **Temps merges + tests E2E** : 1 jour
- **Total estimé** : 5-10 jours de calendrier (en attente locuteur)

**Verrou futur** :
- Faible : si v3 a un bug critique, rollback git possible (`git checkout v2.3`)
- Si plus tard une v4 émerge : même processus ADR + validation

---

### Option B — Cherry-pick incrémental dans v2.3

**Description** : Au lieu de promouvoir le draft v3 entier, importer les
améliorations linguistiques PR par PR dans le corpus v2.3 actuel. Garder
v2.3 comme source de vérité, juste l'enrichir progressivement.

**Avantages** :
- **Pas de bloqueur locuteur** : on peut merger les corrections évidentes
  (typos, `karo` → `kalo`) sans validation native
- **Risque réduit par PR** : si une culture casse, seulement cette culture
  impactée (mais corpus = 1 fichier, donc rollback granulaire impossible
  sans git revert)
- **Pas besoin staging** : tests unitaires sur quelques entrées suffisent

**Inconvénients** :
- **Incohérence corpus** : mélange grammaire v2.3 (verbes anciens) + corrections
  v3 (verbes nouveaux) → cassure stylistique perçue par utilisateurs
- **TTS bénéfices PARTIELS** : si seules quelques cultures ont l'allongement
  voyelles, d'autres restent en prononciation dégradée → expérience inégale
- **Perte du travail global** : on jette le bénéfice du SOV uniforme
- **Effort par PR sans bénéfice global** : 14 PRs à merger × tests × review,
  pour un résultat qualité hybride

**Coût** :
- **Temps merge** : ~1h par PR × 14 = 14h
- **Temps test régression** : 1-2 jours
- **Coût opportunité** : abandonne le bénéfice global v3

**Verrou futur** :
- Élevé : le corpus devient un patchwork, difficile à reprendre proprement
  plus tard pour la vraie promotion v3

---

### Option C — Fermer les 14 PRs + redémarrer plus tard

**Description** : Fermer toutes les PRs #69-#82 + #84 avec commentaire
"À reprendre avec locuteur natif + ADR validation". Le travail reste dans
`dictionnaires/archive/corpus_ivr_v3_full_draft.json` (162 entrées). Pas de
promotion immédiate.

**Avantages** :
- **Repo propre** : zéro PR zombie pendante
- **Décision claire** : on assume "pas maintenant"
- **Liberté future** : quand locuteur natif disponible, on redémarre avec
  un process propre

**Inconvénients** :
- **Perte visibilité travail** : les 14 PRs disparaissent du listing GitHub
  (les commits restent dans git mais sont moins découvrables)
- **Démotivation potentielle** : Ruben a fait 6 semaines de travail visible
  → fermer envoie le signal "on jette"
- **Risque oubli** : si pas de tracking, on oublie de redémarrer plus tard

**Coût** :
- **Temps fermeture** : 5 min (script de fermeture par lot)
- **Coût opportunité** : aucun (travail préservé en archive)

**Verrou futur** :
- Aucun : repartira from scratch avec process propre

---

### Comparatif

| Critère | A (promotion globale) | B (cherry-pick) | C (fermer) |
|---|---|---|---|
| **Qualité linguistique finale** | ✅ Cohérente | ❌ Hybride | ⚠️ v2.3 inchangé |
| **TTS audio amélioré** | ✅ Uniforme | ⚠️ Partiel | ❌ Aucun |
| **Bloqueur locuteur natif** | ❌ Oui | ✅ Non | ✅ Non |
| **Bloqueur staging** | ❌ Oui | ✅ Non | ✅ Non |
| **Effort total** | 5-10j calendaire | 15j travail | 5 min |
| **Risque régression** | Medium (testé staging) | High (incohérent) | 0 |
| **Travail Ruben capitalisé** | ✅ Total | ⚠️ Partiel | ⚠️ Préservé en archive seule |
| **Réversibilité** | ✅ Tag backup + git checkout | ⚠️ Git revert par PR | N/A |
| **Cohérence corpus** | ✅ Uniforme | ❌ Patchwork | ✅ Inchangé |

---

## Décision

**Option retenue : A — Promotion globale v3 après validation rigoureuse**

### Justification

1. **Préserver le travail linguistique** : Ruben a investi 6 semaines à
   réécrire 162 entrées en dioula CI naturel. Fermer (C) ou patchworker (B)
   sacrifie ce travail pour des raisons opérationnelles, alors que le problème
   est juste un manque de tiers (locuteur + staging).

2. **Bénéfice utilisateur maximal** : l'allongement voyelles TTS-friendly
   (`maa loo`, `sanjiii`) améliore la prononciation audio MMS-dyu sur TOUTES
   les cultures simultanément. C'est le bon UX pour les agriculteurs.

3. **Cohérence > rapidité** : un corpus uniforme est plus facile à maintenir
   qu'un patchwork hybride v2.3/v3.

4. **Bloqueurs sont externes** : locuteur natif + staging Sprint J. Les deux
   sont planifiés (Sprint O #207 + Sprint J #202). L'ADR formalise le plan
   d'attente sans gaspiller le travail accumulé.

5. **Réversibilité garantie** : tag `backup/corpus-v2.3-pre-v3-promotion`
   AVANT bascule permet un rollback en 1 commande si régression.

### Conditions d'acceptation pour exécuter la décision

L'option A reste **proposée** jusqu'à validation des 6 prérequis :

| # | Prérequis | Tiers requis | Tracé dans |
|---|---|---|---|
| 1 | Validation locuteur natif dioula CI ≥ 50 entrées échantillon | Locuteur Sprint O #207 | À planifier |
| 2 | Score validation linguistique ≥ 95% | Tooling validate_vocab + locuteur | Mesurer après #1 |
| 3 | Staging déployé + tests E2E pipeline OK | Sprint J #202 (PR #254 prête) | Sprint J.4 |
| 4 | Comparaison métriques WER ASR + latence TTS | Sprint J staging | Sprint J.4 |
| 5 | Tag git `backup/corpus-v2.3-pre-v3-promotion` créé | Toi (Ruben) | Avant promotion |
| 6 | 14 PRs mergées en bloc sur `fix/p3-feedback-deepseek-finetune` | Toi | Étape finale |

---

## Conséquences (si décision A retenue après prérequis)

### Positives

- Corpus dioula CI naturel uniforme sur 162 entrées
- TTS audio MMS-dyu prononciation améliorée (allongement voyelles)
- Vocabulaire validé multi-sources (`jiman` vs `lèmùna`, `kalo` vs `karo`, etc.)
- 6 semaines de travail Ruben enfin valorisées
- Référence canonique pour futures additions (vocabulaire, formes verbales)

### Négatives assumées

- **Bloqueur tiers (locuteur natif)** : projet en attente jusqu'à identification
  d'un locuteur disposé à évaluer 162 × 3 phrases
- **Bloqueur staging** : sans VM staging, impossible de valider la
  non-régression pipeline ASR→NLU→IVR→TTS sur conditions réelles
- **Délai 5-10 jours** entre identification locuteur et bascule prod

### Migration / travail induit

**Phase 1 — Préparation (faisable maintenant, sans tiers)** :
1. Cet ADR (PR ouverte)
2. Tagger les 14 PRs avec label `corpus-v3-dioula-ci` pour regroupement
3. Commenter chaque PR avec lien vers cet ADR + statut "en attente locuteur"
4. Mettre à jour `dictionnaires/archive/README.md`

**Phase 2 — Identification locuteur natif (tiers)** :
5. Identifier 1-2 locuteurs natifs dioula CI (réseau projet, agriculteurs
   bilingues, contacts ATHARI ADVISORS, université Cocody, etc.)
6. Définir format évaluation (sheet Google ou WhatsApp audio ou écrit)

**Phase 3 — Validation linguistique** :
7. Échantillonnage 50 entrées prioritaires (cultures principales :
   riz/maïs/manioc/igname/arachide/tomate)
8. Locuteur évalue : grammaire OK ? Vocabulaire OK ? Prononciation TTS audio ?
9. Itération corrections jusqu'à 95% validation

**Phase 4 — Validation technique (Sprint J)** :
10. Déployer staging (Sprint J #202)
11. Charger v3 draft sur staging, mesurer WER ASR + latence TTS
12. Comparer avec v2.3 sur les mêmes scenarios E2E
13. Si régression : itérer, sinon valider promotion

**Phase 5 — Promotion prod** :
14. Tag backup : `git tag -a backup/corpus-v2.3-pre-v3-promotion -m "..."`
15. Merger les 14 PRs sur `fix/p3-feedback-deepseek-finetune`
16. PR finale : `git mv archive/corpus_ivr_v3_full_draft.json corpus_ivr.json`
17. Tag release : `corpus-v3.0`
18. Mettre à jour cet ADR statut `proposé` → `complété`

### Verrous futurs

- **Format corpus** : v3 reste en JSON même structure que v2.3, donc pas
  de verrou d'API. Réversible à tout moment.
- **Cherry-pick futur** : si un jour besoin de re-modifier une culture
  spécifique, on peut créer une PR ciblée sur `corpus_ivr.json` v3 directement.
- **v4 future** : même processus ADR + validation locuteur (pattern réutilisable).

---

## Hors scope

- **Sprint O corpus enrichissement** (issue #207) : ajout de NOUVELLES
  cultures/entrées au-delà des 162 actuelles. Cet ADR ne concerne QUE la
  promotion du travail v3 EXISTANT.
- **Refactor du format JSON corpus** : potentielle évolution vers YAML ou DB,
  hors scope (ADR dédié).
- **Fine-tuning MMS-dyu sur nouveau corpus** (issue P2-NN) : pipeline
  fine-tune `finetune/finetune_mms_dioula.py` existe mais nécessite GPU Colab
  + données entraînement, hors scope cet ADR.
- **AfroLID détection langue automatique** (ADR-0005) : indépendant de la
  qualité du corpus, hors scope.

---

## Plan d'exécution Phase 1 (faisable cette session)

| Étape | Description | Statut |
|---|---|---|
| 1 | Cet ADR rédigé | ✅ Cette PR |
| 2 | Création label GitHub `corpus-v3-dioula-ci` | À faire |
| 3 | Application label aux 14 PRs | À faire |
| 4 | Commentaire sur chaque PR : "en attente locuteur natif + Sprint J + ADR-0014" | À faire |
| 5 | Mise à jour `dictionnaires/archive/README.md` avec état 14 PRs | À faire |
| 6 | Cet ADR mergé | À faire après validation Ruben |

---

## Métriques de succès (Phase 5 promotion)

| Métrique | Cible |
|---|---|
| Validation linguistique | ≥ 95% (vs 84,9% actuel draft) |
| Locuteur natif évaluation positive | ≥ 90% des 50 entrées échantillon |
| WER ASR staging vs v2.3 | régression ≤ 5% |
| Latence TTS p50 staging | régression ≤ 10% |
| Tests E2E pipeline 5 scénarios WhatsApp | 5/5 verts |
| Tag backup créé avant bascule | ✅ |
| 14 PRs mergées sans conflit | ✅ |
| ADR-0014 marqué `complété` | ✅ |

---

## Références

- **Branche WIP draft** : `fix/p3-feedback-deepseek-finetune` (base des 14 PRs)
- **Fichier draft** : `dictionnaires/archive/corpus_ivr_v3_full_draft.json` (162 entrées, v3, 84,9% validation)
- **Fichier prod actuel** : `dictionnaires/corpus_ivr.json` (162 entrées, v2.3, source de vérité)
- **Archive doc** : [`dictionnaires/archive/README.md`](../../dictionnaires/archive/README.md)
- **Règles dioula** : [`data/GRAMMAIRE_DIOULA_REGLES.md`](../../../data/GRAMMAIRE_DIOULA_REGLES.md) (SOV, marqueurs `bɛ`/`ye`/`ma`, `nɔgɔ` vs `saraka`, etc.)
- **Issues liées** :
  - [#49](https://github.com/ouedraogoissouf2012/wourri/issues/49) — Réécriture corpus en dioula CI SOV naturel (origine du draft v3)
  - [#89](https://github.com/ouedraogoissouf2012/wourri/issues/89) — Validation corpus v3 (78,1% → 84,9%)
  - [#101](https://github.com/ouedraogoissouf2012/wourri/issues/101) — Trancher version référence corpus (archive créée)
  - [#207](https://github.com/ouedraogoissouf2012/wourri/issues/207) — Sprint O corpus v3 enrichissement (dépend locuteur natif)
- **14 PRs** : #69, #70, #71, #72, #73, #74, #75, #76, #77, #78, #79, #80, #82, #84
- **ADR lié** : ADR-0005 (AfroLID détection langue) — indépendant
- **ADR lié** : ADR-0008 (migration pgvector) — pas d'impact, corpus stocké en JSON

---

## Historique

- **2026-05-30 (rédaction)** : ADR rédigé pour formaliser le plan de
  promotion du corpus v3 dioula CI en production. Statut **proposé** —
  attend validation Ruben + identification locuteur natif + déploiement
  Sprint J #202. Les 14 PRs en suspens depuis avril 2026 sont valorisées
  via cet ADR (pas obsolètes, en attente Phase 2-5).
