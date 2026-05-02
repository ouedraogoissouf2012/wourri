# Plan d'action consolidé — Wourri — Avril 2026

**Statut** : proposé, à valider action par action
**Date de rédaction** : 2026-04-22
**Source** : synthèse des 6 explorations approfondies (fonctionnalités, architecture, documentation, données, prompts LLM, recherche internet) du 2026-04-22
**Décision de stratégie gravée** : [ADR-0001](adr/0001-choix-stockage-donnees.md), [ADR-0002](adr/0002-ajout-provider-omnilingual.md), [ADR-0003](adr/0003-plan-ajout-omnilingual.md)

---

## Principes de ce plan

1. **Chaque action a une priorité** (P0 bloquant → P3 vision) et une justification sourcée
2. **Pas d'exécution silencieuse** : chaque action sera validée avant d'être lancée
3. **Décisions structurantes = ADR dédié** (voir section "ADRs à rédiger")
4. **Mises à jour documentaires** explicites pour éviter la perte de connaissance
5. **Effort et impact** mesurés, pas estimés au jugé

### Légende priorités

| Priorité | Critère | Horizon |
|---|---|---|
| **P0 BLOQUANT** | Risque sécurité / légal / production immédiat | Immédiat (heures-jours) |
| **P1 CRITIQUE** | Nécessaire pour livrer P1 dioula CI en qualité | 1-4 semaines |
| **P2 IMPORTANT** | Améliore maintenance, qualité, positionnement | 1-3 mois |
| **P3 VISION** | Prépare P2/P3/P4, aligne sur long-terme | 3-12 mois |

---

## P0 — Actions bloquantes (immédiat)

### [P0-01] Révoquer et tourner la clé API DeepSeek

**Description** : révoquer la clé API DeepSeek actuellement utilisée (potentiellement exposée dans l'historique git ou .env non nettoyé), générer une nouvelle clé, la stocker uniquement dans `.env` non committé.

**Raison** : l'audit du 2026-03-16 (item C1) a identifié la clé comme exposée. Une clé compromise = abus financier possible (crédits DeepSeek) + risque de fuite en cas de publication du repo.

**Effort** : 15 minutes
**Impact** : élimine le risque financier immédiat
**Dépendances** : aucune
**Exécution** : Ruben (console DeepSeek)
**Livrable** : nouvelle clé dans `.env`, ancienne clé révoquée côté dashboard
**Statut** : ✅ fait 2026-04-22 (ancienne clé révoquée, nouvelle générée et placée dans .env local)

---

### [P0-02] Ajouter authentification aux 5 routes API non protégées

**Description** : ajouter le middleware `require_api_key` aux routes qui n'en disposent pas actuellement :
- Toutes les routes de `app/routers/tts.py`
- `app/routers/stt.py`
- `app/routers/rag.py` (toutes)
- `app/routers/feedback.py` (toutes)
- `app/routers/weather.py` (toutes)

**Raison** : audit 2026-03-17 item SEC-02. Ces routes consomment potentiellement des crédits (TTS, STT, DeepSeek via RAG) et exposent des données utilisateurs (feedback). Sans auth, abus financier + fuite PII possibles.

**Effort** : 1-2 heures
**Impact** : ferme une vulnérabilité majeure avant toute mise en production
**Dépendances** : [P0-01]
**Exécution** : Claude (modifications code) + Ruben (review)
**Livrable** : PR modifiant les 5 routers avec `dependencies=[Depends(require_api_key)]`
**Statut** : ✅ fait 2026-04-22
- wouri-api commit `56f4cb9` : 15 routes protégées (stt, weather, rag, tts, feedback)
- whatsapp-server commit `bf40759` (P0-02a) : envoi header X-API-Key depuis app-baileys.js

---

### [P0-03] Compléter le rate limiting sur toutes les routes publiques

**Description** : appliquer `@limiter.limit("10/minute")` (ou adapté selon criticité) sur les 21 routes qui n'en ont pas actuellement. Actuellement seules 4/25 routes sont protégées.

**Raison** : audit 2026-03-17 item SEC-03. Sans rate limit, DoS possible → épuisement crédits DeepSeek + saturation serveur. Les ONGs bailleurs exigent cette protection en production.

**Effort** : 2-3 heures
**Impact** : protection standard niveau production
**Dépendances** : [P0-02]
**Exécution** : Claude + Ruben
**Livrable** : tous les endpoints `@router.post|get|put|delete` ont un `@limiter.limit()`
**Statut** : ✅ fait 2026-04-22
- wouri-api commit `e7ca6a1` : @limiter.limit("10/minute") sur les 15 mêmes routes que P0-02
- Routes statiques (languages, voices, status, cities/list) laissées sans limit

---

### [P0-04] Forcer `debug=False` par défaut

**Description** : changer dans `app/config.py` la valeur par défaut `debug: bool = True` vers `False`. Le mode debug ne doit être actif que par override explicite `.env` en développement.

**Raison** : audit 2026-03-16 item M9. Debug mode expose stack traces et informations sensibles dans les réponses d'erreur. Risque info-leak en production.

**Effort** : 5 minutes
**Impact** : sécurité par défaut
**Dépendances** : aucune
**Exécution** : Claude
**Livrable** : `app/config.py:19` modifié
**Statut** : ✅ fait 2026-04-22 (wouri-api commit `7beb63e`)

---

### [P0-05] Anonymiser les PII dans logs et persistance

**Description** : appliquer une fonction de hachage/masquage cohérente (ex: SHA-256 tronqué ou format `+XXX****1234`) sur tous les numéros WhatsApp avant écriture dans :
- `logs/feedback.jsonl`
- `data/feedback_negatif.jsonl`
- `data/user_preferences.json` (si existe)
- Tous les `logger.info("...")` qui manipulent des `user_id`

**Raison** : audit 2026-03-17 item SEC-C7. Numéros WhatsApp + villes + contenus = PII au sens GDPR-like. Actuellement en clair → violation de la posture GDPR-like P1 gravée dans [vision.md](vision.md).

**Effort** : 3-4 heures (grep des usages + fonction utilitaire + tests)
**Impact** : conformité GDPR-like effective
**Dépendances** : aucune
**Exécution** : Claude + Ruben (validation format anonymisation)
**Livrable** : `app/core/pii_utils.py` (nouvelle fonction) + modifications des call sites
**Statut** : ✅ fait 2026-04-22 (wouri-api commit `7fd1ba1`)
- SHA-256 tronqué 16 chars avec salt PII_SALT (déterministe + GDPR-compatible)
- Appliqué dans feedback.py (3 occurrences) + deepseek.py (1 occurrence)
- Tests unitaires 9/9 passent
- Correctif .gitignore pour ne plus bloquer les tests/**/test_*.py
- Hors scope reporté P2 : user_preferences.json (whatsapp-server) + conversation_history.py (RAM only)

---

## P1 — Actions critiques pour la livraison P1 dioula CI

### [P1-01] Rédiger ADR pour intégration African Next Voices + AfVoices

**Description** : rédiger `docs/adr/0004-corpus-bambara-afrivoices-nextvoices.md` documentant :
- Contexte : les corpus déjà utilisés (jeli-asr 67k, bayelemabaga 42k, Common Voice dyu 5k) sont massivement sous-dimensionnés face à AfVoices (423h+612h spontané) et African Next Voices (9000h dont secteur agriculture)
- Décision : intégrer ces deux sources dans le pipeline de fine-tuning (ADR-0003 Phase 3bis)
- Licences : vérifier par langue (CC-BY probable) et documenter
- Plan de téléchargement et validation

**Raison** : ces deux corpus, tous deux publiés fin 2025, représentent un saut quantitatif et qualitatif majeur pour le bambara/dioula. Les ignorer = livrer P1 en qualité dégradée. Sources : [arXiv 2511.18557 RobotsMali](https://arxiv.org/html/2511.18557), [huggingface.co/datasets/RobotsMali/afvoices](https://huggingface.co/datasets/RobotsMali/afvoices), [theconversation African Next Voices](https://theconversation.com/african-languages-for-ai-the-project-thats-gathering-a-huge-new-dataset-266371).

**Effort** : 2-3 heures (rédaction ADR) + temps de téléchargement séparé
**Impact** : démultiplie le volume de données pour fine-tune Omnilingual
**Dépendances** : ADR-0003 validé (ce qui est le cas)
**Exécution** : Claude (ADR) + Ruben (validation)
**Livrable** : `docs/adr/0004-corpus-bambara-afrivoices-nextvoices.md`
**Statut** : à faire

---

### [P1-02] Ajouter Bambara-ASR-v2 au benchmark ADR-0003 Phase 3

**Description** : mettre à jour [docs/benchmarks/0001-asr-dioula-evaluation.md](benchmarks/0001-asr-dioula-evaluation.md) pour inclure `sudoping01/bambara-asr-v2` (Whisper-large-v2 fine-tuné bambara, Apache 2.0) comme 5ème modèle testé en Phase 3 du plan d'ajout Omnilingual.

**Raison** : ce modèle gère nativement le **code-switching bambara-français**, critique pour les paysans ivoiriens qui mélangent les deux langues. Absent du benchmark actuel. Apache 2.0 = compatible usage commercial. Source : [huggingface.co/sudoping01/bambara-asr-v2](https://huggingface.co/sudoping01/bambara-asr-v2).

**Effort** : 30 minutes (mise à jour protocole)
**Impact** : garantit qu'on ne rate pas la meilleure option commerciale bambara disponible
**Dépendances** : [P1-01] idéalement avant (même corpus d'évaluation)
**Exécution** : Claude
**Livrable** : mise à jour `0001-asr-dioula-evaluation.md`
**Statut** : à faire

---

### [P1-03] Rédiger ADR pour ajout AfroLID comme language detector

**Description** : rédiger `docs/adr/0005-afrolid-language-detection.md` documentant l'ajout d'une brique de détection de langue (français pur vs dioula vs code-switch) avant la cascade ASR→NLU→IVR. Source : [AfroLID paper arXiv 2210.11744](https://arxiv.org/abs/2210.11744), 517 langues africaines supportées.

**Raison** : cascade actuelle suppose que l'entrée est bambara/dioula. En pratique, un utilisateur peut envoyer du français pur ou du code-switch. Sans détection amont, routage sous-optimal. Brique identifiée comme manquante par la recherche.

**Effort** : 2 heures (ADR) + temps d'implémentation séparé
**Impact** : améliore taux de bonne compréhension des entrées utilisateur
**Dépendances** : aucune
**Exécution** : Claude (ADR) + Ruben (validation)
**Livrable** : `docs/adr/0005-afrolid-language-detection.md`
**Statut** : ✅ fait 2026-04-23 (issue #98, PR à venir)

**Résolution** : ADR-0005 rédigé le 2026-04-23 avec investigation pipeline actuel + comparaison 5 options (AfroLID, FastText, cld3, langdetect, status quo).

**Décision tranchée** : **AfroLID** (UBC-NLP, Apache 2.0 vérifié, 517 langues africaines). Seule option qui coche les 3 cases vitales : bambara natif + 50+ langues afri. + licence commerciale permissive.

**Use cases documentés** :
1. Validation post-ASR (priorité) — corrige Whisper si l'audio était en bambara mal détecté → remplace l'heuristique hardcodée `is_likely_dioula_input`
2. Routage NLU sur texte WhatsApp libre (secondaire) — gère les users qui écrivent dans une langue ≠ leur déclaration
3. Détection code-switching (nice to have) — pour pipelines NLU bilingues futurs

**Critères de succès chiffrés** : précision ≥ 90 % dioula CI, latence < 50 ms, RAM < 500 MB. À valider en POC bloquant Phase B d'implémentation.

**Implémentation différée** : déclenchée après Phase 4 d'[ADR-0003](adr/0003-plan-ajout-omnilingual.md) (Omnilingual intégré + benchmarké). Effort estimé 4-5 jours dont 1 jour POC bloquant.

**Statut ADR-0005** : proposé, en attente validation Ruben pour bascule en `accepté`.

---

### [P1-04] Corriger le bug `_load_corpus()` dupliqué dans vdb_service.py

**Description** : dans `app/services/vdb_service.py`, la fonction `_load_corpus()` est définie **deux fois** (l'une avec cache, l'autre qui écrase). Supprimer la seconde définition.

**Raison** : audit 2026-03-17 item ARCHI-04. Bug silencieux : la seconde définition écrase la première, invalidant le cache. Impact performance mesurable à chaque requête chat.

**Effort** : 15 minutes (suppression + test)
**Impact** : correction d'un bug de performance direct
**Dépendances** : aucune
**Exécution** : Claude
**Livrable** : `vdb_service.py` nettoyé, test de non-régression
**Statut** : ✅ fait 2026-04-22 (wouri-api commit `aa8b7ce`)
**Note correction** : l'audit était partiellement incorrect. Il n'y avait PAS de doublon `_load_corpus()`, mais deux fonctions distinctes (`_load_corpus` avec cache + `_load_corpus_entries` sans cache qui relisait le JSON à chaque appel). Fix appliqué : `_load_corpus_entries()` utilise désormais le cache via `_load_corpus().get("entries", [])`.

---

### [P1-05] Débloquer asyncio : inférences ML en `to_thread`

**Description** : refactorer les appels d'inférence ML (TTS bambara/dioula, ASR providers, RAG embeddings) pour les exécuter via `asyncio.to_thread()` au lieu de bloquer le event loop FastAPI.

**Raison** : audit 2026-03-17 item PERF-01. Actuellement, un appel TTS bloque tous les autres requêtes pendant 2-3s. Pour une API multi-utilisateurs, c'est un goulot critique. En particulier `tts_bambara.py`, `tts_dioula.py`, `tts_ivoirian.py`.

**Effort** : 4-6 heures (refactor + tests)
**Impact** : throughput ×N avec N workers uvicorn
**Dépendances** : aucune
**Exécution** : Claude + Ruben
**Livrable** : les 3 fichiers TTS + providers ASR modifiés, tests d'intégration
**Statut** : à faire

---

### [P1-06] Clarifier le statut du mode agentic (contradiction MEMORY.md)

**Description** : MEMORY.md affirme *"Mode Agentic implémenté 2026-03-10 avec 5 outils"*. Vérification par l'agent prompts : dossier `app/services/agent/` existe mais **est vide** (rapport agent D). Trancher :
- Option A : le code a été supprimé → mettre à jour MEMORY.md
- Option B : le code existe ailleurs → localiser et documenter
- Option C : jamais implémenté → corriger MEMORY.md et retirer les références

**Raison** : incohérence interne dans la documentation. Toute prise de décision future s'appuyant sur "le mode agentic existe" serait fausse.

**Effort** : 30 minutes (investigation) + 15 minutes (correction doc)
**Impact** : cohérence documentaire, pas de dette d'info
**Dépendances** : aucune
**Exécution** : Claude (investigation) + Ruben (confirmation intention)
**Livrable** : état clarifié dans MEMORY.md + éventuellement tag de commit
**Statut** : ✅ fait 2026-04-23 (issue #100, PR à venir)

**Résolution** : investigation complète effectuée le 2026-04-23. Preuves accumulées :
- `app/services/agent/` contient uniquement un `__pycache__/` hérité (agent_service.cpython-312.pyc, tools.cpython-312.pyc). Les fichiers `.py` correspondants ont existé localement puis ont été supprimés.
- `git log --all -- app/services/agent/` retourne **vide** → les fichiers n'ont **jamais été committés** dans aucune branche.
- Aucun import `from app.services.agent` dans le code actuel.
- Aucune route `/api/chat/agent` dans `app/routers/chat.py`.
- Fichiers `app/routers/debug.py` et `templates/agent_debug.html` cités dans MEMORY.md : **n'existent pas**.

**Verdict** : le mode agentic était un **prototype local** du 2026-03-10, testé localement puis abandonné, **jamais versionné en production**. MEMORY.md reflétait un état qui n'a jamais existé en dehors du poste de développement.

**Actions prises** :
- Suppression locale de `app/services/agent/` (dossier non-tracké, juste nettoyage disque).
- Correction `MEMORY.md` : retrait des 5 lignes listant des fichiers inexistants (119-123), remplacement de la section "Mode Agentic (implémenté 2026-03-10)" par une section honnête "Mode Agentic — prototype local NON implémenté (clarifié 2026-04-23)".
- Les 3 fichiers `finetune/*.py` cités dans MEMORY.md existent réellement (vérifié), ils sont conservés.

**Décision future** : si un mode agentic devient utile, ADR dédié + redémarrage depuis zéro avec scope validé et tests.

---

### [P1-07] Trancher la version de référence du corpus IVR

**Description** : trois versions cohabitent dans `dictionnaires/` :
- `corpus_ivr.json` (v2.3, 162 entrées, utilisé par vdb_service.py)
- `corpus_ivr_v3_draft.json` (v3, 38 entrées partielles)
- `corpus_ivr_v3_full_draft.json` (v3, 162 entrées réécrites complet)
- `corpus_ivr_v2.1_backup.json` (backup obsolète)

Trancher : quelle version est la source de vérité ? Renommer ou supprimer les autres.

**Raison** : ambiguïté dans la documentation et risque d'utilisation involontaire d'une version ancienne. Clarté nécessaire pour toute itération corpus future.

**Effort** : 1 heure (review diffs + décision + nettoyage fichiers)
**Impact** : clarté pour future itération corpus
**Dépendances** : aucune
**Exécution** : Ruben (décision) + Claude (exécution nettoyage)
**Livrable** : un seul `corpus_ivr.json` à jour, autres archivés ou supprimés
**Statut** : ✅ fait 2026-04-23 (issue #101, PR à venir)

**Résolution** : investigation complète des 4 fichiers le 2026-04-23.

État réel découvert :
- `corpus_ivr.json` (v2.3, 162 entrées) — **source de vérité actuelle**, référencée par `vdb_service.py`, `config.py`, et 5+ outils
- `corpus_ivr_v2.1_backup.json` (v2.1, 162 entrées) — backup figé, **redondant avec git history**
- `corpus_ivr_v3_draft.json` (v3, 38 entrées partielles) — draft incomplet abandonné (issue #49)
- `corpus_ivr_v3_full_draft.json` (v3, 162 entrées réécrites SOV naturel, validation 84,9 %) — candidat sérieux pour devenir prod

**Décision tranchée** : `corpus_ivr.json` (v2.3) reste la source de vérité. Les 3 autres fichiers sont **archivés** dans `dictionnaires/archive/` avec un `README.md` explicatif. Aucun supprimé (préservation des heures de travail dioula CI dans v3_full).

**Question hors scope ouverte** : la promotion de `v3_full_draft` → `corpus_ivr.json` (v2.4 ou v3.0) mérite **un ADR dédié futur** car nécessite tests de régression complets sur le pipeline ASR→NLU→IVR→TTS. Critères pressentis : validation ≥ 95 % (aujourd'hui 84,9 %), évaluation humaine native, tag de release dédié.

**Actions prises** :
- `git mv` des 3 fichiers vers `dictionnaires/archive/` (préserve l'historique git via renommage)
- Création de `dictionnaires/archive/README.md` (statut détaillé de chaque fichier + procédure de promotion future)
- MEMORY.md mis à jour (ligne corpus_ivr_v2.1_backup → mention de l'archive complète)

---

## P2 — Actions importantes (moyen terme)

### [P2-01] Nettoyage du code mort whatsapp-server

**Description** : supprimer les 3 fichiers morts identifiés dans `whatsapp-server/` :
- `app.js` (462L, non utilisé)
- `whatsapp-server.js` (266L, non utilisé)
- `whatsapp-server-simple.js` (124L, non utilisé)

Seul `app-baileys.js` est actif. Corriger aussi le champ `"main"` de `package.json` qui pointe erronément.

**Raison** : audit 2026-03-17 item CLEAN. Code mort = confusion pour collaborateurs futurs + risque d'utiliser un fichier obsolète. MEMORY.md mentionnera `app-baileys.js` comme unique entrée après nettoyage.

**Effort** : 30 minutes
**Impact** : clarté codebase
**Dépendances** : aucune
**Exécution** : Claude + Ruben
**Livrable** : fichiers supprimés, `package.json` corrigé, commit descriptif
**Statut** : à faire

---

### [P2-02] Nettoyage scripts soloni_* legacy à la racine wouri-api

**Description** : supprimer ou archiver les 8+ scripts `soloni_*.py` à la racine `wouri-api/` (export, merge, patch_meta, reexport, sherpa_test, etc.) qui sont des scripts d'expérimentation ONNX non utilisés en production.

**Raison** : le pipeline ASR utilise désormais `app/services/asr/nemo_provider.py` (basé NeMo natif, pas ONNX). Les scripts soloni_* correspondent à une phase d'expérimentation antérieure (février 2026, tentative ONNX + sherpa-onnx) abandonnée. Ils encombrent le projet.

**Effort** : 30 minutes (review + archivage `tools/legacy/` ou suppression)
**Impact** : clarté codebase
**Dépendances** : confirmation qu'aucun script actif ne les importe (grep `import soloni`)
**Exécution** : Claude + Ruben
**Livrable** : scripts déplacés ou supprimés
**Statut** : à faire

---

### [P2-03] Archiver ou supprimer BACKUP_2026-01-26/

**Description** : le dossier `wourri/BACKUP_2026-01-26/` contient un snapshot complet du projet de janvier 2026 (~2 GB incluant modèles). Soit :
- Le déplacer hors du projet actif (autre disque, archive zip externe)
- Le supprimer si git couvre l'historique nécessaire

**Raison** : 2 GB inutiles dans le workspace. Ralentit les outils de recherche (grep, ls, etc.). Git fournit déjà la persistance historique.

**Effort** : 15 minutes (décision) + temps de copie si archivage
**Impact** : légereté du workspace
**Dépendances** : vérifier que git couvre bien les changements depuis janvier 2026
**Exécution** : Ruben (décision)
**Livrable** : dossier déplacé ou supprimé
**Statut** : à faire

---

### [P2-04] Nettoyage dossier whatsapp-server imbriqué

**Description** : le chemin `wourri/whatsapp-server/whatsapp-server/` existe (dossier imbriqué avec son propre `.git`). Vérifier s'il s'agit d'un artefact de clone imbriqué ou d'une structure voulue. Si artefact : supprimer.

**Raison** : structure étrange, ambiguïté. Peut troubler les outils de build/déploiement.

**Effort** : 15 minutes
**Impact** : clarté structurelle
**Dépendances** : aucune
**Exécution** : Claude (investigation) + Ruben (décision)
**Livrable** : structure clarifiée
**Statut** : à faire

---

### [P2-05] Compléter la documentation projet

**Description** : créer les documents manquants identifiés par l'agent de documentation :
- `wourri/README.md` : vue d'ensemble produit + architecture + quickstart (remplace les DOCUMENTATION_*.md redondants)
- `wourri/LICENSE` : clarifier la licence (propriétaire → licence commerciale, Apache 2.0, MIT, etc.)
- `wourri/SECURITY.md` : processus de divulgation vulnérabilités + contact sécurité
- `wourri/PRIVACY.md` : politique vie privée utilisateurs (GDPR-like, obligatoire modèle B2C)
- `docs/adr/README.md` : index des ADRs (voir [P2-06])

**Raison** : projet commercial payant sans LICENSE/PRIVACY = blocage légal. Sans README = onboarding impossible. Ces documents sont le minimum pour une équipe future.

**Effort** : 4-6 heures (rédaction complète)
**Impact** : conformité légale + onboarding équipe
**Dépendances** : [P0-05] (posture PII définie)
**Exécution** : Claude (drafts) + Ruben (validation + choix licence)
**Livrable** : 4 nouveaux fichiers markdown + suppression des doublons DOCUMENTATION_*
**Statut** : à faire

---

### [P2-06] Créer un index ADR

**Description** : créer `docs/adr/README.md` qui liste tous les ADRs avec leur titre, statut, date, résumé 1 ligne. Format standard "ADR index" utilisable comme table des matières.

**Raison** : actuellement 4 ADRs dans `docs/adr/`, future croissance attendue. Sans index, difficile de naviguer.

**Effort** : 30 minutes
**Impact** : navigation documentaire
**Dépendances** : aucune
**Exécution** : Claude
**Livrable** : `docs/adr/README.md`
**Statut** : à faire

---

### [P2-07] Rédiger ADR pour migration Baileys → WhatsApp Business Cloud API

**Description** : rédiger `docs/adr/0006-migration-whatsapp-cloud-api.md` documentant la migration de Baileys (non-officiel, risque ban) vers l'API officielle Meta (WhatsApp Business Cloud API). Tarification Afrique revue à la baisse en février 2025 selon [Meta pricing docs](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing).

**Raison** : pour un produit **commercial payant** B2C/B2B/B2G, utiliser Baileys en production = risque ban du compte WhatsApp personnel, rupture de service pour les utilisateurs, réputation commerciale compromise. Meta officiel = conformité + stabilité.

**Effort** : 3-4 heures (ADR incluant étude pricing + plan de migration)
**Impact** : stabilité production + conformité commerciale
**Dépendances** : aucune (peut être planifié indépendamment)
**Exécution** : Claude (ADR) + Ruben (validation + ouverture compte Meta Business)
**Livrable** : `docs/adr/0006-migration-whatsapp-cloud-api.md`
**Statut** : à faire

---

### [P2-08] Suppression `asr_quality/` + blocklist (après validation Omnilingual)

**Description** : supprimer les fichiers identifiés comme code mort dans [ADR-0002](adr/0002-ajout-provider-omnilingual.md) :
- `app/services/asr_quality/` (lexicon.py, models.py, __init__.py)
- `data/asr_hallucinations_dyu.json`
- `tests/unit/test_asr_quality_*.py`

**Raison** : ces fichiers dupliquent les étapes 1-4 du normalizer ASR existant (`asr_normalizer.py`). Leur seul intérêt était le filtrage post-hoc de NeMo — rendu obsolète par la migration Omnilingual (ADR-0002, ADR-0003).

**Effort** : 30 minutes
**Impact** : réduction de code mort
**Dépendances** : Phase 4 de [ADR-0003](adr/0003-plan-ajout-omnilingual.md) terminée (Omnilingual en prod stable)
**Exécution** : Claude
**Livrable** : fichiers supprimés + tests complets verts
**Statut** : à faire (prévu après Omnilingual validé)

---

### [P2-09] Refactoriser ChatService (extraire orchestration)

**Description** : `app/services/chat_service.py` fait 595 lignes et gère : détection ville + NLU preprocessing + IVR + DeepSeek + météo + traduction. Extraire en composants SRP :
- `ChatOrchestrator` (orchestration)
- `CityDetector` (détection ville)
- `IVRResolver` (recherche IVR exact/concept)
- `MeteoEnricher` (injection météo contextuelle)

**Raison** : audit 2026-03-17 item ARCHI-01 (God Controller). Maintenance difficile, tests unitaires quasi impossibles. Violation SRP documentée.

**Effort** : 2-3 jours (refactor + tests)
**Impact** : maintenabilité + testabilité
**Dépendances** : aucune
**Exécution** : Claude (refactor) + Ruben (validation architecture)
**Livrable** : ChatService découpé en 4-5 classes avec tests unitaires
**Statut** : à faire

---

### [P2-10] Remplacer `print()` par `logger` systématiquement

**Description** : 100+ occurrences de `print()` identifiées dans le code (audit 2026-03-17 item CLEAN-05). Les remplacer par `logger.info/debug/warning/error` selon pertinence.

**Raison** : `print()` ne passe pas par la configuration logging centralisée (`app/core/logging_config.py`). Logs inconsistants, pas de niveau, pas formatés.

**Effort** : 2-3 heures
**Impact** : logs cohérents et filtrables
**Dépendances** : aucune
**Exécution** : Claude
**Livrable** : grep `print(` dans app/ retourne zéro résultat
**Statut** : à faire

---

## P3 — Actions vision (long terme)

### [P3-01] Évaluer Pipecat + Twilio Media Streams pour IVR P2

**Description** : étude comparative et POC light de Pipecat (BSD-2) avec Twilio Media Streams pour préparer P2 (IVR téléphonique). Alternative : LiveKit Agents (Apache 2.0), Agent Voice Response (sur Asterisk).

**Raison** : P2 (IVR téléphonique) est dans la roadmap vision.md. Stacks matures 2025-2026 existent, évite de réinventer la roue. Audio 8 kHz téléphonique imposé, dégradation WER à quantifier. Sources : [Pipecat](https://github.com/pipecat-ai/pipecat), [LiveKit Agents](https://github.com/livekit/agents).

**Effort** : 1 semaine (POC)
**Impact** : prépare P2 sans ADR bloquant
**Dépendances** : P1 dioula CI stabilisé (Omnilingual en prod)
**Exécution** : Ruben (POC) + Claude (assistance technique)
**Livrable** : rapport de POC + décision d'orientation P2
**Statut** : vision, non priorisé

---

### [P3-02] Analyse concurrentielle Farmerline Darli AI + Farmer.CHAT

**Description** : étude documentée des concurrents directs identifiés par la recherche :
- **Farmerline Darli AI** (1M utilisateurs, francophone, déployé en Côte d'Ivoire 2025)
- **Farmer.CHAT / Digital Green** (830k actifs, open-source via Gooey.AI)
- **UlangiziAI** (Malawi, Opportunity International)

Documenter : feature gap, pricing, positionnement, potentiel de différenciation Wourri.

**Raison** : Farmerline est **déjà sur notre marché home (CI francophone)**. Sans analyse de positionnement, stratégie commerciale Wourri flotte. Gooey.AI est open-source, à évaluer comme brique ou concurrent.

**Effort** : 1 semaine (analyse) + ADR de positionnement
**Impact** : clarté stratégique commerciale
**Dépendances** : aucune
**Exécution** : Ruben (analyse marché) + Claude (synthèse)
**Livrable** : `docs/competitive_analysis_2026-04.md` + éventuel ADR de positionnement
**Statut** : vision

---

### [P3-03] Évaluer Gooey.AI comme benchmark ou brique

**Description** : Gooey.AI est le backend de Farmer.CHAT, Apache 2.0, supporte WhatsApp + IVR + langues locales + évaluation. Benchmarker contre Wourri : features, coût, quality.

**Raison** : possibilité de raccourcir le chemin en intégrant des briques Gooey.AI plutôt que tout construire. Ou alternativement, valider que notre stack custom vaut mieux. Sans évaluation, décision à l'aveugle.

**Effort** : 3-5 jours (évaluation technique)
**Impact** : validation du choix "build vs buy" sur certains modules
**Dépendances** : [P3-02]
**Exécution** : Ruben + Claude
**Livrable** : rapport d'évaluation
**Statut** : vision

---

### [P3-04] Pivot business : subventions/B2G vs VC equity

**Description** : le marché AgTech Afrique a chuté de -20% YoY en 2025, equity < 50% pour la 1ère fois. Privilégier : subventions CGIAR, AIM for Scale (Gates), tenders Banque Mondiale, AFD, GIZ, Orange Digital Center (déjà dans le programme DigiGreen). Documenter la stratégie de funding.

**Raison** : source [techpoint.africa/insight/african-agtech-funding-landscape-2025](https://techpoint.africa/insight/african-agtech-funding-landscape-2025/). Wourri est déjà dans le programme DigiGreen & Agri Cohorte 2 — levier à activer prioritairement.

**Effort** : à discuter avec Ruben et conseillers Athari
**Impact** : stratégique, change les priorités produit (B2G ≠ B2C UX)
**Dépendances** : aucune
**Exécution** : Ruben (décision business)
**Livrable** : stratégie de funding documentée
**Statut** : vision

---

### [P3-05] Clarifier souveraineté DeepSeek

**Description** : DeepSeek = API LLM hébergée en Chine. Pour clients B2G (ONGs, gouvernements africains) avec exigences de souveraineté, cela peut être un bloqueur. Options à étudier : Mistral (EU), Claude (US mais multi-région), Llama self-hosted (dépendant compute).

**Raison** : non-négociable gravé dans vision.md : "hébergement EU ou Afrique (pas US)". DeepSeek Chine = ni EU, ni Afrique, ni US. Tension à résoudre avec un ADR dédié.

**Effort** : 3-5 jours (étude comparative + ADR)
**Impact** : conformité B2G
**Dépendances** : [P3-02] (clients B2G identifiés)
**Exécution** : Ruben + Claude
**Livrable** : `docs/adr/0007-choix-llm-conversationnel.md`
**Statut** : vision

---

### [P3-06] Correction préventive APDP → ARTCI dans futures docs

**Description** : le régulateur data en Côte d'Ivoire s'appelle **ARTCI** (Autorité de Régulation des Télécommunications / ICT), pas APDP (APDP = Bénin et Mali). Lors de toute future rédaction concernant la conformité data en CI, utiliser ARTCI.

**Raison** : source vérifiée [dataprotection.africa/cote-divoire](https://dataprotection.africa/cote-divoire/). Erreur factuelle fréquente confondant les régulateurs d'Afrique de l'Ouest. Aucun fichier actuel du projet ne mentionne APDP (vérifié par grep le 2026-04-22), donc action préventive.

**Effort** : 0h (règle à appliquer dans futures rédactions)
**Impact** : éviter erreur factuelle future
**Dépendances** : aucune
**Exécution** : Claude (vigilance) + Ruben (remarque)
**Livrable** : mise à jour [CLAUDE.md](../CLAUDE.md) avec rappel
**Statut** : à faire (mise à jour CLAUDE.md)

---

## ADRs à rédiger (chaînage des décisions)

Les actions ci-dessus en génèrent plusieurs. Ordre de priorité recommandé :

| ADR | Titre | Priorité | Dépendance |
|---|---|---|---|
| ADR-0004 | Intégration corpus African Next Voices + AfVoices | P1 | [P1-01] |
| ADR-0005 | Ajout AfroLID pour language detection | P1 | [P1-03] |
| ADR-0006 | Migration Baileys → WhatsApp Cloud API | P2 | [P2-07] |
| ADR-0007 | Choix LLM conversationnel (souveraineté) | P3 | [P3-05] |
| ADR-0008 | Plan migration ChromaDB → pgvector | P2-P3 | après ADR-0001 accepté |
| ADR-0009 | Stratégie IVR téléphonique P2 | P3 | [P3-01] |

---

## Mises à jour documentaires

**Déjà fait dans cette passe** :
- [MEMORY.md](../../../.claude/projects/c--Users-USER-PC-Documents-propre---moi-wourri/memory/MEMORY.md) — ajout sections datasets manquants + concurrents + erreur APDP→ARTCI préventive

**À faire avant la clôture de cette passe** :
- [ ] Créer `docs/adr/README.md` (index ADRs) — [P2-06]
- [ ] Mettre à jour [CLAUDE.md](../CLAUDE.md) avec rappel ARTCI (partie "Règles bambara/dioula" ou nouvelle section)
- [ ] Éventuellement ajuster [vision.md](vision.md) si tu veux formaliser certaines décisions P3 (ex: ne pas aller US)

---

## Ordre d'exécution recommandé

### Sprint 1 (2026-04-22) — P0 sécurité ✅ TERMINÉ + VALIDÉ EN INTÉGRATION
1. ✅ [P0-01] Révoquer clé DeepSeek (Ruben, 2026-04-22)
2. ✅ [P0-04] Debug=False par défaut — commit `7beb63e`
3. ✅ [P0-02] Auth 15 routes — commit `56f4cb9` + whatsapp-server `bf40759`
4. ✅ [P0-03] Rate limit 15 routes — commit `e7ca6a1`
5. ✅ [P0-05] Anonymisation PII SHA-256 salted — commit `7fd1ba1` (9/9 tests)
6. ✅ [P1-04] Fix cache `_load_corpus_entries` — commit `aa8b7ce`

**Fix bonus découverts en phase de test (2026-04-23)** :
- `f961f3f` — P0-02b + P0-05b : `security.py` et `pii_utils.py` utilisaient `os.getenv()` qui ne lit pas `.env`. Correctif : lecture via Pydantic Settings (`get_settings().api_secret_key`, `get_settings().pii_salt`).
- `62659ee` (whatsapp-server) — P0-02a bis : `app-baileys.js` n'appelait pas `require('dotenv').config()`, donc `WOURI_API_KEY` restait `undefined`. Ligne ajoutée en tête de fichier.

**Tests d'intégration 5/5 passés (2026-04-23)** :
1. ✅ Démarrage backend — tous modèles chargés, zéro warning sécurité
2. ✅ Auth route protégée — `POST /api/tts/french` : 403 sans clé, 200 avec clé valide
3. ✅ Rate limit — 10× 200 OK puis 429 Too Many Requests (seuil 10/min actif)
4. ✅ Anonymisation PII — log feedback contient `"user":"usr_71f5e1969a92b26d"` (format SHA-256 correct, pas de numéro en clair)
5. ✅ Pipeline WhatsApp end-to-end — vocal dioula reçu → ASR Bambara 200 → NLU + chat → réponse audio dioula renvoyée

**Livraison sprint 1** : production-safe basique. ✅ Délivrée + validée 2026-04-23.
**Variables .env requises côté déploiement** : `DEEPSEEK_API_KEY`, `API_SECRET_KEY`, `PII_SALT`, + `WOURI_API_KEY` côté whatsapp-server (égal à `API_SECRET_KEY`).
**Branches prêtes à merger** : `fix/security-p0-sprint1` dans wouri-api (7 commits) ET whatsapp-server (2 commits).

### Sprint 2 (semaine suivante) — P1 corpus et ASR
7. [P1-01] ADR corpus African Next Voices + AfVoices
8. [P1-02] Mise à jour benchmark avec Bambara-ASR-v2
9. [P1-06] Clarification mode agentic
10. [P1-07] Trancher version corpus IVR
11. [P1-05] Asynchronisation inférence ML (en parallèle)

**Livraison sprint 2** : ADRs en place, décisions gravées, dette réduite.

### Sprint 3 — Exécution ADR-0003 + nettoyage
12. Phases 1-5 de [ADR-0003](adr/0003-plan-ajout-omnilingual.md) (Omnilingual provider)
13. [P2-01] à [P2-04] : nettoyage code mort
14. [P2-05] Documentation manquante
15. [P2-06] Index ADRs

### Au fil de l'eau — P2/P3
- [P1-03] ADR AfroLID
- [P2-07] ADR WhatsApp Cloud API
- [P2-08] Suppression asr_quality/ (après Omnilingual prod)
- [P2-09] Refactor ChatService
- [P2-10] print() → logger
- P3 selon priorités business

---

## Comment utiliser ce plan

1. **Référencer par ID** : quand on discute d'une action, utiliser son ID (ex: "on traite [P0-02]")
2. **Mettre à jour le statut** de chaque action au fur et à mesure : à faire / en cours / fait / annulé
3. **Ajouter un bloc "Historique"** en fin de fichier pour logger les décisions de révision
4. **Ne rien commiter ni exécuter** sans validation préalable — le plan propose, tu disposes

---

## Historique

- **2026-04-22 (rédaction)** — Rédaction initiale sur la base des 6 explorations approfondies. 22 actions identifiées, 6 ADRs à rédiger, mises à jour documentaires listées.
- **2026-04-22 (Sprint 1 livré)** — 6 actions P0+P1-04 fermées en 1 session :
  - P0-01 révoquée (clé DeepSeek exposée puis re-générée correctement)
  - P0-02 + P0-02a : auth 15 routes backend + envoi X-API-Key côté WhatsApp
  - P0-03 rate limit 10/min sur 15 routes
  - P0-04 debug=False par défaut
  - P0-05 anonymisation PII SHA-256 salted avec `PII_SALT` (GDPR Art. 4(5))
  - P1-04 optimisation cache corpus VDB (audit partiellement incorrect — fix réel appliqué)
  - Correctif .gitignore : `!tests/**/test_*.py` pour ne plus ignorer les tests organisés
  - 3 nouvelles env vars requises : `API_SECRET_KEY`, `PII_SALT` (wouri-api), `WOURI_API_KEY` (whatsapp-server)
  - Prochaine étape : test d'intégration terrain avant merge des branches `fix/security-p0-sprint1`.
- **2026-04-23 (Sprint 1 validé)** — 2 bugs résiduels découverts et corrigés pendant les tests d'intégration :
  - `f961f3f` (P0-02b+P0-05b) : `security.py` et `pii_utils.py` utilisaient `os.getenv()` qui ne lit pas `.env`. Correctif via Pydantic Settings.
  - `62659ee` whatsapp-server (P0-02a bis) : `app-baileys.js` ne chargeait pas `dotenv`. Ligne `require('dotenv').config()` ajoutée en tête.
  - 5/5 tests d'intégration passés. Pipeline WhatsApp→ASR→NLU→chat→TTS validé bout en bout avec les nouveaux secrets en place.
  - Les 2 branches `fix/security-p0-sprint1` sont prêtes pour merge (9 commits cumulés).
