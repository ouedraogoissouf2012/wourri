# Grammaire Dioula/Bambara — Règles de construction des phrases

> **Objectif** : Ce document contient TOUTES les règles de grammaire nécessaires pour
> corriger les 163 entrées du `corpus_ivr.json` de Wourri. Les phrases actuelles sont
> mal construites (ordre des mots incorrect, mots inventés, verbes manquants) et les
> locuteurs natifs ne comprennent pas les messages audio.
>
> **Sources vérifiées** :
> - Wikibooks Bambara/Verbs (https://en.wikibooks.org/wiki/Bambara/Verbs)
> - Coastsystems Introductory Bambara Course (https://coastsystems.net/en/docs/bambara-manual/)
> - TPE Bambara — Grammaire et écriture (https://tpebambara.wordpress.com/grammaire-et-ecriture/)
> - Wikipedia Bambara language (https://en.wikipedia.org/wiki/Bambara_language)
> - An Ka Taa Grammar Notes (https://www.ankataa.com/grammar-notes/category/Bambara)
> - Réseau Alpha — LE BAMBARA (PDF CNRS)
>
> **Date de recherche** : 2026-04-11

---

## TABLE DES MATIÈRES

1. [Règle fondamentale : SOV](#1-règle-fondamentale--sov)
2. [Marqueurs de temps (auxiliaires)](#2-marqueurs-de-temps-auxiliaires)
3. [Impératif (conseils agricoles)](#3-impératif-conseils-agricoles---crucial-pour-wourri)
4. [Postpositions](#4-postpositions)
5. [Possessifs](#5-possessifs)
6. [Questions](#6-questions)
7. [Conditionnel (si... alors)](#7-conditionnel-si-alors)
8. [Adjectifs](#8-adjectifs-avec-ka--man)
9. [Pluriel](#9-pluriel)
10. [Pronoms](#10-pronoms)
11. [Nombres](#11-nombres)
12. [Vocabulaire agricole attesté](#12-vocabulaire-agricole-attesté)
13. [Erreurs types du corpus actuel](#13-erreurs-types-du-corpus-actuel)
14. [Exemple de correction complète](#14-exemple-de-correction-complète)
15. [Checklist de validation](#15-checklist-de-validation-par-phrase)

---

## 1. Règle fondamentale : SOV

En bambara/dioula, l'ordre des mots est **Sujet → Auxiliaire → Objet → Verbe**.
Le verbe est TOUJOURS en fin de proposition.

```
Français (SVO) : Je    mange   du riz
Bambara  (SOV) : N  bɛ  malo    dun
                 S  AUX  O       V
```

### Règles de placement :

| Élément | Position | Exemple |
|---------|----------|---------|
| Sujet | 1ère position | `N` (je), `Aw` (vous), `Malo` (le riz) |
| Auxiliaire de temps | Après le sujet | `bɛ`, `ye`, `ma`, `bɛna` |
| Objet direct | Avant le verbe | `malo` (riz), `foro` (champ) |
| Verbe | DERNIER mot de la proposition | `dun` (manger), `sɛnɛ` (cultiver) |
| Complément de lieu | Après le verbe, avec postposition | `foro la` (au champ) |
| Complément de temps | EN TÊTE de phrase ou après le verbe | `Sanji tuma na, ...` (pendant la pluie) |

### Exemples corrects :

```
N bɛ malo dun.                    → Je mange du riz.
N ye malo san.                    → J'ai acheté du riz.
Aw ye malo sɛnɛ.                 → Vous avez planté du riz. / Plantez du riz.
Sanji tuma na, aw ye malo sɛnɛ.  → Pendant la saison des pluies, plantez du riz.
```

### Erreur fréquente dans le corpus :

```
FAUX  : Aw ye malo sɛnɛ mɛ kalo la sanji tuma na.
         (trop de compléments collés après le verbe, confus)

JUSTE : Sanji tuma na, aw ye malo sɛnɛ mɛ kalo la.
         (complément de temps en tête, verbe en position correcte)
        OU MIEUX (phrases courtes) :
        Mɛ kalo la, aw ye malo sɛnɛ. Sanji bɛ na o tuma na.
```

---

## 2. Marqueurs de temps (auxiliaires)

L'auxiliaire se place **après le sujet, avant l'objet**. C'est le cœur de la conjugaison bambara.

### Tableau complet :

| Temps | Affirmatif | Négatif | Structure |
|-------|-----------|---------|-----------|
| **Présent/Habituel** | **bɛ** | **tɛ** | S + bɛ/tɛ + O + V |
| **Passé (transitif)** | **ye** | **ma** | S + ye/ma + O + V |
| **Passé (intransitif)** | V + **-ra/-la/-na** | **ma** + V | S + V-ra / S + ma + V |
| **Futur** | **bɛna** | **tɛna** | S + bɛna/tɛna + O + V |
| **Imparfait** | **tun bɛ** | **tun tɛ** | S + tun bɛ/tɛ + O + V |
| **Habituel passé** | bɛ **deli ka** | — | S + bɛ deli ka + V |

### Exemples avec chaque temps :

```
PRÉSENT :
  N bɛ Bamanankan kalan.          → J'apprends le bambara.
  N tɛ malo dun.                  → Je ne mange pas de riz.

PASSÉ TRANSITIF (avec objet) :
  N ye safinɛ san.                → J'ai acheté du savon.
  N ma malo san.                  → Je n'ai pas acheté de riz.
  
PASSÉ INTRANSITIF (sans objet direct) :
  N taara.                        → Je suis allé. (taa + -ra)
  N bora Ameriki.                 → Je suis venu d'Amérique. (bɔ + -ra)
  N ma taa.                       → Je ne suis pas allé.

FUTUR :
  N bɛna taa Bamako.              → J'irai à Bamako.
  N tɛna taa.                     → Je n'irai pas.

IMPARFAIT :
  A tun bɛ deli ka na.            → Il avait l'habitude de venir.
```

### Suffixes du passé intransitif :

| Après... | Suffixe | Exemple |
|----------|---------|---------|
| Voyelle | **-ra** | taa → taa**ra** (est allé) |
| Nasale (n, m, ŋ) | **-na** | don → don**na** (est entré) |
| Consonne | **-la** | bɔ → bɔ**la** (est sorti) |

### Participe passé (-len) :

Ajouté au verbe pour indiquer l'état résultant :

```
yiri tigelen   → un arbre coupé
malo jalen     → du riz séché
foro labɛnnen  → un champ préparé
```

---

## 3. Impératif (conseils agricoles) — CRUCIAL POUR WOURRI

La majorité des phrases du corpus sont des **conseils/ordres** aux agriculteurs.
L'impératif est la forme la plus importante à maîtriser.

### Formes de l'impératif :

| Forme | Structure | Exemple | Traduction |
|-------|-----------|---------|------------|
| **Tu (singulier)** | O + V (verbe seul) | **Malo sɛnɛ!** | Plante du riz ! |
| **Tu + lieu** | O + V + postposition | **Malo sɛnɛ foro la!** | Plante du riz au champ ! |
| **Vous (pluriel)** | **Aw ye** + O + V | **Aw ye malo sɛnɛ!** | Plantez du riz ! |
| **Négatif (tu)** | **Kana** + O + V | **Kana malo sɛnɛ!** | Ne plante pas de riz ! |
| **Négatif (vous)** | **Aw kana** + O + V | **Aw kana malo sɛnɛ!** | Ne plantez pas de riz ! |
| **Nous (inclusif)** | **An ka** + O + V | **An ka malo sɛnɛ!** | Plantons du riz ! |

### Impératifs agricoles utiles :

```
Aw ye foro labɛn!                → Préparez le champ !
Aw ye dugukolo sɛnɛ!            → Labourez la terre !
Aw ye ji don foro la!            → Arrosez le champ !
Aw ye nɔgɔ don dugukolo la!     → Mettez de l'engrais dans la terre !
Aw ye malo tigɛ!                 → Récoltez le riz !
Aw ye a jǎ tile la!             → Faites-le sécher au soleil !
Aw kana a sɛnɛ tilema na!       → Ne le plantez pas en saison sèche !
```

### RÈGLE CRITIQUE pour le corpus Wourri :

Dans le corpus, les conseils utilisent `Aw ye` (vous-impératif). La structure DOIT être :

```
Aw ye + [OBJET] + [VERBE]  (+complément optionnel)

CORRECT : Aw ye malo sɛnɛ foro la.     (Plantez du riz au champ)
FAUX    : Aw ye sɛnɛ malo foro la.     (verbe avant objet = INTERDIT)
FAUX    : Aw ye sɛnɛ santimɛtiri ...   (verbe sans objet + complément flottant)
```

---

## 4. Postpositions

Le bambara utilise des **postpositions** (après le nom), PAS des prépositions (avant le nom comme en français).

| Postposition | Sens | Exemple | Traduction |
|-------------|------|---------|------------|
| **la** / **na** | à, dans, sur (lieu) | foro **la** | au champ |
| **kɔnɔ** | à l'intérieur de | so **kɔnɔ** | dans la maison |
| **kan** | sur, dessus | dugukolo **kan** | sur la terre |
| **fɛ** | avec, près de, chez | ji **fɛ** | avec de l'eau / près de l'eau |
| **kɔfɛ** | après, derrière | sɛnɛ **kɔfɛ** | après la plantation |
| **ɲɛfɛ** | devant, avant | sanji **ɲɛfɛ** | avant la pluie |
| **bolo** | par (agent), main de | a **bolo** | par lui / de sa main |
| **kama** | pour, à cause de | sɛnɛ **kama** | pour cultiver |
| **kɔ** | après (temporel) | kalo saba **kɔ** | après 3 mois |

### Règle `la` vs `na` :

- **la** = forme par défaut
- **na** = après un mot terminant par une nasale (n, m, ŋ)
- Exception : `so` (maison) → jamais de `la` : "N bɛ taa so" (je vais à la maison)

### Exemples dans le contexte agricole :

```
Aw ye nɔgɔ don dugukolo la.     → Mettez l'engrais dans la terre.
Malo bɛ foro kɔnɔ.              → Le riz est dans le champ.
Aw ye a da santimɛtiri mugan kan. → Plantez-le à 20 centimètres (dessus).
Sanji kɔfɛ, aw ye malo tigɛ.    → Après la pluie, récoltez le riz.
Kulun bɛ malo fɛ.               → Les insectes sont près du riz.
```

---

## 5. Possessifs

### Adjectif possessif : `ka`

| Français | Bambara | Exemple |
|----------|---------|---------|
| mon/ma | **n ka** | n ka foro → mon champ |
| ton/ta | **i ka** | i ka malo → ton riz |
| son/sa | **a ka** | a ka so → sa maison |
| notre | **an ka** | an ka dugukolo → notre terre |
| votre | **aw ka** | aw ka sɛnɛ → votre culture |
| leur | **u ka** | u ka foro → leur champ |

### Exception : famille et corps (PAS de `ka`)

```
n fa       → mon père (pas "n ka fa")
n ba       → ma mère
n bolo     → ma main
n ɲɛ       → mes yeux
```

### Pronom possessif : `ta`

```
N ta don.           → C'est le mien.
A ta don.           → C'est le sien.
Aw ta don.          → C'est le vôtre.
```

### Avoir : construction avec `fɛ`

```
Biki bɛ n fɛ.       → J'ai un stylo. (lit: stylo est près-de moi)
Den tɛ n fɛ.        → Je n'ai pas d'enfant.
Foro bɛ aw fɛ.      → Vous avez un champ.
Nɔgɔ tɛ n fɛ.      → Je n'ai pas d'engrais.
```

---

## 6. Questions

### Question oui/non : particule `wa` en fin de phrase

```
I bɛ taa foro la wa?             → Tu vas au champ ?
Sanji bɛna na wa?                → La pluie va venir ?
Malo ka ɲi wa?                   → Le riz est bon ?
```

### Mots interrogatifs :

| Mot | Sens | Exemple | Traduction |
|-----|------|---------|------------|
| **mun** | quoi | I bɛ mun sɛnɛ? | Tu plantes quoi ? |
| **min** | où | I bɛ taa min? | Tu vas où ? |
| **munna** | pourquoi | Munna malo tɛ ɲi? | Pourquoi le riz n'est pas bon ? |
| **jon** | qui | Jon ye sɛnɛ kɛ? | Qui a cultivé ? |
| **tuma jumɛn** | quand | Tuma jumɛn na aw bɛ sɛnɛ? | Quand plantez-vous ? |
| **caman jumɛn** | combien | Caman jumɛn? | Combien ? |

---

## 7. Conditionnel (si... alors)

### Futur conditionnel : `ni` ... + principale

```
Ni sanji na, aw ye malo sɛnɛ.
→ Si la pluie vient, plantez du riz.

Ni i ye nɔgɔ don, malo bɛna ɲi.
→ Si tu mets de l'engrais, le riz sera bon.
```

### Hypothétique : `mana`

```
I mana foro labɛn, sɛnɛ bɛna ɲi.
→ Si tu prépares le champ, la culture sera bonne.

Fanta mana wuli, a bɛ ji bɔ kɔlɔn na.
→ Si Fanta se lève, elle tirera l'eau du puits.
```

### Contrefactuel (irréel passé) : `tun` + passé

```
Ni n tun ye wari sɔrɔ, n tun bɛna malo san.
→ Si j'avais eu de l'argent, j'aurais acheté du riz.
```

---

## 8. Adjectifs (avec `ka` / `man`)

### Affirmatif : nom + `ka` + adjectif

```
Dugukolo ka ɲi.      → La terre est bonne.
Malo ka ca.           → Le riz est abondant.
Foro ka bon.          → Le champ est grand.
Ji ka farin.          → L'eau est fraîche.
```

### Négatif : nom + `man` + adjectif

```
Dugukolo man ɲi.      → La terre n'est pas bonne.
Malo man ca.           → Le riz n'est pas abondant.
```

### Comparaison :

```
Malo ka ɲi ni kaba ye.    → Le riz est meilleur que le maïs.
```

### Couleurs (utiles pour diagnostic agricole) :

| Couleur | Bambara |
|---------|---------|
| blanc | jɛman |
| noir | finman |
| rouge | bilenman |
| vert | ɲugujiman |
| jaune | nɛrɛmugu |

---

## 9. Pluriel

Ajout de **-w** à la fin du mot (prononcé [u]) :

```
foro   → forow      (champs)
malo   → malow      (les riz)
mɔgɔ   → mɔgɔw      (les gens)
yiri   → yiriw      (les arbres)
kulun  → kulunw     (les insectes)
```

Pour les mots terminant en **-u** : ajouter **-w** ou doubler **-uw** :

```
dugu   → duguw      (les villages)
kulu   → kuluw      (les montagnes/tas)
```

> **Note dioula CI** : pour « marché », employer **`lɔgɔ`** (`lɔgɔw` au pluriel),
> PAS `sugu` (forme bambara Mali, bannie dans ce projet — cf. §différences BAM↔DYU).

---

## 10. Pronoms

| Singulier | | Pluriel | |
|-----------|---|---------|---|
| **ne / n** | je/moi | **an** | nous |
| **i** | tu/toi | **aw** | vous |
| **a** | il/elle/lui | **u / olu** | ils/elles/eux |

### Pronoms réfléchis :

```
N bɛ n ko.       → Je me lave. (lit: je lave moi)
I bɛ i ko.       → Tu te laves.
```

---

## 11. Nombres

| Nombre | Bambara | | Nombre | Bambara |
|--------|---------|--|--------|---------|
| 1 | kelen | | 6 | wɔɔrɔ |
| 2 | fila | | 7 | wolonfila |
| 3 | saba | | 8 | seginni |
| 4 | naani | | 9 | konɔnba |
| 5 | duuru | | 10 | tan |

### Dizaines et au-delà :

```
20 = mugan          100 = kɛmɛ
30 = bi saba        1000 = waa
80 = bi seginni (ou bi wɔɔrɔ)
```

### Ordinal :

```
fɔlɔ = premier      filanan = deuxième
sabanan = troisième  laban = dernier
```

---

## 12. Vocabulaire agricole attesté

### Cultures (validé multi-sources, voir MEMORY.md du projet) :

| Français | Bambara/Dioula | Source |
|----------|----------------|--------|
| riz (grain) | malo | An Ka Taa, Bayelemabaga |
| riz (cuit) | kini | An Ka Taa |
| maïs | kaba | An Ka Taa, Common Voice |
| arachide | tiga | An Ka Taa |
| manioc | bananku | An Ka Taa (corrigé v1.1) |
| igname | ku | An Ka Taa (corrigé v1.1) |
| mil | nyɔ | An Ka Taa |
| sorgho | keninge | An Ka Taa |
| coton | kɔrɔni | An Ka Taa |
| tomate | tamati | CI variante |
| cacao | kakawo | Webonary Dioula BF |
| haricot/niébé | soso | CI |
| patate douce | woso | An Ka Taa + Bamadaba |
| sésame | bɛnɛ | An Ka Taa |
| café | kafe | loanword |
| ananas | ananas | loanword |
| banane | bàrànda (CI) / namasa (Mali) | |
| gombo | gan | An Ka Taa |
| oignon | jaba | An Ka Taa |
| mangue | mangoro | An Ka Taa |

### Verbes agricoles :

| Français | Bambara | Exemple |
|----------|---------|---------|
| cultiver/planter | sɛnɛ | Aw ye malo sɛnɛ |
| récolter | tigɛ | Aw ye malo tigɛ |
| regarder/surveiller | filɛ | Aw ye foro filɛ |
| arroser | ji don | Aw ye ji don foro la |
| labourer | dugukolo sɛnɛ | Aw ye dugukolo sɛnɛ |
| préparer | labɛn | Aw ye foro labɛn |
| sécher | jǎ | Aw ye malo jǎ |
| stocker | mara / don bɔn la | Aw ye malo don bɔn la |
| vendre | feere | Aw ye malo feere |
| acheter | san | N ye nɔgɔ san |
| manger | dun | N bɛ malo dun |
| boire | min | Aw ye ji min |
| couper | tigɛ | Aw ye yiri tigɛ |
| mélanger | farala ... kan | Aw ye nɔgɔ fara dugukolo kan |

### Noms agricoles :

| Français | Bambara |
|----------|---------|
| champ | foro |
| terre/sol | dugukolo |
| eau | ji |
| pluie | sanji |
| soleil | tile |
| saison des pluies | sanji tuma / samiya |
| saison sèche | tilema |
| engrais | nɔgɔ (validé v1.4 — PAS saraka) |
| graine | kisɛ |
| feuille | fura |
| racine | biri |
| fruit | den / denw |
| arbre | yiri |
| insecte | kulun |
| maladie | bana |
| grenier | bɔn |
| marché | lɔgɔ |
| argent | wari |
| prix | sɔngɔ |
| semaine | lɔgɔkun |
| mois | kalo |
| jour | tile / don |
| agriculteur | sɛnnɛkɛla |
| travail agricole | sɛnɛ baara |

### Saisons et mois :

| Français | Bambara |
|----------|---------|
| saison des pluies | samiya / sanji tuma |
| saison sèche/chaude | tilema |
| saison froide | fonɛnɛ |
| janvier | Zanviye kalo |
| février | Fevuruye kalo |
| mars | Marisi kalo |
| avril | Avirili kalo |
| mai | Mɛ kalo |
| juin | Zuwɛn kalo |
| juillet | Zuluye kalo |
| août | Uti kalo |
| septembre | Sɛtanburu kalo |
| octobre | Ɔtɔburu kalo |
| novembre | Nowanburu kalo |
| décembre | Desanburu kalo |

### Format TTS validé pour les mois

Le TTS dioula (`mms-tts-dyu`) prononce correctement les mois **loanwords** (emprunts
au français) suivis de `kalo la` (« au mois de »). Format validé (PR #84) :

```
[Loanword] kalo la.     → au mois de [X]
Ex : Zanviye kalo la.   → au mois de janvier
     Marisi kalo la.    → au mois de mars
```

> **Règle** : toujours capitaliser le nom du mois (`Zanviye`, pas `zanviye`) et
> utiliser la forme loanword ci-dessus, JAMAIS la forme malienne `karo`.

### Noms traditionnels des mois (lunaire mandingue)

Certaines sources dioula CI emploient des noms traditionnels liés aux saisons.
À utiliser uniquement si le contexte l'exige ; le corpus Wourri privilégie les
loanwords ci-dessus pour la clarté TTS.

| Nom traditionnel | Sens approximatif | Période |
|------------------|-------------------|---------|
| Sanyɛlɛmakalo | mois du changement de pluie | ~sept-oct |
| Funtenibakalo | mois de la grande chaleur | ~mars-avr |

---

## 12bis. Différences Bambara Mali ↔ Dioula Côte d'Ivoire (CRITIQUE)

**Fondamental** : les données bambara Mali (Bayelemabaga, Jeli, Francophonia) et
la plupart des lexiques en ligne sont en **bambara malien**, PAS en dioula CI.
Certaines formes maliennes sont **bannies** dans ce projet au profit des formes
dioula CI attestées par validation native.

### Formes bannies → formes dioula CI (attestées par le validateur natif)

| Sens | ❌ Bambara Mali (banni) | ✅ Dioula CI (à utiliser) | Source |
|------|------------------------|--------------------------|--------|
| mois | `karo` | `kalo` | validation native, PR #84 |
| marché | `sugu` | `lɔgɔ` | validation native #52/#53 |
| moment/temps | `waati` | `tuma` | validation native #51 |
| beaucoup | `kosɛbɛ` | `caman` | corrections CI du projet |
| cultivateur | `sɛnnɛkɛla` | `sɛnɛbaga` | validation native |

> **Règle absolue** : en cas de doute entre une forme malienne et une forme CI,
> la **validation d'un locuteur natif dioula CI fait autorité** — pas les lexiques
> maliens ni ce document (voir formulaires de validation `data/issue_*_native_validation`).

### Note sur les suffixes

Le suffixe de participe/résultatif `-len` (bambara Mali standard, ex. `jalen` =
séché) coexiste avec `-nin` en dioula CI selon les locuteurs. Le corpus Wourri
suit la forme retenue par le validateur natif entrée par entrée — ne pas
uniformiser sans validation.

### Vocabulaire dioula CI attesté (au-delà des formes bannies)

Termes confirmés par les validations natives des cultures :

| Terme dioula CI | Sens |
|-----------------|------|
| `tigɛ` | récolter / couper (PAS `filɛ` qui = regarder) |
| `Tulu dilanyɔrɔw` | huileries |
| `jibolisira` | canal d'écoulement / drainage |
| `duguturu` | bouture (de manioc) |
| `zira` | cuivre |
| `fɔsifati` | phosphate |
| `jitanya` | sécheresse |
| `sumaya` | humidité |

---

## 13. Erreurs types du corpus actuel

### Erreur 1 : Verbe pas en fin de proposition

```
FAUX  : Aw ye sɛnɛ santimɛtiri mugan mugan.
         (sɛnɛ est le verbe mais il n'est pas en fin, et pas d'objet)
JUSTE : Aw ye malo da santimɛtiri mugan mugan.
         (objet=malo, verbe=da [planter], complément=distance)
```

### Erreur 2 : Mots inventés / non attestés

```
FAUX  : dugukolo lèmùna (terre humide — "lèmùna" n'existe pas)
JUSTE : dugukolo jɛman (terre blanche/claire) ou dugukolo nɔgɔman (terre humide/mouillée)
```

### Erreur 3 : Trop de compléments empilés

```
FAUX  : Aw ye màlo sɛnɛ mɛ kalo la sanji tuma na.
         (planter + mai + pendant la pluie → confusion totale)
JUSTE : Mɛ kalo la, aw ye malo sɛnɛ. O tuma na sanji bɛ na.
         (En mai, plantez le riz. À ce moment la pluie vient.)
```

### Erreur 4 : Phrase sans verbe

```
FAUX  : Sɛnɛ ka kɛ santimɛtiri bi wɔɔrɔ wɔɔrɔ.
         (traduction littérale "culture doit se faire 80cm" — pas naturel)
JUSTE : Aw ye malo da santimɛtiri bi wɔɔrɔ wɔɔrɔ.
         (Plantez le riz à 80 centimètres.)
```

### Erreur 5 : Diacritiques fantaisistes

```
FAUX  : màlo, jì, lèmùna (accents non-standard ajoutés manuellement)
JUSTE : malo, ji (le TTS MMS-dyu ne gère pas les tons, simplifier)
NOTE  : Les tons existent en bambara mais le modèle TTS ne les utilise pas.
        Garder l'orthographe standard sans accents pour la synthèse vocale.
```

### Erreur 6 : Confusion transitif/intransitif au passé

```
FAUX  : Malo tigɛli waati ye kalo saba ye sɛnɛli kɔfɛ.
         (double "ye" — structure cassée)
JUSTE : Kalo saba sɛnɛ kɔfɛ, malo bɛ se ka tigɛ.
         (3 mois après la plantation, le riz peut se récolter.)
```

---

## 14. Exemple de correction complète

### Entrée `riz_conseil_001`

**Original (corpus actuel, score 0.70) :**
```
Bambara : Aw ye màlo sɛnɛ mɛ kalo la sanji tuma na. Aw ye dugukolo lèmùna ɲini, jì ka se ka don a la. Aw ye sɛnɛ santimɛtiri mugan mugan.
Français : Plante ton riz en mai pendant la saison des pluies. Cherche une terre humide où l'eau peut rester. Plante avec 20 centimètres d'écart.
```

**Problèmes identifiés :**

| # | Problème | Fragment fautif | Règle violée |
|---|----------|----------------|--------------|
| 1 | Complément de temps mal placé | `sɛnɛ mɛ kalo la sanji tuma na` | §1 SOV — temps en tête |
| 2 | Mot inventé | `lèmùna` (humide) | §13 — mot non attesté |
| 3 | Contresens verbal | `ji ka se ka don a la` (eau peut entrer) | §2 — `don`=entrer ≠ rester |
| 4 | Verbe manquant | `Aw ye sɛnɛ santimɛtiri` | §3 — impératif sans objet+verbe |
| 5 | Diacritiques inventés | `màlo`, `jì` | §13.5 — simplifier pour TTS |

**Version corrigée :**
```
Bambara : Sanji tuma na, aw ye malo sɛnɛ mɛ kalo la. Aw ye dugukolo jɛman ɲini, ji ka se ka to a la. Aw ye malo da santimɛtiri mugan mugan.
Français : Pendant la saison des pluies, plantez le riz en mai. Cherchez une terre humide, où l'eau peut rester. Plantez le riz tous les 20 centimètres.
```

> **ATTENTION** : Ne jamais supprimer d'information du français lors de la correction bambara.
> Chaque élément du `reponse_fr` DOIT avoir son équivalent dans le `reponse_bambara`.

**Changements :**

| Avant | Après | Justification |
|-------|-------|---------------|
| `Aw ye màlo sɛnɛ mɛ kalo la sanji tuma na` | `Sanji tuma na, aw ye malo sɛnɛ mɛ kalo la` | Complément temporel en tête (§1) |
| `dugukolo lèmùna` | `dugukolo jɛman` | `jɛman` = humide/mouillé, attesté Wikibooks (§13.2) |
| `ji ka se ka don a la` | `ji ka se ka to a la` | `to` = rester (attesté), `don` = entrer (contresens) |
| `Aw ye sɛnɛ santimɛtiri` | `Aw ye malo da santimɛtiri` | Ajout objet `malo` + verbe `da` (planter) (§3) |
| `màlo`, `jì` | `malo`, `ji` | Diacritiques simplifiés pour TTS MMS-dyu (§13.5) |

**Audio de test généré** (2026-04-11) :
- Original : `http://localhost:8000/static/audio/bm_f834c27b-3d9a-423a-95c9-296d9f297ad1.ogg`
- Corrigé  : `http://localhost:8000/static/audio/bm_edab755c-6316-4198-b6e3-da821cc793d9.ogg`

---

## 15. Checklist de validation par phrase

Avant de valider une phrase du corpus, vérifier :

- [ ] **SOV respecté** : le verbe est en dernier dans chaque proposition
- [ ] **Objet avant verbe** : dans `Aw ye X Y`, X = objet, Y = verbe
- [ ] **Auxiliaire correct** : `bɛ` (présent), `ye` (passé/impératif), `bɛna` (futur)
- [ ] **Postpositions correctes** : `la/na` (lieu), `kɔnɔ` (dans), `kan` (sur), `kɔfɛ` (après)
- [ ] **Pas de mots inventés** : chaque mot doit être dans An Ka Taa, Bayelemabaga, ou Common Voice
- [ ] **Pas de diacritiques fantaisistes** : `malo` pas `màlo`, `ji` pas `jì`
- [ ] **3 phrases max** : chaque entrée corpus = 3 phrases courtes (≤15 mots chacune)
- [ ] **Complément de temps en tête** : "Mɛ kalo la, ..." pas "... mɛ kalo la sanji tuma na"
- [ ] **Conditionnel correct** : "Ni sanji na, ..." (si la pluie vient)
- [ ] **Négation correcte** : `tɛ` (présent), `ma` (passé), `tɛna` (futur), `kana` (impératif)
- [ ] **Pluriel en -w** : `forow` (champs), `kisɛw` (graines)
- [ ] **Pas de traduction littérale du français** : penser en SOV, pas en SVO

---

## INSTRUCTIONS POUR L'AUTRE SESSION CLAUDE

Si tu lis ce fichier depuis une autre session Claude Code :

1. **Lis le corpus** : `wouri-api/dictionnaires/corpus_ivr.json` (163 entrées)
2. **Pour chaque entrée** : compare `reponse_bambara` avec les règles ci-dessus
3. **Applique la checklist §15** sur chaque phrase
4. **Corrige** en respectant l'ordre SOV, les bons auxiliaires, et les mots attestés
5. **Supprime** les diacritiques fantaisistes (accents graves/aigus sur les voyelles standard)
6. **Teste l'audio** via `POST http://localhost:8000/api/tts/bambara?text=...&is_french=false`
7. **Le français (`reponse_fr`) reste inchangé** — seul le bambara est corrigé
8. **Incrémente la version** du corpus (production actuelle : v2.4 — voir ADR-0014
   pour le processus de promotion du draft v3) et ajoute une note de correction

### Priorité de correction :
1. Phrases avec verbe manquant ou mal placé (erreur critique)
2. Mots inventés / non attestés (incompréhensible pour le natif)
3. Ordre des compléments (confus mais partiellement compréhensible)
4. Diacritiques (cosmétique, TTS ne les utilise pas)
