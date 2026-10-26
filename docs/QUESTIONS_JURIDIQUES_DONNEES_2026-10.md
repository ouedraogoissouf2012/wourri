# Questions à un juriste — vendre les données de langue de WOURI

- **Date** : 2026-10-26
- **Demandeur** : African Digit Consulting (ADC) — Ouedraogo Issouf
- **Objet** : ADC envisage de **fournir ses données de langue (dioula, baoulé) à des tiers**.
  Ce document pose les questions à trancher **avant** tout engagement commercial.
- **Portée** : ce document **ne contient aucun avis juridique**. Il décrit des faits vérifiés
  dans le projet et formule les questions correspondantes.

---

## 1. De quoi parle-t-on exactement

### 1.1 Ce que le projet a produit lui-même

| Donnée | Volume mesuré | Qui l'a produite |
|---|---|---|
| Dictée baoulé | **433 phrases, 1,3 h d'audio** | Esse, locuteur natif, via l'atelier du projet |
| Paires question → réponse baoulé | **123 paires**, chacune avec l'enregistrement de la réponse | Esse |
| Corpus de conseils dioula | **197 entrées** texte, validées | locuteurs natifs dioula |
| Décisions de validation | ex. **39 mots écartés** car la traduction ne correspond pas au concept | jugement d'Esse, consigné et daté |

### 1.2 Ce que le projet a seulement *consulté* (non redistribuable en l'état)

| Source | Licence / condition relevée | Conséquence pressentie |
|---|---|---|
| Common Voice 27.0 baoulé (Mozilla) | contenu **CC0**, mais conditions d'usage interdisant de **« réhéberger ou repartager le dataset »** | ne peut pas être revendu ni réexposé |
| Wiktionnaire français (gloses baoulé) | **CC BY-SA 4.0** (copyleft) | **alimente aujourd'hui l'atelier** de validation |
| MADLAD, FineWeb-2 | compilations **ODC-BY** (majoritairement jw.org) | attribution, contenu tiers |
| Divers jeux publics (Glosbe, dérivés) | conditions interdisant l'extraction ; une licence « MIT » apposée sur du contenu tiers | écartés par le projet |

### 1.3 Les modèles (si la vente devait aussi porter sur eux)

Les modèles de voix et de traduction utilisés en production (**MMS**, **NLLB**) sont signalés
dans la documentation du projet comme étant sous licence **CC BY-NC — non commerciale**.

---

## 2. Questions — propriété des données

**Contexte.** Les enregistrements ont été produits par **Esse** (locuteur baoulé) et par un
**traducteur**, dans le cadre du projet. À ce jour, **aucun document de cession de droits n'a
été retrouvé** dans les dossiers du projet.

> **Q1.** En l'absence de contrat écrit, **à qui appartiennent** les enregistrements et les
> traductions produits par un intervenant rémunéré en Côte d'Ivoire ? ADC peut-elle les céder
> ou les concéder à un tiers ?

> **Q2.** Quel document faut-il signer, et **peut-il couvrir rétroactivement** ce qui a déjà
> été produit depuis août 2026 ?

> **Q3.** La **voix** d'une personne étant reconnaissable, l'intervenant conserve-t-il un droit
> propre (droit à l'image sonore) distinct du droit d'auteur, qui survivrait à une cession ?

> **Q4.** Les **décisions de validation** (le jugement « ce mot ne veut pas dire cela ») sont-elles
> protégeables comme travail original d'ADC, ou s'agit-il de faits non appropriables ?

---

## 3. Questions — consentement et données personnelles

**Contexte.** Une voix enregistrée est une donnée personnelle : elle identifie la personne.
Le régulateur compétent en Côte d'Ivoire est l'**ARTCI**.

Le projet protège déjà très sérieusement les **agriculteurs** : leurs numéros sont transformés
en empreintes **irréversibles** et le système **refuse techniquement** d'enregistrer une donnée
personnelle dans l'atelier. En revanche, **aucun document de consentement n'a été trouvé pour
les locuteurs** qui prêtent leur voix.

> **Q5.** Vendre ou concéder des **enregistrements vocaux** à un tiers constitue-t-il un
> traitement nécessitant un consentement **spécifique à la redistribution** ? Un accord à
> participer au projet suffit-il, ou faut-il une mention explicite de cession à des tiers ?

> **Q6.** Quelles **mentions obligatoires** doit comporter ce consentement : finalités,
> destinataires, durée, droit de retrait, transfert hors de Côte d'Ivoire ?

> **Q7.** Si un locuteur **retire son consentement après la vente**, quelles sont les
> obligations d'ADC et celles de l'acheteur ? Le retrait est-il opposable à l'acheteur ?

> **Q8.** Quelles **formalités ARTCI** s'appliquent : déclaration, autorisation préalable,
> registre des traitements ? La cession à un acheteur **étranger** change-t-elle le régime ?

> **Q9.** Les locuteurs doivent-ils être **rémunérés** au titre de l'exploitation commerciale,
> au-delà du paiement de la prestation d'enregistrement ?

---

## 4. Questions — licences entrantes et contamination

**Contexte.** Le fichier `bci_mots_wiktionnaire_2026-10-22.json` alimente aujourd'hui l'atelier
de validation. Le Wiktionnaire est sous **CC BY-SA 4.0**, une licence **copyleft** (« partage
dans les mêmes conditions »).

> **Q10.** Un lexique construit **en s'appuyant sur** des gloses CC BY-SA est-il une œuvre
> dérivée soumise au partage à l'identique — ce qui interdirait une concession exclusive ?
> La distinction entre *consulter une source pour vérifier un sens* et *incorporer son contenu*
> est-elle juridiquement opérante ?

> **Q11.** Un **fait linguistique** (« ce mot baoulé signifie X ») est-il protégeable ? Si non,
> la reprise d'un sens vérifié dans une source copyleft contamine-t-elle le résultat ?

> **Q12.** Common Voice interdit de « réhéberger ou repartager » le jeu de données. Un **modèle
> entraîné** dessus, ou des **mesures** calculées dessus, tombent-ils sous cette interdiction ?

> **Q13.** Si ADC vend aussi des **modèles** entraînés à partir de poids **CC BY-NC**
> (MMS, NLLB), la restriction non commerciale se transmet-elle au modèle dérivé ?

---

## 5. Questions — ce qui peut être vendu, et comment

> **Q14.** Quelle **licence de sortie** recommandez-vous selon l'objectif : vente exclusive,
> concession non exclusive, ou publication ouverte avec attribution ?

> **Q15.** Faut-il **séparer juridiquement** les artefacts « création propre d'ADC » de ceux
> qui dérivent de sources tierces ? Cette séparation doit-elle être documentée **par fichier** ?

> **Q16.** Quelles **garanties** ADC devra-t-elle donner à un acheteur (origine licite,
> consentements obtenus, absence de contrefaçon), et quelle **responsabilité** en découle en
> cas de réclamation d'un locuteur ou d'un tiers ?

> **Q17.** Le **registre des sources** tenu par le projet — qui documente l'origine, la licence
> et la décision pour chaque source — constitue-t-il un élément de preuve utile en cas de
> litige ? Comment le renforcer ?

---

## 6. Ce qu'ADC attend de cette consultation

1. **Une réponse ferme sur Q1 et Q5** : ADC a-t-elle le droit de céder ces données, oui ou non ?
   Tant que ce point n'est pas tranché, **aucun engagement commercial ne sera pris**.
2. **Deux modèles de documents** : cession de droits (intervenants) et consentement
   (locuteurs), utilisables en l'état et couvrant la redistribution.
3. **Une règle de tri simple** permettant de classer chaque fichier en « cessible » ou
   « contraint », applicable par une équipe technique sans juriste.

---

## Annexe — pièces disponibles sur demande

- Le **registre des sources** baoulé : origine, volume mesuré, licence et décision pour chaque
  source examinée, y compris celles écartées et les motifs du rejet.
- L'inventaire des données produites par le projet, avec volumes et dates.
- Les décisions d'architecture encadrant la validation linguistique et la protection des
  données personnelles des agriculteurs.
