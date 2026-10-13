# ADR-0042 — Normalizer post-ASR : ne plus changer le dioula courant en noms de culture

**Statut** : proposé
**Date** : 2026-10-12
**Auteur(s)** : Claude (assistant) sous direction de Ouedraogo Issouf
**Valideur** : Ouedraogo Issouf — en attente
**ADRs liés** : [ADR-0014](0014-promotion-corpus-v3-dioula-ci.md) (le natif tranche),
[ADR-0020](0020-filtre-bam-dyu-perimetre-reduit.md) (variantes phonologiques),
[ADR-0022](0022-composition-chaine-asr-dioula.md) (transcriptions de référence),
[ADR-0027](0027-decision-nemo-installer-ou-retirer.md) (NeMo retiré),
[ADR-0031](0031-moteur-amelioration-linguistique.md) (sas de validation),
[ADR-0039](0039-politique-reponse-llm-et-escalade.md) (familles factuelles),
[ADR-0041](0041-choix-culture-et-homographes-nlu.md) (choix de la culture, PR A)

---

## Contexte

Le normalizer post-ASR (`app/services/asr/normalizer/`) corrige chaque transcription
vocale dioula avant le NLU (`app/services/asr/chain.py`). Il a quatre étapes :

1. corrections exactes (`dictionnaires/asr_corrections.json`) ;
2. fusions NeMo (`FUSIONS`, `PHRASE_SUBS` de `asr_bambara_normalizer.py`) ;
3. fuzzy : un mot est rapproché d'un mot-clé du NLU (`fuzzy.py`) ;
4. reconstruction de cultures : des fragments sont fondus en nom de culture (`culture.py`).

### Ce que fait BASE (1332c8b)

Mesure du banc du normalizer : 635 textes dioula de référence du dépôt, mis en forme
de transcription (minuscules, sans ponctuation). Sources : `corpus_ivr.json`,
`bambara_phrases.json`, `dioula_sentence_bank.json`, `GRAMMAIRE_DIOULA_REGLES.md` et
les formulaires `data/issue_*native_validation*.json`. Résultats :

- 355 textes réécrits sur 635 (55,9 %), dont 99 qui gagnent une culture ;
- 153 réécritures introduisent un nom de culture : 110 par l'étape 3, 29 par l'étape 4 ;
- jeux `data/hf_datasets` : 4 786 (findora), 7 447 (francophonia) et 907 (koumankan)
  textes qui gagnent une culture.

Exemples : « tigɛ » → « tiga » (arachide), « mugan » → « mugu » (haricot), « foro » →
« ɲɔforo » (mil), « ka ɲi » → « kaba » (maïs), « ka bana » → « kaban ». Trois causes :

- l'étape 4 réécrit un mot seul à distance ≤ min(3, len//2) d'un nom de culture ;
- l'étape 3 compare les consonnes position par position, s'arrête au bout du mot le
  plus court et admet n'importe quelle voyelle ;
- l'étape 1 remplace des sous-chaînes au milieu d'un mot.

### La première itération et sa contre-vérification

Cinq variantes ont été mesurées le 2026-10-07 (V1 à V5, ci-dessous). V4, recommandée,
a ramené les textes qui gagnent une culture de 99 à 3. Sa contre-vérification a
confirmé ce gain, mais a trouvé cinq défauts :

- la détection « une culture est déjà nommée » comptait « ku » (2 lettres) et « mais »
  (la conjonction) : « ba nan ku … » ne redevenait plus « bananku » ;
- la règle « un mot du vocabulaire NLU n'est jamais fondu » bloquait « sɔ mɔ » →
  « sɔmɔ » ;
- la généralisation était perdue : erreurs de l'issue #85 corrigées sans leur clé
  (leave-one-out), 0 sur 9 contre 3 dans BASE ; confusion r↔g, 2 cas sur 14 contre 12 ;
- l'amendement d'ADR-0020 affirmait à tort que seules e/ɛ, o/ɔ et i/o sont documentées ;
- un test figeait « fura » → « furaw » comme un comportement voulu.

S'y ajoute un défaut de déterminisme. Quand plusieurs variantes phonologiques d'un mot
(ADR-0020) sont dans le vocabulaire, la variante retenue dépend de PYTHONHASHSEED :
« laba » devient « daba » (labourer) ou « jaba » (oignon).

### La seconde contre-vérification

V6, la variante finale de l'itération 2, a été contre-vérifiée sur des copies propres.
Tous ses chiffres se reproduisent. Verdict : publiable avec réserves. Trois points
bloquaient :

- l'ADR affirmait que la PR du NLU (PR A, ADR-0041) corrige le partiel « gan » et la
  conjonction « mais ». Ce n'est pas le cas : avec les deux PR, « organiser » et
  « mugan » gardent un gombo faux, et mixte_010 un maïs faux ;
- la généralisation n'était mesurée que sur des phrases porteuses qui ont toutes un
  verbe agricole (150 cas sur 150, 124 sur 124). Or l'étape 4 ne tournait qu'avec un
  verbe agricole, et 28 seulement des 101 phrases manuel et locuteur-variante de
  `bambara_phrases.json` en ont un. Sur 153 cas sans verbe agricole, V6 en corrigeait
  11, BASE 16 ;
- la frontière de fin de mot de l'étape 1 bloquait une clé suivie d'un pluriel :
  « tigkaw » et « mangogow » n'étaient plus corrigés (0 cas sur 6, BASE 6).

Elle a aussi relevé des limites que l'ADR ne déclarait pas : « tigka ba » lu comme du
maïs, une fausse banane qui empêche de retrouver la patate, des résidus de BASE et des
refus sur des transcriptions simulées. L'itération 3 (2026-10-12) y répond par deux
changements de code (option V6) et par les corrections de cet ADR.

### Contraintes

- `docs/constraints.md` §1.2 : aucune liste de mots ni aucun seuil nouveau dans le Python.
- ADR-0014 et ADR-0031 : aucun dioula n'est inventé, et toute règle qui change la
  reconnaissance d'un mot dioula est à valider nativement.
- ADR-0022 : le dépôt n'a aucune transcription MMS-dyu réelle avec sa référence. Le
  rappel repose sur des erreurs de l'époque NeMo.

## Questions posées avant la décision

1. Quelles corrections faut-il garder ?
2. Où admettre les confusions documentées sans recréer de fausses cultures ?
3. Que veut dire « une culture est déjà nommée » ?
4. « fura » → « furaw » est-il une règle ou un comportement hérité ?
5. Qui décide des entrées de dictionnaire qui réécrivent des mots courants ?
6. Le critère non négociable couvre-t-il aussi les transcriptions fautives ?

Réponses obtenues :

- Q1 → Plan approuvé le 2026-10-07 (« tu peux aller »). Le normalizer ne doit plus
  transformer des mots dioula courants en noms de culture, sans perdre les vraies
  corrections. Critère non négociable : une question agricole dont BASE reconnaissait la
  bonne culture ne doit ni devenir un refus (HORS_SUJET), ni quitter sa famille
  factuelle (ADR-0039 : météo, vente, date).
- Q2 et Q3 → par la mesure, dans un périmètre à faible risque (fusion de l'étape 4,
  mot seul proche d'un nom de culture long). Voir Options.
- Q4 → comportement de BASE conservé, à valider nativement.
- Q5 → le propriétaire ou un locuteur natif ; ces entrées restent hors de cette décision.
- Q6 → en attente du propriétaire. Le critère a été contrôlé sur 499 questions propres.
  Sur des transcriptions simulées, 4 refus et 1 sortie de famille factuelle touchent des
  questions dont BASE trouvait la bonne culture (§Conséquences).

## Confusions documentées dans le dépôt

Chaque paire se lit [lettre de la transcription → lettre du vocabulaire].

| Confusion | Source dans le dépôt | Décision |
|---|---|---|
| e ↔ ɛ, o ↔ ɔ | `asr_corrections.json` : « wulafe » → « wulafɛ », « sufe » → « sufɛ », « malo sene » → « malo sɛnɛ » ; `fuzzy.py` (Wikipedia, Vydrin 2020) | étapes 3 et 4 |
| i → o | « mali » → « malo » (`test_mali_to_malo`, erreur de production) | étapes 3 et 4 ; le sens o → i n'est pas observé |
| allongement final | « sanjiii » → « sanji » (graphie TTS des formulaires validés) | étapes 3 et 4 |
| o → u | « ku » transcrit « ko » (`asr_bambara_normalizer.py`, `PHRASE_SUBS`) | étape 4 seulement |
| a → ɔ, a → o | « sagɔma » → « sɔgɔma », « sagoma » → « sogoma » (`asr_corrections.json`) | étape 4 seulement |
| g → r | « mangogo » → « mangoro » (`asr_corrections.json`, cultures_nemo_errors) | étape 4 seulement |
| r → g | « sɔrɔma » → « sɔgɔma », « soroma » → « sogoma » (`asr_corrections.json`) | étape 4 seulement |
| consonne parasite | « tigka » → « tiga » (`asr_corrections.json`) | étape 4, mot seul, nom exact, verbe agricole requis |
| mot-outil final | « kɔrɔ ni sɛnɛ », « ka ka o sɛnɛ » (`asr_corrections.json`) | étape 4, devant un verbe agricole, nom exact |
| nom coupé en fragments | « ka ka aw », « kaban kuru », « ti ga » | étape 4, fusion de 2 ou 3 mots |
| « ka » soudé, nasale perdue | « kabarada » → « bàrànda » | non retenue : voir option C9b |
| i → ɛ | « jumin » → « jumɛn » (`asr_corrections.json`) | non mesurée, sans nom de culture |
| nasale finale perdue | « ka ga sɛnɛ » → « ka gan sɛnɛ » | non retenue : mot de 2 lettres |

## Mesures communes à toutes les options

Toutes les options sont mesurées avec les mêmes outils, contre BASE :

- **Banc du normalizer** : textes de référence réécrits et textes qui gagnent une
  culture (précision), plus rappel des corrections connues (104 paires : tests,
  dictionnaires, `FUSIONS`, `PHRASE_SUBS`). Il contrôle aussi le déterminisme sur les
  graines PYTHONHASHSEED 0 à 5 et couvre les jeux hf (65 640 textes distincts).
- **150 erreurs ASR simulées** : 41 phrases porteuses du dépôt qui nomment une seule
  culture. Le nom de culture y est altéré comme dans une erreur documentée : scission,
  e/ɛ, o lu i, u lu o, ɔ lu a, r↔g, « ka » soudé. Toutes ces porteuses ont un verbe
  agricole : le générateur l'exige.
- **124 erreurs documentées** replacées dans d'autres phrases du dépôt qui nomment la
  même culture, elles aussi avec un verbe agricole.
- **Leave-one-out** : chaque clé de `asr_corrections.json`, `FUSIONS` et
  `PHRASE_SUBS`, et les 8 erreurs de l'issue #85 (9 cas avec la phrase
  « n bɛ fɛ ka ka aw sɛnɛ »), sont passées au pipeline sans leur propre entrée. On
  compte la culture obtenue : juste, fausse ou aucune.
- **compare_all** : NLU seul et chemin vocal sur 1 735 textes du dépôt et de
  l'évaluation.
- **Critère non négociable** : chemin vocal de 499 questions (jeu de 403 phrases et
  96 pièges, styles écrit, WhatsApp, vocal et mixte), graines 0 à 2. Ce sont des
  questions propres, sans erreur de transcription.

La seconde contre-vérification a ajouté quatre mesures, faites sur BASE, sur la V6 de
l'itération 2 et sur la variante finale :

- **117 cas nouveaux**, sur des porteuses des brouillons
  `data/issue_*_validation_draft.json`, des phrases attestées et de la banque de
  phrases : 79 avec un verbe agricole, 38 sans ;
- **153 cas sans verbe agricole**, produits par le générateur des 150 cas sur des
  porteuses sans verbe agricole ;
- **3 597 textes propres** jamais mesurés : 567 phrases des brouillons, avec leur
  culture, et 3 030 exemples sans tons de `bambara_francais.json` ;
- **critère sur transcriptions simulées** : sur les 544 cas (150 + 124 + 117 + 153),
  refus (HORS_SUJET) et sorties de famille factuelle là où BASE trouvait la culture
  attendue.

Aucune mesure n'invente de dioula. Les phrases porteuses viennent du dépôt, et seule la
graphie d'un nom de culture du dictionnaire y est altérée. Les outils et les jeux de
cas sont ceux de la session du 2026-10-07 et de la seconde contre-vérification ; ils ne
sont pas versionnés.

## Options étudiées

### Option V1 — Étape 4 : garde-fous

- **Description** : la détection compte les noms français ; une fenêtre qui contient un
  mot du vocabulaire NLU n'est jamais fondue ; un mot seul n'est réécrit qu'à
  consonnes égales.
- **Avantages** : 83 textes qui gagnent une culture au lieu de 99.
- **Inconvénients** : l'erreur se déplace vers une fenêtre de deux mots (« ka foro » →
  « kabaforo »). L'étape 3 n'est pas traitée. Généralisation : 51 erreurs simulées sur
  150 (BASE 59), 2 cas de l'issue #85 justes et 7 faux.
- **Coût** : faible.
- **Compatibilité** : listes dans le JSON (§1.2) ; dettes existantes inchangées.

### Option V2 — Étape 4 réservée à la fusion de fragments

- **Description** : plus de mot seul à l'étape 4. Une fusion garde les consonnes du nom
  de culture.
- **Avantages** : 71 textes qui gagnent une culture.
- **Inconvénients** : l'étape 3 ajoute encore 110 cultures. 47 erreurs simulées sur 150,
  aucun cas de l'issue #85 juste.
- **Coût** : faible.
- **Compatibilité** : listes dans le JSON (§1.2).

### Option V3 — V2 et lexique des mots attestés

- **Description** : V2, plus 428 mots validés nativement, jamais réécrits à l'étape 3.
- **Avantages** : 13 textes qui gagnent une culture.
- **Inconvénients** : mesure circulaire sur le corpus validé ; hors de ce corpus, peu de
  gain. « fura », attesté, ne rejoint plus « furaw » : 5 phrases « Je veux un
  traitement » deviennent HORS_SUJET. Il faut maintenir un fichier généré.
  Généralisation : 57 sur 150, issue #85 0 juste.
- **Coût** : script de génération et test de fraîcheur.
- **Compatibilité** : le lexique doit être régénéré à chaque validation native
  (ADR-0014), sinon un test échoue.

### Option V4 — V2 et règles de graphie aux étapes 1 et 3

- **Description** : à l'étape 3, mêmes consonnes ; confusions e/ɛ, o/ɔ et i → o ;
  allongement ; retrait d'un « n » final ; suffixes de pluriel -w et -s. À l'étape 1,
  une clé ne s'arrête plus au milieu d'un mot.
- **Avantages** : 3 textes qui gagnent une culture ; jeux hf 158, 353 et 27.
- **Inconvénients** : les défauts listés au Contexte. Généralisation : 58 sur 150, r↔g
  2/14, issue #85 0 juste. Nouvelle réécriture « feere » → « fere » (vendre, 30 fois),
  due à l'allongement intérieur.
- **Coût** : moyen.
- **Compatibilité** : listes dans le JSON (§1.2) ; son amendement d'ADR-0020 ne suivait
  pas le gabarit (§2.3).

### Option V5 — V4 et lexique des mots attestés

- **Description** : V4 et le lexique de V3.
- **Avantages** : 2 textes qui gagnent une culture.
- **Inconvénients** : les défauts de V4 et de V3 réunis (« fura » perdu, fichier généré
  à maintenir).
- **Coût** : élevé.
- **Compatibilité** : celle de V3 et celle de V4.

### Option V6 — Variante finale

V4 corrigée, et la généralisation rétablie là où le risque est faible. Toutes les
listes et tous les seuils sont dans `dictionnaires/asr_normalizer_regles.json`.
L'itération 3 (2026-10-12) ajoute deux changements, signalés ci-dessous.

**Étape 1** : une clé ne s'arrête plus au milieu d'un mot (V4). Itération 3 : une clé
d'un seul mot admet après elle un suffixe de `suffixes_pluriel` (-w, -s), qu'elle laisse
en place. « tigkaw » devient « tigaw », « mangogow » « mangorow » : les 6 cas de pluriel
d'une clé documentée retrouvent leur culture, comme dans BASE.

**Étape 3** (`fuzzy.py`, `ecart.py`) :

- un candidat doit avoir les mêmes consonnes, dans le même ordre, que le mot ;
- ses voyelles ne peuvent différer que par une confusion courante (e/ɛ, o/ɔ, i → o) ;
- seul le groupe de voyelles final peut être allongé ; « feere » ne devient plus
  « fere » ;
- deux écarts restent admis : le retrait d'un « n » final, et un suffixe sans effet sur
  le concept. Ce suffixe peut être un pluriel (-w, -s) ou le « e » final du français
  (« cacaoyère » → « cacaoyer »), sur un radical d'au moins 4 lettres. La comparaison
  ignore les tons et les accents ;
- abstention si plusieurs variantes phonologiques sont dans le vocabulaire (« laba ») ;
- les confusions réservées à l'étape 4 n'y sont pas admises.

**Étape 4** (`culture.py`), sans culture déjà nommée, et avec un verbe agricole sauf
pour le mot seul :

- *détection* : un mot-clé CULTURE_* compte s'il a au moins 3 lettres et n'est pas
  « mais » (`mots_ignores`). Les noms français sont compris ;
- *fusion de 2 ou 3 mots* : confusions courantes, plus o → u, a → ɔ, a → o et g ↔ r
  (« man go ra » → « mangoro ») ;
- *mot seul hors vocabulaire* : à une confusion documentée d'un nom de culture d'au
  moins 5 lettres, à distance 1 (« mangogo » → « mangoro », « kɔgɔni » → « kɔrɔni »).
  Itération 3 : cette lecture vaut aussi sans verbe agricole
  (`mot_seul.sans_verbe_agricole = true`). « lemuro bɛ ji fɛ caman » donne « lemuru »
  (agrumes) ; la porteuse est agrumes_irrigation_001 du formulaire de l'issue #68.
  C'est une règle de reconnaissance, à valider nativement ;
- *consonne parasite* : un mot seul où deux consonnes se suivent sans nasale en tête
  est lu sans l'une d'elles, et doit alors donner exactement un nom de culture
  (« tigka » → « tiga »). Elle exige toujours le verbe agricole : sans lui, koumankan
  gagnait 8 cultures fausses (« johni », « sosso », « malro ») ;
- *mot court du vocabulaire* : un mot de 2 lettres au plus (« sɔ », « ku ») peut être
  fondu si la fusion donne exactement un nom de culture (« sɔ mɔ » → « sɔmɔ ») ;
- *mot-outil final* : un mot de `_NEVER_FUSE` peut finir une fusion juste avant un
  verbe agricole, si elle donne exactement un nom de culture d'au moins 5 lettres
  (« kɔrɔ ni sɛnɛ » → « kɔrɔni sɛnɛ ») ;
- « exactement » s'entend à la graphie près (e/ɛ, o/ɔ).

Bilan de V6 (variante finale, mesures du 2026-10-12) :

- **Avantages (mesurés)** :
  - 3 textes de référence qui gagnent une culture (BASE 99) ;
  - jeux hf : 158, 346 et 27 (BASE 4 786, 7 447 et 907) ;
  - 3 597 textes propres : 21 gagnent une culture (BASE 374), aucun ne gagne une culture
    que BASE n'ajoutait pas, et la vraie culture des brouillons est trouvée 413 fois,
    comme dans BASE ;
  - avec un verbe agricole : 89 erreurs simulées sur 150 (BASE 59, V4 58), dont r↔g
    10/14 ; 52 erreurs documentées replacées sur 124 (BASE 42) ;
  - sans verbe agricole : 20 cas sur 153 (BASE 16 ; V6 de l'itération 2 : 11) ;
  - 117 cas nouveaux : 72 justes, 9 avec une culture fausse, 36 sans culture. BASE :
    63 justes, 28 fausses, 24 sans culture, 2 justes avec une culture fausse en plus.
    V6 de l'itération 2 : 58 justes ;
  - issue #85 sans clé : 3 justes comme BASE, mais pas les mêmes (« tigka »,
    « mangogo », « kɔrɔ ni » ; BASE avait « kabarada » au lieu de « kɔrɔ ni »), et
    2 cultures fausses au lieu de 6 ;
  - 22 clés à culture sans leur entrée : 10 justes et 2 fausses (BASE 7 et 7). Depuis
    l'itération 3, « mangogo » est aussi corrigé sans sa clé ;
  - 0 refus, 0 sortie de famille factuelle et 0 vraie culture perdue sur les
    499 questions propres, graines 0 à 2, avec ou sans la PR A.
- **Inconvénients (mesurés)** : voir §Conséquences, « Négatives assumées ».
- **Coût** : un module (`ecart.py`), un fichier de règles, 56 tests.
- **Compatibilité** : §1.2 respecté pour toute règle nouvelle ; aucun fichier commun
  avec la PR A (ADR-0041). Ordre de fusion : la PR A d'abord, ou les deux ensemble
  (§Décision).

### Variantes écartées par la mesure (itérations 2 et 3)

| Variante | Gain | Coût mesuré |
|---|---|---|
| C1 : mot court fondu à distance 0 stricte, sans e/ɛ ni o/ɔ | aucun | 6 erreurs simulées corrigées en moins (« so sɔ », « wo sɔ », « sɔ mo »), sans aucun texte hf en moins |
| C3 : mot seul vers un nom de culture de 4 lettres | +3 erreurs simulées (« tira », « nɛgɛ ») | +68 textes hf qui gagnent une culture ; « nɛgɛ » (le métal, 114 fois dans findora) deviendrait « nɛrɛ » (néré) |
| C8 : mot-outil final sans exiger le verbe agricole | +7 simulées, +9 documentées | +46 textes findora : « kan ka o » → « kakao » ×39 (après la clé « kan » → « ka »), « kɔrɔ ni » → « kɔrɔni » ×6 |
| C9b : « ka » soudé et nasale perdue (« kabarada ») | +1 leave-one-out | « barada » (travail, 16 fois dans koumankan) deviendrait « bàrànda » (banane) |
| C12 : confusions de l'étape 4 admises à l'étape 3 (mots de 6 lettres ou plus) | leave-one-out salutations +5 (« sagɔma », « sɔrɔma »…) | « fagali » → « farali » (+vendre) ×37 sur hf, « saigner » → « soigner » ×2 |
| Détection de BASE (cibles de reconstruction) | aucun | identique sur toutes les mesures ; dépend de la liste française en dur, déjà périmée |
| « e » final sans radical minimal | identique | « Mile » (Milet) → « mil » ×3 dans francophonia |
| Itération 3 : à longueur égale, clé d'un seul mot avant une clé de plusieurs mots (étape 1) | « tigka ba » redevient « tiga ba » (arachide) : 2 des 117 cas nouveaux, sur une même phrase | +1 texte hf qui gagne une culture : « kan » → « ka » passe avant « ka ba », et « … kanw donni kan ba la … » devient « … kaba la … » (maïs faux ; francophonia_bambara_french, rang 17416) |

### Comparatif

Textes de référence : 635 en forme production, 1 203 en phrases.

| Critère | BASE | V1 | V2 | V3 | V4 | V5 | V6 |
|---|---|---|---|---|---|---|---|
| Textes réécrits (production) | 355 | 335 | 326 | 136 | 165 | 83 | **147** |
| Gagnent une culture (production / phrases) | 99 / 198 | 83 / 137 | 71 / 95 | 13 / 11 | 3 / 2 | 2 / 0 | **3 / 2** |
| Réécritures qui ajoutent une culture | 153 | 135 | 122 | 15 | 4 | 2 | **4** |
| hf qui gagnent une culture (findora / francophonia / koumankan) | 4786 / 7447 / 907 | 4703 / 6612 / 793 | 3611 / 4480 / 669 | 945 / 3019 / 388 | 158 / 353 / 27 | 158 / 349 / 27 | **158 / 346 / 27** |
| Questions françaises réécrites (/311) | 119 | 119 | 119 | 119 | 50 | 50 | **54** |
| Rappel (paires connues) | 103/104 | 103/104 | 103/104 | 103/104 | 103/104 | 103/104 | **103/104** |
| Erreurs simulées corrigées (/150) | 59 | 51 | 47 | 57 | 58 | 58 | **89** |
| dont r↔g (/14) | 12 | 3 | 2 | 2 | 2 | 2 | **10** |
| Erreurs documentées replacées (/124) | 42 | 41 | 40 | 44 | 48 | 48 | **52** |
| Issue #85 sans clé (/9), juste / fausse / aucune | 3 / 6 / 0 | 2 / 7 / 0 | 0 / 2 / 7 | 0 / 2 / 7 | 0 / 2 / 7 | 0 / 2 / 7 | **3 / 2 / 4** |
| Clés à culture sans leur entrée (/22), juste / fausse / aucune | 7 / 7 / 8 | 7 / 6 / 9 | 7 / 2 / 13 | 7 / 2 / 13 | 7 / 2 / 13 | 7 / 2 / 13 | **10 / 2 / 10** |
| Réécritures nouvelles par rapport à BASE | — | 7 | 1 | 1 | 2 (« feere » ×30) | 0 | **1** (« suma » → « sumaw » ×3) |
| Fichier généré à maintenir | non | non | non | oui | non | oui | **non** |
| tests/unit | 1500 | 1510 | 1519 | 1524 | 1529 | 1533 | **1556** |

La colonne V6 donne la variante finale. Elle ne diffère de la V6 de l'itération 2 que
par les 22 clés (9 / 2 / 11 avant) et par les tests ; les autres lignes sont identiques.

Pour V6, les cultures « fausses » de l'issue #85 sont « kaban kuru » et « kabarada ».
Le NLU les lit comme du maïs, par le mot-clé « kaban » et par le partiel « kaba » :
ce n'est pas le normalizer qui les crée.

Mesures de la seconde contre-vérification, sur BASE, la V6 de l'itération 2 et la
variante finale :

| Mesure | BASE | V6, itération 2 | V6 finale |
|---|---|---|---|
| 117 cas nouveaux, culture juste | 63 | 58 | **72** |
| dont 79 avec un verbe agricole | 51 | 52 | **57** |
| dont 38 sans verbe agricole | 12 | 6 | **15** |
| 153 cas sans verbe agricole, culture juste | 16 | 11 | **20** |
| 3 597 textes propres qui gagnent une culture | 374 | 21 | **21** |
| Refus (HORS_SUJET) sur les 544 cas simulés | 40 | 72 | **66** |
| Refus nouveaux là où BASE trouvait la culture attendue | — | 6 | **4** |
| Sorties de famille factuelle là où BASE trouvait la culture attendue | — | 1 | **1** |

Précision par source, forme production, pour BASE puis V6. Chaque cellule donne les
textes réécrits et, entre parenthèses, ceux qui gagnent une culture :

| Source | BASE | V6 |
|---|---|---|
| corpus_ivr validé | 22/35 (8) | 5/35 (0) |
| corpus_ivr non validé | 102/162 (21) | 25/162 (0) |
| Common Voice dyu (phrases attestées) | 69/99 (6) | 51/99 (0) |
| bambara_phrases (manuel) | 22/97 (5) | 11/97 (0) |
| banque de phrases | 12/42 (4) | 3/42 (0) |
| grammaire (exemples justes) | 3/10 (3) | 0/10 (0) |
| formulaires de validation native | 126/163 (51) | 57/163 (3) |
| termes validés | 4/32 (1) | 0/32 (0) |
| variantes ASR (bambara_phrases) | 32/74 (1) | 31/74 (0) |
| questions françaises | 119/311 (17) | 54/311 (1) |

Les 3 textes de référence qui gagnent une culture portent 4 réécritures :

- « ti ga » → « tiga » (2) : graphie TTS d'arachide dans des formulaires validés sur
  l'arachide ;
- « bananen » → « banane » (1) : mais_diagnostic_001. La banane est fausse d'après la
  glose du dépôt (« bananen » et la patate, §Conséquences) ; à valider nativement ;
- « kafew » → « kafe » (1) : pluriel.

## Décision

**Option retenue** : V6, variante finale (itération 3 comprise).

**Justification** :

- C'est la seule option qui garde la précision de V4 sans perdre la généralisation de
  BASE. Elle compte 3 textes de référence qui gagnent une culture, contre 99 dans BASE ;
  sur les jeux hf, entre −95 % et −97 % de cultures ajoutées ; sur 3 597 textes propres
  jamais mesurés, 21 au lieu de 374.
- Avec un verbe agricole, elle corrige plus d'erreurs simulées que BASE (89 contre 59
  sur 150, 52 contre 42 sur 124) et autant d'erreurs de l'issue #85 sans leur clé
  (3 sur 9), avec 2 cultures fausses au lieu de 6. Sans verbe agricole, elle fait un peu
  mieux que BASE depuis l'itération 3 seulement : 20 cas sur 153 contre 16 (11 avant),
  et 15 sur 38 contre 12 parmi les cas nouveaux.
- L'itération 3 apporte deux changements. Le pluriel des clés d'un seul mot corrige la
  régression signalée sur « tigkaw » et « mangogow » (6 cas sur 6). Le mot seul sans
  verbe agricole (`mot_seul.sans_verbe_agricole = true`) rend la généralisation sans
  verbe agricole ; c'est une règle de reconnaissance, à valider nativement. « tigka ba »
  reste lu comme du maïs : corriger l'ordre des clés créait une chaîne sur un texte
  propre (§Conséquences).
- Chaque confusion admise vient d'une erreur documentée dans le dépôt (tableau
  ci-dessus). Les confusions plus risquées ne sont admises qu'à l'étape 4 : aucune
  culture ne doit être déjà nommée, le nom visé doit être long ou exactement atteint, et
  un verbe agricole est requis, sauf pour le mot seul vers un nom de 5 lettres ou plus.
- Chaque garde-fou a été choisi par la mesure. Le seuil de 5 lettres évite « nɛgɛ » →
  « nɛrɛ », l'exigence du verbe agricole évite « kan ka o » → « kakao », et le radical
  de 4 lettres évite « Mile » → « mil ». La consonne parasite garde le verbe agricole
  (sinon 8 cultures fausses dans koumankan). D'après la contre-vérification, le mot seul
  sans verbe agricole ne change rien au banc, aux jeux hf, aux 3 597 textes propres ni
  aux 499 questions.
- Le comportement ne dépend plus de PYTHONHASHSEED, cas latent « laba » compris : 0
  sortie instable sur les graines 0 à 5, et aucun mot hf n'a plusieurs variantes
  phonologiques connues.
- Le critère non négociable est tenu sur les 499 questions propres (chemin vocal,
  graines 0 à 2) : ni refus, ni sortie de famille factuelle, ni vraie culture perdue,
  avec ou sans la PR A. Il ne l'est pas sur toutes les transcriptions simulées : 4 refus
  et 1 sortie de famille là où BASE trouvait la bonne culture (§Conséquences). Le
  propriétaire dira si le critère couvre aussi ce cas (Q6).
- Dans compare_all, 6 textes quittent une famille factuelle. Cinq n'y entraient que par
  une réécriture fausse de BASE (« fara » → « faran », « ɲɔgɔn » → « ɲɛgɛn », « vont »
  → « vent », « ka sega » → « kasava ») ou ne sont pas des questions (une note de
  changelog). Le sixième, mais_vente_001, est une réponse du corpus : voir
  §Conséquences.
- Ordre de fusion : la PR A (ADR-0041) avant cette PR, ou les deux ensemble. Seule,
  cette PR laisse la conjonction « mais » devenir la culture principale de 6 questions
  (mixte_027, e05, v21, vocal_022, w23, whatsapp_022, sur une ou plusieurs graines).
  Avec les deux PR, ces 6 questions ont leur vraie culture sur les 3 graines, et le
  critère reste sans violation.

## Conséquences

- **Positives** :
  - le dioula courant n'est presque plus réécrit en culture (147 textes réécrits au lieu
    de 355) ;
  - les phrases sans culture ne reçoivent plus de culture inventée ; de 20 textes
    changés de bambara_phrases (chemin vocal), 18 sont corrigés d'après leur glose :
    « fɛn jumɛn ka ɲi ka sɛnɛ » (« Qu'est-ce qui est bon à cultiver ? ») ne devient plus
    une question sur le maïs, et « sanji bɛna na » (« Il va pleuvoir ») n'a plus de
    maladie ;
  - sans verbe agricole, le mot seul retrouve un nom de culture de 5 lettres ou plus
    par une confusion documentée, même là où BASE échouait (« lemugu » → « lemuru »,
    « kɔgɔni » → « kɔrɔni ») ; sur les 544 cas simulés, 5 refus de BASE sont levés ;
  - le comportement est déterministe ;
  - les règles sont toutes dans un JSON.
- **Négatives assumées** : régressions déterministes par rapport à BASE.
  - mais_vente_001 (corpus_ivr), chemin vocal : QUESTION_VENTE devient
    DIAGNOSTIC_PROBLEME. Ce texte est une réponse, pas une question. BASE n'y trouvait
    la vente que par « fara » → « faran », réécriture qui ajoute aussi une fausse vente
    à riz_diagnostic_001 (« furakɛ fara màlo fura la », rendu par « Traite les
    feuilles »). Le remède est côté NLU, après validation native du sens de « fara » ;
  - banque de phrases, « a ka sega tingɛn sanniya anni ka fere » (sans traduction) :
    QUESTION_VENTE devient QUESTION_GENERALE. BASE y créait « kasava » (manioc) par une
    consonne g → v qu'aucune erreur documentée ne justifie ;
  - erreurs simulées perdues, 4 cas : « tira » ×2 et « nɛgɛ » (noms de 4 lettres), et
    « sumba la kɛ » (pas de verbe agricole après « la »). Pour « nɛgɛ » et « sumba la
    kɛ », la question devient un refus (voir les transcriptions simulées, plus bas) ;
  - leave-one-out : « sagɔma » et « sagoma » ne sont plus corrigés sans leur clé (option
    C12 écartée). « kabarada » ne l'est plus sans sa clé (option C9b écartée) ;
  - chemin vocal du français (en production, le français passe par Whisper, pas par ce
    normalizer). Ne sont plus rattachés à leur mot-clé : « Arrose » → « arroser »
    (2 gloses de bambara_phrases, qui deviennent HORS_SUJET), « coupe » ou « coupé » →
    « couper » (7), « seme » → « semer » (2), « ramasse » ou « ramassé » → « ramasser »,
    « cueilli » → « cueillir », « récoltées » → « récolte », « palme » → « palmier ».
    Le français fléchi est à lemmatiser dans le NLU ;
  - sur le texte brut, trois questions françaises deviennent HORS_SUJET :
    - « …mon riz,kan… » et « …les feves de cacao? … » : la ponctuation est collée au nom
      de culture, et BASE n'évitait le refus qu'avec une culture fausse (mil, caprin).
      En forme transcription, sans ponctuation, V6 trouve le riz et le cacao ;
    - la question sur le paludisme d'un enfant : son refus est juste ;
  - 5 questions du jeu de 403 phrases gagnent une culture fausse que BASE effaçait par
    une autre réécriture. Le partiel « gan » de « organiser » (3 styles) et de « mugan »
    donne le gombo. La conjonction « mais » donne le maïs dans une phrase mixte, où
    BASE réécrivait « sɔrɔ mais » en « sɔgɔma ». La PR A (ADR-0041) ne corrige pas ces
    défauts. Elle rend le choix de la culture déterministe et retire un homographe
    douteux (« mais », « fini »…) quand la phrase cite une autre culture ; elle ne
    touche pas aux partiels dans un mot (« gan » dans « mugan », « organiser »). Avec
    les deux PR, la vraie culture passe devant (cacao, mil), mais le gombo faux reste,
    et un « mais » seul reste lu comme le maïs (mixte_010). Dans compare_all, des textes
    de corpus_ivr qui contiennent « mugan » (« santimɛtiri mugan », « tile mugan »)
    passent ainsi du haricot faux de BASE à un gombo faux ;
  - « tigka ba » : la phrase attestée « … ye tiga ba caman lajɛ … » (corpus_ivr,
    arachide_conseil_001), avec l'erreur documentée « tigka », devient « tigkaba », lu
    comme du maïs ; BASE trouvait l'arachide. Les clés « ka ba » et « tigka » ont la
    même longueur : « ka ba » s'applique d'abord, et « tigka » ne se déclenche plus
    dans un mot. Passer les clés d'un seul mot en premier corrige ce cas, mais crée une
    chaîne sur un texte propre (variante écartée, ci-dessus). À traiter avec la décision
    sur les entrées « kan » et « ka ba » (§Validations en attente, point 3) ;
  - « bananen » et la patate : dans le brouillon patate_diagnostic_001 (issue #62,
    version_b), « woso » transcrit « wo sa » ou « wosko » devant « bananen » n'est plus
    reconstruit. BASE donnait la patate et une banane fausse, V6 la banane fausse seule.
    L'étape 3 réécrit « bananen » en « banane » (retrait du « n » final ; BASE le
    faisait aussi) ; la détection, qui compte désormais les noms français, voit une
    culture nommée, et l'étape 4 ne fait rien. La banane est fausse d'après la glose du
    dépôt : dans le brouillon banane_diagnostic_001 (issue #57, version_b), « Aw ye
    yiri bananen bɔ joona » rend « Retirez les pieds malades vite ». « bananen » fait
    gagner la banane à 7 phrases des brouillons, dont 6 ne portent pas sur la banane ;
  - transcriptions simulées (544 cas : 150, 124, 117 et 153) : les refus passent de 40 à
    66. Sur 31 refus nouveaux, 15 remplacent une culture fausse de BASE et 12 une
    réponse sans culture ; 5 refus de BASE sont levés. Restent 4 refus et 1 sortie de
    famille factuelle sur des questions dont BASE trouvait la bonne culture. Les deux
    premiers viennent du jeu de 150 cas, où ils n'étaient comptés que comme pertes. Le
    propriétaire tranche (Q6) :
    - « aw ye nɛgɛ jiridenw jukoro ka mara » (« nɛrɛ » transcrit « nɛgɛ ») :
      CONSEIL_PRODUCTION → HORS_SUJET ;
    - « aw bɛ se ka sumba la kɛ a kisɛw la ka feere lɔgɔ la » (« sumbala » coupé) :
      CONSEIL_PRODUCTION → HORS_SUJET ;
    - « aw ye ntentu lu kisɛ ɲuman falen san cnra fɛ » (« ntèntulu » coupé, sans verbe
      agricole) : CONSEIL_PRODUCTION → HORS_SUJET ;
    - « aw ye kisɛw ja ka ɲɛ sani ka sumba la kɛ » (« sumbala » coupé, sans verbe
      agricole) : CONSEIL_PRODUCTION → HORS_SUJET ;
    - « aw bɛ se ka sumba la kɛ a kisɛ la ka fere sugu la » (« sumbala » coupé,
      brouillon de l'issue #67) : QUESTION_VENTE → QUESTION_GENERALE.
- **Résidus connus de BASE, non traités** (relevés par la seconde contre-vérification ;
  ce ne sont pas des régressions) :
  - « mali » → « malo » (i → o, étape 3) : environ 170 textes de francophonia, le
    premier résidu. La règle i → o le garde, comme BASE ;
  - « ka ban » → « kaban » (étape 4) : 34 dans findora, 14 dans francophonia ;
  - la clé « ka ba » sur un mot entier : 9 et 21 (findora, francophonia) ;
  - « finiw » → « fini » (fonio), par le suffixe -w : environ 40 dans francophonia ;
  - « bɛni » → « beni », « gali » → « gari », « lɔni » → « jɔni ».
- **Migration / travail induit** :
  - fichiers : `app/services/asr/normalizer/{culture,data,exact,fuzzy}.py`,
    `app/services/asr/normalizer/ecart.py` (nouveau),
    `dictionnaires/asr_normalizer_regles.json` (nouveau),
    `tests/unit/test_asr_normalizer.py`, `tests/unit/test_asr_normalizer_helpers.py`,
    une entrée d'Historique dans ADR-0020 ;
  - tests : le fichier `tests/unit/test_asr_normalizer.py` de l'itération 2 (66 tests)
    échoue 22 fois sur le code de BASE et 9 fois sur celui de V4, sur les graines 0 à 5
    (seconde contre-vérification, avant les 2 tests de l'itération 3) ;
  - ordre de fusion : la PR A (ADR-0041) avant cette PR, ou les deux ensemble ;
  - rebase sur origin/APIPy (c8975dd) : sans conflit. c8975dd modifie `finetune/` et
    `docs/benchmarks/` 0004 et 0005, aucun fichier de cette PR ni de la PR A ;
  - rollback : `git revert` du commit ; si le fichier de règles manque, l'étape 4 ne
    fait rien ; `mot_seul.sans_verbe_agricole` mis à false ne retire que la lecture du
    mot seul sans verbe agricole ;
  - l'index `docs/adr/README.md` n'est pas mis à jour ici, pour ne partager aucun
    fichier avec l'autre PR du jour : à faire après les deux fusions.
- **Verrous futurs** : toute nouvelle confusion passe par le JSON et par la mesure (banc
  et leave-one-out). Les seuils restés dans le Python le restent :
  `_max_distance_for_word`, min(3, len//2), longueur < 4, `_AGRI_VERBS`, `_NEVER_FUSE`
  et la liste des noms français exclus. C'est une dette déjà existante.

### Validations en attente (locuteur natif ou propriétaire)

Ces points sont hors du code de cette décision et restent à valider :

1. Les règles de reconnaissance de V6 elles-mêmes : o → u, a → ɔ, a → o et g ↔ r à
   l'étape 4, la consonne parasite, le mot-outil final, le mot court du vocabulaire, et
   le mot seul sans verbe agricole (itération 3). Elles généralisent des erreurs de
   l'époque NeMo ; il faut des transcriptions MMS-dyu réelles avec leur référence
   (ADR-0022).
2. « fura » → « furaw » (ACTION_TRAITER) est le comportement de BASE, conservé. Les gloses
   du dépôt se contredisent : bambara_phrases, phrase 117, « ne bɛ fɛ ka fura sɔrɔ » →
   « Je veux un traitement » ; mais reponse_fr lit « fura » « feuilles » dans
   riz_diagnostic_001 et tomate_diagnostic_001, et « floraison » dans
   anacarde_validation_020.
3. Entrées de dictionnaire qui réécrivent des mots courants, inchangées :
   - « kan » → « ka » (58 fois dans la référence, « ka kan » devient « ka ka ») ;
   - « ka ba » → « kaba » : appliquée à des mots entiers (résidus ci-dessus) et avant
     « tigka », de même longueur (« tigka ba » lu comme du maïs). L'ordre des clés de
     même longueur se décide avec « kan » et « ka ba » ;
   - « walakaba » → « kaba » (38 fois, mot attesté dans Common Voice) ;
   - `PHRASE_SUBS` « ko » → « ku » (igname) ;
   - « kabarada » → « bàrànda », alors que « ka barada » (son travail) figure 5 fois
     dans koumankan.
4. Le conflit « anice » : `asr_corrections.json` donne « i ni ce », `FUSIONS` « a ni cɛ ».
   C'est le seul échec du rappel, dans BASE comme dans V6.
5. Les variantes phonologiques d'ADR-0020 réécrivent le texte servi, alors que la
   Décision les réservait au matching : « turu » → « tulu », et sur hf « lɔni » →
   « jɔni », « gali » → « gari ».
6. Les mots que le NLU ne connaît pas encore, dont le sens est à confirmer :
   - « fara » : « a fara sugu ma » est rendu par « le vendre au marché »
     (mais_vente_001), mais « furakɛ fara màlo fura la » par « Traite les feuilles »
     (riz_diagnostic_001) ;
   - « sega » (banque de phrases, sans traduction) ;
   - « suma » : « à l'ombre » d'après reponse_fr d'igname_stockage_001. BASE et V6 le
     lisent comme ACTION_PLANTER, via « suman » dans BASE et « sumaw » dans V6 ;
   - « bananen » : la glose de banane_diagnostic_001 (brouillon de l'issue #57,
     version_b) rend « Aw ye yiri bananen bɔ joona » par « Retirez les pieds malades
     vite ». Il fait gagner une banane à mais_diagnostic_001 et à 7 phrases des
     brouillons.
7. Le critère non négociable sur des transcriptions fautives (Q6) : les 4 refus et la
   sortie de famille listés en « Négatives assumées » sont-ils acceptables ?

## Références

- Banc du normalizer, 150 erreurs simulées, 124 erreurs documentées, leave-one-out,
  compare_all, jeux de 403 phrases et 96 pièges : session du 2026-10-07 (non versionnés).
- Seconde contre-vérification et mesure finale du 2026-10-12 : 117 cas nouveaux,
  153 cas sans verbe agricole, 3 597 textes propres, critère sur transcriptions
  simulées, arbre combiné PR A + PR B (non versionnés).
- `dictionnaires/asr_corrections.json`, `app/services/asr_bambara_normalizer.py`,
  `tests/unit/test_asr_normalizer.py` (issue #85), `data/GRAMMAIRE_DIOULA_REGLES.md` §9.
- `data/issue_57_banane_validation_draft.json` (banane_diagnostic_001) et
  `data/issue_62_patate_validation_draft.json` (patate_diagnostic_001) : « bananen ».
- ADR-0014, ADR-0020, ADR-0022, ADR-0027, ADR-0031, ADR-0039, ADR-0041 ;
  `docs/constraints.md` §1.2 et §2.3.

## Historique

- 2026-10-07 — rédaction (statut proposé) : options V1 à V5 de la première itération,
  contre-vérification, variante finale V6. Remplace l'amendement d'ADR-0020 proposé
  dans V4 (une entrée d'Historique d'ADR-0020 renvoie ici).
- 2026-10-12 — itération 3 (statut proposé) : corrections après la seconde
  contre-vérification. Code : pluriel des clés d'un seul mot (étape 1), mot seul sans
  verbe agricole (étape 4, `mot_seul.sans_verbe_agricole`), 2 tests. ADR : rôle de la
  PR A corrigé et ordre de fusion recommandé ; généralisation chiffrée sans verbe
  agricole ; critère contrôlé sur questions propres, refus sur transcriptions simulées
  listés (Q6) ; limites ajoutées (« tigka ba », « bananen » et la patate, résidus de
  BASE) ; variante « ordre des clés » écartée.
