# ADR-0040 — Boucle de retour : tenir la promesse faite à l'agriculteur sans ré-identifier

**Statut** : **accepté**
**Date** : 2026-10-05
**Auteur(s)** : Claude (assistant) sous direction de Ouedraogo Issouf
**Valideur** : Ouedraogo Issouf — **accepté le 2026-10-05** (option D)
**ADRs liés** : [ADR-0039](0039-politique-reponse-llm-et-escalade.md) (**exécute** sa dette §Conséquences), [ADR-0031](0031-moteur-amelioration-linguistique.md) (sas de validation), [ADR-0025](0025-retention-logs-pii-artci.md) (PII / ARTCI), [ADR-0024](0024-transition-convex-multitenant.md)

---

## Contexte

### La promesse, et le trou

L'[ADR-0039](0039-politique-reponse-llm-et-escalade.md) (accepté, déployé, validé en
production le 2026-10-05) interdit au LLM d'inventer sur les faits vérifiables. À la
place, l'agriculteur reçoit :

> « Bonne question. Je préfère ne pas te répondre au hasard : **je la transmets à un
> expert, tu auras une réponse.** »

Cette formulation a été arbitrée par le valideur, **en connaissance de sa conséquence**,
tracée en 🔴 au §Conséquences de l'ADR-0039 : **la boucle de retour n'existe pas.** La
question part bien dans la file d'amélioration (`improvement_queue`), mais **rien ne
renvoie la réponse à l'agriculteur qui a posé la question.**

Autrement dit : nous venons de supprimer un mensonge (l'IA qui invente) et nous l'avons
remplacé par **une promesse non tenue**. C'est l'objet du présent ADR.

### Le verrou de confidentialité — délibéré, et solide

Ce n'est pas un oubli d'implémentation : **la ré-identification est impossible par
conception.**

- `app/core/pii_utils.py` — `anonymize_user_id()` applique **SHA-256 avec sel** :
  « Même input → même output (déterministe). **Irréversible sans le salt.** »
- `app/services/improvement_queue.py`, en-tête : « **Aucun numéro** : uniquement `user`
  déjà anonymisé par l'appelant. »
- Le module va plus loin : il **refuse l'écriture** d'une tâche dont le contenu
  sérialisé contient `user_id` ou `@s.whatsapp` (`[LQE] tâche refusée : PII détectée`).

Une tâche stocke donc : `id`, `ts`, `status`, `language`, `intent`, `source`, `cultures`,
`excerpt` (la question, 200 car.), **`user` = l'empreinte anonyme**, `fingerprint`.

Ce verrou sert la conformité **ARTCI** (cf. [ADR-0025](0025-retention-logs-pii-artci.md)) :
l'atelier linguistique manipule du contenu, **jamais des personnes**.

### Où vit réellement la donnée personnelle

Côté `whatsapp-server` **uniquement** : `user_preferences.json` (préférences par
identifiant WhatsApp) et `lib/message_queue.js`, qui stocke `userNumber`
(ex. `22541540178@s.whatsapp.net`) pour garantir qu'aucun message n'est perdu.
Ces deux fichiers sont **gelés** par le brief d'intégration.

### Ce qui se passe déjà quand une question est validée

`decide_task()` fait transiter une tâche (`bronze` → `admin_accepted` /
`speaker_accepted` / `production`). **Le contenu validé, lui, ne revient pas dans la
tâche** : conformément à l'ADR-0031, il part dans le **corpus** (pgvector) via l'import.

Conséquence importante : **une fois la question validée et importée, le moteur sait y
répondre — pour tout le monde.** Il ne manque donc pas une « réponse à livrer », il
manque **un rappel à la bonne personne**.

### Le fait qui ouvre une solution élégante

L'anonymisation est **déterministe** : `anonymize_user_id(id)` donne toujours la même
empreinte. Or, **au moment où l'agriculteur écrit, nous détenons son identifiant réel.**
Nous pouvons donc recalculer son empreinte **dans le sens direct** et retrouver ses
questions escaladées — **sans aucune table de ré-identification, sans stocker un numéro
de plus.** Le sens interdit (empreinte → personne) n'est jamais emprunté.

---

## Questions posées avant la décision

1. **Quel niveau de service la promesse doit-elle tenir ?** Une notification *poussée*
   (l'agriculteur reçoit un message spontané) ou un *rappel au prochain échange* ?
2. **Accepte-t-on de créer une table de correspondance** empreinte → numéro, c'est-à-dire
   de **défaire le verrou** posé par l'ADR-0031 et de créer une base ré-identifiante
   soumise à l'ARTCI (durée de conservation, droit à l'effacement, sécurité) ?
3. **Si la promesse ne peut pas être tenue intégralement, préfère-t-on corriger le
   message** plutôt que de laisser une attente non satisfaite ?

**Réponses du valideur (Ouedraogo Issouf, 2026-10-05)** :

- **Q1 → rappel au prochain échange.** Pas de notification poussée.
- **Q2 → NON.** On ne crée pas de table de correspondance : le verrou de l'ADR-0031 est
  **confirmé**, aucune base ré-identifiante n'est constituée.
- **Q3 → oui, le message est aligné** sur ce que le système tient réellement.

---

## Options étudiées

### Option A — Notification poussée (vraie promesse tenue)

- **Description** : à l'escalade, enregistrer la correspondance `empreinte → identifiant
  WhatsApp` dans un magasin dédié et protégé. Quand la tâche atteint `production`, un
  déclencheur résout la correspondance et émet un message sortant.
- **Avantages** : tient la promesse **au sens littéral** ; l'agriculteur n'a rien à faire.
- **Inconvénients** : **défait le verrou de l'ADR-0031** — on recrée exactement la
  capacité de ré-identification que le projet a volontairement supprimée. Crée une base
  **PII soumise à l'ARTCI** (conservation, effacement, sécurité, journalisation des
  accès). Exige un **déclencheur** côté atelier, un **émetteur sortant** côté
  `whatsapp-server` (dont `message_queue.js` est **gelé**), et une politique
  anti-spam/anti-réveil nocturne.
- **Coût** : élevé — nouveau magasin PII + nouveau flux sortant + conformité + gel à lever.
- **Compatibilité contraintes** : **mauvaise** (ADR-0031, ADR-0025, brief de gel).

### Option B — Ne rien promettre (corriger le message seul)

- **Description** : remplacer la formulation par une phrase qui n'engage pas :
  « Je n'ai pas encore de réponse fiable à cette question. Je la fais étudier — **repose-la
  moi dans quelques jours.** »
- **Avantages** : **honnête immédiatement** ; zéro PII, zéro infrastructure ; une ligne.
- **Inconvénients** : repose entièrement sur la mémoire de l'agriculteur ; aucune valeur
  ajoutée ; l'escalade reste invisible pour lui.
- **Coût** : minimal.
- **Compatibilité contraintes** : parfaite.

### Option C — Rappel au prochain échange (sens direct uniquement)

- **Description** : à chaque message entrant, le moteur calcule l'empreinte de
  l'agriculteur (**sens direct**, aucune table) et regarde si l'une de ses questions
  escaladées a depuis été validée. Si oui, il **rejoue la question conservée dans
  `excerpt`** à travers la cascade — qui la couvre désormais — et délivre la réponse,
  précédée d'un rappel : « Tu m'avais demandé *…* — voici la réponse. » Un marqueur de
  remise évite la répétition.
- **Avantages** : **le verrou de confidentialité reste intact** (le sens empreinte →
  personne n'est jamais emprunté) ; **aucune donnée personnelle supplémentaire** ; aucun
  flux sortant, donc aucun gel à lever ; réutilise la cascade existante et le corpus
  fraîchement enrichi ; **auto-nettoyant** (rien à livrer si l'agriculteur ne revient pas).
- **Inconvénients** : la réponse n'arrive **qu'au retour** de l'agriculteur — ce n'est pas
  une notification. Exige un marqueur de remise sur la tâche et un coût de lecture par
  message entrant (atténuable par un index sur l'empreinte).
- **Coût** : moyen-faible, entièrement dans le moteur.
- **Compatibilité contraintes** : **excellente**.

### Option D — Option C + message aligné sur ce qui est réellement tenu

- **Description** : C, **et** reformuler l'accusé pour promettre exactement ce que le
  système fait : « Je la fais étudier par un expert. **Reviens me voir : je te donnerai la
  réponse.** »
- **Avantages** : la promesse devient **vraie** ; l'agriculteur sait quoi faire ; tous les
  avantages de C.
- **Inconvénients** : ceux de C.
- **Coût** : C + une constante.
- **Compatibilité contraintes** : excellente.

### Comparatif

| Critère | A — poussée | B — ne rien promettre | C — rappel au retour | D — C + message aligné |
|---|---|---|---|---|
| Promesse tenue | oui | sans objet (supprimée) | oui, au retour | **oui, au retour** |
| Verrou ADR-0031 préservé | **non** | oui | **oui** | **oui** |
| Nouvelle donnée personnelle | **oui** (base ré-identifiante) | non | **non** | **non** |
| Conformité ARTCI à instruire | **lourde** | néant | néant | néant |
| Gel à lever (`message_queue.js`) | **oui** | non | non | non |
| Valeur pour l'agriculteur | maximale | nulle | bonne | **bonne, et annoncée** |
| Coût | élevé | minimal | moyen-faible | moyen-faible |
| Réversible | difficilement | oui | oui (drapeau) | oui (drapeau) |

---

## Décision

**Option retenue** : **D — rappel au prochain échange + message aligné.**
*Arbitrée par Ouedraogo Issouf le 2026-10-05.*

Concrètement :
1. À chaque message entrant, le moteur calcule l'empreinte de l'agriculteur **dans le sens
   direct** et cherche ses questions escaladées désormais validées.
2. S'il en trouve une, il **rejoue la question conservée** (`excerpt`) dans la cascade et
   délivre la réponse, précédée d'un rappel explicite.
3. Un **marqueur de remise** empêche la répétition.
4. L'accusé devient : « Je la fais étudier par un expert. **Reviens me voir : je te
   donnerai la réponse.** »

**Justification** :

- Elle **tient la promesse** sans jamais emprunter le sens interdit : l'empreinte est
  recalculée **depuis** l'identifiant au moment où l'agriculteur écrit, jamais l'inverse.
  **Aucune donnée personnelle nouvelle n'est créée**, donc aucune instruction ARTCI.
- Elle **ne touche à aucun fichier gelé** et n'ajoute aucun flux sortant : tout vit dans le
  moteur, en extension.
- Elle rend la promesse **exacte** : on annonce ce que le système fait réellement
  (« reviens me voir »), au lieu de laisser entendre une notification qui n'arrivera pas.
- L'option A reste **possible plus tard** si le produit l'exige : elle devra alors être
  instruite pour elle-même (ADR dédié, base ré-identifiante, conformité ARTCI,
  anti-spam). Rien dans D ne l'empêche.

---

## Conséquences

- **Positives** : la promesse cesse d'être vide ; chaque question escaladée qui aboutit
  **revient à son auteur** ; le travail de validation devient **visible** pour
  l'agriculteur, ce qui l'encourage à poser des questions difficiles ; le verrou de
  confidentialité est **confirmé**, pas contourné.
- **Négatives assumées** : la réponse n'arrive **pas spontanément** — un agriculteur qui ne
  revient jamais ne la recevra pas. C'est le prix explicite du refus de créer une base
  ré-identifiante.
- **Travail induit** : marqueur de remise sur la tâche (`delivered_at`) ; lecture des
  questions en attente à l'entrée du moteur (indexée par empreinte) ; rejeu de
  `excerpt` dans la cascade ; reformulation de la constante d'accusé ; drapeau de
  configuration pour désactiver le rappel sans redéploiement.
- **Verrous futurs** : si l'option A est un jour retenue, le marqueur de remise et le
  stockage de la question restent valables — D n'est pas un cul-de-sac.
- **Limite honnête** : la pertinence du rappel dépend du **délai de validation** par les
  locuteurs/experts. Si une tâche met des semaines à être traitée, le rappel arrivera
  longtemps après la question. Le délai de traitement de l'atelier devient donc un
  indicateur produit à suivre.

## Références

- [ADR-0039](0039-politique-reponse-llm-et-escalade.md) §Conséquences — la dette que le présent ADR exécute
- [ADR-0031](0031-moteur-amelioration-linguistique.md) — sas de validation, « un LLM ne déclare jamais une phrase correcte »
- [ADR-0025](0025-retention-logs-pii-artci.md) — rétention et PII (ARTCI)
- Code vérifié : `app/core/pii_utils.py` (`anonymize_user_id`, SHA-256 salé irréversible), `app/services/improvement_queue.py` (champs de tâche, garde PII à l'écriture, `decide_task`), `whatsapp-server/lib/message_queue.js` (stockage `userNumber`, **gelé**)
- Validation terrain du 2026-10-05 : la promesse est servie en production depuis le déploiement de #551

## Historique

- 2026-10-05 — rédaction initiale (statut **proposé**).
- 2026-10-05 — **accepté** : option **D**. Le verrou de confidentialité de l'ADR-0031 est
  explicitement **confirmé** (pas de table de ré-identification, pas de base PII nouvelle) ;
  l'option A reste ouverte pour plus tard, sous ADR dédié.
