# Wourri — Feuille de route stratégique

## Vision

Wourri devient un **IVR intelligent** (Interactive Voice Response) pour les agriculteurs d'Afrique de l'Ouest.
Inspiré de l'approche du **CGIAR** (Viamo, Farm Radio International, AfricaRice) :
- Les systèmes IVR agricoles CGIAR utilisent des réponses pré-enregistrées par thème, validées par des agronomes et des locuteurs natifs, organisées par culture × problème × saison.
- Wourri reprend ce modèle mais remplace l'arbre de menu ("appuyez sur 1 pour le riz") par la compréhension vocale naturelle via ASR + NLU.
- Le paysan parle librement → le NLU fait la navigation → une réponse bambara validée est retournée directement.

**Principe fondamental : ne plus traduire en temps réel. Récupérer du bambara déjà validé.**

---

## Pourquoi ce pivot ?

| Approche actuelle | Problème |
|---|---|
| DeepSeek génère en français → traduit vers bambara | Traducteurs (DeepSeek + NLLB) non fiables sur bambara agricole |
| DeepSeek trad : 36-45% confiance | Bambara grammaticalement cassé |
| NLLB : perd le vocabulaire agricole | `malo` → `jiridenw` (arbres), pas du riz |

**Solution : BD vectorielle + corpus IVR pré-validé**

---

## Architecture cible

### Chemin principal (80% des cas)
```
Audio paysan
    ↓ [ASR NeMo / futur: MALIBA-AI ASR]
Texte bambara
    ↓ [NLU]
Intent + Concepts (ex: QUESTION_SAISON_PLANTATION + CULTURE_RIZ)
    ↓ [BD Vectorielle Chroma]
Recherche : intent × culture × condition → réponse bambara validée
    ↓ [MALIBA-AI TTS]
Audio bambara → paysan
```
Pas de DeepSeek. Pas de traduction. Direct.

### Chemin fallback (20% — questions hors corpus)
```
Multi-générateurs : DeepSeek brouillon + NLLB + templates
    ↓
Pipeline de validation multi-sources
    ↓ (score > 0.75)
Réponse validée → envoyée au paysan + injectée dans la VDB
    ↓ (score ≤ 0.75)
Message de sécurité bambara générique
```

### Rôle de DeepSeek (change)
- **Avant** : génère les réponses en temps réel
- **Après** : génère des brouillons hors-ligne pour alimenter le corpus, validés avant stockage

---

## Liste de travail détaillée

---

### BLOC A — Documentation ✅ FAIT

| Tâche | Description | État |
|---|---|---|
| A1 | Réécrire PROGRESS.md : état réel de tous les composants | ✅ |
| A2 | Créer ROADMAP.md : plan stratégique + liste de travail | ✅ |

---

### BLOC B — BD Vectorielle + Corpus IVR

**Besoin** : "base de phrases pré-enregistrées, prêtes à l'emploi — répertoire de réponses types pour les agriculteurs" (style CGIAR IVR)

| Tâche | Description | Priorité |
|---|---|---|
| B1 | Définir la structure du corpus JSON : `{intent, culture, condition, reponse_bambara, reponse_fr}` | HAUTE |
| B2 | Construire le corpus initial : riz × 8 intents, maïs × 8 intents, arachide × 8 intents = ~120 entrées de base | HAUTE |
| B3 | Intégrer Chroma comme BD vectorielle locale (Python, gratuit, embarqué) | HAUTE |
| B4 | Modifier `chat.py` : NLU → chercher dans VDB avant tout → retourner bambara direct si trouvé | HAUTE |
| B5 | Fallback propre : si VDB ne trouve pas → message sécurité bambara valide (`"N bɛ i dɛmɛ, i ɲinini ko dɔ wɛrɛ"`) | HAUTE |

**Couverture estimée après B** : 75-85% des questions réelles des paysans

---

### BLOC C — Pipeline de validation multi-sources

**Besoin** : "utiliser des métriques de validation concrètes + sources déjà validées + système de vote pondéré"

| Tâche | Description | Priorité |
|---|---|---|
| C1 | Indexer les sources validées | MOYENNE |
| | - FLORES-200 (Meta) : ~1000 phrases bambara traduites par humains | |
| | - Bamada.net : contenu bambara communautaire actif | |
| | - Bamanankan.org : référence académique bambara | |
| | - Joliba FM (Mali) : transcriptions radio bambara oral | |
| | - CommonVoice Mozilla : phrases bambara lues et validées | |
| | - Wikipedia bambara (bm.wikipedia.org) : texte validé | |
| C2 | Vérification lexicale : chaque mot de la phrase vérifié contre les dictionnaires indexés | MOYENNE |
| | → **Taux de concordance lexicale** = % mots reconnus | |
| C3 | Score grammatical : patterns bambara connus (S + bɛ + V, S + ka + V, marqueurs ye/ko...) | MOYENNE |
| | → **Structure grammaticale plausible** | |
| C4 | Vote pondéré multi-sources | MOYENNE |
| | FLORES-200 → 1.0 (validation humaine professionnelle) | |
| | Bamanankan.org → 0.9 (académique) | |
| | Dictionnaire bambara → 0.85 | |
| | Bamada.net → 0.8 (communauté active) | |
| | Joliba FM → 0.8 (oral natif, proche paysan) | |
| | NLLB back-traduction → 0.5 (modèle, pas humain) | |
| | DeepSeek seul → 0.4 (peu de données bambara) | |
| | Feedback paysan implicite → 1.0 (vérité terrain) | |
| C5 | Correction de mots inconnus : mot hors dictionnaire → remplacé par le mot validé le plus proche | MOYENNE |
| | (distance phonétique + règles bambara + contexte sémantique) | |
| C6 | Auto-apprentissage : phrase validée (score > 0.75) → injectée dans la BD vectorielle | MOYENNE |
| | → Le corpus grossit à chaque échange sans intervention manuelle | |
| C7 | Feedback implicite paysan : si suivi cohérent après réponse → signal validation positive loggé | BASSE |
| | → **Compréhensibilité** + **Cohérence avec le contexte** mesurées par comportement réel | |

---

### BLOC D — TTS MALIBA-AI

**Besoin** : "le TTS Coqui peut mal prononcer le bambara — utiliser MALIBA-AI"

| Tâche | Description | Priorité |
|---|---|---|
| D1 | Évaluer MALIBA-AI : API disponible, modèles bambara/dioula, licence, test prononciation | MOYENNE |
| | → Vérifier : gestion des tons (ɛ, ɔ, tons hauts/bas), qualité naturelle, latence | |
| D2 | Intégrer MALIBA-AI en remplacement de `facebook/mms-tts-bam` | MOYENNE |
| D3 | Tester : phrases avec tons bambara prononcées correctement, compréhensibles pour paysan | MOYENNE |

---

### BLOC E — IA Agentique (DeepSeek function calling)

**Besoin** : "où en sommes-nous avec l'IA agentique ?"

| Tâche | Description | Priorité |
|---|---|---|
| E1 | Infrastructure function calling : DeepSeek appelle des outils au lieu de tout générer | BASSE |
| E2 | Météo comme outil : DeepSeek consulte la météo réelle avant de conseiller | BASSE |
| E3 | Calendrier agricole comme outil : conseils saisonniers précis par région | BASSE |

---

## Ordre d'exécution

```
Phase 1 (MAINTENANT)
  ✅ A1, A2 — Documentation à jour

Phase 2 (COURT TERME — Résout le problème principal)
  ⏳ B1 → B2 → B3 → B4 → B5
  → Le paysan reçoit enfin du bambara validé et fiable

Phase 3 (MOYEN TERME — Améliore la qualité et l'autonomie)
  ⏳ C1 → C7 — Pipeline de validation multi-sources
  ⏳ D1 → D3 — MALIBA-AI TTS

Phase 4 (PLUS TARD — IA agentique)
  ⏳ E1 → E3 — Function calling, météo, calendrier
```

---

## Sources et partenaires potentiels

| Organisation | Pertinence | Ressource disponible |
|---|---|---|
| **AfricaRice** (CGIAR, Abidjan) | Riz en Afrique de l'Ouest | Guides riz CI/Mali, variétés locales |
| **IITA** (CGIAR) | Maïs, manioc, igname | Guides culture Afrique subsaharienne |
| **ICRISAT** (CGIAR) | Mil, arachide, sorgho | Guides cultures sahéliennes |
| **ANADER** (Côte d'Ivoire) | Extension agricole CI | Contenu local validé agents terrain |
| **Viamo** | Plateforme IVR agricole Afrique | Contenu IVR bambara existant |
| **Farm Radio International** | Radio + IVR agricole Afrique | Scripts radio bambara |
| **FLORES-200 (Meta)** | Corpus bambara validé | ~1000 phrases humaines multilingues |
| **Bamanankan.org** | Référence académique bambara | Dictionnaire + grammaire |
| **Bamada.net** | Communauté bambara active | Articles, forums validés |
| **Joliba FM** | Radio Mali en bambara | Transcriptions orales natives |

---

## Métriques de succès

| Indicateur | Cible |
|---|---|
| Couverture corpus (% questions couvertes par VDB) | > 80% |
| Taux de concordance lexicale (% mots bambara valides) | > 90% |
| Score de validation moyen des réponses | > 0.75 |
| Latence totale (audio → audio) | < 8s |
| Taux de suivi cohérent paysan (satisfaction implicite) | > 70% |
