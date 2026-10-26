# ADR-0045 — NLU baoulé : la méthode du dioula, validée par le locuteur dans l'atelier

**Statut** : proposé
**Date** : 2026-10-21
**Auteur(s)** : Claude (assistant) sous direction de Ouedraogo Issouf
**Valideur** : Ouedraogo Issouf — plan approuvé en discussion le 2026-10-21 (« tu peux aller »)
**ADRs liés** : [ADR-0015](0015-strategy-pattern-cascade-chat-et-anglais.md) (handlers par langue), [ADR-0034](0034-atelier-parite-linguistique.md) (atelier, parité), [ADR-0035](0035-collecte-dataset-asr-dictee.md) (dictée), [ADR-0041](0041-choix-culture-et-homographes-nlu.md) (NLU), [ADR-0043](0043-accueil-baoule-langue-annoncee.md) (langue annoncée), [ADR-0044](0044-procedure-finetune-asr-baoule.md) (ASR)
**Issue** : #475 (epic #472) — chantier BAO-3

---

## Contexte

- Le baoulé a maintenant un ASR mesuré : 22,0 → 18,7 % de CER (fiche 0006). Il manque la **compréhension** : aujourd'hui, le baoulé est servi en français (ADR-0043, option W).
- Le **dioula** comprend sans traduire mot à mot :
  1. des **mots-clés par concept** (`dictionnaires/nlu_concepts.json`) ;
  2. le moteur `IntentClassifier` déduit l'**intention** ;
  3. une **réponse validée** est cherchée dans le corpus (intention × culture) ;
  4. le LLM n'intervient qu'en dernier recours.
- **Données disponibles** : la dictée d'esse, soit 433 phrases agricoles baoulé écrites et validées par un locuteur natif, avec leur traduction française et l'audio. Elles comptent 236 questions et 197 réponses sur 15 filières, déjà enregistrées.
- **Mesure d'amorçage** (`scripts/baoule_nlu_bootstrap.py`, validation croisée sur des questions jamais vues, mots-clés **non validés**) : culture retrouvée 171/183, intention 135/236.
- **Exigence du valideur** (2026-10-21) :
  - pas de traduction mot à mot ;
  - la validation passe par les **écrans locuteur de l'atelier**, pas par des fichiers Excel.
- **Échéance** : une première version utilisable par un paysan le vendredi 2026-10-23.

## Questions posées avant la décision

1. Comment le baoulé comprend-il une question ?
2. Qui valide les mots-clés, et où ?
3. D'où viennent les réponses en baoulé ?

Réponses (discussion du 2026-10-21) :

- Q1 → comme le dioula : concepts, puis intention, puis réponse validée.
- Q2 → le locuteur natif, dans l'atelier (écran « À accepter »).
- Q3 → les réponses de la dictée, écrites et lues par le locuteur natif. Aucun texte baoulé n'est généré.

## Options étudiées

### Option A — Traduire le baoulé en français, puis réutiliser le pipeline français
- **Inconvénients** : aucun traducteur baoulé fiable ; le sens se perd au mot à mot (refusé par le valideur) ; risque de baoulé inventé dans les réponses.

### Option B — Méthode du dioula, mots-clés validés dans l'atelier (retenue)
- **Avantages** :
  - moteur d'intention inchangé, mêmes intents que le dioula ;
  - chaque mot-clé est validé par un natif ;
  - réponses natives avec l'audio du locuteur ;
  - mesurable.
- **Inconvénients** :
  - couverture limitée aux questions de la dictée (environ 200 réponses, 15 filières) ;
  - l'atelier doit savoir gérer un élément qui n'est pas du contenu.

### Option C — Mots-clés validés hors atelier (fichier CSV)
- **Inconvénients** : contourne l'outil existant, pas de traçabilité par compte locuteur (refusé par le valideur).

## Décision

**Option B.**

1. **Atelier — type d'élément** : la table `lqe.productions` reçoit une colonne `kind`.
   - **Valeurs** :
     - `contenu` (défaut, comportement actuel) ;
     - `mot_cle` : « tel mot baoulé veut dire tel concept » ;
     - `paire_qr` : « telle réponse répond à telle question ».
   - **Ce qui change pour ces deux nouveaux types** :
     - ils échappent à la garde de parité (ADR-0034) : ce ne sont pas des extensions du contenu servi ;
     - ils ne sont **jamais** listés dans le corpus et ne sont **jamais** promouvables (`production` reste réservé au contenu servi) ;
     - leur décision finale est l'acceptation ou le rejet par le locuteur (rôle `review`), avec correction possible du texte avant acceptation.
   - **Écran « À accepter »** : il affiche le type et le sens (« Mot-clé : kakao → cacao » ; question et réponse proposée l'une sous l'autre).
2. **Construction du NLU baoulé** :
   - `dictionnaires/nlu_concepts_bci.json` est construit **uniquement** depuis les `mot_cle` acceptés (texte éventuellement corrigé) ;
   - même structure et mêmes intents que `nlu_concepts.json`.
3. **Réponses** :
   - corpus baoulé = paires question/réponse de la dictée ;
   - les paires reliées par position sont gardées, celles reliées par le sens doivent avoir été acceptées dans l'atelier ;
   - chaque réponse porte l'audio du locuteur.
4. **API** : `Language.BAOULE` et un `BaouleHandler` (Strategy, ADR-0015) suivent la cascade du dioula : NLU baoulé, puis réponse du corpus baoulé, puis repli honnête. Ce sera l'option A d'ADR-0043, branchée dans une étape suivante de ce chantier.

## Conséquences

- **Positives** :
  - compréhension par le sens ;
  - tout le baoulé servi est validé par un natif ;
  - la validation se fait dans l'outil existant, par compte.
- **Négatives assumées** :
  - couverture limitée à la dictée ; une question hors de ces sujets reçoit un repli honnête ;
  - une migration de schéma de l'atelier, à déployer sur le serveur avant la validation.
- **Retour arrière** : `kind` a pour défaut `contenu`, ce qui ne change rien pour l'existant. Les éléments `mot_cle` et `paire_qr` se suppriment par leur type.

## Révision du 2026-10-26 — Corriger une paire question → réponse

**Constat.** Une paire ne pouvait qu'être acceptée ou rejetée. Le locuteur a rejeté des paires presque justes faute de pouvoir les corriger (capture du 2026-10-26 : 34 paires rejetées sur 36 décidées). Un rejet ne disait donc pas « faux », mais « à corriger ».

**Décision (approuvée par le valideur le 2026-10-26).**

1. **Atelier** : « Corriger » sur une paire, comme sur un mot-clé.
   - La question (`text_local`, `text_fr`) et la réponse proposée (`meta.reponse_bci`, obligatoire, `meta.reponse_fr`) se corrigent ensemble.
   - À la première correction, la question et la réponse d'origine sont gardées dans `meta.texte_origine` ; « Reprendre » restaure les deux.
   - Une réponse envoyée pour un autre type que `paire_qr` est refusée.
2. **Construction** (`scripts/baoule_nlu_build.py`) : une paire acceptée entre au corpus avec la question et la réponse **telles que le locuteur les a acceptées**, et non plus le texte de la dictée.
3. **Audio** : l'enregistrement de la dictée dit la réponse d'origine. Si le locuteur a corrigé la réponse baoulé, elle est servie **en texte seul** (`audio_reponse` vide), jamais avec un audio qui dirait autre chose. Ces réponses sont marquées `audio_a_reenregistrer` et listées à la construction, pour un nouvel enregistrement dans l'écran Dictée.
4. **Reprise des rejets** : `scripts/reprendre_validations.py --types paire_qr --statuts admin_rejected` remet les seules paires rejetées « à valider », pour correction. Les paires acceptées ne sont pas touchées.
5. **Mots-clés acceptés hors concept** (approuvé par le valideur le 2026-10-26). Le locuteur accepte un mot comme baoulé correct et en précise la traduction ; cette traduction peut ne plus dire le concept (« amun » = « vous », proposé pour « planter »). Règle : un mot accepté n'entre dans son concept que si la traduction du locuteur dit encore ce concept.
   - La décision mot par mot est une **donnée datée**, pas une liste dans le code : `dictionnaires/relecture_mots_cles_bci.json` (identifiant externe, concept, mot, sens du locuteur, décision `hors_concept` / `a_confirmer` / `garde`).
   - Relecture du 2026-10-26 : sur 128 mots acceptés à traduction changée, 39 hors concept, 7 à confirmer par le locuteur (écartés tant qu'il n'a pas répondu), le reste garde son concept. Un mot écarté reste un mot baoulé validé avec son sens.
   - Effet mesuré : 168 → 123 mots-clés, 38 → 35 concepts (vendre, haricot et météo n'ont plus de mot validé) ; questions de la dictée bruitées à 19 % inchangées (106 bonnes, 5 mauvaises, 14 replis). Mesure optimiste : le vrai test reste des questions vocales nouvelles.

## Historique

- 2026-10-21 — proposé (plan approuvé par le valideur ; validation par l'atelier exigée).
- 2026-10-22 — **décision du valideur : démo terrain avant la fin de la validation**. « On doit partir de ce que nous connaissons et apprendre sur le terrain avec les corrections et le retour des paysans. » Les paysans ne lisent pas : la démo est vocale (serveur voix baoulé, réponses lues par le locuteur). Dictionnaire **« demo »** (`scripts/baoule_nlu_build.py --demo`) : mots-clés de l'amorçage (non encore validés, usage interne au NLU) et **seulement les 123 paires reliées par position** (9 filières) ; les 74 paires reliées par le sens restent écartées jusqu'à leur validation. Tout ce que le paysan entend ou lit reste le texte et la voix du locuteur natif. Mesure (questions de la dictée) : exacte 123/123 ; bruitée à 19 % 83 à 87 % bonnes, 4 à 7 % mauvaises, le reste en repli honnête (escaladé). Remplacé par la version validée dès la fin de la validation dans l'atelier.
- 2026-10-26 — état de la validation (export de l'atelier) : mots-clés 290 décidés, 172 acceptés dont 128 avec une traduction précisée, 118 rejetés ; paires 74, 2 acceptées, 34 rejetées, 38 à décider. Révision « Corriger une paire » (ci-dessus). Construction validée essayée sur ces décisions : 38 concepts, 168 mots-clés, 125 réponses ; questions de la dictée exactes 125/125, bruitées à 19 % 106 bonnes, 5 mauvaises, 14 replis honnêtes. Pas encore déployée.
