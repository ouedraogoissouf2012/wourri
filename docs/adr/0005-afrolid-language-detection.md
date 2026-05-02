# ADR-0005 — Détection de langue textuelle via AfroLID

**Statut** : proposé (en attente validation Ruben)
**Date** : 2026-04-23
**Auteur** : Claude (assistant)
**Valideur** : Ruben
**Issue source** : [#98](https://github.com/ouedraogoissouf2012/wourri/issues/98) — [P1-03] du [PLAN_ACTION_2026-04.md](../PLAN_ACTION_2026-04.md)

---

## Contexte

### Pipeline actuel — comment Wourri détermine la langue

| Cas | Mécanisme actuel |
|---|---|
| **Texte WhatsApp** | Aucune détection. Le user déclare sa langue à l'onboarding (`prefs.language` = "french" / "dioula" / "both"), tout le pipeline fait confiance à cette déclaration |
| **Audio en mode dioula** | Routé direct vers ASR Bambara (`NemoSoloniASR` puis fallback `MMSDyuASR`), pas de détection |
| **Audio en mode français** | `Faster-Whisper` transcrit + retourne `info.language` + `info.language_probability` (auto-détection native Whisper) |
| **Code-switching FR ↔ bambara** | Heuristique [`is_likely_dioula_input(text, lang_prob)`](../../app/services/stt_whisper.py) — environ 50 patterns hardcodés (phrases incohérentes, mots fréquents, onomatopées) qui détectent un audio bambara mal transcrit en français |

### Limites identifiées du pipeline actuel

1. **Confiance aveugle dans la déclaration utilisateur** : un user qui a déclaré "français" peut taper en bambara (`i ni cɛ, je veux du riz`) et le pipeline traite tout en français. La salutation `i ni cɛ` n'est pas reconnue, l'expérience utilisateur dégrade.

2. **Code-switching texte non géré** : aucun équivalent à `is_likely_dioula_input` pour les messages texte. Côté audio, `Bambara-ASR-v2` (M4 du benchmark ADR-0003) gère nativement le code-switching FR-bambara, mais cette capacité n'est pas exploitée si l'entrée est textuelle.

3. **Anti-pattern hardcoding** : `is_likely_dioula_input` est une liste de patterns ad-hoc dans [stt_whisper.py:769-810](../../app/services/stt_whisper.py). Maintenance manuelle, faux positifs/négatifs, non scalable. Doctrine projet : éviter le hardcoding (cf. [constraints.md](../constraints.md)).

4. **Non scalable aux 50+ langues cibles** ([vision.md](../vision.md)) : ajouter baoulé, bété, agni, wolof, peul, mooré… nécessiterait 50 heuristiques distinctes. Ingérable.

5. **Pas d'observabilité** : aucune métrique sur la fréquence des cas où la déclaration utilisateur est fausse. On vole à l'aveugle sur la qualité du routage.

### Pourquoi traiter ça maintenant

L'implémentation effective d'AfroLID est **différée** (P2 ou Sprint 3, après stabilisation Omnilingual ASR via [ADR-0003](0003-plan-ajout-omnilingual.md)). Mais **graver la décision maintenant** permet :

- Aux futurs ADRs (baoulé en P2, IVR téléphonique en P3) de référencer une stratégie de détection langue claire au lieu de re-débattre
- D'éviter qu'on hardcode 5 nouvelles heuristiques entre temps "en attendant"
- De documenter la dette `is_likely_dioula_input` comme "à supprimer quand AfroLID sera intégré"

C'est un travail de **cohérence architecturale**, pas une livraison de feature.

---

## Options étudiées

### Option A — AfroLID (UBC-NLP, retenue)

- **Source** : [github.com/UBC-NLP/afrolid](https://github.com/UBC-NLP/afrolid) — paper [arXiv 2210.11744](https://arxiv.org/abs/2210.11744)
- **Architecture** : Transformer language identification, pré-entraîné sur 517 langues africaines
- **Couverture** : bambara/dioula natif, baoulé, bété, agni, wolof, peul, hausa, etc. — couvre tout l'horizon vision Wourri
- **Licence** : ✅ **Apache 2.0** (vérifié sur [github.com/UBC-NLP/afrolid/LICENSE](https://github.com/UBC-NLP/afrolid/blob/main/LICENSE) le 2026-04-23) → compatible produit payant
- **Précision papier** : F1 macro > 95 % sur les 517 langues
- **Précision dioula CI spécifique** : non publiée → à mesurer en POC
- **Estimations à valider** : modèle ~200-500 MB, latence ~10-50 ms par requête, RAM ~500 MB

### Option B — FastText langid (Meta, rejetée)

- **Source** : [fasttext.cc/docs/en/language-identification.html](https://fasttext.cc/docs/en/language-identification.html)
- **Couverture** : 176 langues (dont bambara `bm`)
- **Licence** : MIT
- **Avantages** : ultra-léger (~150 MB), latence très basse (~1 ms)
- **Limites** : qualité bambara documentée comme moyenne (le modèle est entraîné majoritairement sur Wikipedia), aucune optimisation pour code-switching, couverture africaine bien moindre qu'AfroLID
- **Verdict** : acceptable comme fallback ou pour environnements ultra-contraints, **mais n'aligne pas avec l'horizon 50 langues africaines** de [vision.md](../vision.md)

### Option C — cld3 (Google, rejetée)

- **Source** : [github.com/google/cld3](https://github.com/google/cld3)
- **Couverture** : ~107 langues
- **Bambara** : ❌ **NON couvert**
- **Verdict** : exclu d'office (manque la langue P1 de Wourri)

### Option D — langdetect (Python lib, rejetée)

- **Source** : [pypi.org/project/langdetect](https://pypi.org/project/langdetect/)
- **Couverture** : 55 langues
- **Bambara** : ❌ **NON couvert**
- **Verdict** : exclu d'office

### Option E — Status quo (heuristiques + déclaration user, rejetée)

- **Pour** : zéro effort, marche pour P1 dioula CI
- **Contre** : tous les problèmes identifiés en section "Limites" + dette qui s'accumule à chaque nouvelle langue ajoutée
- **Verdict** : tactique court-terme acceptable, **insoutenable au-delà de 5 langues**

### Comparatif synthétique

| Critère | AfroLID | FastText | cld3 | langdetect | Status quo |
|---|---|---|---|---|---|
| Couvre dioula/bambara | ✅ | ⚠️ | ❌ | ❌ | (heuristique) |
| Couvre 50+ langues afri. | ✅ | ⚠️ | ❌ | ❌ | ❌ |
| Code-switching | ✅ documenté | ❌ | ❌ | ❌ | partiel/audio uniquement |
| Licence commerciale | ✅ Apache 2.0 | ✅ MIT | ✅ Apache 2.0 | ✅ MIT | — |
| Production-ready | ✅ | ✅ | ✅ | ⚠️ | ⚠️ heuristique fragile |
| Aligné vision Wourri | ✅ | ⚠️ | ❌ | ❌ | ❌ |

---

## Décision

**Option A — AfroLID** comme détecteur principal de langue textuelle pour Wourri.

### Justification

1. **Seule option qui coche les 3 cases vitales** : bambara natif + 50+ langues africaines + licence commerciale permissive
2. **Aligné horizon long-terme** ([vision.md](../vision.md) : 50+ langues)
3. **Permet de supprimer l'anti-pattern hardcoding** `is_likely_dioula_input`
4. **Architecture moderne** (Transformer, pré-entraîné 2022, maintenance active UBC-NLP)
5. **Coût d'intégration acceptable** (modèle modéré, latence faible attendue, dépendance à valider en POC)

---

## Use cases d'intégration

### Use case 1 — Validation post-ASR (PRIORITAIRE)

Après transcription Whisper FR :

```
Audio reçu → Whisper transcrit → texte
  → AfroLID détecte langue du texte transcrit
  → Si AfroLID dit "bambara" et confiance >= 0.85
     → Retransciption via ASR Bambara (corrige Whisper qui s'est trompé)
  → Sinon
     → Pipeline français standard
```

**Bénéfice** : remplace l'heuristique fragile `is_likely_dioula_input` par un détecteur ML générique, pas spécifique à dioula → fonctionne aussi pour baoulé/bété/wolof quand on les ajoutera.

### Use case 2 — Routage NLU sur texte WhatsApp libre (SECONDAIRE)

User envoie un message texte (sans audio) :

```
Texte reçu
  → AfroLID détecte langue
  → Si différente de prefs.language déclaré + confiance >= 0.90
     → Logger l'écart (pour observabilité)
     → Router NLU vers la langue détectée (plus pertinent que la déclaration)
  → Sinon
     → Faire confiance à prefs.language
```

**Bénéfice** : gère les users qui changent de langue à la volée sans avoir à modifier leur profil.

### Use case 3 — Détection code-switching (NICE TO HAVE)

Un message peut contenir 2 langues mêlées (`i ni cɛ, je veux du riz`).

```
Texte reçu
  → AfroLID retourne distribution de probas par langue
  → Si top-2 langues ont chacune > 0.30
     → Activer pipeline NLU bilingue (à concevoir séparément)
```

**Bénéfice** : fonctionnalité avancée, à activer après validation des 2 premiers use cases.

---

## Critères de succès (à mesurer en POC d'implémentation future)

| Critère | Seuil cible | Méthode mesure |
|---|---|---|
| Précision dioula CI | ≥ 90 % | Test sur 100 phrases dioula curées (issue de `dictionnaires/corpus_ivr.json` v3) |
| Précision français | ≥ 95 % | Test sur 100 phrases françaises courantes Wourri |
| Latence détection | < 50 ms par requête (CPU) | Benchmark sur Colab T4 + machine VPS cible |
| RAM consommée | < 500 MB chargé en mémoire | Mesure via `psutil` |
| Détection code-switching | Top-2 langues identifiées correctement sur ≥ 70 % d'un set bilingue | Set de test à constituer (50 phrases) |
| Compatibilité licence | Apache 2.0 préservée pour tout dérivé | Vérification au moment de l'implémentation |

Si un critère n'est pas atteint → ré-ouvrir cet ADR pour ajustement (ex : passer en fallback FastText, ajouter un fine-tuning, etc.).

---

## Plan d'implémentation (différé, P2 ou Sprint 3)

### Phase A — POC isolé (1 jour)

- Tester AfroLID via Hugging Face transformers ou repo officiel UBC-NLP
- Mesurer les 5 critères de succès sur sets de test internes
- Document les résultats dans `docs/benchmarks/0002-afrolid-evaluation.md`

### Phase B — Intégration use case 1 (post-ASR validation, 1-2 jours)

- Créer `app/services/lang_detection/afrolid_detector.py` (singleton)
- Modifier la cascade `app/services/asr/__init__.py` : appel AfroLID après ASR pour corriger Whisper si besoin
- Tests unitaires + intégration

### Phase C — Intégration use case 2 (routage NLU texte, 1 jour)

- Modifier `app/services/chat_service.py` pour appeler AfroLID sur les messages texte avant NLU
- Logger les écarts vs `prefs.language` pour observabilité
- Tests unitaires + intégration

### Phase D — Suppression dette `is_likely_dioula_input` (0.5 jour)

- Une fois AfroLID stable : retirer la fonction et ses 50 patterns hardcodés de `stt_whisper.py`
- Tester non-régression

**Effort total estimé** : 4-5 jours dont 1 jour POC bloquant.

**Calendrier** : déclenché après Phase 4 d'[ADR-0003](0003-plan-ajout-omnilingual.md) (Omnilingual intégré + benchmarké). Pas avant.

---

## Conséquences

### Positives

- **Suppression durable de l'anti-pattern hardcoding** `is_likely_dioula_input`
- **Scalabilité aux 50+ langues** sans heuristique nouvelle à chaque ajout
- **Détection code-switching** (capacité non disponible aujourd'hui sur texte)
- **Observabilité** : on saura combien de fois la déclaration utilisateur est fausse
- **Aligné [ADR-0003](0003-plan-ajout-omnilingual.md)** : Omnilingual côté ASR + AfroLID côté texte = stack cohérente multi-langues africaines
- **Licence Apache 2.0** : compatible produit payant, aucun risque commercial

### Négatives assumées

- **Coût mémoire** : ~500 MB supplémentaires (le serveur a déjà NeMo + MMS + Whisper + NLLB + TTS chargés simultanément — le memory pressure connu sur Windows pourrait s'aggraver)
- **Latence ajoutée** : ~10-50 ms par requête (négligeable en absolu, mais cumulé avec ASR + NLU + LLM = à surveiller)
- **Précision dioula CI non garantie** : le paper AfroLID donne des chiffres macro, pas par langue → POC obligatoire avant intégration
- **Dépendance à fairseq ou transformers** (selon implémentation choisie) — autre dépendance ML à maintenir
- **Pas de gain immédiat pour P1** : le pipeline actuel marche pour dioula CI seul. Le gain devient évident en P2 (baoulé/bété/agni) et au-delà

### Verrous futurs levés

- Ajout baoulé/bété/agni (P2) : pas besoin d'écrire `is_likely_baoule_input`
- Ajout wolof/peul/hausa (P3) : idem
- IVR téléphonique multi-langues (P2-P3) : routage langue avant ASR plus simple

---

## Risques et mitigations

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| Précision dioula < 90 % en POC | Moyenne | Haut | POC bloquant Phase B. Si <90% → fallback FastText documenté ou fine-tuning AfroLID sur corpus dioula |
| Modèle trop lourd pour VPS | Faible | Moyen | Quantization int8 (réduit RAM ~4×) ; charger uniquement si nécessaire (lazy load) |
| Latence > 50 ms perceptible | Faible | Faible | Cache des détections récentes (clé = hash(texte)) |
| Maintenance UBC-NLP s'arrête | Faible | Moyen | Modèle pré-entraîné téléchargeable et auto-hostable indéfiniment |
| Conflit dépendances Python | Moyenne | Moyen | POC en environnement isolé d'abord |

---

## Références

- [github.com/UBC-NLP/afrolid](https://github.com/UBC-NLP/afrolid) — repo officiel + LICENSE Apache 2.0 vérifiée 2026-04-23
- [arXiv 2210.11744](https://arxiv.org/abs/2210.11744) — paper AfroLID
- [docs/vision.md](../vision.md) — horizon 50+ langues africaines justifie ce choix
- [docs/constraints.md](../constraints.md) — doctrine "pas de hardcoding"
- [ADR-0002](0002-ajout-provider-omnilingual.md) — stack ASR multi-langues qui sera complétée par AfroLID
- [ADR-0003](0003-plan-ajout-omnilingual.md) — calendrier d'implémentation aligné (post Phase 4)
- [app/services/stt_whisper.py:769-810](../../app/services/stt_whisper.py) — fonction `is_likely_dioula_input` à supprimer après intégration AfroLID
- Issue [#98](https://github.com/ouedraogoissouf2012/wourri/issues/98) — issue source de cet ADR

---

## Historique

- **2026-04-23 (rédaction)** — investigation pipeline actuel, comparaison 5 options, choix AfroLID. Statut : proposé, en attente validation Ruben.
