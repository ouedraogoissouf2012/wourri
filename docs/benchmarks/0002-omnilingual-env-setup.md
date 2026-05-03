# Benchmark #0002 — Environnement Omnilingual ASR (Phase 1)

**Statut** : 🚧 en cours (squelette créé, à remplir au fur et à mesure des essais Colab)
**Date de création** : 2026-05-03
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

| Composant | Cible | Pourquoi |
|---|---|---|
| Plateforme | Google Colab (T4 GPU gratuit) | Pas de GPU NVIDIA local (Intel Iris Xe), cf. ADR-0002 |
| Python | 3.10 ou 3.11 (par défaut Colab) | Compatibilité fairseq2 |
| PyTorch | fourni par Colab (2.x + CUDA 12) | Ne PAS réinstaller (perd les optims T4) |
| GPU | NVIDIA T4 (16 GB VRAM) | Suffisant pour 300M et 1B (cf. ADR-0002) |

---

## 3. Versions packages (à figer après essais)

| Package | Version testée | Statut | Source |
|---|---|---|---|
| `omnilingual-asr` | _à remplir_ | _à remplir_ | PyPI |
| `fairseq2` | _à remplir_ | _à remplir_ | PyPI |
| `torch` | _à remplir_ | _à remplir_ | Colab par défaut |
| `datasets` (HF) | _à remplir_ | _à remplir_ | PyPI |
| `psutil` | _à remplir_ | _à remplir_ | PyPI |

> **Note** : ce tableau sera figé une fois qu'une combinaison fonctionnelle aura
> été identifiée. Toute installation ultérieure devra reproduire ces versions
> exactes via `pip install pkg==X.Y.Z`.

---

## 4. Procédure d'install reproductible

### 4.1 Pré-requis

1. Compte Google avec accès Colab gratuit
2. Runtime Colab configuré sur **T4 GPU** (Runtime → Change runtime type → T4 GPU)
3. Notebook ouvert : `wouri-api/finetune/colab/omnilingual_smoke_test.ipynb`

### 4.2 Étapes d'install (séquence Colab)

```bash
# Cellule 1 : install
!pip install --quiet omnilingual-asr
!pip install --quiet fairseq2
```

> **Ne PAS réinstaller `torch`** : Colab fournit déjà une build optimisée pour T4
> avec la bonne version CUDA. Réinstaller perd les optimisations et casse souvent
> les dépendances.

### 4.3 Vérification post-install

```python
import importlib.metadata as md
for pkg in ["omnilingual-asr", "fairseq2", "torch"]:
    print(f"{pkg}: {md.version(pkg)}")

import torch
assert torch.cuda.is_available(), "GPU CUDA requis"
print(f"GPU: {torch.cuda.get_device_name(0)}")
```

Output attendu (à compléter après premier run réussi) :
```
omnilingual-asr: <version>
fairseq2: <version>
torch: <version>+cu12x
GPU: Tesla T4
```

---

## 5. Résolution issue #61 fairseq2

**Issue tracker** : [facebookresearch/omnilingual-asr#61](https://github.com/facebookresearch/omnilingual-asr/issues/61)

**Symptôme attendu** : crash à l'install ou à l'import de `fairseq2`, possiblement
lié à `libmkl`, à des incompatibilités CUDA, ou à des dépendances Python manquantes.

### Workaround appliqué

_À remplir après essais_ :
- [ ] Erreur exacte rencontrée :
- [ ] Workaround testé :
- [ ] Workaround validé :

### Si workaround impossible

Time-box 5 jours sur cette résolution. Au-delà : escalade Plan B (Djelia)
documentée dans [ADR-0002](../adr/0002-ajout-provider-omnilingual.md) section
"Option D — rejetée comme principal, retenue comme Plan B".

---

## 6. Résultats smoke test (à remplir après exécution Colab)

### 6.1 Critères de sortie ADR-0003 Phase 1

| Critère | Cible | Mesuré | Statut |
|---|---|---|---|
| Notebook exécute sans crash sur Colab T4 | binaire | _à remplir_ | ⬜ |
| Modèle 300M charge en < 60 s | < 60 s | _à remplir_ | ⬜ |
| 1 audio dioula transcrit (output non vide) | non vide | _à remplir_ | ⬜ |
| Doc reproduit sur 2ème session Colab | binaire | _à remplir_ | ⬜ |

### 6.2 Mesures détaillées

| Métrique | Valeur observée |
|---|---|
| Temps install `omnilingual-asr` + `fairseq2` | _à remplir_ |
| Temps chargement modèle 300M | _à remplir_ |
| RAM Python (delta) | _à remplir_ |
| VRAM GPU (peak) | _à remplir_ |
| Latence inférence (1 audio Common Voice dyu) | _à remplir_ |
| Real-Time Factor (RTF) | _à remplir_ |

### 6.3 Transcription test

| | |
|---|---|
| Audio source | _ID Common Voice ou chemin Drive_ |
| Référence (ground truth) | _texte attendu_ |
| Sortie Omnilingual 300M (`dyu_Latn`) | _texte produit_ |
| Évaluation qualitative | _à remplir, échelle 1-5 ou commentaire libre_ |

---

## 7. Troubleshooting

### Erreurs courantes

| Erreur | Cause probable | Solution |
|---|---|---|
| `ModuleNotFoundError: No module named 'omnilingual_asr'` | Install pas terminé | Re-runner Cellule 1 |
| `CUDA out of memory` | VRAM saturée | Restart runtime + Cellule 1 |
| `nvidia-smi: command not found` | Runtime sur CPU | Runtime → Change → T4 GPU |
| `fairseq2 import error: ...` | Issue #61 fairseq2 | Voir section 5 |

_(Section à enrichir au fil des essais.)_

---

## 8. Reproduction (procédure 2ème session Colab)

Pour valider le critère de sortie "reproduit par Ruben sur 2ème session" :

1. Ouvrir une **nouvelle session Colab** (Runtime → Disconnect and delete runtime)
2. Re-sélectionner T4 GPU
3. Ouvrir le notebook `omnilingual_smoke_test.ipynb` (depuis GitHub ou Drive)
4. Exécuter toutes les cellules dans l'ordre
5. Confirmer que les 4 critères de sortie sont à nouveau atteints
6. Reporter les résultats du 2ème run dans la section 6 (colonne dédiée à ajouter)

---

## 9. Hors périmètre Phase 1

- Création du `OmnilingualProvider` Python → **Phase 2** (ADR-0003)
- Benchmark vs NeMo/MMS-dyu → **Phase 3** (cf. [benchmark 0001](0001-asr-dioula-evaluation.md))
- Intégration dans la chain ASR production → **Phase 4**
- Suppression `asr_quality/` → **Phase 5**

---

## 10. Validation finale Phase 1

Avant de passer en Phase 2, Ruben confirme :

- [ ] Tous les 4 critères de sortie sont VERTS (section 6.1)
- [ ] La doc est suffisamment précise pour qu'un nouvel intervenant reproduise
- [ ] L'API exacte d'`omnilingual_asr` (load, transcribe) est documentée pour Phase 2
- [ ] Décision : **GO Phase 2** (création du provider) OU **STOP + escalade Plan B**

---

## Historique

- **2026-05-03** : squelette créé. À remplir lors du premier essai Colab.
