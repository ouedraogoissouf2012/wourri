# ADR-0041 — Choix de la culture et homographes français dans le NLU

**Statut** : proposé
**Date** : 2026-10-12
**Auteur(s)** : Claude (assistant) sous direction de Ouedraogo Issouf
**Valideur** : Ouedraogo Issouf — en attente
**ADRs liés** : [ADR-0014](0014-promotion-corpus-v3-dioula-ci.md) (validation native, aucun dioula inventé), [ADR-0031](0031-moteur-amelioration-linguistique.md) (sas de validation linguistique), [ADR-0039](0039-politique-reponse-llm-et-escalade.md) (garde LLM : familles factuelles), [ADR-0015](0015-strategy-pattern-cascade-chat-et-anglais.md) (cascade de réponse), ADR-0042 (normalizer post-ASR, PR séparée, non fusionnée)

---

## Contexte

### Le problème

Quand une question cite plusieurs cultures, le NLU doit en retenir une : c'est elle qui
fixe la phrase française envoyée à DeepSeek (`culture_concept`), le préfixe
`[Paysan cultive: X]`, la réponse IVR, le conseil saisonnier et les métriques. Sur
`1332c8b` (base de cette décision), ce choix est **tiré au hasard** :

- `ConceptExtractor.extract` parcourt les mots par un `set` : l'ordre des concepts dépend de
  `PYTHONHASHSEED` ; `IntentClassifier.classify` refait un second tirage indépendant
  (`set(concepts)`), si bien que le préfixe contredit la phrase française ;
- en production, `PYTHONHASHSEED` n'est pas fixé (`Dockerfile.prod`) : une même question
  change de culture à chaque redémarrage ;
- mesuré sur 32 phrases du dépôt (58 cas à au moins deux entités, 10 graines) : 58 cas sur 58
  varient ; `culture_concept` n'est juste que dans 209 couples phrase-graine sur 460 ; le
  conseil saisonnier porte 12 fois sur une autre culture que la réponse servie.

Une règle déterministe « première culture citée » ne suffit pas : des mots-clés de culture
sont aussi des **mots français courants**. « Mais comment faire pour mon manioc » contient la
conjonction « mais » (mot-clé du maïs) ; en tête de phrase, elle deviendrait la culture
retenue à chaque fois. Sur un jeu de 403 phrases étiquetées (écrit, WhatsApp, vocal, mixte
dioula-français), un homographe employé dans son sens courant est lu comme culture 240 fois
sur 250 (« mais » 100/103, « fini » 25/30, partiel « gan » 30/30…).

### Ce qui cadre la décision

- Plan approuvé par l'utilisateur le 2026-10-07 (« tu peux aller ») : choix de culture
  déterministe, **première culture citée**, et traitement des homographes français.
- Critère **non négociable** fixé au même moment : aucune question agricole pour laquelle la
  base reconnaissait la bonne culture ne doit devenir un refus (`HORS_SUJET`) ni perdre son
  intent de famille factuelle (ADR-0039 : `QUESTION_VENTE`, `QUESTION_METEO_AGRICOLE`,
  `QUESTION_DATE`).
- `docs/constraints.md` §1.2 : aucune liste de mots en dur dans le Python ; §2.3 : ADR exigé
  pour une décision qui touche le NLU.
- ADR-0014 : aucun dioula inventé ; tout changement de **reconnaissance** d'un mot dioula
  est signalé « à valider nativement ».

### Pourquoi maintenant

Une première itération (variantes V0 à V3 ci-dessous) a été contre-vérifiée le 2026-10-07.
La variante alors recommandée (V1) corrigeait bien l'ordre, mais transformait des questions
agricoles en refus hors-sujet et sortait des questions de prix de la famille `QUESTION_VENTE`.

La deuxième itération (option E, première version, rédigée le 2026-10-07) a été
contre-vérifiée à son tour et jugée non publiable. La seconde contre-vérification a écrit
83 nouveaux pièges (« pièges2 ») et relevé trois défauts bloquants :

- un faux partiel (« organique », « automatique », « Kabadougou ») suffisait à retirer un
  homographe qui était la vraie culture : sur les pièges2, 8 régressions déterministes du
  préfixe et 6 de la culture servie par l'IVR ;
- retirer une culture changeait l'intent (le barème donne 10 points par culture) : 8
  questions des pièges2 passaient vers une salutation horaire ou vers la météo ;
- l'ADR affirmait sans réserve qu'aucune vraie culture n'était perdue et qu'aucune
  régression n'était déterministe ; sur les pièges2, 24 phrases perdaient une vraie culture.

Elle a proposé trois corrections et les a mesurées sur des prototypes. Elles sont appliquées
au code le 2026-10-12 (itération 3) : un partiel ne fait plus retirer un homographe et passe
après lui ; l'intent se calcule avant le retrait ; un nombre compte comme mot voisin. Les
chiffres de E sont ceux de l'itération 3 ; ceux de la première version sont étiquetés
« E, itération 2 ».

### Comment les options ont été mesurées

Mêmes outils pour toutes les options, code réel de l'arbre, base pgvector remplacée par un
bouchon qui sert la première culture demandée ayant une entrée (intent, culture) dans
`corpus_ivr.json` (essais 1 et 2 réels de `chercher_reponse_ivr`). Jeux (non versionnés,
sessions du 2026-10-07 et du 2026-10-12) :

- **jeu A-jeu** : 403 phrases étiquetées à la main (293 à culture principale) ; chemin
  « NLU seul » et chemin vocal (normalizer post-ASR puis NLU) ;
- **96 pièges** écrits par la première contre-vérification pour casser la règle (76 à
  culture principale) ; A-jeu et ces pièges forment les « 499 phrases » (369 à culture
  principale) ;
- **83 pièges2** écrits par la seconde contre-vérification (65 à culture principale ; écrit
  15, WhatsApp 41, vocal 18, mixte 9 ; dioula recopié de `bambara_phrases.json`) ;
- **jeu A-ordre** : 32 phrases du dépôt × 2 chemins, 46 cas à culture attendue connue, 10 graines ;
- **compare_all** : les 1 735 textes du dépôt (corpus IVR, phrases bambara, banque de phrases,
  questions) avant/après, NLU seul et chemin vocal ;
- **textes du dépôt à culture connue** (phrases attestées, réponses du corpus, questions),
  mesurés à l'itération 2 seulement.

Pour la base, les chiffres sont des moyennes sur 12 graines (63,8 % = espérance) ; les
options sont déterministes. À l'itération 3, les autres mesures ont été refaites sur l'arbre
final : 12 graines pour le déterminisme, le préfixe et l'IVR ; `culture_concept` calculé
comme le fait `NLUService.process` (classifieur sur tous les concepts), aux graines 0 à 2,
sorties identiques. Le dioula des tests et des mesures est recopié du dépôt.

## Questions posées avant la décision

1. Quelle règle de choix quand la phrase cite plusieurs cultures ?
2. Un homographe hors contexte sûr doit-il être retiré même quand c'est le seul signal de culture ?
3. Une culture vue seulement par un partiel (« anacardiers », « lanacarde ») passe-t-elle avant
   ou après une culture citée par un mot entier ?
4. La règle « un partiel ne compte qu'en début de mot » (V1) peut-elle entrer sans validation native ?
5. Que faire quand la première culture citée n'a pas d'entrée IVR pour l'intent ?
6. Que faire si la section de configuration des homographes est invalide ?
7. La règle des homographes peut-elle changer l'intent ? (soulevée par la seconde
   contre-vérification)
8. Un nombre peut-il servir de mot avant ou après un homographe ? (idem)

Réponses obtenues (plan approuvé par l'utilisateur le 2026-10-07 et critère non négociable
fixé le même jour) :

- Q1 → première culture citée.
- Q2 → non : un homographe ne doit jamais faire d'une question agricole un refus. Il n'est
  retiré que si une autre culture est citée de façon sûre.

Propositions du concepteur, à valider par le valideur (elles s'appuient sur les mesures des
options et des variantes de E ci-dessous) :

- Q2, mise en œuvre → « citée de façon sûre » veut dire citée par un mot entier ou un
  multi-mots ; un partiel ne suffit pas (itération 3). À l'itération 2, un partiel suffisait,
  et un faux partiel retirait la vraie culture.
- Q3 → après : une culture vue seulement par un partiel passe après celles citées par un mot
  entier ou un multi-mots (ce que la base faisait par hasard), et après un homographe douteux
  gardé (itération 3). C'est un écart avec la lettre du plan (« première culture citée ») :
  « lanacarde a combien cette annee ? mon voisin fait le cacao » donne le cacao.
- Q4 → non : elle change la reconnaissance de mots dioula (walakaba, gɔfɛrɛnɛrɛ, lamaloya) ;
  elle sort de cette décision et devient une option future soumise à validation native.
- Q5 → garder le repli existant (la culture suivante est servie) et le documenter dans le code.
- Q6 → comportement explicite, testé, qui ne désactive pas tout le NLU.
- Q7 → non : l'intent se calcule sur tous les concepts, avant le retrait ; la règle ne choisit
  que la culture (itération 3).
- Q8 → oui : seuls les jetons sans lettre ni chiffre (ponctuation détachée, émoji) sont
  sautés ; dans « le 12 mais », le mot avant est « 12 » (itération 3). À l'itération 2, tout
  jeton sans lettre était sauté, chiffres compris.

## Options étudiées

Toutes les options rendent l'ordre déterministe (positions dans l'extracteur, liste ordonnée
dans le classifieur). A à D sont les variantes V0 à V3 de la première itération ; E est la
variante retenue, décrite dans sa version de l'itération 3.

### Option A — Ordre seul (V0)

- **Description** : ordre de première apparition dans le texte, sans traitement des homographes.
- **Avantages** : aucun changement d'ensemble de concepts ni d'intent (compare_all : 0 texte
  changé) ; déterministe ; `culture_concept` 63,8 % → 64,8 % sur A-jeu ; A-ordre 209 → 340/460.
- **Inconvénients** : les homographes en tête deviennent des erreurs **systématiques** (« mais
  comment faire pour mon manioc » → maïs à chaque fois) ; préfixe 72,1 % → 64,8 % (en baisse) ;
  un partiel placé avant passe devant (anacarde_validation_019 : néré au lieu d'anacarde).
- **Coût** : faible. **Compatibilité** : conforme.

### Option B — Contexte sûr strict + partiel en début de mot (V1)

- **Description** : un homographe hors contexte sûr (déterminant ou préposition avant, forme
  « maïs », dernier mot) ne compte **jamais** ; un partiel ne compte qu'en début de mot.
- **Avantages** : cultures en trop 240 → 36 ; `culture_concept` 82,3 %, préfixe 83,6 %, vocal
  90,2 % ; A-ordre 440/460 ; phrases sans culture qui reçoivent une culture 92 → 31/110.
- **Inconvénients (mesurés par la contre-vérification)** : 9 questions d'A-jeu à vraie culture
  deviennent des **refus hors-sujet** (« caoutchouc a encore baisse ? », « mes jeunes mais
  jaunissent », « mil » seul…) ; 6 questions de prix sortent de `QUESTION_VENTE` (garde
  ADR-0039 contournée) ; 12 bascules vers `QUESTION_METEO_AGRICOLE` ; « mais » sans
  déterminant perdu (pièges : FN 3 → 17) ; sur les 76 pièges à culture principale,
  `culture_concept` 49,6 → 29, avec 18 régressions déterministes ; compare_all : 76 textes du
  corpus IVR changent (58 d'intent) ; 51 phrases attestées n'ont plus de culture (walakaba,
  gɔfɛrɛnɛrɛ), changement de reconnaissance dioula non validé.
- **Coût** : moyen. **Compatibilité** : contraire au critère non négociable et à ADR-0014.

### Option C — Mot faible (V2)

- **Description** : une culture vue seulement par un homographe (12 mots, sans contexte) est
  retirée si une autre culture est citée ; partiel en début de mot.
- **Avantages** : meilleur choix brut sur A-jeu (`culture_concept` 85,3 %, préfixe 86,7 %) ;
  jamais de refus par construction.
- **Inconvénients** : le **vrai** maïs disparaît dès qu'une autre culture est citée (« euh je
  veux mettre du mais dans le bas-fond après le riz » → riz ; les deux cultures ne sont plus
  détectées que dans 11 phrases sur 22) ; FN 4 → 11 ; « cacao et café » perdrait le café ;
  compare_all : 75 textes du corpus changent (57 d'intent) ; même règle de partiel que B.
- **Coût** : faible. **Compatibilité** : perte de vraies cultures ; partiel non validé.

### Option D — Contexte sûr + indices faibles (V3)

- **Description** : B, plus des homographes de sens (café, lime, fibre…) et les partiels comme
  indices faibles.
- **Avantages** : cultures en trop 240 → 35 ; A-ordre 460/460.
- **Inconvénients** : mêmes refus que B (même règle stricte) ; nouveaux manques (listes à
  virgules « Malo, kaba, wala tiga », pluriels vus par partiel, oignons) ; deux règles ;
  compare_all : 79 textes du corpus changent (58 d'intent).
- **Coût** : moyen. **Compatibilité** : comme B.

### Option E — Ordre par classes + homographe retiré seulement à côté d'une culture citée par un mot entier (retenue)

- **Description** (itération 3 ; entre parenthèses, ce qui différait à l'itération 2) :
  1. **Ordre** : d'abord les concepts vus par un mot entier ou un multi-mots, puis les
     cultures vues seulement par des homographes douteux et gardées (point 3), puis les
     concepts vus seulement par un partiel (itération 2 : partiels avant douteux) ; dans
     chaque groupe, première apparition dans le texte, puis rang dans `nlu_concepts.json`.
     Le classifieur suit cet ordre : `culture_concept` = première culture de la liste.
     Partiels inchangés (sous-chaîne, comme avant).
  2. **Homographes** (« mais », « fini », « beni », « mil », « caoutchouc ») : chacun a ses
     contextes sûrs dans `nlu_concepts.json` (section `homographes`) — forme sûre (« maïs »),
     mots avant sûrs propres au mot, mots après qui rendent douteux (« mais pas », « mil
     francs ») ou sûr (« mais et », « mais ou »). Le mot avant ne compte pas s'il est accolé
     par un trait d'union (« arrose-le ») ou s'il termine un mot-clé multi-mots reconnu,
     quel qu'il soit (salutation « i ni ce », mais aussi « jusqu au »). Les jetons sans
     lettre ni chiffre (ponctuation détachée, émoji) sont sautés, pas un nombre : dans « le 12
     mais », le mot avant est « 12 » (itération 2 : tout jeton sans lettre était sauté). Pour
     « fini » et « beni », aucun mot français ne rend l'occurrence sûre (leur sens culture est
     dioula).
  3. **Règle de retrait** : une culture vue seulement par des occurrences douteuses est
     retirée si la phrase cite une autre culture par un mot entier ou un multi-mots ; gardée
     sinon, même à côté d'une culture vue seulement par un partiel (itération 2 : un partiel
     suffisait à la retirer). Un homographe ne fait donc jamais d'une question agricole un
     refus, et la question de prix garde sa culture.
  4. **Intent** : calculé sur tous les concepts, avant le retrait
     (`ConceptExtractor.extraire` rend `Extraction(concepts, concepts_intent)`,
     `NLUService.process` classe `concepts_intent`). Le barème ne dépend que de l'ensemble
     des concepts : l'intent est par construction celui que donne le dictionnaire sans la
     section `homographes`. Le premier `CULTURE_` est le même dans les deux vues
     (itération 2 : intent calculé après le retrait).
  5. Conseil saisonnier sur la culture servie ; métrique `/api/chat` = première `CULTURE_`
     (comme `/api/asr`, un `ANIMAL_` n'est plus compté comme culture).
- **Avantages (mesurés, base → E)** :
  - 499 phrases, NLU seul : `culture_concept` 236,6 → 313/369, préfixe 263,7 → 313, culture
    servie par l'IVR 252,2 → 296 ; 0 régression déterministe ; 150, 114 et 104 corrections.
    A-jeu seul : `culture_concept` 63,8 % → 85,0 % (249/293), préfixe 72,1 % → 85,0 %, IVR
    69,2 % → 80,9 % ; 96 pièges : 49,6 → 64/76, préfixe 52,6 → 64, IVR 49,6 → 59 ;
  - mêmes 499 phrases : cultures en trop 289 → 167, cultures manquées 44 → 44 ; aucune vraie
    culture que la base trouvait aux 12 graines n'est perdue sur ces deux jeux (les pièges2
    en perdent : voir les inconvénients) ;
  - chemin vocal (196 phrases, 147 à culture principale) : `culture_concept` 93,3 → 131,
    préfixe 106,4 → 131, IVR 103,2 → 126 ; 0 régression déterministe ; cultures manquées
    4 → 4. A-jeu seul : 64,6 % → 91,8 %, préfixe 74,6 % → 91,8 %, IVR 72,1 % → 88,5 % ;
  - pièges2, NLU seul : `culture_concept` 30,4 → 39/65, préfixe 40,1 → 39, IVR 39,0 → 40 ;
    chemin vocal (27) : 11,3 → 17, 15,6 → 18, 16,7 → 19 ; 0 régression déterministe de la
    culture retenue, mais 15 phrases perdent à chaque graine une vraie culture (voir les
    inconvénients) ; E, itération 2 : 17, 25 et 25, avec 8 régressions déterministes du
    préfixe et 6 de l'IVR ;
  - 0 refus hors-sujet nouveau et 0 changement d'intent, en mode dioula/both comme en mode
    FR, sur les 499 phrases et les pièges2, deux chemins : aucune sortie de `QUESTION_VENTE`,
    aucune bascule vers une salutation ou vers la météo (E, itération 2 : 1 changement sur
    A-jeu, mixte_025 ; 8 sur les pièges2) ;
  - A-ordre : `culture_concept` 209 → 460/460, métrique `/api/asr` 283 → 460, `/api/chat`
    268 → 450, culture servie juste 275 → 440, conseil sur une autre culture 12 → 0. Pour
    `/api/chat`, l'outil applique encore la formule de la base, qui compte un `ANIMAL_` ; la
    formule du routeur, première `CULTURE_`, est celle de `/api/asr` ;
  - compare_all : 8 textes sur 1 735 changent de concepts, 0 d'intent, uniquement des
    retraits (« mais » conjonction 6 fois, « fini » 2 fois) ; mêmes textes et mêmes concepts
    qu'à l'itération 2, qui comptait en plus deux phrases ajoutées à la main (1 737 textes),
    dont une changée ;
  - textes du dépôt, première culture juste (mesure de l'itération 2, non refaite) :
    questions 249 → 251 (vocal 247 → 252), réponses du corpus 336 → 338 (vocal 327 → 336),
    phrases attestées 147 → 148 (vocal 141 → 144) ;
  - déterminisme : 0 champ variable sur 12 graines (499 phrases et pièges2, deux chemins,
    tous les champs : concepts, intent, phrase française, préfixe, refus, cascade IVR,
    conseil), contre 328 et 362 phrases variables pour la base sur les 499 phrases (79 et 80
    sur les pièges2) ; A-ordre : 0 cas variable sur 10 graines.
- **Inconvénients (mesurés)** :
  - les phrases sans culture gardent leur fausse culture (A-jeu : 92/110, comme la base) :
    « j'ai planté mais rien ne pousse » reste une question sur le maïs ; c'est le prix du
    critère « jamais de refus » ;
  - pièges2 : 15 phrases perdent une vraie culture que la base trouvait aux 12 graines
    (cultures manquées 4 → 19 ; E, itération 2 : 24 phrases). Chaque fois, un homographe
    écrit sans contexte sûr, en style télégraphique, côtoie une autre culture citée par un
    mot entier : listes (« semences mais riz arachide dispo ? », « prix mil arachide a
    korhogo ? »), composés à trait d'union sans tréma (« association riz-mais c bon ? »),
    « mais avec niebe », « semer mais avant manioc », « caoutchouc et cacao », « caoutchouc
    ou cacao » (« caoutchouc » n'a aucun mot après sûr), « mil + riz », « mon mais pas
    encore mur », « jusqu au mais », puce collée (« -le mais »). Quatorze de ces phrases
    n'ont pas de culture principale dans le jeu ; la quinzième garde la bonne (le riz). La
    culture perdue sort de la réponse : « prix mais igname a bouake auj ? » ne garde que
    l'igname (préfixe, phrase française, IVR) ;
  - contextes jugés sûrs à tort : sur le groupe de 30 phrases des pièges2 écrit pour ce cas,
    `culture_concept` est juste 7 fois, contre 12,2 en moyenne pour la base (préfixe
    15,7 → 7, IVR 17,6 → 11) ; dans les 23 autres, la culture de l'homographe passe en tête.
    Cas relevés, pour « mais » : prépositions employées comme adverbes (« Et après ? Mais
    comment je fais pour mon riz ? », « je fais avec mais… », « on peut faire sans mais… »,
    « je suis pour mais… »), y compris à travers une fin de phrase (« Je suis pour ! Mais
    comment faire avec mon manioc ? ») ;
    « sur » pour « sûr » (« c sur mais cmt faire pr mon manioc ? ») ; « mais ou » pour
    « mais où » (« mais ou est ce que je vends mon cacao ? ») ; « mais et si » ; verbe
    « entre » (« L'eau entre mais elle ne ressort pas… ») ; « c le notre mais », « j'ai du
    son mais » ; en vocal, pronom écrit sans trait d'union (« arrose le mais doucement… ») ;
    « ani ce mais… » (voir les validations natives). Pour « mil » : « 15 mil ou 20 mil ».
    Pour « caoutchouc », au sens de matière ou de sachet, après « le », « mon », « ce » :
    « Le caoutchouc de mon pulvérisateur fuit… », « dans mon caoutchouc jai gardé les
    semences d arachide », « ce caoutchouc noir là on peut garder le maïs dedans » ;
  - régressions « chance » (la base tombait juste sur une partie des graines, E se trompe
    toujours) : 22 (`culture_concept`), 19 (préfixe) et 18 (IVR) sur les 499 phrases, 12 de
    chaque en vocal ; 25, 23 et 19 sur les pièges2, où elles annulent le gain du préfixe
    (40,1 → 39). Types : « première citée » sur les contrastes et les phrases « contexte puis
    question » (« Le maïs pousse bien, mais le riz souffre… pour le riz », « J'ai récolté
    l'igname ; comment planter le manioc », « pas le cacao mais le café », « Je veux remplacer
    mes caféiers par des cacaoyers ») ; contextes jugés sûrs à tort (ci-dessus) ; homographes
    de sens hors champ (« kiosque à café », « une lime ») ; « gombo. » collé au point (seuls
    les partiels de « fatigant » restent) ; « mais oui g deja traité lanacarde » (ci-dessous) ;
    en vocal, des cultures créées par le normalizer (« mille », « mangé », « gants »), qui
    relèvent de la PR du normalizer ;
  - contrepartie de l'itération 3 : « mais oui g deja traité lanacarde 2 fois » donne le
    maïs en premier, car l'anacarde n'y est vue que par un partiel (juste à 67 % des graines
    pour la base, à chaque graine pour E, itération 2) ; trois « gants en caoutchouc » sans
    culture gardent en plus l'hévéa ; sur A-jeu, cultures en trop 149 → 153. Un test fige
    cette limite ;
  - « Je veux planter l'hévéa mais je n'ai pas assez de terre » (3 phrases) : la base servait
    une réponse IVR sur le maïs (12/12), E ne sert plus de réponse IVR (pas d'entrée hévéa
    pour cet intent) : la question passe au niveau suivant de la cascade ;
  - l'intent compte encore la culture retirée (10 points par culture, comme la base) : la
    règle ne corrige pas le barème de l'intent, elle ne le modifie plus ;
  - changement de reconnaissance dioula, signalé : « fini » et « beni » ne comptent plus
    quand une autre culture est citée par un mot entier ou un multi-mots (« Ku ma fini ka ji
    don », igname_stockage_001, perd le mil).
- **Coût** : un module (`homographes.py`), une section JSON, la méthode `extraire` et son
  appel dans `NLUService.process` ; 62 tests unitaires (58 dans
  `test_nlu_ordre_homographes.py`, 4 dans `test_ivr_searcher.py`) et 1 test d'intégration ;
  1 568 tests passent (`tests/unit` et `tests/integration/test_chat_asr_endpoints.py`). Les
  mots voisins sont trouvés par dichotomie (l'itération 2 recalculait la liste à chaque
  homographe : coût quadratique relevé par la seconde contre-vérification).
- **Compatibilité** : listes dans `nlu_concepts.json` (§1.2) ; aucun mot dans le Python, qui
  ne garde que des règles de structure (jeton sans lettre ni chiffre, trait d'union, fin de
  multi-mots), décrites dans la section ; dioula des tests recopié du dépôt (ADR-0014).

#### Variantes de E mesurées pour trancher les sous-questions

Mesures déterministes. Les chiffres « E, itération 2 » ont été mesurés à l'itération 2, sur
A-jeu et les 96 pièges (deux chemins), à partir de E, itération 2. Les « prototypes » sont
ceux de la seconde contre-vérification (2 graines, mêmes outils) : elle a ajouté ses
corrections une à une, dans l'ordre des lignes 3 à 6, et les a mesurées aussi sur les
pièges2. L'arbre final donne les mêmes sorties que le dernier prototype sur les 499 phrases
et les pièges2.

| Sous-question | Choix (itération 3) | Alternative | Effet mesuré de l'alternative |
|---|---|---|---|
| Ordre entre mot entier et partiel seul | classe, puis position | position seule (comme V0/V1) | E, itération 2 : A-jeu `culture_concept` 249 → 234, préfixe et IVR : 15 régressions déterministes (le partiel de « organique », « organiser », « manganèse », « ouragan », « automatique » passe devant la vraie culture) ; vocal 111 → 106 ; pièges 64 → 62 ; A-ordre 460 → 440 (anacarde_validation_019 : néré) |
| Homographe douteux à côté d'une autre culture | retirer | garder, classé en dernier | E, itération 2 : 0 changement d'intent, `culture_concept` +1 (mixte_025), mais cultures en trop 149 → 240 et l'IVR sert le maïs pour « je veux planter l'hévéa mais… » (repli sur la fausse culture). L'itération 3 obtient le même intent en le calculant avant le retrait |
| Un partiel suffit-il à retirer un homographe douteux (« culture sûre ») ? | non (itération 2 : oui) | oui | E, itération 2 : sur A-jeu, même choix de culture et 149 cultures en trop au lieu de 153 (« mais oui g deja traité lanacarde » ; 3 « gants en caoutchouc ») ; pièges2 : 24 phrases perdent une vraie culture, contre 15 avec « non », dont 8 retirées par un faux partiel (« organique », « manganèse », « automatique », « fatigant », « Kabadougou », « génère ») |
| Rang de l'homographe douteux gardé face au partiel seul | douteux avant (itération 2 : partiel avant) | partiel avant | Prototypes, pièges2 : le faux partiel passe devant l'homographe vrai gardé, 8 régressions déterministes du préfixe et 6 de l'IVR (« mes jeunes mais ont besoin d engrais organique ? » → gombo) ; douteux avant : 0 et 0. E, itération 2 : sur A-jeu, douteux avant coûte « mais oui g deja traité lanacarde » (`culture_concept` 249 → 248) |
| Intent avant ou après le retrait | avant (itération 2 : après) | après | E, itération 2 : 1 changement d'intent sur A-jeu (mixte_025, vers la météo) ; prototypes, pièges2 : 8 en NLU seul, 3 en vocal (« ani sogoma mais comment faire pour mon manioc » → salutation, « Mon cacao est beau mais la chaleur me fait peur. » → météo). Avant : 0, et sur les pièges2 `culture_concept` 25 → 33, IVR 31 → 34 |
| Nombre avant ou après un homographe | compte comme mot (itération 2 : sauté) | sauté | Prototypes, pièges2 : `culture_concept` 33, préfixe 33, IVR 34 et cultures en trop 42, au lieu de 39, 39, 40 et 36 (« la pluie est tombée le 12 mais mon riz… », « jai traité le 3 mais… tomates », « sac dengrais pr 30 mil… cacao », « j'ai vendu pour 40 mil mon cacao ») ; 499 phrases : mêmes chiffres |
| « mais » sûr en dernier mot (« quand semer mais ») | non | oui | E, itération 2 : A-jeu identique ; pièges : 3 faux maïs de plus (« j ai mis l uree mais » en fin de phrase). La règle de retrait garde déjà « quand semer mais ? » seul ; « texte réduit au mot » l'est aussi |
| Mots après douteux | « pas » (mais), francs/f/fcfa (mil) | aucun | E, itération 2 : pièges `culture_concept` 64 → 61, vocal 19 → 17 (« traite le mais pas… cacao ») |
| « un » mot avant sûr de « mais » + « il » mot après douteux | non | oui | E, itération 2 : mêmes chiffres ; « il » rendrait douteux « hectare de mais il faut » (nom), « un » ne précède le maïs dans aucune phrase des jeux |
| Mots après sûrs « et », « ou » | oui | non | E, itération 2 : 3 vraies cultures perdues (« on peut associer mais et niebe ? », « je met mais ou arachide ? ») |

### Comparatif

| Critère (base → option) | Base | A (V0) | B (V1) | C (V2) | D (V3) | E, itération 2 | E, itération 3 (retenue) |
|---|---|---|---|---|---|---|---|
| `culture_concept` juste, A-jeu (293) | 63,8 % (aléatoire) | 64,8 % | 82,3 % | 85,3 % | 82,9 % | 85,0 % | 85,0 % |
| préfixe DeepSeek juste, A-jeu | 72,1 % | 64,8 % | 83,6 % | 86,7 % | 84,3 % | 85,3 % | 85,0 % |
| `culture_concept`, chemin vocal, A-jeu (122) | 64,6 % | 71,3 % | 90,2 % | 91,0 % | 91,0 % | 91,0 % | 91,8 % |
| cultures en trop, A-jeu (homographes, /250) | 240 | 240 | 36 | 91 | 35 | 149 | 153 (a) |
| vraies cultures manquées, A-jeu (homographes, /141) | 4 | 4 | 7 | 11 | 8 | 4 | 4 (a) |
| `culture_concept` juste, 96 pièges (/76) | 49,6 | non mesuré | 29 | non mesuré | non mesuré | 64 | 64 |
| pièges2 : `culture_concept`, préfixe, IVR justes (/65) | 30,4 ; 40,1 ; 39,0 | non mesuré | non mesuré | non mesuré | non mesuré | 17 ; 25 ; 25 | 39 ; 39 ; 40 |
| pièges2 : phrases qui perdent une vraie culture que la base trouvait aux 12 graines | — | non mesuré | non mesuré | non mesuré | non mesuré | 24 | 15 |
| régressions déterministes de la culture retenue (A-jeu et pièges ; pièges2) | — | non mesuré | 18 sur les pièges (`culture_concept`) ; non mesuré | non mesuré | non mesuré | 0 ; 8 (préfixe) et 6 (IVR) | 0 ; 0 |
| refus hors-sujet nouveaux (questions à vraie culture) | — | 0 (ensembles inchangés) | 9 | 0 (par construction) | oui (règle de B), non chiffré | 0 | 0 |
| sorties de `QUESTION_VENTE` | — | 0 (ensembles inchangés) | 6 (A-jeu) | non mesuré | non mesuré | 0 | 0 |
| bascules d'intent vers une salutation ou la météo (A-jeu et pièges ; pièges2) | — | 0 (ensembles inchangés) | 12 vers la météo (A-jeu) ; non mesuré | non mesuré | non mesuré | 1 ; 8 | 0 ; 0 |
| `culture_concept` juste, A-ordre (/460) | 209 | 340 | 440 | 440 | 460 | 460 | 460 |
| corpus IVR changés dans compare_all (dont intent) | — | 0 | 76 (58) | 75 (57) | 79 (58) | 4 (0) | 4 (0) |
| reconnaissance dioula modifiée | — | non | partiels (walakaba, gɔfɛrɛnɛrɛ…), fini, beni | partiels, fini, beni | partiels, fini, beni | fini, beni (à côté d'une culture vue par un mot entier ou un partiel) | fini, beni (à côté d'une culture vue par un mot entier ou un multi-mots) |
| variation selon `PYTHONHASHSEED` | oui | non | non | non | non | non | non (b) |

(a) E, itération 3 : l'évaluation par homographe (/250, /141) n'a pas été refaite. Le bilan
des ensembles donne 240 → 153 cultures en trop et 34 → 34 cultures manquées, sans vraie
culture perdue sur A-jeu. Pour la base et E, itération 2, ce bilan et l'évaluation par
homographe donnent les mêmes cultures en trop (240 et 149).

(b) Chemin vocal : tant que la PR du normalizer (ADR-0042) n'est pas fusionnée, la sortie du
normalizer dépend encore de la graine pour « laba » (voir les conséquences) ; 0 sortie
variable sur les jeux mesurés.

## Décision

**Option retenue** : E, dans sa version de l'itération 3 — ordre par classes et homographe
retiré seulement à côté d'une culture citée par un mot entier ou un multi-mots.

**Justification** :

- Parmi les options qui traitent les homographes, E est la seule pour laquelle le critère non
  négociable est vérifié sur tous les jeux : 0 refus nouveau et 0 changement d'intent (mode
  dioula/both et mode FR) sur les 499 phrases et les pièges2, deux chemins, donc aucune
  sortie de la famille VENTE. B et D créent des refus ; pour C, les sorties de VENTE n'ont pas
  été mesurées, et compare_all change 57 intents du corpus IVR. A ne change aucun ensemble,
  mais rend systématiques les erreurs des homographes en tête et fait baisser le préfixe
  (72,1 % → 64,8 %).
- Choix de la culture : sur A-jeu, `culture_concept` et préfixe à 85,0 % (C : 85,3 % et
  86,7 %) ; 0 régression déterministe de la culture retenue sur A-jeu, les 96 pièges et les
  pièges2. Ce n'est pas vrai des cultures détectées : sur les pièges2, 15 phrases perdent à
  chaque graine une vraie culture (point suivant).
- Vraies cultures : sur A-jeu, E n'en perd aucune (manquées 34 → 34), C en perd
  (homographes manqués 4 → 11) ; sur les 96 pièges, E n'en perd aucune (10 → 10). E en perd
  pourtant aussi : sur les pièges2, 15 phrases perdent une vraie culture que la base trouvait
  aux 12 graines. Comme C, E retire la vraie culture écrite sans contexte sûr quand une
  autre culture est citée par un mot entier (C n'a pas été mesurée sur ces pièges). La
  différence est l'étendue : E garde l'homographe dans ses contextes sûrs (« du mais », « le
  mil et le riz », « mais et niebe »), C le retire dans tous les cas.
- Les régressions « chance » restantes sont d'un type connu : la règle « première citée »
  elle-même (contrastes, « contexte puis question »), les contextes jugés sûrs à tort, les
  homographes de sens hors champ, la ponctuation collée, et en vocal les insertions du
  normalizer. Sur les pièges2, écrits pour casser la règle, le préfixe ne progresse pas
  (40,1 → 39).
- Sur les textes du dépôt, E ne change aucun intent (compare_all : 8 textes sur 1 735,
  uniquement des retraits) ; B en changeait 58 dans le corpus IVR.
- Les classes (mot entier, puis homographe douteux gardé, puis partiel) rendent la règle
  explicable en une phrase et corrigent anacarde_validation_019 sans toucher à la
  reconnaissance des partiels.
- Retirer plutôt que classer en dernier : sinon le repli IVR sert la fausse culture quand la
  vraie n'a pas d'entrée (mesuré : réponse maïs pour une question sur l'hévéa).
- Corrections de l'itération 3 : sans elles, un faux partiel retire la vraie culture (8
  régressions déterministes du préfixe sur les pièges2) et le retrait change l'intent (8
  bascules vers une salutation ou la météo). Leur prix mesuré : « mais oui g deja traité
  lanacarde » donne le maïs, et A-jeu compte 4 cultures en trop de plus (149 → 153).

**Ce que cela signifie concrètement** :

- `concept_extractor.py` : occurrences avec position et nature (`MOT`, `DOUTEUX`, `PARTIEL`,
  qui sont aussi les rangs de l'ordre) ; règle de retrait (seule une culture vue par un mot
  entier ou un multi-mots fait retirer, `_NATURES_SURES`) ; tri par (nature, position, rang
  JSON) ; `extraire` rend les concepts retenus et ceux de l'intent ; mot voisin = jeton qui
  contient une lettre ou un chiffre, trouvé par dichotomie. `homographes.py` : lecture et
  validation de la section, test des contextes sûrs. Aucun mot dans le Python.
- `nlu_service.py` : l'intent est classé sur `concepts_intent` ; la phrase française et le
  résultat gardent les concepts retenus.
- `intent_classifier.py` : liste ordonnée au lieu d'un `set` ; `culture_concept` = première
  culture de la liste.
- `ivr_searcher.py` : conseil saisonnier sur la culture servie ; `routers/chat.py` : métrique
  = première `CULTURE_`.
- Repli IVR conservé (Q5) et documenté là où il a lieu (`corpus_service.chercher_reponse_ivr`,
  essai 1, et ses deux appelants dans `ivr_searcher.py`).
- Section invalide (Q6) : signalée en `ERROR` au chargement ; la **règle** est désactivée
  (chaque homographe compte comme culture, comme avant) mais le NLU reste disponible. Sont
  refusés : une section sans objet « mots », une déclaration qui n'est pas un objet, un champ
  inconnu, une liste qui n'est pas une liste de mots d'un seul mot, un champ texte
  (`sens_courant`, `note`) qui n'est pas un texte, un homographe qui n'est pas un mot-clé
  d'un seul mot de sa `CULTURE_` ou qui contient un de ses partiels, une même forme
  normalisée déclarée deux fois (« mais » et « maïs »). Auparavant, une erreur de lecture
  faisait renvoyer `None` à `get_nlu_service` et coupait tout le NLU. Le fichier livré est
  vérifié par les tests.

## Conséquences

- **Positives** :
  - même culture en tête pour la phrase française, le préfixe DeepSeek, la liste transmise à
    l'IVR et les deux métriques, sans dépendre du redémarrage (chemin vocal : sauf « laba »,
    voir plus bas) ; le conseil saisonnier suit la culture servie ;
  - « mais comment faire pour mon manioc », « j'ai fini de semer le riz », « Dieu a béni ma
    récolte de cacao » ne parlent plus du maïs, du mil ni du sésame ;
  - la règle des homographes ne change aucun intent : ni refus, ni sortie de la famille
    VENTE, ni bascule vers une salutation ou la météo (0 sur les 499 phrases et les pièges2) ;
  - le conseil saisonnier ne parle plus d'une autre culture que la réponse.
- **Négatives assumées** :
  - sans autre culture citée par un mot entier, un homographe reste lu comme culture (« oui
    mais », « c'est fini », « soyez béni », « gants en caoutchouc ») : 92 phrases sans
    culture sur 110 en reçoivent une, comme avant ;
  - à l'inverse, à côté d'une culture citée par un mot entier, un homographe écrit sans
    contexte sûr est retiré même quand c'est une vraie culture : listes et messages
    télégraphiques (pièges2 : 15 phrases, dont « semences mais riz arachide dispo ? » et
    « prix caoutchouc et cacao a soubre ? ») ;
  - contextes jugés sûrs à tort, à mesurer sur de vraies transcriptions avant de toucher aux
    listes : prépositions employées comme adverbes (« je suis pour mais… », « on verra après
    mais… »), « sur » pour « sûr », « mais ou » pour « mais où », « mais et si », caoutchouc
    au sens de matière après « le », « mon », « ce » (pièges2 : 7 justes sur 30, base 12,2) ;
  - l'exclusion « mot avant qui termine un mot-clé multi-mots » vaut pour tous les
    multi-mots, pas seulement les salutations : « jai desherbe le riz jusqu au mais du
    voisin » perd le maïs (« jusqu au », `TEMPS_HORIZON_LOINTAIN`). À l'inverse, une variante
    de salutation absente des mots-clés ne protège pas : « ani ce mais comment faire pour mon
    manioc » donne le maïs en premier, car « ce » y est un mot avant sûr ;
  - « mais oui g deja traité lanacarde » donne le maïs : une culture vue seulement par un
    partiel ne fait pas retirer l'homographe et passe après lui ;
  - « première citée » se trompe sur les contrastes (« pas le cacao mais le café ») et sur les
    phrases « contexte puis question » : c'est la cause de 16 des 22 régressions « chance » de
    `culture_concept` sur les 499 phrases ;
  - chemin vocal : tant que la PR du normalizer (ADR-0042) n'est pas fusionnée, la sortie du
    normalizer dépend encore de `PYTHONHASHSEED` pour « laba » (« daba » aux graines 0 et 1,
    « jaba », donc `CULTURE_OIGNON`, aux graines 2 et 3, relevé par la seconde
    contre-vérification). Aucun texte des jeux mesurés n'est touché (0 sortie variable) ;
  - homographes de sens non traités : café (« kiosque à café »), lime (l'outil), fibre
    (« fibre optique », « fibre de coco »), coton (« coton et alcool »), sésame (« le sésame
    pour exporter »), oignons (« occupe-toi de tes oignons »), chocolat (le produit). Faux
    partiels conservés (« organique », « gants », « fatigant », « automatique », « génère ») :
    ils ne passent plus devant une culture citée par un mot entier ni devant un homographe
    gardé, et ne font plus retirer un homographe ;
  - repli IVR : si la première culture citée n'a pas d'entrée pour l'intent, la réponse porte
    sur la suivante (jeu A-ordre : agrumes cités, igname servie, 20 cas sur 460) ;
  - l'ordre de `nlu_concepts` renvoyé par `/api/asr` change (le serveur WhatsApp lit
    `nlu_message` en priorité) ; les métriques `top_cultures` ne sont pas comparables avant
    et après.
- **Validations natives en attente (ADR-0014)** :
  - « fini » (fonio) et « beni » (sésame) : ne comptent plus quand une autre culture est
    citée par un mot entier ou un multi-mots ; aucun texte du dépôt ne les emploie au sens
    culture (« Ku ma fini ka ji don » est traduit « Ne les lavez pas ») ;
  - particules « le » et « de » (« magamaw le ye », « Kabako de Kɛra ») : restent des mots
    avant sûrs de « mais », un « … le mais … » en dioula compte donc comme maïs ;
  - « ani ce » (`bambara_phrases.json`, phrase d'indice 1, source `asr-variante`, « Merci »
    dans le fichier) n'est pas un mot-clé `SALUTATION` (qui contient « i ni ce », « a ni ce »,
    « anice ») : son « ce » compte comme mot avant sûr de « mais ». La protection d'une
    salutation dépend de sa présence dans les mots-clés ; ajouter « ani ce » aux mots-clés
    changerait la reconnaissance d'un mot dioula, c'est au natif de le trancher ;
  - « walakaba » (41 phrases attestées de mais_conseil_001), « gɔfɛrɛnɛrɛ(w) » (10, de
    nere_conseil_001), « lamaloya » : leur sens culture n'est pas établi ; ils restent
    reconnus par partiel, comme avant. Prérequis de l'option future ci-dessous.
- **Options futures (non décidées ici)** :
  - **partiel seulement en début de mot** (option B) : retire « mugan », « organique »,
    « fatigant », « automatique », « génère » ; mesuré, il retire aussi le maïs de 41 phrases
    « walakaba » et le néré de 10 phrases « gɔfɛrɛnɛrɛ » : à décider après validation native ;
  - **« plus souvent citée »** (à égalité, la première) : 19/22 sur les phrases à deux vraies
    cultures d'A-jeu contre 12/22 pour « première citée », 67/82 contre 60/82 sur les textes
    du dépôt et A-jeu réunis (mesure de la première itération) ; à mesurer sur de vraies
    transcriptions avant d'en changer ;
  - marqueurs de contraste dans le JSON (« pas X mais Y », « plutôt que », « remplacer X par Y ») ;
  - ponctuation collée (« maïs. », « riz, ») : la décoller ferait passer ces mots par la
    règle des homographes ; changement à part, à mesurer.
- **Migration / travail induit** : fichiers `app/services/nlu/concept_extractor.py`,
  `app/services/nlu/homographes.py` (nouveau), `app/services/nlu/intent_classifier.py`,
  `app/services/nlu/nlu_service.py`, `app/services/chat/ivr_searcher.py`,
  `app/services/corpus_service.py` (commentaire), `app/routers/chat.py`,
  `dictionnaires/nlu_concepts.json` (v3.4, changelog daté du 2026-10-12), tests. Aucun
  fichier en commun avec la PR du normalizer (ADR-0042). Ligne d'index à ajouter dans
  `docs/adr/README.md` au merge (le numéro se prend au merge). Retour arrière :
  `git revert`, sans migration de données.
- **Verrous futurs** : changer de règle de choix (« plus souvent citée ») ne touche que le tri
  de l'extracteur ; ajouter un homographe ne demande qu'une entrée JSON, validée au
  chargement ; l'intent ne dépend pas de la section `homographes`, qui ne change que la
  culture retenue.

## Références

- Plan approuvé le 2026-10-07 (« tu peux aller ») ; contre-vérification de la première
  itération (V0 à V3) du même jour ; seconde contre-vérification de l'itération 2 (verdict
  « non publiable », bloquants B1 à B3, 83 pièges2, prototypes des trois corrections).
- Audit des sites dépendant de l'ordre : `concept_extractor.py`, `intent_classifier.py`,
  `sentence_builder.py`, `nlu_preprocessor.py`, `ivr_searcher.py`, `corpus_service.py`,
  `routers/chat.py`, `routers/asr.py`, `calendrier_agricole.py`.
- Jeux et outils de mesure des sessions du 2026-10-07 et du 2026-10-12 (non versionnés) :
  jeu A-jeu (403 phrases), 96 pièges, 83 pièges2, jeu A-ordre, compare_all, textes du dépôt
  à culture connue.
- Tests : `tests/unit/test_nlu_ordre_homographes.py`, `tests/unit/test_ivr_searcher.py`,
  `tests/integration/test_chat_asr_endpoints.py`.
- ADR-0042 (PR du normalizer, non fusionnée) : abstention du fuzzy quand plusieurs variantes
  phonologiques d'un mot sont dans le vocabulaire (cas « laba »).

## Historique

- 2026-10-07 — rédaction, statut proposé.
- 2026-10-12 — itération 3, statut proposé : trois corrections de la seconde
  contre-vérification (un partiel ne fait plus retirer un homographe et passe après lui ;
  intent calculé avant le retrait ; un nombre compte comme mot voisin), validation de la
  section renforcée, mesures finales ; affirmations ramenées aux jeux mesurés ; réponses aux
  questions 3 à 8 présentées comme propositions à valider.
