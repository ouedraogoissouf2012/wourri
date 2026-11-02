# Session de collecte avec le locuteur — mots baoulé manquants

- **Date** : 2026-11-02
- **Objet** : trois concepts n'ont **plus aucun mot validé** — `TEMPS_METEO`, `ACTION_VENDRE`,
  `CULTURE_HARICOT` (suite de la relecture, PR #597).
- **Conséquence** : un paysan qui pose en baoulé une question **météo** ou de **vente** n'est
  **pas compris du tout**. La météo est une fonction centrale de WOURI.
- **Réf.** : #600, ADR-0045, ADR-0046.

> **Règle rappelée** : aucun mot baoulé n'est inventé ici. Ce document ne contient que des
> **questions en français** à poser au locuteur. Les réponses viennent de lui.

---

## Partie A — 7 réponses qui débloquent sans rien collecter

Ces mots ont déjà été proposés et acceptés par le locuteur, mais sa traduction laisse un
doute. **Ils attendent seulement un « oui » ou un « non » de sa part.** Trois d'entre eux
suffiraient à réparer *vendre*.

| # | Mot | Sens qu'il a donné | Question à lui poser |
|---|---|---|---|
| 1 | **gua** | « prix » | Si un paysan dit **gua**, parle-t-il de **vendre**, ou seulement du **prix** ? |
| 2 | **to** | « paye » | **to** veut-il dire **vendre**, ou seulement **payer / acheter** ? |
| 3 | **fien** | « sale » | ⚠️ **à lever en priorité** — voir ci-dessous |
| 4 | **sielɛ** | « mets-là » | **sielɛ** sert-il à dire **stocker / conserver la récolte** ? |
| 5 | **afuɛ** | « année » | Dans une question de paysan, **afuɛ** peut-il désigner une **période / saison** ? |
| 6 | **juejue** | « santé » | **juejue** s'emploie-t-il pour **saluer** quelqu'un ? |
| 7 | **nnolo** | « passer informations » | **nnolo** sert-il à **demander un conseil** ? |

### ⚠️ Le point n° 3 est ambigu en français, pas en baoulé

Le locuteur a écrit que **fien** veut dire « **sale** ». Ce mot français a deux sens
possibles, et ils mènent à des conclusions opposées :

- **sale** = *vente* (comme en anglais) → le mot **entre** dans le concept *vendre* ;
- **sale** = *pas propre* → le mot **n'a rien à voir** avec vendre.

**Il faut lui demander lequel des deux il voulait dire.** Tant que ce n'est pas tranché, le
mot reste écarté — ce qui est le bon réflexe, mais prive peut-être *vendre* d'un mot juste.

**Comment poser la question, sans suggérer la réponse :**
> « Quand tu as écrit que **fien** veut dire *sale*, est-ce que tu parlais de quelque chose de
> **pas propre**, ou de quelque chose qu'on **vend** ? »

---

## Partie B — collecte nouvelle : il ne reste aucun candidat

### B.1 · Météo — **priorité la plus haute**

**Les trois mots proposés ont tous été écartés**, et pour de bonnes raisons :

| Mot écarté | Sens donné par le locuteur | Pourquoi ce n'est pas la météo |
|---|---|---|
| **dô** | « l'heure » | l'heure qu'il est, pas le temps qu'il fait |
| **ayrɛ** | « médicament » | sans rapport |
| **lika dolɛ** | « ombre » | une conséquence du soleil, pas le temps lui-même |

➡️ **Ne pas les reproposer.** Il faut repartir de zéro sur ce concept.

**Questions à poser au locuteur** (une par ligne, il répond en baoulé) :

> - Comment dit-on **le soleil** ?
> - Comment dit-on **le vent** ?
> - Comment dit-on **la chaleur** ? Et **le froid** ?
> - Comment dit-on **les nuages** ?
> - Comment un paysan demande-t-il : « **quel temps fait-il aujourd'hui ?** »
> - Comment dit-on : « **il fait beau** » ?
> - Comment demande-t-on : « **est-ce qu'il va pleuvoir ?** »

> 📝 **Attention à ne pas confondre deux concepts.** *La pluie* et *la saison des pluies*
> appartiennent à un autre concept, déjà pourvu. Ce qu'on cherche ici, c'est **le temps qu'il
> fait maintenant** : soleil, vent, chaleur, nuages.

### B.2 · Vendre — à traiter **après** la partie A

Si le locuteur confirme **gua**, **to** ou **fien**, le concept est réparé **sans collecte**.
Sinon, poser :

> - Comment dit-on **vendre** ?
> - Comment dit-on **le marché** ?
> - Comment un paysan demande-t-il : « **à combien je peux vendre ma récolte ?** »

### B.3 · Haricot — le moins urgent

Mot écarté : **n'ma**, que le locuteur traduit par « fruits » — trop général.

> - Comment dit-on **le haricot** ? Et le **niébé** ?
> - Comment dit-on : « **un champ de haricots** » ?

---

## Partie C — après la séance

1. Consigner les réponses dans l'atelier, comme les autres mots : chaque mot passe par la
   validation normale, **rien n'entre directement dans le dictionnaire**.
2. Pour les 7 mots de la partie A, mettre à jour
   `dictionnaires/relecture_mots_cles_bci.json` : passer chaque décision à `garde` ou à
   `hors_concept` selon sa réponse. **Ne laisser aucun `a_confirmer` sans suite** — un mot
   oublié dans cet état reste écarté pour toujours, en silence.
3. Reconstruire le dictionnaire et vérifier que les trois concepts ont de nouveau des mots.
4. **Contrôle final, le seul qui compte** : poser une vraie question météo en baoulé et
   vérifier qu'elle est comprise. Tant que ce test n'est pas passé, le concept n'est pas
   réparé — seulement rempli.

---

## Pour celui qui anime la séance

- **Ne pas suggérer de réponse.** Si l'on propose un mot et qu'on demande « c'est bien ça ? »,
  on obtient un acquiescement, pas une information. C'est exactement ce qui a produit les
  39 mots écartés.
- **Noter le sens en français tel qu'il le dit**, même si cela paraît étrange : c'est
  précisément cette traduction qui a permis de détecter que `ayrɛ` signifiait « médicament ».
- **Un mot par question.** Les listes à cocher fabriquent des faux positifs.
- Si un mot a plusieurs sens, **le noter**, ne pas trancher à sa place.
