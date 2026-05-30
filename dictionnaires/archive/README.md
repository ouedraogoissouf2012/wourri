# Archive — versions historiques du corpus IVR

**Dernière mise à jour** : 2026-05-30 (session ADR-0014 formalisation)

Ce dossier contient des versions historiques ou exploratoires du corpus IVR
qui **ne sont plus utilisées par le code applicatif**. La source de vérité
actuelle reste `dictionnaires/corpus_ivr.json` (v2.3, 162 entrées).

## ⚠️ État du draft v3 dioula CI (mai 2026)

Le fichier `corpus_ivr_v3_full_draft.json` est l'objet d'un **plan de promotion
formalisé via [ADR-0014](../../docs/adr/0014-promotion-corpus-v3-dioula-ci.md)**.

**14 Pull Requests ouvertes** sur la branche `fix/p3-feedback-deepseek-finetune`
proposent des enrichissements/corrections sur ce draft :

- **#69** : correction `karo` → `kalo` (mois en dioula CI)
- **#70** : arachide (5 entrées)
- **#71-80** : igname, manioc, cacao, mil, coton, banane, tomate, haricot, gombo, oignon (8 entrées par culture)
- **#82** : 35 entrées restantes (sésame, café, ananas, mangue, néré, agrumes)
- **#84** : fix TTS format mois

**Toutes labellisées** `corpus-v3-dioula-ci` pour regroupement visuel GitHub.

**Statut** : ⏳ **en attente de validation locuteur natif dioula CI + tests E2E
staging (Sprint J #202) + score validation ≥ 95%** (actuel 84,9%).

**Décision tranchée** (ADR-0014) : promotion globale (Chemin A) après prérequis
validés. Plan en 5 phases. Tag backup `backup/corpus-v2.3-pre-v3-promotion`
créé AVANT bascule pour rollback garanti.

**Voir [ADR-0014](../../docs/adr/0014-promotion-corpus-v3-dioula-ci.md)
pour le plan complet** (3 options analysées, recommandation argumentée,
critères d'acceptation, plan d'exécution).

## Pourquoi conserver ces fichiers ?

- **Traçabilité** : reflet d'étapes du travail sur le corpus
- **Référence** : utiles comme contexte pour de futures décisions de promotion
- **Réversibilité** : un `git mv` permet de remettre n'importe lequel en
  source de vérité si besoin

## Contenu

### `corpus_ivr_v2.1_backup.json` (162 entrées, v2.1)

Backup figé de la version 2.1 effectué juste avant l'enrichissement AXE-3
(injection de phrases attestées Common Voice dyu, qui a abouti à v2.2).

**Statut** : redondant avec `git history`, mais conservé physiquement comme
sécurité psychologique. Peut être supprimé si on fait une revue de cleanup
ultérieure.

### `corpus_ivr_v3_draft.json` (38 entrées partielles, v3.0-dioula-ci)

Premier draft de la réécriture v3 dioula CI SOV naturel — couvre les
**38 premières phrases** réécrites manuellement (issue [#49](https://github.com/ouedraogoissouf2012/wourri/issues/49)).

Continué dans `corpus_ivr_v3_full_draft.json` (162 entrées complètes).

**Statut** : exploratoire, non destiné à devenir prod tel quel.

### `corpus_ivr_v3_full_draft.json` (162 entrées, v3.0-dioula-ci-full)

Version complète de la réécriture v3 — **162 entrées entièrement réécrites
en dioula CI SOV naturel** avec 4 passes de validation
([commit 4f6c715](https://github.com/ouedraogoissouf2012/wourri/commit/4f6c715))
qui ont fait passer la validation de **78,1 % à 84,9 %**.

**Statut** : **candidat sérieux pour devenir la nouvelle source de vérité
v2.4 / v3 en production**, mais nécessite :

- Test de régression complet sur le pipeline ASR → NLU → IVR → TTS
- Comparaison métriques avant/après (WER, latence, qualité réponses)
- Validation utilisateur sur un échantillon représentatif
- Décision formalisée dans un **ADR dédié** (à rédiger)

Voir issue [#49](https://github.com/ouedraogoissouf2012/wourri/issues/49)
et issue [#89](https://github.com/ouedraogoissouf2012/wourri/issues/89)
(qui a fait le passage 78,1 % → 84,9 %).

## Promotion v3 → prod : ADR futur

La promotion de `corpus_ivr_v3_full_draft.json` comme nouvelle source de
vérité de production est **hors scope de l'issue [#101]** et fera l'objet
d'un ADR dédié quand les ressources de test seront disponibles.

Critères d'acceptation pressentis :

- Validation ≥ 95 % (aujourd'hui : 84,9 %)
- Aucune régression sur tests d'intégration pipeline vocal
- Évaluation humaine native dioula CI sur les 162 entrées
- Tag de release dédié (`corpus-v3.0`)

Tant que cet ADR n'est pas écrit et validé, **la source de vérité reste
`dictionnaires/corpus_ivr.json` (v2.3)**.

## Comment restaurer un fichier d'archive en source de vérité

Si un jour il faut promouvoir l'un de ces fichiers en source de vérité :

```bash
# Exemple : promouvoir v3_full_draft → corpus_ivr.json
cd wouri-api
git mv dictionnaires/archive/corpus_ivr_v3_full_draft.json dictionnaires/corpus_ivr.json --force
# (force car corpus_ivr.json existe déjà — opération destructive sur la v2.3)
```

Avant ce type d'opération : **toujours créer un tag backup** :

```bash
git tag backup/corpus-v2.3-pre-v3-promotion
```

## Références

- Issue [#101](https://github.com/ouedraogoissouf2012/wourri/issues/101) — [P1-07] Trancher la version de référence du corpus IVR (l'issue qui a déclenché cette archive)
- Issue [#49](https://github.com/ouedraogoissouf2012/wourri/issues/49) — Réécriture corpus en dioula CI SOV naturel
- Issue [#89](https://github.com/ouedraogoissouf2012/wourri/issues/89) — Validation corpus v3 (78,1 % → 84,9 %)
- [docs/PLAN_ACTION_2026-04.md](../../docs/PLAN_ACTION_2026-04.md) — section [P1-07]
