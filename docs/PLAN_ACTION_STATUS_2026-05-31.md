# État du Plan d'Action 2026-04 — Snapshot 2026-05-31

> **Pour** : Ruben (à relire à tête reposée)
> **Source de vérité du plan original** : [`docs/PLAN_ACTION_2026-04.md`](PLAN_ACTION_2026-04.md)
> **Ce document** = snapshot de l'avancement à date, avec recommandations pour la suite.
> **Snapshot après** : session marathon 29-30-31 mai 2026 (25 PRs mergées).

---

## Sommaire

1. [Vue d'ensemble](#1-vue-densemble)
2. [P0 BLOQUANT — sécurité (5/5 fait)](#2-p0-bloquant)
3. [P1 CRITIQUE — qualité dioula (4/7 fait)](#3-p1-critique)
4. [P2 IMPORTANT — maintenance + qualité (4/10 fait)](#4-p2-important)
5. [P3 VISION — long terme (1/6 fait)](#5-p3-vision)
6. [Sprints I→O + Phase 5 (#209)](#6-sprints-roadmap)
7. [Bugs/issues nouveaux session](#7-bugs-issues-nouveaux)
8. [Ce qui RESTE faisable à 2 (sans tiers)](#8-faisable-a-2)
9. [Ce qui NÉCESSITE un tiers](#9-necessite-tiers)
10. [Recommandation pour la suite](#10-recommandation)

---

## 1. Vue d'ensemble

| Catégorie | Avancement | Détail |
|---|---|---|
| **P0 BLOQUANT** | **5/5 = 100%** ✅ | Sécurité production OK |
| **P1 CRITIQUE** | **4/7 = 57%** | Reste 3 ADRs structurants (Sprint N) |
| **P2 IMPORTANT** | **4/10 = 40%** | +1 cette session (P2-09 ChatService refactor) |
| **P3 VISION** | **1/6 = 17%** | Normal, c'est de la vision long terme |
| **Sprints I→Phase 5** | **2/8 = 25%** | I fait, J préparé, reste 6 |

**Bilan honnête** : le projet est solidement avancé sur la sécurité (P0 complet) et la qualité interne (P2-09 refactor god file livré). Reste surtout des décisions/blocages externes (locuteur natif dioula CI, provisionnement VM staging par toi, décisions ADRs SSH + ARTCI).

---

## 2. P0 BLOQUANT

**Status : ✅ 5/5 complet (avant cette session, en avril 2026)**

| Action | Description | Statut |
|---|---|---|
| [P0-01] | Révoquer clé DeepSeek exposée | ✅ 2026-04-22 |
| [P0-02] | Auth `require_api_key` sur 5 routes non protégées | ✅ 2026-04-22 (commit `56f4cb9` + `bf40759`) |
| [P0-03] | Rate limiting `@limiter.limit("10/minute")` 21 routes | ✅ 2026-04-22 (commit `e7ca6a1`) |
| [P0-04] | `debug=False` par défaut | ✅ 2026-04-22 (commit `7beb63e`) |
| [P0-05] | Anonymiser PII dans logs + persistance | ✅ 2026-04-22 (commit `7fd1ba1`) |

**Conséquence** : tu peux mettre en production sans risque sécurité immédiat.

---

## 3. P1 CRITIQUE

**Status : 4/7 fait — reste 3 ADRs structurants (regroupés Sprint N #206)**

| Action | Description | Statut | Issue/PR |
|---|---|---|---|
| [P1-01] | ADR African Next Voices + AfVoices | ❌ à faire | Sprint N [#206](https://github.com/ouedraogoissouf2012/wourri/issues/206) |
| [P1-02] | Bambara-ASR-v2 benchmark | ❌ à faire | Sprint N [#206](https://github.com/ouedraogoissouf2012/wourri/issues/206) |
| [P1-03] | ADR AfroLID language detection | ❌ à faire | Sprint N [#206](https://github.com/ouedraogoissouf2012/wourri/issues/206) |
| [P1-04] | Fix `_load_corpus` dupliqué vdb_service | ✅ commit `aa8b7ce` | — |
| [P1-05] | `asyncio.to_thread` inférences ML | ✅ Sprint G.2 [PR #194](https://github.com/ouedraogoissouf2012/wourri/pull/194) | — |
| [P1-06] | Clarifier statut mode agentic (contradiction MEMORY) | ✅ [issue #100 fermée](https://github.com/ouedraogoissouf2012/wourri/issues/100) | — |
| [P1-07] | Trancher version référence corpus IVR | ✅ [issue #101 fermée](https://github.com/ouedraogoissouf2012/wourri/issues/101) + archive créée | — |

**Ce qui reste = 3 ADRs brouillons à rédiger** (P1-01, P1-02, P1-03 → Sprint N). Effort : ~2-3h par ADR brouillon.

---

## 4. P2 IMPORTANT

**Status : 4/10 fait (+ cette session P2-09)**

| Action | Description | Statut | Issue/PR |
|---|---|---|---|
| [P2-01] | Nettoyage code mort whatsapp-server (3 fichiers obsolètes) | ❌ à faire | Sprint L [#204](https://github.com/ouedraogoissouf2012/wourri/issues/204) |
| [P2-02] | Nettoyage scripts `soloni_*` legacy à la racine wouri-api | ❌ à faire | Sprint L [#204](https://github.com/ouedraogoissouf2012/wourri/issues/204) |
| [P2-03] | Archiver ou supprimer `BACKUP_2026-01-26/` | ❌ à faire | Sprint L [#204](https://github.com/ouedraogoissouf2012/wourri/issues/204) |
| [P2-04] | Nettoyage dossier `whatsapp-server/whatsapp-server/` imbriqué | ✅ Sprint H.0 [PR #195](https://github.com/ouedraogoissouf2012/wourri/pull/195) | — |
| [P2-05] | Compléter documentation projet | ⚠️ partiel | SESSION_RECAP + runbook staging livrés cette session |
| [P2-06] | Créer index ADR | ✅ [`docs/adr/README.md`](adr/README.md) | — |
| [P2-07] | ADR migration Baileys → WhatsApp Cloud API | ❌ vision long terme | (à rédiger plus tard quand budget) |
| [P2-08] | Suppression `asr_quality/` + blocklist | ❌ après Omnilingual validé | (Phase 4 ADR-0003) |
| **[P2-09]** | **Refactoriser ChatService (extraire orchestration)** | ✅ **FAIT CETTE SESSION** | **5 PRs : [#262](https://github.com/ouedraogoissouf2012/wourri/pull/262), [#265](https://github.com/ouedraogoissouf2012/wourri/pull/265), [#266](https://github.com/ouedraogoissouf2012/wourri/pull/266), [#267](https://github.com/ouedraogoissouf2012/wourri/pull/267), [#268](https://github.com/ouedraogoissouf2012/wourri/pull/268)** |
| [P2-10] | Remplacer `print()` par `logger` systématiquement | ❌ à faire | Sprint L [#204](https://github.com/ouedraogoissouf2012/wourri/issues/204) |

**Ce qui reste P2 (hors Sprint L)** : P2-07 ADR WhatsApp Cloud API (vision), P2-08 suppression asr_quality (après Omnilingual validé), P2-05 doc à compléter.

**P2-09 ChatService refactor — résultat chiffré** :
- `chat_service.py` : 660 → **274 lignes (-58%)**
- Nouveau sous-package `app/services/chat/` : 6 modules (_types, meteo_injector, city_detector, nlu_preprocessor, ivr_searcher, deepseek_router)
- Tests : +39 (de 258 à 297)

---

## 5. P3 VISION

**Status : 1/6 fait (normal pour de la vision)**

| Action | Description | Statut |
|---|---|---|
| [P3-01] | Évaluer Pipecat + Twilio IVR P2 (téléphonique) | ❌ vision |
| [P3-02] | Analyse concurrentielle Farmerline Darli AI + Farmer.CHAT | ❌ vision |
| [P3-03] | Évaluer Gooey.AI comme benchmark/brique | ❌ vision |
| [P3-04] | Pivot business : subventions/B2G vs VC equity | ❌ vision (décision toi + investisseurs) |
| [P3-05] | Clarifier souveraineté DeepSeek (LLM chinois pour data CI) | ❌ vision |
| [P3-06] | Correction préventive APDP → ARTCI dans futures docs | ✅ MEMORY.md déjà à jour, corrections au fil de l'eau |

**P3 = à activer dans 3-12 mois selon contexte stratégique** (financement, partenariats, etc.).

---

## 6. Sprints Roadmap (#209)

**Status : 2/8 fait sur la roadmap Sprints I→O + Phase 5**

| Sprint | Description | Statut | Bloqueur |
|---|---|---|---|
| **Sprint I** | Préparation déploiement (Dockerfile.prod + compose + runbook) | ✅ FAIT | — |
| **Sprint J** | Déploiement staging + monitoring | ⚠️ **J.1 préparé** ([PR #254](https://github.com/ouedraogoissouf2012/wourri/pull/254) mergée), J.2-J.5 à exécuter | **TOI** (provisionnement VM Scaleway) |
| **Sprint K** | Phase E ADR-0008 bascule pgvector + dépréciation ChromaDB | ❌ | Bloqué Sprint J |
| **Sprint L** | Cleanup tech-debt (Sprint F follow-ups + backlog tests + P2 plan d'action) | ❌ | Aucun (faisable à 2) |
| **Sprint M** | Qualité ASR + perf | ❌ | (#205) |
| **Sprint N** | ADRs structurants (P1-01/02/03) | ❌ | (#206) |
| **Sprint O** | Corpus v3 enrichissement (18 cultures + QUALITE 1-6) | ❌ | **Locuteur natif** dioula CI (#207 + [ADR-0014](adr/0014-promotion-corpus-v3-dioula-ci.md)) |
| **Phase 5** | Vision long terme (Omnilingual ASR + AfroLID + IVR téléphonique + WhatsApp Cloud API) | ❌ | (#208 — vision) |

**Détail Sprint J** (le plus prioritaire) :
- **J.1 Préparation infra** : ✅ FAIT (PR #254) — docker-compose.staging.yml + Loki/Promtail + runbook 632 lignes
- **J.2 Provisionnement VM** : ⏳ à faire par toi (Scaleway DEV1-S, ~10 €/mois, 1-2h)
- **J.3 Premier déploiement** : ⏳ après J.2 (scan QR WhatsApp + tests health)
- **J.4 Tests E2E** : ⏳ 10 scénarios documentés dans runbook
- **J.5 Workflow CI auto-deploy** : ⏳ PR séparée future

---

## 7. Bugs/issues nouveaux session

| Issue | Type | Statut |
|---|---|---|
| [#260](https://github.com/ouedraogoissouf2012/wourri/issues/260) | Bug : substring collision feedback ("pas bon" → positif au lieu de négatif) | ✅ Fix mergé [PR #264](https://github.com/ouedraogoissouf2012/wourri/pull/264) |
| [#269](https://github.com/ouedraogoissouf2012/wourri/issues/269) | **NOUVEAU bug** : regex `\b` JS ne reconnait pas `ɲ` (Unicode), `\bɲuman\b` ne match jamais | ❌ à fixer (~20 min, futur) |
| [#257](https://github.com/ouedraogoissouf2012/wourri/issues/257) | Followup #213 : `WOURI_API_KEY_FILE` pour whatsapp-server | ❌ à faire (~1h) |
| [#258](https://github.com/ouedraogoissouf2012/wourri/issues/258) | Followup #213 : `url_resolver.py` support `POSTGRES_PASSWORD_FILE` | ❌ à faire (~1h) |
| [#259](https://github.com/ouedraogoissouf2012/wourri/issues/259) | Followup #213+#222 : `API_SECRET_KEY_PREVIOUS_FILE` rotation Docker secrets | ❌ à faire (~1h) |
| **14 PRs corpus dioula** #69-#84 | Réécriture corpus en dioula CI naturel (~120 entrées) | ❌ Bloquées sur locuteur natif (ADR-0014 mergé) |

---

## 8. Ce qui RESTE faisable à 2 (sans tiers)

### Quick wins (~1-2h chacun)
- [#269](https://github.com/ouedraogoissouf2012/wourri/issues/269) Fix bug Unicode word boundary regex (~20 min)
- [P2-02](#) + [P2-03](#) Nettoyage scripts soloni + BACKUP_2026-01-26 (~30 min)
- [P2-10](#) `print()` → `logger` systematique (~1h, find+replace ciblé)
- [#257](https://github.com/ouedraogoissouf2012/wourri/issues/257), [#258](https://github.com/ouedraogoissouf2012/wourri/issues/258), [#259](https://github.com/ouedraogoissouf2012/wourri/issues/259) followups Docker secrets (~1h chacun)
- Audit + nettoyage [P2-01](#) code mort whatsapp-server (~1h)

### Moyens (~3-6h)
- **Sprint L #204** combo : P2-01 + P2-02 + P2-03 + P2-10 + tests follow-ups (#148, #149, #150, #178, #179, #183, #184) = **~4-5j de travail découpable en 3-4 PRs**
- **Sprint N #206 ADRs structurants** (P1-01 AfVoices/ANV + P1-02 Bambara-ASR-v2 + P1-03 AfroLID) = ~2-3h par ADR brouillon, total 6-9h

### Gros chantiers (>1j)
- **Refactor TTS bambara/dioula DRY** (god files identifiés audit `c` précédent) : tts_bambara.py 583 l + tts_dioula.py 538 l → sous-package `app/services/tts/`, ~5-6h, gros gain DRY
- **Refactor ASR normalizer** : asr_normalizer.py 465 l → sous-package `app/services/asr/`, ~3-4h
- **Sprint M qualité ASR + perf** ([#205](https://github.com/ouedraogoissouf2012/wourri/issues/205)) — gros

---

## 9. Ce qui NÉCESSITE un tiers (bloqué)

| Tâche | Tiers requis | Plan |
|---|---|---|
| **Sprint J.2-J.5** staging | TOI physiquement sur Scaleway (compte cloud + carte bancaire) | Runbook prêt dans [`docs/staging-deployment.md`](staging-deployment.md), 1-2h hands-on |
| **Sprint K Phase E pgvector** | Bloqué par Sprint J.2-J.5 | Auto après Sprint J |
| **Sprint O corpus v3** | Locuteur natif dioula CI | [ADR-0014](adr/0014-promotion-corpus-v3-dioula-ci.md) mergé, plan en 5 phases prêt |
| **14 PRs corpus** #69-#84 | Locuteur natif | Label `corpus-v3-dioula-ci` posé, commentaires sur chaque PR |
| **#215 ARTCI conformité** | Avocat / DPO | Décisions policy à prendre (RPO/RTO + rétention légale) |
| **ADR-0013 SSH** ([PR #253](https://github.com/ouedraogoissouf2012/wourri/pull/253) mergée brouillon) | Décision TOI parmi 3 options (self-hosted runner / Tailscale / OIDC) | Recommandation : Tailscale (mais à valider) |
| **QUALITE-6 [#92](https://github.com/ouedraogoissouf2012/wourri/issues/92)** contact locuteur natif | Locuteur natif | Sprint O |
| **P3-04 pivot business** | TOI (décision subventions vs VC) | Vision |
| **P2-07 ADR WhatsApp Cloud API** | TOI + Meta Business compte | Quand budget |

---

## 10. Recommandation pour la suite

**Single recommendation** : **Sprint L #204 — cleanup tech-debt en bloc**.

### Pourquoi

1. **Plus haut ROI faisable à 2** : regroupe 9 items du backlog dans 1 sprint
2. **0 décision externe** : tout est faisable sans tiers
3. **+60% completion du plan d'action** : termine TOUT le cleanup P2 d'un coup
4. **Découpable** : 3-4 PRs successives sur ~4-5 jours

### Contenu Sprint L détaillé

| Item | Effort | Type |
|---|---|---|
| [P2-01] code mort whatsapp-server (3 fichiers) | ~1h | hygiène |
| [P2-02] scripts `soloni_*` legacy | ~30 min | hygiène |
| [P2-03] archiver `BACKUP_2026-01-26/` | ~15 min | hygiène |
| [P2-10] `print()` → `logger` | ~1h | code quality |
| [#148] couverture `_clarify_missing_culture` | ~1h | test |
| [#149] test miroir auth-on upload limits | ~1h | test sécurité |
| [#150] assertion par négation faible | ~30 min | test fix |
| [#178] Phase B follow-up : score_validation CHECK + reponse_fr nullable | ~1-2h | conformité ADR |
| [#179] Phase B follow-up : tests EXPLAIN GIN/ivfflat | ~2-3h | test infra |
| [#183] Phase C follow-up : couverture tests corpus_service + corpus_facade | ~2h | test |
| [#184] Phase C follow-up : validation longueur embedding + dim guard | ~1h | sécurité |

**Total estimé** : ~12-15h réparties sur 3-4 PRs.

### Ordre de merge recommandé

1. **PR 1 — Hygiène repo** (P2-01 + P2-02 + P2-03) : ~2h, 0 risque
2. **PR 2 — Tests backlog Sprint B** (#148 + #149 + #150) : ~2-3h, ajout tests
3. **PR 3 — `print()` → `logger`** (P2-10) : ~1h, refactor pur
4. **PR 4 — Sprint F follow-ups** (#178 + #179 + #183 + #184) : ~6-8h, conformité ADR-0008

### Alternative (si tu préfères)

**Refactor TTS DRY** (god files tts_bambara/tts_dioula) — ~5-6h, gros gain qualité. Mais P2-09 viens d'être fait, donc Sprint L (cleanup) peut être plus apaisant.

---

## Référence rapide — bilan session 29-30-31 mai 2026

| Métrique | Valeur |
|---|---:|
| PRs mergées session | **25** |
| Issues fermées | 14 |
| Issues backlog créées | 5 |
| Tests Python | 188 → 324 (+72%) |
| Tests WhatsApp | 213 → 219 (+3%) |
| Refactor #233 bambara_validator | ✅ 100% (4 PRs) |
| Refactor #204 P2-09 chat_service | ✅ 100% (5 PRs) |
| Bug critique #260 | ✅ fix mergé |
| Nouveau bug #269 détecté | ⚠️ tracé pour fix futur |
| Sub-package `app/services/chat/` | 6 modules |
| Tag stable | `v0.17.0-stable` |
| ADRs livrés brouillons | 2 (ADR-0013, ADR-0014) |
| MEMORY.md | 203 → 101 lignes (-50%) |

---

**Document à relire à ton rythme**. Quand tu veux discuter d'une action précise, référence-la par son code (P2-X, Sprint Y, #N) — j'ai tout le contexte.
