# 09 — Synthèse pour la direction

**WOURI — assistant agricole vocal pour les agriculteurs ivoiriens**
Audit technique du 11 octobre 2026 · Feuille de route trimestrielle

---

## En une page

WOURI **fonctionne et sert de vrais agriculteurs** en dioula, sur WhatsApp. L'audit confirme
une base technique **saine et sérieusement documentée**. Trois manques, en revanche, exposent
le projet à des risques importants. **Aucun n'est une faute de construction** : ce sont des
chantiers qui n'ont pas encore trouvé leur place, faute de temps dédié.

| | |
|---|---|
| **Ce qui va bien** | Le produit tourne. L'architecture tient. Les décisions sont tracées. La protection des données des agriculteurs est exemplaire. |
| **Ce qui manque** | On ne **mesure** pas la qualité. On ne **sauvegarde** pas automatiquement. La **licence** des voix n'est pas tranchée. |
| **Ce qui est demandé** | **450 USD sur 3 mois** et, surtout, **du temps protégé** pour un développeur unique. |

---

## 1. Les progrès déjà réalisés

Ces résultats sont **vérifiés dans le code**, pas déclaratifs.

### 1.1 Le produit répond à de vrais agriculteurs
Conversation WhatsApp en dioula et en français, météo agricole localisée, conseils issus d'un
corpus de **197 réponses validées par des locuteurs natifs**.

### 1.2 Le problème des réponses inventées a été traité
Un reproche avait été formulé après une démonstration : l'application inventait des réponses.
**C'est corrigé et vérifié en production** (octobre 2026) :

- sur les questions à réponse vérifiable — prix, météo, dates — l'intelligence artificielle est
  **empêchée de répondre** ; la question part vers un expert ;
- une question portant sur un horizon lointain ne reçoit plus la météo du jour ;
- quand un expert a validé la réponse, **elle est rendue à l'agriculteur** qui l'avait posée.

### 1.3 La confidentialité est traitée sérieusement
Les numéros des agriculteurs sont transformés en empreintes **irréversibles**, et le système
**refuse techniquement** d'enregistrer une donnée personnelle dans l'atelier de validation.
C'est aligné avec les attentes de l'ARTCI.

### 1.4 Le baoulé a progressé avec méthode
Les modèles candidats ont été **comparés sur des chiffres** (290 échantillons), le meilleur
retenu par une décision écrite, et un premier essai d'entraînement a été mené.

### 1.5 La discipline de décision
**40 décisions techniques documentées**, chacune avec ses options et ses conséquences. C'est
rare à cette taille, et cela protège l'entreprise : le projet ne dépend pas de la mémoire
d'une seule personne.

---

## 2. Les trois manques à combler

### 2.1 On ne mesure pas la qualité du dioula

Le protocole de mesure existe depuis avril 2026 ; **il n'a jamais été exécuté** — il attend la
validation d'un locuteur.

**Ce que cela signifie concrètement** : nous ne pouvons pas prouver que l'application comprend
bien, ni détecter si elle se dégrade, ni démontrer un progrès à un partenaire ou à un bailleur.
**Si on nous demande quelle est la qualité, nous n'avons pas de réponse chiffrée.**

*Réglé en semaine 2 — à condition d'obtenir un créneau de locuteur.*

### 2.2 Il n'y a pas de sauvegarde automatique

Le corpus validé représente **des mois de travail de locuteurs natifs**. C'est l'actif le moins
remplaçable du projet. Aujourd'hui, seules des **procédures écrites** existent : rien ne se
déclenche tout seul.

*Réglé en semaine 1. C'est le chantier le plus rentable du plan : deux jours de travail contre
un risque de perte définitive.*

### 2.3 La licence des voix n'est pas tranchée

Les modèles de voix et de traduction utilisés sont, d'après la documentation du projet
elle-même, **sous licence non commerciale**. La question est identifiée depuis plusieurs mois
et n'a jamais été arbitrée.

**Ce que cela signifie** : tant que WOURI n'est pas vendu, il n'y a pas de problème. **Le jour
où il est commercialisé, c'est bloquant.** Il faut l'instruire maintenant, quand nous avons le
temps de changer de solution — pas sous la pression d'un contrat.

*Instruit en semaine 1. Nécessite probablement un avis juridique externe.*

---

## 3. Pourquoi du temps dédié est nécessaire

Un développeur unique porte aujourd'hui l'API, la passerelle WhatsApp, les modèles vocaux,
l'atelier linguistique, le déploiement et la relation avec les locuteurs.

Le plan retient **42 jours de chantiers sur 48 jours disponibles** en 12 semaines, soit
**4 jours par semaine**, le cinquième étant réservé aux incidents et à la maintenance.

> **Ce plan assume des reports.** Le backlog dépasse largement la capacité : la voix baoulé et
> 26 sujets secondaires sont **explicitement reportés**. Un planning qui prétendrait tout tenir
> serait faux — et le retard se découvrirait trop tard.

**Ce qui est demandé n'est pas un effort supplémentaire, mais de la protection** : que les
demandes nouvelles n'entrent pas dans la semaine en cours, et soient arbitrées le lundi
suivant, en remplaçant un chantier plutôt qu'en s'y ajoutant.

---

## 4. Objectifs du trimestre

| | Objectif | Comment on saura que c'est atteint |
|---|---|---|
| 1 | **Savoir ce que vaut notre dioula** | Des chiffres de qualité publiés, pour la première fois |
| 2 | **Ne plus pouvoir perdre nos données** | Une sauvegarde automatique **et une restauration testée** |
| 3 | **Sécuriser juridiquement les voix** | Une décision écrite sur les licences |
| 4 | **Servir nos utilisateurs francophones** | Le corpus validé leur est enfin délivré |
| 5 | **Ouvrir le baoulé aux agriculteurs** | Un agriculteur peut se déclarer baoulophone |
| 6 | **Détecter les régressions sans y penser** | Une mesure automatique et une alerte en cas de baisse |

---

## 5. Budget demandé

| Poste | 3 mois |
|---|---|
| Outil de développement assisté | 300 USD |
| Calcul GPU à la demande | 150 USD |
| **Total** | **450 USD** |

**Déjà couvert** : hébergement, base de données, plateforme des locuteurs, données collectées.
**Aucun nouvel abonnement n'est proposé.**

⚠️ **Deux réserves honnêtes** :

1. Le budget GPU est **juste** pour l'entraînement baoulé. Nous proposons d'utiliser d'abord
   les ressources gratuites — pratique déjà en place sur le projet — et de garder le budget
   comme filet de sécurité.
2. Le **temps des locuteurs natifs** n'est pas budgété, et **quatre chantiers en dépendent**.
   C'est la ressource la plus critique du projet. Aucun montant d'infrastructure ne la remplace.

---

## 6. Décisions attendues de la direction

| # | Décision | Échéance | Recommandation |
|---|---|---|---|
| **D1** | Faire instruire la **licence des modèles vocaux** (avis juridique) | **Semaine 1** | Lancer immédiatement ; ne pas commercialiser avant |
| **D2** | Garantir un **créneau de locuteur dioula** | **Semaine 1** | Indispensable à la première mesure de qualité |
| **D3** | Arbitrer le **consentement et la réutilisation** des enregistrements | Semaine 2 | À trancher avant toute nouvelle collecte |
| **D4** | Clarifier la **rémunération des locuteurs** | Semaine 2 | Quatre chantiers en dépendent |
| **D5** | Accepter le **report de la voix baoulé** | Semaine 1 | Oui — sans porte d'entrée, une voix ne sert personne |
| **D6** | Accepter que **26 sujets secondaires attendent** | Semaine 2 | Oui |
| **D7** | Arbitrer le **budget GPU** si l'entraînement échoue | Semaine 6 | Ressources gratuites d'abord |

---

## 7. En résumé

**WOURI n'est pas un prototype fragile.** C'est un produit en service, construit avec méthode,
dont les décisions sont tracées et dont le problème de fiabilité signalé après la démonstration
**a été corrigé et vérifié en production**.

Ce qui lui manque n'est pas de la technique supplémentaire, mais **trois filets de sécurité** :
une mesure, une sauvegarde et une clarification juridique. Les trois tiennent en **moins de
trois semaines de travail** et **450 USD sur le trimestre**.

**La vraie contrainte n'est pas l'argent. C'est le temps d'un développeur unique, et la
disponibilité des locuteurs natifs qui font la valeur du produit.**

---

*Documents détaillés : [01 état des lieux](01-etat-des-lieux.md) ·
[02 architecture](02-audit-architecture.md) · [03 langues et ML](03-audit-langues-ml.md) ·
[04 backlog](04-backlog-priorise.md) · [05 feuille de route](05-roadmap-12-semaines.md) ·
[06 budget](06-budget-ressources.md) · [07 gouvernance](07-modele-reporting-manager.md) ·
[08 risques](08-risques-et-decisions.md)*
