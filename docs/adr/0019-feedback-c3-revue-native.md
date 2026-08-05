# ADR-0019 — Feedback utilisateur : signal analytics + file de revue native (refonte C3)

**Statut** : accepté
**Date** : 2026-08-05
**Auteur(s)** : Claude (assistant) sous direction de Ouedraogo Issouf
**Valideur** : Ouedraogo Issouf

---

## Contexte

Le circuit d'auto-apprentissage « C3 » ajoute des réponses au corpus à partir du
feedback utilisateur. État factuel vérifié dans le code (`origin/APIPy`, 2026-08-05) :

- `app/routers/feedback.py:65-83` : sur un feedback 👍 dont `source ∈ {ivr_fallback,
  fallback_generic}` avec `reponse_bambara` non vide, le code appelle
  `corpus_facade.ajouter_reponse_validee(...)` avec `score_validation = 0.80`
  **hardcodé** et tags `["feedback_positif", "auto_appris"]`.
- L'ajout va dans **ChromaDB** (`vdb_service.py:310-349`, id `dynamic_{intent}_{culture}_{ts}`,
  `source="auto_validated"`), **jamais** dans le fichier `dictionnaires/corpus_ivr.json`.

Deux problèmes structurants (issue #338) :

### Problème 1 — l'ajout est perdu à chaque redémarrage (fonctionnalité de facto cassée)
`vdb_service.py:117-137` déclenche un rebuild complet de la collection Chroma dès que
`vdb_count != len(corpus_entries)` (nb d'entrées Chroma ≠ nb d'entrées du JSON).
Or l'auto-ajout **incrémente précisément `vdb_count`**. Séquence :

1. feedback 👍 → +1 entrée `dynamic_*` dans Chroma (`vdb_count` = N+1)
2. redémarrage → `needs_rebuild = (N+1 ≠ N)` → **VRAI** → `delete_collection` + repeuplement depuis le JSON (N entrées)
3. → l'entrée auto-apprise **disparaît**

L'auto-apprentissage ajoute puis perd systématiquement. La fonctionnalité n'apporte rien.

### Problème 2 — il contredit le principe fondateur du projet
Le corpus est enrichi **sans aucune validation native** (`score_validation=0.80` attribué
par le code, pas par un humain). Cela viole la règle d'or gravée dans l'ADR-0014,
`GRAMMAIRE_DIOULA_REGLES.md` §12bis et `docs/GUIDE_DIOULA_CIRCUIT_ET_METHODE.md` :

> **« Aucune IA ne parle correctement dioula. Le locuteur natif de Côte d'Ivoire
> fait autorité. Seule la décision validée entre en production. »**

Une réponse DeepSeek fallback (`ivr_fallback`) est du dioula IA non validé. Un feedback 👍
d'un utilisateur peu alphabétisé ne constitue pas une validation linguistique native.

**Pourquoi on décide maintenant** : le chantier de validation native du corpus v3 vient
d'aboutir à 100 % (162/162, PR #336). Laisser C3 injecter du dioula non validé dans le
store réintroduirait exactement le problème que ce chantier a résolu.

## Questions posées avant la décision

1. Quel doit être le sort de C3 (auto-apprentissage) ?
2. À quoi doit servir le feedback utilisateur 👍/👎 dans la vision produit ?

Réponses obtenues (Ruben, 2026-08-05) :

- **Q1 → Transformer C3 en file de revue native.** Le feedback 👍 ne va plus au corpus
  directement ; il alimente une file d'attente persistante de propositions qu'un
  locuteur natif valide plus tard (comme le processus des formulaires PDF).
- **Q2 → Le feedback est un signal pour améliorer (analytics).** Il ne modifie JAMAIS
  le corpus automatiquement ; il sert à identifier les réponses qui marchent/ne marchent
  pas et à prioriser les réécritures. La qualité reste garantie par la validation native.

## Options étudiées

### Option A — Feedback = signal analytics + file de revue native *(alignée sur les réponses)*

- **Description** :
  - Le feedback 👍/👎 est **toujours logué** (analytics : dashboard #41, priorisation).
  - Sur un 👍 concernant une réponse `ivr_fallback`/`fallback_generic`, la réponse est
    ajoutée à une **file de candidats persistante** (fichier versionnable
    `data/feedback_candidates.jsonl`), PAS au store vectoriel.
  - Un candidat n'entre au corpus que **via le processus de validation native existant**
    (formulaire → natif → promotion), jamais automatiquement.
  - Suppression de l'appel `ajouter_reponse_validee()` depuis `feedback.py`.
- **Avantages** :
  - Respecte l'ADR-0014 : aucune donnée non validée n'entre au corpus.
  - Corrige le problème 1 (plus de `dynamic_*` volatiles → plus de perte au rebuild).
  - Le feedback garde toute sa valeur (signal + réservoir de candidats à valider).
  - Réutilise le pipeline de validation native déjà éprouvé.
- **Inconvénients** : le corpus ne grandit plus « tout seul » — l'enrichissement passe
  toujours par une revue native (mais c'est l'intention).
- **Coût** : faible. Retrait de ~15 lignes dans `feedback.py`, ajout d'un writer JSONL
  candidats, tests.
- **Compatibilité** : conforme `constraints.md`, ADR-0014, vision produit.

### Option B — Désactiver C3 complètement

- **Description** : retirer l'auto-apprentissage ; le feedback est seulement logué.
  Aucune file de candidats.
- **Avantages** : le plus simple et le plus sûr ; aucune donnée non validée n'entre.
- **Inconvénients** : perd le réservoir de « bonnes réponses fallback repérées » — un 👍
  sur une réponse DeepSeek utile est oublié au lieu d'être proposé à la validation.
- **Coût** : très faible.
- **Compatibilité** : conforme, mais moins riche que A (Q1 demandait explicitement une
  file de revue, pas une simple désactivation).

### Option C — Réparer la persistance + garder l'auto-ajout sans validation native

- **Description** : corriger le bug de rebuild (persister les `dynamic_*`) mais continuer
  d'ajouter automatiquement au corpus servi, sans revue native.
- **Avantages** : le corpus grandit sans effort humain.
- **Inconvénients** : **viole le principe fondateur** — injecte du dioula IA non validé
  dans le store servi aux agriculteurs. Rejeté sur Q1 et Q2.
- **Coût** : moyen (persistance Chroma).
- **Compatibilité** : ❌ contraire à l'ADR-0014 et à la vision.

### Comparatif

| Critère | A (analytics + file revue) | B (désactiver) | C (réparer auto-ajout) |
|---|---|---|---|
| Respecte ADR-0014 (natif tranche) | ✅ | ✅ | ❌ |
| Corrige la perte au rebuild | ✅ (plus de dynamic_*) | ✅ | ⚠️ (persiste mais garde le mal) |
| Conserve la valeur du feedback | ✅ (signal + candidats) | ⚠️ (signal seul) | ✅ |
| Enrichissement corpus | via revue native | manuel pur | auto (non validé) |
| Coût dev | faible | très faible | moyen |
| Aligné réponses Ruben | ✅ Q1+Q2 | partiel | ❌ |

## Décision

**Option retenue** : **A — Feedback = signal analytics + file de revue native**
(validée par Ruben le 2026-08-05).

**Justification** : elle répond exactement aux deux réponses stratégiques (file de revue
native + feedback comme signal), corrige le problème de perte au rebuild en supprimant la
source du mal (les entrées `dynamic_*`), et rétablit la conformité à l'ADR-0014 sans
sacrifier la valeur du feedback (qui devient un réservoir de candidats à valider + un
signal analytics).

## Conséquences

- **Positives** : corpus servi = uniquement du dioula validé nativement ; plus de perte
  silencieuse ; le feedback nourrit le dashboard et la file de validation.
- **Négatives assumées** : l'enrichissement du corpus reste un acte humain (revue native)
  — c'est voulu.
- **Migration / travail induit** :
  1. `feedback.py` : retirer l'appel `ajouter_reponse_validee()` ; sur 👍 fallback, écrire
     un candidat dans `data/feedback_candidates.jsonl` (intent, cultures, reponse_bambara,
     reponse_fr, ts, user anonymisé, status="pending_native_review").
  2. Nettoyer le store des entrées `dynamic_*`/`auto_validated` existantes (au prochain
     rebuild elles disparaissent de toute façon ; documenter).
  3. Optionnel : petit outil `tools/review_feedback_candidates.py` pour transformer la
     file en formulaire de validation (réutilise `generate_culture_validation_pdf.py`).
  4. Mettre à jour `docs/GUIDE_DIOULA_CIRCUIT_ET_METHODE.md` §2.3 (C3 devient file de revue).
  5. Tests : un 👍 fallback écrit un candidat (pas d'ajout au store) ; un 👍 `ivr_exact`
     ne fait rien ; un 👎 logue en négatif ; aucune entrée `auto_validated` créée.
  - **Rollback** : réversible (réintroduire l'appel). Aucune migration de données destructive.
- **Verrous futurs** : si un jour on veut un vrai apprentissage semi-automatique, il devra
  passer par la file de revue native (jamais d'ajout direct).

## Références

- Issue #338 (auto-apprentissage C3 perdu au redémarrage)
- Code : `app/routers/feedback.py:45-144`, `app/services/vdb_service.py:117-137,310-349`,
  `app/services/corpus_facade.py:367-412`
- ADR-0014 (promotion corpus v3 — principe « le natif tranche »)
- ADR-0008 (façade stockage Chroma/pgvector)
- `docs/GUIDE_DIOULA_CIRCUIT_ET_METHODE.md` §2.3 (circuit C3 documenté)

## Historique

- 2026-08-05 — rédaction initiale (statut proposé), après questions stratégiques à Ruben.
- 2026-08-05 — **accepté** par Ruben (Option A). Implémentation autorisée.
