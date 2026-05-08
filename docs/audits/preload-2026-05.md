# Audit — Préchargement des modèles ML (Phase 0)

**Statut** : draft (Phase 0 du plan de révision préchargement)
**Auteur** : Claude (sous direction Ruben)
**Déclencheur** : crash mémoire observé 2026-05-07 lors du démarrage de l'API
**Dernière révision** : 2026-05-08 (mesures `psutil` réelles 7/7 modèles + clarification scope ADR-0008)
**Suite attendue** : ADR-0011 "Stratégie de préchargement des modèles ML" basé sur cet audit

---

## 1. Contexte

### 1.1 Crash observé
Logs `wouri-api` du 2026-05-07 : `Faster-Whisper large-v3-turbo` n'a pas pu se charger
au démarrage (`mkl_malloc: failed to allocate memory`), entraînant systématiquement
un `500 Internal Server Error` sur `/api/stt/transcribe` (toute requête vocale FR).
ChromaDB a échoué simultanément (`os error 1455 = ERROR_COMMITMENT_LIMIT`,
fichier de pagination Windows insuffisant). Fallback JSON corpus IVR actif.

### 1.2 Mesure machine au moment du crash
| Métrique | Valeur |
|---|---|
| RAM physique totale | 15.79 GB |
| RAM libre au moment de l'incident | 1.14 GB (≈ 93% saturée) |
| Mémoire virtuelle totale (RAM + page file) | 39.79 GB |
| Mémoire virtuelle libre | **0.46 GB** ← cause directe du `mkl_malloc` |
| Page file alloué | 24 GB |
| Page file utilisé courant / pic | 15.6 GB / 17.5 GB |

Source : `Get-CimInstance Win32_OperatingSystem` + `Win32_PageFileUsage` exécutés
le 2026-05-07 sur le poste de Ruben en parallèle de l'API.

### 1.3 Profil utilisateur cible (rappel mémoire projet)
Cas d'usage prioritaire : **agriculteurs dioula** (Côte d'Ivoire, Mali) souvent
peu alphabétisés. Modes utilisateur observés : `dioula` et `both` largement
majoritaires, `french` minoritaire. Source : `MEMORY.md` + règle UX
"selon langue choisie" PR #123.

---

## 2. Méthodologie

L'audit s'appuie sur :
- **Lecture du code** : tous les services `wouri-api/app/services/` qui chargent
  des modèles ML (greppé sur `from_pretrained`, `WhisperModel`, `EncDec*`,
  `VitsModel`, `nemo`, `registry.get`).
- **Logs d'exécution** : `wouri-api` au démarrage 2026-05-07 (timestamps depuis
  `lifespan` startup phase).
- **Mesures `psutil` réelles** (révision 2026-05-08) : script
  [`tools/profile_preload.py`](../../tools/profile_preload.py) exécuté
  successfully (7/7 modèles chargés). Résultats bruts dans
  [`profile_preload_2026-05-08.json`](profile_preload_2026-05-08.json).
- **Analyse des callers** : grep sur les usages de chaque service pour mesurer
  qui appelle quoi.

---

## 3. Inventaire des modèles ML chargés au démarrage

Ordre exact dans [`app/main.py:34-122`](../../app/main.py) (lifespan startup) :

**Mesures réelles (psutil, 2026-05-08, 7/7 modèles chargés sans crash)** :

| # | Étape | Modèle / Service | Δ RSS (MB) | Δ VMS (MB) | Durée (s) | Via `ModelRegistry` ? | Statut cycle de vie |
|---|---|---|---:|---:|---:|---|---|
| 0 | NLU | NLU JSON (concepts bambara) | **+0.7** | +1.2 | 0.02 | N/A (JSON) | Durable |
| 1 | ASR bambara | NeMo Soloni 114M (RNN-T + CTC) | **+1185.5** | +1754.1 | 26.13 | ✅ Oui (`nemo_soloni`) | Durable |
| 2 | Traduction | NLLB-200 distilled 600M | **+1007.1** | +3355.7 | 11.81 | ❌ **Non** (cache instance `self._model`) | Durable |
| 3 | TTS bambara | mms-tts-bam (VITS) | **+3.4** | +140.1 | 0.53 | ✅ Oui (`tts_bambara`) | Durable |
| 4 | TTS dioula | mms-tts-dyu (VITS) | **+3.1** | +140.8 | 2.50 | ✅ Oui (`tts_dioula`) | Durable |
| 5 | STT français | Faster-Whisper large-v3-turbo (int8) | **+821.7** | +821.2 | 11.95 | ❌ **Non** (global `_whisper_model`) | Durable |
| 6a + 6b | RAG (lib + embedding) | `chromadb.PersistentClient` + `paraphrase-multilingual-MiniLM-L12-v2` | **+295.6** | +743.6 | 3.28 | ❌ **Non** | 6a transitoire (ADR-0008 Phase E) / 6b durable |

**Sources** :
- Fichier de service : [`services/nlu/nlu_service.py`](../../app/services/nlu/nlu_service.py),
  [`asr_soloni_nemo.py`](../../app/services/asr_soloni_nemo.py),
  [`translation/nllb_translator.py`](../../app/services/translation/nllb_translator.py),
  [`tts_bambara.py`](../../app/services/tts_bambara.py),
  [`tts_dioula.py`](../../app/services/tts_dioula.py),
  [`stt_whisper.py`](../../app/services/stt_whisper.py),
  [`vdb_service.py`](../../app/services/vdb_service.py).
- Mesures : [`profile_preload_2026-05-08.json`](profile_preload_2026-05-08.json).

**Totaux mesurés (2026-05-08)** :
- **RSS cumulé après tous les chargements** : **3317 MB** (process Python ≈ 3339 MB total, baseline 22 MB)
- **VMS cumulé** : **6957 MB** (process Python ≈ 6970 MB total) — RSS × 2.1, indique
  un volume important de pages mappées mais non résidentes (page file actif)
- **Mémoire système consommée** : 2666 MB (3984 → 1318 MB libre)
- **Mémoire système disponible finale** : 1318 MB sur 16166 MB total

### 3.A Surprises vs estimations initiales

| Modèle | Estimation initiale | Mesure réelle (RSS) | Écart |
|---|---|---|---|
| NeMo Soloni | ~ 500 MB | **1185 MB** | **2.4× plus lourd** ❗ |
| NLLB-200 distilled | ~ 2400 MB | 1007 MB RSS / **3356 MB VMS** | RSS 2.4× plus léger, mais VMS énorme |
| TTS Bambara | ~ 140-200 MB | **+3 MB RSS** / +140 MB VMS | RSS quasi nul (libs partagées avec NeMo) |
| TTS Dioula | ~ 140-200 MB | **+3 MB RSS** / +140 MB VMS | Idem |
| Whisper int8 | ~ 800-1000 MB | 822 MB | conforme |
| ChromaDB + MiniLM | ~ 470 MB | 296 MB | un peu plus léger |

**Constats clés** :
1. **NeMo est le plus gros consommateur en RSS** (1.2 GB), pas NLLB. NeMo charge tout
   l'écosystème PyTorch + decoder beam + tokenizer + RNN-T loss → bien plus lourd
   que le poids brut du modèle (114M params).
2. **NLLB a un VMS énorme (3.3 GB) mais un RSS modéré (1 GB)** : le modèle est
   largement mappé mais paresseusement résident. À l'usage (génération de texte),
   plus de pages deviennent résidentes → pic de RSS attendu.
3. **TTS Bambara et Dioula sont quasi-gratuits** une fois NeMo chargé (libs torch
   partagées). Les déprioriser n'apporterait quasi rien.
4. **Whisper conforme à l'estimation** (~822 MB).

### 3.1 Modèles NON préchargés (lazy à la demande, déjà OK)

| Modèle | Service | Trigger lazy |
|---|---|---|
| MMS Ivorian (par langue ivoirienne) | [`services/asr/mms_generic_provider.py`](../../app/services/asr/mms_generic_provider.py) | `registry.get("mms_ivorian")` |
| MMS DYU adapter | [`services/asr/mms_dyu_provider.py`](../../app/services/asr/mms_dyu_provider.py) | `registry.get("mms_dyu")` |
| Omnilingual ASR (Meta, ADR-0002) | [`services/asr/omnilingual_provider.py`](../../app/services/asr/omnilingual_provider.py) | `registry.get(<key>)` |
| TTS Ivorian par langue (Attié, Sénoufo, etc.) | [`services/tts_ivoirian.py`](../../app/services/tts_ivoirian.py) | `registry.get(<key>)` |

Ces modèles ne sont chargés que lorsqu'un endpoint spécifique les sollicite,
et passent tous par `ModelRegistry`. **Comportement de référence**.

---

## 4. Cartographie `ModelRegistry`

### 4.1 Modèles qui passent par le registry (uniformes)
- `nemo_soloni` ([`asr_soloni_nemo.py:78`](../../app/services/asr_soloni_nemo.py))
- `tts_bambara` ([`tts_bambara.py:75`](../../app/services/tts_bambara.py))
- `tts_dioula` ([`tts_dioula.py:60`](../../app/services/tts_dioula.py))
- `mms_dyu`, `mms_ivorian`, langues ivoiriennes individuelles, omnilingual

**Bénéfices acquis** :
- Lock thread-safe par clé (anti double-chargement)
- Possibilité d'`unload()` pour libérer la RAM
- Cache cohérent unique
- Logs uniformes `[Registry] Chargement…` / `[Registry] Modele chargé`

### 4.2 Modèles qui contournent `ModelRegistry` (non-uniformes)

#### a) Whisper — `stt_whisper.py:99-131`
```python
_whisper_model = None  # cache global
def get_whisper_model(model_name: str = None):
    global _whisper_model, _model_name
    if _whisper_model is None:
        ...
        _whisper_model = WhisperModel(_model_name, device="cpu",
                                       compute_type="int8", cpu_threads=4,
                                       num_workers=1)
    return _whisper_model
```
**Problèmes** :
- Pas de lock → 2 requêtes vocales FR concurrentes peuvent toutes deux entrer
  la branche `is None` et tenter un double chargement (≈ 2 GB momentané au
  lieu de 1).
- Pas d'`unload` possible → impossible de libérer la RAM en cas de pression.
- Échec silencieux : si le chargement plante (mémoire), l'exception est
  propagée mais la variable globale reste `None`, donc chaque appel suivant
  retentera et échouera à nouveau (boucle d'échec coûteuse vu dans les logs).

#### b) NLLB — `translation/nllb_translator.py:31-53`
```python
def _ensure_loaded(self):
    if self._model is not None:
        return True
    if self._load_failed:
        return False  # gate anti-OOM répété ✅
    ...
    self._tokenizer = AutoTokenizer.from_pretrained(settings.hf_translator_model)
    self._model = AutoModelForSeq2SeqLM.from_pretrained(settings.hf_translator_model)
```
**État** :
- A déjà un gate `_load_failed` pour éviter de retenter à l'infini → mieux que Whisper.
- Mais pas de lock thread-safe.
- Pas d'`unload` possible.
- Cache attaché à l'instance singleton `TranslationService`, pas centralisé.

#### c) ChromaDB + MiniLM — `vdb_service.py:40, 63-128`
```python
_chroma_collection = None
_corpus_cache: dict | None = None
```
**État** :
- Cache global, pas de lock.
- Pas d'`unload` possible.
- En cas d'échec mémoire, fallback JSON activé via `corpus_cache` (résilient,
  observé dans les logs 2026-05-07).

**Couplage MiniLM ⇄ ChromaDB** : MiniLM est instancié à
[`vdb_service.py:80`](../../app/services/vdb_service.py) via
`embedding_functions.SentenceTransformerEmbeddingFunction(model_name=...)` qui
wrappe un `SentenceTransformer` à l'intérieur de l'objet `EmbeddingFunction`
ChromaDB. Le modèle est donc **détenu par la collection Chroma**, pas
exposé directement.

**Implication pour l'ADR-0011 à venir** :
- `chromadb.PersistentClient` est marqué **transitoire** par
  [ADR-0008](../adr/0008-plan-migration-chromadb-pgvector.md) (suppression en
  Phase E). Pas d'effort à investir pour le faire passer par `ModelRegistry`.
- MiniLM est **durable** (ADR-0008 Q3 acte que le modèle d'embedding ne change
  pas dans la migration), mais il sera **naturellement extrait** quand
  ADR-0008 Phase C livrera `corpus_service.py` qui instanciera
  `SentenceTransformer` directement (sans passer par l'API ChromaDB).
- **Décision implicite pour ADR-0011** : on n'isole **pas** MiniLM
  prématurément ; on hérite du gain quand ADR-0008 sera exécuté. Cette dette
  est traçable et bornée.

---

## 5. Latence de chargement

### 5.1 Mesures réelles (2026-05-08, 7/7 succès)

| Étape | Modèle | Durée |
|---|---|---:|
| 1 | NLU | 0.02 s |
| 2 | **NeMo Soloni** | **26.13 s** ← le plus long |
| 3 | NLLB-200 | 11.81 s |
| 4 | TTS Bambara | 0.53 s |
| 5 | TTS Dioula | 2.50 s |
| 6 | **Whisper** | **11.95 s** |
| 7 | ChromaDB + MiniLM | 3.28 s |

**Total temps de boot avant disponibilité de l'API : 56 secondes** (mesure
psutil 2026-05-08, machine sous pression ~12 GB de RAM autres apps actives).

### 5.2 Logs précédents (2026-05-07, machine plus saturée)

Lors du test précédent, Whisper et ChromaDB avaient crashé (mémoire) :
- NeMo : ≈ 21 s
- Whisper : crash `mkl_malloc`
- ChromaDB : crash `os error 1455`

→ **Confirmation** : la machine n'est pas intrinsèquement faible. La pression
mémoire externe (Chrome / autres apps) a fait basculer l'environnement
au-dessus du seuil VMS critique le 2026-05-07. Le 2026-05-08 (avec moins de
pression), tout charge.

---

## 6. Fréquence d'usage des endpoints (estimée)

Pas de logs prod historiques disponibles → **estimation qualitative** basée
sur l'analyse du flow WhatsApp (cf. [`whatsapp-server/CLAUDE.md`](../../../whatsapp-server/CLAUDE.md))
et le profil utilisateur cible.

| Endpoint | Modèles requis | Fréquence estimée | Justification |
|---|---|---|---|
| `/api/asr/transcribe-and-translate` | NeMo Soloni + dictionnaire (rare NLLB) | **Très élevée** | Cas usage principal : utilisateur dioula envoie un vocal |
| `/api/asr/transcribe` (vocal dioula) | NeMo Soloni | Élevée | Variante du précédent |
| `/api/chat/` | DeepSeek (cloud) + dictionnaire (rare NLLB) | **Très élevée** | Tous les messages texte / réponses agricoles |
| `/api/tts/bambara` | TTS Bambara/Dioula | **Très élevée** | Réponse audio dioula systématique en mode `dioula` / `both` |
| `/api/tts/french` | Edge-TTS (cloud, **pas de modèle local**) | Élevée | Mode `both` (combo audio dioula + texte FR) — voir PR #129 |
| `/api/stt/transcribe` (vocal FR) | Whisper | **Faible** | Mode `french` minoritaire |
| `/api/rag/search` | ChromaDB + MiniLM (ou fallback JSON) | Variable | Déclenché par chat_service quand pertinent |

**Constat clé** : Whisper, qui est le plus gros consommateur RAM hors NLLB,
sert le profil utilisateur **minoritaire**. NLLB sert toutes les langues mais
n'est invoqué qu'en fallback du dictionnaire (qui couvre déjà 15779 mots BAM→FR
+ 22010 mots FR→BAM, ≈ 90% des usages typiques).

---

## 7. Caches globaux qui contournent le registry — récap

| Variable globale | Fichier | Type | Lock ? | Unload possible ? | Cycle de vie |
|---|---|---|---|---|---|
| `_whisper_model` | `stt_whisper.py:100` | `WhisperModel \| None` | ❌ | ❌ | Durable → cible ADR-0011 |
| `_model_name` | `stt_whisper.py:101` | `str` | ❌ (mais immuable de fait) | ❌ | Durable |
| `NLLBTranslator._model` | `nllb_translator.py:18` | `AutoModelForSeq2SeqLM \| None` | ❌ | ❌ | Durable → cible ADR-0011 |
| `NLLBTranslator._tokenizer` | `nllb_translator.py:19` | `AutoTokenizer \| None` | ❌ | ❌ | Durable → cible ADR-0011 |
| `_chroma_collection` | `vdb_service.py:40` | `Collection \| None` | ❌ | ❌ | **Transitoire (ADR-0008 Phase E)** |
| `_corpus_cache` | `vdb_service.py:24` | `dict \| None` | ❌ | ❌ (mais petit, ~quelques MB) | Sera réutilisé par `corpus_service.py` |
| MiniLM `SentenceTransformer` (interne à `EmbeddingFunction`) | `vdb_service.py:80` | objet sentence-transformers | ❌ | ❌ | Durable, mais isolation **différée à ADR-0008 Phase C** |

---

## 8. Observabilité actuelle

| Mécanisme | État |
|---|---|
| Logs au chargement initial | ✅ Existent (`[PRELOAD]`) |
| Métriques RAM par modèle au runtime | ❌ Aucune |
| Endpoint d'inspection runtime des modèles chargés | Partiel : `/health` retourne `whisper_status.model_loaded` (bool) |
| Logs sur unload | ✅ Existent dans `ModelRegistry.unload()` (mais peu appelés) |
| Métriques de mémoire totale process Python | ❌ Aucune |
| Alerte sur threshold mémoire | ❌ Aucune |

---

## 9. Limites de cet audit

1. ~~**Tailles mémoire non profilées**~~ → **Levée 2026-05-08** : mesures `psutil`
   réelles capturées via [`tools/profile_preload.py`](../../tools/profile_preload.py).
2. **Pas de stats d'usage prod** : la fréquence des endpoints est estimée
   qualitativement. Un audit plus poussé nécessiterait des métriques temporelles
   (par exemple, comptage des appels par endpoint sur 7 jours via les logs
   FastAPI). Actuellement, on a uniquement les logs locaux des tests 2026-05-07
   et 2026-05-08.
3. ~~**Latences de chargement** : approximées~~ → **Levée 2026-05-08** : durées
   mesurées avec `time.perf_counter`.
4. **Modèles non encore intégrés** : Omnilingual ASR (ADR-0002) est codé mais
   pas activé dans la chain en production locale. Quand il le sera, ajoutera
   une charge supplémentaire (~1.5-2 GB selon variante choisie) à anticiper
   dans l'ADR-0011.
5. **Pic RSS pendant l'inférence non mesuré** : NLLB notamment a un VMS très
   supérieur à son RSS au boot — l'usage réel (génération de texte) peut faire
   monter le RSS de plusieurs centaines de MB. À profiler dans une session
   ultérieure si pertinent (mais l'ordre de grandeur des préchargements est
   suffisant pour l'ADR-0011).
6. **Mesure unique** : le profilage 2026-05-08 est un seul tir. Une variabilité
   ±10% est attendue selon l'état système. Suffisant pour les ordres de
   grandeur.

---

## 10. Synthèse — chiffres pour l'ADR-0011

### 10.1 Empreinte mémoire par modèle (mesures réelles 2026-05-08)
```
                                       Δ RSS      Δ VMS    Durée
NLU JSON                                +0.7 MB    +1 MB   0.02 s   [JSON]
NeMo Soloni 114M                     +1185.5 MB +1754 MB  26.13 s   [via Registry]
NLLB-200 distilled 600M              +1007.1 MB +3356 MB  11.81 s   [contourne Registry]
TTS Bambara (mms-tts-bam)               +3.4 MB  +140 MB   0.53 s   [via Registry]
TTS Dioula (mms-tts-dyu)                +3.1 MB  +141 MB   2.50 s   [via Registry]
Whisper large-v3-turbo int8           +821.7 MB  +821 MB  11.95 s   [contourne Registry]
ChromaDB + MiniLM-L12-v2              +295.6 MB  +744 MB   3.28 s   [contourne Registry]
                                     ─────────  ─────────
Total cumulé (RSS / VMS)              3317 MB   6957 MB
Process Python total après boot       3339 MB   6970 MB
Boot complet (incluant baseline)      ~3.3 GB RSS, ~7.0 GB VMS, 56 s
```

### 10.2 Charges critiques (utilisation effective × poids réel)
- **Toujours utilisés (gros poids)** : NeMo (1.2 GB) — vocaux dioula = cas usage principal
- **Toujours utilisés (gratuits une fois NeMo chargé)** : TTS Bambara + Dioula (+3 MB chacun en RSS)
- **Souvent utilisés** : NLLB (1 GB RSS / 3.3 GB VMS) — fallback dictionnaire
- **Parfois utilisés** : ChromaDB+MiniLM (296 MB), Whisper (822 MB)

### 10.3 Économies potentielles par scénario

**Scénario A — Lazy-load Whisper uniquement** (mode dioula/both majoritaire) :
- Économie boot : -822 MB RSS / -821 MB VMS
- Boot post-optimisation : ~ 2.5 GB RSS / ~ 6.1 GB VMS
- Coût : 30-60s sur le 1er vocal FR par démarrage (rare cas usage)

**Scénario B — Lazy-load Whisper + NLLB** (NLLB est rarement déclenché) :
- Économie boot : -1828 MB RSS / **-4177 MB VMS** ← gain énorme sur la pression page file
- Boot post-optimisation : ~ 1.5 GB RSS / ~ 2.8 GB VMS
- Coût : 30-60s sur 1er vocal FR + 5-15s sur 1re traduction NLLB hors-dictionnaire

**Scénario C — Lazy + unload TTL** : décharger après 30 min d'inactivité.
Bénéfice si la machine continue à subir de la pression mémoire externe.

### 10.4 Pistes d'optimisation à étudier dans l'ADR (réordonnées par impact réel)

**Périmètre ADR-0011** : modèles **durables** uniquement (NeMo, NLLB, TTS×2,
Whisper). ChromaDB lib et MiniLM **hors-scope** (cf. § 4.2.c et ADR-0008).

| # | Piste | Économie boot (RSS / VMS) | Coût | Priorité reco |
|---|---|---|---|---|
| 1 | **Migrer Whisper + NLLB vers `ModelRegistry`** (uniformité, lock, unload) | 0 / 0 | Refactor non fonctionnel | **Prérequis** |
| 2 | **Lazy-load NLLB** | -1007 / **-3356 MB** | 5-15s 1re trad hors-dict (rare) | **Très haute** ← gain VMS énorme |
| 3 | **Lazy-load Whisper** | -822 / -821 MB | 30-60s 1er vocal FR (rare en mode dioula) | **Haute** |
| 4 | **Unload-on-idle (TTL)** sur `ModelRegistry` | variable selon usage | Complexité++ | Optionnelle (Phase 3 bis) |
| 5 | **Quantization NLLB fp16** | ~ -500 MB RSS attendu | Benchmark qualité requis | Optionnelle |
| 6 | **Réduction Whisper turbo → medium int8** | ~ -750 MB | Qualité FR dégradée | Rejeté (qualité critique) |

**Reclassement vs version initiale** : avec les chiffres réels, **NLLB est la cible
prioritaire** (gain VMS énorme), pas Whisper. Cohérent avec le profil utilisateur
dioula (NLLB rarement déclenché, dictionnaire couvre 90%).

### 10.5 Gain attendu post-ADR-0008 (référence, hors ADR-0011)

Une fois ADR-0008 Phase E livrée :
- Suppression dépendance `chromadb` → libère ~ 50-100 MB (lib + indices)
- MiniLM reste chargé mais via `ModelRegistry` (instancié dans
  `corpus_service.py` Phase C)
- Bénéfice cumulé attendu : modèle isolable, lazy-loadable, unloadable comme
  les autres. **À traiter dans un ADR de suivi** (ex: ADR-0012) ou en
  amendement à ADR-0011 lors de la livraison ADR-0008.

### 10.6 Pré-requis ADR
- Confirmer le profil utilisateur dominant (dioula/both vs french) — déjà fait
  dans la mémoire projet.
- Décider quelles pistes (1-6) retenir et dans quel ordre. **Recommandation
  d'audit** : pistes 1+2+3 minimum (refactor + lazy NLLB + lazy Whisper).
- Définir des métriques de succès mesurables (RAM peak boot, latence boot,
  latence p95 1er appel par endpoint).
- Acter explicitement que **MiniLM est hors-scope** ADR-0011 (référence
  ADR-0008).
- Cible chiffrée mesurable post-implémentation : RSS boot ≤ 1.6 GB, VMS boot
  ≤ 3 GB pour le profil utilisateur dioula uniquement.

---

## 11. Annexes

### A. Sources lues
- [`app/main.py`](../../app/main.py) (lifespan startup)
- [`app/services/model_registry.py`](../../app/services/model_registry.py)
- [`app/services/stt_whisper.py`](../../app/services/stt_whisper.py)
- [`app/services/asr_soloni_nemo.py`](../../app/services/asr_soloni_nemo.py)
- [`app/services/translation/nllb_translator.py`](../../app/services/translation/nllb_translator.py)
- [`app/services/translation/translation_service.py`](../../app/services/translation/translation_service.py)
- [`app/services/tts_bambara.py`](../../app/services/tts_bambara.py)
- [`app/services/tts_dioula.py`](../../app/services/tts_dioula.py)
- [`app/services/vdb_service.py`](../../app/services/vdb_service.py)
- [`app/routers/stt.py`](../../app/routers/stt.py)

### B. Logs analysés
- Session uvicorn `wouri-api` du 2026-05-07 13:13:58 → 13:15:?? (transcription dans
  l'historique de session WhatsApp Wourri). **Crash mémoire Whisper + ChromaDB**.
- Session profilage `tools/profile_preload.py` du 2026-05-08 19:04:41 → 19:05:39.
  **7/7 modèles chargés sans crash**. Résultats bruts dans
  [`profile_preload_2026-05-08.json`](profile_preload_2026-05-08.json).

### C. Décisions ADR liées
- [ADR-0002](../adr/0002-ajout-provider-omnilingual.md) : ajout Omnilingual ASR
  (impact futur sur l'empreinte mémoire à anticiper).
- [ADR-0008](../adr/0008-plan-migration-chromadb-pgvector.md) : migration
  ChromaDB → pgvector. **Implications confirmées** :
  - **ChromaDB lib** (`chromadb.PersistentClient`) → supprimée en Phase E (~50-100 MB libérés)
  - **MiniLM** (`paraphrase-multilingual-MiniLM-L12-v2`, ~470 MB) → **conservé**
    (cf. ADR-0008 Q3 : "Le modèle d'embedding ne change pas dans ce plan").
    Sera instancié directement par `corpus_service.py` (Phase C), donc
    isolable via `ModelRegistry` à ce moment-là.
  - **Conséquence pour ADR-0011** : MiniLM hors-scope, isolation différée à
    livraison ADR-0008. Pas d'effort prématuré.

---

## 12. Prochaines étapes (proposées)

1. **Validation de cet audit par Ruben** (cette étape).
2. **Rédaction de l'ADR-0011** "Stratégie de préchargement des modèles ML"
   basé sur les chiffres ci-dessus, avec options A/B/C/D et recommandation unique.
3. **Validation de l'ADR-0011** explicite par Ruben.
4. **Phase 2 d'implémentation** : refactor uniformisation (migration
   Whisper et NLLB vers `ModelRegistry`).
5. **Phase 3** : application stratégie ADR (lazy-load, unload TTL si retenu).
6. **Phase 4** : observabilité (`/health` enrichi, métriques RAM).
7. **Phase 5** : tests + validation manuelle.

---

## Historique

- **2026-05-07** — Rédaction initiale (Phase 0 du plan révision préchargement,
  déclenché par le crash mémoire `mkl_malloc` observé en test manuel).
- **2026-05-08 (matin)** — Révision suite à rappel Ruben sur ADR-0008 (migration
  ChromaDB → pgvector). Ajout colonne "Statut cycle de vie" dans le tableau
  d'inventaire (§ 3) ; séparation explicite de ChromaDB lib (transitoire)
  et MiniLM (durable, isolation différée à ADR-0008 Phase C) ; mise à jour
  des § 4.2.c, 7, 10.3-10.5, et Annexe C. Aucun changement de chiffres,
  uniquement clarification du périmètre ADR-0011 vs ADR-0008.
- **2026-05-08 (soir)** — Injection des **mesures `psutil` réelles** via
  [`tools/profile_preload.py`](../../tools/profile_preload.py). 7/7 modèles
  chargés sans crash. Mise à jour des § 3 (tableau remplacé par mesures réelles
  + nouvelle § 3.A "Surprises vs estimations"), § 5 (latences mesurées), § 9
  (limites 1, 3 levées), § 10.1-10.6 (chiffres réels + reclassement priorités
  pistes : NLLB devient prioritaire car gain VMS énorme). Le total réel
  (3.3 GB RSS / 7.0 GB VMS) est plus modéré que l'estimation initiale (4.8 GB
  RSS), mais le VMS est la métrique critique pour la pression page file
  Windows.
