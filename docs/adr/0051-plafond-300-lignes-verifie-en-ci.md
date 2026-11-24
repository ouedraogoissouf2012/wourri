# ADR-0051 — Plafond de 300 lignes par fichier, vérifié en intégration continue

**Statut** : accepté
**Date** : 2026-11-17
**Décideur** : Ouedraogo Issouf
**Lié à** : [ADR-0050](0050-source-unique-donnees-linguistiques.md) — même motif : rendre une règle exécutoire

---

## 1. Contexte

### 1.1 La règle existe, mais nulle part où elle engage

Le plafond de 300 lignes figure dans le protocole de revue du projet, qui demande
de décomposer « les fichiers qui passent au-dessus de 300 lignes ».

Il ne figure **ni dans `docs/constraints.md`**, qui porte les règles non
négociables, **ni dans aucun contrôle automatique**. Il n'a donc jamais engagé
personne.

### 1.2 L'état mesuré au 2026-11-17

| Mesure | Valeur |
|---|---|
| Fichiers de code (hors tests, hors dépendances) | 197 |
| Lignes totales | 28 420 |
| Fichiers au-dessus de 300 lignes **physiques** | **19** (9,6 %) |
| Le plus long | `scripts/generate_culture_validation_pdf.py` — 749 lignes |

Les dix plus longs :

| Fichier | Lignes | Nature |
|---|---|---|
| `scripts/generate_culture_validation_pdf.py` | 749 | script hors ligne |
| `app/services/corpus_service.py` | 668 | **service applicatif** |
| `scripts/prevalidation_rules.py` | 628 | script hors ligne |
| `scripts/build_culture_validation_drafts.py` | 621 | script hors ligne |
| `scripts/generate_issue_40_hevea_validation_pdf.py` | 561 | script hors ligne |
| `app/services/stt_whisper.py` | 463 | **service applicatif** |
| `app/main.py` | 429 | **point d'entrée** |
| `app/services/admin_metrics.py` | 425 | **service applicatif** |
| `scripts/import_corpus_from_convex.py` | 420 | script hors ligne |
| `app/services/weather.py` | 379 | **service applicatif** |

Observation utile : **cinq des dix plus longs sont des scripts hors ligne**, qui
ne tournent jamais en production. Le coût de maintenance n'y est pas le même que
dans un service appelé à chaque message d'agriculteur.

### 1.3 Pourquoi la règle compte

La demande qui a motivé cet ADR est explicite : « on ne peut pas passer notre vie
à refaire à chaque fois que nous voulons apporter des modifications ou des
ajouts ». Un fichier long concentre les motifs de changement : toute évolution y
touche, les conflits s'y multiplient, et la relecture n'y est plus sérieuse.

---

## 2. Question posée et réponse

| Question | Réponse du 2026-11-17 |
|---|---|
| Comment appliquer le plafond ? | **Plafond strict vérifié en intégration continue** |

Cette réponse a une conséquence de séquencement qui doit être tranchée ici :
**brancher le contrôle aujourd'hui rendrait la CI rouge en permanence**, puisque
19 fichiers dépassent déjà. L'ordre des opérations fait donc partie de la
décision.

---

## 3. Options de séquencement

### Option A — Découper les 19 fichiers, puis brancher le contrôle

| | |
|---|---|
| Charge estimée | 12 à 15 j |
| CI rouge pendant | aucun |
| Risque | élevé — découper `corpus_service.py` ou `weather.py` touche des chemins servis en production, sans besoin fonctionnel |
| Effet immédiat | aucun : la règle n'engage personne pendant trois semaines |

### Option B — Brancher le contrôle avec une liste d'exemptions qui ne peut que diminuer

Le contrôle échoue si un fichier **non listé** dépasse 300 lignes, ou si un
fichier listé **s'allonge encore**. La liste des 19 est figée, inscrite comme
dette, et ne peut jamais s'agrandir.

| | |
|---|---|
| Charge estimée | 0,5 j pour le contrôle, puis résorption au fil des PR |
| CI rouge pendant | aucun |
| Risque | faible — aucun fichier n'est touché sans besoin |
| Effet immédiat | **total sur le code neuf** : aucun nouveau dépassement n'est possible |

### Option C — Plafond strict immédiat, sans exemption

| | |
|---|---|
| Charge estimée | 0,5 j |
| CI rouge pendant | jusqu'à la fin du découpage, soit deux à trois semaines |
| Risque | **très élevé** — une CI rouge en permanence cesse d'être lue, et le projet perd son seul garde-fou existant |

---

## 4. Comparatif

| Critère | A — découper d'abord | B — exemptions décroissantes | C — strict immédiat |
|---|---|---|---|
| Empêche tout nouveau dépassement | dans 3 semaines | **immédiatement** | immédiatement |
| CI exploitable pendant la transition | oui | **oui** | non |
| Touche du code en production sans besoin | **oui** | non | oui |
| Charge avant effet | 12 à 15 j | **0,5 j** | 0,5 j |
| Risque de voir la règle abandonnée | moyen | faible | **élevé** |

---

## 5. Points à trancher avec la décision

1. **Le périmètre.** Le plafond s'applique-t-il aux tests ? Un fichier de tests
   long n'a pas le même coût qu'un service long, et les suites de ce projet sont
   volontairement bavardes en commentaires d'intention.
2. **Les scripts hors ligne.** Cinq des dix plus longs n'ont jamais tourné en
   production. Même plafond, ou plafond distinct ?
3. **Les fichiers générés.** `corpus_ivr_bci.json` fait 2 700 lignes. Les données
   ne sont pas du code : elles doivent être explicitement hors périmètre, faute
   de quoi la règle devient absurde.
4. **Ce qui compte comme ligne.** Lignes physiques, ou lignes hors commentaires et
   hors lignes vides ? Compter les commentaires pénalise la pratique de
   documentation que ce projet cultive.

---

## 6. Décision

### **Option B retenue**, et le plafond porte sur les **lignes logiques**

Validée par Ouedraogo Issouf le 2026-11-17.

#### 6.1 Ce qui est compté

**Les lignes logiques** : hors commentaires, hors lignes vides, hors chaînes de
documentation au sens PEP 257 — la première instruction d'un module, d'une classe
ou d'une fonction. **Une chaîne SQL compte**, elle n'est pas de la documentation.
Le découpage est fait par le `tokenize` et l'`ast` de Python, pas par une
heuristique.

**En JavaScript et dans les composants Vue**, la règle est la même : hors
commentaires `//` et `/* */`, hors lignes vides. Un analyseur lexical reconnaît
les chaînes, les gabarits et les expressions régulières, afin qu'un `//` ou un
`/*` placé à l'intérieur de l'un d'eux ne soit pas pris pour un commentaire. Dans
un `.vue`, le bloc `template` ignore `<!-- -->`, le bloc `style` ignore `/* */`,
et les balises de bloc comptent. Le `.ts` est hors périmètre, et les fichiers
engendrés — `convex/_generated` — sont exclus comme toute donnée produite.

Cette règle doit être écrite, et pas seulement implémentée : vingt-sept fichiers
du périmètre sont en `.js` ou en `.vue`, dont un exempté et un à une ligne du
plafond. Un chiffre dont la méthode n'est pas publiée n'est pas opposable à
l'auteur d'une PR.

La mesure change la portée de la règle :

| Périmètre | Fichiers au-dessus de 300 |
|---|---|
| Code hors tests, lignes physiques | 19 sur 197 |
| Code hors tests, lignes logiques | 8 |
| **Périmètre décidé — tests inclus, lignes logiques** | **17** |

`app/config.py` fait 364 lignes physiques pour **96 logiques** : il est à 73 % de
commentaires. Compter le physique obligerait à découper un fichier dont le seul
tort est d'être bien documenté, et découragerait la pratique de documentation que
ce projet cultive. Le plafond doit sanctionner la complexité, pas l'explication.

#### 6.2 Le séquencement : option B

Le contrôle échoue si un fichier **non listé** dépasse 300 lignes logiques, ou si
un fichier **listé s'allonge** par rapport à la valeur inscrite. La liste est
figée et **ne peut que diminuer**.

L'option A — découper les fichiers d'abord — demandait douze à quinze jours à
toucher du code servi en production sans besoin fonctionnel : c'est exactement le
travail répété que cet ADR cherche à éviter. L'option C aurait rendu la CI rouge
pendant des semaines ; une CI rouge en permanence cesse d'être lue, et le projet
aurait perdu son seul garde-fou existant.

#### 6.3 Les quatre points de la section 5, tranchés

| Point | Décision |
|---|---|
| Les tests | **inclus**. Le comptage logique rend la règle juste : les commentaires d'intention ne pénalisent pas. |
| Les scripts hors ligne | **même plafond**. Un script de 632 lignes logiques reste illisible. Priorité basse dans la résorption. |
| Les fichiers générés et de données | **exclus**. `dictionnaires/*.json` n'est pas du code. |
| Ce qui compte comme ligne | **lignes logiques**, voir 6.1. |

#### 6.4 La dette initiale

Mesurée sur `origin/APIPy` @ `626d00d`, le 2026-11-24, dans le périmètre décidé
au 6.3 — tests inclus.

| Fichier | Logiques | Physiques | Nature |
|---|---|---|---|
| `scripts/generate_culture_validation_pdf.py` | 632 | 749 | script hors ligne |
| `tests/unit/test_operational_services.py` | 518 | 595 | test |
| `scripts/generate_issue_40_hevea_validation_pdf.py` | 488 | 561 | script hors ligne |
| `tests/unit/test_bambara_validator_source.py` | 479 | 778 | test |
| `scripts/build_culture_validation_drafts.py` | 461 | 621 | script hors ligne |
| `tests/integration/test_corpus_schema.py` | 395 | 580 | test |
| `tests/unit/test_corpus_service.py` | 390 | 583 | test |
| `tests/unit/test_dioula_handler.py` | 390 | 526 | test |
| `app/services/corpus_service.py` | 364 | 668 | **service applicatif** |
| `scripts/prevalidation_rules.py` | 346 | 628 | script hors ligne |
| `finetune/prepare_dioula_dataset.py` | 341 | 520 | script hors ligne |
| `tools/test_tts_batch.py` | 339 | 439 | outil hors ligne, malgré son nom |
| `wouri-lqe-web/src/views/AssignView.test.js` | 332 | 467 | test (front) |
| `tests/unit/test_chat_service.py` | 328 | 504 | test |
| `app/services/admin_metrics.py` | 325 | 425 | **service applicatif** |
| `tests/unit/test_asr_chain.py` | 321 | 513 | test |
| `tests/unit/test_ivr_searcher.py` | 314 | 434 | test |

**Dix-sept fichiers** : neuf tests, six scripts ou outils hors ligne, **deux
services applicatifs**. Quinze des dix-sept ne tournent jamais en production.

`corpus_service.py` sera réécrit par l'ADR-0050 phase 2 : il ne doit pas être
découpé avant. `admin_metrics.py` est le seul service applicatif réellement à
résorber par découpage.

Deux fichiers sont au bord sans dépasser, et il faut les connaître :

| Fichier | Logiques | Marge |
|---|---|---|
| `app/main.py` | 300 | **0** — le plafond est « au-dessus de 300 » |
| `wouri-lqe-web/src/views/StudioView.vue` | 299 | **1 ligne** |

La marge de `StudioView.vue` a une conséquence déjà identifiée : le correctif de
l'enregistreur vocal dans la fiche de relecture — le défaut signalé par le
locuteur baoulé, qui ne peut pas redire une phrase qu'il corrige — ajoutera des
lignes à ce fichier et fera échouer le contrôle. C'est le comportement voulu : il
forcera l'extraction de l'enregistreur de `DictationView.vue` dans un composant
réutilisable, qui est la conception correcte. Le plafond joue ici son rôle, il ne
gêne pas.

Mise en œuvre suivie par l'issue #621.

#### 6.5 Le cliquet, décidé avec la mise en œuvre

Une liste d'exemptions se contourne de la façon la plus simple du monde : en
relevant le chiffre inscrit dans la même PR que l'allongement. Le contrôle doit
donc comparer sa liste à celle de la **branche de base**, et refuser toute
exemption ajoutée, toute valeur relevée et tout plafond relevé.

Conséquence voulue : **une valeur inscrite au-dessus du réel échoue aussi.** La
liste ne peut pas seulement cesser de grandir, elle doit descendre quand un
fichier raccourcit. C'est ce qui rend la dette réellement décroissante au lieu de
simplement figée.

Deuxième point révélé par la mise en œuvre : **25 fichiers de code suivis par git
n'étaient déclenchés par aucune chaîne d'intégration** — les vingt fichiers de
`finetune/` et les cinq `.py` de la racine. Un contrôle qu'aucun déclencheur
n'appelle ne contrôle rien. Les déclencheurs de `ci-api.yml` reçoivent donc
`finetune/**` et `*.py`.

---

## 7. Conséquences attendues

- `docs/constraints.md` reçoit la règle, qui cesse de vivre uniquement dans un
  protocole de revue.
- Le contrôle est un script court, appelé par les trois chaînes d'intégration
  existantes.
- La dette est **inscrite et décroissante** : chaque fichier résorbé sort de la
  liste et ne peut plus y revenir, et le cliquet du 6.5 l'y oblige.

---

## 8. Historique

| Date | Évolution |
|---|---|
| 2026-11-17 | Rédaction. Statut **proposé**. Mesure de l'existant faite : 19 fichiers sur 197 dépassent le plafond en lignes physiques. Décision en attente. |
| 2026-11-17 | **Option B retenue**, plafond sur les lignes logiques, tests inclus, données exclues. Statut **accepté**. |
| 2026-11-24 | **Correction de trois erreurs de la rédaction initiale**, relevées pendant la mise en œuvre (#621), avant toute ligne de code. (1) Le §6.4 publiait `corpus_service.py` à 327 lignes logiques : l'outil de mesure du 17/11 prenait ses quatre requêtes SQL en triple guillemets pour des chaînes de documentation. La valeur réelle est **364**, fichier inchangé depuis le 13/10. (2) Le §6.3 décidait « tests inclus » et le §6.4 listait une dette mesurée **sans** les tests : les deux sections se contredisaient, et une liste de cinq exemptions aurait rendu la CI rouge au premier commit, c'est-à-dire la règle inapplicable. La dette réelle est de **dix-sept fichiers**. (3) L'en-tête portait « accepté » sans qu'aucune entrée d'historique n'enregistre la décision. Mesures reprises avec le `tokenize` et l'`ast` de Python, méthode recoupée sur les valeurs déjà connues. |
| 2026-11-24 | Ajout du **§6.5** : le cliquet comparant la liste à la branche de base, et la correction des déclencheurs de `ci-api.yml`, qui laissaient 25 fichiers de code hors de toute chaîne d'intégration. |
