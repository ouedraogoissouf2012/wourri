# WOURRI — Le dioula de bout en bout : audit exhaustif

> **Document de référence.** Établi le 2026-08-09 par un audit multi-agents (7 explorateurs,
> un par sous-système, + vérification **adversariale** : chaque affirmation « dormant /
> cassé / absent » a été contre-vérifiée par un second agent chargé de la réfuter, puis
> les contradictions ont été tranchées manuellement sur le code). **210 éléments inventoriés**,
> chaque claim porte sa preuve `fichier:ligne`. État du code : branche `APIPy` au 2026-08-09,
> corpus v2.4.1, backend corpus `pgvector` (défaut depuis #354).

---

## 0. Synthèse exécutive

### Le paradoxe central du projet

**L'aval (répondre) est solide. L'amont (comprendre) est en panne. La boucle (apprendre) est débranchée.**

- **Répondre** ✅ — la cascade chat sert du dioula issu du corpus (`ivr_exact`), la voix
  `mms-tts-dyu` fonctionne, la météo du jour est injectée en dioula dans les salutations,
  le conseil saisonnier est concaténé à chaque réponse corpus.
- **Comprendre** 🔴 — sur les 3 moteurs ASR de la chaîne dioula, **2 sont cassés** :
  NeMo Soloni (package `nemo` **jamais installé**, absent de `requirements.txt`) et
  l'adapter MMS fine-tuné dioula CI (bug de chemin depuis avril). **100 % de l'audio
  dioula est transcrit par le modèle générique `facebook/mms-1b-all` (adapter bambara
  malien)** — aucun modèle spécifique dioula CI ne sert. Le « second passage agricole »
  ne se déclenche jamais.
- **Apprendre** 🔴 — la file de candidats à revue native (ADR-0019) ne peut **jamais**
  recevoir sa cible : un 👍 sur une réponse `deepseek_open` (le seul chemin produisant du
  dioula machine) est exclu par la condition du code. L'outil de revue référencé n'existe
  pas. Aucun candidat n'a jamais été déposé.

### Le second paradoxe : la validation dort

| Corpus | Entrées | Validées nativement (score 1.0) | Servi aux agriculteurs ? |
|---|---|---|---|
| `corpus_ivr.json` v2.4.1 (**prod**) | 197 | **35** (17,8 % — anacarde + palmier, #40) | ✅ OUI |
| `archive/corpus_ivr_v3_full_draft.json` | 162 | **162** (100 %) | ❌ NON (ADR-0014, critères 2-4) |

Les 162 réécritures dioula CI intégralement validées par le locuteur natif **dorment en
archive**, pendant que la prod sert leurs anciennes versions à 0.6–0.9. Et le draft
contient une **typo d'intent** (`DIAGNOSTIQUE_PROBLEME`) qui rendrait une entrée
inatteignable s'il était promu tel quel.

### Chiffres clés

- **210** éléments audités, **7** sous-systèmes, **~60** claims négatifs contre-vérifiés
- ASR : **1/3** providers dioula fonctionnel (le générique) ; adapter fine-tuné 3,86 Go jamais chargé
- NLU : **57** concepts, **690** mots-clés (~410 dioula / ~280 FR-EN), **16** intents — mais **0** marqueur temporel (demain/sini) et **3** familles reconnues sans réponse (météo, élevage, hévéa)
- Corpus : **197** entrées servies, **15** trous intent×culture, **24/197** avec phrases attestées
- TTS : **deux voix différentes** pour « le dioula » selon le point d'entrée (chat = `mms-tts-dyu`, endpoints `/api/tts/*` = `mms-tts-bam` bambara malien)
- Traduction : **deux cibles NLLB divergentes** (chat → `dyu_Latn`, endpoints + compréhension → `bam_Latn`) ; dictionnaire 15 779 clés issu à ~99,96 % de **Bamadaba (bambara malien)**
- **~2,8 Go** de doublons purs sur disque ; dataset de fine-tuning (79 k phrases) **hors contrôle de version**

---

## 1. Le circuit RÉEL d'un vocal dioula (tel qu'il s'exécute, pas tel qu'il est documenté)

```
Agriculteur envoie un vocal WhatsApp
  │
  ▼ whatsapp-server (lib/asr_client.js:151)
POST /api/asr/transcribe-and-translate   [asr.py:107-220]
  │
  ▼ ASRChain [chain.py:95-117] — ordre déclaré : NeMo → MMS-dyu → MMS-generic
  │    ✗ NeMo Soloni ........ CASSÉ (package nemo non installé)      [nemo_provider.py:30-37]
  │    ✗ MMS-dyu (fine-tuné). CASSÉ (chemin faux depuis avril)       [mms_dyu_provider.py:16]
  │    ✓ MMS-generic ........ SEUL transcripteur réel (adapter 'bam') [mms_generic_provider.py]
  │    ✗ Gate AGRI_KEYWORDS . jamais déclenché (dépend de MMS-dyu)   [chain.py:73]
  ▼
normalize_asr_output [asr_normalizer.py] — LA brique qualité qui marche :
  corrections exactes (59) → fusions NeMo → variantes phonologiques ADR-0020 → fuzzy NLU
  ▼
NLU [nlu_service.py] : 57 concepts → intent (SANS filtre de confiance vers l'IVR)
  + traduction BAM→FR d'affichage (dictionnaire→NLLB bam_Latn) ; la compréhension
  effective = phrase FR reconstruite par le NLU (nlu_message, "à utiliser en priorité")
  ▼ whatsapp-server réinjecte message + bambara_text
POST /api/chat/  →  ChatService.process : ville → NLU → météo → HANDLERS[langue]
  ▼ DioulaHandler / BothHandler (cascade identique)
  ├─ 1. IVR exact  [ivr_searcher.py:72-165]  corpus pgvector, filtre intent+culture,
  │      SANS seuil de similarité (l'embedding ne fait que classer 5 candidats)
  │      + inject_meteo (tags salutations) + conseil saisonnier + TTS mms-tts-dyu
  │      → source=ivr_exact  (DIOULA VALIDÉ)
  ├─ 2. IVR concept [ivr_searcher.py:173-253] + clarification si action sans culture (#94)
  │      → source=ivr_fallback / clarification_culture  (DIOULA VALIDÉ)
  └─ 3. DeepSeek (répond en FRANÇAIS contraint) → si audio : dictionnaire salutations
         puis NLLB fra_Latn→dyu_Latn → TTS
         → source=deepseek_open  (DIOULA MACHINE NON VALIDÉ)
         ⚠ si include_audio=False : response_dioula = texte FR non traduit
  ▼
Réponse (texte + audio) → WhatsApp → feedback 👍/👎
  ✗ un 👍 sur deepseek_open ne dépose JAMAIS de candidat (condition feedback.py:83)
```

---

## 2. Ce qui MARCHE (actif, prouvé au runtime)

| Élément | Rôle | Preuve |
|---|---|---|
| Corpus v2.4.1 → pgvector | 197 réponses dioula servies, cascade 3 essais | `corpus_service.py:240-294`, boot `main.py:157` |
| `season_scoring` | bonus saison +0.15 / conditions +0.05 sur chaque recherche | `corpus_service.py:164-174` |
| Cascade handlers (ADR-0015) | FRENCH / DIOULA / BOTH / ENGLISH tous branchés | `handlers/__init__.py:33-39` |
| Clarification culture (#94) | action sans culture → question dioula, plus de fallback maïs | `ivr_searcher.py:228-235` |
| Garde anti inter-culture | jamais une réponse d'une autre culture | `ivr_searcher.py:36-52,112` |
| `asr_normalizer` (4 étapes) | 59 corrections + fusions + phonologie ADR-0020 + fuzzy | `chain.py:66-71`, `asr_normalizer.py:487-496` |
| Filtre phonologique ADR-0020 | variantes gw/g, l/d, l/j, r/l, nin/len avant fuzzy | `asr_normalizer.py:199` |
| MMS-generic ASR | le transcripteur réel (adapter `bam` Meta) | `mms_generic_provider.py:53-54` |
| TTS dioula `mms-tts-dyu` | la voix du bot (pipeline v3 : pauses, vitesses, nettoyage tons) | `tts_dioula.py:49,240-520` |
| Météo→dioula (templates) | 6 verdicts codés en dur, injectés dans les 4 salutations | `meteo_injector.py:52-68`, `ivr_searcher.py:126` |
| Conseil saisonnier | calendrier cultural par mois/culture, concaténé aux réponses corpus | `calendrier_agricole.py:191-262` |
| Dictionnaire + NLLB (lazy) | phrase exacte → mot-à-mot (BAM→FR) → NLLB ; salutations protégées de la MT | `translation_service.py:74-94`, ADR-0011 |
| Prévalidation Codex (offline) | tables conditionnelles au sens, 24 validations natives produites | `prevalidation_rules.py` |
| Dépôt feedback (partiel) | le POST écrit bien candidats/négatifs… quand la condition matche | `feedback.py:83-97` |
| Whisper FR + corrections | vocaux français (99 corrections agri + 132 villes) | `stt_whisper.py:293,329-334` |

## 3. Ce qui est CASSÉ (avec preuves)

| # | Élément | Ce qui casse | Preuve |
|---|---|---|---|
| C1 | **NeMo Soloni ASR** (1er provider) | package `nemo` **non installé**, absent de `requirements.txt` et du Dockerfile ; le modèle .nemo (459 Mo) est orphelin sur disque | `nemo_provider.py:30-37`, `Dockerfile.prod:42-44` |
| C2 | **Adapter MMS-dyu fine-tuné** (2ᵉ provider, 3,86 Go — le SEUL modèle dioula CI) | chemin off-by-one (`app/modeles_manuels/` inexistant, régression refactor #44 d'avril, commit 1ccbec6) → `is_available()`=False à jamais ; **aggravants** : le dossier réel n'a pas de `config.json`, `.dockerignore:49` l'exclut de l'image, `librosa` hors requirements | `mms_dyu_provider.py:16,37` |
| C3 | **Gate agricole AGRI_KEYWORDS** | dépend du 2ᵉ passage MMS-dyu (cassé) → ne se déclenche **jamais** | `chain.py:73` |
| C4 | **ChromaDB** (modes `chroma`/`dual`) | incompatible numpy 2.4 (`np.float_ removed`, reproduit) ; dégradation **silencieuse** (collection→None, tout part en fallback) | `vdb_service.py:130-135`, `config.py:122-124` |
| C5 | **Templates de déploiement** | `.env.prod.template:73` et `docker-compose.staging.yml:112` livrent `CORPUS_STORAGE_MODE=dual` — or en dual **Chroma (mort) est autoritaire** → un déploiement avec ces templates casse TOUT le chemin corpus | `.env.prod.template:73` |
| C6 | **Feedback ADR-0019 (cible)** | la file de candidats exige `source ∈ {ivr_fallback, fallback_generic}` ; le dioula machine émet `deepseek_open` et `fallback_generic` n'est produit **nulle part** → la boucle de collecte ne peut jamais capturer sa cible | `feedback.py:83` vs `deepseek_router.py:69` |
| C7 | **Draft v3 : typo d'intent** | `mangue_limogo_diagnostic_001` porte `DIAGNOSTIQUE_PROBLEME` (au lieu de `DIAGNOSTIC_`) → entrée inatteignable si le draft est promu tel quel ; aucun test ne le détecte | draft v3 (vérifié) |
| C8 | **`/health` ment sur le TTS FR** | `"tts_french": True` **codé en dur** (« Edge-TTS toujours disponible » — Edge-TTS n'existe pas) : le monitoring ne verra jamais une panne | `main.py:301` |
| C9 | **TTS FR/EN muets en Docker prod** | le binaire `piper` n'est pas installé dans l'image (`grep piper Dockerfile.prod` = 0) ; défauts `PIPER_MODEL_*` vides → dégradation silencieuse | `Dockerfile.prod:29-34,64-69` |
| C10 | **`tools/bambara_validator.py`** | `DATA_DIR` remonte 4 parents (un de trop) → les 6 sources locales chargent **vide en silence** | `bambara_validator.py:41` |
| C11 | **Scripts finetune in-repo** | chemins `wouri-api/wouri-api/` inexistants ; seules les copies **hors git** (`wourri/finetune/`) fonctionnent | `prepare_dioula_dataset.py:34-41` |
| C12 | **Tests ASR aveugles** | les tests mockent `is_available` → ils passent alors que 2 providers sur 3 sont morts en conditions réelles | `test_asr_providers.py` |

## 4. Ce qui EXISTE mais DORT (disponible, non utilisé)

### 4.1 Les trésors linguistiques dormants

| Ressource | Contenu | Pourquoi ça dort |
|---|---|---|
| **Draft corpus v3** (`archive/corpus_ivr_v3_full_draft.json`) | 162 réponses dioula CI **100 % validées nativement** — l'actif le plus précieux du repo | ADR-0014 : critères 2-4 (staging, E2E, rollback) non remplis |
| **KenLM dioula agricole** (`data/models/kenlm_dyu_agri.binary`, 535 Ko, entraîné sur ~31 k phrases) | modèle de langue pour filtrer les hallucinations ASR | `DioulaLMFilter` complet et testé mais **jamais câblé** ; package `kenlm` non installé ; flag `ENABLE_LM_RESCORING` cité en docstring **n'existe pas** |
| **Datasets parallèles** (`data/hf_datasets/`) | koumankan 10 929 paires dyu-fr ; findora 20 513 ; francophonia 44 500 (téléchargement partiel 58 %) | aucun code ne les charge ; consommés seulement par notebooks Colab (upload manuel) et par les copies finetune hors git |
| **15 brouillons hévéa** (`data/issue_40_hevea_validation_draft.json`) | formulations prêtes pour le formulaire natif | validation native jamais réalisée → hévéa = 0 réponse |
| **Backlog LinguaOps** (`docs/linguaops/`, ~15 issues prêtes) | capture feedback SQL, quarantaine corpus, câblage LM filter, journalisation OOV | bloqué sur un « ADR-0016 LinguaOps » jamais écrit — et le numéro 0016 a depuis été pris par un autre ADR |
| **Lexiques de référence** (`data/references_dioula/`) | Webonary bambara 2,3 Mo + index dioula + Mandenkan | consultation humaine uniquement, aucun code ne les lit |
| **`deepseek_translator.py`** (263 lignes, testé) | traduction FR→BAM par DeepSeek avec ancres Bamadaba + back-translation NLLB | jamais branché — candidat évident pour améliorer la qualité du tier 3 |
| **`translate_dioula_to_french()`** | la SEULE fonction de compréhension utilisant le bon code `dyu_Latn` | zéro appelant — le chemin actif lit en `bam_Latn` |
| **Omnilingual ASR** (provider + notebook + requirements dédiés) | alternative ASR Meta, dyu natif (1672 langues) | jamais instancié dans la chaîne ; flags `omnilingual_*` lus par personne ; dépendances non installées |
| **Dataset fine-tuning AXE-4** (`wourri/data/dioula_dataset`, 79 k phrases) | la base du seul fine-tuning dioula réalisé | vit **hors du dépôt git** (niveau parent), risque de perte réel |

### 4.2 Code dormant / dead config (nettoyage)

| Élément | Preuve |
|---|---|
| Settings jamais lus : `asr_language`, `asr_hallucinations_path`, `default_ivorian_language`, `tts_french_voice`, `omnilingual_*` | `config.py:61,83,94,107,185-189` (grep = 0 lecteur) |
| Dépendance `edge-tts==6.1.9` installée, **jamais importée** | `requirements.txt:28` |
| `hors_sujet_examples` (15 exemples) jamais chargés — et contredits par le code (élevage listé hors-sujet mais `ANIMAL_*` le fait passer) | `nlu_concepts.json:1319-1335` |
| `out_of_scope_response` clés bambara/dioula jamais servies + `get_out_of_scope_response()` sans appelant | `nlu_service.py:144-146` |
| Label `CULTURE_SORGHO` inatteignable (aussi dans `calendrier_agricole.py`) | `sentence_builder.py:22` |
| `variants_for_text()` (phonologie) sans consommateur | `bam_dyu_phonology.py:144-166` |
| `ajouter_reponse_validee` ×3 + `get_reponse_fallback` ×3 — conservés délibérément (décision tracée ADR-0019) | `corpus_facade.py:367-431` |
| Mode `dual` + table `corpus_divergences` + `/admin/corpus-divergence-report` | `corpus_facade.py:254-330` |
| `POST /api/chat/simple`, wrappers rétrocompat ChatService (7), `try_deepseek_french`, `preload_all_models` TTS ivoirien, enum `IvorianLanguage` | `chat.py:69-86`, `chat_service.py:136-261` |
| `dictionnaires/config.json` (métadonnées jamais lues, référence un `sources/manuel.csv` absent) | vérifié |
| **Doublons disque ~2,8 Go** : `mms-dioula-adapter-final.zip` (2,26 Go), `bayelemabaga.tar.gz` (46 Mo), `.arpa` intermédiaires (7,5 Mo), mms-tts-bam en double (cache HF 277 Mo + copie locale 145 Mo) | ls vérifiés |
| Artefacts de campagnes mars-avril périmés : `generate_validation_d1.py` (« 144 phrases »), `test_corpus_audit.py` (« v1.3 »), rapports axe2/axe5, wav figés | racine repo |

## 5. Ce qui N'EXISTE PAS (attendu ou référencé, mais absent)

| Élément | Référencé par | Impact |
|---|---|---|
| `tools/review_feedback_candidates.py` | `feedback.py:35` (« Lu par… ») | le maillon candidat→formulaire natif n'existe pas |
| `data/asr_hallucinations_dyu.json` | `config.py:107` + ADR-0002/0003 | blocklist d'hallucinations jamais créée |
| Flag `ENABLE_LM_RESCORING` | docstring `lm_filter.py:19,23` | flag fantôme — n'existe dans aucun settings |
| Marqueurs temporels NLU (`sini`, demain, aujourd'hui, `bi`) | — | « pleuvra-t-il demain ? » indistinguable d'une question de saison (cf. #355) |
| Entrées corpus : `QUESTION_METEO_AGRICOLE` (0), `QUESTION_GENERALE` (0), `ANIMAL_*` (0), `CULTURE_HEVEA` (0) | NLU les reconnaît | tout finit chez DeepSeek (sauf météo/générale **avec** culture → repli CONSEIL_PRODUCTION) |
| Code langue `dyu` dans `SUPPORTED_LANGUAGES` | le vrai modèle runtime est `mms-tts-dyu` | « dioula » résout vers `bam` (bambara malien) dans la source unique des langues |
| Modèles TTS `dyi`/`myk`/`dnj` sur disque | déclarés dans les 8 langues | 1er appel = téléchargement internet jamais démontré |
| `data/feedback_candidates.jsonl` + `feedback_negatif.jsonl` | producteurs branchés | jamais créés — zéro candidat, zéro négatif depuis ADR-0019 (4 votes négatifs de mars vivent dans l'ancien `logs/feedback.jsonl`) |
| Packages : `nemo`, `kenlm`, `librosa`, `reportlab`, `pypdf` dans `requirements*.txt` | code qui les importe | casse silencieuse locale et/ou Docker |
| ADR LinguaOps | exigé par `ISSUES_LINGUAOPS.md` (P0 « bloque tout ») | jamais écrit ; numéro 0016 consommé par Promtail/Alloy |
| Validation native des mots-clés `ANIMAL_*` | homonymes à risque : `wari` (= argent), `dɔnkili` (= chanson), `fali` (= âne) | faux positifs « agricoles » possibles |

## 6. Les mensonges du code (doc/commentaires contredits par les faits)

À corriger — ils ont déjà induit des décisions en erreur :

1. **`CLAUDE.md`** : « `asr_soloni_nemo.py` — ASR NeMo actif » → le fichier est **supprimé** (ADR-0021) et NeMo n'est **pas installé**.
2. **`config.py:55`** : « Lingva Translate est utilisé pour la traduction » → **aucun code Lingva n'existe** (grep repo entier = ce commentaire).
3. **`lm_filter.py:19,23`** : documente `ENABLE_LM_RESCORING` → le flag **n'existe pas**.
4. **`feedback.py:35`** : « Lu par tools/review_feedback_candidates.py » → le fichier **n'existe pas**.
5. **`corpus_facade.py:7` + `main.py:154-155`** : « mode chroma (DÉFAUT) » → le défaut est **pgvector** depuis #354.
6. **`main.py:301`** : `"tts_french": True — « Edge-TTS est toujours disponible »` → Edge-TTS n'est pas le TTS FR (c'est Piper), et la valeur est un littéral jamais calculé.
7. **`requirements.txt`** (commentaire chromadb) : « compatible numpy 2.4 » → **faux, reproduit** (`np.float_ removed`).
8. **`config.py:103`** : koumankan/findora « restent sur disque pour le fine-tuning » → aucun script in-repo fonctionnel ne les lit.
9. **`GET /api/chat/languages`** : n'annonce pas `english` pourtant fonctionnel (ADR-0015).
10. **`deepseek_router.py:88`** : « sera supprimée en PR 3/4 » → jamais fait.
11. **`tts_common.py:8-10`** : affirme que tts_ivoirian n'a pas la normalisation → faux depuis PR #231.
12. **`handlers/__init__.py:14-18`** : décrit un état « PR 2/4 » périmé.

## 7. Détail par sous-système

### 7.1 ASR (comprendre la voix)
- **Chaîne réelle** : `[NeMo ✗, MMS-dyu ✗, MMS-generic ✓]` → tout passe par le générique.
- La qualité dioula repose **entièrement sur le post-traitement** : `asr_corrections.json`
  (59 corrections dont 17 issues de vrais tests WhatsApp), fusions syllabiques, variantes
  phonologiques ADR-0020, fuzzy sur les 690 mots-clés NLU.
- Piste de réparation adapter : corriger le `.parent` manquant (**1 ligne**) + fournir les
  fichiers processor (`config.json`/`vocab.json` — noter que des candidats existent à la
  racine `modeles_manuels/`, à vérifier : ceux de la racine appartiennent au TTS VitsModel).
- Whisper est **FR uniquement** (`language='fr'` en dur, `stt_whisper.py:293`).

### 7.2 NLU (comprendre le sens)
- 57 concepts / 16 intents / 690 mots-clés — préchargé, ~10 ms, robuste (tons strippés).
- **Le seuil de confiance (0.2) ne filtre que la reconstruction de phrase FR** — l'intent
  pilote l'IVR sans aucun filtre (`nlu_service.py:122,132-142`).
- Matching « partial » **sans frontière de mot** (29 patterns) : `gan` (gombo) matche
  « or**gan**isation » (`concept_extractor.py:120`).
- Hors-sujet : détection **purement négative** ; en mode DIOULA un message sans caractères
  bambara **saute le NLU entièrement** (`nlu_preprocessor.py:119-130`).
- Mots-clés `ANIMAL_*` jamais validés nativement (homonymes `wari`, `dɔnkili`, `fali`).

### 7.3 Corpus (les réponses validées)
- 197 entrées servies via pgvector ; **peuplement UNIQUEMENT manuel**
  (`scripts/import_corpus_ivr.py`) — modifier le JSON sans relancer l'import = prod périmée.
- Trous : mangue 2 entrées (6 intents vides), agrumes 4, néré 5, hévéa 0 ; anacarde/palmier
  sans QUESTION_VENTE ; **15 cases vides** sur 176.
- `phrases_attestees` : 24/197 entrées seulement (157 phrases) — inopérant pour ~88 % du corpus.
- Le process de validation (PDF → natif → draft, méthode Codex) est réel, éprouvé
  (24 fichiers de traçabilité) — mais ses dépendances PDF (`reportlab`/`pypdf`) sont hors
  requirements et la « VERSION B » dépend d'un cache temporaire volatile.

### 7.4 Traduction
- **BAM→FR** (comprendre) : dictionnaire (phrase exacte → mot-à-mot ≥40 %) → NLLB `bam_Latn`.
  Mais la compréhension **effective** du chat = la phrase FR reconstruite par le NLU.
- **FR→dioula** (répondre, tier 3 seulement) : salutations dictionnaire → NLLB
  **`dyu_Latn`** direct (`tts_dioula.py:114`) — **court-circuite** la chaîne TranslationService.
- **Divergence** : les endpoints `/api/tts/translate` et `/api/tts/bambara` traduisent vers
  **`bam_Latn`**. Deux dialectes cibles coexistent silencieusement selon le chemin.
- Le dictionnaire 15 779 clés provient à ~99,96 % de **Bamadaba (bambara malien)** —
  4 entrées manuelles dioula CI seulement.

### 7.5 TTS et langues
- **Deux voix pour « le dioula »** : cascade chat = `mms-tts-dyu` (correct) ; endpoints
  `/api/tts/*` avec `language=dioula` = **`mms-tts-bam`** (bambara malien) — et le
  whatsapp-server appelle `/api/tts/bambara` (`app-baileys.js:189,203`) → l'incohérence
  est exercée en réel.
- 8 langues déclarées (`constants.py`) mais `dyu` absent du registre ; 4 langues avec
  modèle en cache jamais testées ; 3 sans modèle sur disque.
- La voix principale du produit (`tts_dioula.py`, ~280 lignes de pipeline v3) n'a
  **aucun test de synthèse automatisé**.

### 7.6 Météo (audit du 2026-08-08, intégré)
- La conversion météo→dioula **existe et tourne** (6 verdicts en dur), mais uniquement
  comme contexte injecté dans les 4 salutations.
- Une **question** météo directe → 0 entrée corpus → DeepSeek (avec la météo **du jour**,
  jamais la prévision : seul `current` est demandé à Open-Meteo, `weather.py:88`).
- Deux générateurs de conseil dupliqués (chat vs API REST) aux seuils divergents.
- → issues **#355** (prévision + intent), **#356** (consolidation), **#357** (multilingue).

### 7.7 Feedback / boucle d'amélioration
- Dépôt de candidats branché et testé, MAIS : condition qui exclut `deepseek_open` (C6),
  outil de revue inexistant, fichiers jamais créés (aucun trafic réel depuis ADR-0019),
  et `FrenchHandler` sans `meta` → trafic FR invisible dans `top_sources`.

## 8. Recommandations priorisées

### P0 — répare ce qui trahit le produit
1. **ASR dioula** : corriger `ADAPTER_PATH` (1 ligne) + fournir le processor de l'adapter
   + trancher NeMo (installer `nemo-toolkit` OU retirer le provider et le préchargement).
   C'est LE levier qualité de compréhension. *(issue à créer)*
2. **Feedback** : inclure `deepseek_open` dans la condition de mise en file — sinon la
   boucle d'apprentissage ne collectera jamais rien. *(issue à créer)*
3. **Templates de déploiement** : `dual` → `pgvector` (`.env.prod.template`,
   `.env.staging.template`, `docker-compose.staging.yml`) — sinon le prochain déploiement
   casse le corpus entier. *(issue à créer)*
4. **Draft v3** : corriger la typo `DIAGNOSTIQUE_PROBLEME` + ajouter un test de validité
   des intents du draft (avant toute promotion). *(issue à créer)*

### P1 — la valeur qui attend
5. **Promotion corpus v3** (staging #202 → E2E #305 → rollback → promotion ADR-0014) :
   162 réponses validées à mettre enfin dans la bouche du bot.
6. **Unifier la voix dioula** (`/api/tts/*` : dyu vs bam) et la cible NLLB (`dyu_Latn`
   partout où l'on parle à un Ivoirien). *(issue à créer)*
7. **Météo** : #356 → #355 → #357 (déjà créées).
8. **Nettoyage Chroma** (#203, plan tracé) — élimine C4/C5 par construction.
9. **Statuer** sur KenLM/lm_filter et Omnilingual : câbler (issues LinguaOps L1-05) ou retirer.

### P2 — hygiène
10. Purger les 12 mensonges du code + dead configs + `edge-tts`.
11. Supprimer ~2,8 Go de doublons ; versionner le dataset fine-tuning (79 k phrases).
12. Valider nativement les mots-clés `ANIMAL_*` ; réparer `bambara_validator` (DATA_DIR).
13. Ajouter les dépendances manquantes aux requirements (`librosa`, `reportlab`, `pypdf` en dev).

---

## 9. Méthode et limites de cet audit

- 7 agents explorateurs (un par sous-système) + 7 vérificateurs adversariaux chargés de
  **réfuter** chaque claim négatif ; ~60 claims contre-vérifiés, dont 6 **réfutés ou
  nuancés** et corrigés dans ce document ; 1 contradiction inter-agents (adapter MMS-dyu)
  tranchée manuellement sur le code.
- Les preuves valent pour **cette machine et ce dépôt** au 2026-08-09. Une instance
  déployée ailleurs (aucune connue) n'est pas couverte.
- Les nombres de lignes cités peuvent glisser au fil des commits — les noms de fichiers
  et de fonctions font foi.
