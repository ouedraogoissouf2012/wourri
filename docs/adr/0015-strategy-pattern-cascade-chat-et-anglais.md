# ADR-0015 — Strategy Pattern pour la cascade chat + ajout de l'anglais

**Statut** : accepté
**Date** : 2026-06-01
**Auteur** : Claude (assistant)
**Valideur** : Ruben (validé le 2026-06-02)
**Lié à** : [ADR-0008](0008-plan-migration-chromadb-pgvector.md) (architecture corpus stable, condition préalable)

---

## Contexte

### Origine du besoin

Lors de la présentation du **2026-05-31**, un investisseur a soulevé la question :

> *« Pourquoi l'application ne supporte-t-elle pas l'anglais ? Cela vous aiderait
> à vous exporter et démontrerait que c'est une plateforme multi-langue. »*

Cette demande révèle deux usages :

1. **Court terme** : démontrer un bot multi-langue lors des pitches investisseurs
   (un investisseur anglophone peut tester le bot, voir qu'il comprend, mesurer la qualité)
2. **Moyen terme** : préparer l'expansion vers des marchés anglophones d'Afrique
   (Kenya, Tanzanie, Nigeria, Ghana) si la traction se confirme

### État actuel de la cascade chat

[`app/services/chat_service.py:67-114`](../../wouri-api/app/services/chat_service.py#L67) implémente
le pipeline message → réponse en **3 chemins distincts via if/elif** :

```python
if language in (DIOULA, BOTH) and nlu.intent:
    result = await self._try_ivr_exact(...)          # cascade dioula niveau 1
    if result: return result

if language in (DIOULA, BOTH):
    result = await self._try_ivr_concept(...)        # cascade dioula niveau 2
    if result: return result
    return await self._try_deepseek_dioula(...)      # cascade dioula niveau 3

return await self._try_deepseek_french(...)          # chemin français direct
```

**Anti-pattern OCP** : ajouter une nouvelle langue (anglais maintenant, espagnol/swahili
demain) impose **modifier** ce bloc à chaque fois. Le code n'est pas ouvert à l'extension,
il est ouvert au patching, ce qui s'aggrave avec le temps.

**Autre problème** : [`app/services/deepseek.py:41-80`](../../wouri-api/app/services/deepseek.py#L41)
contient un `if language in (DIOULA, BOTH): ... else: ...` qui hardcode les system prompts
par langue. Même anti-pattern OCP.

### Pourquoi maintenant

1. **Demande investisseurs** : besoin clarifié et urgent (prochain pitch dans semaines)
2. **Architecture stable** : ADR-0008 vient d'être livré (pgvector pur actif), le corpus
   ne bougera plus pendant ce refactor — fenêtre saine
3. **Précédent éprouvé** : on a déjà appliqué Strategy Pattern dans le projet
   ([PR #256 refactor `bambara_validator` Source ABC](https://github.com/ouedraogoissouf2012/wourri/pull/256))
   et le refactor P2-09 chat_service (PRs #262–#268, 5 PRs incrémentales). On connaît
   la méthode et son risque maîtrisé.
4. **Coût marginal faible** : extraire les 3 chemins dans des handlers nommés est ~6-8h
   de code soigné, et chaque ajout de langue futur sera **pure extension**.

### Ce que ce plan PRODUIT

Une cascade chat **ouverte à l'extension** (OCP-compliant) où chaque langue est isolée
dans son propre handler, et l'ajout de l'anglais comme **première extension validant
le pattern**. Pas de surcharge d'abstraction : un Protocol simple + un registre dict.

---

## Questions tranchées avant la décision

### 1. Vrai support EN agricole ou passthrough ?

**Passthrough.** Le corpus IVR (162 entrées) est uniquement BAM/FR. Traduire chaque
entrée en EN avec relecture native = 1-2 mois de travail + recrutement traducteur agricole
anglophone. Hors scope du besoin investisseur (qui veut voir une démo, pas tester les
subtilités du dioula ivoirien). Un vrai support EN agricole fera l'objet d'un **ADR
séparé** si export commercial confirmé.

### 2. NLLB FR↔EN passthrough ou DeepSeek direct EN ?

**DeepSeek direct.** DeepSeek est un LLM multilingue qui produit du EN natif de qualité
supérieure à une traduction NLLB de réponse FR. Bénéfices : latence ÷ 3 (1 appel vs
3 calls), qualité supérieure, code plus simple. Le corpus IVR étant inutilisable pour
EN, la cascade IVR est bypassée — DeepSeek est la seule source légitime.

### 3. TTS anglais : Edge TTS, Piper EN, ou autre ?

**Piper EN.** Cohérent avec l'existant ([`tts_french.py`](../../wouri-api/app/services/tts_french.py)
utilise Piper FR), 100 % offline, modèle ONNX local (~60 MB pour
`en_US-amy-medium.onnx`), aucune dépendance réseau. Conservation du pattern de code
identique à `tts_french.py`.

### 4. Détection langue : auto ou explicite ?

**Choix explicite** via le système `user_preferences.json` côté `whatsapp-server`
(déjà géré dans l'onboarding). L'investisseur choisit `English` dans la sélection
de langue → toutes ses requêtes API portent `language=ENGLISH`. Pas de détection regex
auto (faux positifs sur prénoms, anglicismes en français, etc.).

### 5. Refactor incrémental ou Big Bang ?

**Incrémental en 4 PRs**, suivant la méthode éprouvée par le refactor P2-09 (5 PRs).
Chaque PR est mergeable indépendamment, garde la rétrocompatibilité via wrappers, et
peut être rollback isolément. Pas de big bang, pas de risque catastrophique.

### 6. Que reste-t-il pour un vrai support EN agricole (hors scope) ?

Réservé à un futur ADR-0016 si export confirmé :
- Traduction des 162 entrées corpus FR→EN avec relecture native anglophone
- Adaptation des 54 concepts NLU (keywords agricoles EN : "rice paddy",
  "groundnut", "cassava", "millet")
- Tests E2E EN sur la cascade IVR complète
- ~1-2 mois de travail + budget traducteur

---

## Décision

### Refactor cascade chat → Strategy Pattern

Créer un **Protocol** [`LanguageHandler`](../../wouri-api/app/services/chat/handlers/_protocol.py)
et un **registre dict** [`HANDLERS: dict[Language, LanguageHandler]`](../../wouri-api/app/services/chat/handlers/__init__.py)
dans le sous-package [`app.services.chat.handlers/`](../../wouri-api/app/services/chat/handlers/).

Chaque langue a son propre fichier handler :

```
app/services/chat/handlers/
├── __init__.py            # HANDLERS registry + dispatcher
├── _protocol.py           # Protocol LanguageHandler (interface)
├── french_handler.py      # FrenchHandler (extraction de try_deepseek_french)
├── dioula_handler.py      # DioulaHandler (cascade IVR exact → concept → DeepSeek)
├── both_handler.py        # BothHandler (idem dioula, mode bilingue)
└── english_handler.py     # EnglishHandler (NOUVEAU : DeepSeek direct EN)
```

[`chat_service.process()`](../../wouri-api/app/services/chat_service.py#L67) devient un
**thin dispatcher** :

```python
async def process(self, message, city, language, ...) -> ChatResult:
    detected_city = detect_city(message)
    city = detected_city or city
    nlu = preprocess_nlu(message, bambara_text, language)
    weather_data = await get_weather(city)

    handler = HANDLERS[language]
    return await handler.process(
        message=message, nlu=nlu, city=city,
        weather_data=weather_data,
        include_audio=include_audio,
        language=language,
        user_id=user_id,
    )
```

**Bénéfice** : ajouter une 5e langue (espagnol) = 1 entrée dans `HANDLERS` + 1 nouveau
fichier `spanish_handler.py` + 1 nouveau `tts_spanish.py`. **Zéro modification** de
`chat_service.process()` ni du code existant. Vrai OCP.

### Externalisation des system prompts DeepSeek

Créer [`app/services/deepseek_prompts.py`](../../wouri-api/app/services/deepseek_prompts.py) :

```python
SYSTEM_PROMPTS: dict[Language, str] = {
    Language.FRENCH: FRENCH_PROMPT,
    Language.DIOULA: DIOULA_PROMPT,
    Language.BOTH:   DIOULA_PROMPT,  # même prompt en mode bilingue
    Language.ENGLISH: ENGLISH_PROMPT,
}
```

[`chat_with_deepseek()`](../../wouri-api/app/services/deepseek.py#L16) lit
`SYSTEM_PROMPTS[language]`. Toute nouvelle langue = 1 entrée dans le dict, jamais de
modification du `if/else` (qui disparaît).

### Ajout de l'anglais comme première extension

- Enum `Language.ENGLISH = "english"` dans [`app/models/schemas.py`](../../wouri-api/app/models/schemas.py#L9)
- Entrée dans `HANDLERS[Language.ENGLISH] = EnglishHandler()`
- Entrée dans `SYSTEM_PROMPTS[Language.ENGLISH] = ENGLISH_PROMPT` (prompt agricole adapté EN)
- Nouveau module [`tts_english.py`](../../wouri-api/app/services/tts_english.py) (Piper EN)
- Tests E2E EN : 5 questions agricoles génériques (rice, maize, weather, cassava, greeting)

---

## Conséquences

### Positives

- **OCP respecté** : chaque langue future = pure extension, jamais de modification
- **Tests isolés** : un handler par fichier = tests unitaires par langue, pas de mélange
- **Lecture du code** : `chat_service.process()` passe de 47 lignes à ~15 lignes
- **Symétrie** : pattern identique au refactor `bambara_validator` Source ABC (PR #256),
  déjà éprouvé en production
- **Démonstration multi-langue** : argument marketing solide pour pitches investisseurs
- **Coût TTS = 0** : Piper EN est offline gratuit, aucune charge récurrente
- **Préparation expansion** : ajouter espagnol/swahili devient trivial

### Négatives / risques

- **Risque régression cascade dioula** : c'est notre code prod actuel, extraction
  délicate. **Mitigation** : tests existants (15 tests `test_ivr_searcher.py` + 7 tests
  `test_deepseek_router.py` + tests `test_chat_service.py`) doivent rester verts à chaque
  PR. Bot live en local pour validation finale (envoi message WhatsApp avant push).
- **Effort augmenté** : ~6-8h code + ~3-4h tests vs ~3-5h en patch direct. Accepté pour
  la qualité long terme.
- **Réponses EN moins précises culturellement** : DeepSeek est généraliste, pas adapté
  CI/Mali. Acceptable pour démo investisseur, **PAS** pour agriculteurs anglophones réels.
  Un futur ADR-0016 traitera le vrai support EN agricole si export confirmé.
- **Coût API DeepSeek par message EN** : ~$0.0001 par requête, négligeable pour volume
  pitch investisseur.

### Dette technique introduite

Aucune. Le refactor **supprime** une dette existante (anti-OCP cascade if/elif) au lieu
d'en créer.

### Critères de rollback

- Toute PR rollbackable indépendamment via revert git
- Tests existants restent verts à chaque PR
- Bot live en local doit répondre correctement à 5 messages dioula avant push de chaque PR
- Si échec : `git revert <sha>` + analyse + nouvelle PR corrigée

---

## Plan d'exécution

Méthode incrémentale **4 PRs**, suivant le pattern P2-09 (5 PRs livrées avec succès) et
le refactor #233 (4 PRs Source ABC livrées avec succès).

### PR 1/4 — Protocol + FrenchHandler (validation pattern)

**Objectif** : poser l'infrastructure Strategy Pattern et extraire le chemin le plus
simple (français direct) pour valider le pattern sur un cas trivial.

**Scope** :
- Créer [`app/services/chat/handlers/_protocol.py`](../../wouri-api/app/services/chat/handlers/_protocol.py)
  avec `LanguageHandler` Protocol
- Créer [`app/services/chat/handlers/french_handler.py`](../../wouri-api/app/services/chat/handlers/french_handler.py)
  (`FrenchHandler.process()` = extraction de `try_deepseek_french`)
- Créer [`app/services/chat/handlers/__init__.py`](../../wouri-api/app/services/chat/handlers/__init__.py)
  avec `HANDLERS = {Language.FRENCH: FrenchHandler()}` (entrée unique)
- Wrappers de rétrocompatibilité dans `chat_service.ChatService._try_deepseek_french`
  qui délègue à `HANDLERS[Language.FRENCH].process(...)`
- Tests : 5+ tests unit `test_french_handler.py` (audio on/off, DeepSeek erreur, etc.)

**Critère de sortie** : test existants verts + 5+ nouveaux tests + 1 message FR au bot
local répond correctement.

### PR 2/4 — DioulaHandler + BothHandler (extraction cascade)

**Objectif** : extraire la cascade dioula (3 niveaux : IVR exact → IVR concept →
DeepSeek dioula) dans un handler propre.

**Scope** :
- Créer [`app/services/chat/handlers/dioula_handler.py`](../../wouri-api/app/services/chat/handlers/dioula_handler.py)
  qui contient la cascade IVR exact → concept → DeepSeek dioula
- Créer [`app/services/chat/handlers/both_handler.py`](../../wouri-api/app/services/chat/handlers/both_handler.py)
  (identique à dioula, factorise via héritage ou composition)
- Ajout des 2 entrées dans `HANDLERS`
- Wrappers de rétrocompatibilité sur `_try_ivr_exact`, `_try_ivr_concept`,
  `_try_deepseek_dioula`
- Tests : `test_dioula_handler.py` + `test_both_handler.py` (couvrent les 3 niveaux
  cascade)

**Critère de sortie** : tests existants verts (15 tests `test_ivr_searcher.py` + 7 tests
`test_deepseek_router.py` ne doivent pas bouger) + nouveaux tests + 1 message dioula et
1 message both au bot local répondent correctement.

### PR 3/4 — chat_service.process() en dispatcher pur + externalisation prompts

**Objectif** : convertir `chat_service.process()` en thin dispatcher et externaliser
les system prompts DeepSeek.

**Scope** :
- `chat_service.process()` réduite à ~15 lignes : dispatcher pur sur `HANDLERS[language]`
- Suppression du `if/elif` dans `chat_service.process()`
- Création [`app/services/deepseek_prompts.py`](../../wouri-api/app/services/deepseek_prompts.py)
  avec `SYSTEM_PROMPTS: dict[Language, str]`
- `chat_with_deepseek()` lit `SYSTEM_PROMPTS[language]` au lieu du `if/else`
- Tests : adapter `test_chat_service.py` pour vérifier dispatcher

**Critère de sortie** : tous les tests verts + bot live répond correctement aux 3 modes
existants (français, dioula, both) sans changement perceptible.

### PR 4/4 — EnglishHandler + tts_english + tests E2E EN

**Objectif** : valider le pattern en ajoutant l'anglais comme **pure extension**.

**Scope** :
- Ajout `Language.ENGLISH = "english"` dans enum
- Ajout `SYSTEM_PROMPTS[Language.ENGLISH] = ENGLISH_PROMPT` (prompt agricole EN adapté)
- Création [`app/services/chat/handlers/english_handler.py`](../../wouri-api/app/services/chat/handlers/english_handler.py)
  (`EnglishHandler.process()` : DeepSeek direct EN + TTS EN, ~50 lignes)
- Ajout `HANDLERS[Language.ENGLISH] = EnglishHandler()`
- Création [`app/services/tts_english.py`](../../wouri-api/app/services/tts_english.py)
  (Piper EN, ~80 lignes, copie adaptée de `tts_french.py`)
- Mise à jour onboarding WhatsApp ([`whatsapp-server/lib/onboarding.js`](../../whatsapp-server/lib/onboarding.js))
  pour ajouter le choix `🇬🇧 English`
- Tests E2E EN : 5 questions agricoles (rice planting, maize harvest, weather forecast,
  cassava care, greeting) qui retournent une réponse EN cohérente
- Documentation : section README "Multi-language support"

**Critère de sortie** : 5 tests E2E EN verts + démo manuelle : bot répond correctement
à 3 questions EN d'un investisseur fictif + tous les tests existants verts + tous les
modes existants (FR/DIOULA/BOTH) fonctionnent toujours.

### Critères de sortie globaux ADR-0015

- [ ] 4 PRs mergées (#TBD-1, #TBD-2, #TBD-3, #TBD-4) sur branche `APIPy`
- [ ] CI verte sur les 4 PRs (357+ tests, 0 régression)
- [ ] Tests E2E manuels : 1 message FR, 1 dioula, 1 both, 1 EN répondent correctement
- [ ] Documentation README mise à jour avec section EN
- [ ] Bot live local démarre sans erreur dans tous les modes (FR / DIOULA / BOTH / EN)
- [ ] Mémoire MEMORY.md mise à jour avec backlog produit EN livré

---

## Risques résiduels et plan de mitigation

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| Régression cascade dioula | Moyen | Critique (prod) | Tests existants + bot live + PR incrémentales rollbackables |
| Coût téléchargement modèle Piper EN | Faible | Faible | Modèle 60 MB, téléchargement 1× depuis github release officielle |
| Réponse DeepSeek EN générique (pas agricole CI) | Élevé | Faible (démo OK) | Acceptation explicite dans cet ADR, futur ADR-0016 si export |
| Voix Piper EN ne plaît pas aux investisseurs | Faible | Moyen | Choix de modèle adaptable (amy/lessac/joe/kathleen) sans toucher code |
| Tests E2E EN flaky (DeepSeek API timeout) | Moyen | Faible | Retry × 2 dans le test E2E + skipif si pas de clé DeepSeek |

---

## Décisions explicitement non prises (réservées à ADR séparés)

- Vrai support agricole EN (traduction corpus + concepts NLU EN) → **ADR-0016** si export
  commercial confirmé
- Détection langue automatique (regex / classifier) → pas nécessaire, choix explicite
  user_preferences suffit
- Internationalisation des messages d'erreur (les 5 messages d'erreur côté chat_service
  restent en français pour cette ADR — futures langues l10n via gettext si besoin)
- Support d'autres langues européennes (espagnol, portugais) → pure extension, pas
  d'ADR nécessaire grâce au pattern installé
