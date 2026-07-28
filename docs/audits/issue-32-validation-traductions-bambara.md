# Issue #32 — audit et fiche de validation des traductions bambara/dioula

- **Date de l'audit** : 2026-07-28
- **Branche** : `audit/32-bambara-validation`
- **Base vérifiée** : `0ccde4d2f496d858701f565abba9f74a97d16899` (`APIPy`)
- **Statut** : audit préparatoire — aucune traduction de production modifiée

## Conclusion

L'issue #32 n'est pas déjà implémentée :

- elle est toujours ouverte ;
- sa chronologie GitHub ne contient aucune PR ni aucun commit de résolution ;
- aucun test dédié ne couvre les traductions de remerciement et de salutation ;
- les différents chemins de traduction ne donnent pas les mêmes résultats.

L'affirmation initiale de l'issue selon laquelle `i ni ce` signifierait
uniquement « bonjour » est contredite par les références du dépôt et par la
confirmation orale reçue. En revanche, cette confirmation ne permet pas
encore de choisir une forme unique pour tous les contextes.

L'ajout global demandé par T3, `merci` → `i ni baaraji`, ne doit donc pas être
appliqué tel quel. Les références écrivent `baraji` et décrivent
`i ni baraji` comme une formule de récompense ou de bénédiction. Son emploi
comme remerciement a été confirmé oralement, mais son registre doit encore
être précisé avant d'en faire le remerciement générique de Wourri.

## Méthode et limite sur le mot « fréquent »

Le projet ne collecte aucune métrique de fréquence des traductions. Les
historiques de conversation sont uniquement conservés en mémoire et aucune
télémétrie ne permet d'établir les vingt formulations réellement les plus
utilisées par les utilisateurs.

Pour rendre T1 reproductible sans consulter de conversations privées :

1. la source utilisée est `dictionnaires/bambara_phrases.json`, décrite comme
   la liste des phrases courantes ;
2. seules les lignes `source: "manuel"` sont retenues comme formes
   canoniques candidates ;
3. les sens français sont dédupliqués en conservant leur ordre dans le
   fichier ;
4. les 20 premiers sens forment l'audit T1 ;
5. les 50 premiers sens forment la fiche de validation T5.

Ces listes mesurent donc la priorité opérationnelle dans le dépôt, pas la
fréquence réelle en production. T1 ne pourra être qualifiée de statistique
que lorsqu'une télémétrie agrégée et respectueuse de la vie privée existera.

## Confirmation orale reçue

Le propriétaire du projet a rapporté une confirmation orale d'un locuteur le
2026-07-28. Après déduplication de la réponse, les trois formes distinctes
confirmées sont :

| Forme | Sens confirmé oralement | Références internes | Statut |
|---|---|---|---|
| `i ni ce` | Merci | Webonary : « merci (sg.) » ; Mandenkan : `i ni ce o !` → « Merci ! » | Confirmé pour le sens « merci » |
| `abarika` | Merci | Webonary : `abarika`, variante de `barika`, interjection « merci » | Confirmé |
| `i ni baraji` | Merci | Webonary : « que Dieu te bénisse » ; Mandenkan : `baraji` = récompense divine | Confirmé comme remerciement, registre à préciser |

La réponse répétait deux fois `i ni ce`. Elle ne permet pas de déduire une
validation de `a ni ce` ou de `aw ni ce`. `a ni ce` est néanmoins attesté
comme « merci » par Webonary.

Cette confirmation valide un sens possible. Elle ne valide pas encore :

- le registre neutre, religieux ou solennel de chaque forme ;
- le singulier, le pluriel et le degré de politesse ;
- l'usage éventuel de `i ni ce` comme salutation ;
- les 47 autres phrases nécessaires à T5.

## Références linguistiques relues

- `data/references_dioula/webonary_bambara_fr_en_de.txt`
  - lignes 33-37 : `abarika` = merci ;
  - lignes 75-76 : `a ni ce` = merci ;
  - lignes 2191-2199 : `baraji` = récompense divine, grâce, bénédiction ;
  - lignes 2254-2258 : `barika` = remercier, bénir ;
  - lignes 5988-5993 : `ce` = salut ou merci selon la formule ;
  - lignes 22285-22317 : `i ni baraji`, `i ni ce`, `i ni sɔgɔma`,
    `i ni suu`, `i ni tile` et `i ni wula` ;
  - lignes 27284-27289 : `k'an si` = bonne nuit à la personne qui va dormir.
- `data/references_dioula/mandenkan_lexique_text.txt`
  - lignes 487-490 : `baraji` = récompense divine ;
  - lignes 7515-7516 : `i ni ce o !` = Merci ;
  - lignes 8699-8700 : `i ni su !` = Bonsoir ;
  - lignes 9986-9987 : `i(a) ni wula !` = bonjour/bonsoir l'après-midi.
- `data/hf_datasets/francophonia_bambara_french.json`
  - lignes 167107-167108 : emploi attesté de `i ni ce` pour « merci » ;
  - lignes 168811-168812 : emploi attesté de `abarika` pour « merci ».

## Comportement effectif des services

Les résultats ci-dessous ont été reproduits en exécutant les fonctions
actuelles, sans charger de modèle NLLB pour les correspondances exactes.

### Français vers bambara/dioula

| Chemin de production | Bonjour | Bonsoir | Bonne nuit | Salut | Merci |
|---|---|---|---|---|---|
| `TranslationService` / `WordTranslator` | `i ni ce` | `ani wula` | `ani su` | fallback NLLB | `a ni ce` |
| `tts_bambara.translate_to_bambara` | `Nba, i ni ce!` | `Nba, i ni su!` | `ani su.` | `Nba, i ni ce!` | `Nba, i ni ce!` |
| `tts_dioula.translate_to_dioula` | `i ni ce` | `i ni wula` | `i ni su` | `i ni ce` | `i ni ce` |

Le routeur `/api/tts` utilise actuellement `tts_bambara` pour
`Language.DIOULA`, alors que le fallback conversationnel DeepSeek utilise
`tts_dioula`. Un utilisateur peut donc recevoir deux traductions différentes
pour le même texte selon le point d'entrée.

### Bambara/dioula vers français

| Entrée | `TranslationService` | `tts_bambara.translate_to_french` | Preuve ou risque |
|---|---|---|---|
| `i ni ce` | Bonjour | Bonjour | Oralement confirmé aussi comme « merci » : contexte perdu |
| `a ni ce` | Merci | Bonjour | Contradiction directe entre deux services |
| `abarika` | Merci | Merci | Cohérent avec la confirmation orale |
| `i ni baraji` | `On et récompenser` | `On et récompenser` | Résultat mot-à-mot incorrect ; sens oral « merci », nuance de bénédiction dans les sources |
| `i ni wula` | Bonsoir | Bonsoir | Attesté pour l'après-midi |
| `i ni su` | Bonne nuit | Bonne nuit | Les références le donnent comme « bonsoir » après le coucher du soleil |

`Nba` est décrit dans les données du projet comme une réponse masculine à une
salutation. Son ajout devant toutes les salutations sortantes de
`tts_bambara` doit être validé par un locuteur avant d'être conservé.

## T1 — audit des 20 traductions prioritaires

La « forme manuelle » est la première forme `source: "manuel"` du fichier.
La « sortie moteur » est la valeur effectivement renvoyée par
`WordTranslator` sur la branche auditée.

| # | Français | Forme manuelle | Sortie moteur actuelle | Constat |
|---:|---|---|---|---|
| 1 | Bonjour | `i ni ce` | `i ni ce` | Techniquement stable ; le contexte bonjour/merci reste à valider |
| 2 | Bonjour (matin) | `i ni sogoma` | `ani sɔgɔma` | La dernière variante écrase la forme canonique ; `i ni sɔgɔma` est attesté |
| 3 | Bonsoir | `i ni wula` | `ani wula` | La dernière variante écrase la forme canonique ; `i ni wula` est attesté l'après-midi |
| 4 | Bonne nuit | `i ni su` | `ani su` | Conflit avec les références : `i ni suu` = bonsoir, `k'an si` = bonne nuit au coucher |
| 5 | Bonjour à tous | `aw ni ce` | `aw ni ce` | Stable, validation native plurielle requise |
| 6 | Bonjour à tous (matin) | `aw ni sogoma` | `aw ni sogoma` | Stable, validation native plurielle requise |
| 7 | Merci pour ton travail | `i ni baara` | `i ni baara` | Stable, validation native du contexte requise |
| 8 | Merci | `a ni ce` | `a ni ce` | Attesté par Webonary, mais non cité dans la confirmation orale reçue |
| 9 | Comment vas-tu ? | `i ka kɛnɛ wa` | fallback NLLB | Échec technique causé par la ponctuation de la clé française |
| 10 | Ça va bien | `here sira` | `here sira` | Stable, validation native requise |
| 11 | Oui | `ɔwɔ` | `ɔwɔ` | Stable |
| 12 | Non | `ayi` | `ayi` | Stable |
| 13 | Comment tu t'appelles ? | `i tɔgɔ ye mun ye` | fallback NLLB | Échec technique causé par la ponctuation |
| 14 | Bonjour, comment tu t'appelles ? | `ani sɔgɔ ma i tɔgɔ` | fallback NLLB | Échec technique causé par la ponctuation |
| 15 | Je veux cultiver du riz | `ne bɛ fɛ ka malo sɛnɛ` | `n b'a fe ka malo sene` | Une variante NeMo sans tons écrase la forme manuelle |
| 16 | Je veux cultiver du maïs | `ne bɛ fɛ ka kaba sɛnɛ` | `n b'a fe ka kaba sene` | Une variante NeMo sans tons écrase la forme manuelle |
| 17 | Je veux cultiver des arachides | `ne bɛ fɛ ka tiga sɛnɛ` | `n b'a fɛ ka tiga sɛnɛ` | Une variante NeMo écrase la forme manuelle |
| 18 | Est-ce qu'il va pleuvoir ? | `sanji bɛna na wa` | fallback NLLB | Échec technique causé par la ponctuation |
| 19 | Je veux de l'aide | `ne bɛ fɛ ka dɛmɛ sɔrɔ` | `n b'a fɛ ka dɛmɛ sɔrɔ` | Une variante NeMo écrase la forme manuelle |
| 20 | Mon champ | `ne ka foro` | `n ka foro` | Une variante ASR abrégée écrase la forme manuelle |

Résultat T1 :

- 8 formes sont identiques à la première forme manuelle ;
- 8 formes sont remplacées par une variante plus tardive ;
- 4 formes tombent vers NLLB à cause de la ponctuation ;
- seules les trois formes de remerciement rapportées plus haut ont reçu une
  confirmation orale dans le cadre de cette issue.

T1 est donc auditée techniquement, mais son critère de validation native
n'est pas encore rempli.

## T5 — fiche de validation de 50 phrases

Instructions au locuteur :

1. lire le français et la forme manuelle ;
2. cocher « Valide » si le sens, la grammaire et le registre conviennent au
   dioula CI/bambara visé par Wourri ;
3. sinon cocher « Corriger » et écrire la forme recommandée dans la colonne
   de décision ;
4. préciser si une expression dépend de l'heure, du singulier/pluriel, du
   sexe du locuteur, du respect ou d'un contexte religieux.

| # | Français | Forme manuelle à évaluer | Sortie moteur actuelle | Décision du locuteur |
|---:|---|---|---|---|
| 1 | Bonjour | `i ni ce` | `i ni ce` | ☐ Valide ☐ Corriger : |
| 2 | Bonjour (matin) | `i ni sogoma` | `ani sɔgɔma` | ☐ Valide ☐ Corriger : |
| 3 | Bonsoir | `i ni wula` | `ani wula` | ☐ Valide ☐ Corriger : |
| 4 | Bonne nuit | `i ni su` | `ani su` | ☐ Valide ☐ Corriger : |
| 5 | Bonjour à tous | `aw ni ce` | `aw ni ce` | ☐ Valide ☐ Corriger : |
| 6 | Bonjour à tous (matin) | `aw ni sogoma` | `aw ni sogoma` | ☐ Valide ☐ Corriger : |
| 7 | Merci pour ton travail | `i ni baara` | `i ni baara` | ☐ Valide ☐ Corriger : |
| 8 | Merci | `a ni ce` | `a ni ce` | ☐ Valide ☐ Corriger : |
| 9 | Comment vas-tu ? | `i ka kɛnɛ wa` | fallback NLLB | ☐ Valide ☐ Corriger : |
| 10 | Ça va bien | `here sira` | `here sira` | ☐ Valide ☐ Corriger : |
| 11 | Oui | `ɔwɔ` | `ɔwɔ` | ☐ Valide ☐ Corriger : |
| 12 | Non | `ayi` | `ayi` | ☐ Valide ☐ Corriger : |
| 13 | Comment tu t'appelles ? | `i tɔgɔ ye mun ye` | fallback NLLB | ☐ Valide ☐ Corriger : |
| 14 | Bonjour, comment tu t'appelles ? | `ani sɔgɔ ma i tɔgɔ` | fallback NLLB | ☐ Valide ☐ Corriger : |
| 15 | Je veux cultiver du riz | `ne bɛ fɛ ka malo sɛnɛ` | `n b'a fe ka malo sene` | ☐ Valide ☐ Corriger : |
| 16 | Je veux cultiver du maïs | `ne bɛ fɛ ka kaba sɛnɛ` | `n b'a fe ka kaba sene` | ☐ Valide ☐ Corriger : |
| 17 | Je veux cultiver des arachides | `ne bɛ fɛ ka tiga sɛnɛ` | `n b'a fɛ ka tiga sɛnɛ` | ☐ Valide ☐ Corriger : |
| 18 | Est-ce qu'il va pleuvoir ? | `sanji bɛna na wa` | fallback NLLB | ☐ Valide ☐ Corriger : |
| 19 | Je veux de l'aide | `ne bɛ fɛ ka dɛmɛ sɔrɔ` | `n b'a fɛ ka dɛmɛ sɔrɔ` | ☐ Valide ☐ Corriger : |
| 20 | Mon champ | `ne ka foro` | `n ka foro` | ☐ Valide ☐ Corriger : |
| 21 | Ma culture | `ne ka sɛnɛfɛn` | `n ka sɛnɛfɛn` | ☐ Valide ☐ Corriger : |
| 22 | Il fait soleil | `tile bɛ` | `tile bɛ` | ☐ Valide ☐ Corriger : |
| 23 | Il pleut | `sanji bɛ na` | `sanji bɛ na` | ☐ Valide ☐ Corriger : |
| 24 | Mon nom est | `ne tɔgɔ ye` | `n tɔgɔ ye` | ☐ Valide ☐ Corriger : |
| 25 | Je viens de | `ne bɛ bɔ` | `n bɛ bɔ` | ☐ Valide ☐ Corriger : |
| 26 | Je peux | `ne bɛ se ka` | `n bɛ se ka` | ☐ Valide ☐ Corriger : |
| 27 | Qu'est-ce que c'est ? | `mun ye` | fallback NLLB | ☐ Valide ☐ Corriger : |
| 28 | Comment ? | `cogo di` | fallback NLLB | ☐ Valide ☐ Corriger : |
| 29 | S'il te plaît | `n'i ko dɛ` | `n'i ko dɛ` | ☐ Valide ☐ Corriger : |
| 30 | Au revoir | `k'an bɛn` | `k'an bɛn` | ☐ Valide ☐ Corriger : |
| 31 | Que Dieu te protège | `ala k'i kisi` | `ala k'i kisi` | ☐ Valide ☐ Corriger : |
| 32 | Je suis agriculteur | `ne ye sɛnɛkɛla ye` | `n ye sɛnɛkɛla ye` | ☐ Valide ☐ Corriger : |
| 33 | Je veux faire de l'agriculture | `ne bɛ fɛ ka sɛnɛ kɛ` | `n b'a fɛ ka sɛnɛ kɛ` | ☐ Valide ☐ Corriger : |
| 34 | Il y a une maladie sur ma culture | `bana bɛ ne ka sɛnɛfɛn kan` | `bana bɛ n ka sɛnɛfɛn kan` | ☐ Valide ☐ Corriger : |
| 35 | Il faut arroser | `jii ka kan` | `jii ka kan` | ☐ Valide ☐ Corriger : |
| 36 | Quand est-ce que je peux cultiver ? | `waati jumɛn na ne bɛ se ka sɛnɛ` | fallback NLLB | ☐ Valide ☐ Corriger : |
| 37 | Qu'est-ce qui est bon à cultiver ? | `fɛn jumɛn ka ɲi ka sɛnɛ` | fallback NLLB | ☐ Valide ☐ Corriger : |
| 38 | Je veux cultiver du mil | `ne bɛ fɛ ka ɲɔ sɛnɛ` | `n b'a fɛ ka ɲɔ sɛnɛ` | ☐ Valide ☐ Corriger : |
| 39 | Je veux cultiver un champ | `ne bɛ fɛ ka foro sɛnɛ` | `n bɛ fɛ ka foro sɛnɛ` | ☐ Valide ☐ Corriger : |
| 40 | Je veux arroser | `ne bɛ fɛ ka jii di` | `n b'a fɛ ka jii di` | ☐ Valide ☐ Corriger : |
| 41 | Comment cultiver du riz | `malo sɛnɛ cogo` | `malo sɛnɛ cogo` | ☐ Valide ☐ Corriger : |
| 42 | Comment cultiver du maïs | `kaba sɛnɛ cogo` | `kaba sɛnɛ cogo` | ☐ Valide ☐ Corriger : |
| 43 | Le sol est bon | `dugukolo ka ɲi` | `dugukolo ka ɲi` | ☐ Valide ☐ Corriger : |
| 44 | Je veux savoir | `ne bɛ fɛ ka dɔn` | `n b'a fɛ ka dɔn` | ☐ Valide ☐ Corriger : |
| 45 | C'est possible | `a bɛ se ka kɛ` | `a bɛ se ka kɛ` | ☐ Valide ☐ Corriger : |
| 46 | Ce n'est pas possible | `a tɛ se ka kɛ` | `a tɛ se ka kɛ` | ☐ Valide ☐ Corriger : |
| 47 | Je veux cultiver | `ne bɛ fɛ ka sɛnɛ` | `n b'a fe ka sene` | ☐ Valide ☐ Corriger : |
| 48 | Tu veux cultiver du riz | `i bɛ fɛ ka malo sɛnɛ` | `i be fe ka malo sene` | ☐ Valide ☐ Corriger : |
| 49 | Tu veux cultiver du maïs | `i bɛ fɛ ka kaba sɛnɛ` | `i be fe ka kaba sene` | ☐ Valide ☐ Corriger : |
| 50 | Nous voulons cultiver | `an bɛ fɛ ka sɛnɛ` | `an be fe ka sene` | ☐ Valide ☐ Corriger : |

État technique de cette fiche :

- 19 sorties moteur sont identiques à la première forme manuelle ;
- 23 sorties sont écrasées par une variante ASR/NeMo plus tardive ;
- 8 sorties basculent vers NLLB à cause de la ponctuation ;
- 50 décisions natives restent nécessaires avant de marquer T5 comme
  terminée.

## Défauts techniques identifiés

### D1 — les phrases françaises ponctuées ne correspondent jamais

Le chargeur indexe la clé française avec sa ponctuation :

```python
self._phrases_fr_bam[fr.lower()] = entry.get("bam", "")
```

Le traducteur retire ensuite la ponctuation finale avant la recherche :

```python
phrase_key = text_lower.rstrip('.!?;:,')
```

Une entrée stockée comme `comment vas-tu ?` ne peut donc pas correspondre à
la clé recherchée `comment vas-tu`. Huit phrases de la fiche de 50 tombent
vers NLLB pour cette seule raison.

### D2 — les variantes d'entrée écrasent les formes de sortie

`_phrases_fr_bam` ne conserve qu'une valeur par texte français. Chaque ligne
ultérieure remplace la précédente. Les variantes `asr-variante` et
`nemo-variante`, conçues pour reconnaître une entrée vocale, deviennent donc
des sorties TTS.

Exemple :

```text
forme manuelle : ne bɛ fɛ ka malo sɛnɛ
sortie actuelle : n b'a fe ka malo sene
```

Les variantes de reconnaissance et les formes canoniques de génération
doivent être séparées.

### D3 — le contexte salutation/remerciement est écrasé

`i ni ce` et `a ni ce` sont forcés vers « Bonjour » par
`tts_bambara._BAM_GREETING_TO_FR`, alors que le dictionnaire et la
confirmation reçue attestent un sens de remerciement. Le préfixe seul ne
suffit pas à décider du sens.

### D4 — bonsoir et bonne nuit sont confondus

Les services utilisent `i ni su` ou `ani su` pour « bonne nuit ». Les
références relues donnent :

- `i ni wula` : bonsoir l'après-midi ;
- `i ni suu` : bonsoir après le coucher du soleil ;
- `k'an si` : bonne nuit à la personne qui va dormir.

Une validation native du contexte ivoirien doit trancher avant correction.

### D5 — métadonnées et couverture de tests

`bambara_phrases.json` annonce `total_phrases: 109`, mais contient :

- 156 lignes ;
- 152 clés bambara distinctes ;
- 88 sens français distincts.

Il n'existe aucun test de régression dédié à `TranslationService`,
`WordTranslator`, aux salutations TTS ou aux ambiguïtés ci-dessus.

## Décisions natives encore nécessaires

Avant toute correction de production, demander explicitement :

1. quelle forme employer pour un « merci » générique et neutre ;
2. si `i ni baraji` convient hors contexte religieux ou solennel ;
3. comment distinguer `i ni ce` salutation de `i ni ce` remerciement ;
4. quelle forme employer pour bonsoir l'après-midi et après le coucher du
   soleil ;
5. quelle forme employer au moment de souhaiter bonne nuit à une personne qui
   va dormir ;
6. si `Nba` doit être prononcé par Wourri au début d'une salutation ou
   uniquement comme réponse ;
7. les corrections éventuelles des 50 lignes de la fiche T5.

## Plan de correction après validation

Ce plan n'est pas autorisé tant que les décisions ci-dessus ne sont pas
reçues :

1. normaliser de façon symétrique les clés de phrases françaises ;
2. séparer les variantes acceptées en entrée de la forme canonique générée ;
3. centraliser les traductions de salutations et remerciements utilisées par
   les deux services TTS ;
4. ajouter les expressions exactes validées dans les deux directions ;
5. corriger uniquement les lignes rejetées par le locuteur ;
6. synchroniser `metadata.total_phrases` ;
7. ajouter des tests unitaires de régression pour les 20 traductions
   prioritaires et toutes les corrections natives ;
8. exécuter la suite de tests avant PR.
