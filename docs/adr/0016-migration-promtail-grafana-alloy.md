# ADR-0016 — Migration de Promtail vers Grafana Alloy

**Statut** : accepté
**Date** : 2026-07-29
**Auteur** : Codex (sous direction du mainteneur Wourri)
**Valideur** : mainteneur Wourri (validation explicite du périmètre le 2026-07-29)

---

## Contexte

Le monitoring staging défini dans `docker-compose.staging.yml` repose sur
Loki 3.3.2 et Promtail 3.3.2. Deux faits imposent une correction avant tout
déploiement :

1. Grafana a arrêté Promtail le 2 mars 2026. Le composant ne reçoit plus de
   support ni de mises à jour ; Grafana recommande désormais Alloy.
2. `config/promtail/promtail-config.yml` découvre les conteneurs via
   `unix:///var/run/docker.sock`, mais le service Compose ne monte pas ce
   socket. La collecte Docker décrite par le runbook ne peut donc pas
   fonctionner dans l'état actuel.

La collecte doit rester locale à la VM staging, envoyer les logs vers le Loki
existant et conserver les labels utilisés par les requêtes du runbook :
`job`, `container_name` et `stack="wourri-staging"`.

Cette décision ne provisionne aucune VM, ne modifie aucun DNS et n'active
aucun déploiement. Elle prépare uniquement une configuration locale
reproductible dans le cadre de l'issue #39.

## Questions posées avant la décision

1. Faut-il conserver Promtail jusqu'au premier déploiement ?
2. Faut-il remplacer aussi Loki ?
3. Comment limiter la collecte aux seuls conteneurs Wourri staging ?
4. Comment valider la nouvelle configuration sans déployer ?

Réponses obtenues :

- Le mainteneur a validé le remplacement de Promtail maintenant, tout en
  reportant le déploiement.
- Loki reste compatible avec Alloy via l'endpoint
  `/loki/api/v1/push` ; son remplacement n'apporterait rien à ce correctif.
- `discovery.docker` et `discovery.relabel` permettent de garder uniquement
  les noms `wourri_*_staging` et de produire les labels existants.
- La commande officielle `alloy validate` sera exécutée localement et en CI.

## Options étudiées

### Option A — Conserver Promtail 3.3.2

- **Avantage** : aucun changement immédiat de syntaxe.
- **Inconvénients** : composant en fin de vie, aucune correction de sécurité
  future et configuration Docker actuellement inopérante.
- **Coût** : dette opérationnelle reportée au moment du déploiement.
- **Compatibilité** : incompatible avec l'exigence d'une base maintenable.

### Option B — Migrer vers Grafana Alloy natif

- **Avantages** : composant officiellement supporté, pipeline Docker → Loki
  natif, configuration validable par CLI, conservation du Loki existant.
- **Inconvénients** : nouvelle syntaxe Alloy et montage nécessaire du socket
  Docker.
- **Coût** : migration bornée à un service Compose, un fichier de
  configuration, le runbook et la CI.
- **Compatibilité** : respecte l'architecture existante et n'ajoute aucun
  service externe.

### Option C — Utiliser le logging driver Loki du daemon Docker

- **Avantage** : suppression de l'agent de collecte.
- **Inconvénients** : installation d'un plugin sur l'hôte, configuration
  globale du daemon Docker, couplage de tous les conteneurs au backend Loki
  et risque d'affecter les démarrages si Loki est indisponible.
- **Coût** : procédure hôte plus intrusive et rollback plus risqué.
- **Compatibilité** : disproportionné pour la VM staging.

### Comparatif

| Critère | A — Promtail | B — Alloy | C — Driver Loki |
|---|---|---|---|
| Support éditeur | terminé | actif | actif |
| Changement du daemon Docker | non | non | oui |
| Conservation de Loki | oui | oui | oui |
| Validation locale | limitée | `alloy validate` | nécessite un hôte configuré |
| Risque opérationnel | croissant | borné | élevé |

## Décision

**Option retenue : B — Grafana Alloy natif**, version
`grafana/alloy:v1.18.0`.

Alloy découvre les conteneurs par le socket Docker, garde uniquement les noms
`wourri_*_staging`, reconstruit les labels documentés puis transmet les logs
au Loki interne. Son interface HTTP n'est pas publiée sur l'hôte.

Le socket est monté en lecture seule. Cette option empêche sa modification
directe depuis le système de fichiers du conteneur, mais ne transforme pas
l'API Docker en API strictement read-only : un processus compromis pourrait
toujours tenter des requêtes privilégiées au daemon. Le risque est accepté
pour la VM staging dédiée et réduit par :

- `no-new-privileges:true` ;
- aucune exposition réseau de l'interface Alloy ;
- collecte limitée aux conteneurs Wourri staging ;
- image épinglée sur une version exacte.

Un proxy de socket filtrant les méthodes Docker reste une amélioration future
possible si Alloy doit être déployé sur une VM mutualisée ou en production.

## Conséquences

- **Positives** :
  - suppression d'un composant en fin de vie ;
  - correction de la découverte Docker non fonctionnelle ;
  - labels LogQL existants conservés ;
  - validation syntaxique reproductible localement et en CI.
- **Négatives assumées** :
  - accès d'Alloy au socket Docker de la VM staging ;
  - nouveau format de configuration à maintenir ;
  - les métriques internes portent désormais les noms Alloy, pas Promtail.
- **Migration / travail induit** :
  1. remplacer le service et le volume Promtail dans le Compose staging ;
  2. ajouter `config/alloy/config.alloy` ;
  3. retirer `config/promtail/promtail-config.yml` ;
  4. mettre à jour le runbook et la CI ;
  5. valider avec l'image Alloy épinglée avant toute PR.
- **Rollback** : revert du commit de migration. Promtail ne constitue
  toutefois qu'un rollback temporaire, car il n'est plus supporté.
- **Verrous futurs** : aucun sur Loki ; l'endpoint standard peut recevoir les
  logs d'un autre agent si nécessaire.

## Références

- Issue Wourri
  [#39](https://github.com/ouedraogoissouf2012/wourri/issues/39)
- [Fin de vie de Promtail](https://grafana.com/docs/loki/latest/send-data/promtail/)
- [Guide officiel de migration vers Alloy](https://grafana.com/docs/alloy/latest/set-up/migrate/from-promtail/)
- [Découverte Docker Alloy](https://grafana.com/docs/alloy/latest/reference/components/discovery/discovery.docker/)
- [Source de logs Docker Alloy](https://grafana.com/docs/alloy/latest/reference/components/loki/loki.source.docker/)
- [Installation Docker Alloy](https://grafana.com/docs/alloy/latest/set-up/install/docker/)

## Historique

- 2026-07-29 — décision acceptée et migration locale autorisée ; déploiement
  explicitement reporté.
