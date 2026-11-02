# ADR-0047 — Les décisions de validation vivent en base, pour toutes les langues

**Statut** : **accepté**
**Date** : 2026-11-02
**Auteur(s)** : Claude (assistant) sous direction de Ouedraogo Issouf
**Valideur** : Ouedraogo Issouf — **validé le 2026-11-02**
**ADRs liés** : [ADR-0034](0034-atelier-parite-linguistique.md) (atelier multi-langues),
[ADR-0045](0045-nlu-baoule-methode-dioula-validation-atelier.md), [ADR-0046](0046-validation-multisources-mots-baoule.md),
[ADR-0031](0031-moteur-amelioration-linguistique.md)

---

## Contexte

### Ce qui a déclenché la décision

Trois concepts baoulé n'ont **plus aucun mot validé** — `TEMPS_METEO`, `ACTION_VENDRE`,
`CULTURE_HARICOT` (#600). Un paysan qui pose en baoulé une question **météo** n'est donc **pas
compris du tout**, alors que la météo est une fonction centrale de WOURI.

En cherchant comment faire travailler le locuteur sur ces trous, deux impossibilités sont
apparues — et elles ne concernent pas le baoulé, mais **la conception de l'atelier**.

### Impossibilité 1 — une décision de validation qui n'habite pas l'outil de validation

Sept mots portent la décision `a_confirmer` dans
`dictionnaires/relecture_mots_cles_bci.json` : ils attendent une réponse du locuteur.

**Or ces sept fiches sont `admin_accepted` en base** (vérifié) : elles existent normalement
dans l'atelier. Seule la décision de les écarter vit **ailleurs** — dans un fichier, dans un
autre dépôt. Conséquences mesurées :

- le locuteur **ne peut ni les voir ni y répondre** ;
- **rien ne les relance** : un mot oublié dans cet état reste écarté pour toujours, en silence ;
- le fichier est **nommé par langue** (`..._bci.json`).

### Impossibilité 2 — ajouter un mot pour un concept est hors de portée du locuteur

L'onglet « Ajouter » est une **zone de texte JSON brute**, dont le gabarit est :

```json
[{"text_local":"","text_fr":""}]
```

Il ne porte **ni `kind` ni `concept_id`**. Même rempli correctement, il créerait un *contenu*,
pas un **mot-clé rattaché à un concept**. Un locuteur natif non technicien ne peut pas s'en
servir pour combler un concept vide.

### Le fait qui commande la décision

L'atelier est **déjà conçu pour N langues**, et c'est explicite :

> `language_registry.py` — « Référentiel des langues, **source de vérité unique** (ADR-0034 P4).
> Activer une langue = un INSERT. **Zéro code, zéro `if`-langue**. »

De plus, **les 61 concepts portent déjà un `label_fr`** réutilisable.

Autrement dit : **l'architecture est bonne, et une seule pièce casse le motif** — le fichier de
relecture, spécifique à une langue et extérieur à l'atelier.

> **Ce que nous décidons ici servira de repère pour toutes les langues à venir.** Le critère
> n'est donc pas « le moins coûteux pour le baoulé », mais **« ce qui se généralise sans être
> réécrit »**.

---

## Questions posées avant la décision

1. Où doivent vivre les décisions de validation : en base, comme toutes les autres, ou dans des
   fichiers par langue ?
2. Quand on repose une question au locuteur, faut-il lui transmettre **le motif** ?
3. L'écran de complétion doit-il lister des concepts figés, ou se **déduire des données** ?

**Réponses du valideur (2026-11-02)** : en base · oui, le motif doit suivre · déduit des données.

---

## Options étudiées

### Option A+ — la décision retourne en base, avec son motif

- **Description** : les fiches à réexaminer repassent en `bronze` et réapparaissent dans
  « À accepter », **avec un motif de réexamen** attaché à la fiche et affiché sur la carte
  (ex. « ta traduction *prix* ne dit pas le concept *vendre* »). Un onglet
  **« Concepts à compléter »** liste les concepts sans aucun mot validé **pour la langue
  courante**, avec le libellé français et un champ de saisie ; l'envoi crée une fiche
  `mot_cle` **bronze** rattachée au bon concept, validée ensuite dans le flux normal.
- **Avantages** : aucune nouvelle règle à apprendre pour le locuteur ; le motif empêche de
  reposer la question à l'identique ; **une primitive réutilisable** (tout relecteur, toute
  langue, peut remettre une fiche en question avec sa raison) ; **zéro code par langue** ;
  l'écran de complétion devient le **parcours d'amorçage d'une nouvelle langue**, où tous les
  concepts sont vides.
- **Inconvénients** : demande un champ de plus sur la fiche et une requête « concepts sans
  mot » ; ne supprime pas à lui seul le fichier de relecture existant.
- **Coût** : moyen-faible, entièrement dans l'atelier.
- **Compatibilité ADR-0034** : **excellente**.

### Option B — un onglet « À confirmer » qui lit le fichier de relecture

- **Description** : un écran dédié lit `relecture_mots_cles_<langue>.json` et propose au
  locuteur de trancher chaque `a_confirmer`.
- **Avantages** : ne touche pas aux données existantes ; livrable vite.
- **Inconvénients** : **réintroduit le couplage par langue que l'ADR-0034 a supprimé**. À dix
  langues : dix fichiers, dix dérives, un écran à maintenir pour chacun. Le canal de décision
  parallèle **survit** au lieu de disparaître. Les décisions restent hors de l'historique de
  l'atelier (qui a décidé, quand).
- **Coût** : faible à court terme, **croissant à chaque langue**.
- **Compatibilité ADR-0034** : **mauvaise**.

### Option C — hors interface : séance orale, saisie par un tiers

- **Description** : le chef de projet appelle le locuteur, note les réponses, les reporte.
- **Avantages** : immédiat, aucun développement.
- **Inconvénients** : **retranscription manuelle** (erreurs), aucune trace de qui a décidé
  quoi, ne passe pas à l'échelle, et **le locuteur reste dépendant d'un tiers**. Contraire à
  l'esprit de l'ADR-0031 (tout passe par le sas de validation).
- **Compatibilité contraintes** : mauvaise.

### Comparatif

| Critère | A+ | B | C |
|---|---|---|---|
| Décisions dans l'historique de l'atelier | **oui** | non | non |
| Code par langue à ajouter | **aucun** | un écran + un fichier | sans objet |
| Le locuteur travaille seul | **oui** | oui | **non** |
| Le motif du réexamen survit | **oui** | partiel | non |
| Sert l'ouverture d'une langue nouvelle | **oui** | non | non |
| Respecte ADR-0034 (zéro `if`-langue) | **oui** | **non** | sans objet |

---

## Décision

**Option retenue : A+.**

1. **Réexamen tracé** — une fiche peut être remise en `bronze` avec un **motif** porté par la
   fiche elle-même et affiché dans « À accepter ». Les sept `a_confirmer` baoulé sont traités
   par ce mécanisme, et la catégorie `a_confirmer` disparaît du fichier de relecture.
2. **Onglet « Concepts à compléter »** — déduit des données : concepts sans aucun mot validé
   **pour la langue courante**, libellé français, champ de saisie ; crée une fiche `mot_cle`
   **bronze** rattachée au concept. Rien n'entre directement au dictionnaire.

**Justification** : c'est la seule option qui **ne coûte rien par langue supplémentaire**.
L'option B livrerait plus vite et coûterait à chaque langue ouverte — en reconstituant
exactement le couplage que l'ADR-0034 a éliminé. Comme ce travail sert de **repère pour les
langues suivantes**, le critère décisif est la généralisation, pas le délai.

---

## Conséquences

- **Positives** : le locuteur travaille **de bout en bout dans l'interface** ; chaque décision
  porte son auteur et sa date ; une nouvelle langue hérite **gratuitement** du parcours
  d'amorçage ; un canal de décision parallèle est supprimé au lieu d'être outillé.
- **Négatives assumées** : un champ de plus sur la fiche et une requête supplémentaire ; les
  sept mots baoulé repassent par « À accepter », ce qui rallonge brièvement la file du
  locuteur.
- **Travail induit** : champ de motif (base + API + affichage) ; requête « concepts sans mot
  par langue » ; onglet de saisie ; remise en `bronze` des sept fiches avec leur motif ;
  retrait de la catégorie `a_confirmer` du fichier de relecture ; tests des deux côtés.
- 🔴 **Dette tracée** — le fichier `relecture_mots_cles_<langue>.json` **doit disparaître** :
  ses décisions `hors_concept` ont elles aussi leur place en base, comme des rejets motivés.
  Tant qu'il existe, **chaque nouvelle langue héritera de son propre fichier orphelin**. Cette
  migration n'est pas faite ici ; elle est la suite logique et doit être instruite **avant la
  troisième langue**, pas après.
- **Verrou futur** : aucun. Le mécanisme de réexamen motivé est générique ; il servira à
  d'autres cas que les mots-clés (paires, contenus).

## Références

- [ADR-0034](0034-atelier-parite-linguistique.md) — « activer une langue = un INSERT, zéro code, zéro `if`-langue »
- [ADR-0031](0031-moteur-amelioration-linguistique.md) — un LLM ne déclare jamais une phrase correcte
- [ADR-0045](0045-nlu-baoule-methode-dioula-validation-atelier.md), [ADR-0046](0046-validation-multisources-mots-baoule.md) — méthode de validation des mots
- Issue #600 — trois concepts sans mot validé
- Code vérifié : `wouri-lqe/app/data/language_registry.py`, `wouri-lqe/app/services/ingest.py`, `wouri-lqe-web/src/views/StudioView.vue`, `dictionnaires/relecture_mots_cles_bci.json`

## Historique

- 2026-11-02 — rédaction et **acceptation** (option A+), sur la base du constat que l'atelier
  est déjà multi-langues et que seul le fichier de relecture casse ce motif.
