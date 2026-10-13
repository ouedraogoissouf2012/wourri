# 07 — Gouvernance et reporting

**Date** : 2026-10-11 · Conçu pour **un développeur unique**. Toute cérémonie qui coûte plus
qu'elle ne rapporte a été écartée.

## 1. Cycle hebdomadaire réaliste

| Jour | Activité | Durée |
|---|---|---|
| Lundi matin | **Revue des priorités** : ce qui est fait, ce qui bloque, ce qui change | 30 min |
| Lundi → jeudi | **Chantiers de la feuille de route** (4 jours) | — |
| Vendredi | **Réserve** : incidents, maintenance, documentation, mise à jour des ADR | 1 jour |
| Vendredi fin | **Rapport hebdomadaire** (modèle au §4) | 20 min |

**Pourquoi le vendredi est réservé** : sur un produit en production avec des agriculteurs
réels, les incidents arrivent. Sans réserve, ils mangent les chantiers **et** le planning ment.

## 2. Démonstration toutes les deux semaines

**Fin des semaines paires (S2, S4, S6, S8, S10, S12)** — 30 minutes maximum.

Règles :
- On montre **le produit qui tourne**, pas des diapositives.
- On montre aussi **ce qui n'a pas marché** — un fine-tune raté documenté est un résultat.
- Chaque démonstration se termine par **une décision demandée au manager**, pas par un constat.

| Démo | Contenu attendu |
|---|---|
| S2 | Premiers chiffres ASR dioula (DIO-1) — la première mesure de l'histoire du projet |
| S4 | Mode français servant le corpus + accueil baoulé |
| S6 | Mesure de qualité automatisée + couverture de tests |
| S8 | Résultat du fine-tune baoulé (**même s'il est négatif**) |
| S10 | NLU baoulé + indicateurs de l'atelier |
| S12 | Bilan trimestriel et proposition pour le trimestre suivant |

## 3. Registres à tenir

### 3.1 Registre des décisions techniques — ✅ **existe déjà**
`docs/adr/` (40 ADR) et son index. **Rien à créer.** Deux améliorations :
combler les numéros manquants (0006, 0007, 0009) par une note, et vérifier chaque mois que les
ADR « proposés » n'ont pas été oubliés.

### 3.2 Journal des expérimentations ML — 🟡 **partiellement existant**
`docs/benchmarks/` joue déjà ce rôle (6 documents). À formaliser : **une entrée par
expérience**, même ratée, avec date, objectif, données + révision, hyperparamètres, résultat
mesuré, conclusion.

> **Règle** : une expérience sans entrée dans le journal **n'a pas eu lieu**. C'est ce qui
> distingue un travail de R&D d'une suite d'essais.

### 3.3 Tableau des blocages et arbitrages — ❌ **à créer**
Voir §5. Un simple tableau suffit ; pas d'outil supplémentaire.

## 4. Modèle de rapport hebdomadaire au manager

```markdown
# WOURI — Semaine S{n} ({date})

## 1. Livré cette semaine
- [CHANTIER-ID] Titre — état : terminé / en cours (X %)
  Preuve : PR #___ / mesure obtenue / document publié

## 2. Mesuré
| Indicateur | Semaine précédente | Cette semaine |
|---|---|---|
| CER / WER dioula | | |
| CER baoulé | | |
| Couverture de tests | | |
| Questions escaladées en attente | | |
| Délai médian de validation | | |

## 3. Ce qui n'a pas avancé — et pourquoi
(Factuel. Un chantier bloqué annoncé tôt coûte moins cher qu'un retard découvert tard.)

## 4. Décisions attendues du manager
| Sujet | Options | Échéance |
|---|---|---|

## 5. Semaine suivante
- Chantiers prévus et capacité engagée
```

**Deux règles de rédaction** :
1. **Aucun indicateur sans source.** Si la mesure n'a pas tourné, écrire « non mesuré » —
   jamais une estimation présentée comme un chiffre.
2. **Les mauvaises nouvelles en premier.** Un rapport qui commence par les réussites et cache
   le blocage en bas de page n'est pas un rapport de pilotage.

## 5. Tableau des blocages, besoins et arbitrages

| # | Sujet | Type | Bloque | Demandé à | Échéance | État |
|---|---|---|---|---|---|---|
| B1 | Licence des poids ML (CC-BY-NC) | Arbitrage | Toute commercialisation | Manager + juriste | **S1** | 🔴 ouvert |
| B2 | Disponibilité d'un locuteur dioula (Ruben) | Besoin | DIO-1, AGR-2 | Manager | **S1** | 🔴 ouvert |
| B3 | Rémunération des locuteurs | Arbitrage | BAO-3, QUA-3 | Manager | S2 | 🔴 ouvert |
| B4 | Report du TTS baoulé (BAO-4) | Arbitrage | — | Manager | S1 | 🟡 proposé |
| B5 | 26 issues non planifiées | Arbitrage | — | Manager | S2 | 🟡 proposé |
| B6 | Budget GPU serré pour BAO-2 | Besoin | BAO-2 | Manager | S6 | 🟡 proposé |

## 6. Procédure de demande de nouvelle fonctionnalité

Objectif : **limiter le développement aléatoire** sans bloquer les bonnes idées.

1. **Formuler** en trois phrases : le problème de l'agriculteur, ce qu'il ne peut pas faire
   aujourd'hui, comment on saura que c'est réglé.
2. **Ouvrir une issue** — jamais une demande orale seule.
3. **Classer** : si la demande touche le stockage, un modèle ML, la pile technique, un nouveau
   service ou une API publique → **un ADR est obligatoire avant tout code** (règle projet
   existante, `docs/constraints.md` §2.3).
4. **Arbitrer en revue du lundi** : entre dans la capacité, ou **remplace un chantier
   existant**. On ne « rajoute » jamais sans retirer.
5. **Refuser explicitement** quand c'est non. Une demande sans réponse revient trois fois.

> **La règle la plus importante** : *rien n'entre dans la semaine en cours.* Une demande
> arrivée mardi est arbitrée le lundi suivant. C'est la seule protection d'un développeur
> unique contre la dispersion.
