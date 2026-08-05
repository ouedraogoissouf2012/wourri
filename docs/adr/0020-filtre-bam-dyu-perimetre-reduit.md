# ADR-0020 — Filtre BAM↔DYU : périmètre réduit aux règles phonologiques (refonte #90)

**Statut** : accepté
**Date** : 2026-08-05
**Auteur(s)** : Claude (assistant) sous direction de Ouedraogo Issouf
**Valideur** : Ouedraogo Issouf

---

## Contexte

L'issue #90 (avril 2026) demande de coder un filtre bidirectionnel bambara Mali ↔
dioula CI (`app/services/language/bam_dyu_filter.py`, `convert_bam_to_dyu` /
`convert_dyu_to_bam`) couvrant 5 règles phonologiques, ~6 substitutions lexicales et
3 transformations grammaticales. Motivation d'alors (SYNTHESE §2.6) : *« FONDATION
DE TOUT : ces différences doivent être codées avant toute exploitation des données
bambara Mali (Bayelemabaga 47k, Jeli 67k, Francophonia 77k) utilisées brutes. »*

**Deux faits vérifiés dans le code (`origin/APIPy`, 2026-08-05) rendent la spec
d'avril partiellement caduque ou dangereuse :**

### Fait 1 — la substitution lexicale automatique contredit une décision plus récente
#90 liste `lɔgɔ ↔ sugu` comme substitution mécanique. Or `scripts/prevalidation_rules.py`
(ADR-0019, spec Codex) a acté que **`sugu` n'est PAS toujours malien** : le lexique
dioula CI Mandenkan l'atteste au sens « sorte/espèce ». La substitution n'est valide
que **conditionnellement au sens français** (« marché » → `lɔgɔ`). Un filtre qui
remplacerait `sugu → lɔgɔ` aveuglément **corromprait** les phrases où `sugu` = sorte.
C'est précisément le piège que la spec Codex nous a fait éviter. Idem `kosɛbɛ`.

### Fait 2 — la motivation « exploiter les données bambara Mali » n'est plus d'actualité
- Les datasets Bayelemabaga/Jeli/Francophonia **ne sont PAS utilisés au runtime**
  (`git grep bayelemabaga|jeli|francophonia -- app/**` → 0 résultat).
- Le **corpus IVR est désormais validé nativement à 100 %** (162/162, PR #336) — on
  n'a plus besoin de convertir du bambara brut pour peupler le corpus.
- Le NLU travaille déjà sur `nlu_concepts.json` + le normalizer post-ASR
  (`asr_normalizer.py`), sans séparation stricte BAM/DYU.

**Pourquoi on décide maintenant** : #90 est traitable côté code, mais le coder tel
qu'écrit introduirait des régressions (substitutions aveugles) et du code mort (filtre
pour exploiter des datasets non utilisés). Il faut redéfinir un périmètre réaliste.

## Questions posées avant la décision

1. Comment cadrer le filtre vu la contradiction `sugu`/`lɔgɔ` avec la spec Codex ?
2. À quoi doit servir le filtre concrètement dans le pipeline ?

Réponses obtenues (Ruben, 2026-08-05) :

- **Q1 → On garde la validation d'aujourd'hui** (spec Codex : substitutions
  conditionnelles au sens, pas de remplacement aveugle).
- **Q2 → Ruben laisse choisir la version la plus viable et proposer.**

## Analyse — ce qui reste utile de #90

En séparant les 3 catégories de règles de #90 :

| Catégorie | Nature | Automatisable sans casser ? |
|---|---|---|
| **Phonologie** (gw↔g, l↔d/j, r↔l intervoc, nin↔len) | Transformations de surface, réversibles | ✅ **Oui** — déterministes, pas de dépendance au sens |
| **Lexique** (sugu, filɛ, bon, ta…) | Dépend du **sens** de la phrase | ❌ Non — déjà géré conditionnellement dans `prevalidation_rules.py` |
| **Grammaire** (équatif, progressif, réfléchi) | Analyse syntaxique | ❌ Non — nécessite un analyseur dioula (inexistant) |

**Le seul périmètre sûr et utile est la phonologie.** Et son usage réaliste n'est PAS
« exploiter les datasets bambara » (caduc), mais **aider le normalizer post-ASR** :
les modèles ASR (entraînés majoritairement sur bambara Mali) produisent parfois des
formes maliennes ; des règles phonologiques DYU↔BAM peuvent générer des **variantes**
pour améliorer le matching NLU/corpus, en complément du fuzzy-matching existant.

## Options étudiées

### Option A — Filtre phonologique seul, au service du normalizer *(recommandée)*

- **Description** : créer `app/services/language/bam_dyu_phonology.py` avec les 5 règles
  phonologiques déterministes et réversibles (`variants_dyu_bam(word) -> set[str]`).
  L'utiliser dans `asr_normalizer.py` pour générer des variantes de matching (pas pour
  réécrire le texte servi). **Aucune substitution lexicale ni grammaticale automatique.**
  Les substitutions lexicales conditionnelles restent dans `prevalidation_rules.py`.
- **Avantages** : sûr (pas de corruption sémantique), utile (améliore le matching ASR→NLU),
  ne duplique/contredit pas la spec Codex, périmètre testable (≥90 % sur 50 paires phono).
- **Inconvénients** : ne fait pas la conversion lexicale « complète » rêvée en avril
  (mais celle-ci est dangereuse et inutile aujourd'hui).
- **Coût** : faible (~1 module + tests + wiring normalizer).
- **Compatibilité** : conforme spec Codex, ADR-0019, principe « le natif tranche ».

### Option B — Filtre complet unidirectionnel DYU→BAM

- **Description** : coder DYU→BAM (phonologie + substitutions non-ambiguës) pour normaliser
  l'entrée ASR vers un « bambara canonique » avant NLU.
- **Avantages** : normalisation plus poussée de l'entrée.
- **Inconvénients** : réintroduit les substitutions lexicales ambiguës (sugu…) → risque de
  corruption ; recouvre partiellement le normalizer existant (dette de duplication).
- **Coût** : moyen.
- **Compatibilité** : ⚠️ tension avec la spec Codex sur les formes conditionnelles.

### Option C — Fermer #90 comme caduc

- **Description** : la motivation (exploiter bambara Mali brut) ayant disparu et les
  substitutions étant gérées ailleurs, fermer #90 sans coder.
- **Avantages** : zéro code, zéro risque.
- **Inconvénients** : abandonne le gain réel des règles phonologiques pour le matching ASR.
- **Coût** : nul.
- **Compatibilité** : ok mais laisse un petit gain qualité ASR sur la table.

### Comparatif

| Critère | A (phono seule) | B (DYU→BAM complet) | C (fermer) |
|---|---|---|---|
| Sûr (pas de corruption sémantique) | ✅ | ⚠️ | ✅ |
| Utile (gain qualité ASR/NLU) | ✅ | ✅ | ❌ |
| Compatible spec Codex / natif tranche | ✅ | ⚠️ | ✅ |
| Duplication avec l'existant | non | partielle | — |
| Coût | faible | moyen | nul |

## Décision

**Option retenue** : **A — Filtre phonologique seul, au service du normalizer**
(validée par Ruben le 2026-08-05).

**Justification** : c'est le seul périmètre de #90 à la fois **sûr** (les règles
phonologiques sont déterministes et réversibles, sans dépendance au sens) et **encore
utile** aujourd'hui (améliorer le matching ASR→NLU quand les modèles bambara sortent des
formes maliennes). Il respecte la décision de garder la spec Codex : les substitutions
lexicales restent **conditionnelles au sens** dans `prevalidation_rules.py`, jamais dans
un filtre aveugle. Il évite le code mort (Option B recouvre le normalizer ; la conversion
des datasets bruts est caduque).

## Conséquences

- **Positives** : gain de robustesse ASR→NLU sans risque de corruption ; #90 traité de
  façon réaliste ; cohérence avec ADR-0019/spec Codex.
- **Négatives assumées** : la « conversion lexicale/grammaticale complète » de #90 n'est
  PAS implémentée (délibérément — dangereuse et inutile). #90 sera fermé avec ce périmètre
  réduit documenté.
- **Migration / travail induit** :
  1. `app/services/language/__init__.py` + `bam_dyu_phonology.py` : 5 règles phonologiques
     (gw↔g devant ɛ, l↔d initial, l↔j initial, r↔l intervocalique, nin↔len résultatif) sous
     forme de `variants(word) -> set[str]` réversibles.
  2. Wiring dans `asr_normalizer.py` : après le fuzzy-matching existant, tenter les variantes
     phonologiques comme candidats supplémentaires (sans réécrire le texte final).
  3. Tests : ≥90 % sur 50 paires phonologiques connues (critère SYNTHESE) + non-régression
     sur les 15 cultures ASR qui marchent.
  4. Fermer #90 avec le périmètre réduit documenté (renvoi à cet ADR).
  - **Rollback** : le module est additif ; le retirer du normalizer suffit.
- **Verrous futurs** : si un vrai besoin de conversion lexicale automatique émerge, il devra
  passer par la validation native (jamais de substitution aveugle sur `sugu`/`kosɛbɛ`…).

## Références

- Issue #90 (filtre BAM↔DYU) ; SYNTHESE §2.6/§4 ; GRAMMAIRE_DIOULA_REGLES.md §12bis
- `scripts/prevalidation_rules.py` (substitutions conditionnelles, ADR-0019)
- `app/services/asr_normalizer.py` (normalizer post-ASR existant)
- Constat runtime : datasets bambara Mali non utilisés (`git grep` app/)
- ADR-0019 (feedback = signal ; principe « le natif tranche »)

## Historique

- 2026-08-05 — rédaction initiale (statut proposé), après questions stratégiques à Ruben.
  Décision Option A (périmètre phonologique) en attente de validation.
- 2026-08-05 — **accepté** par Ruben (« je valide »). Passage en Phase 5 (implémentation).
- 2026-08-05 — **implémenté** : `app/services/language/bam_dyu_phonology.py`
  (5 règles, `phonological_variants` / `variants_for_text`) + wiring dans
  `asr_normalizer._fuzzy_correct_word` (étape variantes phonologiques avant le
  fuzzy). Tests : `tests/unit/test_bam_dyu_phonology.py` (116 tests, 50 paires,
  taux 100 % ≥ critère 90 %). Non-régression : suite complète 1065 passed / 1 skip
  (les 2 erreurs restantes = tests d'intégration Postgres, hors périmètre, skippés
  en CI). Limite documentée : voisinage `wolo`/`woro` inerte (early-return vocab).
