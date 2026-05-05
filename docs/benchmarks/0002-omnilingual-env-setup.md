# Benchmark #0002 — Environnement Omnilingual ASR (Phase 1)

**Statut** : ✅ Phase 1 validée 2026-05-04 (3 critères sur 4, le 4e à reconfirmer en 2e session)
**Date de création** : 2026-05-03
**Date de validation** : 2026-05-04
**Décision qu'il informe** : exécution de [ADR-0003](../adr/0003-plan-ajout-omnilingual.md) Phase 1
**Contexte** : [ADR-0002](../adr/0002-ajout-provider-omnilingual.md) — ajout d'un provider Omnilingual

---

## 1. Objectif

Documenter un environnement d'installation **reproductible** d'Omnilingual ASR
permettant de charger le modèle 300M et transcrire 1 audio dioula sans crash,
sur Colab T4.

Le critère de sortie ADR-0003 exige que la procédure soit **reproductible par
Ruben sur une 2ème session Colab** sans intervention.

---

## 2. Environnement cible

| Composant | Valeur validée | Pourquoi |
|---|---|---|
| Plateforme | Google Colab (T4 GPU gratuit) | Pas de GPU NVIDIA local (Intel Iris Xe), cf. ADR-0002 |
| Python | 3.12.13 (Colab par défaut 2026-05) | Compatibilité fairseq2 |
| CUDA | 12.x (driver 580) | Aligné avec torch 2.8.0 |
| GPU | NVIDIA T4 (15.36 GB VRAM) | Suffisant pour 300M (peak 0.65 GB) et 1B |

---

## 3. Versions packages — figées après validation Phase 1

| Package | Version | Source |
|---|---|---|
| `omnilingual-asr` | **0.1.0** | PyPI (Apache 2.0) |
| `fairseq2` | **0.6** | PyPI |
| `torch` | **2.8.0** | PyPI (forcer cette version) |
| `torchaudio` | **2.8.0** | PyPI (alignement obligatoire) |
| `torchvision` | **0.23.0** | PyPI (alignement obligatoire) |

> **Important** : ces versions sont **interdépendantes**. Toute déviation
> recasse la cascade torch/torchaudio/torchvision (cf. section 5).

---

## 4. Procédure d'install reproductible

### 4.1 Pré-requis

1. Compte Google avec accès Colab gratuit
2. Runtime Colab configuré sur **T4 GPU** (Runtime → Change runtime type → T4 GPU)
3. Notebook ouvert : `wouri-api/finetune/colab/omnilingual_smoke_test.ipynb`
4. Un fichier MP3 dioula (Common Voice dyu v24) uploadé dans `/content/`

### 4.2 Étapes d'install (séquence Colab)

**Cellule unique d'install (5-7 min)** :

```python
!pip install --quiet omnilingual-asr fairseq2
!pip uninstall -y torch torchaudio torchvision
!pip install --quiet torch==2.8.0 torchaudio==2.8.0 torchvision==0.23.0
```

> **Ne PAS faire les `pip install` séparément** : pip peut alors choisir des
> versions intermédiaires non compatibles. Toujours désinstaller le stack
> torch d'un coup puis réinstaller en une seule commande.

### 4.3 ⚠️ Restart de session OBLIGATOIRE après install

**Avant d'utiliser quoi que ce soit** :

1. Menu **Exécution** → **Redémarrer la session**
2. Confirmer **Oui**

**ATTENTION — distinguer 2 options similaires** :

| Option menu Exécution | Effet |
|---|---|
| ✅ **Redémarrer la session** | Vide la mémoire Python, garde les packages installés |
| ❌ **Réinitialiser tout l'environnement d'exécution** | **SUPPRIME tous les packages** → 7 min reperdues |

### 4.4 Vérification post-install (après restart)

```python
import importlib.metadata as md
for pkg in ["omnilingual-asr", "fairseq2", "torch", "torchaudio", "torchvision"]:
    print(f"{pkg}: {md.version(pkg)}")

import torch
assert torch.cuda.is_available(), "GPU CUDA requis"
print(f"GPU: {torch.cuda.get_device_name(0)}")
```

Output attendu (validé 2026-05-04) :
```
omnilingual-asr: 0.1.0
fairseq2: 0.6
torch: 2.8.0+cu128
torchaudio: 2.8.0
torchvision: 0.23.0
GPU: Tesla T4
```

---

## 5. Pièges rencontrés et résolus (issue #61 fairseq2)

L'[issue #61 facebookresearch/omnilingual-asr](https://github.com/facebookresearch/omnilingual-asr/issues/61)
documente l'instabilité de la toolchain fairseq2. Voici les 3 manifestations
concrètes rencontrées pendant Phase 1, et leurs solutions appliquées.

### 5.1 Piège #1 — ABI numpy break

**Symptôme** :
```
ValueError: numpy.dtype size changed, may indicate binary incompatibility.
Expected 96 from C header, got 88 from PyObject
```

**Cause** : Colab démarre avec `numpy 2.x` chargé en mémoire par d'autres
modules (jax, opencv, etc.). L'install fairseq2 downgrade `numpy` à 1.26.4
sur disque. Mais en mémoire, les modules torch._dynamo restent liés à 2.x
→ conflit binaire.

**Solution** : redémarrer la session après install (cf. 4.3). Python recharge
proprement numpy 1.26.4 depuis le disque.

### 5.2 Piège #2 — Mismatch CUDA torchaudio

**Symptôme** :
```
OSError: libcudart.so.13: cannot open shared object file
```

**Cause** : Colab préinstalle `torchaudio 2.10/2.11` compilé pour CUDA 13.
fairseq2 downgrade torch à 2.8.0 (CUDA 12). torchaudio cherche `libcudart.so.13`
qui n'est pas installé sur la machine.

**Solution** : aligner torchaudio sur torch 2.8.0 (`torchaudio==2.8.0`).
Inclus dans la commande d'install 4.2.

### 5.3 Piège #3 — Cascade torchvision::nms

**Symptôme** :
```
RuntimeError: operator torchvision::nms does not exist
```

**Cause** : `torcheval` (dépendance de `fairseq2.metrics`) charge `torchvision`.
Colab préinstalle `torchvision 0.25+cu128` lié à torch 2.10. Avec torch 2.8.0,
les ops C++ de torchvision ne sont pas exposées.

**Solution** : aligner torchvision sur torch 2.8.0 (`torchvision==0.23.0`).
Inclus dans la commande d'install 4.2.

### 5.4 Piège bonus — Session Colab perdue après inactivité

**Symptôme** : `ModuleNotFoundError: No module named 'omnilingual_asr'` après
> 90 min d'inactivité ou > 12 h de session.

**Cause** : Colab gratuit déconnecte les runtimes inactifs et supprime
l'environnement (packages compris).

**Solution** : refaire l'install + restart. Pour limiter, soit :
- Sauvegarder une copie du notebook dans Drive (le code est sauvé, pas les packages)
- Utiliser Colab Pro (sessions plus longues)
- Long terme : monter Drive et installer dans un dossier persistent (optimisation Sprint ultérieur)

---

## 6. Résultats smoke test (validés 2026-05-04)

### 6.1 Critères de sortie ADR-0003 Phase 1

| Critère | Cible | Mesuré | Statut |
|---|---|---|---|
| Notebook exécute sans crash sur Colab T4 | binaire | OUI | ✅ |
| Modèle 300M charge en < 60 s | < 60 s | **27.8 s** | ✅ |
| 1 audio dioula transcrit (output non vide) | non vide | `"éga kene a"` | ✅ |
| Doc reproduit sur 2ème session Colab | binaire | À reconfirmer | ⏳ |

**3 critères sur 4 validés.** Le 4e (reproduction) sera reconfirmé lors de la prochaine session Colab.

### 6.2 Mesures détaillées

| Métrique | Valeur observée |
|---|---|
| Temps install (1ère fois) | ~5-7 minutes (download ~1.5 GB) |
| Temps chargement modèle 300M (1ère fois, download HF) | 16-28 s (variable selon bande passante) |
| Temps chargement modèle 300M (cache HF) | < 30 s |
| RAM Python (delta après chargement) | +0.57 GB |
| VRAM GPU (peak) | 0.65 GB / 15.36 GB |
| Latence inférence (audio 2.81s) | 0.40 s |
| **Real-Time Factor (RTF)** | **0.142** (7× plus rapide que le temps réel) |

### 6.3 Transcription test

| | |
|---|---|
| Audio source | `common_voice_dyu_38389110.mp3` (Common Voice dyu v24, 32 kHz) |
| Durée | 2.81 s |
| Référence (ground truth) | `I ka kɛnɛ wa?` ("Comment vas-tu ?") |
| Sortie Omnilingual 300M (`dyu_Latn`) | `éga kene a` |
| Match exact | NON |
| Évaluation qualitative | Texte dioula reconnaissable (`kene` ≈ `kɛnɛ`, perte du diacritique ɛ). Pas de hallucination français/anglais. Modèle a correctement identifié la langue. |

### 6.4 Limites identifiées (à mesurer en Phase 3)

- **Modèle 300M = le plus petit**. Le **1B** sera testé en Phase 3 (qualité supérieure attendue, cf. chiffres Meta CER 6.5% sur dyu_Latn pour 7B).
- **Audio très court (2.81s)** → moins de contexte pour le modèle. Tester sur 5-15s en Phase 3.
- **Common Voice 24 sorti déc 2025**, possiblement pas dans le training set Omnilingual (publié nov 2025) → biais possible, à vérifier.
- **Pas de normalisation post-ASR** appliquée ici. En Phase 4, `asr_normalizer.py` corrigera diacritiques.

---

## 7. API officielle omnilingual-asr 0.1.0 (références pour Phase 2)

Validé en Phase 1, à utiliser dans `OmnilingualProvider` (Phase 2) :

### 7.1 Imports

```python
from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline
from omnilingual_asr.models.wav2vec2_llama.lang_ids import supported_langs
```

### 7.2 Liste des langues (1672 codes, format `{lang}_{script}`)

```python
print(len(supported_langs))  # 1672
"dyu_Latn" in supported_langs  # True
"bam_Latn" in supported_langs  # True
"bci_Latn" in supported_langs  # True (baoulé)
"ann_Latn" in supported_langs  # True (proche agni)
```

### 7.3 Chargement modèle

```python
pipeline = ASRInferencePipeline(model_card="omniASR_CTC_300M")
# Variantes : omniASR_CTC_1B, omniASR_LLM_1_2B, omniASR_LLM_7B
# ⚠️ PAS "omniASR_CTC_300M_v2" → ModelNotKnownError
```

### 7.4 Transcription

```python
transcriptions = pipeline.transcribe(
    [chemin_fichier_audio],   # liste de chemins MP3/WAV
    lang=["dyu_Latn"],        # liste codes langues (même longueur)
    batch_size=1,
)
# Retourne : list[str], une transcription par fichier
```

**Note** : le pipeline gère le resampling et le format audio en interne.
Pas besoin de pré-traiter l'audio.

**Limite documentée** : audios < 40 secondes pour les modèles CTC et LLM.

---

## 8. Troubleshooting

### Erreurs courantes

| Erreur | Cause probable | Solution |
|---|---|---|
| `ModuleNotFoundError: No module named 'omnilingual_asr'` | Session Colab perdue OU restart pas fait après install | Refaire install + restart session |
| `ValueError: numpy.dtype size changed` | ABI numpy break (cf. 5.1) | Redémarrer la session (PAS réinitialiser) |
| `OSError: libcudart.so.13` | Mismatch CUDA torchaudio (cf. 5.2) | Aligner torchaudio==2.8.0 |
| `RuntimeError: operator torchvision::nms does not exist` | Cascade torchvision (cf. 5.3) | Aligner torchvision==0.23.0 |
| `ModelNotKnownError: omniASR_CTC_300M_v2 is not a known model` | Mauvais nom model_card | Utiliser `omniASR_CTC_300M` (sans `_v2`) |
| `nvidia-smi: command not found` | Runtime sur CPU | Runtime → Change → T4 GPU |
| `CUDA out of memory` | VRAM saturée | Restart session + vérifier qu'aucun autre modèle n'est chargé |
| `DatasetNotFoundError: 'mozilla-foundation/common_voice_24_0'` | Dataset gated, nécessite token HF | Upload manuel d'un MP3 dans `/content/` |

---

## 9. Reproduction (procédure 2ème session Colab)

Pour valider le critère de sortie "reproduit par Ruben sur 2ème session" :

1. Ouvrir une **nouvelle session Colab** (Runtime → Disconnect and delete runtime)
2. Re-sélectionner T4 GPU
3. Ouvrir le notebook `omnilingual_smoke_test.ipynb` (depuis GitHub branche `feat/omnilingual-asr-provider`)
4. Exécuter Cellule 0 → confirmer Tesla T4
5. Exécuter Cellule 1 (install ~5-7 min)
6. **Restart de session** (Exécution → Redémarrer la session)
7. Re-uploader `common_voice_dyu_38389110.mp3` dans `/content/`
8. Exécuter Cellules 2 → 3 → 4 → 5 → 6 → 7
9. Confirmer que les 3 critères automatiques de Cellule 7 sont ✅
10. Reporter le 4e critère ✅ ici (date + nom session)

**Validation 2ème session** (à remplir) :
- [ ] Date :
- [ ] Temps install (1ère cellule) :
- [ ] Temps chargement modèle :
- [ ] Transcription produite :
- [ ] Tous critères verts : OUI / NON

---

## 10. Hors périmètre Phase 1 (renvois explicites)

- Création du `OmnilingualProvider` Python → **Phase 2** (ADR-0003)
- Benchmark vs NeMo/MMS-dyu → **Phase 3** (cf. [benchmark 0001](0001-asr-dioula-evaluation.md))
- Intégration dans la chain ASR production → **Phase 4**
- Suppression `asr_quality/` → **Phase 5**
- Mesure qualité réelle (WER, CER) → **Phase 3**
- Test du modèle 1B → **Phase 3**

---

## 11. Validation finale Phase 1

- [x] Critère 1 : Notebook exécute sans crash (validé 2026-05-04)
- [x] Critère 2 : Modèle 300M charge en < 60 s (mesuré 27.8 s, validé 2026-05-04)
- [x] Critère 3 : 1 audio dioula transcrit, output non vide (validé 2026-05-04)
- [ ] Critère 4 : Reproduit par Ruben sur 2ème session Colab (à valider)
- [x] API exacte d'`omnilingual_asr` documentée pour Phase 2 (cf. section 7)
- [x] Pièges toolchain documentés (cf. section 5)

**Décision** : 🟢 GO Phase 2 (création du provider) dès validation du critère 4.

---

## Historique

- **2026-05-03** : squelette créé.
- **2026-05-04** : exécution réelle sur Colab T4 par Ruben. 3 critères validés sur 4.
  Doc rempli avec versions exactes, pièges rencontrés, métriques mesurées,
  API officielle documentée.
