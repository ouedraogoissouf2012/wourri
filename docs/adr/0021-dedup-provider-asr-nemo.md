# ADR-0021 — Déduplication du provider ASR NeMo Soloni + conversion audio (#303B)

**Statut** : accepté
**Date** : 2026-08-07
**Auteur(s)** : Claude (assistant) sous direction de Ouedraogo Issouf
**Valideur** : Ouedraogo Issouf
**Lié à** : [ADR-0002/0003](.) (chaîne ASR), issue #303, #204 (dette Sprint L)

---

## Contexte

L'audit #303 a relevé une duplication dans la couche ASR. La **partie A** (PR #350)
a supprimé deux modules entièrement morts (`asr_mms_dyu.py`, `asr_ivorian.py`). Cet
ADR traite la **partie B** : une duplication entre du code **vivant**, donc plus
délicate — elle touche le câblage ASR runtime et le préchargement au démarrage.

### Les deux définitions du provider NeMo Soloni

Le modèle bambara NeMo (`RobotsMali/soloni-114m-tdt-ctc-v0`) est chargé par **deux
modules différents**, avec une logique **dupliquée mot pour mot** :

| | `app/services/asr_soloni_nemo.py` (legacy, 175 l.) | `app/services/asr/nemo_provider.py` (canonique, 114 l.) |
|---|---|---|
| Chemin modèle | `NEMO_PATH` (:18) | `NEMO_PATH` (:17) — **identique** |
| Import nemo/torch | try/except (:32) | try/except (:30) — **identique** |
| Config décodeur | beam / malsd_batch / beam_size=4 (:63-72) | beam / malsd_batch / beam_size=4 (:60-69) — **identique** |
| Clé registre | `registry.get("nemo_soloni")` (:78) | `registry.get("nemo_soloni")` (:74) — **PARTAGÉE** |
| Conversion WAV | `_convert_to_wav_16k` (:114) — copie | `transcribe_with_temp_files` → `audio_utils.convert_to_wav_16k` |

- **Consommateur de la version canonique** : `asr/__init__.py` → `ASRChain` → c'est le
  pipeline ASR **réellement exécuté au runtime**.
- **Consommateur de la version legacy** : `app/main.py:23,72` — le **préchargement au
  démarrage** (`get_nemo_model`) et le **statut santé** (`check_nemo_asr_status`).

### Le risque concret : divergence silencieuse (bug latent)

Les deux modules partagent la clé de cache `"nemo_soloni"`
([model_registry.py:10](../../app/services/model_registry.py), health_memory.py:16).
Séquence réelle au démarrage :

1. `main.py` préchauffe via `asr_soloni_nemo.get_nemo_model()` → charge le modèle avec
   la config décodeur **de asr_soloni_nemo**, et le stocke sous `registry["nemo_soloni"]`.
2. Au runtime, `NemoSoloniASR._get_model()` fait `registry.get("nemo_soloni")` → récupère
   le modèle **déjà en cache** ; son propre `_load()` (donc sa propre config décodeur)
   **n'est JAMAIS exécuté**.

Aujourd'hui c'est inoffensif car les deux configs sont identiques. **Mais si un jour
on change la config décodeur d'un seul des deux** (ex. `beam_size` 4→8 dans
`nemo_provider` pour améliorer la précision), le changement est **silencieusement
ignoré** : le runtime sert le modèle préchargé avec l'ancienne config. Aucune erreur,
aucun log — juste une transcription qui n'utilise pas la config qu'on croit. C'est le
type de bug le plus coûteux à diagnostiquer.

### La conversion audio dupliquée

`convert_to_wav_16k` (ffmpeg → WAV 16 kHz mono) existe en plusieurs exemplaires :

- [asr/audio_utils.py:23](../../app/services/asr/audio_utils.py) — **source unique
  documentée** (« Utilisé par tous les ASR providers »), utilisée par le package `asr/`.
- `asr_soloni_nemo.py:114` (`_convert_to_wav_16k`) — copie legacy (part avec le module
  si on le supprime).
- `stt_whisper.py:110` (`convert_audio_to_wav`) — **variante** (signature différente :
  retourne `str | None` ; Whisper est un provider hors du package `asr/`).

Le binaire ffmpeg est déjà centralisé dans `_ffmpeg.py` (`get_ffmpeg`) ; seule la
commande de conversion est recopiée.

## Questions posées avant la décision

1. **Source unique** : le préchargement doit-il pointer vers le provider canonique
   (`asr/nemo_provider.py`) pour éliminer la divergence par construction, ou garder
   deux façades avec un noyau partagé ?
2. **Whisper** : faut-il unifier aussi `stt_whisper.convert_audio_to_wav` (variante, hors
   package `asr/`), ou le laisser (provider séparé, signature différente) ?

## Options étudiées

### Option A — `nemo_provider` comme source unique, suppression du legacy *(recommandée)*

- **Description** : `asr/nemo_provider.py` devient la **seule** définition du provider
  NeMo. On expose dans le package `asr/` une fonction de préchargement et une fonction
  de statut (qui instancient `NemoSoloniASR` et appellent `_get_model()` /
  `is_available()`). `app/main.py` et le routeur santé pointent dessus. On **supprime**
  `asr_soloni_nemo.py` (sa copie `_convert_to_wav_16k` disparaît avec). La clé registre
  `"nemo_soloni"` reste, mais **un seul `_load()` existe** → plus aucune divergence
  possible.
- **Avantages** : élimine la duplication ET le bug latent **par construction** (une seule
  config décodeur, un seul chemin de conversion) ; DRY total ; ~175 lignes retirées.
- **Inconvénients** : touche le **câblage préchargement** de `main.py` (chemin critique au
  démarrage) → à tester (démarrage + statut santé). `transcribe_bambara_nemo` (point
  d'entrée async du legacy) doit être vérifié sans consommateur avant suppression.
- **Coût** : moyen (câblage + vérif démarrage).
- **Compatibilité** : conforme à l'architecture providers (ADR chaîne ASR) ; le legacy
  était une survivance pré-package `asr/`.

### Option B — Noyau NeMo partagé, deux façades conservées

- **Description** : extraire `NEMO_PATH` + le chargement + la config décodeur dans un
  `asr/nemo_core.py`, importé par `nemo_provider` ET `asr_soloni_nemo`. Les deux façades
  subsistent mais partagent une **seule** logique de chargement.
- **Avantages** : moins invasif (préchargement `main.py` inchangé) ; supprime la
  duplication de logique et le risque de divergence de config.
- **Inconvénients** : garde **deux façades** pour la même chose (dette résiduelle,
  confusion « lequel utiliser ? ») ; plus de fichiers que A ; la copie
  `_convert_to_wav_16k` doit être remplacée à la main par `audio_utils.convert_to_wav_16k`.
- **Coût** : moyen.
- **Compatibilité** : ok, mais laisse une ambiguïté architecturale.

### Option C — Statu quo + test-garde de non-divergence

- **Description** : ne rien refactorer ; ajouter un test qui **assert que les deux configs
  décodeur sont identiques** (échoue si l'une diverge), et rediriger la copie
  `_convert_to_wav_16k` vers `audio_utils`.
- **Avantages** : zéro risque runtime ; effort minimal ; ferme la trappe de la divergence.
- **Inconvénients** : **ne supprime pas la duplication** (viole DRY) ; le test surveille
  le symptôme au lieu de guérir la cause ; deux modules NeMo demeurent.
- **Coût** : faible.
- **Compatibilité** : ok mais laisse la dette structurelle.

### Comparatif

| Critère | A (source unique) | B (noyau partagé) | C (test-garde) |
|---|---|---|---|
| Élimine la duplication | ✅ totale | ⚠️ logique oui, façades non | ❌ |
| Supprime le bug latent | ✅ par construction | ✅ | ⚠️ surveillé, pas supprimé |
| Impact préchargement `main.py` | 🟠 oui (à tester) | 🟢 aucun | 🟢 aucun |
| Lignes nettes retirées | ~175 | ~120 | ~0 |
| Dette résiduelle | aucune | 2 façades | 2 modules |
| Coût / risque | moyen | moyen | faible |

## Décision

**Option retenue** : **A — `nemo_provider` comme source unique** (validée par Ruben le 2026-08-07).
Justification : **Option A** — c'est la seule qui supprime à la fois la
duplication et le bug latent *par construction*, en alignant préchargement et runtime sur
une source unique. Le surcoût (câblage `main.py`) est maîtrisable par un test de démarrage.
Pour la **Q2 (Whisper)** : laisser `stt_whisper.convert_audio_to_wav` hors périmètre (signature
différente, provider séparé) et le traiter plus tard si besoin — éviter d'élargir le blast radius.

## Conséquences

- **Positives** : une seule définition du provider NeMo ; impossible de faire diverger
  préchargement et runtime ; une seule fonction de conversion ffmpeg dans la couche `asr/`.
- **Négatives assumées** : Option A modifie le préchargement (chemin critique) — nécessite
  une vérification de démarrage réelle (pas seulement des tests unitaires mockés).
- **Migration / travail induit (si A retenue)** :
  1. Ajouter dans `asr/` : `preload_nemo()` + `nemo_status()` (ou équivalent) s'appuyant sur
     `NemoSoloniASR`.
  2. Rediriger `app/main.py:23,72` et le routeur santé vers ces fonctions.
  3. Vérifier qu'aucun code ne consomme `transcribe_bambara_nemo` / `get_nemo_model` du legacy.
  4. Supprimer `asr_soloni_nemo.py`.
  5. Tests : suite unit + **démarrage réel** (préchargement charge le modèle sous
     `"nemo_soloni"`, statut santé cohérent) + non-régression transcription.
  - **Rollback** : réversible (restaurer `asr_soloni_nemo.py` + le câblage `main.py`).
- **Verrou futur** : toute évolution de la config décodeur NeMo se fait désormais à **un
  seul endroit** (`nemo_provider._get_model`).

## Références

- Issue #303 (modules ASR morts/dupliqués) ; PR #350 (partie A)
- `app/services/asr_soloni_nemo.py`, `app/services/asr/nemo_provider.py`
- `app/services/asr/audio_utils.py` (conversion + pipeline temp files)
- `app/main.py:23,72` (préchargement), `app/services/model_registry.py` (clé `nemo_soloni`)
- `app/services/_ffmpeg.py` (binaire ffmpeg centralisé)

## Historique

- 2026-08-07 — rédaction initiale (statut proposé), après cartographie du code réel.
  Recommandation Option A (source unique), en attente de validation.
- 2026-08-07 — **accepté** par Ruben (Option A). Passage en Phase 5 (implémentation).
