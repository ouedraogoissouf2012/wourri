# ADR-0043 — Accueil du baoulé : déclaration de langue et repli honnête (« langue annoncée »)

**Statut** : proposé
**Date** : 2026-10-17
**Auteur(s)** : Claude (assistant) sous direction de Ouedraogo Issouf
**Valideur** : Ouedraogo Issouf — en attente (option W choisie en discussion le 2026-10-17, ADR à valider avant fusion)
**ADRs liés** : [ADR-0015](0015-strategy-pattern-cascade-chat-et-anglais.md) (handlers par langue, ajout de l'anglais), [ADR-0031](0031-moteur-amelioration-linguistique.md) (pas d'invention linguistique), [ADR-0034](0034-atelier-parite-linguistique.md) (réponses natives produites par l'atelier), [ADR-0036](0036-choix-modele-asr-baoule.md) (ASR baoulé), [ADR-0037](0037-conserver-multibranches-orphelines.md) (branche `whatsappServeur`)
**Issue** : #477 (epic #472) — chantier BAO-1 de la feuille de route (`docs/wouri-planning/05-roadmap-12-semaines.md`)

---

## Contexte

### Le verrou

Aucun agriculteur ne peut se déclarer baoulophone. La feuille de route (BAO-1, P0) en fait le préalable de tout le chantier baoulé : sans cette porte d'entrée, aucun travail ASR, NLU ou TTS n'atteint un utilisateur. Critères d'acceptation de BAO-1 : (1) l'utilisateur choisit le baoulé et la préférence survit au redémarrage ; (2) **un repli explicite est servi tant que le contenu baoulé est absent — jamais une réponse inventée**.

### Ce que fait le code aujourd'hui (vérifié le 2026-10-17)

**Serveur WhatsApp** (`origin/whatsappServeur`, déployé par `deploy-wa.yml`) :

- `lib/onboarding.js` (`_handleWaitingLanguage`) ne reconnaît que 1 français, 2 dioula, 3 les deux, 4 anglais. « 5 » ou « baoulé » fait reposer la question.
- `lib/user_prefs.js` persiste n'importe quelle valeur de `language`, sans validation.
- `lib/message_handler.js` envoie la préférence **brute** à `/api/chat/` (`language: prefs.language`).
- `lib/response_sender.js` :
  - `sendResponse` n'a pas de branche `else` : une langue inconnue ne reçoit **aucune réponse** ;
  - `sendExcuse` envoie l'**audio dioula** à toute langue autre que `french` et `both`, y compris `english` (bug existant).

**API** (`APIPy`) :

- `Language` (`app/models/schemas.py`) n'accepte que `french`, `dioula`, `both`, `english`.
  - Une autre valeur est rejetée en **422** sur `/api/chat/`.
  - Une valeur ajoutée à l'enum sans handler lève `KeyError` dans `HANDLERS[language]`. L'exception est rattrapée en un faux « problème de connexion » (HTTP 200).
- Aucun ASR baoulé n'est en production. Le fournisseur Omnilingual existe (`services/asr/omnilingual_provider.py`) mais n'est pas branché (`omnilingual_enabled=False`). Le fine-tune est en cours (#474, fiche `docs/benchmarks/0005`).

**Conséquence si l'on ajoutait seulement l'option au menu WhatsApp :**

- chaque message d'un utilisateur baoulé reçoit un 422 ;
- le circuit breaker du serveur WhatsApp compte ces 422 comme des pannes et peut **s'ouvrir pour tous les utilisateurs** ;
- le message échoué reste en file et est rejoué en échec à chaque reconnexion ;
- l'utilisateur reçoit une excuse en audio dioula, fausse.

### Contraintes applicables (`docs/constraints.md`)

- §3.3 / §5 : **aucune invention linguistique**. Aucun texte en baoulé ne peut être écrit sans validation d'un locuteur natif.
- §2.3 : un changement du protocole de langue entre le serveur WhatsApp et l'API est une décision structurante, d'où cet ADR.
- §3.1 : pas de sur-ingénierie. Rien de l'ASR, du NLU ni du TTS baoulé n'est construit ici.

## Questions posées avant la décision

1. Où vit la langue « baoulé » tant qu'elle n'est pas servie : dans l'API, ou seulement dans le serveur WhatsApp ?
2. Que reçoit un utilisateur baoulé pour un message écrit ? Et pour un message vocal ?
3. Faut-il un texte en baoulé ?

Réponses (discussion du 2026-10-17) :

- Q1 → serveur WhatsApp seulement (option W ci-dessous). L'API ne change pas.
- Q2 → écrit : réponse en français, annoncée comme telle dès la confirmation du choix. Vocal : message honnête, sans transcription (aucun ASR ne comprend le baoulé ; Whisper FR produirait une transcription fausse).
- Q3 → non. Tous les messages sont en français ; une phrase baoulé validée par un locuteur natif pourra être ajoutée plus tard.

## Options étudiées

### Option W — « langue annoncée » côté serveur WhatsApp (retenue)

- **Description** : le serveur WhatsApp connaît une notion de langue **annoncée**, choisissable mais servie dans une langue de repli (`PENDING_LANGUAGES = { baoule: "french" }`, `lib/i18n.js`). Concrètement :
  - la préférence `baoule` est enregistrée telle quelle ;
  - les messages, l'appel `/api/chat/` et le format de réponse utilisent la langue de repli ;
  - un vocal reçoit un message honnête ;
  - les statistiques comptent la langue sous `bci`.
- **Avantages** :
  - aucun changement de contrat d'API, donc aucun risque de 422 ni de pollution du circuit breaker ;
  - la demande baoulé devient **mesurable** (`/ingest/event`, `language = bci`) ;
  - la préférence est déjà en place le jour où le service baoulé existera : personne ne sera réonboardé ;
  - le mécanisme sert à toute future langue annoncée (une entrée dans `PENDING_LANGUAGES`).
- **Inconvénients** : la notion de langue annoncée vit dans le serveur WhatsApp. Un autre canal (IVR, démo) devra la reprendre s'il propose le baoulé.
- **Coût** : environ 9 fichiers du serveur WhatsApp, et 20 tests ajoutés. Aucun fichier de l'API.

### Option A — l'API déclare la langue

- **Description** : `Language.BAOULE` dans l'API, avec un `BaouleHandler` (sur le modèle de l'`EnglishHandler`) qui sert un repli français, plus des entrées dans `SYSTEM_PROMPTS`.
- **Avantages** : contrat explicite ; prêt à recevoir l'ASR et le NLU baoulé.
- **Inconvénients** :
  - change le contrat public de `/api/chat/` pour un handler qui ne ferait que du français ;
  - les répondeurs déterministes (`meteo_responder.py`, `culture_zone_responder.py`) renvoient de l'**audio dioula** pour toute langue différente de `french` : il faudrait les adapter ;
  - deux dépôts à déployer de façon coordonnée.
- **Quand** : quand l'ASR (#474) et le NLU (#475) baoulé existeront. Le passage de W à A se fera alors par un nouvel ADR.

### Option 0 — ne rien proposer tant que le baoulé n'est pas servi

- **Rejetée** : elle contredit BAO-1 (P0) et prive le projet de la mesure de la demande.

### Comparatif

| Critère | W (retenue) | A | 0 |
|---|---|---|---|
| Débloque BAO-1 | ✅ | ✅ | ❌ |
| Contrat d'API | inchangé | modifié | inchangé |
| Risque sur les autres utilisateurs | aucun (l'API reçoit une langue connue) | faible, si les deux déploiements sont coordonnés | aucun |
| Mesure de la demande baoulé | ✅ (`bci`) | ✅ | ❌ |
| Invention linguistique | aucune | aucune | — |
| Prêt pour l'ASR/NLU baoulé | préférence en place, routage à faire (ADR futur) | ✅ | ❌ |

## Décision

**Option retenue** : **W**, langue annoncée côté serveur WhatsApp.

**Justification** : elle remplit les deux critères de BAO-1 (choix persisté, repli honnête) sans toucher au contrat de l'API ni exposer les autres utilisateurs. Elle n'invente aucun texte et rend la demande mesurable. L'option A est la suite naturelle, mais elle n'a de valeur qu'une fois l'ASR et le NLU baoulé disponibles.

## Conséquences

- **Positives** :
  - un agriculteur peut choisir le baoulé : « 5 », « baoulé », « baoule » ou « bci » ;
  - il est prévenu tout de suite que Wourri lui répond en français ;
  - ses vocaux ne partent plus vers un ASR qui les déformerait ;
  - le nombre de baoulophones devient visible dans les statistiques (`bci`).
- **Correction incluse** : `sendExcuse` n'envoie plus d'audio dioula par défaut. L'anglais reçoit désormais un texte anglais (`EXCUSE_MSG.UNAVAILABLE_EN` / `BACK_EN`), et une langue inconnue un texte bilingue.
- **Négatives assumées** :
  - le baoulé est proposé au menu sans être compris : l'honnêteté repose sur le message de confirmation et sur le message des vocaux ;
  - la réponse est en texte français, alors qu'une partie du public baoulé lit peu le français. Une voix baoulé (#476) ou des réponses natives (atelier, ADR-0034) restent à venir.
- **Travail induit** (branche `feat/477-accueil-baoule` sur `whatsappServeur`) :
  - `lib/i18n.js` : `PENDING_LANGUAGES`, `LANGUAGE_LABELS`, `contentLanguage()`, `isPendingLanguage()`, option 5 dans les trois menus, `PREFS_SAVED` honnête, `VOICE_UNAVAILABLE` ;
  - `lib/onboarding.js` : choix 5 et libellés ;
  - `lib/message_handler.js` : vocal intercepté, `/api/chat/` appelé dans la langue de repli ;
  - `lib/pending_replay.js` : idem au rejeu ;
  - `lib/response_sender.js` : réponses et excuses dans la langue de repli, excuses anglaise et par défaut corrigées ;
  - `lib/excuse_audio.js` : textes d'excuse anglais ;
  - `lib/ingest_event.js` : `baoule` → `bci` ;
  - `lib/user_prefs.js` : commentaire du format ;
  - tests : `tests/baoule_langue_annoncee.test.js` (20 tests) et `tests/i18n.test.js`. Suite complète : 534 tests.
  - **Retour arrière** : retirer `baoule` de `SUPPORTED_LANGUAGES` et de `PENDING_LANGUAGES`. Les utilisateurs déjà en `baoule` seraient alors traités comme une langue inconnue (excuse bilingue) : il faudrait les rebasculer en `french`.
- **Déploiement** : une fusion sur `whatsappServeur` déclenche `deploy-wa.yml` (si `DEPLOY_WA_ENABLED`). L'API n'est pas redéployée.
- **Verrous futurs** : la valeur persistée `baoule` devient un contrat entre le serveur WhatsApp et ses fichiers de préférences. L'option A devra la reprendre telle quelle, ou prévoir une migration.

## Références

- Issue #477, epic #472 ; feuille de route `docs/wouri-planning/05-roadmap-12-semaines.md` (BAO-1) et `10-feuille-de-route-baoule.md`.
- `docs/constraints.md` §2.3, §3.1, §3.3.
- Analyse du code du 2026-10-17 (serveur WhatsApp `84a6904`, API `d561c53`).

## Historique

- 2026-10-17 — proposé (option W, choisie en discussion avec le valideur ; code et tests prêts sur `feat/477-accueil-baoule`).
