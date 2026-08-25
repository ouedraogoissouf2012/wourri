# ADR-0035 — Collecte du dataset ASR par dictée guidée + contrat d'export

**Statut** : **accepté**
**Date** : 2026-08-25 (proposé et accepté le même jour)
**Auteur(s)** : Issouf Ouédraogo + assistance agent
**Valideur** : Issouf — « la meilleure option, la plus rigoureuse, pas de bricolage » (délègue le choix technique) 2026-08-25

---

## Contexte

- Chantier **« faire comprendre le baoulé (bci) à Wourri »** (epic #472, phase **#474 fine-tune ASR**).
  Comprendre ≠ produire : c'est un chantier **distinct** de la collecte de parité (ADR-0034).
- **État vérifié** :
  - Le benchmark ASR baoulé est **outillé** mais **pas encore mesuré** (ADR-0034 ; PR #479 ;
    `finetune/colab/asr_baoule_benchmark.ipynb`). Aucun CER baoulé n'est encore prouvé.
  - L'atelier `wouri-lqe` collecte déjà des `(text_local, audio_url)` via la table **`lqe.productions`**,
    mais en mode **production libre** : le locuteur *invente* la réponse à un concept ; la transcription
    est **optionnelle** (`concept_id` nullable, ADR-0034 P4). Résultat concret : les **14 audios bci**
    déjà collectés par `esse.adc` sont **sans texte** → **inexploitables pour l'ASR** (pas de paire
    audio↔transcription fiable).
  - Le fine-tune d'un modèle ASR (Wav2Vec2 / Whisper / Omnilingual) exige un **dataset supervisé** :
    des paires **(audio, transcription exacte)**. La seule façon d'obtenir une transcription *garantie*
    est la **dictée guidée** : on **donne** la phrase, le locuteur la **lit** → le texte est connu d'avance.
- **Pourquoi maintenant** : le locuteur `esse` (informaticien, natif bci) est **prêt à travailler**.
  Un lot de **206 phrases agricoles baoulé** (15 filières, validées par le locuteur, caractères
  `ɛ ɔ ɲ` corrects) est **prêt** (`phrases_baoule_208.csv`). Il manque **l'écran de collecte** et
  **l'export** pour transformer ces phrases en dataset.
- **Contrainte forte** (rappel ADR-0034 / persistance corrigée 2026-08-24) : les audios vivent dans
  `/data` (bind mount Contabo `~/wourri-lqe-data`), les métadonnées dans **Postgres** (jamais perdues).
- **Contrainte OCP** : « extensible mais non modifiable » — on **ajoute** un module ; on ne touche pas
  au flux `productions` existant ni aux fichiers gelés.

## Questions posées avant la décision

1. Où stocker les paires de dictée ? (réutiliser `productions` vs table dédiée)
2. Quel **format d'export** pour que Colab l'ingère sans friction ?
3. Convertit-on l'audio côté serveur (16 kHz mono WAV) ou côté Colab ?
4. Quel **modèle** cible-t-on pour le fine-tune ?

Réponses obtenues (discussion 2026-08-25 + faits vérifiés) :

- Q1 → **table dédiée** : la dictée est un *mode de collecte différent* (texte **imposé**, pas produit),
  avec un cycle de vie propre (`todo` → `recorded`) qui **ne mappe pas** sur `bronze→accepter→promouvoir`,
  et qui ne doit **pas polluer la matrice de parité** (un audio de dictée ne « couvre » aucun concept).
- Q2 → **format standard Common Voice / HF `audiofolder`** : un dossier de clips + un `metadata.csv`
  (`file_name`, `transcription`, …). C'est **exactement** ce que consomment `datasets.load_dataset("audiofolder")`,
  les scripts d'exemple Wav2Vec2/Whisper de HF, et `jiwer` (le notebook #479 fait déjà `path`/`sentence`).
- Q3 → **côté Colab** : le navigateur produit du **webm/opus** ; le rééchantillonnage 16 kHz mono se fait
  là où le GPU/entraînement est déjà (`librosa.load(path, sr=16000)`). Garde le backend atelier **léger**
  (pas de dépendance ffmpeg serveur, cohérent OCP).
- Q4 → **différé** : le choix du modèle dépend des **résultats du benchmark #479/#473** (CER mesuré).
  Cet ADR décide **la collecte et le dataset**, pas le modèle. Le fine-tune (#474) = **ADR séparé**,
  gaté sur le benchmark.

## Options étudiées

### Option A — Table dédiée `lqe.dictation` + export `audiofolder` (retenue proposée)

- **Description** : nouvelle table `lqe.dictation` (prompt imposé + audio + statut `todo`/`recorded`),
  un module `dictation` (repo + routes) **greffé** sur l'atelier ; réutilise l'auth RBAC et l'`AudioStore`
  existants (OCP). Import des phrases par l'admin ; écran **Dictée** pour le locuteur (lit → enregistre →
  suivante) ; **export ZIP** `audio/*.webm` + `metadata.csv` (contrat HF).
- **Avantages** : transcription **garantie** (texte imposé) → dataset **directement exploitable** ; **zéro
  pollution** de la matrice de parité ; réutilise l'infra audio+Postgres déjà durcie (persistance corrigée) ;
  format d'export **standard** → maillon ③ (Colab) cohérent sans code de conversion maison ; scale à
  d'autres langues (langue = donnée, comme ADR-0034).
- **Inconvénients** : une table + un module de plus dans l'atelier.
- **Coût** : moyen-faible — surtout du **câblage sur l'existant** (`get_conn`, `_row`, `AudioStore`,
  patterns de `productions_repo`/`routers`).
- **Compatibilité** : respecte OCP (ajout pur), « zéro `if`-langue », amende/étend ADR-0034 sans le modifier.

### Option B — Réutiliser `lqe.productions` (mode « dictée » via un flag)

- Rapide en apparence, mais : mélange **deux buts** (parité vs entraînement) dans une table, **pollue la
  matrice de couverture** (il faudrait des `WHERE` partout pour exclure la dictée → viole « zéro `if` »),
  et force le cycle `bronze→…` inadapté à `todo/recorded`. **Dette structurelle** immédiate.

### Option C — Collecte hors atelier (upload de fichiers / Google Forms / CSV manuel)

- Pas de garantie de paire audio↔texte, pas de suivi de progression, **hors** de l'infra de persistance
  qu'on vient de sécuriser. Refait à la main ce que l'atelier fait déjà. **Rejetée.**

### Comparatif

| Critère | A (retenue) | B | C |
|---|---|---|---|
| Transcription garantie | ✅ texte imposé | ✅ | ⚠️ manuel, fragile |
| Pollution matrice parité | ✅ aucune | ❌ forte | ✅ (hors atelier) |
| `if`-langue / `if`-mode en dur | ✅ zéro | ❌ inévitable | — |
| Réutilise infra audio/Postgres durcie | ✅ | ✅ | ❌ |
| Export standard pour Colab | ✅ `audiofolder` | ✅ (si ajouté) | ⚠️ ad hoc |
| Coût / délai | moyen-faible | faible mais dette | faible mais jetable |

## Décision

**Option retenue** : **A** — table dédiée `lqe.dictation` + export `audiofolder`.

**Justification** : c'est la seule qui donne une **transcription garantie** (condition *sine qua non* d'un
dataset ASR) **sans** polluer la parité (ADR-0034) ni violer « zéro `if` », tout en réutilisant l'infra
audio/Postgres qu'on vient de fiabiliser. Le format d'export standard rend le maillon ③ (Colab) cohérent
« out of the box ».

**Périmètre précis de cet ADR** (maillons ① et ②) :

1. **Table `lqe.dictation`** — colonnes : `id` (identity), `language`, `filiere`, `text_local` (phrase
   imposée), `text_fr`, `prompt_hash` (idempotence import), `audio_url` (NULL tant que non lu), `status`
   (`todo`/`recorded`), `recorded_by`, `recorded_at`, `created_at`. Index unique `(language, prompt_hash)`
   (ré-import idempotent) + index `(language, status)`.
2. **`dictation_repo.py`** — `import_prompts` (bulk `INSERT … ON CONFLICT DO NOTHING`), `list_prompts`,
   `counts`, `set_recorded` (garde par langue), `export_rows`.
3. **`routers/dictation.py`** — `POST /dictation/import` (admin), `GET /dictation/prompts` +
   `GET /dictation/progress` (locuteur, sa langue), `POST /dictation/{id}/audio` (locuteur, multipart →
   `AudioStore`), `GET /dictation/export` (admin → **ZIP** `audio/` + `metadata.csv`).
4. **`metadata.csv`** (contrat) : `file_name,transcription,language,filiere,text_fr` — `file_name` +
   `transcription` = convention HF `audiofolder` ; les autres colonnes = métadonnées.
5. **Front `DictationView.vue`** — écran Dictée (phrase imposée → `MediaRecorder` → soumettre → suivante,
   progression `X/N`) ; boutons admin **Importer** (le CSV des 206 phrases) et **Exporter le dataset**.
6. **Audio** : stocké **tel quel** (webm/opus) via l'`AudioStore` existant ; rééchantillonnage 16 kHz mono
   **au moment du fine-tune** (Colab), pas côté serveur.

**Hors périmètre (différé, ADR séparé)** : le **choix du modèle** et le **fine-tune** (#474), gatés sur
le **CER du benchmark** #479/#473.

## Conséquences

- **Positives** : premier **dataset ASR baoulé supervisé** de Wourri (paires garanties) ; export
  standard → fine-tune reproductible ; module isolé (n'affecte ni le moteur ni le flux parité).
- **Négatives assumées** : une table + un module de plus ; l'audio n'est pas normalisé côté serveur
  (assumé — la normalisation vit dans le notebook d'entraînement).
- **Migration / travail induit** : `db/migrations/004_dictation.sql` ; `app/services/dictation_repo.py` ;
  `app/routers/dictation.py` (câblé dans `main.py`) ; `wouri-lqe-web/src/views/DictationView.vue` (+ route,
  + entrées API) ; tests `pytest` sur Postgres réel (`lqe_test`). **Rollback** : la table et le module sont
  additifs → `DROP TABLE dictation` + retrait du routeur, aucun impact sur `productions`.
- **Verrous futurs** : le contrat `metadata.csv` devient l'entrée du notebook de fine-tune → le figer.
- **Dettes tracées** : (1) pas de conversion audio serveur (déportée Colab) ; (2) qualité audio non
  contrôlée automatiquement (silence/clipping) — revue humaine pour l'instant.

## Références

- ADR liés : **ADR-0034** (atelier de parité — *étendu* ici avec un 2ᵉ mode de collecte, non modifié) ;
  **ADR-0033** (atelier service séparé) ; **ADR-0003** (plan Omnilingual — volet « comprendre »).
- Benchmark : `docs/benchmarks/0003-asr-baoule-evaluation.md` + `finetune/colab/asr_baoule_benchmark.ipynb`
  (PR #479) — mesure le CER qui **gatera** le choix de modèle (#474, ADR à venir).
- Format dataset : HF `datasets` `audiofolder` (`file_name` + `metadata.csv`) ; Common Voice
  (`path`/`sentence`) — conventions consommées par les scripts de fine-tune Wav2Vec2/Whisper.
- Sources phrases : lot locuteur `esse` (206 phrases, 15 filières) → `phrases_baoule_208.csv`.

## Historique

- 2026-08-25 — **proposé** (Option A).
- 2026-08-25 — **accepté** (Option A). Issouf délègue le choix technique en exigeant « la meilleure option, la plus rigoureuse, pas de bricolage ». L'Option A **est** ce choix : l'Option B (réutiliser `productions`) est la dette structurelle écartée (flags + `WHERE` partout → viole « zéro `if` » d'ADR-0034).
