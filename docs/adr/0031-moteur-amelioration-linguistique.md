# ADR-0031 — Moteur d'amélioration linguistique (statuts, rôles, publication)

**Statut** : accepté
**Date** : 2026-08-16
**Auteur(s)** : Claude (sous direction Issouf)
**Valideur** : Issouf (ouedraogoissouf2012) — accepté 2026-08-16 (« fait » après merge #434)

---

## Contexte

WOURI sert déjà des phrases dioula **en production** (`corpus_entries` pgvector,
import Convex L3 #410). La règle métier est claire : **ne pas inventer** du
dioula ; un LLM ne publie pas dans le corpus (ADR-0014, ADR-0019).

Le trou opérationnel : il n'existe **pas de niveaux de confiance** ni d'écran
locuteur. Une fiche est soit dans pgvector (servie), soit dehors. D'où le
blocage #298 / #355 (« on attend le natif ») et le risque d'importer du bambara
malien comme du dioula CI.

Issouf a validé le produit (2026-08-16) : locuteur connecté → **sa** langue
seulement ; « grand locuteur » dépose des trouvailles ; **l'admin** corréle
avec des sources de vérité avant le corpus ; un curieux pourra tester plus tard
sans écrire.

Issues : epic #428, ADR #429, T1a #430, T1b #431, T1c #433, plus tard #432.

**Contraintes** : qualité > vitesse ; pas de 2ᵉ store parallèle ; pas de 2ᵉ
auth (#372 / ADR-0030) ; ARTCI (pas de numéro sur les écrans) ; `corpus_service.py`
reste la lecture runtime.

## Questions posées avant la décision

1. Où vivent les statuts et les validations ?
2. Qui peut publier dans le corpus servi par WhatsApp ?
3. Comment isoler Baoulé / Bété plus tard sans `if` métier ?
4. Un 2ᵉ système d'auth FastAPI est-il acceptable ?

Réponses (session 2026-08-16) :

- Q1 → Convex = atelier de validation ; pgvector = runtime Or+ / Production.
- Q2 → locuteur vote ; **admin** promeut après corrélation de sources.
- Q3 → **1 compte = 1 langue** (org / membership Convex). Pilote = `dyu_ci`.
- Q4 → **non** : réutiliser Better Auth / RBAC #372.

## Options étudiées

### Option A — Convex atelier + pgvector runtime (recommandée)

- **Description** : Bronze / Argent / Or / Production et `source_lang`
  (`dyu` | `bam` | …) vivent dans Convex. L'import L3 n'écrit dans
  `corpus_entries` que les fiches **Or ou Production**. Auth/rôles = #372.
  File 👎 / ingest → tâches locuteur. File admin = sas avant import.
- **Avantages** : un seul atelier ; WhatsApp inchangé ; compatible #410
  (fusion texte Convex + tags locaux) ; isolation multi-langue = orgs.
- **Inconvénients** : dépend du merge / brancher #373 (auth). Tant que #373
  est draft, T1c (écrans) attend ; T1a peut préparer le **contrat** d'export.
- **Coût** : moyen. Pas de nouvelle BDD.
- **Compatibilité** : ✅ ADR-0014, 0019, 0030.

### Option B — Tables de validation dans PostgreSQL / FastAPI

- **Description** : nouveaux modèles SQL + UI FastAPI/Jinja, auth maison.
- **Avantages** : indépendant de #373.
- **Inconvénients** : **2ᵉ identité** + 2ᵉ file à côté de Convex. Contredit
  ADR-0030. Gonfle `wouri-api` (déjà >300 lignes sur les god-files).
- **Coût** : court terme plus vite, long terme double maintenance.
- **Compatibilité** : ❌ trajectoire Convex.

### Option C — Tableur / outil externe (Sheets, Airtable)

- **Description** : natifs valident hors repo ; import manuel JSON.
- **Avantages** : zéro code auth.
- **Inconvénients** : pas d'isolation de langue, pas d'audit, pas de file
  reliée au 👎 WhatsApp. Ce n'est pas un produit.
- **Compatibilité** : ⚠️ palliatif, pas une architecture.

### Comparatif

| Critère | A Convex atelier | B FastAPI maison | C Tableur |
|---|---|---|---|
| Duplication auth / corpus | Aucune | Deux systèmes | Hors système |
| Isolation 1 locuteur = 1 langue | Org Convex | À construire | Non |
| WhatsApp / `corpus_service` | Inchangés | Risque de couplage | Manuel |
| Alignement ADR-0030 / #372 | ✅ | ❌ | — |
| Time-to-écran T1 | Attend #373 | Plus tôt | Immédiat et fragile |

## Décision

**Option retenue** : **A**.

### Statuts

| Niveau | Origine typique | Servi WhatsApp / IVR |
|---|---|---|
| Bronze | LLM, web, bam voisin, grand locuteur | **Non** |
| Argent | 1 relecture locuteur | **Non** |
| Or | Natif (+ métier si conseil agricole) | Oui, via import L3 |
| Production | Or testé terrain | Oui |

`source_lang=bam` ne passe **jamais** en Production sans revalidation `dyu` CI.

### Rôles

| Rôle | Peut | Ne peut pas |
|---|---|---|
| Curieux (hors T1) | tester, noter | écrire le corpus |
| Locuteur | valider **sa** langue | publier en Production |
| Grand locuteur | déposer Bronze | sauter le sas admin |
| Admin | corréler sources, promouvoir Or/Prod | inventer du dioula |

### Publication

```
👎 / ingest / grand locuteur
        → tâche Bronze (#431)
        → écran locuteur (#433)
        → file admin
        → Or / Production
        → import L3 (#410) → pgvector
```

Un LLM ne déclare jamais une phrase correcte. `import_corpus_from_convex.py`
**filtre** : pas Or+ → pas d'écriture `corpus_entries`.

### Isolation langues

Pas de `if language == "baoule"` dans le moteur. Une 2ᵉ langue = nouvelle org
+ locuteurs membres. Pilote T1 = **dyu_ci uniquement**.

### Auth

Réutiliser #372. **Interdit** : JWT maison parallèle, comptes en dur dans
FastAPI pour les locuteurs.

## Conséquences

- **Positives** : débloque #298 / #355 sans inventer du dioula ; WhatsApp
  reste autonome si Convex down.
- **Négatives assumées** : écrans T1c attendent un socle auth mergé (#373).
- **Travail induit** : #430 contrat + filtre import ; #431 tâches ; #433 UI
  après acceptation **et** auth disponible.
- **Verrous** : pgvector n'est plus un atelier d'édition humaine.
- **Rollback** : retirer le filtre Or+ de l'import (le runtime ne change pas).

## Références

- Epic #428, ADR #429, T1a #430, T1b #431, T1c #433, plus tard #432
- [ADR-0014](0014-promotion-corpus-v3-dioula-ci.md), [ADR-0019](0019-feedback-c3-revue-native.md),
  [ADR-0020](0020-filtre-bam-dyu-perimetre-reduit.md), [ADR-0030](0030-plateforme-api-produit-convex.md)
- Import L3 #410 (PR #420)

## Historique

- 2026-08-16 — rédaction initiale, statut **proposé**, Option A recommandée.
- 2026-08-16 — **accepté** (Issouf, session après merge PR #434).
