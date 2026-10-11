# 08 — Risques et décisions requises

**Date** : 2026-10-11 · Cotation : Impact × Probabilité. Seuls les risques **étayés par une
preuve** figurent ici.

## 1. Registre des risques

### R1 — 🔴 CRITIQUE · Licence non commerciale des poids ML

| | |
|---|---|
| **Impact** | Très élevé — bloque la commercialisation du produit |
| **Probabilité** | Élevée — le problème est **déjà présent**, seule son échéance est incertaine |
| **Preuve** | ADR-0034:18 et :74 ; ADR-0002:126 ; ADR-0003:221 |
| **Statut** | Identifié depuis plusieurs ADR, **jamais tranché** |

La voix dioula en production (`facebook/mms-tts-dyu`) et la traduction
(`facebook/nllb-200-distilled-600M`) reposent sur des poids que le projet qualifie lui-même de
**non commerciaux**. Le risque est invisible tant qu'il n'y a pas de facturation, puis il
bloque tout.

**Mitigation** : LIC-1 en semaine 1 · **Décision D1 requise**.

### R2 — 🔴 ÉLEVÉ · Aucune sauvegarde automatisée

| | |
|---|---|
| **Impact** | Très élevé — perte du corpus validé, de la file d'amélioration, des préférences |
| **Probabilité** | Moyenne — mais l'événement est irréversible |
| **Preuve** | `pg_dump` uniquement dans des procédures écrites ; aucun script planifié dans `scripts/` ; `docs/guide-projet-wourri.md:354` reconnaît le manque |

Le corpus représente des **mois de validation par des locuteurs natifs**. C'est l'actif le
moins remplaçable du projet, et il n'est pas sauvegardé automatiquement.

**Mitigation** : INF-2 en semaine 1. **Aucune décision requise — à faire, point.**

### R3 — 🔴 ÉLEVÉ · Aucune mesure de qualité du dioula

| | |
|---|---|
| **Impact** | Élevé — pilotage à l'aveugle sur la langue principale |
| **Probabilité** | Certaine — c'est un fait constaté, pas un risque futur |
| **Preuve** | `docs/benchmarks/0001-asr-dioula-evaluation.md` : « proposé, en attente de validation Ruben **avant exécution** » |

Sans référence chiffrée : aucune amélioration prouvable, aucune régression détectable, aucune
comparaison possible. Et une affirmation de qualité devant un partenaire serait **invérifiable**.

**Mitigation** : DIO-1 en semaine 2 · **Décision D2 requise** (disponibilité du locuteur).

### R4 — 🔴 ÉLEVÉ · Absence de consentement sur les enregistrements vocaux

| | |
|---|---|
| **Impact** | Élevé — juridique et éthique, sur des personnes réelles |
| **Probabilité** | Élevée |
| **Preuve** | `docs/compliance/` ne contient qu'`artci-logs.md` ; ADR-0035 organise la collecte sans traiter les droits |

Le projet est par ailleurs **exemplaire** sur la protection des données des agriculteurs
(anonymisation irréversible, refus d'écriture de PII). Ce soin n'a pas été étendu aux
**locuteurs** qui donnent leur voix.

**Mitigation** : QUA-3 en semaine 3 · **Décision D3 requise**.

### R5 — 🟠 MOYEN · Le mode français ne sert pas le corpus

| | |
|---|---|
| **Impact** | Moyen à élevé — le travail de validation n'atteint pas ces utilisateurs |
| **Probabilité** | Certaine — constaté dans le code |
| **Preuve** | `app/services/chat/handlers/french_handler.py` : aucune cascade IVR |

**Mitigation** : FR-1 en semaine 3.

### R6 — 🟠 MOYEN · Déploiement automatique sans palier

| | |
|---|---|
| **Impact** | Moyen — une régression part en production sans approbation |
| **Probabilité** | Moyenne |
| **Preuve** | `.github/workflows/deploy-api.yml` : tout push sur `APIPy` déclenche le déploiement |

Compensé par une suite de tests fournie (98 fichiers), mais **la couverture réelle est
inconnue** (R7). Le couple « déploiement automatique + couverture inconnue » est le vrai sujet.

**Mitigation** : INF-1 ; à réexaminer après la mesure de couverture.

### R7 — 🟠 MOYEN · Couverture de tests inconnue

| **Preuve** | `ci-api.yml` : aucune mention de couverture |
|---|---|

98 fichiers de test pour 16 821 lignes : le volume rassure, la **réalité est non mesurée**.

**Mitigation** : INF-1 en semaines 5–6.

### R8 — 🟠 MOYEN · Chiffres ML potentiellement optimistes

| **Preuve** | 🔍 aucun découpage train/test versionné ni séparation par locuteur trouvés |
|---|---|

Si des locuteurs apparaissent des deux côtés, le **CER 22,1 % du baoulé serait surestimé**.
Ce n'est pas une accusation : c'est une **vérification qui n'a pas été faite**.

**Mitigation** : QUA-2 — à faire **avant** BAO-2 si possible.

### R9 — 🟡 FAIBLE · Documentation d'amorçage périmée

`CLAUDE.md` : 163 entrées / 54 concepts annoncés contre **197 / 60** réels.
**Mitigation** : DOC-1 en semaine 12.

### R10 — 🟡 FAIBLE · Copie obsolète du pipeline ML hors dépôt

`finetune/` racine (mars 2026) peut être exécuté à la place de `finetune/colab/`.
**Mitigation** : INF-3 en semaine 12.

## 2. Décisions requises du manager

| # | Décision | Options | Recommandation | Échéance |
|---|---|---|---|---|
| **D1** | **Licence des poids ML** | (a) rester non commercial ; (b) migrer vers des poids permissifs ; (c) demander une autorisation | **Instruire immédiatement** ; ne pas commercialiser avant réponse | **S1** |
| **D2** | **Disponibilité d'un locuteur dioula** | (a) créneau garanti ; (b) exécuter DIO-1 sans volet humain | **(a)** — sinon la mesure reste partielle | **S1** |
| **D3** | **Consentement et réutilisation des voix** | (a) usage interne seul ; (b) publication du corpus | À trancher **avant** toute nouvelle collecte | **S2** |
| **D4** | **Rémunération des locuteurs** | (a) bénévole ; (b) rémunéré (budget à prévoir) | Clarifier : 4 chantiers en dépendent | **S2** |
| **D5** | **Report du TTS baoulé (BAO-4)** | (a) accepter le report ; (b) l'inclure en retirant un P1 | **(a)** — sans BAO-1 et BAO-3, une voix ne sert personne | **S1** |
| **D6** | **26 issues non planifiées** | (a) rester au backlog ; (b) échanger contre un chantier | **(a)** | **S2** |
| **D7** | **Budget GPU pour BAO-2** | (a) gratuit d'abord, budget en filet ; (b) concentrer sur un mois ; (c) augmenter | **(a)** — s'appuie sur la pratique Kaggle existante | **S6** |

## 3. Ce que l'audit n'a PAS pu vérifier

Par honnêteté de méthode, les points suivants restent **non vérifiés** :

| Sujet | Pourquoi |
|---|---|
| Réception effective des journaux par Grafana/Alloy | Nécessite l'accès au tableau de bord |
| Taux de réussite actuel de la CI | Non exécutée dans cette mission |
| Séparation par locuteur dans les jeux ML | Nécessite l'inspection des métadonnées des jeux |
| Enregistrement de la révision de modèle en production | Nécessite la lecture détaillée de `model_registry.py` et de l'état d'exécution |
| Montants réels des coûts d'hébergement | Nécessite l'accès à la facturation |
| Termes juridiques exacts des licences ML | Nécessite une source à jour et un avis juridique |
| État des services Convex / LQE web en production | Hors du périmètre de dépôt audité |
