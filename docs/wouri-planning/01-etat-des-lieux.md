# 01 — État des lieux WOURI

**Date de l'audit** : 2026-10-11
**Méthode** : lecture du code réel, de l'historique Git et de la configuration. Aucune
fonctionnalité n'est décrite sans preuve. Aucun service externe n'a été modifié.

## Conventions de fiabilité

| Marque | Sens |
|---|---|
| ✅ **CONFIRMÉ** | Vérifié directement dans le code, un fichier versionné ou l'historique Git |
| 🟡 **PARTIEL** | Le mécanisme existe, mais sa portée ou son effet réel n'est pas entièrement vérifié |
| 🔍 **À VÉRIFIER** | Nécessite un accès ou une exécution non réalisée dans cette mission |
| ❌ **ABSENT** | Recherché et non trouvé |

---

## 1. Périmètre réel du dépôt

✅ **CONFIRMÉ** — Le dossier `wourri/` n'est **pas** un dépôt Git. Il contient **deux dépôts
distincts** :

| Dépôt | Branche de production | Rôle |
|---|---|---|
| `wouri-api/.git` | `APIPy` | API FastAPI, NLU, corpus, ASR/TTS, atelier LQE |
| `whatsapp-server/.git` | `whatsappServeur` | Passerelle Baileys (WhatsApp) |

✅ **CONFIRMÉ** — Stratégie de **branches orphelines multiples** documentée par
[ADR-0037](../adr/0037-conserver-multibranches-orphelines.md). Des copies de travail
supplémentaires existent à la racine (`wa-lqe-backend/`, `wb-lqe-web/`, `wc-moteur/`,
`wd-adr/`) : ce sont des *worktrees*, pas des dépôts séparés.

⚠️ **Point d'attention** — Des artefacts **hors dépôt** subsistent à la racine :
`finetune/` (daté de mars 2026), `cv-corpus-24.0-2025-12-05-dyu/`, `BACKUP_*.zip`, `output/`,
`debug_audio/`. Le dossier `finetune/` racine est une **copie obsolète** : la version de
référence est versionnée sous `finetune/colab/` sur `APIPy` (7 notebooks).

## 2. Volumétrie mesurée

| Indicateur | Valeur | Source |
|---|---|---|
| Fichiers Python (API) | **122** | `find wouri-api/app -name '*.py'` |
| Lignes Python (API) | **16 821** | idem |
| Fichiers de test | **98** | `find tests -name 'test_*.py'` |
| Organisation des tests | `tests/unit`, `tests/integration`, `tests/e2e` | arborescence |
| ADR rédigés | **40** (0001→0040) | `docs/adr/` sur `APIPy` |
| Entrées corpus IVR | **197** | `dictionnaires/corpus_ivr.json` |
| Concepts NLU | **60** | `dictionnaires/nlu_concepts.json` |
| Issues ouvertes | **43** | `gh issue list` |
| PR ouvertes | **0** | `gh pr list` |

🔴 **Écart documentaire confirmé** — `CLAUDE.md` annonce « corpus IVR v2.3, **163** entrées »
et « **54** concepts NLU ». Les fichiers réels en contiennent **197** et **60**. La
documentation d'amorçage est **désynchronisée** : tout agent ou développeur qui s'y fie
raisonne sur des chiffres faux.

## 3. Livraisons récentes (octobre 2026)

✅ **CONFIRMÉ** par `git log origin/APIPy` :

| Commit | Apport |
|---|---|
| `a240b08` | Boucle de retour à l'agriculteur ([ADR-0040](../adr/0040-boucle-de-retour-agriculteur.md)) |
| `2c035e9` | Garde LLM : interdiction d'inventer sur les faits vérifiables ([ADR-0039](../adr/0039-politique-reponse-llm-et-escalade.md)) |
| `a01cc17` | Question météo à horizon lointain → escalade au lieu de la météo du jour |
| `2927744` | Création de `/app/data` dans l'image (persistance de la file d'amélioration) |
| `a71e681` | Embarquer la question de l'agriculteur, pas l'étiquette d'intent |
| `c8975dd` | Test mécanique du fine-tune Omnilingual baoulé (#474) |

Le rythme de livraison est **soutenu et tracé** : chaque correctif porte un numéro d'issue et,
pour les décisions structurantes, un ADR.

## 4. Ce qui fonctionne aujourd'hui

✅ **CONFIRMÉ** — Cascade de réponse (ADR-0015) : `IVR exact → IVR concept → répondeurs
déterministes (météo / date / culture-zone) → LLM`, implémentée dans
`app/services/chat_service.py` et `app/services/chat/handlers/`.

✅ **CONFIRMÉ** — Garde anti-invention (`app/services/chat/llm_guard.py`) : sur les familles
de questions à réponse vérifiable, le LLM est **court-circuité** et la question est escaladée
vers un expert.

✅ **CONFIRMÉ** — Anonymisation irréversible des utilisateurs
(`app/core/pii_utils.py::anonymize_user_id`, SHA-256 salé) et refus d'écriture de toute PII
dans la file d'amélioration (`app/services/improvement_queue.py`).

## 5. Les trois faiblesses structurelles

Détaillées dans [08-risques-et-decisions.md](08-risques-et-decisions.md) :

1. 🔴 **Aucun chiffre de qualité mesuré pour le dioula** — le protocole existe, il n'a jamais
   été exécuté.
2. 🔴 **Aucune sauvegarde automatisée de la base** — uniquement des procédures écrites.
3. 🔴 **Aucun document de consentement** pour les enregistrements vocaux.
