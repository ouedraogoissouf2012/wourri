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

## Historique

- 2026-10-21 — proposé (plan approuvé par le valideur ; validation par l'atelier exigée).
