# ADR-0037 — Conserver le dépôt multi-branches orphelines (n'exécute pas ADR-0010)

**Statut** : **accepté**
**Date** : 2026-08-27
**Auteur(s)** : Issouf Ouédraogo + assistance agent
**Valideur** : Issouf — « amender ADR-0010 » (dette #489) 2026-08-27
**Remplace** : [ADR-0010](0010-migration-monorepo.md)

---

## Contexte

- [ADR-0010](0010-migration-monorepo.md) « Migration vers monorepo » a été **accepté le 2026-04-23** (Option C), avec une exécution planifiée « sous 3-6 semaines ». **Quatre mois plus tard, il n'a pas été exécuté** et aucune issue ne le suivait (dette #489, audit 2026-08-27).
- État vérifié le 2026-08-27 : le dépôt `ouedraogoissouf2012/wourri` héberge toujours **3 histoires git orphelines** — `git merge-base APIPy whatsappServeur` = exit 1 (aucun ancêtre commun). `APIPy` = Python/FastAPI, `whatsappServeur` = Node/Baileys.
- **Le pattern fonctionne en pratique** : CI par branche (`ci-api.yml` / `ci-wa.yml`), déploiement Dokploy par service (ADR-0026), livraisons régulières depuis des mois. Les inconvénients listés par ADR-0010 (CI, Dependabot, code partagé) sont soit **contournés**, soit **mineurs** à l'échelle actuelle.
- Un ADR **« accepté » non exécuté pendant 4 mois** est un signal trompeur pour quiconque lit `docs/adr/`. La dette #489 demandait de trancher : **exécuter** ou **amender**.

## Décision

**Conserver le pattern multi-branches orphelines. NE PAS migrer vers un monorepo.** [ADR-0010](0010-migration-monorepo.md) passe au statut **remplacé** (par le présent ADR).

**Justification** : la migration monorepo (subtree, réécriture d'historique, CI unifiée à filtres `paths`) est **coûteuse et risquée** (1-2 jours + risque sur l'historique/les déploiements) pour un gain surtout **organisationnel/cosmétique**. Le pattern actuel **livre** ; le coût de la migration n'est pas justifié aujourd'hui. On acte honnêtement l'état plutôt que de laisser un ADR « accepté » dormant.

## Conséquences

- **Positives** : `docs/adr/` reflète la réalité ; aucun travail de migration risqué ; le flux 3-branches (éprouvé) continue.
- **Dette résiduelle assumée** (les points d'ADR-0010 non résolus) : Dependabot / code scanning limités à la branche par défaut ; un visiteur du dépôt voit la branche par défaut, pas les 3 produits ; pas de code partagé Python↔Node ; changements cross-service fragmentés sur 2 branches. **Acceptés** au vu du coût de la migration.
- **Mitigations en place** : CI par branche ; les changements cross-service restent rares (une PR par arbre).
- **Réversibilité** : si le besoin cross-service devient bloquant (ex. gros code partagé), rouvrir la migration via un **nouvel ADR** qui remplacera celui-ci. La décision n'est pas irréversible — elle acte juste « pas maintenant ».

## Références

- Remplace [ADR-0010](0010-migration-monorepo.md) (contexte, options monorepo, arguments détaillés y restent valables si la question est rouverte).
- Dette : issue #489 (audit d'architecture 2026-08-27).

## Historique

- **2026-08-27** — **accepté** (dette #489). Issouf tranche pour l'amendement plutôt que l'exécution : le multi-branches est conservé, ADR-0010 passe en « remplacé ».
