# Issue #32 — audit et fiche de validation des traductions bambara/dioula

- **Date de l'audit** : 2026-07-28
- **Branche** : `audit/32-bambara-validation`
- **Base vérifiée** : `0ccde4d2f496d858701f565abba9f74a97d16899` (`APIPy`)
- **Statut** : validation native reçue — corrections et tests implémentés sur la branche

## Conclusion

L'issue #32 n'était pas déjà implémentée au début de l'audit :

- elle est toujours ouverte ;
- sa chronologie GitHub ne contient aucune PR ni aucun commit de résolution ;
- aucun test dédié ne couvre les traductions de remerciement et de salutation ;
- les différents chemins de traduction ne donnent pas les mêmes résultats.

Le retour final du locuteur reçu le 2026-07-28 valide 49 formes de la fiche et
corrige la première :

- `Bonjour` → `i ni sogoma` ;
- les lignes 2 à 50 sont validées telles qu'elles figurent dans la colonne
  « Forme manuelle à évaluer » ;
- `co di` est signalé comme variante possible de `mun ye` à la ligne 27, sans
  invalider la forme proposée ;
- `i ni ce`, `abarika` et `i ni baraji` sont confirmés pour le sens « Merci ».

La forme canonique générée pour un merci générique reste `a ni ce`, qui est la
ligne 8 validée de la fiche. Les autres formes de remerciement sont reconnues
en entrée sans écraser cette sortie canonique.

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

## Confirmations du locuteur reçues

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

Le retour écrit sur la fiche complète ensuite cette première confirmation :
la ligne 1 est corrigée en `i ni sogoma` et toutes les lignes 2 à 50 sont
validées. La note de la ligne 27 indique que `co di` peut aussi être employé.

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

## Comportement des services avant correction

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
| 1 | Bonjour | `i ni sogoma` | `i ni ce` | Corrigé par le locuteur : `i ni ce` signifie ici « Merci » |
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

- les 20 traductions prioritaires ont reçu une décision native ;
- la ligne 1 est corrigée en `i ni sogoma` ;
- les lignes 2 à 20 sont validées ;
- avant correction technique, 8 formes étaient remplacées par une variante
  plus tardive et 4 tombaient vers NLLB à cause de la ponctuation.

T1 est validée.

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
| 1 | Bonjour | `i ni sogoma` | `i ni ce` | Corrigé : `i ni sogoma` |
| 2 | Bonjour (matin) | `i ni sogoma` | `ani sɔgɔma` | Validé |
| 3 | Bonsoir | `i ni wula` | `ani wula` | Validé |
| 4 | Bonne nuit | `i ni su` | `ani su` | Validé |
| 5 | Bonjour à tous | `aw ni ce` | `aw ni ce` | Validé |
| 6 | Bonjour à tous (matin) | `aw ni sogoma` | `aw ni sogoma` | Validé |
| 7 | Merci pour ton travail | `i ni baara` | `i ni baara` | Validé |
| 8 | Merci | `a ni ce` | `a ni ce` | Validé |
| 9 | Comment vas-tu ? | `i ka kɛnɛ wa` | fallback NLLB | Validé |
| 10 | Ça va bien | `here sira` | `here sira` | Validé |
| 11 | Oui | `ɔwɔ` | `ɔwɔ` | Validé |
| 12 | Non | `ayi` | `ayi` | Validé |
| 13 | Comment tu t'appelles ? | `i tɔgɔ ye mun ye` | fallback NLLB | Validé |
| 14 | Bonjour, comment tu t'appelles ? | `ani sɔgɔ ma i tɔgɔ` | fallback NLLB | Validé |
| 15 | Je veux cultiver du riz | `ne bɛ fɛ ka malo sɛnɛ` | `n b'a fe ka malo sene` | Validé |
| 16 | Je veux cultiver du maïs | `ne bɛ fɛ ka kaba sɛnɛ` | `n b'a fe ka kaba sene` | Validé |
| 17 | Je veux cultiver des arachides | `ne bɛ fɛ ka tiga sɛnɛ` | `n b'a fɛ ka tiga sɛnɛ` | Validé |
| 18 | Est-ce qu'il va pleuvoir ? | `sanji bɛna na wa` | fallback NLLB | Validé |
| 19 | Je veux de l'aide | `ne bɛ fɛ ka dɛmɛ sɔrɔ` | `n b'a fɛ ka dɛmɛ sɔrɔ` | Validé |
| 20 | Mon champ | `ne ka foro` | `n ka foro` | Validé |
| 21 | Ma culture | `ne ka sɛnɛfɛn` | `n ka sɛnɛfɛn` | Validé |
| 22 | Il fait soleil | `tile bɛ` | `tile bɛ` | Validé |
| 23 | Il pleut | `sanji bɛ na` | `sanji bɛ na` | Validé |
| 24 | Mon nom est | `ne tɔgɔ ye` | `n tɔgɔ ye` | Validé |
| 25 | Je viens de | `ne bɛ bɔ` | `n bɛ bɔ` | Validé |
| 26 | Je peux | `ne bɛ se ka` | `n bɛ se ka` | Validé |
| 27 | Qu'est-ce que c'est ? | `mun ye` | fallback NLLB | Validé ; variante signalée : `co di` |
| 28 | Comment ? | `cogo di` | fallback NLLB | Validé |
| 29 | S'il te plaît | `n'i ko dɛ` | `n'i ko dɛ` | Validé |
| 30 | Au revoir | `k'an bɛn` | `k'an bɛn` | Validé |
| 31 | Que Dieu te protège | `ala k'i kisi` | `ala k'i kisi` | Validé |
| 32 | Je suis agriculteur | `ne ye sɛnɛkɛla ye` | `n ye sɛnɛkɛla ye` | Validé |
| 33 | Je veux faire de l'agriculture | `ne bɛ fɛ ka sɛnɛ kɛ` | `n b'a fɛ ka sɛnɛ kɛ` | Validé |
| 34 | Il y a une maladie sur ma culture | `bana bɛ ne ka sɛnɛfɛn kan` | `bana bɛ n ka sɛnɛfɛn kan` | Validé |
| 35 | Il faut arroser | `jii ka kan` | `jii ka kan` | Validé |
| 36 | Quand est-ce que je peux cultiver ? | `waati jumɛn na ne bɛ se ka sɛnɛ` | fallback NLLB | Validé |
| 37 | Qu'est-ce qui est bon à cultiver ? | `fɛn jumɛn ka ɲi ka sɛnɛ` | fallback NLLB | Validé |
| 38 | Je veux cultiver du mil | `ne bɛ fɛ ka ɲɔ sɛnɛ` | `n b'a fɛ ka ɲɔ sɛnɛ` | Validé |
| 39 | Je veux cultiver un champ | `ne bɛ fɛ ka foro sɛnɛ` | `n bɛ fɛ ka foro sɛnɛ` | Validé |
| 40 | Je veux arroser | `ne bɛ fɛ ka jii di` | `n b'a fɛ ka jii di` | Validé |
| 41 | Comment cultiver du riz | `malo sɛnɛ cogo` | `malo sɛnɛ cogo` | Validé |
| 42 | Comment cultiver du maïs | `kaba sɛnɛ cogo` | `kaba sɛnɛ cogo` | Validé |
| 43 | Le sol est bon | `dugukolo ka ɲi` | `dugukolo ka ɲi` | Validé |
| 44 | Je veux savoir | `ne bɛ fɛ ka dɔn` | `n b'a fɛ ka dɔn` | Validé |
| 45 | C'est possible | `a bɛ se ka kɛ` | `a bɛ se ka kɛ` | Validé |
| 46 | Ce n'est pas possible | `a tɛ se ka kɛ` | `a tɛ se ka kɛ` | Validé |
| 47 | Je veux cultiver | `ne bɛ fɛ ka sɛnɛ` | `n b'a fe ka sene` | Validé |
| 48 | Tu veux cultiver du riz | `i bɛ fɛ ka malo sɛnɛ` | `i be fe ka malo sene` | Validé |
| 49 | Tu veux cultiver du maïs | `i bɛ fɛ ka kaba sɛnɛ` | `i be fe ka kaba sene` | Validé |
| 50 | Nous voulons cultiver | `an bɛ fɛ ka sɛnɛ` | `an be fe ka sene` | Validé |

État technique avant correction :

- 19 sorties moteur sont identiques à la première forme manuelle ;
- 23 sorties sont écrasées par une variante ASR/NeMo plus tardive ;
- 8 sorties basculent vers NLLB à cause de la ponctuation ;
- 50 décisions natives sont maintenant enregistrées.

T5 est validée.

## Défauts techniques identifiés avant correction

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

Avant correction, `bambara_phrases.json` annonçait `total_phrases: 109`, mais
contenait :

- 156 lignes ;
- 152 clés bambara distinctes ;
- 88 sens français distincts.

Après correction, le fichier contient 175 lignes, 171 clés bambara distinctes
et 88 sens français distincts. `metadata.total_phrases` est synchronisé à
175. Les variantes ASR auparavant reconnues directement par `tts_bambara`
ont été déplacées dans cette source commune afin de préserver leur support.

## Décisions natives appliquées

1. `Bonjour` générique utilise `i ni sogoma`.
2. `Merci` générique produit `a ni ce`, conformément à la ligne 8 validée.
3. `i ni ce`, `abarika` et `i ni baraji` sont reconnus comme « Merci » sans
   devenir la sortie canonique unique.
4. `i ni wula` reste la forme validée pour « Bonsoir ».
5. `i ni su` reste la forme validée pour « Bonne nuit ».
6. Les formes canoniques validées sont produites sans ajouter `Nba`, absent
   de la fiche soumise au locuteur.
7. Les lignes 2 à 50 conservent leur première forme manuelle validée.

## Correction implémentée et vérifiée

- les clés françaises sont normalisées de façon symétrique au chargement et
  à la recherche ;
- les variantes ASR/NeMo restent acceptées en entrée, mais seules les
  premières formes `manuel` peuvent devenir des sorties canoniques ;
- `TranslationService`, `tts_bambara` et `tts_dioula` consomment la même
  source pour les expressions validées placées en tête de phrase ;
- les phrases complètes validées sont prioritaires sur l'extraction d'une
  salutation ;
- `tests/unit/test_validated_bambara_translations.py` couvre les 50 phrases,
  les huit cas de ponctuation, les formes de remerciement et les deux chemins
  TTS ;
- tests ciblés : 134 réussis ;
- suite unitaire complète : 603 réussis ;
- vérification HTTP réelle avec `curl` sur `/api/tts/translate` :
  - `Bonjour` → `i ni sogoma` ;
  - `Merci` → `a ni ce` ;
  - `Comment vas-tu ?` → `i ka kɛnɛ wa`.
