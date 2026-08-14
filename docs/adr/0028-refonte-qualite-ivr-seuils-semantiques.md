# ADR-0028 — Refonte qualité IVR : seuils de confiance + exploitation du score sémantique pgvector

**Statut** : accepté
**Date** : 2026-08-14
**Auteur(s)** : Claude (assistant) sous direction de Ouedraogo Issouf
**Valideur** : Ouedraogo Issouf (Ruben)
**Lié à** : issue [#297](https://github.com/ouedraogoissouf2012/wourri/issues/297)
**ADRs liés** : [ADR-0001](0001-choix-stockage-donnees.md) (pgvector), [ADR-0008](0008-plan-migration-chromadb-pgvector.md) (migration+index ivfflat), [ADR-0015](0015-strategy-pattern-cascade-chat-et-anglais.md) (cascade chat)

---

## Contexte

La cascade de réponse Wourri (NLU → IVR exact → IVR concept → DeepSeek+NLLB →
fallback, cf. `chat_service.py` + `chat/ivr_searcher.py`) doit refuser une réponse
IVR **hors-sujet** et laisser la main au tier suivant (DeepSeek) quand aucune
entrée du corpus n'est réellement pertinente. Or, deux mécanismes censés jouer ce
rôle sont soit mal placés, soit inexistants.

### État actuel qui pose problème (vérifié dans le code)

**1. Le seuil de confiance NLU ne gate QUE la reconstruction de phrase FR.**

`app/services/nlu/nlu_service.py:56` :

```python
MIN_CONFIDENCE_THRESHOLD = 0.2
```

`nlu_service.py:121-128` — ce seuil conditionne uniquement l'appel à
`SentenceBuilder.build()` (la phrase FR envoyée à DeepSeek). L'`intent` classifié,
lui, est **toujours** propagé quelle que soit la confiance, et c'est cet `intent`
(non seuillé) qui pilote la recherche IVR dans `ivr_searcher.try_ivr_exact()`
(`ivr_searcher.py:99-104`). Conséquence : une classification d'intent faible
(0.05) déclenche quand même une recherche corpus.

De plus, `0.2` est un **attribut de classe hardcodé** — violation directe de
`constraints.md §1.2` (« pas de magic number, tout seuil externalisé »).

**2. La recherche IVR jette la similarité sémantique pgvector.**

`app/services/corpus_service.py:193-232` — `_query_candidates()` exécute :

```sql
SELECT id, intent, cultures, conditions, reponse_bambara, reponse_fr, score_validation
FROM corpus_entries
WHERE intent = :intent
ORDER BY embedding <=> CAST(:query_emb AS vector)
LIMIT 5
```

La distance cosine `<=>` sert **uniquement à ordonner** le TOP-5 ; elle **n'est pas
sélectionnée**. `_best_result_pg()` (`corpus_service.py:144-190`) reçoit donc des
`rows` **sans distance** et choisit le « meilleur » sur un score qui ignore
totalement la pertinence sémantique — il ne combine que `score_validation`
(qualité de la rédaction humaine, constante par entrée) + bonus saison/conditions
(`season_scoring.score_entry`). Autrement dit : **dès qu'une entrée existe pour
l'`intent`, l'IVR répond**, même si le TOP-1 est sémantiquement à côté de la plaque.

**3. Il n'existe aucun seuil de rejet sémantique.**

`chercher_reponse_ivr()` (`corpus_service.py:240-294`) retourne le premier `best`
non-nul rencontré dans sa cascade 3-essais. Aucun plancher de similarité ne peut
transformer un mauvais match en `None` (ce qui laisserait DeepSeek prendre le
relais). Le seul garde-fou existant est `_result_matches_requested_cultures()`
(`ivr_searcher.py:36-52`), qui filtre sur la **culture** mais pas sur le **sens**.

### Ce qui n'est PAS mesurable aujourd'hui (honnêteté sur les données)

L'index pgvector est `ivfflat ... vector_cosine_ops` (ADR-0008 §Phase B, ligne
`USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)`). Donc `<=>`
renvoie une **distance cosine** ∈ [0, 2] (0 = identique), et la similarité
utilisable = `1 - distance`.

**Mais aucune distance n'est aujourd'hui ni sélectionnée, ni loggée, ni persistée**
(`grep` confirmé : `<=>` n'apparaît que dans les `ORDER BY`). Il n'existe donc
**pas encore** de distribution de distances réelles exploitable pour fixer un seuil
objectif. Toute calibration « mesurée » exige d'abord une **phase d'instrumentation
en observation** (exposer la distance sans l'utiliser pour gater), puis une analyse
de la distribution sur trafic réel. Cette contrainte est structurante et détermine
les options ci-dessous.

### Pourquoi maintenant

L'audit qualité IVR (#297) a identifié ce chemin comme la première cause de
réponses « à côté » : l'utilisateur reçoit une réponse corpus confiante et fausse
au lieu d'un fallback DeepSeek ou d'une demande de clarification. C'est directement
un signal de dérive vision (`vision.md §10` : « le WER/qualité casse la confiance »).

---

## Questions posées avant la décision

1. **De quelles données dispose-t-on pour calibrer un seuil de distance ?**
   → Réponse Ruben (2026-08-14) : **logs prod exploitables** (des requêtes réelles
   WhatsApp existent). ⚠️ Nuance vérifiée dans le code : la **distance n'est pas
   encore loggée** — les logs contiennent les requêtes mais pas les distances
   pgvector. Une phase d'instrumentation est donc un prérequis à toute calibration.

2. **Le seuil doit-il vivre dans le code ou en config ?**
   → `constraints.md §1.2` tranche : **externalisé** (`config.py`), jamais hardcodé.

3. **Où placer le gating : côté NLU (avant recherche) ou côté corpus (après
   recherche) ?** → étudié dans les options (ce sont deux plans complémentaires,
   pas exclusifs).

---

## Options étudiées

### Option A — Seuil sémantique post-recherche, exposé et gaté (recommandée, en 2 temps)

**Description.** Rendre la distance cosine visible et l'exploiter comme critère de
rejet, en deux phases pour respecter l'exigence « mesurer avant de fixer » :

- **Phase A1 — Instrumentation (observation, zéro gating).**
  - `_query_candidates()` : ajouter `embedding <=> CAST(:query_emb AS vector) AS distance`
    au `SELECT` (l'`ORDER BY` existe déjà, coût nul supplémentaire côté index).
  - Propager `distance` dans les `rows` jusqu'à `_best_result_pg`, et **logger** la
    distance du `best` retenu (`logger.info("[VDB-PG] best=%s distance=%.4f ...")`).
  - **Aucun changement de comportement** : on observe la distribution des distances
    sur trafic réel (1–2 semaines), séparément pour les bons vs mauvais matches
    (annotation légère a posteriori par Ruben sur un échantillon).
- **Phase A2 — Gating calibré.**
  - Introduire `IVR_MAX_SEMANTIC_DISTANCE` (float, **externalisé `config.py`**),
    calibré sur la distribution collectée en A1 (p.ex. le point de séparation entre
    la masse « bons matches » et la queue « hors-sujet »).
  - Dans `chercher_reponse_ivr()` : si `best` a une `distance > IVR_MAX_SEMANTIC_DISTANCE`,
    retourner `None` → la cascade passe à DeepSeek (ou clarification).
  - Remplacer le hardcode `MIN_CONFIDENCE_THRESHOLD = 0.2` par un settings
    `NLU_MIN_CONFIDENCE` (même migration config, sujet #297 point 1).

**Avantages.**
- Exploite la donnée qui existe déjà en base (embeddings) sans nouveau modèle.
- Le seuil est **calibré sur mesure réelle**, pas deviné (respecte `constraints.md §5`).
- Réversible : un seuil très permissif = comportement actuel ; on resserre progressivement.
- Sépare proprement « observer » de « décider » — pas de régression pendant A1.

**Inconvénients / coût.**
- 2 déploiements (instrumentation puis gating) + fenêtre d'observation (~2 semaines).
- Exige une annotation manuelle légère de Ruben (bons/mauvais matches) pour placer
  le seuil sans biais.
- La distance ivfflat est **approchée** (ANN) : le TOP-1 n'est pas garanti exact.
  Impact faible sur un seuil de rejet grossier, à noter (mitigation : `SET
  ivfflat.probes` si besoin de précision).

**Compatibilité contraintes.** ✔ Pas de hardcoding, ✔ mesuré avant fixé, ✔ réversible.

---

### Option B — Gating pré-recherche sur la confiance NLU seule

**Description.** Ne pas toucher au corpus ; utiliser la confiance NLU (déjà
calculée par `IntentClassifier.classify`) comme unique porte : si
`confidence < NLU_MIN_CONFIDENCE`, **ne pas** lancer `try_ivr_exact` du tout et
router directement vers DeepSeek/clarification. Externaliser le seuil en config.

**Avantages.**
- Le plus simple : un seul point de décision, aucune modification SQL.
- La confiance NLU est déjà disponible, aucune instrumentation nouvelle.
- Corrige le hardcode `0.2` (point 1 de #297).

**Inconvénients / coût.**
- **Ne corrige pas la cause racine** (point 2 de #297) : quand l'intent est
  correctement classé avec forte confiance mais que le corpus n'a pas de bonne
  entrée pour la formulation précise, l'IVR répond quand même à côté. La confiance
  NLU mesure « ai-je reconnu un intent », pas « le corpus a-t-il une bonne réponse ».
- La confiance NLU est un score maison à base de règles/keywords
  (`intent_classifier.py`), pas une probabilité calibrée → seuiller dessus reste
  fragile.

**Compatibilité contraintes.** ✔ Pas de hardcoding, ⚠ ne résout que la moitié du problème.

---

### Option C — Score composite (sémantique × validation × saison) + seuil

**Description.** Comme A (exposer la distance), mais au lieu d'un seuil de rejet
binaire, **fusionner** la similarité sémantique `(1 - distance)` dans le score de
`_best_result_pg` : `score = w_sem·sim + w_val·score_validation + bonus_saison`,
puis appliquer un plancher sur ce score composite. Poids externalisés en config.

**Avantages.**
- Modèle de ranking plus riche : un match sémantiquement moyen mais parfaitement
  validé + de saison peut battre un match sémantiquement proche mais générique.
- Un seul mécanisme gère à la fois le *ranking* et le *rejet*.

**Inconvénients / coût.**
- **Plusieurs hyperparamètres à calibrer** (`w_sem`, `w_val`, seuil) au lieu d'un
  seul → surface de calibration bien plus large, plus dur à valider sans biais,
  surtout avec peu de données annotées.
- Risque de sur-ingénierie (`constraints.md §3.1`) : on transforme un filtre de
  rejet en système de scoring pondéré avant d'avoir prouvé qu'un simple seuil ne
  suffit pas.
- Change le comportement de ranking existant (regression surface plus grande).

**Compatibilité contraintes.** ⚠ Risque de sur-ingénierie ; à réserver si le seuil
simple (A) se révèle insuffisant après mesure.

---

### Option D — Statu quo instrumenté (ne rien gater, seulement observer)

**Description.** Se limiter à la Phase A1 (exposer + logger la distance) et **ne
prendre aucune décision de gating** tant que la distribution n'est pas analysée.

**Avantages.** Zéro risque de régression ; produit la donnée qui manque.
**Inconvénients.** Ne corrige pas #297 à court terme (les réponses hors-sujet
continuent). N'est pas une solution, c'est un prérequis — d'où son intégration
**dans** l'Option A plutôt qu'en alternative.

---

### Comparatif

| Critère | A (seuil sémantique 2-temps) | B (confiance NLU) | C (score composite) | D (observer seul) |
|---|---|---|---|---|
| Corrige cause racine #297 (pt 2) | ✔ oui | ~ partiel | ✔ oui | ✘ non (prérequis) |
| Corrige hardcode seuil (pt 1) | ✔ oui | ✔ oui | ✔ oui | ✘ non |
| Calibration mesurée requise | 1 seuil | 1 seuil | ≥ 3 hyperparams | — |
| Risque de régression | Faible (gating en A2 seulement) | Faible | Moyen (ranking modifié) | Nul |
| Sur-ingénierie | Non | Non | Risque | Non |
| Délai avant effet | ~2 sem (observation) | Immédiat | ~2 sem + tuning | N/A |
| Réversibilité | Élevée (seuil permissif) | Élevée | Moyenne | Totale |

---

## Décision

**Option A retenue** (2026-08-14, Ruben) : seuil sémantique post-recherche,
exposé et gaté, en deux phases —

- **Phase A1 — Instrumentation (observation, zéro gating).** Exposer la distance
  cosine pgvector dans `_query_candidates()` / `_best_result_pg()` et la logger
  sur le `best` retenu. Aucun changement de comportement : on collecte la
  distribution réelle (bons vs mauvais matches, annotation légère de Ruben) avant
  toute décision de seuil.
- **Phase A2 — Gating calibré.** Introduire `IVR_MAX_SEMANTIC_DISTANCE`, calibré
  sur la distribution collectée en A1, comme critère de rejet dans
  `chercher_reponse_ivr()` : au-dessus du seuil, `None` → la cascade passe à
  DeepSeek/clarification.

**B intégrée comme sécurité peu coûteuse** : le hardcode `MIN_CONFIDENCE_THRESHOLD
= 0.2` est remplacé par un settings externalisé `NLU_MIN_CONFIDENCE`, qui coupe la
recherche IVR sous ce seuil (indépendamment du gating sémantique A2).

**C explicitement différée** : le score composite (sémantique × validation ×
saison) n'est envisagé que si la mesure A1 montre qu'un seuil de rejet simple ne
sépare pas proprement bons/mauvais matches — pour éviter une calibration
multi-paramètres non justifiée par la donnée.

Justification : A est la seule option qui attaque la cause racine (distance
jetée) tout en respectant « mesurer avant de fixer » ; B seule laisse le bug de
fond ; C introduit une calibration multi-paramètres avant d'avoir prouvé sa
nécessité (sur-ingénierie). Le hardcode `0.2` est corrigé dans tous les cas.

---

## Conséquences

- **Positives** : les réponses IVR hors-sujet peuvent enfin être rejetées au profit
  de DeepSeek/clarification ; les seuils passent en config (fin du hardcoding) ; la
  distance sémantique devient observable (utile aussi au dashboard ADR-0017, sans PII).
- **Négatives assumées** : fenêtre d'observation avant bénéfice ; dépendance à une
  annotation manuelle de Ruben pour placer le seuil sans biais ; la nature ANN de
  ivfflat rend le TOP-1 approché (impact faible sur un seuil grossier).
- **Migration / travail induit (si A acceptée)** :
  1. `config.py` : ajouter `IVR_MAX_SEMANTIC_DISTANCE` et `NLU_MIN_CONFIDENCE`.
  2. `corpus_service._query_candidates` : `SELECT ... AS distance` + propagation.
  3. `corpus_service._best_result_pg` / `chercher_reponse_ivr` : logger la distance
     (A1), puis gating (A2).
  4. `nlu_service` : remplacer l'attribut de classe par la lecture settings.
  5. Tests unitaires : rejet quand `distance > seuil`, pass quand `distance ≤ seuil`,
     seuil injecté (pas de dépendance à la vraie base).
- **Verrou futur** : une fois le seuil calibré et publié, tout changement du modèle
  d'embedding (`paraphrase-multilingual-MiniLM-L12-v2`) invalide la calibration →
  re-mesure obligatoire (à tracer ici en Historique).

## Références

- Code : `app/services/nlu/nlu_service.py:56,121-128` ;
  `app/services/corpus_service.py:144-232,240-294` ;
  `app/services/chat/ivr_searcher.py:36-52,72-165`.
- Index vectoriel : [ADR-0008](0008-plan-migration-chromadb-pgvector.md) (ivfflat, vector_cosine_ops).
- Contraintes : `docs/constraints.md §1.2` (hardcoding), `§5` (mesurer, pas deviner).
- Issue [#297](https://github.com/ouedraogoissouf2012/wourri/issues/297).

## Historique

- 2026-08-14 — rédaction (statut **proposé**). Option A recommandée, décision
  réservée à Ruben. Nuance factuelle relevée : les logs prod n'exposent pas encore
  la distance pgvector → phase d'instrumentation prérequise à toute calibration.
- 2026-08-14 — **accepté**. Ruben valide l'Option A (instrumentation A1 puis
  gating calibré A2 ; `NLU_MIN_CONFIDENCE` et `IVR_MAX_SEMANTIC_DISTANCE`
  externalisés en config ; Option C différée).
