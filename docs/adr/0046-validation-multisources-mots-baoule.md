# ADR-0046 — Validation multi-sources des mots baoulé : la méthode du dioula, avec deux garde-fous

**Statut** : proposé
**Date** : 2026-10-24
**Auteur(s)** : Claude (assistant) sous direction de Ouedraogo Issouf
**Valideur** : Ouedraogo Issouf — procédé demandé le 2026-10-24 (« on prend un mot et on cherche sa signification en baoulé […] on y va »)
**ADRs liés** : [ADR-0045](0045-nlu-baoule-methode-dioula-validation-atelier.md) (NLU baoulé, validation dans l'atelier), [ADR-0041](0041-choix-culture-et-homographes-nlu.md) (homographes), [ADR-0014](0014-promotion-corpus-v3-dioula-ci.md) (validation native du dioula)
**Issue** : #475

---

## Contexte

- **Le besoin** : constituer un dictionnaire de mots baoulé fiable, avant les phrases. Pour chaque mot français, on cherche sa traduction dans plusieurs sources. Les sources qui concordent valident le mot ; les cas limites vont au locuteur natif (esse), dans l'atelier.
- **Ce qu'a fait le dioula** (`tools/bambara_validator.py`) :
  - dix sources pondérées selon leur fiabilité : dictionnaire validé ×5, corpus dioula CI ×3, bambara ×2, sites web ×1, confirmations ×1 ;
  - un score sur 20 : **8/20 et plus = validé, 5–7 = décision manuelle**.
- **Ce que la vérification a montré (2026-10-24)** : le constat **C10** de `docs/AUDIT_DIOULA_2026-08.md` n'est pas corrigé.
  - `DATA_DIR` remonte un dossier de trop, et `data/validation_sources/` n'existe nulle part sur le poste.
  - Les six sources locales se chargent **vides en silence** : l'outil ne peut plus atteindre 8/20.
  - Dans les faits, les mots dioula ont été validés par le locuteur natif, après comptage d'occurrences source par source (changelog de `nlu_concepts.json`, ex. « maŋoro (15 Baye + 30 Jeli) »).
- **Le souvenir du valideur** : « 8 sites sur 12 valident, 6–7 vont au locuteur ». C'est le même principe que le code, sans les poids.

## Options étudiées

### Option A — Vote non pondéré « 8 sources sur 12 »
- **Avantages** : simple à expliquer.
- **Inconvénients** :
  - le baoulé n'a pas 12 sources indépendantes qui donnent un sens ;
  - une source fragile (pivot anglais) pèserait autant que le locuteur natif ;
  - deux sources copiées l'une sur l'autre (PanLex et ChiKhaPo) compteraient double.

### Option B — Vote pondéré sur 20, seuils du dioula, deux garde-fous (retenue)
- **Avantages** :
  - même méthode et mêmes seuils que le dioula ;
  - les sources fiables pèsent plus ;
  - les garde-fous corrigent les deux faiblesses mesurées au premier passage.
- **Inconvénients** : les poids sont un jugement. Ils sont écrits ici et ajustables par décision du valideur.

## Décision

**Option retenue : B.** Code : `scripts/baoule_sources.py` (sources) et `scripts/baoule_validation_mots.py` (vote, seuils, sorties).

**Sources et poids** (le registre complet, avec les mesures et les licences, est dans `docs/REGISTRE_SOURCES_BAOULE.md`) :

| Source | Rôle | Poids |
|---|---|---|
| Mots acceptés par esse dans l'atelier | sens, locuteur natif | 5 |
| Dictée d'esse (433 phrases, traduction française) | sens, co-occurrence | 3 |
| Wiktionnaire français (826 entrées, CC BY-SA) | sens, glose française | 3 |
| GATITOS (Google, 3 996 entrées, CC BY) : même entrée anglaise traduite en français et en baoulé | sens, pivot anglais | 2 |
| PanLex (via ChiKhaPo, CC0/MIT) baoulé → anglais → français | sens, pivot anglais | 2 |
| Bible baoulé 1998 alignée verset par verset sur Louis Segond 1910 | sens, co-occurrence **mot à mot uniquement** | 1 |
| Common Voice (phrases validées) / Zenodo / SMOL / web (FineWeb-2, MADLAD, GlotCC, FinePDFs réunis) | attestation de la graphie | 1 chacun |
| **Total** | | **20** |

**Règles** :
1. Score = somme des poids des sources qui proposent le mot. Une source compte une fois par concept.
2. **Validé** : score ≥ 8, **et** au moins deux sources de sens, **et** au moins une source forte (locuteur, dictée ou Wiktionnaire).
3. **Au locuteur** (fiche `mot_cle` dans l'atelier) : score ≥ 5 et au moins 2 points de sens. La Bible seule ne suffit pas.
4. **Écarté** : le reste, gardé dans le rapport avec ses sources.

**Garde-fous** :
- **Source vide = arrêt** (`SourceVide`) : la leçon du constat C10. Une source déclarée ne peut pas manquer en silence. La source locuteur se désactive seulement explicitement (`--sans-locuteur`), et le rapport le consigne.
- **Mots-outils mesurés** : les mots présents dans plus de 3 % des phrases du corpus web (n, be, ɔ, sran, like, fa, si…) sont écartés, ainsi que les n-grammes qu'ils bordent. Ils prouvent qu'un texte est du baoulé, pas qu'un mot traduit « cacao ». La liste est calculée à chaque passage et consignée dans le rapport, jamais écrite à la main.
- **Les attestations ne valident jamais un sens** (règle 2) : au premier passage, sans cette règle, *to*, *si* et *do* étaient validés par le seul pivot anglais.

**Mots français cherchés** : le libellé de chaque concept de `nlu_concepts.json` et ses mots-clés français.
- Un mot-clé est reconnu comme français quand il figure dans le vocabulaire des données (Bible française, GATITOS, dictée), sans liste écrite à la main.
- Les homographes déclarés (ADR-0041 : « mais », « fini »…) ne sont jamais cherchés.

**Bible** : décision du valideur (2026-10-24), « mot pour mot, pas de phrase ».
- Seules les statistiques de paires de mots servent.
- Le texte (© Alliance Biblique de Côte d'Ivoire 1998) reste dans le dossier local des sources, n'est jamais versionné et ne sert jamais de réponse.

**Pas de scraping maison** :
- les sites ouverts (jw.org, etc.) sont déjà dans les collections web publiées (FineWeb-2, MADLAD) ;
- les autres l'interdisent (Glosbe, baoule.ci « tous droits réservés », kasahorow « all rights reserved »).

## Mesure au premier passage (2026-10-24, sans la source locuteur)

- **18 mots validés**, 16 concepts sur 61 couverts. Exemples : riz *awie*, banane *manda*, cacao *kakao*, café *kafe*, ananas *ablɛlɛ*, poule *akɔ*, mouton *bua*, chèvre *boli*, poisson *jue*, pluie *nzue*, récolter *kpɛ*, vendre *atɛ*, aide *uka*.
- **61 candidats à 5–7/20**, dont 56 nouveaux pour l'atelier ; 5 étaient déjà proposés. Exemples : igname *duo*, manioc *agba*, maïs *able*, arachide *ngatɛ*.
- **222 écartés.**

Avant les garde-fous, le passage donnait 30 validés et 160 candidats, où figuraient des mots-outils (ɔ, be, « 12 »).

## Conséquences

- **Positives** :
  - le dictionnaire baoulé suit la méthode du dioula, avec un score et des sources traçables pour chaque mot ;
  - le locuteur ne reçoit que les cas limites ;
  - une source cassée ne peut plus fausser le vote en silence.
- **Négatives assumées** :
  - les mots validés sans le locuteur restent des validations de sources écrites. Ils entrent au dictionnaire servi seulement par `baoule_nlu_build.py`, sur décision du valideur ;
  - beaucoup de concepts restent sans mot : salutations, saisons, rôles. Les sources écrites en parlent peu, la dictée et le locuteur sont la voie.
- **Travail induit** :
  - importer `lot_atelier_locuteur.json` dans l'atelier (compte locuteur, onglet « Ajouter ») ;
  - relancer avec `--locuteur` quand esse aura validé ;
  - corriger le constat C10 du dioula, hors de cet ADR.
- **Retour arrière** : aucun impact sur la production. Rien n'est servi par cette décision.

## Historique

- 2026-10-24 — proposé, premier passage mesuré (ci-dessus).
