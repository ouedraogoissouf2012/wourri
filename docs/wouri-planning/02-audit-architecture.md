# 02 — Audit d'architecture

**Date** : 2026-10-11 · Périmètre : `wouri-api`, `whatsapp-server`, déploiement, CI/CD.

## 1. Cartographie applicative

```
Agriculteur (WhatsApp)
        |
        v
whatsapp-server (Node.js / Baileys)        <- dépôt séparé, branche whatsappServeur
  lib/ : message_handler, message_queue, circuit_breaker, city_resolver,
         user_prefs, onboarding, i18n, audio_cache, alerts_dispatcher
        |
        | HTTP
        v
wouri-api (FastAPI)                        <- dépôt wouri-api, branche APIPy
  routers/   : chat, asr, tts, stt, weather, rag, admin, lqe, speaker,
               admin_baoule, provider_baoule, feedback, demo, health_memory
  services/  : chat_service (cascade) + chat/handlers (FR / DIOULA / BOTH)
               nlu/ (concepts + intents) · corpus/ (pgvector) · asr/ · tts_*
               translation/ (NLLB, DeepSeek, dictionnaire, scoring)
               improvement_queue (atelier) · weather · model_registry
        |
        +--> PostgreSQL + pgvector     (corpus IVR, unique backend — ADR-0008/#203)
        +--> Open-Meteo                (météo — ADR-0038)
        +--> DeepSeek                  (LLM, sous garde ADR-0039)
        +--> Volume /app/data          (file d'amélioration LQE)
```

✅ **CONFIRMÉ** — 16 routeurs, 11 sous-paquets de services, 122 modules Python.

## 2. Points forts architecturaux

### 2.1 Cascade en Strategy Pattern — ✅ CONFIRMÉ
`app/services/chat_service.py::ChatService.process` est un **dispatcher pur** sur un registre
`HANDLERS[language]`. Ajouter une langue = 1 handler + 1 entrée, sans toucher la méthode
(OCP). C'est une bonne décision, tenue dans le temps ([ADR-0015](../adr/0015-strategy-pattern-cascade-chat-et-anglais.md)).

### 2.2 Séparation des responsabilités linguistiques — ✅ CONFIRMÉ
`app/services/asr/base.py` définit l'interface des fournisseurs ASR ; trois implémentations
interchangeables (`mms_dyu_provider`, `mms_generic_provider`, `omnilingual_provider`) sont
composées par `asr/chain.py`. L'inversion de dépendance est réelle, pas décorative.

### 2.3 Verrou de confidentialité — ✅ CONFIRMÉ
L'anonymisation est **irréversible par conception** et la file d'amélioration **refuse**
l'écriture d'une tâche contenant une PII. C'est un choix rare et solide, aligné ARTCI.

### 2.4 Discipline de décision — ✅ CONFIRMÉ
40 ADR, chacun avec contexte, options chiffrées, décision et conséquences. Peu de projets de
cette taille tiennent ce niveau de traçabilité.

## 3. Faiblesses d'architecture

### 3.1 🔴 Le mode français ne consulte pas le corpus — CONFIRMÉ
`app/services/chat/handlers/french_handler.py` n'implémente **aucune cascade IVR** : le LLM est
son chemin par défaut. Conséquences mesurées :
- une connaissance validée par un locuteur natif **n'est jamais servie** aux utilisateurs en
  mode français ;
- la boucle de retour (ADR-0040) **ne peut pas se refermer** pour eux ;
- la surface d'invention du LLM reste maximale sur ce mode.

**C'est la faiblesse structurelle la plus coûteuse du produit.**

### 3.2 🟡 Paquet `asr_quality/` vide — CONFIRMÉ
`app/services/asr_quality/` ne contient **aucun fichier source** (seulement `__pycache__/`).
Soit du code a été supprimé sans retirer le paquet, soit il n'a jamais été versionné. Dans les
deux cas, **aucune mesure de qualité ASR n'est exécutable depuis l'application**.

### 3.3 🟡 Documentation d'amorçage désynchronisée — CONFIRMÉ
`CLAUDE.md` donne des chiffres faux (163 entrées / 54 concepts contre 197 / 60 réels) et décrit
la cascade comme « IVR exact > IVR concept > DeepSeek+NLLB > fallback », sans les répondeurs
déterministes ni le garde LLM ajoutés depuis. Un contributeur qui s'y fie part avec une carte
périmée.

### 3.4 🟡 Trous dans la numérotation ADR — CONFIRMÉ
Les numéros **0006, 0007, 0009** n'existent pas. Sans note explicative, un lecteur ne peut pas
distinguer « jamais écrit » de « supprimé ».

## 4. Déploiement et CI/CD

✅ **CONFIRMÉ** — `.github/workflows/ci-api.yml` (sur `APIPy`) exécute :
`docker build --check` · validation `docker compose config` (prod + staging) ·
`scripts/check_env_consistency.py` · `alembic upgrade head` · la suite de tests.

✅ **CONFIRMÉ** — `.github/workflows/deploy-api.yml` : **tout push sur `APIPy` déclenche le
déploiement**. Il n'y a pas d'étape d'approbation manuelle entre le merge et la production.

### Faiblesses de la chaîne

| Constat | Statut | Effet |
|---|---|---|
| Aucune mesure de couverture de tests | ❌ **ABSENT** | On ignore quelles parties des 16 821 lignes sont réellement exercées |
| Aucune porte qualité bloquante hors tests | 🟡 **PARTIEL** | Pas de lint/typage imposé en CI |
| Déploiement automatique sans approbation | ✅ **CONFIRMÉ** | Rapide, mais une régression part en production sans palier |
| Build d'image long (>10 min observé) | 🟡 **PARTIEL** | Un test post-merge trop rapide teste l'ancienne version |

## 5. Observabilité et exploitation

✅ **CONFIRMÉ** — Journalisation structurée et rétention PII pensées
([ADR-0025](../adr/0025-retention-logs-pii-artci.md), `app/core/log_retention.py`) ;
bascule Promtail → Grafana Alloy décidée ([ADR-0016](../adr/0016-migration-promtail-grafana-alloy.md)) ;
tableau de bord sans PII ([ADR-0017](../adr/0017-dashboard-observabilite-sans-pii.md)).

🔍 **À VÉRIFIER** — Le fait que la chaîne Alloy/Loki **reçoive effectivement** des données en
production n'a pas été contrôlé dans cette mission (nécessite un accès au tableau de bord).

🔴 **ABSENT** — **Aucune sauvegarde automatisée versionnée.** `pg_dump` n'apparaît que dans des
**procédures écrites** (`docs/RUNBOOK_REDEPLOIEMENT_2026-08.md`, `docs/deployment.md`) ; aucun
script planifié n'est présent dans `scripts/`. `docs/guide-projet-wourri.md:354` reconnaît
lui-même l'absence d'un équivalent backup/restore.

## 6. Sécurité — état mesuré

| Contrôle | Statut | Preuve |
|---|---|---|
| Limitation de débit | ✅ **CONFIRMÉ** | `app/middleware/rate_limit.py` ([ADR-0018](../adr/0018-strategie-rate-limiting-api.md)) |
| Protection par clé d'API | ✅ **CONFIRMÉ** | `require_api_key` / `X-API-Key` dans **13** modules |
| Secrets en dur | ✅ **AUCUN DÉTECTÉ** | Recherche de motifs `sk-…` / mot de passe littéral : 0 occurrence |
| Exposition réduite sur Internet | ✅ **CONFIRMÉ** | [ADR-0032](../adr/0032-exposition-etroite-moteur-demo.md) |
| Durcissement du déploiement SSH | ✅ **CONFIRMÉ** | [ADR-0013](../adr/0013-ssh-deploy-hardening-options.md) |
| Rotation des secrets | 🔍 **À VÉRIFIER** | Aucune procédure planifiée trouvée ; une rotation reste en dette connue |

> Conformément à la consigne, **aucun secret n'est reproduit** dans ce rapport.
