# ADR-0039 — Politique de réponse du LLM : faits vérifiables, escalade préventive et sas de validation

**Statut** : **accepté**
**Date** : 2026-09-24
**Auteur(s)** : Claude (assistant) sous direction de Ouedraogo Issouf
**Valideur** : Ouedraogo Issouf — **accepté le 2026-09-24** (option B, bascule immédiate, message avec promesse d'expert)
**ADRs liés** : [ADR-0015](0015-strategy-pattern-cascade-chat-et-anglais.md) (cascade — **amendé** par le présent ADR), [ADR-0028](0028-refonte-qualite-ivr-seuils-semantiques.md) (seuils IVR), [ADR-0031](0031-moteur-amelioration-linguistique.md) (sas de validation), [ADR-0019](0019-feedback-c3-revue-native.md) (revue native), [ADR-0038](0038-grandeur-meteo-alimentant-le-conseil.md) (météo)

---

## Contexte

### Ce qui déclenche la décision

Le **23 septembre 2026**, démonstration terrain à **Bodokro** (région de Bouaké) en
présence de la direction. Retour de la direction : l'application **« hallucine »** sur
plusieurs questions. L'analyse des journaux de production de la journée
(`RAPPORT_TESTS_2026-09-23.md`, 76 interactions, 61 requêtes) confirme des réponses
inexactes et en identifie la source : **le LLM (DeepSeek) répond directement aux
questions non couvertes par le corpus validé**.

Le propriétaire du produit affirme qu'il était convenu que **le LLM ne réponde pas
directement**, et que toute question non couverte soit **remontée puis validée** avant
d'être intégrée au corpus. **Cet accord n'a jamais été gravé dans un ADR** et **n'est pas
ce qui est déployé** (§ suivant). L'ADR-0007 « Choix LLM conversationnel » est listé au
`README.md` des ADR comme **planifié (P3)** — **le fichier n'existe pas**. Il n'existe
donc à ce jour **aucune décision écrite encadrant le rôle du LLM**.

### État actuel — vérifié dans le code déployé (`origin/APIPy`)

**1. Le LLM est le dernier niveau de cascade et sa réponse part à l'agriculteur.**

- `app/services/chat/handlers/dioula_handler.py:147` — `return await try_deepseek_dioula(...)`
  (Niveau 3, après IVR exact → IVR concept → météo/date/culture-zone).
  `BothHandler` hérite de `DioulaHandler` sans override → **le mode `both` suit ce chemin**.
- `app/services/chat/handlers/french_handler.py:114` — `response_text = await chat_with_deepseek(...)`.
  ⚠️ Le `FrenchHandler` **n'a aucune cascade IVR** (docstring du fichier : « Pas de cascade
  IVR : le corpus n'a pas de chemin direct FR-seulement »). En mode français, **le LLM est le
  chemin par défaut, par conception**, et non un dernier recours.

**2. La remontée vers le sas de validation existe mais est REACTIVE, pas préventive.**

`app/services/improvement_queue.py` (ADR-0031 / #431) implémente la file d'amélioration.
Son **seul** appelant côté conversation est `app/routers/feedback.py` :

```python
# ADR-0031 / #431 : 👎 → tâche Bronze (file équivalente). Jamais de corpus.
from app.services.improvement_queue import enqueue_improvement_task
```

Autrement dit : une question n'est remontée **que si l'agriculteur appuie sur 👎**, et
**après** que le LLM a déjà répondu. Le schéma de publication d'ADR-0031
(`👎 / ingest / grand locuteur → tâche Bronze → écran locuteur → file admin → Or/Production`)
**ne comporte aucune branche « question non couverte »**.

**3. Certaines questions factuelles atteignent le LLM au lieu du moteur de données.**

Le 23/09, des questions météo localisées — « *quand il aura la pluie dans la localité
d'Aberkouadjokro* », « *es ce que les pluies continueront jusqu'à fin octobre* » — ont été
servies par `deepseek_french`. **Le LLM ne dispose d'aucune donnée météo** : sa réponse est
nécessairement inventée. C'est le cas d'hallucination le plus grave car il porte sur une
**décision agricole datée** (semer, traiter, récolter).

> **Ce qui est établi vs ce qui ne l'est pas (rigueur).** Le NLU **classe correctement** ces
> deux phrases en `QUESTION_METEO_AGRICOLE` (vérifié en rejouant `ConceptExtractor` +
> `IntentClassifier` sur le texte exact). La cause n'est donc **pas** une mauvaise
> classification. L'hypothèse restante — **non prouvée faute de journalisation** — est que
> `build_meteo_response()` a renvoyé `None` (donnée météo/prévision indisponible au moment
> de l'appel) et que **la cascade est alors retombée sur le LLM**. Le même jour à 11:48, une
> autre question météo a bien été servie par `meteo_prevision` : le chemin déterministe
> fonctionne, mais **son échec bascule silencieusement vers le LLM**.
>
> **C'est exactement le défaut que le présent ADR corrige** : l'indisponibilité d'une donnée
> factuelle ne doit jamais se traduire par une réponse inventée.

**4. Angle mort d'observabilité — le chemin LLM français n'enregistre pas l'intent.**

`french_handler.py` renvoie `meta={"source": "deepseek_french"}` — **sans clé `intent`**
(contrairement à `deepseek_router.py:69` qui, lui, renvoie `meta={"intent": nlu.intent, …}`).
Conséquence mesurée : **les 21 lignes LLM du 23/09 portent `intent = NULL`** dans
`admin_request_metrics`, alors que toutes les lignes déterministes portent un intent réel.
**On ne peut donc pas savoir a posteriori quelles questions ont été envoyées au LLM ni
pourquoi.** Cet angle mort doit être comblé en même temps que la politique, sinon l'effet
de la décision restera invérifiable.

### Ce que le projet a déjà décidé et qui cadre le sujet

- **ADR-0031** grave : « **Un LLM ne déclare jamais une phrase correcte.** » Le principe
  existe donc déjà — mais il n'a été appliqué qu'à **l'écriture du corpus**
  (`import_corpus_from_convex.py` filtre : pas Or+ → pas d'écriture), **jamais à la
  réponse servie en direct à l'agriculteur**.
- **`docs/constraints.md` §3.3** — « Pas d'invention linguistique » : aucun contenu
  dioula non validé ne doit être servi.
- **ADR-0028** a déjà traité le symptôme voisin côté corpus (l'IVR répondait hors-sujet)
  en introduisant un **seuil de rejet sémantique** — la même philosophie (« mieux vaut ne
  pas répondre que mal répondre ») s'applique ici au niveau supérieur.

### Mesure — quelle part du trafic est concernée (donnée décisive)

Table `admin_request_metrics`, endpoint `/api/chat`, production :

| Source | 23 sept. (démo) | 30 derniers jours |
|---|---:|---:|
| `deepseek_french` | 15 | 28 (31,8 %) |
| `deepseek_open` (dioula/both) | 6 | 7 (8,0 %) |
| **Total LLM** | **21 / 39 = 53,8 %** | **35 / 88 = 39,8 %** |
| `ivr_exact` (corpus validé) | 12 | 33 (37,5 %) |
| `culture_zone` | 4 | 7 (8,0 %) |
| `meteo_prevision` + `meteo_actuel` | 1 | 9 (10,2 %) |
| `clarification_culture` | 1 | 3 (3,4 %) |

**Fait structurant : le LLM porte aujourd'hui ~40 % des réponses (54 % le jour de la
démo).** Toute coupure sèche transforme ces 40 % en « je ne peux pas répondre ». C'est la
contrainte centrale de cette décision : le problème n'est pas seulement *« le LLM
invente »*, c'est *« le corpus validé ne couvre que ~60 % des questions »*.

> **Limite d'honnêteté sur les données** : le **texte des réponses n'est pas journalisé**
> (seuls `intent`, `source`, `status_code`, `duration_ms` le sont). Le taux réel
> d'hallucination **n'est donc pas mesurable a posteriori** ; on raisonne sur la
> *possibilité* d'hallucination par catégorie de question, pas sur un taux observé.

---

## Questions posées avant la décision

1. **Que reçoit l'agriculteur quand aucune réponse validée n'existe ?** Une promesse de
   réponse d'expert (⇒ engagement de service : il faut une boucle humaine **et** un canal
   de retour vers l'agriculteur), ou un refus poli sans promesse ?
2. **Coupe-t-on le LLM partout, ou seulement sur les questions à réponse vérifiable**
   (météo, prix, dates, calendrier local) où il ne *peut pas* savoir ?
3. **Bascule immédiate, ou mode « observation » d'abord** pour mesurer l'impact réel sur
   la couverture avant de dégrader l'expérience ?
4. Le mode **français** (où le LLM est le chemin par défaut, sans cascade IVR) est-il
   traité comme le mode dioula/both, ou conserve-t-il un régime distinct ?

**Réponses du valideur (Ouedraogo Issouf, 2026-09-24)** :

- **Q1 → avec promesse d'expert.** L'agriculteur reçoit « ta question est transmise à un
  expert, tu auras une réponse ». ⚠️ Conséquence assumée et **tracée** : cette formulation
  crée un **engagement de service**. La boucle de retour vers l'agriculteur **n'existe pas
  aujourd'hui** et devient un **travail induit obligatoire** (cf. §Conséquences).
- **Q2 → seulement sur les questions à réponse vérifiable** (option B).
- **Q3 → bascule immédiate**, en une seule livraison. Pas de phase d'observation préalable
  (option D écartée comme méthode) : la correction est attendue par la direction.
- **Q4 → même régime pour le mode français.** Le garde s'applique dans les deux handlers.
  En mode français, les questions météo disposent déjà d'un chemin déterministe
  (`meteo_responder`, câblé par #514) ; le conseil général continue de passer par le LLM
  avec escalade, comme en dioula/both.

---

## Options étudiées

### Option A — Coupure totale du LLM + escalade préventive systématique

- **Description** : si aucun niveau déterministe (corpus IVR, culture-zone, météo, date)
  ne répond, on **n'appelle pas le LLM**. L'agriculteur reçoit un message d'accusé
  (« ta question est transmise à un expert ») et la question est enfilée dans
  `improvement_queue` (tâche Bronze) pour validation native puis intégration au corpus.
- **Avantages** : risque d'hallucination **nul** ; applique littéralement le principe
  ADR-0031 ; alimente le corpus de façon systématique (chaque question non couverte
  devient une tâche) ; coût LLM nul.
- **Inconvénients (mesurés)** : **~40 % des questions** (54 % le jour de la démo) n'ont
  plus de réponse immédiate. En mode **français**, où le LLM est le chemin par défaut,
  la dégradation est quasi totale. Crée un **engagement de service** (répondre plus tard)
  qu'aucun canal ne sert aujourd'hui : `improvement_queue` alimente l'atelier **linguistique**,
  pas une boucle « répondre à cet agriculteur ».
- **Coût** : dev faible (un garde en fin de cascade) ; **risque produit élevé** ;
  charge humaine de validation non dimensionnée.
- **Compatibilité contraintes** : parfaite sur §3.3 (aucune invention) ; contraire à la
  promesse produit de `vision.md` (« information agronomique aux agriculteurs »).

### Option B — Garde sur les faits vérifiables + escalade préventive (chirurgical)

- **Description** : distinguer deux familles de questions.
  1. **Faits vérifiables** (météo d'une localité, date, prix, calendrier local) : le LLM
     n'y a **jamais** accès à la vérité → **interdiction d'appel**. Ces questions sont
     routées vers le moteur de données (Open-Meteo, calendrier, `date_responder`) ; si la
     donnée manque, **refus explicite + escalade**, jamais de LLM.
  2. **Conseil agronomique général** hors corpus : le LLM répond encore, **mais** la
     question est **systématiquement escaladée** (`improvement_queue`) pour produire une
     réponse validée qui la remplacera au prochain passage.
- **Avantages** : supprime la **catégorie la plus grave** d'hallucination (celle de la
  démo : météo localisée) sans détruire la couverture ; le corpus grossit à chaque
  question non couverte, donc la part LLM **décroît mécaniquement** ; compatible avec le
  mode français.
- **Inconvénients** : le LLM peut encore se tromper sur l'agronomie générale (moins
  visible, moins datable, mais réel) ; nécessite de **définir et maintenir la liste des
  familles « faits vérifiables »** (risque de hardcoding → externaliser, `constraints.md` §1.2).
- **Coût** : dev moyen (garde + classifieur de famille + câblage escalade) ; risque
  produit faible.
- **Compatibilité contraintes** : bonne. Ne sert aucune donnée factuelle inventée.

### Option C — Le LLM répond, mais la réponse est marquée « non validée » + escalade

- **Description** : aucune coupure. Toute réponse LLM est préfixée/suffixée d'une mention
  (« réponse non encore validée par un expert ») et systématiquement escaladée.
- **Avantages** : zéro perte de couverture ; transparence ; alimente le corpus.
- **Inconvénients** : **ne règle pas le reproche de la direction** — une prévision de pluie
  inventée reste une prévision inventée, et un avertissement **en audio** est très faible
  pour un agriculteur peu alphabétisé qui écoute une note vocale. Alourdit chaque message.
- **Coût** : dev faible. **Risque de crédibilité élevé** (on documente le défaut au lieu
  de le corriger).
- **Compatibilité contraintes** : faible sur l'esprit d'ADR-0031.

### Option D — Mode observation d'abord, puis bascule calibrée

- **Description** : phase 1, on **journalise** ce qui *serait* bloqué (famille de question,
  disponibilité d'une réponse déterministe) **sans changer l'expérience** ; on mesure
  pendant N jours la couverture réelle par famille. Phase 2 : on active la coupure avec un
  périmètre calibré sur la mesure.
- **Avantages** : décision de périmètre fondée sur des **chiffres**, pas sur une intuition ;
  rend enfin mesurable le taux de recours au LLM par famille ; sans régression pendant la
  mesure.
- **Inconvénients** : **ne corrige rien pendant la phase 1** — inacceptable seul, alors que
  la direction attend une correction.
- **Coût** : dev faible ; délai.
- **Compatibilité contraintes** : neutre. C'est une **méthode de déploiement**, pas une
  politique — combinable avec A ou B.

### Comparatif

| Critère | A — coupure totale | B — faits vérifiables | C — marquage | D — observation |
|---|---|---|---|---|
| Hallucination sur faits datés (météo) | supprimée | **supprimée** | subsiste | subsiste (phase 1) |
| Hallucination agronomique générale | supprimée | subsiste (escaladée) | subsiste | subsiste |
| Couverture perdue immédiatement | **~40 %** (54 % en démo) | **~0 %** | 0 % | 0 % |
| Mode français (LLM par défaut) | cassé | préservé | préservé | préservé |
| Alimente le corpus validé | oui (fort) | oui (fort) | oui | non |
| Engagement « réponse d'expert » à tenir | **oui, non outillé** | optionnel | non | non |
| Répond au reproche de la direction | oui | **oui** | non | pas tout de suite |
| Coût dev | faible | moyen | faible | faible |
| Réversible | oui (flag) | oui (flag) | oui | oui |

---

## Décision

**Option retenue** : **B — Garde sur les faits vérifiables + escalade préventive**,
en **bascule immédiate** (une seule livraison, sans phase d'observation), avec un message
d'accusé **portant promesse d'une réponse d'expert**.
*Arbitrée par Ouedraogo Issouf le 2026-09-24.*

**Ce que cela signifie concrètement** :

1. **Familles à réponse vérifiable** (météo, date, prix, calendrier local) : le LLM n'est
   **jamais** appelé. La question va au moteur déterministe ; si la donnée manque →
   **refus explicite + escalade**, jamais d'invention.
2. **Conseil agronomique général hors corpus** : le LLM répond encore, mais la question est
   **systématiquement escaladée** (`improvement_queue`) pour produire une réponse validée
   qui la remplacera au prochain passage.
3. **Message d'accusé** : « ta question est transmise à un expert, tu auras une réponse ».
4. **Même régime en mode français** et en dioula/both.

**Justification** (fondée sur la mesure du §Contexte) :

- Elle supprime **la catégorie d'hallucination qui a provoqué le reproche** (faits datés
  et localisés, dont la météo) — celle où le LLM ne peut structurellement pas avoir raison.
- Elle **ne détruit pas 40 % de la couverture**, contrairement à l'option A. La coupure
  totale est souhaitable **comme cible**, mais elle n'est atteignable qu'une fois le corpus
  suffisamment couvrant : l'escalade préventive de l'option B est précisément le mécanisme
  qui y conduit.
- Elle est **réversible** et pilotable par configuration (pas de magic number en dur,
  `constraints.md` §1.2).

> L'option A reste la **cible** : quand la couverture du corpus validé le permettra
> (mesurable via `admin_request_metrics.source`), le périmètre du garde pourra être
> élargi jusqu'à la coupure totale, **sans nouvelle refonte** — c'est le même point
> d'application dans la cascade.

---

## Conséquences

- **Positives** : plus aucune réponse inventée sur une donnée factuelle datée ; chaque
  question non couverte devient une **tâche de validation** (le corpus croît au lieu de
  stagner) ; la part LLM devient un **indicateur de maturité** suivi dans le temps.
- **Négatives assumées** : le LLM continue de répondre sur l'agronomie générale hors
  corpus (option B) — c'est une **dette explicitement tracée**, levée progressivement par
  l'escalade ; certaines questions factuelles recevront un refus explicite là où elles
  recevaient (faussement) une réponse.
- **Migration / travail induit** :
  - point d'application **unique** en fin de cascade (`dioula_handler` / `french_handler`),
    en **extension OCP** — la logique existante des niveaux déterministes n'est pas réécrite ;
  - classification des familles « faits vérifiables » **externalisée** (pas de liste en dur) ;
  - branchement de `improvement_queue.enqueue_improvement_task` sur le chemin « non couvert »
    (aujourd'hui branché seulement sur 👎) ;
  - **échec de donnée factuelle ≠ repli LLM** : quand un répondeur déterministe d'une famille
    vérifiable renvoie `None` (donnée indisponible), la cascade doit produire un **refus
    explicite + escalade**, et non passer au LLM (cause probable du cas météo du 23/09) ;
  - **combler l'angle mort d'observabilité** : ajouter `intent` au `meta` du chemin
    `deepseek_french` (§Contexte point 4), sans quoi l'effet de cette décision restera
    invérifiable ;
  - journaliser la famille + la décision du garde pour rendre la couverture mesurable.
  - **Rollback** : flag de configuration → retour au comportement actuel sans redéploiement de code.
- 🔴 **Travail induit OBLIGATOIRE issu de l'arbitrage Q1 (promesse d'expert)** — le message
  « tu auras une réponse » **engage le produit**. Il manque aujourd'hui **la boucle de
  retour** : `improvement_queue` alimente l'atelier de validation (ADR-0031), mais **rien
  ne renvoie la réponse validée à l'agriculteur qui a posé la question**. À construire :
  (a) conserver le lien question ↔ demandeur (identifiant anonymisé déjà porté par
  `enqueue_improvement_task`) ; (b) un canal de notification WhatsApp une fois la réponse
  promue Or/Production ; (c) un délai annoncé tenable. **Tant que (b) n'existe pas, la
  promesse n'est pas tenue** — c'est une **dette tracée**, à traiter en priorité après la
  présente livraison. Le repli sans risque est une formulation sans promesse.
- **Verrous futurs** : le périmètre « faits vérifiables » devient un point de décision
  permanent — toute nouvelle famille de questions factuelles (prix de marché, intrants…)
  devra y être ajoutée explicitement, sinon elle retombe silencieusement sur le LLM.

---

## Références

- Analyse de la démonstration du 23/09/2026 : `RAPPORT_TESTS_2026-09-23.md` (journaux prod, 76 interactions)
- Note à la direction : `WOURI-note-demo-23sept` (4 p.)
- Mesures : table `admin_request_metrics`, production, 23/09 et 30 derniers jours
- Code vérifié : `dioula_handler.py:147`, `french_handler.py:114`, `routers/feedback.py` (appel `enqueue_improvement_task`), `improvement_queue.py`
- Contraintes : `docs/constraints.md` §1.2 (pas de hardcoding), §3.3 (pas d'invention)
- Produit : `docs/vision.md` (cascade documentée ligne « NLU → IVR exact → IVR concept → DeepSeek+NLLB → fallback »)
- ADR-0007 « Choix LLM conversationnel » : **planifié au README, jamais rédigé** — le présent ADR couvre la politique de réponse ; le choix du fournisseur reste à documenter.

## Historique

- 2026-09-24 — rédaction initiale (statut **proposé**).
- 2026-09-24 — **accepté** par Ouedraogo Issouf : option **B**, bascule **immédiate** (option D écartée), message d'accusé **avec promesse d'expert** (dette de la boucle de retour tracée en §Conséquences), même régime pour le mode français.
- 2026-10-05 — **implémenté** par #550 / PR #551 (mergée, déployée) : `app/services/chat/llm_guard.py` + câblage `dioula_handler` / `french_handler`, réglages `LLM_GUARD_ENABLED` et `LLM_FACTUAL_INTENTS`, `intent` ajouté au `meta` du chemin `deepseek_french` (angle mort §Contexte 4). Périmètre initial des familles vérifiables : `QUESTION_METEO_AGRICOLE`, `QUESTION_VENTE`, `QUESTION_DATE`.
