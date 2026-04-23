# ADR-NNNN — {Titre court de la décision}

**Statut** : proposé | accepté | remplacé par ADR-XXXX | déprécié
**Date** : YYYY-MM-DD
**Auteur(s)** : {Nom}
**Valideur** : {Nom du décideur final}

---

## Contexte

Décrire la situation qui appelle une décision. Faits, pas opinions.

- Contraintes projet pertinentes (réf. `docs/vision.md`, `docs/constraints.md`)
- État actuel qui pose problème
- Pourquoi on décide *maintenant* (ce qui a changé)

## Questions posées avant la décision

1. …
2. …

Réponses obtenues (réf. transcript / discussion) :

- Q1 → …
- Q2 → …

## Options étudiées

### Option A — {Nom}

- **Description courte**
- **Avantages** (mesurés si possible, pas supposés)
- **Inconvénients** (mesurés si possible)
- **Coût** (temps, argent, complexité, verrou futur)
- **Compatibilité** avec contraintes projet

### Option B — {Nom}

Même structure.

### Option C — {Nom}

Même structure.

### Comparatif

| Critère | A | B | C |
|---|---|---|---|
| Scalabilité | … | … | … |
| Coût ops | … | … | … |
| Dette technique | … | … | … |
| Vitesse dev | … | … | … |
| Verrou vendor | … | … | … |

## Décision

**Option retenue** : {A / B / C}

**Justification** : pourquoi celle-ci, pas les autres. Raisonnement explicite.

## Conséquences

- **Positives** : …
- **Négatives assumées** : …
- **Migration / travail induit** : fichiers à créer/modifier, ordre de migration, rollback possible
- **Verrous futurs** : ce qui devient difficile à changer après cette décision

## Références

- Discussion / transcript / issue
- Benchmarks
- Documentation externe
- ADR liés (prérequis, suites)

## Historique

- YYYY-MM-DD — décision initiale
- YYYY-MM-DD — révision (si superseded)
