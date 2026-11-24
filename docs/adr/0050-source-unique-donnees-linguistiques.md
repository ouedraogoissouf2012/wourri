# ADR-0050 — Source unique des données linguistiques : PostgreSQL

**Statut** : accepté
**Date** : 2026-11-17
**Décideur** : Ouedraogo Issouf
**Prolonge** : [ADR-0001](0001-choix-stockage-donnees.md) (PostgreSQL + pgvector, validé le 2026-04-21),
[ADR-0008](0008-plan-migration-chromadb-pgvector.md) (migration ChromaDB → pgvector)

---

## 1. Contexte

### 1.1 La décision existe déjà

L'ADR-0001, validé le 2026-04-21, a retenu PostgreSQL + pgvector comme **store
unifié**, avec cette justification : « un seul store couvre corpus IVR + vecteurs
+ profils utilisateurs + billing + historique conversationnel. **Pas de
synchronisation inter-store, pas de bug de cohérence.** »

Le présent ADR ne choisit pas une architecture : il constate que celle-ci n'est
pas appliquée, et décide **comment l'appliquer et comment empêcher qu'elle dérive
à nouveau**.

### 1.2 L'état réel au 2026-11-17

| Donnée | Où elle vit | Conforme à ADR-0001 |
|---|---|---|
| Corpus IVR dioula — 197 entrées | `corpus_entries` (PostgreSQL + pgvector) | oui |
| Corpus IVR baoulé — 193 entrées | `dictionnaires/corpus_ivr_bci.json`, chargé en mémoire | **non** |
| Concepts NLU — 61 | `dictionnaires/nlu_concepts.json` + table `nlu_concepts` | partiellement |
| Concepts NLU baoulé — 39 | `dictionnaires/nlu_concepts_bci.json` | **non** |
| Relecture mots-clés baoulé — 46 | `dictionnaires/relecture_mots_cles_bci.json` | **non** |
| Dictionnaire bambara-français — 11 331 entrées, 3,2 Mo | `dictionnaires/bambara_francais.json` | **non** |
| Messages système | `dictionnaires/messages_systeme_sources.json` | **non** |
| Corrections et règles ASR — 15 | `dictionnaires/asr_*.json` | **non** |
| Calendriers culturaux — 13 | `app/data/calendrier_agricole.py` (module Python) | **non** |
| Zones agricoles — 4, localités — 59 | `app/data/zones_agricoles.py`, `cities.py` | **non** |

**Total hors base : environ 3,6 Mo de contenu linguistique**, réparti sur onze
fichiers JSON et trois modules Python.

### 1.3 Pourquoi la dérive a eu lieu

Rien ne l'empêchait. L'ADR-0001 est un document ; aucun contrôle automatique ne
vérifie qu'une nouvelle langue passe par la base. Le baoulé a été livré vite, en
rechargeant un fichier — ce qui marchait, et qui n'a déclenché aucune alerte.

**C'est le point central de cet ADR** : une règle qui n'est pas vérifiée par la
machine est une règle qui sera contournée sous pression de délai.

### 1.4 Le coût mesuré de la non-conformité

Mesures du 2026-11-16 (`docs/` — étude de robustesse) :

| Taille du corpus baoulé | Durée d'une recherche |
|---|---|
| 193 — aujourd'hui | 64 ms |
| 1 000 | 288 ms |
| 5 000 | 1 126 ms |

La recherche baoulé balaie le corpus en mémoire et recalcule ses trigrammes à
chaque requête : **74 % du temps est du recalcul**. Le dioula, lui, passe par un
index vectoriel et ne paie pas ce prix.

---

## 2. Questions posées et réponses

Arbitrages du 2026-11-17 :

| Question | Réponse |
|---|---|
| Quel périmètre ? | **Tout contenu linguistique** — corpus, NLU, messages système, dictionnaires, calendriers, corrections ASR |
| Que devient le fichier versionné ? | **La base devient la vraie source.** Priorité absolue : ne perdre aucune donnée existante |
| Comment faire respecter la règle ? | **Contrôle automatique en intégration continue** |

---

## 3. Le fait qui complique : deux corpus, deux modèles de recherche

Les corpus dioula et baoulé ne partagent que **quatre champs sur dix**. Ce ne
sont pas deux traductions d'une même structure.

| | Dioula | Baoulé |
|---|---|---|
| Indexé par | intention × cultures | la question elle-même |
| Recherche | vecteur sur un texte-document | similarité de trigrammes sur la question |
| Champs propres | `conditions`, `phrases_attestees`, `score_validation`, `tags` | `question_locale`, `audio_reponse`, `filiere`, `appariement` |
| Champs communs | `id`, `intent`, `cultures`, `reponse_fr` | idem |

De plus, la table `corpus_entries` **n'a pas de colonne `langue`** : sa colonne
de réponse s'appelle `reponse_bambara`. Elle est monolingue par construction.

Unifier n'est donc pas ajouter une ligne : c'est décider quel modèle de
recherche porte les deux langues, et la troisième.

### 3.1 Toute donnée linguistique n'appelle pas un vecteur

Précision nécessaire pour éviter une mauvaise mise en œuvre : « tout en base »
ne signifie pas « tout avec un embedding ».

| Nature | Accès réel | Besoin d'un index vectoriel |
|---|---|---|
| Corpus IVR (question → réponse) | recherche par le sens | **oui** |
| Dictionnaire bambara-français (11 331 entrées) | consultation par clé | non — index B-tree |
| Calendriers, zones, localités | lecture par identifiant | non |
| Corrections ASR, règles de normalisation | application séquentielle | non |
| Messages système | lecture par rôle | non |

Appliquer un embedding à 11 331 entrées de dictionnaire coûterait du calcul et
de l'espace sans rien apporter : la consultation s'y fait par clé exacte.

---

## 4. Options étudiées

### Option A — Colonne `langue` ajoutée à `corpus_entries`

Ajouter `langue`, renommer `reponse_bambara` en `reponse_locale`, ajouter les
champs baoulé en colonnes nullables (`question_locale`, `audio_reponse`,
`filiere`).

| | |
|---|---|
| Volume migré | 193 lignes baoulé ; 197 lignes dioula renommées sur place |
| Code applicatif touché | `corpus_service`, `baoule_ivr`, les deux scripts d'import |
| Risque sur la production dioula | **réel** — renommage de colonne sur une table servie |
| Charge estimée | 4 j |
| Tient à la 3ᵉ langue | mal — chaque langue ajoute ses colonnes nullables |

### Option B — Une table par langue

`corpus_dyu`, `corpus_bci`, puis `corpus_bet`.

| | |
|---|---|
| Volume migré | 193 lignes ; le dioula n'est pas touché |
| Risque sur la production dioula | **nul** |
| Charge estimée | 3 j |
| Tient à la 3ᵉ langue | non — duplication du schéma, de l'index et du code à chaque langue |

### Option C — Schéma linguistique normalisé

Trois entités : `langue`, `enonce` (un texte, sa langue, son rôle, son média),
`reponse` (reliant un concept à ses énoncés). Le corpus devient une relation,
pas une table par langue.

| | |
|---|---|
| Volume migré | 390 lignes, réécrites dans le nouveau schéma |
| Code applicatif touché | `corpus_service`, `baoule_ivr`, imports, atelier LQE |
| Risque sur la production dioula | **élevé** — tout le chemin de réponse dioula est réécrit |
| Charge estimée | 9 j |
| Tient à la 3ᵉ langue | **oui** — une langue n'ajoute que des lignes, jamais de colonne |

### Option D — Import automatisé, fichiers conservés comme source

Les fichiers JSON restent la source versionnée ; un import automatique les
pousse en base à chaque déploiement.

| | |
|---|---|
| Charge estimée | 2 j |
| Tient à la 3ᵉ langue | oui |
| Conforme à la demande du 2026-11-17 | **non** — la base ne devient pas la vraie source |

Option écartée d'emblée : elle contredit l'arbitrage rendu. Elle est documentée
parce qu'elle a un mérite réel — la relecture du contenu linguistique en PR,
traitée en section 6.

---

### Option E — Le schéma normalisé de l'option C, migré en deux temps

Même cible que l'option C, mais l'ordre de migration retire son unique objection.

**Phase 1 — le baoulé.** On crée le schéma cible, on y migre les 193 entrées
baoulé, on bascule le chemin baoulé. Le dioula n'est pas touché et continue de
tourner sur `corpus_entries`. La langue non conforme est réparée, et le schéma
définitif existe dès le premier jour.

**Phase 2 — le dioula.** On migre les 197 entrées dans le même schéma, avec une
vérification exhaustive — 197 lignes se comparent une par une, pas par
échantillon. `corpus_entries` n'est retirée qu'après la bascule vérifiée.

| | |
|---|---|
| Volume migré | 193 puis 197 lignes |
| Risque sur la production dioula | **reporté et isolé** — le dioula n'est touché qu'en phase 2, sur un schéma déjà éprouvé par 193 entrées |
| Charge estimée | 5 j + 4 j |
| Tient à la 3ᵉ langue | **oui** — une langue n'ajoute que des lignes |
| Réversibilité | phase 2 réversible tant que `corpus_entries` subsiste |

Le périmètre est séquencé de la même façon : les corpus IVR d'abord, puis NLU et
messages système, puis dictionnaire et calendriers. Traiter les 3,6 Mo d'un seul
tenant transformerait neuf jours en vingt-cinq.

---

## 5. Comparatif

| Critère | A — colonne langue | B — table par langue | C — normalisé | D — import auto | **E — normalisé, séquencé** |
|---|---|---|---|---|---|
| Respecte l'arbitrage du 17/11 | oui | oui | oui | **non** | **oui** |
| Risque sur le dioula en production | moyen | nul | élevé | nul | **reporté et isolé** |
| Survit à la 3ᵉ langue sans refonte | non | non | oui | oui | **oui** |
| Charge estimée | 4 j | 3 j | 9 j | 2 j | **5 j + 4 j** |
| Nombre de schémas à maintenir | 1 | N | 1 | 1 | **1** |
| Répare le baoulé avant de toucher le dioula | non | oui | non | oui | **oui** |
| Perte possible de données | aucune | aucune | aucune si vérifiée | aucune | **aucune — vérification exhaustive** |

---

## 6. Le point à ne pas perdre de vue : la relecture linguistique

Aujourd'hui, une correction du locuteur baoulé apparaît dans un diff de PR. Les
70 réenregistrements de novembre ont été relus ainsi, entrée par entrée.

Faire de la base la seule source supprime cette relecture. Ce n'est acceptable
qu'à une condition, qui fait partie de la décision :

> **Toute modification de contenu linguistique en base doit laisser une trace
> consultable et réversible** — soit par l'atelier LQE, qui historise déjà les
> validations, soit par un export versionné produit automatiquement.

Sans cette condition, on échange un risque de désynchronisation contre un risque
de modification silencieuse. Le second est pire.

---

## 7. Décision

### **Option E retenue** — schéma normalisé, migré en deux temps

Validée par Ouedraogo Issouf le 2026-11-17.

**Justification, dans l'ordre de poids.**

**Elle est la seule à répondre au motif de la demande.** L'objectif posé est de ne
plus tout refaire à chaque ajout. Les options A et B recommencent à chaque langue
— A ajoute des colonnes nulles, B duplique le schéma, l'index et le code. Seul un
schéma où une langue n'ajoute que des lignes tient à la troisième.

**Elle répare d'abord ce qui est cassé.** Le baoulé est la langue non conforme ;
c'est elle qui migre en premier. Le dioula, qui respecte déjà l'ADR-0001 et sert
en production, n'est touché qu'ensuite.

**Elle retire l'unique objection faite à l'option C.** Le risque portait sur la
réécriture du chemin dioula. Le séquencement le reporte en phase 2, sur un schéma
déjà éprouvé par 193 entrées, et le rend réversible tant que `corpus_entries`
subsiste.

**La vérification est exhaustive, pas statistique.** 390 lignes au total : chaque
entrée est comparée avant et après. Ce protocole a été appliqué deux fois sur ce
corpus en novembre 2026 et a détecté des écarts réels.

### Mise en œuvre

| Phase | Portée | Suivi |
|---|---|---|
| 1 | corpus baoulé — 193 entrées | issue #623 |
| 2 | corpus dioula — 197 entrées | issue #624 |
| 3 | NLU, messages, dictionnaire, calendriers | issue #625 |

### Amendement du 2026-11-24 — la source reste le fichier relu, la base en est la copie servie

Validé par Ouedraogo Issouf le 2026-11-24, **en renversement de l'arbitrage du
2026-11-17** qui faisait de la base la source de vérité.

Le §7 retenait l'option E pour le **schéma**, et cela ne change pas. Ce qui
change est la **source** : le fichier relu en PR reste l'artefact validé, et la
base en est la copie servie, tenue à jour automatiquement. C'est l'option D pour
la source, l'option E pour le schéma.

**Pourquoi ce renversement.** La mise en œuvre de la phase 1 a rendu visible ce
que l'arbitrage du 17 novembre ne pouvait pas peser : faire de la base la source
supprime la relecture en PR du contenu linguistique. Or la PR est **le dernier
endroit où un humain voit une phrase baoulé ou dioula avant qu'un agriculteur
l'entende**. La règle cardinale du projet — rien d'inventé, validation par un
locuteur natif (ADR-0014, ADR-0031, ADR-0046) — perd son dernier garde-fou
automatique si ce point de passage disparaît. Le §6 de cet ADR le reconnaissait
déjà : la relecture en PR est le seul mérite réel de l'option D. Il s'est avéré
décisif.

**Ce qui empêche la copie de dériver.** Le reproche fait à l'option D était
l'oubli de l'import, déjà constaté en production. Il est levé par la
synchronisation automatique : **le moteur applique lui-même le contenu** dès
qu'il constate une empreinte différente, à la première requête de la langue
concernée — jamais au démarrage, `app/main.py` étant à zéro ligne de marge sous
le plafond de l'ADR-0051. L'application se fait sous verrou consultatif
PostgreSQL, en une transaction, hors de la boucle d'exécution, et chaque écriture
est historisée.

Il n'y a donc **aucun geste humain à oublier** : la décision humaine est le merge
de la PR, exactement comme pour le code. Un contrôle d'intégration continue exige
par ailleurs que la base synchronisée depuis le fichier courant soit égale, entrée
par entrée, au fichier lui-même.

**Ce qui reste vrai de l'option E.** Le schéma normalisé, la migration en deux
temps, la réversibilité tant que `corpus_entries` subsiste, et la condition posée
au §6 : toute modification de contenu linguistique en base laisse une trace
consultable et réversible.

---

## 8. Conséquences attendues

- **La règle devient vérifiable** : un contrôle d'intégration continue refuse
  toute PR qui introduit un chargement de contenu linguistique depuis un fichier,
  et exige l'égalité entre le fichier relu et la base synchronisée.
- **Le peuplement manuel disparaît.** Aujourd'hui, `scripts/import_corpus_ivr.py`
  doit être lancé à la main après toute modification du corpus — oubli déjà
  constaté en production. La synchronisation par le moteur le supprime, sans
  remplacer l'oubli d'un script par l'oubli d'un autre.
- **Les scripts hors ligne ne sont pas repris** : `baoule_nlu_build.py` continue
  d'écrire le fichier relu en PR, qui reste l'artefact validé (amendement du
  2026-11-24). Il n'écrit pas en base.
- **La recherche ne change pas en phase 1.** Elle garde son algorithme et ses
  seuils : la base devient la source des données, pas le moteur de recherche.
  C'est la condition pour que les 193 réponses servies restent identiques.

### Ce qui reste hors périmètre

- L'atelier LQE est **déjà** en PostgreSQL (ADR-0034) : il n'est pas concerné.
- Les modèles ML (ASR, embeddings) restent en volume monté, pas en base.

---

## 9. Historique

| Date | Évolution |
|---|---|
| 2026-11-17 | Rédaction. Statut **proposé**. Arbitrages de périmètre, de source de vérité et d'application recueillis. Décision en attente. |
| 2026-11-17 | **Option E retenue** — schéma linguistique normalisé, migré en deux temps, baoulé puis dioula. Statut **accepté**. |
| 2026-11-24 | **Amendement : la source reste le fichier relu en PR**, la base en est la copie servie, synchronisée automatiquement par le moteur. Renverse l'arbitrage du 17/11 « la base devient la vraie source », qui aurait supprimé la relecture humaine du contenu linguistique avant mise en production — dernier garde-fou de la règle « rien d'inventé ». Le schéma reste celui de l'option E. Validé par Ouedraogo Issouf. |
| 2026-11-24 | **Correction de deux affirmations fausses du §8**, relevées pendant la mise en œuvre (#623). (1) « La recherche baoulé passe par un index, le coût de 64 ms disparaît » : faux deux fois. Un index trigramme ou vectoriel changerait les réponses servies et relève d'une décision séparée avec A/B ; et les 64 ms étaient surévaluées d'un facteur 2,6 à 4,2 — la mesure refaite donne ≈ 1 ms en médiane sur une requête typique, ≈ 15 ms pour un balayage complet des 193 entrées. (2) « `baoule_nlu_build.py` devra écrire en base » : il continue d'écrire le fichier relu, par l'amendement ci-dessus. |
