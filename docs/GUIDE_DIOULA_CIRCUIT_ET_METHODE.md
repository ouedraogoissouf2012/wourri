# WOURRI — Guide du dioula : circuit réel, méthode, et mémos dev

> **Document de référence capital.** Rédigé le 2026-08-05, fondé sur une lecture
> du code réel (branche `APIPy`), pas sur des suppositions. Chaque affirmation est
> vérifiable par `fichier:ligne`. **Les sections « ⚠️ N'EXISTE PAS » sont aussi
> importantes que le reste** : elles évitent de croire à des mécanismes fantômes.

---

## 0. TL;DR (à lire en premier)

- Le **corpus v3 dioula CI** est **validé nativement à 100 %** (162/162) — mais **dans le draft archivé**, PAS en production. La prod sert toujours `corpus_ivr.json` **v2.4 (197 entrées)**.
- La règle d'or du projet : **l'IA propose, le natif tranche.** Aucune traduction dioula n'entre en prod sans validation d'un locuteur natif de Côte d'Ivoire (ADR-0014).
- Il existe un **auto-apprentissage** (feedback 👍 → ajout au corpus), mais il écrit dans **ChromaDB**, pas dans le JSON, et **peut être perdu** au prochain rebuild. À connaître absolument.
- Plusieurs mécanismes « prévus » **n'ont jamais été codés** (registre de vocabulaire, chargement des gros datasets). Détaillé §2.

---

## 1. Ce qui est FAIT (acquis fonctionnels réels)

### 1.1 Corpus v3 validé nativement à 100 %
Chantier lancé en avril 2026 (0 %) → **100 % aujourd'hui** (162/162 entrées à `score_validation = 1.0`).
- **Fichier** : `dictionnaires/archive/corpus_ivr_v3_full_draft.json`
- **Traçabilité** : `data/issue_*_native_validation_*.json` (un par culture, avec `corrections` + `comments` du natif)
- **Cultures validées** : arachide, igname, manioc, cacao, coton, banane, tomate, haricot, gombo, oignon, patate, sésame, café, ananas, mangue, néré, agrumes, maïs, riz, mil + messages système (salutations/hors-sujet/fallback).

### 1.2 Processus de validation industrialisé
- **Générateur de formulaires PDF** : `scripts/generate_culture_validation_pdf.py`
- **Constructeur de données** : `scripts/build_culture_validation_drafts.py`
- **Pipeline de prévalidation** (méthode Codex) : `scripts/prevalidation_rules.py` (§4 ci-dessous)

### 1.3 Gouvernance du dépôt réparée
La branche par défaut GitHub était `wourri` (obsolète depuis janvier), alors que le travail se fait sur `APIPy`. Conséquence : les `Closes #X` ne fermaient jamais les issues. **Corrigé** : branche par défaut = `APIPy`. Désormais, un merge avec `Closes #X` ferme l'issue automatiquement.

---

## 2. Le CIRCUIT TOTAL des données dioula (le cœur)

### 2.1 Les sources déclarées — ⚠️ ATTENTION : en grande partie DEAD CONFIG

`app/config.py:99-120` déclare 4 sources de vocabulaire (`asr_vocab_sources`) :

| name | fichier | statut réel |
|---|---|---|
| koumankan | `data/hf_datasets/koumankan_dyu_fr.json` | ⚠️ **JAMAIS chargé par le code** |
| findora | `data/hf_datasets/findora_fr_dioula.json` | ⚠️ **JAMAIS chargé par le code** |
| ivr | `dictionnaires/corpus_ivr.json` | ✅ utilisé (via vdb_service, pas via ce setting) |
| nlu | `dictionnaires/nlu_concepts.json` | ✅ utilisé (via asr_normalizer, pas via ce setting) |

**⚠️ N'EXISTE PAS** (vérifié — cherché dans tout `app/`) :
- La classe **`VocabularyRegistry`** (mentionnée dans les commentaires de `config.py:96`) → **n'existe pas**.
- La table **`_EXTRACTORS`** (dispatch `schema` → extracteur) → **n'existe pas**.
- **Aucun code ne lit `asr_vocab_sources`** hors `config.py`. C'est du **dead config** : réglable via `.env`, sans aucun effet.

**Conséquence dev capitale** : les gros datasets `koumankan` (10 929 paires) et `findora` sont **présents sur disque mais inertes**. Ils ne servent ni de hotwords ASR, ni de lexique de validation actif. Ils sont là pour un **usage futur** (fine-tuning, cf. `finetune/`), pas dans le runtime.

### 2.2 Ce qui charge RÉELLEMENT du vocabulaire dioula (3 chemins indépendants)

1. **Normalisation post-ASR** — `app/services/asr_normalizer.py:54-71`
   Lit `dictionnaires/nlu_concepts.json` (via sa propre constante, pas le setting). Extrait les mots-clés des concepts pour du fuzzy-matching Levenshtein (rapidfuzz) qui corrige les sorties ASR.

2. **Quality gate agricole ASR** — `app/services/asr/chain.py:21-26`
   La liste `AGRI_KEYWORDS` (~26 mots : `malo`, `kaba`, `tiga`, `sɛnɛ`…) est **hardcodée dans le code source**. Si aucun mot agricole n'est détecté dans une transcription ≥3 mots → 2ᵉ passage ASR avec le provider MMS-dyu (`chain.py:73-91`).

3. **Filtre langue LM (OOV)** — `app/services/validation/lm_filter.py`
   Rejette une transcription si le ratio hors-vocabulaire dépasse `OOV_REJECT = 0.40`, **si** un lexique lui est passé en paramètre.

### 2.3 L'auto-ajout au corpus (circuit d'apprentissage « C3 ») — MÉCANISME RÉEL

**Point d'entrée** : `POST /api/feedback/positif` (`app/routers/feedback.py:45-83`).

**Conditions EXACTES d'ajout** (`feedback.py:65`) :
```python
if req.source in ("ivr_fallback", "fallback_generic") and req.reponse_bambara:
```
| Cas | Ajout au corpus ? |
|---|---|
| feedback 👍 sur réponse `ivr_fallback` (DeepSeek hors-corpus) | ✅ **OUI** |
| feedback 👍 sur réponse `fallback_generic` | ✅ **OUI** |
| feedback 👍 sur `ivr_exact` (déjà dans le corpus) | ❌ non (rien à faire) |
| `reponse_bambara` vide | ❌ non |
| feedback 👎 (négatif) | ❌ **JAMAIS** — logué dans `data/feedback_negatif.jsonl` pour réécriture prioritaire |

**⚠️ AUCUN contrôle humain avant l'ajout.** Tout feedback positif éligible ajoute directement, avec :
- `score_validation = 0.80` **hardcodé** (`feedback.py:74`)
- tags `["feedback_positif", "auto_appris"]`
- id généré `dynamic_{intent}_{culture}_{timestamp}` (`vdb_service.py:328`)
- `source = "auto_validated"` (`vdb_service.py:342`)

**OÙ l'ajout est stocké** (dépend du flag `corpus_storage_mode`, défaut `chroma`) :
- Mode `chroma` (défaut) → **ChromaDB** (`data/chroma_ivr/`), persistant sur disque.
- Mode `dual` → Chroma (autoritatif) + pgvector en thread best-effort.
- Mode `pgvector` → `INSERT INTO corpus_entries` (PostgreSQL).

**🔴 PIÈGE MAJEUR À CONNAÎTRE** : l'auto-ajout **n'écrit JAMAIS dans `dictionnaires/corpus_ivr.json`**. Il vit uniquement dans le store vectoriel. Or la collection Chroma est **supprimée et repeuplée depuis le JSON** au prochain rebuild (voir §2.4). **Donc les entrées auto-apprises `dynamic_*` peuvent être PERDUES** si un rebuild se déclenche. C'est une dette structurante : l'apprentissage C3 est **volatile**.

### 2.4 Chargement du corpus au démarrage (`vdb_service.py:70-149`)

Au boot (`main.py:157-159` → `corpus_facade.initialiser_vdb()`) :
1. `PersistentClient(path=data/chroma_ivr)`.
2. Embedding : modèle local `modeles_manuels/paraphrase-multilingual-MiniLM-L12-v2` (dim 384), fallback HF.
3. **Rebuild déclenché si** : collection vide **OU** `nb_entrées_chroma ≠ nb_entrées_json` **OU** `version_stockée ≠ version_json` (fichier sentinelle `.corpus_version`). Rebuild = `delete_collection` + repeuplement depuis le JSON.
4. Document indexé par entrée : `"{reponse_fr} {tags} {phrases_attestees}"`. Métadonnées : `intent`, `cultures`, `conditions`, `reponse_bambara`, `score_validation`, `source`.

### 2.5 La recherche IVR (`chercher_reponse_ivr`, `vdb_service.py:185-256`)

Cascade à 3 essais :
1. `intent == X` **ET** `culture` exacte (n=3)
2. `intent == X` **ET** `culture == "*"` générique (n=3)
3. `intent == X` seul, toutes cultures (n=5)
4. sinon `None` → fallback DeepSeek

**⚠️ Il n'y a PAS de seuil de similarité cosine.** Le filtrage se fait par **métadonnées exactes** (`intent`/`cultures`). La similarité sémantique sert seulement à **ordonner** les candidats. Le choix final (`_best_result`, `vdb_service.py:259-307`) est un **score métier** :
- base = `score_validation`
- **+0.15** si la saison courante est dans les `conditions` de l'entrée
- **−0.05** si condition saisonnière non matchée
- **+0.05** par condition explicite matchée

Saison : mars-juin & sept-oct = `saison_pluie`, sinon `saison_seche` (`vdb_service.py:50-62`).

### 2.6 Draft v3 → Prod : le lien (ou son absence)

- **Servi par l'API** : `dictionnaires/corpus_ivr.json` **uniquement** (chemin hardcodé `vdb_service.py:21`). Actuellement **v2.4, 197 entrées**.
- **Draft v3** : `dictionnaires/archive/corpus_ivr_v3_full_draft.json` (v3.0, 162 entrées, 100 % validé) → **JAMAIS lu par le code**. Aucune référence à `archive/` dans `app/`.
- **⚠️ Aucun script automatique de promotion draft→prod.** La promotion est un **acte manuel gouverné par l'ADR-0014** : une PR qui remplace le contenu de `corpus_ivr.json` par celui du draft.
- Une fois le JSON prod remplacé, le rebuild Chroma est **automatique** au démarrage suivant (car `version` change).

---

## 3. Schéma du circuit complet

```
   AUDIO vocal (WhatsApp)
        │
        ▼
   ASR (chain.py) : NeMo Soloni → MMS-dyu → MMS-generic
        │  + quality gate AGRI_KEYWORDS (hardcodés)
        ▼
   asr_normalizer.py : fuzzy-match vs nlu_concepts.json
        │
        ▼
   NLU (nlu_service) : intent + culture
        │
        ▼
   chat_service → HANDLERS[langue] → cascade :
        ├─ 1. IVR exact  (chercher_reponse_ivr : métadonnées exactes + score saison)
        ├─ 2. IVR concept
        └─ 3. DeepSeek fallback → NLLB → TTS  (source = ivr_fallback)
        │
        ▼
   Réponse dioula (TTS mms-tts-dyu) + français
        │
        ▼
   Feedback utilisateur 👍/👎
        ├─ 👍 sur ivr_fallback → ajouter_reponse_validee() → ChromaDB (dynamic_*, score 0.80)
        │                         ⚠️ volatile : perdu au rebuild
        └─ 👎 → feedback_negatif.jsonl (réécriture prioritaire)

   CORPUS :
     corpus_ivr.json (v2.4, PROD, servi)  ◄── source de vérité du store vectoriel
     archive/corpus_ivr_v3_full_draft.json (v3, 100% validé, PAS servi)
                                            └── promotion = PR manuelle (ADR-0014)
```

---

## 4. Comment IMPLÉMENTER le dioula — la méthode (différente)

### 4.1 Le principe fondateur
**« Aucune IA ne parle correctement dioula. Le locuteur natif de Côte d'Ivoire fait autorité. »**
On ne génère pas du dioula par IA pour le mettre en prod. On **propose** (IA/pipeline), le **natif valide/corrige**, et **seule sa décision** entre au corpus.

### 4.2 Hiérarchie d'autorité (pour trancher une forme dioula)
1. Décision native WOURI (formulaires PDF validés) — **suprême**
2. ADR WOURI
3. Corrections natives déjà fusionnées
4. Sources explicitement dioula CI (Mandenkan)
5. Dictionnaires mandingues généraux (An Ka Taa)
6. Sources bambara Mali (Bamadaba) — **comparaison seulement**

### 4.3 Règles lexicales — conditionnelles au SENS, pas au mot
`scripts/prevalidation_rules.py` (§3.1) :
- `sugu → lɔgɔ` **uniquement** si le français signifie « marché » (car `sugu` = « sorte/espèce » est valide en dioula CI)
- `kosɛbɛ → caman` (préférence éditoriale, mais `kosɛbɛ` reste attesté)
- `karo → kalo`, `waati → tuma`, `wagati → tuma`, `sɛnnɛkɛla → sɛnɛbaga` (inconditionnelles — formes maliennes sans sens CI alternatif)

Normalisation orthographique par **table explicite** (`foroo→foro`, `sanjiii→sanji`) — **jamais** de regex générale sur les voyelles (détruirait des longueurs légitimes comme `naani`, `duuru`, `bɛɛ`).

### 4.4 Ce qui reste TOUJOURS au natif (jamais automatisé)
Choix entre synonymes, nom d'un ravageur, langage technique vs paysan, naturalité orale, ordre SOV, prononciation d'acronymes, formulation TTS, dosages agronomiques. Le script les **signale** (`termes_a_confirmer`), ne les résout pas.

---

## 5. Comment UTILISER (commandes concrètes)

### 5.1 Générer un formulaire de validation pour une culture
```bash
cd wouri-api
# Construire le JSON de données (VERSION A du draft + VERSION B des anciennes PR)
python scripts/build_culture_validation_drafts.py
# Générer le PDF remplissable
uv run --with reportlab --with pypdf python scripts/generate_culture_validation_pdf.py --culture <nom>
```
→ PDF dans `output/pdf/` ou `Downloads/dioula/`.

### 5.2 Le cycle de validation (le workflow éprouvé)
1. Générer le formulaire PDF (§5.1)
2. Le locuteur natif le remplit (coche A/B/Correction + écrit la correction dioula)
3. Extraire les corrections des PDF remplis → `data/issue_<N>_<culture>_native_validation_*.json`
4. Promouvoir dans le **draft** (`score_validation = 1.0`) — **jamais la prod directement**
5. Test de protection ADR-0014 + PR

### 5.3 Démarrer le backend
```bash
cd wouri-api
uvicorn app.main:app --port 8000 --reload
```
Prérequis : `.env` avec `DEEPSEEK_API_KEY`, `API_SECRET_KEY`. Le fix `extra = "ignore"` (config.py) tolère `HF_TOKEN`/`FFMPEG_PATH` dans le `.env`.

### 5.4 Tester une réponse IVR (avec clé API)
```bash
KEY=$(grep API_SECRET_KEY= .env | cut -d= -f2)
curl -s -X POST http://127.0.0.1:8000/api/chat/ \
  -H "Content-Type: application/json" -H "X-API-Key: $KEY" \
  -d '{"message":"a quel prix vendre mon arachide ?","language":"both","include_audio":false}'
# → source: ivr_exact, intent: QUESTION_VENTE, response_dioula: ...
```

### 5.5 TTS dioula (code langue = `bam`, PAS `dyu`)
```bash
curl -s -X POST "http://127.0.0.1:8000/api/tts/ivorian?text=<URLencodé>&language=bam" \
  -H "X-API-Key: $KEY"
# → {"audio_url": "/static/audio/bam_xxx.ogg"}
```
⚠️ Le TTS dioula (`mms-tts-dyu`) est exposé sous le code **`bam`** (« Bambara/Dioula »), pas `dyu`.

---

## 6. MÉMOS DEV (pièges & règles d'or)

| # | Mémo | Pourquoi |
|---|---|---|
| 1 | **Le natif tranche, toujours.** Ne jamais mettre du dioula IA en prod sans validation native. | ADR-0014, principe fondateur |
| 2 | **Travailler sur `APIPy`**, jamais sur `wourri` (obsolète). Les PR ciblent `APIPy` (= branche par défaut). | Gouvernance |
| 3 | **`corpus_ivr.json` = prod servie ; le draft v3 n'est PAS servi.** La promotion est une PR manuelle. | §2.6 |
| 4 | **L'auto-apprentissage C3 est VOLATILE** (Chroma, perdu au rebuild). Ne pas compter dessus pour du permanent. | §2.3 🔴 |
| 5 | **`asr_vocab_sources` = dead config.** Les datasets koumankan/findora ne sont pas chargés au runtime. | §2.1 ⚠️ |
| 6 | **Règles lexicales conditionnelles au SENS**, pas au mot. `sugu`/`kosɛbɛ` ne sont PAS bannis absolument. | §4.3 |
| 7 | **Jamais de regex générale sur les voyelles.** Table explicite uniquement. | §4.3 |
| 8 | **Recherche IVR = métadonnées exactes (intent+culture) + score saison**, pas de seuil de similarité. | §2.5 |
| 9 | **TTS dioula = code `bam`**, pas `dyu`. | §5.5 |
| 10 | **Toujours tester en conditions CI** (`.env` minimal) avant de dire « fini ». Le `.env` local pollué masque des échecs. | Expérience |
| 11 | **ADR avant tout code structurant** (stockage, ML, corpus, API). | Règle projet |
| 12 | **Un token/secret dans le `.env` ne doit jamais fuiter.** Rotation si exposé. | Sécurité |

---

## 7. Les 4 critères ADR-0014 pour la mise en PRODUCTION du corpus v3

Le corpus est validé à 100 % (critère 1). Restent **3 critères** avant toute prod :

| Critère | État |
|---|---|
| 1. Validation native complète (≥95 %) | ✅ **100 %** |
| 2. Staging déployé (#202) | ❌ à faire |
| 3. Tests E2E de cascade IVR en staging | ❌ à faire |
| 4. Plan de rollback (backup prod) documenté | ❌ à faire |

**Tant que 2-3-4 ne sont pas remplis, le draft v3 reste archivé. La prod sert v2.4.**

---

## 8. Références code (pour approfondir)

| Sujet | Fichier |
|---|---|
| Config + dead config vocab | `app/config.py:99-120` |
| Auto-ajout C3 | `app/routers/feedback.py:45-83` |
| Store vectoriel Chroma | `app/services/vdb_service.py` |
| Façade multi-backend | `app/services/corpus_facade.py` |
| Recherche IVR + scoring saison | `app/services/vdb_service.py:185-307` |
| Chaîne ASR + gate agricole | `app/services/asr/chain.py` |
| Normalisation post-ASR | `app/services/asr_normalizer.py` |
| Pipeline prévalidation | `scripts/prevalidation_rules.py` |
| Générateur formulaires | `scripts/generate_culture_validation_pdf.py` |
| Règles grammaticales dioula | `data/GRAMMAIRE_DIOULA_REGLES.md` (§12bis = BAM↔DYU) |
| Gouvernance promotion | `docs/adr/0014-promotion-corpus-v3-dioula-ci.md` |
| Stockage vectoriel | `docs/adr/0008-plan-migration-chromadb-pgvector.md` |
