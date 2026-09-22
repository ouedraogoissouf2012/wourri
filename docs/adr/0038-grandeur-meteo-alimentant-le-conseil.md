# ADR-0038 — Quelle grandeur météorologique alimente le conseil agricole

**Statut** : **accepté**
**Date** : 2026-09-17
**Auteur** : Claude (assistant IA)
**Valideur** : Issouf (ouedraogoissouf2012)
**Issue** : #517

---

## 1. Contexte

### 1.1 Le défaut constaté

Le moteur convertit trois mesures en une condition agronomique parmi six, puis
récite une phrase dioula validée nativement (ADR-0014). Les phrases et les
données ne parlent pas du même temps.

**Ce que les phrases affirment** — templates de `app/services/weather_conditions.py`,
validés par un locuteur natif :

| Condition | Dioula | Sens |
|---|---|---|
| `orage` | `sanfɛla **bɛ na**` | l'orage **vient** |
| `grosse_pluie` | `sanji **bɛ na**` | la pluie **vient** |
| `pluie_legere` | `sanji fɛrɛn **bɛ na**` | la pluie légère **vient** |
| `couvert` | `sanji **bɛ se ka na**` | la pluie **peut venir** |

Le marqueur `bɛ` + le verbe `na` (venir) place ces phrases au registre
**prospectif** : elles annoncent ce qui arrive.

**Ce que la donnée décrit** — `app/services/chat_service.py:93` appelle
`get_weather()`, qui ne demande que le bloc `current` d'Open-Meteo. Ce bloc
porte `interval: 900` : une mesure sur **quinze minutes** (vérifié par appel
réel le 2026-09-11).

Le moteur dit donc « la pluie vient » à partir d'une mesure de ce qui tombe
maintenant.

### 1.2 Ce que l'analyse initiale affirmait à tort

L'issue #517 et le registre des constats énoncent que « la donnée nécessaire —
`daily[0]` — est déjà récupérée puis jetée, aucun appel réseau supplémentaire ».

**C'est faux pour le chemin ordinaire.** `get_weather_forecast_tomorrow` — seule
fonction demandant le bloc `daily` — n'est appelée que depuis
`app/services/chat/meteo_responder.py:78`, dans la branche `TEMPS_DEMAIN`. Une
salutation ou une question météo sur aujourd'hui ne récupère jamais `daily`.

Le correctif proposé dans #517 supposait une donnée gratuite qui ne l'est pas.

### 1.3 Pourquoi le correctif proposé aurait aggravé le défaut

`daily[0]` est le **cumul de la journée entière**, pluie déjà tombée comprise.
Alimenter « la pluie **vient** » avec de la pluie tombée le matin déplace
l'erreur sémantique au lieu de la corriger — et modifie ce qu'une phrase
validée nativement affirme, sans repasser par la validation. ADR-0014 l'interdit.

### 1.4 Observation de terrain

Une mesure du 2026-09-10 sur Bouaké, dans la **même réponse API** :

| Bloc | Valeurs | Condition produite |
|---|---|---|
| `current` (13:15) — le seul lu | code 51, 0,10 mm | `pluie_legere` → « bon moment pour commencer les semis » |
| `daily[0]` — journée entière | code 95, 12,60 mm, proba 94 % | `orage` → « mettez à l'abri immédiatement » |

**Observation unique, non reproduite** : une tentative de re-mesure le
2026-09-17 a échoué (réseau indisponible). Elle illustre l'écart, elle ne le
quantifie pas.

### 1.5 Cadrage projet

- [`docs/vision.md`](../vision.md) — la latence bout-en-bout au-delà de 10 s
  rend le produit inutilisable ; le conseil doit être actionnable en zone rurale.
- [`docs/constraints.md`](../constraints.md) §1.2 — aucune donnée métier en dur :
  les seuils doivent être paramétrables.
- [`docs/constraints.md`](../constraints.md) §3.3 — aucune invention linguistique
  ni agronomique sans source.
- [ADR-0014](0014-promotion-corpus-v3-dioula-ci.md) — le dioula validé ne se
  réinterprète pas ; changer ce qu'une phrase affirme exige une re-validation.

---

## 2. Questions stratégiques et réponses

Posées avant toute proposition d'option, le 2026-09-17.

| Question | Réponse |
|---|---|
| À quelle échéance SODEXAM remplace-t-il Open-Meteo ? | **Pas d'accord à ce jour** ; on continue avec l'existant. |
| Un locuteur natif est-il mobilisable pour de nouvelles formulations ? | **Oui, sous quelques semaines.** |
| Les seuils (`> 5 mm`, `> 0 mm`) ont-ils une source agronomique ? | **Non — hérités, jamais sourcés.** |

### Ce que ces réponses impliquent

**Investir sur Open-Meteo est légitime.** Aucun remplacement à court terme :
un travail propre sur le fournisseur actuel servira plusieurs campagnes.

**La validation native n'est pas un verrou absolu**, mais elle a un coût de
délai et constitue une ressource rare — à dépenser là où elle produit le plus.

**Le point décisif : les seuils ne sont pas sourcés aujourd'hui non plus.**
`> 5 mm` sur quinze minutes n'a pas davantage de fondement agronomique que sur
une journée. Toute option déplaçant la fenêtre temporelle rend cette dette
**visible**, elle ne la crée pas. Aucune option ne peut donc être écartée au
motif qu'« elle obligerait à recalibrer » : le calibrage manque déjà.

---

## 3. Options étudiées

### Option A — Aligner la donnée sur les phrases

Alimenter les templates avec une **prévision à courte échéance** : pluie
attendue des prochaines heures jusqu'à la fin de journée, calculée depuis le
bloc `hourly` d'Open-Meteo.

**Mise en œuvre** : ajouter `hourly=precipitation,precipitation_probability,weather_code`
à la requête existante (même appel, pas un second) ; sommer de l'heure courante
à la fin de journée locale ; passer ce cumul à `classify_meteo`.

| Pour | Contre |
|---|---|
| Les phrases validées deviennent **exactes** — « la pluie vient » décrit bien ce qui vient | Charge utile en hausse : 24 valeurs horaires au lieu de 5 scalaires |
| **Aucune validation native requise** — la ressource rare reste disponible ailleurs | Seuils à recalibrer pour la nouvelle fenêtre |
| Répond à la question que l'agriculteur se pose : « puis-je semer / dois-je bâcher ? » | Contrat d'acquisition modifié |
| Un seul appel réseau, cache inchangé | Fenêtre à choisir (fin de journée ? 6 h ? 12 h ?) — paramètre de plus |

### Option B — Aligner les phrases sur la donnée

Passer au cumul journalier `daily[0]` et **commander de nouveaux templates** en
registre rétrospectif (« aujourd'hui il est tombé… »).

| Pour | Contre |
|---|---|
| Grandeur agronomique classique, comparable aux bulletins décadaires | **Consomme la validation native** — ressource rare, délai de semaines |
| Cohérent avec la demande SODEXAM (bloc C, agrégats) | Un conseil rétrospectif est **moins actionnable** : l'agriculteur agit sur ce qui vient |
| Aucun bloc supplémentaire dans la requête | Le cumul du jour mélange passé et futur — ambigu à 18 h |
| | Seuils à recalibrer également |

### Option C — Distinguer l'état et la prévision

Conserver `current` pour décrire l'état présent, et introduire un **second jeu
de conditions** prospectives alimenté par la prévision. Deux familles de
templates, deux registres.

| Pour | Contre |
|---|---|
| Sémantiquement le plus juste : chaque phrase décrit ce qu'elle mesure | **Double le corpus météo** : 6 conditions deviennent 12 |
| Permet « il pleut, et ça va continuer » | Consomme la validation native pour 6 nouvelles phrases |
| | Complexité de composition : quelle famille servir quand ? |
| | Sur-dimensionné au vu des 4 entrées de corpus concernées |

### Option D — Ne rien changer au moteur

Corriger l'issue #517 et le registre, qui portent une analyse erronée, et
laisser le comportement en l'état.

| Pour | Contre |
|---|---|
| Risque nul, aucune régression possible | Le défaut sémantique demeure : le service affirme ce qu'il ne mesure pas |
| Honnête : l'analyse d'origine était fausse | « Bon moment pour semer » peut être servi un jour d'orage annoncé |
| | La dette de calibrage reste invisible |

---

## 4. Comparatif

| Critère | A — donnée vers phrases | B — phrases vers donnée | C — deux registres | D — statu quo |
|---|:---:|:---:|:---:|:---:|
| Justesse sémantique des phrases servies | **haute** | haute | **très haute** | faible |
| Actionnabilité pour l'agriculteur | **haute** | moyenne | haute | faible |
| Validation native consommée | **aucune** | 6 phrases | 6 phrases | aucune |
| Délai externe sur le chemin critique | **aucun** | semaines | semaines | aucun |
| Contrat d'acquisition modifié | oui | non | oui | non |
| Seuils à recalibrer | oui | oui | oui | non |
| Complexité ajoutée au moteur | faible | **nulle** | élevée | **nulle** |
| Reste valable après bascule SODEXAM | oui (grandeur nommée) | oui | oui | — |

---

## 5. Décision

### **Option A retenue** — aligner la donnée sur les phrases

Validée par Issouf le 2026-09-17.

Le moteur alimentera les templates prospectifs avec la **précipitation attendue
sur la fenêtre à venir**, et non plus avec la mesure instantanée sur quinze
minutes.

**Deux postures actées avec la décision :**

| Sujet | Choix | Motif |
|---|---|---|
| Seuils non sourcés | **Dette tracée, livraison non bloquée** | Le calibrage actuel n'est pas meilleur ; attendre laisserait un défaut sémantique avéré en production. Une issue de sourçage CNRA/ANADER est ouverte en parallèle. |
| Fenêtre temporelle | **De l'heure courante à la fin de journée locale** | Correspond à l'horizon de décision d'une journée de travail. Valeur configurable, donc ajustable sans redéploiement de code. |

Ces deux points restent **explicitement non validés agronomiquement** et sont
portés comme dette dans la section Conséquences.

### Justification retenue

Trois raisons, dans l'ordre de poids.

**Elle rend justes des phrases déjà validées.** C'est la seule option qui
corrige l'erreur sémantique **sans rien demander au locuteur natif** : les
chaînes existantes cessent d'être approximatives et deviennent exactes. La
validation native, ressource rare, reste disponible pour les sujets qui n'ont
pas d'alternative — le registre pronominal divergent (#526) ou le marqueur
`sini` absent des prévisions (#355).

**Elle sert la décision réelle de l'agriculteur.** Un conseil agricole porte
sur ce qui vient : semer, bâcher, traiter. Le cumul écoulé informe, il ne fait
pas agir.

**Elle survit à la bascule SODEXAM.** Le moteur consommerait une grandeur
nommée — « précipitation attendue sur la fenêtre à venir » — et non un bloc
propre à Open-Meteo. Cette grandeur devra être ajoutée à la demande SODEXAM,
qui ne la couvre pas encore : le bloc B n'offre qu'un cumul journalier à
horizon 7-10 jours.

### Ce que la recommandation ne règle pas

**Les seuils restent non sourcés.** L'option A ne crée pas cette dette, elle la
rend visible. Deux voies possibles, à trancher avec la décision :

- livrer avec les seuils marqués **dette tracée**, explicitement non validés,
  et ouvrir une issue de sourçage auprès du CNRA ou de l'ANADER ;
- bloquer la livraison jusqu'à obtention d'une source.

L'auteur recommande la première : le calibrage actuel n'est pas meilleur, et
attendre laisserait en production un défaut sémantique avéré.

**La fenêtre reste à choisir.** « Jusqu'à la fin de journée » est le candidat
naturel — il correspond à l'horizon de décision d'une journée de travail — mais
ce choix relève lui aussi de l'agronomie et doit figurer dans la même demande
de sourçage.

---

## 6. Conséquences

### Si l'option A est retenue

**Acquisition** — la requête `get_weather()` gagne un bloc `hourly`. Le document
[`CONTRAT_API_OPEN_METEO.md`](../CONTRAT_API_OPEN_METEO.md) devra être mis à
jour : son §2.1 affirme aujourd'hui que le service demande cinq variables.

**Format pivot** — une clé s'ajoute (précipitation attendue sur la fenêtre). Le
format reste stable pour les consommateurs existants.

**Tests** — les 23 tests météo verrouillent `classify_meteo` sur des valeurs,
**aucun ne teste quelle grandeur lui est passée**. Ils resteraient verts après
le changement. Il faut donc ajouter les tests qui manquent : ceux qui gardent
la provenance de la donnée, pas seulement le seuil.

**Demande SODEXAM** — le bloc B devra recevoir une ligne supplémentaire pour la
prévision infra-journalière.

**Réversibilité** — élevée. Le changement est localisé dans l'acquisition et le
choix de la grandeur passée à `classify_meteo` ; un `git revert` suffit.

### Si l'option D est retenue

L'issue #517 et le registre des constats doivent être corrigés : ils affirment
qu'une donnée gratuite existe, ce qui est faux hors branche « demain ».

### Dans tous les cas

L'affirmation erronée de #517 est à rectifier, indépendamment de l'option
choisie.

---

## 7. Historique

| Date | Évolution |
|---|---|
| 2026-09-17 | Rédaction initiale. Statut **proposé**, décision TBD. |
| 2026-09-17 | **Option A validée** par Issouf. Statut **accepté**. Seuils portés en dette tracée ; fenêtre fixée à « heure courante → fin de journée locale », configurable. |
