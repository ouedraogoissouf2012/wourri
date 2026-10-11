# 04 — Inventaire fonctionnel et backlog priorisé

**Date** : 2026-10-11 · Base : 43 issues ouvertes, 0 PR en attente, 40 ADR.

## 1. Matrice fonctionnelle

| Fonctionnalité | Statut réel | Preuve | Risque | Action nécessaire |
|---|---|---|---|---|
| Conversation WhatsApp (texte) | ✅ **En service** | `whatsapp-server/lib/message_handler.js`, `app/routers/chat.py` | Faible | Conserver |
| Cascade de réponse multi-niveaux | ✅ **En service** | `app/services/chat_service.py` + `chat/handlers/` (ADR-0015) | Faible | Conserver |
| Corpus IVR validé (197 entrées) | ✅ **En service** | `dictionnaires/corpus_ivr.json`, `corpus_service.py` | Moyen — peuplement pgvector **manuel** | Automatiser l'import |
| Garde anti-invention du LLM | ✅ **En service** | `app/services/chat/llm_guard.py` (ADR-0039) | Faible | Conserver, étendre aux familles manquantes |
| Boucle de retour à l'agriculteur | ✅ **En service** | `app/services/chat/pending_answers.py` (ADR-0040) | Moyen — ne se referme pas en mode français | Lever le blocage FR |
| Météo agricole | ✅ **En service** | `app/services/weather.py` (ADR-0038) | Faible | Conserver |
| **Mode français** | 🟡 **Dégradé** | `chat/handlers/french_handler.py` — **aucune cascade IVR** | 🔴 **Élevé** — le corpus validé n'est jamais servi | **FR-1 (P0)** |
| TTS dioula | ✅ **En service** | `app/services/tts_dioula.py` + prosodie | 🔴 Élevé — **licence CC-BY-NC** | **LIC-1 (P0)** |
| ASR dioula | ✅ **En service** | `app/services/asr/chain.py`, 3 fournisseurs | 🔴 Élevé — **qualité non mesurée** | **DIO-1 (P0)** |
| Atelier de validation (LQE) | ✅ **En service** | `app/services/improvement_queue.py` (ADR-0031/0033) | Moyen | Mesurer le délai de traitement |
| Anonymisation / conformité PII | ✅ **En service** | `app/core/pii_utils.py`, ADR-0025 | Faible | Conserver |
| Limitation de débit | ✅ **En service** | `app/middleware/rate_limit.py` (ADR-0018) | Faible | Conserver |
| Provider baoulé (Bronze) | 🟡 **Partiel** | `app/services/baoule_provider.py` (#443 fermée) | Moyen | Poursuivre la collecte |
| ASR baoulé | 🟡 **Mesuré, non intégré** | benchmark 0003, ADR-0036 | Moyen | **BAO-2** |
| **Déclaration de langue baoulé** | ❌ **Absent** | #477 ouverte | 🔴 **Élevé** — rend tout le baoulé inutilisable | **BAO-1 (P0)** |
| NLU baoulé | ❌ **Absent** | #475 ouverte | Moyen | **BAO-3** |
| TTS baoulé | ❌ **Absent** | #476 ouverte | Moyen | **BAO-4** |
| Mesure de qualité en CI | ❌ **Absent** | `asr_quality/` vide ; 0 mention de couverture en CI | 🔴 **Élevé** | **QUA-1 / INF-1** |
| Sauvegarde automatisée | ❌ **Absent** | `pg_dump` seulement dans des procédures écrites | 🔴 **Élevé** — perte de données possible | **INF-2 (P0)** |
| Consentement enregistrements vocaux | ❌ **Absent** | `docs/compliance/` ne contient qu'`artci-logs.md` | 🔴 **Élevé** — juridique | **QUA-3 (P0)** |

## 2. Ce qui doit être conservé et consolidé AVANT tout nouveau développement

Conformément à la consigne (« identifier les fonctions existantes à conserver et améliorer
avant de proposer de nouveaux développements ») :

1. **La cascade et ses garde-fous** — l'architecture est saine ; elle doit être **étendue au
   mode français**, pas refaite.
2. **Le circuit de validation native** — il fonctionne et constitue l'actif différenciant du
   projet. Il faut en **mesurer le délai**, pas le remplacer.
3. **La discipline ADR** — à maintenir ; combler les trous de numérotation (0006, 0007, 0009)
   par une simple note.
4. **Le corpus IVR** — 197 entrées validées ; l'import pgvector doit cesser d'être manuel.

**Aucune reconstruction n'est proposée dans cette feuille de route.** Les chantiers P0 sont
tous des **consolidations** ou des **levées de risque**, pas des réécritures.

## 3. Backlog priorisé

**Règle de priorisation** : P0 = risque élevé non couvert ou blocage produit ·
P1 = valeur forte, risque maîtrisé · P2 = amélioration.

### P0 — à traiter dans les 4 premières semaines

| ID | Titre | Pourquoi P0 | Charge | Issue |
|---|---|---|---|---|
| **LIC-1** | Trancher la licence des poids ML | Bloque toute commercialisation ; identifié depuis ADR-0002, jamais tranché | 2 j (arbitrage, pas code) | — |
| **INF-2** | Sauvegarde automatisée + restauration testée | Perte de données possible aujourd'hui | 2 j | — |
| **DIO-1** | Exécuter le benchmark ASR dioula #0001 | Aucune référence chiffrée sur la langue principale | 4 j | #0001 |
| **FR-1** | Servir le corpus en mode français | Le travail de validation native n'atteint pas ces utilisateurs | 3 j | — |
| **QUA-3** | Document de consentement des enregistrements | Risque juridique sur les voix collectées | 2 j | ADR-0035 |
| **BAO-1** | Déclaration de langue baoulé | Débloque tout l'axe baoulé | 3 j | #477 |

### P1 — semaines 5 à 9

| ID | Titre | Valeur | Charge | Issue |
|---|---|---|---|---|
| **QUA-1** | Mesure de qualité linguistique en CI | Détecte les régressions automatiquement | 4 j | — |
| **BAO-2** | Fine-tune ASR baoulé (run complet + mesure) | Passe de 22,1 % CER à une base améliorée | 5 j | #474 |
| **INF-1** | Couverture de tests mesurée + seuil | Rend visible ce qui n'est pas testé | 2 j | — |
| **DIO-2** | Automatiser l'import corpus vers pgvector | Supprime une étape manuelle oubliable | 2 j | — |
| **AGR-1** | Mesurer le délai de traitement de l'atelier | La promesse « reviens me voir » en dépend | 2 j | ADR-0040 |
| **BAO-3** | NLU baoulé (texte vers concept) | Rend le baoulé fonctionnel | 4 j | #475 |

### P2 — semaines 10 à 12, ou report assumé

| ID | Titre | Charge | Issue |
|---|---|---|---|
| **QUA-2** | Séparation par locuteur et découpage versionné | 3 j | — |
| **DOC-1** | Resynchroniser CLAUDE.md et combler les trous ADR | 1 j | — |
| **AGR-2** | Formulation dioula de l'accusé et du rappel | 2 j | ADR-0039 |
| **INF-3** | Nettoyage des artefacts hors dépôt | 1 j | — |
| **BAO-4** | TTS baoulé | 5 j | #476 |

## 4. Issues ouvertes non reprises dans les 12 semaines

Sur les 43 issues ouvertes, celles portant les étiquettes `audit` (18) et `priority:P3` (8)
ne sont **pas** planifiées ici. Ce n'est pas un oubli : un développeur unique ne peut pas
absorber 43 sujets en 12 semaines. Elles restent au backlog et seront réexaminées à la revue
hebdomadaire ([07](07-modele-reporting-manager.md)).

**Décision à confirmer par le manager** : accepter que ces 26 issues restent en attente, ou
arbitrer un échange contre un chantier P1.
