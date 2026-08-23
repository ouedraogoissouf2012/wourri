# ADR-0034 — Atelier de parité linguistique : concepts multilingues, assignations & audio natif

**Statut** : **accepté**
**Date** : 2026-08-22 (proposé) · 2026-08-23 (accepté)
**Auteur(s)** : Issouf Ouédraogo + assistance agent
**Valideur** : Issouf — « je valide » 2026-08-23

---

## Contexte

- Wourri est un **bot vocal agricole**. La Côte d'Ivoire compte **~60 langues** ; dioula (`dyu`), baoulé (`bci`), bété (`btg`/`bev`/`bet`) sont les **3 premiers pilotes**, pas la cible finale.
- Le **corpus dioula** (`dictionnaires/corpus_ivr.json`, 163 concepts validés : `intent × cultures × conditions`, `reponse_fr`, `reponse_bambara`) est la **langue de référence**.
- L'atelier LQE (ADR-0033) existe déjà (service séparé, RBAC, flux bronze→accepter→promouvoir) mais : stocke en **JSONL**, ne gère **pas** l'audio, et n'a **aucun mécanisme de parité inter-langues** ni d'assignation.
- **Recherche du 2026-08-22 (4 angles sourcés)** :
  - (a) **aucun TTS baoulé/bété** n'existe et en construire un est long/incertain (tons + harmonie vocalique ATR) ; l'**audio natif humain** est l'approche éprouvée des IVR agricoles africains (Viamo 3-2-1, ANADER e-Extension CI, Farm Radio, Avaaj Otalo).
  - (b) L'ASR baoulé/bété-Gagnoa devient possible via **Omnilingual ASR** (Meta, nov. 2025, Apache-2.0) — mais c'est un **autre chantier** (comprendre ≠ produire).
  - (c) Les poids **MMS = CC-BY-NC** (non commercial). **Wourri n'est pas commercial** → usage acceptable (dette tracée si évolution commerciale).
- **Correction ISO** : le bété ivoirien = `bev` (Daloa), `btg` (Gagnoa), `bet` (Guiberoua) — **pas** `bte` (= Gamo-Ningi, Nigeria).

## Questions posées → réponses (discussion 2026-08-22/23)

1. Pivot de traduction ? → **le français** (le sens) ; le dioula reste une **référence** affichée.
2. Source des contenus ? → **le corpus existant** (l'admin *pioche*, ne saisit pas) ; saisie manuelle **débloquée seulement** quand la langue est à jour → **« parité avant extension »**.
3. Voix ? → **audio natif requis**, texte optionnel (enregistrement navigateur `MediaRecorder` + téléversement).
4. Échelle ? → **architecturer pour ~60 langues** (piloter sur 3). **Zéro `if`-langue** dans le métier.
5. Stockage ? → **PostgreSQL + pgvector**.
6. Clé de concept ? → l'**`id` du corpus IVR** ; le baoulé validé **reste dans l'atelier** (pas d'injection moteur tant qu'il n'y a pas de canal WhatsApp de cette langue).
7. Commercial ? → **non** (pour l'instant).

## Options étudiées

### Option A — Atelier générique « concept × langue » + assignations + audio natif (pgvector) *(retenue)*
- **Description** : référentiel de langues *first-class* ; matrice de couverture ; l'admin assigne **par lot** les concepts manquants (consigne = français) ; le locuteur produit **texte + audio natif** → flux bronze→accepter→promouvoir existant réutilisé. Interfaces `ConceptCatalog` / `AudioStore` (OCP).
- **Avantages** : scale à 60 langues (langue = donnée) ; produit une **réponse vocale** en baoulé/bété (seule voie viable) ; parité pilotée et mesurable ; robuste (Postgres transactionnel) ; construit le **premier corpus vocal natif** de ces langues.
- **Inconvénients** : réintroduit Postgres + l'audio dans l'atelier (plus léger avant) ; migration JSONL→Postgres des données existantes.
- **Coût** : moyen — surtout du **câblage sur l'existant** (le flux de validation existe déjà).
- **Compatibilité** : respecte l'exigence « extensible non modifiable » et « zéro `if`-langue ».

### Option B — Prolonger l'existant (JSONL par langue, saisie libre, sans audio)
- Rapide, mais **pas de parité pilotée**, **pas d'audio** (donc **aucune réponse vocale** en baoulé/bété), JSONL non transactionnel, matrice ingérable à 60 langues. → **impasse produit**.

### Option C — Tout automatique (TTS/ASR synthétique par langue, sans humain)
- Rejetée par la recherche : **pas de TTS** baoulé/bété, qualité tonale risquée (ATR). Irréaliste à court/moyen terme.

### Comparatif

| Critère | A (retenue) | B | C |
|---|---|---|---|
| Scale à 60 langues | ✅ (langue = donnée) | ❌ (JSONL/CSV env) | ⚠️ dépend de modèles absents |
| Réponse vocale bci/bté | ✅ audio natif | ❌ aucune | ❌ (pas de TTS) |
| Parité pilotée | ✅ matrice + assignations | ❌ | ❌ |
| Robustesse données | ✅ Postgres transactionnel | ❌ JSONL | — |
| Coût / délai | moyen (câblage sur l'existant) | faible mais jetable | très élevé, incertain |
| `if`-langue en dur | **zéro** | risque | risque |

## Décision

**Option A**, avec :

1. **Modèle** : `concept` (clé = `id` du corpus IVR, pivot = `text_fr`) × `langue`. **Référentiel `languages`** : ISO-639-3, nom, famille, script, disponibilité ASR/TTS, **statut `active` / `backlog`**. **Matrice de couverture** = requête SQL (concepts × langues).
2. **Assignations** : l'admin sélectionne un **lot** de concepts manquants → le système extrait le **français** → assignation à une langue cible. **Garde « parité avant extension »** : nouveau concept manuel bloqué tant que la langue courante n'est pas à jour.
3. **Production** : onglet « Demandes » (consigne FR + référence dioula + `intent`/`cultures`) → **audio natif requis** + texte optionnel → bronze → accepter → promouvoir (flux existant, inchangé).
4. **Stockage** : **PostgreSQL + pgvector** (relationnel + recherche sémantique pour la déduplication de concepts). **Amende** le choix « JSONL léger » de l'ADR-0033.
5. **Médias** : interface `AudioStore` (volume local aujourd'hui → stockage objet demain).
6. **Architecture SOLID / OCP** : 5 briques (Catalogue, Couverture, Assignations, Production, Médias), dépendances par **interfaces injectées**, **zéro `if`-langue**.

## Conséquences

- **Positives** : construit le premier **corpus vocal natif** baoulé/bété agricole (inexistant ailleurs) ; scale à 60 langues ; alimente **plus tard** le fine-tuning ASR/TTS ; robuste.
- **Négatives assumées** : introduit Postgres+pgvector **et l'audio** dans l'atelier ; « comprendre les questions » **non résolu ici** (ADR séparé) ; migration JSONL→Postgres des données atelier.
- **Migration / travail induit** : schéma Postgres (`languages`, `concepts` = vue/lecture du corpus IVR, `productions`, `assignments`, `media`) ; **pont lecture seule** moteur→atelier pour le catalogue ; front : onglet « Demandes » + enregistrement audio + écran admin « Assigner ».
- **Verrous futurs** : la clé de concept = `id` IVR → couple l'atelier au schéma d'id du moteur (acceptable).
- **Dettes tracées** : (1) licence MMS **non-commerciale** → migrer (Omnilingual/WAXAL) si Wourri devient commercial ; (2) « comprendre » baoulé/bété = **ADR séparé** (Omnilingual ASR, cf. ADR-0003).

## Références

- Recherche interne 2026-08-22 (4 angles web sourcés) :
  - MMS — table de couverture officielle : https://dl.fbaipublicfiles.com/mms/misc/language_coverage_mms.html (baoulé/bété = LID only ; `dyu` complet).
  - Omnilingual ASR — https://github.com/facebookresearch/omnilingual-asr ( `bci_Latn`, `btg_Latn`, `dyu_Latn` supervisés ; Apache-2.0).
  - Google WAXAL — https://huggingface.co/datasets/google/WaxalNLP (voix baoulé réutilisable).
  - Kallaama (protocole collecte agricole) — https://arxiv.org/abs/2404.01991 ; Viamo 3-2-1 — https://viamo.io/services/3-2-1/ ; ANADER e-Extension CI — https://sti-portal.fao.org/innovations/anaders-e-extension-system-cote-divoire.
- ADR liés : **ADR-0033** (atelier service séparé — *amendé* ici sur le stockage) ; **ADR-0031** (moteur d'amélioration) ; **ADR-0003** (plan ajout Omnilingual — volet « comprendre ») ; ADR corpus pgvector du moteur.

## Historique

- 2026-08-22 — proposé (Option A).
- 2026-08-23 — **accepté** par Issouf.
