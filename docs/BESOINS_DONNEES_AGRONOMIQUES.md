# Besoins en données — la vie d'une plante

> **Objet** : parcourir le cycle complet d'une plante, stade par stade, pour
> établir quelle donnée est nécessaire à quel moment, et quelle décision elle
> permet.
>
> **Périmètre** : prospectif, indépendant de toute source de données. L'état
> actuel de la chaîne est documenté dans
> [CONTRAT_API_OPEN_METEO.md](CONTRAT_API_OPEN_METEO.md) pour l'acquisition et
> [TRAITEMENT_DONNEES_METEO.md](TRAITEMENT_DONNEES_METEO.md) pour le traitement.
>
> **Établi le** : 2026-09-11

---

## Niveau de vérification

| Marque | Signification |
|---|---|
| **[CODE]** | Établi par lecture du code Wourri |
| **[SOURCÉ]** | Établi par une source externe identifiée, citée en fin de document |
| **[À VALIDER]** | Ordre de grandeur, ou valeur établie sous d'autres latitudes — **à faire confirmer pour les conditions ivoiriennes avant tout usage** |

> **Règle de validation.** Les seuils, fenêtres et coefficients agronomiques
> **ne doivent pas être inventés**, ni transposés sans examen depuis d'autres
> zones climatiques. Toute valeur marquée [À VALIDER] attend sa source auprès
> d'une institution agronomique compétente. Même exigence que celle appliquée au
> corpus linguistique par l'ADR-0014.

---

## 1. Le principe : une donnée n'a pas de sens en soi

C'est le point de départ, et il commande tout le reste.

**La pluie n'est pas une information. C'est trois informations opposées selon le
stade de la plante.**

| Stade | Ce que signifie « il pleut » | Décision induite |
|---|---|---|
| Avant semis | déclencheur — la fenêtre s'ouvre | semer |
| Floraison | survie — la fécondation est sauvée | rien à faire, mais l'angoisse tombe |
| Récolte et séchage | **menace** — pourrissement, aflatoxine | rentrer, bâcher, retarder |

Aujourd'hui le système applique **une seule interprétation** de la pluie, quel que
soit le stade : une pluie légère déclenche systématiquement *« bon moment pour
commencer les semis »* — [CODE]. Ce message est juste en mars et absurde en
octobre sur une parcelle prête à récolter.

**C'est la racine de l'impression « robotique ».** Le système ne sait pas où en
est la plante, donc il ne peut pas interpréter ce qu'il mesure.

```
DONNEE  +  STADE PHENOLOGIQUE  =  INFORMATION
   |             |
   |             └── absent du systeme aujourd'hui
   └── present mais instantane
```

Il manque donc deux choses, et l'une conditionne l'autre :
1. **savoir où en est la plante** — le stade ;
2. **avoir mémorisé ce qu'elle a subi** — l'historique.

---

## 2. Le cycle, stade par stade

Pour chaque stade : le processus physiologique, le facteur limitant, la donnée
qui le mesure, la résolution temporelle nécessaire, et la décision rendue possible.

### Stade 0 — Avant le semis : préparer et décider

| | |
|---|---|
| **Processus** | Le sol se réchauffe et se réhumidifie. Rien ne vit encore. |
| **Ce qui se joue** | La décision la plus coûteuse de l'année : **quand semer**. Semer trop tôt sur une fausse pluie → la levée grille. Semer trop tard → le cycle ne tient pas dans la saison. |
| **Donnée nécessaire** | Démarrage effectif des pluies (*onset*) — pas la moyenne calendaire. Cumul des 3 à 10 derniers jours. **Absence de séquence sèche dans les 20-30 jours à venir.** Humidité et température du sol. |
| **Résolution** | journalière, avec **regard avant** de 2 à 4 semaines |
| **Décision** | semer / attendre / choisir une variété à cycle plus court |

La difficulté est que l'onset n'admet pas de définition unique : sur un site
ivoirien, quatre méthodes de référence donnent des dates s'étalant sur **32 jours**,
et une longueur de saison variant de 95 à 127 jours — [SOURCÉ].

Le système travaille aujourd'hui sur une fenêtre calendaire **constante** —
[CODE]. Elle ne varie pas d'une année à l'autre, alors que l'onset réel varie de
plusieurs semaines.

### Stade 1 — Semis

| | |
|---|---|
| **Processus** | La graine est placée. Elle absorbe l'eau du sol (imbibition). |
| **Ce qui se joue** | Le contact graine-sol et l'humidité du lit de semence. |
| **Donnée nécessaire** | Pluie des jours suivants, humidité du sol, **absence de pluie battante** dans les 48 h (croûte de battance, semence déchaussée). |
| **Résolution** | journalière, regard avant de 3 à 7 jours |
| **Décision** | semer aujourd'hui ou décaler de quelques jours |

**Et surtout : la date de semis doit être enregistrée.** C'est le point zéro du
compteur. Sans elle, aucun stade ultérieur n'est calculable.

### Stade 2 — Germination et levée

| | |
|---|---|
| **Processus** | L'embryon se développe, la plantule perce. C'est la phase la plus fragile de toute la vie de la plante. |
| **Ce qui se joue** | La densité du peuplement — définitive. Une levée ratée ne se rattrape pas. |
| **Donnée nécessaire** | **Température du sol** (seuil de germination), humidité du sol maintenue, absence de séquence sèche de 5-7 jours, absence de croûte. |
| **Résolution** | journalière |
| **Décision** | ressemer ou non — décision à prendre sous 10 à 15 jours |

C'est ici que la **température du sol**, jamais évoquée dans une prévision
classique, compte davantage que la température de l'air.

### Stade 3 — Croissance végétative

| | |
|---|---|
| **Processus** | La plante installe ses feuilles et ses racines. Elle construit l'usine qui produira plus tard. |
| **Ce qui se joue** | La surface foliaire, donc la capacité photosynthétique future. |
| **Donnée nécessaire** | **Degrés-jours cumulés** — le rythme réel de développement. Cumul d'eau, rayonnement, statut azoté. |
| **Résolution** | cumul depuis le semis, mis à jour quotidiennement |
| **Décision** | date du premier apport d'engrais, sarclage, désherbage |

**Le degré-jour est ici l'unité de temps pertinente, pas le jour civil.** Une
plante avance en somme de températures. Une saison fraîche décale l'ensemble du
cycle ; un calendrier en mois dérive, un compteur en degrés-jours suit.

### Stade 4 — Transition florale

| | |
|---|---|
| **Processus** | La plante bascule du végétatif au reproductif. L'organe reproducteur s'initie, invisible de l'extérieur. |
| **Ce qui se joue** | **Le potentiel de rendement est fixé ici**, avant même la floraison. |
| **Donnée nécessaire** | Absence de stress hydrique, absence de stress thermique. |
| **Résolution** | journalière, sur une fenêtre courte |
| **Décision** | dernière fenêtre utile pour une irrigation de sauvetage |

Sur maïs, la transition intervient autour de 10-12 feuilles ; un déficit hydrique
à ce moment réduit **le nombre de rangs et le nombre d'ovules par rang** — [SOURCÉ].
L'agriculteur ne voit rien, et la perte est déjà inscrite.

Les stades et seuils exacts pour les variétés cultivées en Côte d'Ivoire sont
[À VALIDER].

### Stade 5 — Floraison — le stade le plus critique

| | |
|---|---|
| **Processus** | Pollinisation et fécondation. Fenêtre très courte, irrattrapable. |
| **Ce qui se joue** | Le nombre de grains ou de fruits. **C'est le stade où une saison se gagne ou se perd.** |
| **Donnée nécessaire** | **Séquence sèche** — le compteur de jours consécutifs sans pluie utile. **Température maximale** (avortement floral). Humidité relative. Vent (dessèchement des soies, des stigmates). |
| **Résolution** | **journalière, avec alerte anticipée** |
| **Décision** | irriguer en urgence si possible ; sinon, se préparer à une perte et adapter la suite |

Le chiffre à retenir : sur maïs, **un manque d'eau de seulement 5 à 7 jours
pendant cette fenêtre** perturbe la pollinisation et ampute directement le
potentiel — [SOURCÉ].

**Cinq jours.** Aucune donnée instantanée ne peut détecter cela. Il faut un
compteur qui tourne.

### Stade 6 — Nouaison et avortement des grains

| | |
|---|---|
| **Processus** | Les grains fécondés s'installent — ou avortent. |
| **Ce qui se joue** | Le nombre de grains qui iront jusqu'au bout. |
| **Donnée nécessaire** | **Degrés-jours depuis la floraison**, poursuite du suivi hydrique. |
| **Résolution** | cumul de degrés-jours |
| **Décision** | fin de la période d'irrigation critique |

La démonstration la plus nette de l'utilité du degré-jour : sur maïs, le **stade
limite d'avortement des grains** intervient environ **250 degrés-jours après la
floraison femelle**, soit une quinzaine de jours selon les conditions — [SOURCÉ].

Ce n'est pas « quinze jours ». C'est « 250 degrés-jours », qui valent quinze jours
une année et vingt une autre. Un système qui compte en jours se trompe de date ;
un système qui compte en degrés-jours ne se trompe pas.

### Stade 7 — Remplissage du grain

| | |
|---|---|
| **Processus** | Les assimilats migrent des feuilles vers les grains. |
| **Ce qui se joue** | **Le poids** des grains — deuxième composante du rendement. |
| **Donnée nécessaire** | Bilan hydrique, rayonnement, amplitude thermique jour/nuit, maintien de la surface foliaire verte. |
| **Résolution** | cumul sur la période |
| **Décision** | dernière irrigation utile ; estimation de rendement |

C'est la **deuxième période sensible** : un déficit ici limite le transfert vers
les grains et donne des grains moins denses — [SOURCÉ].

### Stade 8 — Maturation

| | |
|---|---|
| **Processus** | La plante cesse d'accumuler. Le grain perd son eau. |
| **Ce qui se joue** | La date optimale de récolte. |
| **Donnée nécessaire** | Degrés-jours cumulés, **prévision de pluie à 7-10 jours**, humidité relative. |
| **Résolution** | journalière, avec regard avant d'une semaine |
| **Décision** | récolter maintenant ou attendre |

**Ici, la pluie devient un ennemi.** C'est le renversement d'interprétation
annoncé au §1 : la même donnée qui déclenchait le semis menace désormais la
récolte.

### Stade 9 — Récolte

| | |
|---|---|
| **Processus** | Prélèvement. Fenêtre de quelques jours. |
| **Ce qui se joue** | Pertes au champ, qualité sanitaire, **risque de contamination fongique**. |
| **Donnée nécessaire** | Fenêtre sans pluie de 2 à 4 jours, humidité relative, ensoleillement. |
| **Résolution** | **horaire à journalière**, sur 3 à 7 jours |
| **Décision** | organiser la main-d'œuvre, mobiliser le séchage |

Un point sous-estimé : en Afrique subsaharienne, les agriculteurs **retardent
souvent la récolte de plusieurs semaines** pour laisser sécher au champ, ce qui
aggrave la contamination fongique et la production d'aflatoxine — [SOURCÉ].

Un conseil de fenêtre de récolte a donc une valeur sanitaire, pas seulement
logistique.

### Stade 10 — Séchage

| | |
|---|---|
| **Processus** | Le produit descend de ~23 % à ~13 % d'humidité. |
| **Ce qui se joue** | **La sécurité sanitaire de toute la récolte.** |
| **Donnée nécessaire** | **Humidité relative de l'air**, température, rayonnement, absence de pluie sur plusieurs jours consécutifs. |
| **Résolution** | **horaire** |
| **Décision** | étaler / rentrer / prolonger le séchage |

Les repères de la littérature, sur maïs : l'humidité à la récolte dépasse souvent
**23 %** et doit descendre **sous 15 % en 10 jours**, puis entre **11 et 13 % en
20 jours** pour éviter la contamination fongique et l'aflatoxine — [SOURCÉ].

C'est le stade où **l'humidité relative devient la variable maîtresse**, davantage
que la pluie. Or c'est exactement la variable que le système reçoit déjà et
n'exploite pas — [CODE].

### Stade 11 — Stockage

| | |
|---|---|
| **Processus** | Conservation sur plusieurs mois. Équilibre hydrique entre grain et air. |
| **Ce qui se joue** | Pertes de stockage, salubrité, et **la valeur marchande dans le temps**. |
| **Donnée nécessaire** | Humidité relative et température du lieu de stockage, suivi de l'équilibre, **prix de marché**. |
| **Résolution** | journalière à hebdomadaire, sur plusieurs mois |
| **Décision** | traiter, aérer, ou **vendre maintenant plutôt que stocker** |

Repère sourcé : une humidité de grain de **13,5 %** est en équilibre avec une
humidité relative de **70 % à 27 °C** — [SOURCÉ]. Au-delà, le grain reprend de
l'eau et le risque fongique remonte.

Le corpus contient **22 entrées `QUESTION_STOCKAGE`** et **18 entrées
`QUESTION_VENTE`** — [CODE]. Aucune n'a accès à une donnée d'humidité de
stockage ni à un prix.

---

## 3. Ce que ce parcours établit

### 3.1 Le stade phénologique est le pivot, pas la météo

Sur douze stades, **onze** exigent de savoir où en est la plante pour interpréter
la donnée. La météo seule ne dit rien ; météo + stade dit tout.

Et le stade se calcule à partir de deux éléments seulement :

```
date de semis  +  degres-jours cumules  =  stade phenologique
   ^                      ^
   |                      └── calculable si l'on historise la temperature
   └── a demander a l'agriculteur
```

**Ni l'un ni l'autre ne demande une source de données externe.**

### 3.2 La résolution temporelle varie selon le stade

C'est une contrainte technique rarement explicitée.

| Stade | Résolution requise | Horizon |
|---|---|---|
| Avant semis | journalière | **regard avant 20-30 j** |
| Levée | journalière | 10-15 j |
| Végétatif | cumul depuis semis | continu |
| Floraison | journalière + **alerte** | 5-7 j |
| Nouaison | cumul de degrés-jours | continu |
| Maturation | journalière | regard avant 7-10 j |
| Récolte | **horaire** | 3-7 j |
| Séchage | **horaire** | 3-10 j |
| Stockage | hebdomadaire | plusieurs mois |

Le système travaille aujourd'hui en instantané avec un horizon de 24 h. Aucun
stade n'est correctement servi par cette résolution, et **quatre stades exigent
un regard arrière** que rien ne permet aujourd'hui.

### 3.3 Les grandeurs qui reviennent le plus souvent

En comptant les occurrences à travers les douze stades :

| Grandeur | Stades concernés | Disponible aujourd'hui ? |
|---|---:|---|
| **Séquence sèche** (jours consécutifs) | 5 | non — demande un historique |
| **Degrés-jours cumulés** | 4 | non — demande un historique |
| **Humidité relative** | 4 | **reçue, non exploitée** — [CODE] |
| Cumul de pluie glissant | 4 | non — demande un historique |
| Prévision à 7-10 jours | 3 | non — horizon limité à 24 h |
| Humidité du sol | 3 | non |
| Température du sol | 2 | non |
| Rayonnement | 2 | non |
| Prix de marché | 1 | non |

**Trois des quatre grandeurs les plus sollicitées ne demandent aucune source
nouvelle.** Elles demandent de conserver ce qui transite déjà.

---

## 4. Les données non climatiques

Le cycle fait apparaître des besoins qui ne relèvent d'aucun service météo.

**De l'agriculteur** — date de semis, culture, variété et durée de cycle,
surface, texture du sol, accès à l'irrigation, date de récolte effective. Ces
informations ne coûtent qu'une question, et sans elles rien de ce qui précède
n'est calculable.

**D'institutions agronomiques** — fenêtres de semis par couple culture × zone,
sommes de températures par stade et par variété, seuils d'intervention
phytosanitaire, normes d'humidité de conservation. Ce sont les tables soumises à
la règle de validation.

**De sources de marché** — prix et tendance, pour que le stade 11 débouche sur une
décision de vente et non sur un simple conseil de conservation.

**De la télédétection** — indice de végétation et anomalie, humidité de surface.
Ces sources ouvertes permettent d'observer l'état réel du couvert, et de
**corriger** le stade estimé par le calcul.

**De la boucle de retour** — ce qui a été conseillé, ce qui a été fait, le
résultat obtenu. C'est la seule façon de vérifier que les seuils retenus sont les
bons sous conditions ivoiriennes.

---

## 5. Les deux verrous

### Verrou 1 — Le système ne sait pas où en est la plante

Il n'existe aujourd'hui aucune notion de date de semis, donc aucun stade
phénologique. Toute interprétation contextuelle est impossible.

**Levée du verrou** : demander la date de semis lors de l'échange. Coût nul.

### Verrou 2 — Le système ne se souvient de rien

La donnée météo n'est conservée que **15 minutes en mémoire** — [CODE]. Aucune
table, aucun historique.

Conséquence directe : **aucune grandeur cumulée n'est calculable**, quelle que
soit la richesse de la source. Séquence sèche, degrés-jours, cumul décadaire,
durée d'humectation — toutes supposent une série temporelle.

**Levée du verrou** : historiser ce qui est déjà reçu. Cela débloque, sans donnée
nouvelle :

| Grandeur | Stades servis |
|---|---|
| Séquence sèche en cours | 0, 2, 5, 7 |
| Cumul glissant 10 et 30 jours | 0, 1, 3, 7 |
| Degrés-jours depuis une date | 3, 4, 6, 8 |
| Jours consécutifs à humidité élevée | 9, 10, 11 |

---

## 6. Priorisation

| Rang | Besoin | Ce qu'il débloque | Difficulté |
|---|---|---|---|
| **1** | **Date de semis déclarée** | le stade phénologique — donc l'interprétation de toute donnée | très faible |
| **2** | **Historisation de la météo reçue** | séquence sèche, degrés-jours, cumuls | faible — interne |
| **3** | **Exploiter l'humidité déjà reçue** | stades 9, 10, 11 — séchage et stockage | très faible — déjà reçue |
| **4** | **Prévision à 7-10 jours** | stades 0, 8, 9 — semis, récolte, séchage | faible — paramètre de requête |
| **5** | **Sommes de températures par stade** | passage du calendrier au degré-jour | validation agronomique |
| **6** | **Démarrage effectif des pluies** | remplace une constante par une observation | source externe |
| **7** | **Humidité et température du sol** | stades 1, 2 — levée | source externe ou modèle |
| **8** | **Prix de marché** | stade 11 — décision de vente | source externe |

Les rangs **1 à 4 ne dépendent d'aucun tiers**. Les rangs 3 et 4 sont
particulièrement frappants : l'humidité relative est **déjà reçue à chaque
appel**, et l'horizon de prévision est un simple paramètre de requête.

---

## 7. Synthèse

```
CE QUE LE SYSTEME FAIT AUJOURD'HUI

   mesure instantanee  ->  1 condition parmi 6  ->  message

CE QUE LA PLANTE DEMANDE

   date de semis
        + degres-jours cumules      ->  STADE
        + historique meteo          ->  CE QU'ELLE A SUBI
        + previsions 7-10 j         ->  CE QUI VIENT
                                        |
                                        v
                                 message interprete
                                 selon le stade

LE RENVERSEMENT

   « il pleut »  au semis      ->  opportunite
   « il pleut »  a la floraison ->  soulagement
   « il pleut »  au sechage     ->  danger

   Aujourd'hui : une seule lecture, quel que soit le stade.
```

Le premier pas ne demande ni source externe, ni infrastructure : **demander quand
l'agriculteur a semé, et garder ce que l'on reçoit déjà.**

---

## 8. Journal

| Date | Ajout |
|---|---|
| 2026-09-11 | Création — parcours du cycle en 12 stades, résolution temporelle par stade, verrous, priorisation |

> **Règle** : toute valeur agronomique ajoutée à ce document doit porter sa
> source. Une valeur marquée [À VALIDER] ne peut pas être implémentée en l'état.

---

## Sources

**Stades critiques et stress hydrique**

- [ARVALIS — Impacts du stress hydrique sur le maïs](https://www.arvalis.fr/infos-techniques/quels-impacts-du-stress-hydrique-sur-les-mais)
- [ARVALIS — Conséquences du stress hydrique à l'approche de la floraison](https://www.arvalis.fr/infos-techniques/mais-fourrage-evaluer-les-consequences-du-stress-hydrique-lapproche-de-la)
- [Chambre d'agriculture de la Vienne — Irrigation du maïs grain](https://vienne.chambres-agriculture.fr/fileadmin/user_upload/250_chambre_dagriculture_de_la_vienne/Documents/Piloter_son_entreprise/Reglementation/Irrigation/20210604_FT5_Mais.pdf)

> Ces références décrivent le maïs en conditions tempérées. **Les seuils et
> sommes de températures doivent être revalidés pour les variétés et conditions
> ivoiriennes** — marqué [À VALIDER] dans le corps du document.

**Démarrage de la saison des pluies**

- [Frontiers in Climate — Sensibilité des diagnostics de démarrage de saison des pluies, cas de Lamto (Côte d'Ivoire)](https://www.frontiersin.org/journals/climate/articles/10.3389/fclim.2026.1793665/full)

**Besoins en eau des cultures**

- [FAO — Irrigation and Drainage Paper 56, évapotranspiration des cultures](https://www.fao.org/4/x0490e/x0490e00.htm)
- [FAO AQUASTAT — Besoins en eau d'irrigation](https://www.fao.org/aquastat/fr/data-analysis/irrig-water-use/irrig-water-requirement/)

**Post-récolte, séchage et conservation**

- [Journal of Stored Products Research — Séchage et stockage du maïs, réduction de l'aflatoxine](https://www.sciencedirect.com/science/article/pii/S0022474X2500253X)
- [Journal of Stored Products Research — Pratiques post-récolte pour le contrôle de l'aflatoxine](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7001978/)
- [PMC — Séchage solaire ambiant et pertes post-récolte du maïs](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7360773/)

---

## Références internes

| Document | Contenu |
|---|---|
| [CONTRAT_API_OPEN_METEO.md](CONTRAT_API_OPEN_METEO.md) | acquisition de la donnée météo — requête émise, réponse reçue, structure |
| [TRAITEMENT_DONNEES_METEO.md](TRAITEMENT_DONNEES_METEO.md) | traitement de la donnée météo — normalisation, classification, contextualisation |
