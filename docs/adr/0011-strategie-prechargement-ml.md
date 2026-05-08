# ADR-0011 — Stratégie de préchargement des modèles ML

**Statut** : accepté
**Date** : 2026-05-08
**Auteur** : Claude (sous direction Ruben)
**Valideur** : Ruben (validé le 2026-05-08)

---

## Contexte

### Origine

Le 2026-05-07, le démarrage de `wouri-api` a échoué partiellement sur la
machine de Ruben : `Faster-Whisper large-v3-turbo` n'a pas pu se charger
(`mkl_malloc: failed to allocate memory`), et ChromaDB a échoué simultanément
(`os error 1455 = ERROR_COMMITMENT_LIMIT`). Conséquence visible : tous les
vocaux français renvoyaient `500 Internal Server Error`.

### Audit Phase 0 réalisé (2026-05-08)

Voir [docs/audits/preload-2026-05.md](../audits/preload-2026-05.md) pour le
détail complet. Synthèse :

- 7 modèles ML chargés au démarrage par [`app/main.py`](../../app/main.py)
  lifespan (NLU, NeMo Soloni, NLLB-200, TTS Bambara, TTS Dioula, Whisper,
  ChromaDB+MiniLM).
- **Mesures `psutil` réelles** via [`tools/profile_preload.py`](../../tools/profile_preload.py) :
  - Total RSS cumulé : **3.3 GB**
  - Total VMS cumulé : **7.0 GB** (RSS×2.1, indique une pression page file)
  - Mémoire système consommée : 2.7 GB (process Python + dépendances)
  - Durée totale boot : 56 s
- **3 modèles contournent `ModelRegistry`** : Whisper (cache global non
  thread-safe), NLLB (cache instance non thread-safe), ChromaDB+MiniLM
  (cache global, MiniLM couplé à `embedding_functions` Chroma).
- **Plus gros consommateurs RSS** : NeMo (1.2 GB), NLLB (1.0 GB), Whisper
  (0.8 GB).
- **Plus gros consommateur VMS** : NLLB (3.4 GB) — gain potentiel énorme si
  lazy-load.

### Profil utilisateur cible (rappel mémoire projet)

Cas d'usage prioritaire : agriculteurs dioula (Côte d'Ivoire, Mali) souvent
peu alphabétisés. Modes utilisateur : `dioula` et `both` largement
majoritaires, `french` minoritaire. Whisper FR sert donc le profil minoritaire.
NLLB sert d'appoint au dictionnaire (couvert à 90% par 15779 mots BAM→FR
existants).

### Pourquoi décider maintenant

1. **Crash bloquant observé** en environnement de test (les vocaux FR sont
   inutilisables tant que la pression mémoire externe est élevée).
2. **Infrastructure cible existe partiellement** : `ModelRegistry` est
   thread-safe, supporte `unload()` et est déjà utilisé par 3 modèles. Pas
   besoin d'inventer.
3. **Impact ADR-0008 connu et borné** : la migration ChromaDB → pgvector
   sortira la lib ChromaDB de l'équation (~50-100 MB libérés en Phase E),
   mais MiniLM reste durable. Cet ADR-0011 peut donc être livré sans attendre.
4. **Dette de double-chargement potentielle** : sans lock, deux requêtes
   concurrentes peuvent tenter de charger Whisper en même temps → ×2 mémoire
   momentanée. Risque non actualisé aujourd'hui mais latent.

### Ce que ce plan PRODUIT

Un ADR qui :
1. Fixe la stratégie cible de préchargement (eager / lazy par modèle)
2. Cadre le périmètre de refactor (modèles à migrer vers `ModelRegistry`)
3. Définit des métriques de succès chiffrées et mesurables
4. Référence les ADRs liés (ADR-0008 sur ChromaDB, ADR-0002 sur Omnilingual)

L'implémentation effective fera l'objet de Phases 2-5 distinctes (cf. § Plan
d'exécution).

---

## Questions tranchées avant la décision

1. **Le `ModelRegistry` existant est-il une infrastructure suffisante ?**
   → **Oui** ([`app/services/model_registry.py`](../../app/services/model_registry.py)).
   Lock par clé, `unload()` disponible, thread-safe, déjà utilisé par
   `nemo_soloni`, `tts_bambara`, `tts_dioula`. Pas besoin de réécrire.

2. **Le profil utilisateur dominant justifie-t-il le lazy-load Whisper ?**
   → **Oui**. Mode `french` minoritaire, le coût d'attente sur le 1er vocal
   FR (~30-60s) est acceptable face au gain (842 MB RSS / 821 MB VMS au boot).

3. **Le dictionnaire couvre-t-il assez d'usages pour justifier le lazy-load NLLB ?**
   → **Oui**. 15779 mots BAM→FR + 22010 FR→BAM couvrent ≈ 90% des usages
   typiques selon les retours projet. NLLB n'est qu'un fallback rare.

4. **Faut-il modifier le modèle MiniLM (couplé Chroma) dans cet ADR ?**
   → **Non, hors scope.** Couvert par [ADR-0008](0008-plan-migration-chromadb-pgvector.md)
   Phase C (instanciation `SentenceTransformer` directe dans `corpus_service.py`).

5. **Faut-il quantizer NLLB en fp16/int8 dans cet ADR ?**
   → **Non, hors scope.** Bénéfice estimé ~500 MB RSS, mais nécessite un
   benchmark qualité (BLEU sur traductions agricoles) qui mérite un ADR
   séparé. Le lazy-load apporte déjà l'essentiel du gain.

6. **Faut-il réduire la taille de Whisper (large → medium) ?**
   → **Non.** La qualité française est critique pour les utilisateurs
   francophones. Le lazy-load résout le problème mémoire sans dégrader la
   qualité.

7. **Faut-il un mécanisme `unload-on-idle` (TTL) ?**
   → **Pas dans cette première itération.** Complexité++ (scheduler, race
   conditions, métriques). Reportable à un ADR suivant si pression mémoire
   continue après livraison de l'option retenue (cf. § Hors scope).

---

## Options étudiées

### Option A — Statu quo (rejetée)

- **Description** : conserver le préchargement eager de tous les modèles dans
  `app/main.py` lifespan.
- **Avantages** : 0 latence sur la 1re requête de chaque endpoint, validation
  au boot que tous les modèles sont chargeables.
- **Inconvénients** :
  - Crash mémoire reproductible sous pression externe (Chrome + autres apps).
  - 3.3 GB RSS / 7.0 GB VMS chargés en permanence, même si l'utilisateur
    n'utilise jamais Whisper ou NLLB hors-dictionnaire.
  - Boot de 56 s.
- **Coût** : 0 dev, mais **bug bloquant connu** non résolu.
- **Compatibilité contraintes** : ne respecte pas l'objectif de robustesse en
  environnement local de dev.

### Option B — Lazy-load total (rejetée)

- **Description** : tous les modèles lazy, aucun preload au boot.
- **Avantages** : boot quasi-instantané (< 5 s), empreinte mémoire minimale au
  démarrage.
- **Inconvénients** :
  - **NeMo Soloni est utilisé sur quasiment toutes les requêtes** (cas
    d'usage principal dioula). Le 1er vocal après chaque démarrage attendrait
    26 s — UX dégradée pour l'usage **dominant**.
  - TTS Bambara/Dioula sont quasi-gratuits (+3 MB RSS chacun) après NeMo —
    les deprécharger n'apporte presque rien et ajoute de la latence.
  - Pas de validation au boot que les modèles critiques sont disponibles.
- **Coût** : refactor moyen.
- **Compatibilité contraintes** : casse l'UX du cas d'usage principal.

### Option C — Lazy ciblé NLLB + Whisper (RETENUE)

- **Description** : preload eager de **NeMo + TTS Bambara + TTS Dioula**
  (modèles utilisés par le cas d'usage principal). Lazy-load de **NLLB** et
  **Whisper** (modèles utilisés par cas secondaires/rares).
- **Avantages** :
  - Économie boot : **-1828 MB RSS / -4177 MB VMS** (lazy NLLB + Whisper)
  - Boot post-optimisation : ~ 1.5 GB RSS / ~ 2.8 GB VMS pour profil dioula
    uniquement (vs 3.3 GB / 7.0 GB actuel)
  - Boot < 30 s (vs 56 s actuel)
  - Conserve l'UX optimale pour le cas d'usage dominant (vocaux dioula
    instantanés)
  - Migration vers `ModelRegistry` apporte gratuitement : lock thread-safe
    (anti double-chargement), `unload()` disponible pour le futur
- **Inconvénients (assumés)** :
  - **1er vocal FR par démarrage** : latence 30-60 s (chargement Whisper).
    Mitigation : timeout WhatsApp côté Baileys = 180 s, marge confortable.
  - **1re traduction NLLB hors-dictionnaire** : latence 5-15 s. Cas rare
    (90% couvert par dictionnaire).
  - Pas de validation au boot que Whisper et NLLB sont chargeables. Mitigation :
    test au démarrage en mode dégradé (cf. § Plan d'exécution).
- **Coût** : refactor moyen (~ 200-300 lignes modifiées sur 4 fichiers).
- **Compatibilité contraintes** : respecte le profil utilisateur dominant +
  rétablit la robustesse mémoire.

### Option D — Option C + Unload-on-idle (TTL) (différée)

- **Description** : Option C, plus un mécanisme de déchargement automatique
  d'un modèle inactif depuis N minutes (ex: 30 min), implémenté dans
  `ModelRegistry`.
- **Avantages** :
  - Mémoire dynamiquement libérée pendant les périodes creuses
  - Bénéfice fort si pression mémoire externe continue (Chrome, autres apps)
- **Inconvénients** :
  - Complexité++ : scheduler async, locks pour gérer un appel pendant un
    unload en cours, métriques pour détecter un thrashing (load/unload répété)
  - Bénéfice incertain en pratique : si le modèle est rechargé peu après,
    coûte plus que ne fait gagner
  - Tests difficiles (timing-dependent)
- **Coût** : élevé.
- **Décision** : **différée**. Si l'Option C ne suffit pas en pratique
  (pression mémoire externe persistante après livraison), un ADR de suivi
  pourra ajouter ce comportement à `ModelRegistry`.

### Comparatif

| Critère | A (statu quo) | B (lazy total) | C (lazy ciblé) | D (C + TTL) |
|---|---|---|---|---|
| Boot RSS | 3.3 GB ❌ | ~ 0.5 GB ✅ | ~ 1.5 GB ✅ | ~ 1.5 GB ✅ |
| Boot VMS | 7.0 GB ❌ | ~ 1 GB ✅ | ~ 2.8 GB ✅ | ~ 2.8 GB ✅ |
| Durée boot | 56 s ❌ | < 5 s ✅ | < 30 s ✅ | < 30 s ✅ |
| UX 1er vocal dioula | instantané ✅ | 26 s ❌ | instantané ✅ | instantané ✅ |
| UX 1er vocal FR | instantané ✅ | 30-60 s ⚠️ | 30-60 s ⚠️ | 30-60 s ⚠️ |
| Robustesse pression mémoire | ❌ | ✅ | ✅ | ✅✅ |
| Complexité dev | 0 | moyenne | moyenne | élevée |
| Risque régression | 0 | élevé | faible | moyen |

---

## Décision

**Option retenue : C — Lazy ciblé NLLB + Whisper**, avec **migration préalable**
de Whisper et NLLB vers `ModelRegistry`.

**Justification** :
1. Résout le crash mémoire observé sans dégrader l'UX du cas d'usage dominant
   (vocaux dioula instantanés grâce au preload eager de NeMo + TTS).
2. Économie chiffrée significative : -1828 MB RSS / -4177 MB VMS au boot.
   Le gain VMS est particulièrement critique pour la pression page file
   Windows.
3. Rétablit l'uniformité d'infrastructure (tous les modèles via
   `ModelRegistry`), ouvrant la porte à des optimisations futures (Option D
   TTL, métriques observabilité) sans nouveau refactor.
4. Respecte les ADRs existants (pas de conflit avec ADR-0002, ADR-0008).
5. Trade-off assumé : 30-60 s sur le 1er vocal FR par démarrage. Mitigé par
   le timeout côté WhatsApp Baileys (180 s) et la rareté du cas (mode
   `french` minoritaire).

L'**Option D** reste évaluable dans un ADR de suivi si les chiffres post-livraison
montrent que C ne suffit pas.

---

## Métriques de succès

À mesurer post-implémentation via [`tools/profile_preload.py`](../../tools/profile_preload.py)
(profil utilisateur dioula uniquement, sans Whisper ni NLLB chargés) :

| Métrique | Cible | Méthode |
|---|---|---|
| **RSS boot** | ≤ **1.6 GB** | `psutil.Process().memory_info().rss` après lifespan |
| **VMS boot** | ≤ **3.0 GB** | `psutil.Process().memory_info().vms` |
| **Durée boot** | ≤ **30 s** | timestamp `lifespan` start → end |
| **Mémoire système disponible post-boot** | ≥ **3.0 GB** | `psutil.virtual_memory().available` |
| **Latence p95 1er vocal FR** | ≤ **60 s** | logs `/api/stt/transcribe` premier appel |
| **Latence p95 1re trad NLLB** | ≤ **15 s** | logs `[NLLB]` premier appel |
| **Latence p95 1er vocal dioula** | ≤ **5 s** | logs `/api/asr/transcribe` premier appel (preload eager attendu) |
| **0 régression** sur endpoints existants | passing | smoke tests + tests d'intégration existants |

Échec d'une cible → diagnostic + soit ajustement implémentation, soit
réévaluation Option D.

---

## Conséquences

### Positives

- **Robustesse boot** : plus de crash `mkl_malloc` même sous pression mémoire
  externe modérée
- **Démarrage 47% plus rapide** (56 s → ≤ 30 s)
- **Empreinte mémoire boot 55% plus légère** en RSS (3.3 GB → ≤ 1.6 GB)
- **Empreinte VMS boot 60% plus légère** (7.0 GB → ≤ 3.0 GB) — soulage la
  pression page file
- **Anti double-chargement** sur Whisper et NLLB (lock par clé via
  `ModelRegistry`)
- **Possibilité d'unload** disponible (préparation Option D future)
- **Logs uniformes** `[Registry]` pour tous les modèles (simplifie
  l'observabilité Phase 4)

### Négatives assumées

- **1re vocal FR par démarrage** : latence 30-60 s. Acceptable car cas
  d'usage minoritaire et timeout WhatsApp 180 s.
- **1re trad NLLB hors-dictionnaire** : latence 5-15 s. Acceptable car cas
  rare (dictionnaire couvre 90%).
- **Pas de validation au boot** que Whisper et NLLB peuvent se charger.
  Mitigation : ajout d'un endpoint `/admin/preload-check` (Phase 4) qui
  permet de tester manuellement le chargement de chaque modèle lazy.
- **Risque double-chargement déplacé** : sur la 1re requête concurrente, deux
  threads peuvent entrer la branche "non chargé" — mais résolu par le lock
  par clé du `ModelRegistry` (gratuit avec la migration).

### Migration / travail induit

**Phase 2 — Refactor uniformisation** (~ 200-300 lignes)
- [`app/services/stt_whisper.py`](../../app/services/stt_whisper.py) : `_whisper_model` global → `registry.get("whisper", loader=_load)`. Suppression du gate `_load_failed` (le Registry gère).
- [`app/services/translation/nllb_translator.py`](../../app/services/translation/nllb_translator.py) : `self._model` / `self._tokenizer` → `registry.get("nllb_model", ...)`. Conserver le gate `_load_failed` interne (utile pour tagger un échec persistant et éviter les retries inutiles dans le translate fallback).

**Phase 3 — Application stratégie**
- [`app/main.py`](../../app/main.py) : suppression des blocs `# 4. Précharger Whisper` (lignes 97-104) et `# 2. Précharger NLLB` (l'appel `service.preload_nllb()` ligne 75). Conservation de TranslationService init (dictionnaire) et de tout le reste.

**Phase 4 — Observabilité**
- `/health` enrichi : retourne pour chaque modèle `loaded: bool` + `rss_mb: float`
- Optionnel : endpoint admin `/admin/preload-check` pour test manuel des modèles lazy

**Phase 5 — Tests**
- Tests unitaires : `tests/integration/test_lazy_loading.py` (1er appel après boot fonctionne, lock concurrent OK)
- Smoke tests : tous endpoints existants doivent passer
- Test de profil : `tools/profile_preload.py --skip whisper,nllb` doit montrer RSS ≤ 1.6 GB

**Documentation**
- Mise à jour `app/main.py` docstring
- Mise à jour `MEMORY.md` (section "Décisions architecturales gravées")
- Mise à jour `docs/adr/README.md` index

### Verrous futurs

- **Aucun majeur**. Le `ModelRegistry` permet un retour facile :
  - Lazy → eager : ajout d'un appel `registry.get(...)` au boot de `lifespan`
  - Eager → lazy : suppression de l'appel boot
- **Préparation pour Option D (TTL unload)** : la migration vers Registry est
  un prérequis acquis. L'ajout d'un mécanisme TTL ne nécessitera plus de
  refactor des services.
- **Préparation pour ADR-0008** : MiniLM sera naturellement isolé en Phase C
  d'ADR-0008 et pourra rejoindre le Registry à ce moment-là.

---

## Plan d'exécution

| Phase | Périmètre | Livrable | Critère PASS |
|---|---|---|---|
| **2** | Refactor uniformisation Whisper + NLLB → `ModelRegistry` | Code modifié, tests existants passent | Smoke test serveur, 0 régression |
| **3** | Suppression preload Whisper + NLLB du lifespan | `main.py` modifié | RSS boot ≤ 1.6 GB mesuré, vocal FR fonctionne après attente |
| **4** | Observabilité `/health` enrichi | Champ `models` détaillé dans réponse `/health` | Réponse JSON conforme au schéma documenté |
| **5** | Tests + validation manuelle | Tests d'intégration + checklist | Toutes métriques de succès atteintes |

**Granularité** : chaque phase = 1 PR distincte (revue isolée), ordre strict.

**Plan de rollback** : `git revert` du commit Phase 3 restore le preload eager.
Pas de migration de données ni d'état. Rollback < 5 min.

---

## Hors scope

- **MiniLM (paraphrase-multilingual-MiniLM-L12-v2)** : couvert par
  [ADR-0008](0008-plan-migration-chromadb-pgvector.md) Phase C
  (instanciation directe dans `corpus_service.py`). Hérite naturellement du
  `ModelRegistry` à ce moment-là. Pas d'effort prématuré.
- **ChromaDB lib** : transitoire selon ADR-0008 Phase E. Pas de migration vers
  Registry.
- **Quantization NLLB (fp16 / int8)** : ADR séparé futur si besoin (gain
  estimé ~500 MB RSS, nécessite benchmark qualité BLEU).
- **Réduction Whisper (large → medium)** : rejeté (qualité française critique).
- **Unload-on-idle (TTL)** : différé à un ADR de suivi si Option C ne suffit pas.
- **Modèles déjà lazy** : MMS Ivorian, MMS DYU, Omnilingual, TTS langues
  ivoiriennes — déjà via `ModelRegistry`, comportement de référence.
- **Omnilingual ASR (ADR-0002)** : sera ajouté à la chain ASR ; sa stratégie
  de préchargement suivra ADR-0011 (lazy par défaut, eager si confirmé en
  cas d'usage principal).

---

## Références

- [ADR-0001 — Choix stockage de données](0001-choix-stockage-donnees.md)
  (PostgreSQL + pgvector remplace ChromaDB)
- [ADR-0002 — Ajout provider Omnilingual ASR](0002-ajout-provider-omnilingual.md)
- [ADR-0008 — Plan migration ChromaDB → pgvector](0008-plan-migration-chromadb-pgvector.md)
- [Audit Phase 0 préchargement](../audits/preload-2026-05.md)
- Mesures `psutil` réelles : [`profile_preload_2026-05-08.json`](../audits/profile_preload_2026-05-08.json)
- Code clé :
  - [`app/main.py`](../../app/main.py) — lifespan startup
  - [`app/services/model_registry.py`](../../app/services/model_registry.py) — infrastructure cible
  - [`app/services/stt_whisper.py`](../../app/services/stt_whisper.py) — Whisper à migrer
  - [`app/services/translation/nllb_translator.py`](../../app/services/translation/nllb_translator.py) — NLLB à migrer
- Profil utilisateur : `MEMORY.md` (modes dioula/both majoritaires)

---

## Historique

- **2026-05-08 (rédaction)** — Rédaction initiale. Statut : **proposé**, attend
  validation Ruben. Basé sur l'audit Phase 0 livré le même jour avec mesures
  `psutil` réelles. Décision Option C (lazy ciblé NLLB + Whisper) retenue
  après comparatif chiffré des 4 options.
- **2026-05-08 (acceptation)** — Ruben valide l'ADR. Statut basculé à **accepté**.
  Phase 2 (refactor uniformisation Whisper + NLLB → `ModelRegistry`) peut
  démarrer. Phases 3-5 enchaînées dans des PR distinctes.
