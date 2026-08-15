# ADR-0029 — Activation du filtre LM KenLM dioula (anti-hallucination ASR)

**Statut** : accepté
**Date** : 2026-08-14
**Auteur(s)** : Claude (assistant) sous direction de Ouedraogo Issouf
**Valideur** : Ouedraogo Issouf (Ruben)
**Lié à** : issue [#94](https://github.com/ouedraogoissouf2012/wourri/issues/94) (« Améliorer ASR dioula CI — KenLM + hotwords + fix CULTURE_MAIS »)
**Hérite de** : [ADR-0022](0022-composition-chaine-asr-dioula.md) (verrou d'évaluation WER de la chaîne ASR — voir §Décision)
**ADRs liés** : [ADR-0027](0027-decision-nemo-installer-ou-retirer.md) (NeMo), [ADR-0003](0003-plan-ajout-omnilingual.md) (bench ASR)

---

## Contexte

### Portée de cet ADR (et ce qu'il ne couvre pas)

L'issue #94 groupe trois sujets. Deux sont hors périmètre ici :
- **fix CULTURE_MAIS** : déjà livré (commit `39d59ae`, Phase 1 — suppression du
  fallback silencieux vers `CULTURE_MAIS`, ajout `clarify_missing_culture`).
- **hotwords ASR** : non traité (les datasets `koumankan`/`findora` sont inertes,
  cf. `docs/GUIDE_DIOULA_CIRCUIT_ET_METHODE.md:65`) → à faire l'objet d'un ADR distinct.

**Cet ADR ne tranche que l'activation du filtre LM KenLM** (1 ADR = 1 sujet).

### État actuel qui pose problème (vérifié dans le code)

Le module `app/services/validation/lm_filter.py` existe (livré inactif au commit
`39d59ae`, 2026-04-19) et est fonctionnel, mais :

1. **Il n'a aucun consommateur.** `grep` sur `app/` : ni `get_lm_filter`, ni
   `DioulaLMFilter`, ni `rescore_candidates` ne sont appelés hors du module lui-même.
   Le filtre est du **code non câblé**.

2. **Le flag `ENABLE_LM_RESCORING` n'existe pas.** La docstring (`lm_filter.py:19,23`)
   le mentionne, mais `config.py` ne le déclare nulle part (`grep` négatif). L'« activation »
   ne dépend aujourd'hui que de deux conditions implicites : package `kenlm` installé
   **et** fichier binaire présent (`lm_filter.py:88-102`). Sinon → pass-through
   silencieux (`verdict="HIGH"` systématique).

3. **Le binaire `kenlm_dyu_agri.binary` n'est ni tracké ni présent.** Attendu à
   `data/models/kenlm_dyu_agri.binary` (`lm_filter.py:37`), le répertoire
   `data/models/` **n'existe pas** sur `APIPy`. Seul un notebook Colab
   (`finetune/colab/kenlm_only.ipynb`) est tracké — le binaire doit être entraîné
   puis versionné, ce qui n'a pas été fait.

4. **Seuils hardcodés.** `PPL_REJECT=500`, `PPL_CAUTION=150`, `OOV_REJECT=0.40`,
   `REPEAT_MAX_REJECT=3` (`lm_filter.py:41-44`) sont des constantes module — la
   docstring elle-même dit « à calibrer après première utilisation en prod ».
   Violation `constraints.md §1.2`.

### Contrainte d'architecture décisive : pas de n-best list

Le pipeline ASR (`app/services/asr/chain.py`) ne produit **pas** de liste de
n-meilleures hypothèses : chaque provider (`transcribe_wav`) retourne **une seule
chaîne** (`chain.py:145`). Or `rescore_candidates()` (`lm_filter.py:174-188`)
suppose plusieurs candidats. **Il n'y a donc rien à rescorer aujourd'hui.**

Décision de rôle (Ruben, 2026-08-14) : le LM est retenu comme **filtre
anti-hallucination mono-hypothèse** — il score l'unique transcription via
`score().verdict` pour détecter/dégrader les sorties absurdes (« ka ka aw » =
kakawo fragmenté, répétitions pathologiques, perplexité aberrante). **Pas** de
vrai rescoring shallow-fusion (qui exigerait de faire émettre des n-best par les
providers, donc une refonte de la chaîne — hors scope).

### Rapport avec ADR-0022

ADR-0022 (proposé) verrouille : « **toute modification de la chaîne ASR exige une
éval WER comparative sur ≥ 30 vraies voix dioula avec transcriptions de référence** ».
Le filtre LM **modifie le comportement de sortie de la chaîne** (il peut altérer
ou dégrader la confiance d'une transcription). Il **hérite donc de ce verrou** :
pas d'activation gating en prod sans mesure sur vraies voix.

Faut-il **étendre** ADR-0022 plutôt qu'un nouvel ADR ? **Non.** ADR-0022 traite la
*composition* (ordre des providers, NeMo). L'activation d'un filtre de validation
post-ASR est un *sujet distinct* (une brique nouvelle, un binaire à versionner, un
flag à créer). La convention README (« 1 ADR = 1 sujet ») impose un ADR séparé qui
**référence** le verrou de bench d'ADR-0022 — c'est ce que fait le présent ADR.

### Pourquoi maintenant

Les hallucinations NeMo/MMS sur dioula CI sont documentées (AUDIT_DIOULA, cascade
kakawo→ka ka aw). Le filtre existe mais dort : soit on l'active proprement
(binaire versionné + flag + mesure), soit on décide de ne pas l'activer et on trace
la dette. Laisser du code non câblé indéfiniment contredit `constraints.md §1.1`.

---

## Questions posées avant la décision

1. **Vrai rescoring n-best ou filtre anti-hallucination mono-hypothèse ?**
   → Ruben (2026-08-14) : **filtre anti-hallucination** (pas de refonte n-best).
2. **Comment versionner le binaire KenLM ?** → étudié en Option (git-lfs vs
   download-au-build vs hébergement objet).
3. **Faut-il étendre ADR-0022 ?** → Non (sujet distinct, cf. Contexte).

---

## Options étudiées

### 1) Activer ou non le filtre

#### Option A — Activer comme filtre anti-hallucination, derrière un flag OFF par défaut *(recommandée)*
- Créer `ENABLE_LM_RESCORING: bool = False` dans `config.py` (le nom existant dans
  la docstring ; défaut OFF = zéro régression tant que non validé).
- Câbler `get_lm_filter().score()` dans `ASRChain._transcribe_wav` **après**
  normalisation : si `verdict == "REJECT"`, dégrader (p.ex. déclencher le second
  passage agricole existant, ou marquer la transcription douteuse pour la clarification).
- Externaliser les 4 seuils PPL/OOV en config.
- Activation en prod **conditionnée** au bench WER (verrou ADR-0022).

#### Option B — Ne pas activer, retirer le module
- Supprimer `lm_filter.py` + notebook. Réversible via git.
- Cohérent si on juge que le normalizer 4-étapes + `AGRI_KEYWORDS` (`chain.py:22-27`)
  couvrent déjà les hallucinations et qu'un LM 4-gram n'ajoute rien de mesuré.

#### Option C — Statu quo (laisser dormant)
- Ne rien faire. Le module reste non câblé, le flag inexistant.
- Rejetée : c'est précisément l'état-problème (`constraints.md §1.1` : pas de code
  mort laissé en l'état).

### 2) Versionnage du binaire (si Option A retenue)

| Sous-option | Description | Avantages | Inconvénients |
|---|---|---|---|
| **V1 — git-lfs** | Binaire suivi via Git LFS dans le repo | Reproductible, versionné avec le code, simple à cloner | Nécessite LFS sur le repo + CI + hôte Dokploy ; quota LFS GitHub ; taille (~dizaines de Mo) |
| **V2 — download au build** | Binaire hébergé (release GitHub / objet), `curl` dans le Dockerfile ou au boot | Repo léger ; versionnable via tag de release | Dépendance réseau au build/boot ; checksum à vérifier ; point de panne déploiement |
| **V3 — volume monté (comme MMS-dyu adapter)** | Binaire hors-git, monté en volume Dokploy (cohérent avec `MMS_DYU_ADAPTER_PATH`, ADR-0022 travail induit) | Cohérent avec la pratique existante des modèles lourds ; repo léger | Non versionné avec le code ; provisioning manuel de l'hôte ; risque de dérive silencieuse |

Recommandation : **V3** si le binaire s'aligne sur le pattern « gros modèle monté
en volume » déjà acté pour l'adapter MMS-dyu (ADR-0022) — cohérence opérationnelle.
**V1 (git-lfs)** si Ruben préfère la reproductibilité au prix du quota LFS. **V2**
seulement si le binaire reste petit et qu'on veut un repo léger sans LFS.

### 3) Protocole de bench WER avant/après (prérequis à toute activation prod)

Ce protocole **réutilise le verrou et le harnais d'ADR-0022** (pas de nouveau
protocole ad hoc) :

1. **Corpus** : les mêmes **≥ 30 vraies voix dioula CI annotées** exigées par
   ADR-0022 (collecte terrain Ruben + locuteur natif). Inclure explicitement des
   cas d'hallucination connus (kakawo→ka ka aw, répétitions).
2. **Métrique primaire** : WER via `finetune/evaluate_wer.py` (chemins in-repo à
   corriger, cf. ADR-0022 réf. audit C11).
3. **Comparaison A/B** : même chaîne ASR, filtre LM **OFF** vs **ON**, sur le même
   corpus. Mesurer : Δ WER global, et surtout **taux d'hallucinations grossières
   avant/après** (le filtre vise les hallucinations, pas le WER moyen).
4. **Critère d'activation** : le filtre passe en prod (`ENABLE_LM_RESCORING=True`)
   **seulement si** il réduit les hallucinations grossières **sans** dégrader le WER
   global au-delà d'un delta convenu (à fixer avec Ruben, p.ex. ≤ +2 pts WER pour
   une réduction nette des hallucinations). Sinon → OFF, dette tracée.
5. **Anti-biais** : pas de calibration des seuils PPL sur le corpus de bench
   lui-même (sur-apprentissage) — les seuils se calibrent sur un split distinct ou
   sur la littérature (Kumar et al. 2023, déjà citée `lm_filter.py:40`) puis se
   valident sur le bench.

---

### Comparatif décision (1)

| Critère | A (activer, flag OFF) | B (retirer) | C (statu quo) |
|---|---|---|---|
| Résout le code mort #94 | ✔ (câblé + flag) | ✔ (supprimé) | ✘ |
| Réduit hallucinations | Potentiellement (à mesurer) | Non | Non |
| Coût amont | Binaire + flag + config + bench | Faible (suppression) | Nul |
| Risque régression | Faible (OFF par défaut) | Nul | Nul |
| Respecte constraints.md | ✔ | ✔ | ✘ (code mort) |
| Réversibilité | Élevée (flag) | Moyenne (git revert) | — |

---

## Décision

**Option A retenue** (2026-08-14, Ruben), sur les trois axes posés :

1. **Activer (A)**, pas retirer (B) : le filtre est câblé comme **filtre
   anti-hallucination mono-hypothèse** (pas de rescoring n-best — hors scope, cf.
   Contexte), derrière `ENABLE_LM_RESCORING: bool = False` en config (flag OFF par
   défaut = zéro régression tant que non validé). Les 4 seuils PPL/OOV sont
   externalisés.
2. **Versionnage V3** (volume monté) : cohérent avec le pattern déjà acté pour
   l'adapter MMS-dyu (ADR-0022) — binaire hors-git, provisionné sur l'hôte.
3. **Protocole de bench** : hérite du verrou ADR-0022 sans le modifier.
   **Activation en prod conditionnée** au bench WER comparatif OFF/ON sur
   **≥ 30 vraies voix dioula CI annotées**, critère d'activation = réduction nette
   des hallucinations grossières sans dégradation du WER global au-delà du delta
   convenu avec Ruben.

Justification : A est la seule option qui résout le code mort (#94, `constraints.md
§1.1`) tout en gardant un risque de régression nul par défaut (flag OFF) ; le rôle
« filtre anti-hallucination » plutôt que rescoring n-best correspond à la
contrainte d'architecture réelle de la chaîne ASR (une seule hypothèse par
provider) ; le versionnage V3 évite d'introduire un nouveau pattern de gestion de
modèle lourd alors qu'un pattern équivalent existe déjà.

---

## Conséquences

- **Positives (si A)** : hallucinations grossières filtrables ; fin du code non
  câblé et des seuils hardcodés ; activation réversible par flag ; réutilise le
  harnais WER existant.
- **Négatives assumées (si A)** : dépendance à un binaire externe à provisionner ;
  travail de collecte de vraies voix (partagé avec ADR-0022) ; le LM 4-gram peut
  produire des faux rejets sur du dioula correct mais rare (mitigé par flag OFF +
  bench avant activation).
- **Négatives (si B)** : on abandonne un travail d'entraînement déjà amorcé
  (notebook Colab) — acceptable si non prouvé utile.
- **Migration / travail induit (si A)** :
  1. `config.py` : `ENABLE_LM_RESCORING` + 4 seuils PPL/OOV externalisés.
  2. `lm_filter.py` : lire les seuils depuis settings ; respecter le flag.
  3. `asr/chain.py` : câbler `score()` après normalisation, brancher la dégradation.
  4. Versionnage binaire selon V1/V2/V3.
  5. Tests : pass-through si flag OFF / binaire absent ; REJECT déclenche la
     dégradation attendue ; seuils injectés.
  6. Bench WER (verrou ADR-0022) avant `ENABLE_LM_RESCORING=True` en prod.
- **Verrou futur** : réentraîner le LM (nouveau corpus) invalide la calibration des
  seuils → re-bench (à tracer ici).

## Références

- Code : `app/services/validation/lm_filter.py` (module entier) ;
  `app/services/asr/chain.py:22-27,77-127,145` ; `app/config.py` (absence du flag).
- Commit d'origine : `39d59ae` (« feat(#94): fix CULTURE_MAIS + LM filter (inactif) »).
- Verrou d'évaluation : [ADR-0022](0022-composition-chaine-asr-dioula.md) §Décision.
- Contraintes : `docs/constraints.md §1.1` (pas de code mort), `§1.2` (hardcoding), `§5`.
- Issue [#94](https://github.com/ouedraogoissouf2012/wourri/issues/94).

## Historique

- 2026-08-14 — rédaction (statut **proposé**). Rôle « filtre anti-hallucination »
  acté par Ruben ; décision activer/retirer + versionnage réservée à Ruben.
  Confirmé : hérite du verrou de bench WER d'ADR-0022 sans en modifier la composition.
- 2026-08-14 — **accepté**. Ruben valide l'Option A : activation en filtre
  anti-hallucination, flag `ENABLE_LM_RESCORING=False` par défaut, seuils
  externalisés, binaire versionné en V3 (volume monté), activation prod
  conditionnée au bench WER ≥ 30 voix (héritage ADR-0022).
