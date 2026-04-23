# Session complète 2026-04-22 / 2026-04-23 — Log exhaustif

**Contexte de sauvegarde** : PC de Ruben risque de s'éteindre (chargeur défaillant). Ce fichier préserve l'intégralité du fil de travail pour que rien ne soit perdu même en cas de perte disque.

---

## Vue d'ensemble — Ce qui a été livré en 2 jours

### Sprint 1 — P0 Sécurité (2026-04-22, validé 2026-04-23)

**9 commits livrés, 5/5 tests d'intégration passés.**

| Action | Commit wouri-api | Commit whatsapp-server |
|---|---|---|
| P0-04 debug=False par défaut | `7beb63e` | — |
| P1-04 Cache `_load_corpus_entries` | `aa8b7ce` | — |
| P0-02 Auth 15 routes backend | `56f4cb9` | — |
| P0-02a Envoi X-API-Key WhatsApp | — | `bf40759` |
| P0-03 Rate limit 15 routes | `e7ca6a1` | — |
| P0-05 Anonymisation PII SHA-256 | `7fd1ba1` | — |
| P0-02b+P0-05b Fix lecture .env Pydantic | `f961f3f` | — |
| P0-02a bis dotenv.config() | — | `62659ee` |
| P0-01 Révocation clé DeepSeek | Action Ruben dashboard | — |

**Variables .env requises** :
- `wouri-api/.env` : `DEEPSEEK_API_KEY`, `API_SECRET_KEY`, `PII_SALT`
- `whatsapp-server/.env` : `WOURI_API_KEY` (même valeur que `API_SECRET_KEY`)

### Sprint 2 — P1 (2026-04-23, en cours, 2/6 livrés)

| Issue | Action | PR | Status |
|---|---|---|---|
| #97 | [P1-02] Bambara-ASR-v2 benchmark | PR #102 | ✅ mergé |
| #100 | [P1-06] Clarifier mode agentic | PR #103 | ✅ mergé |
| #96 | [P1-01] ADR-0004 corpus African Next Voices + AfVoices | — | ⏸️ ouvert |
| #98 | [P1-03] ADR-0005 AfroLID | — | ⏸️ ouvert |
| #99 | [P1-05] Asynchroniser inférences ML | — | ⏸️ ouvert |
| #101 | [P1-07] Trancher version corpus IVR | — | ⏸️ ouvert |

### Documentation livrée

Tous les fichiers sont dans `wouri-api/docs/` sur branche **APIPy** (poussée sur GitHub) :

| Fichier | Rôle |
|---|---|
| `vision.md` | Vision produit (50+ langues, IVR+WhatsApp, payant, GDPR-like) |
| `constraints.md` | Non-négociables qualité |
| `PLAN_ACTION_2026-04.md` | 22 actions P0→P3 avec IDs référençables |
| `adr/README.md` | Index des ADRs |
| `adr/0000-template.md` | Template réutilisable |
| `adr/0001-choix-stockage-donnees.md` | **ACCEPTÉ** — pgvector remplace ChromaDB |
| `adr/0002-ajout-provider-omnilingual.md` | **ACCEPTÉ** — Omnilingual ASR ajouté à la chain existante |
| `adr/0003-plan-ajout-omnilingual.md` | Proposé — plan migration ASR en 5 phases |
| `adr/0010-migration-monorepo.md` | **ACCEPTÉ 2026-04-23** — migration monorepo après Sprint 2 |
| `benchmarks/0001-asr-dioula-evaluation.md` | Protocole benchmark ASR (6 modèles testés) |

### Décisions architecturales gravées (3 ADRs acceptés)

1. **ADR-0001** : PostgreSQL + pgvector remplace ChromaDB. Migration planifiée.
2. **ADR-0002** : Meta Omnilingual ASR ajouté en tête de chain (ne remplace pas NeMo). `app/services/asr_quality/` à supprimer (duplique `asr_normalizer.py`).
3. **ADR-0010** : Migration vers monorepo (1 repo, branche `main`, sous-dossiers `wouri-api/`, `whatsapp-server/`, `shared/`, `docs/`, `.github/`) après stabilisation Sprint 2. Horizon 3-6 semaines.

### Doctrines de travail en vigueur (gravées en mémoire Claude)

1. **Recommandation unique** — pas de menu A/B/C, UNE solution tranchée
2. **Process ADR obligatoire** — toute décision structurante passe par un ADR
3. **Plan-and-confirm** — plan présenté puis OKAY explicite avant code
4. **Zéro hardcoding** — toute donnée métier externalisée
5. **Qualité > vitesse** — jamais de raccourci
6. **Vérifier avant d'affirmer** — lire le code réel, ne pas supposer
7. **ARTCI** (pas APDP) en Côte d'Ivoire
8. **Issue → branche → commit → PR → merge** — workflow discipline

---

## Découvertes majeures de la recherche 2026-04-22 (6 agents)

### Datasets bambara/dioula critiques NON encore intégrés

- **African Next Voices** (Gates Foundation, nov 2025) — 9 000+h parole spontanée, secteur agriculture — [robotsmali.org](https://robotsmali.org/en/african-next-voices-robotsmali-releases-major-bambara-dataset-models-research-tools/)
- **AfVoices** (RobotsMali, fin 2025) — 423h segmentées + 612h brutes bambara — [huggingface.co/datasets/RobotsMali/afvoices](https://huggingface.co/datasets/RobotsMali/afvoices)
- **Bambara-ASR-v2 sudoping01** (Djelia/MALIBA-AI) — Whisper-large-v2 fine-tuné bambara, Apache 2.0, gère code-switching bambara-français nativement

### Modèle ASR retenu long-terme

- **Meta Omnilingual ASR** (Apache 2.0, nov 2025) — 1 600+ langues dont dyu (CER 6,5%), bam (1,0%), bci/baoulé (10,7%), ann (proche agni 3,1%). **bet/bété absent**.
- Plan B si échec : Djelia/Soloba (Apache 2.0, bambara uniquement)

### Concurrents directs identifiés

- **Farmerline Darli AI** — 1M users, déployé CI francophone 2025 — menace stratégique directe
- **Farmer.CHAT / Digital Green / Gooey.AI** — 830k users, open-source, WhatsApp + RAG
- **Intron Sahara v2** (mars 2026) — 57 langues dont 23 africaines

### Corrections factuelles

- **Régulateur data CI = ARTCI** (pas APDP qui concerne Bénin/Mali)

---

## État actuel du repo GitHub (ouedraogoissouf2012/wourri)

### Branches actives

- **`APIPy`** — branche dev Python backend (tip : `3a8e805` après merge PR #103)
- **`whatsappServeur`** — branche dev Node WhatsApp (tip : `62659ee` Sprint 1)
- **`wourri`** — branche cPanel orpheline (inchangée, à archiver lors migration monorepo)

### Tags backup (poussés sur GitHub le 2026-04-23)

- `backup/APIPy-pre-sprint1` — état avant merge Sprint 1 dans APIPy
- `backup/APIPy-pre-merge` — état APIPy local avant pull remote
- `backup/APIPy-pre-sync` — état origin/APIPy avant pull (incluait PR #9)
- `backup/whatsappServeur-pre-sprint1` — état whatsappServeur avant Sprint 1

### Issues ouvertes Sprint 2

- [#96](https://github.com/ouedraogoissouf2012/wourri/issues/96) P1-01
- [#98](https://github.com/ouedraogoissouf2012/wourri/issues/98) P1-03
- [#99](https://github.com/ouedraogoissouf2012/wourri/issues/99) P1-05
- [#101](https://github.com/ouedraogoissouf2012/wourri/issues/101) P1-07

### 14 Labels créés

`priority:P0/P1/P2/P3`, `project:apipy/whatsapp/docs`, `type:security/adr/corpus/asr/infra/refactor`, `status:wip`

---

## Actions urgentes à faire par Ruben AVANT que le PC s'éteigne

### 🔴 Critique — sauvegarde manuelle nécessaire

Ces fichiers ne sont PAS sur GitHub et seront perdus si le disque tombe :

1. **`wouri-api/.env`** — secrets DEEPSEEK_API_KEY, API_SECRET_KEY, PII_SALT
2. **`whatsapp-server/.env`** — WOURI_API_KEY
3. **`C:\Users\USER PC\.claude\projects\c--Users-USER-PC-Documents-propre---moi-wourri\memory\*.md`** — mémoire persistante Claude (contextualise tout le projet)

**Action recommandée** : copier ces fichiers sur :
- Une clé USB physique
- OU un cloud perso (Google Drive, OneDrive, Dropbox)
- OU les transférer sur un autre téléphone/PC

### 🟠 Important — utile mais reproductibles

- **Modèles HuggingFace en cache** : `~/.cache/huggingface/hub/` — peuvent être re-téléchargés
- **VDB ChromaDB** `wouri-api/data/chroma_ivr/` — reconstructible depuis `corpus_ivr.json`
- **Audios `debug_audio/`** — de test, re-générables
- **Datasets `data/hf_datasets/`** — re-téléchargeables via HuggingFace Hub

### 🟢 Déjà en sécurité sur GitHub

- Tout le code `wouri-api/app/`
- Tous les docs `wouri-api/docs/`
- Tous les dictionnaires `wouri-api/dictionnaires/`
- Tous les tests `wouri-api/tests/`
- Tout le code `whatsapp-server/` (app-baileys.js etc.)
- Tous les tags backup (4 tags)
- Toutes les issues + labels + PRs

---

## Où reprendre après redémarrage

### Depuis une machine propre (worst case)

```bash
git clone https://github.com/ouedraogoissouf2012/wourri.git wouri-api
cd wouri-api
git checkout APIPy
git pull origin APIPy

# Autre clone pour whatsapp-server (même repo, branche différente)
cd ..
git clone https://github.com/ouedraogoissouf2012/wourri.git whatsapp-server
cd whatsapp-server
git checkout whatsappServeur
git pull origin whatsappServeur
```

### Environnement à reconstituer

1. Installer Python 3.12, Node 18+, Git
2. Restaurer `.env` des 2 projets depuis la sauvegarde manuelle
3. `pip install -r requirements.txt` dans wouri-api
4. `npm install` dans whatsapp-server
5. Restaurer `memory/*.md` Claude depuis la sauvegarde (ou recréer depuis ce fichier)

### Prochaine action Sprint 2

**Issue [#101] P1-07** — Trancher la version de référence du corpus IVR (1h, même workflow disciplined).

Plan validé mais non exécuté au moment de la sauvegarde.

---

## Fil conducteur de la session (pour comprendre le "pourquoi")

1. **Continuation d'une session précédente** (résumé compacté dans le transcript)
2. **Mise en place de doctrines strictes** : ADR obligatoire, recommandation unique, plan-and-confirm, pas de hardcoding
3. **Sprint 1 sécurité** livré + testé en intégration avec 2 fix résiduels découverts
4. **Décisions architecturales** gravées : pgvector (ADR-0001), Omnilingual (ADR-0002), monorepo (ADR-0010)
5. **Setup GitHub** : 14 labels + 6 issues P1 créées
6. **Début Sprint 2** : 2 issues closes via workflow issue → branche → PR discipliné
7. **Sauvegarde d'urgence** (ce fichier)

---

*Fichier créé le 2026-04-23 en mode urgence suite problème chargeur PC. Contient l'intégralité du contexte de travail pour permettre reprise depuis une nouvelle machine sans perte de contexte.*
