# Wourri — Journal de progression

## Contexte du projet

**Wourri** = assistant agricole WhatsApp pour l'Afrique de l'Ouest (Côte d'Ivoire / Mali)
- Serveur WhatsApp (Node.js / Baileys) → reçoit messages vocaux des paysans
- API Python (FastAPI, port 8000) → traitement IA (ASR, NLU, TTS, météo, chat)
- Objectif : permettre aux agriculteurs de parler en bambara/dioula et recevoir des conseils agricoles dans leur langue

---

## Session 1 — Intégration Soloni (ASR Bambara)

**Date** : 27 février 2026

### Problèmes résolus

| # | Problème | Cause | Solution |
|---|---|---|---|
| 1 | `soloni_ctc_single.onnx` plante sherpa-onnx | IR version 10 (torch dynamo) | Fusion via NeMo export natif (opset17 = IR v8) |
| 2 | `onnx.compose.merge_models` échoue | Noms de nœuds internes en conflit | `compose.add_prefix("ctc_")` sur le modèle CTC |
| 3 | "No graph was found in the protobuf" | Chemin `propre à moi` avec `à` → C++ ORT ne lit pas | Copie modèle vers `C:\soloni\` (sans accent) |
| 4 | "vocab_size does not exist in metadata" | Métadonnée absente dans le ONNX fusionné | Ajout `vocab_size = "1025"` dans `model.metadata_props` |
| 5 | "subsampling_factor does not exist" | Métadonnée absente | Ajout `subsampling_factor = "8"` |
| 6 | `invalid unordered_map<K,T> key` | Ordre outputs inversé | Rename `ctc_logprobs → log_probs` + reorder |
| 7 | Transcription très mauvaise | `subsampling_factor` mis à 4 (vrai = 8) | Diagnostic par forward pass |
| 8 | Tête CTC auxiliaire trop imprécise | CTC = décodeur secondaire du TDT | Migration vers **NeMo TDT direct** |

### Fichiers clés
- `app/services/asr_soloni_nemo.py` — service NeMo TDT **[ACTIF]**
- `app/routers/asr.py` — route `/api/asr/transcribe-and-translate`
- Modèle : `RobotsMali/soloni-114m-tdt-ctc-v0` (NeMo TDT)

---

## Session 2 — Amélioration traduction Bambara → Français

**Date** : 27 février 2026

### Problèmes résolus

| # | Problème | Solution |
|---|---|---|
| 1 | `"an ni sɔgɔma"` non reconnu comme salutation | Ajout variantes NeMo dans `_BAM_GREETING_PREFIXES` |
| 2 | `b'a fɛ` (contraction parlée) non traduit | Ajout patterns `n b'a fɛ ka` → "Je veux" |
| 3 | Phrases NeMo manquantes dans le dictionnaire | Ajout 20+ phrases NeMo-variante dans `bambara_phrases.json` |

---

## Session 3 — NLU, DeepSeek, pipeline complet

**Date** : 1-2 mars 2026

### Bug NeMo beam search
- **Problème** : `results[0]` retournait une liste d'objets `Hypothesis` avec `beam_size=4`
- **Fix** : `if isinstance(result, list): result = result[0]`
- **Décodeur** : changé vers `malsd_batch` (recommandé NeMo pour modèles TDT)

### Normalizer ASR
- **Fichier créé** : `app/services/asr_bambara_normalizer.py`
- **Rôle** : corrige les fusions syllabiques NeMo (`anisogma → a ni sɔgɔma`, `inice → i ni cɛ`, etc.)
- Appelé après chaque transcription dans `asr_soloni_nemo.py`

### NLU — Faux positifs corrigés

| Intent | Problème | Fix appliqué |
|---|---|---|
| ANIMAL_PORC | `farin` = "courageux" en bambara → faux positifs | Retiré, remplacé par `woro`, `bolofin` |
| QUESTION_SAISON_PLANTATION | Se déclenchait sur culture seule | Ajout `required_at_least_one_of: ["ACTION_PLANTER", "TEMPS_SAISON_*"]` |
| QUESTION_RECOLTE | Se déclenchait sur culture seule (priorité 4 > CONSEIL_PRODUCTION 3) | Ajout `required_at_least_one_of: ["ACTION_RECOLTER"]` |
| QUESTION_IRRIGATION | Se déclenchait sur culture seule | Ajout `required_at_least_one_of: ["ACTION_ARROSER", "PROBLEME_SECHERESSE"]` |
| QUESTION_ENGRAIS | Se déclenchait sur culture seule | Ajout `required_at_least_one_of: ["ENGRAIS_FERTILISANT"]` |
| QUESTION_STOCKAGE | Se déclenchait sur culture seule | Ajout `required_at_least_one_of: ["ACTION_STOCKER"]` |
| QUESTION_VENTE | Se déclenchait sans signal de vente | Ajout `required_at_least_one_of: ["ACTION_VENDRE"]` |

**Résultat** : "an ni sɔgɔma n bɛ ka malo sene" → CONSEIL_PRODUCTION ✅ (avant : QUESTION_RECOLTE ❌)

### DeepSeek prompt restructuré
- Exactement **3 phrases courtes** (max 12 mots chacune)
- Vocabulaire simple, dioula ivoirien parlé
- Interdit : jargon technique, markdown, plus de 3 phrases
- Tutoyer systématiquement

### Enrichissement contexte DeepSeek
- `chat.py` : ajout préfixe `[Paysan cultive: riz]` avant d'envoyer à DeepSeek
- DeepSeek comprend le contexte culture/animal sans que le paysan le répète

### Seuil de confiance traduction relevé
- **Avant** : `confidence > 0.0` → toute traduction acceptée même à 36%
- **Après** : `confidence > 0.6` → NLLB utilisé si DeepSeek traduction < 60%

### Diagnostic traduction FR→Bambara
- **Problème identifié** : ni DeepSeek ni NLLB ne produisent du bambara agricole fiable
  - DeepSeek : hallucine la grammaire bambara (données d'entraînement insuffisantes)
  - NLLB : perd le vocabulaire spécifique (`malo`→`jiridenw`, `kaba`→`dumuni nafama`)
- **Décision** : changer d'architecture → ne plus traduire en temps réel

---

## État actuel des composants

| Composant | État | Notes |
|---|---|---|
| ASR Soloni NeMo TDT | ✅ Fonctionnel | ~3s/requête sur CPU |
| Normalizer ASR bambara | ✅ Actif | Corrige fusions syllabiques NeMo |
| Pipeline WhatsApp end-to-end | ✅ Fonctionnel | Node.js → FastAPI → réponse audio |
| NLU — Classification intent | ✅ Corrigé | 7 intents avec `required_at_least_one_of` |
| NLU — Extraction concepts | ✅ Fonctionnel | 19 cultures/animaux + 10 actions + contextes |
| DeepSeek — Réponse française | ✅ Fonctionnel | 3 phrases courtes, vocabulaire simple |
| Traduction FR→Bambara | ❌ Défaillante | Architecture à changer (voir ROADMAP) |
| TTS Bambara (MMS-TTS-BAM) | ⚠️ Acceptable | Prononciation tons imprécise → remplacer par MALIBA-AI |
| TTS Français (Edge-TTS) | ✅ Fonctionnel | |
| Météo (Open-Meteo) | ✅ Fonctionnel | 59 villes CI |

---

## Architecture actuelle (pipeline complet)

```
Audio WhatsApp paysan (OGG)
    ↓
Node.js / Baileys (port 3001)
    ↓ bytes audio
FastAPI (port 8000)
    ↓
/api/asr/transcribe-and-translate
    ↓ ffmpeg → WAV 16kHz
    ↓ NeMo TDT model.transcribe()
    ↓ asr_bambara_normalizer (correction fusions)
    ↓ texte bambara propre
    ↓ NLU : concepts + intent + phrase française reconstruite
    ↓
/api/chat/
    ↓ [Paysan cultive: X] + phrase française NLU
    ↓ Météo Bouaké/ville
    ↓ DeepSeek → réponse française 3 phrases
    ↓ Traduction FR→BAM (DeepSeek+ancres, fallback NLLB) ← MAILLON FAIBLE
    ↓
TTS MMS-TTS-BAM → OGG audio
    ↓
WhatsApp paysan
```
