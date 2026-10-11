# 03 — Audit linguistique et ML

**Date** : 2026-10-11 · Dioula et baoulé traités **séparément**, comme demandé.

---

## PARTIE A — DIOULA

### A.1 Ce qui est en service

✅ **CONFIRMÉ**

| Brique | Implémentation | Fichier |
|---|---|---|
| Corpus IVR | **197 entrées** validées, servies via PostgreSQL + pgvector | `dictionnaires/corpus_ivr.json`, `app/services/corpus_service.py` |
| NLU | **60 concepts**, extraction par mots-clés + classification d'intention | `app/services/nlu/` |
| ASR | Chaîne à 3 fournisseurs composables | `app/services/asr/chain.py` |
| TTS | `facebook/mms-tts-dyu` + prosodie dédiée | `app/services/tts_dioula.py` |
| Traduction | NLLB-200 distilled 600M + DeepSeek + dictionnaire + scoring | `app/services/translation/` |

### A.2 Le point le plus important : aucune qualité dioula n'est mesurée

🔴 **CONFIRMÉ** — `docs/benchmarks/0001-asr-dioula-evaluation.md` porte en en-tête :

> **Statut** : proposé, **en attente de validation Ruben avant exécution**

Le document définit un protocole sérieux (WER principal via `jiwer`, CER secondaire, mesure de
la dégradation 8 kHz vs 16 kHz, 20 audios minimum, évaluation humaine). **Il n'a jamais été
exécuté.** Aucun fichier de résultats dioula n'existe, alors que le baoulé en a un
(`0003-asr-baoule-evaluation-results.md`).

**Conséquence directe** : le dioula est une **référence fonctionnelle** — il tourne, des
agriculteurs l'utilisent — mais **pas une référence chiffrée**. Toute affirmation du type
« le dioula marche bien » est aujourd'hui **invérifiable**. On ne peut ni prouver une
amélioration, ni détecter une régression, ni comparer un nouveau modèle à l'existant.

C'est le **chantier numéro 1** de la feuille de route (DIO-1).

### A.3 Validation linguistique — un vrai point fort

✅ **CONFIRMÉ** — Le projet applique une règle explicite : **un LLM ne déclare jamais une
phrase correcte** (ADR-0031). La hiérarchie est **locuteur natif > GRAMMAIRE_DIOULA_REGLES.md**,
et le dioula ivoirien est distingué du bambara malien (lɔgɔ et non sugu, tuma et non waati,
kalo et non karo).

Le commit `1332c8b` (« appliquer la validation native du 2026-10-07 ») montre que ce circuit
**fonctionne réellement** : une validation humaine datée se traduit en modification du NLU.

### A.4 Jeux de données disponibles

✅ **CONFIRMÉ** — `data/hf_datasets/` : `koumankan_dyu_fr.json`, `findora_fr_dioula.json`,
`francophonia_bambara_french.json`. Audios de test TTS sous `data/tts_test_axe1/`.
Common Voice `dyu` v24.0 présent **hors dépôt**, à la racine du dossier de travail.

🔍 **À VÉRIFIER** — La **séparation par locuteur** entre entraînement et évaluation n'a pas pu
être contrôlée : aucun découpage versionné ne l'atteste. Sans elle, une mesure future serait
**optimiste et donc fausse**.

---

## PARTIE B — BAOULÉ

### B.1 Ce qui existe — mieux instrumenté que le dioula

✅ **CONFIRMÉ** — Le baoulé dispose de **chiffres mesurés**, ce qui n'est pas le cas du dioula.
Source : `docs/benchmarks/0003-asr-baoule-evaluation-results.md`.

| Modèle | Paramètres | **CER** | WER | n | Verdict |
|---|---|---|---|---|---|
| Omnilingual ASR CTC 300M | 300M | 26,0 % | 67,6 % | 290 | viable |
| **Omnilingual ASR CTC 1B** | **1B** | **22,1 %** | **56,7 %** | **290** | ✅ **retenu** |

Le choix du **CER comme métrique principale** est justifié dans le protocole : le baoulé est
une langue **peu écrite**, à orthographe variable — le WER y pénalise des variantes
acceptables. Raisonnement correct et rarement explicité.

✅ **CONFIRMÉ** — ADR-0036, **accepté** : le **1B** est retenu comme base de fine-tuning (#474).

### B.2 Pipeline d'entraînement

✅ **CONFIRMÉ** — Versionné sous `finetune/colab/` sur `APIPy` : 7 notebooks, dont
`omnilingual_finetune_smoke_test.ipynb`, `asr_baoule_benchmark.ipynb` et
`sync_smoke_test_notebook.py` (synchronisation notebook vers script).

✅ **CONFIRMÉ** — `docs/benchmarks/0005-omnilingual-finetune-smoke-test.md` documente un test
mécanique (100 étapes, lr 1e-5, échauffement progressif) et **se garde explicitement de
conclure** : une baisse de la perte ou de l'UER y est qualifiée de « bon signe, pas un
critère ». C'est de la rigueur méthodologique réelle.

✅ **CONFIRMÉ** — Données : Common Voice `bci`, miroir `Klayt/baoule-common-voice`, avec
**révision épinglée** — condition nécessaire à la reproductibilité.

### B.3 État des travaux

| Issue | Sujet | État |
|---|---|---|
| #472 | EPIC pipeline vocal baoulé bout-en-bout | ouverte |
| #473 | Benchmark ASR | ouverte (résultats publiés) |
| #474 | Fine-tune ASR | ouverte (essai mécanique passé) |
| #475 | NLU baoulé (texte vers concept) | ouverte |
| #476 | TTS baoulé fine-tuné | ouverte |
| #477 | Accueil : déclaration de langue | ouverte |
| #443 | Provider JSON Bronze | **fermée** |

✅ **CONFIRMÉ** — `app/services/baoule_provider.py` : validation JSON vers **Bronze
uniquement**, n'écrit jamais pgvector, et **aucun contenu baoulé n'y est inventé**. Le
cloisonnement avec le corpus dioula est **délibéré et respecté**.

🔴 **Dépendance bloquante produit** — **#477 (déclaration de langue)**. Tant qu'un utilisateur
ne peut pas se déclarer baoulophone, **aucun** travail ASR/TTS baoulé n'atteint un agriculteur :
le moteur ne détecte pas la langue de lui-même. Un modèle à CER 22 % sans porte d'entrée vaut,
pour l'utilisateur final, exactement zéro.

---

## PARTIE C — RISQUES TRANSVERSES ML

### C.1 Licence non commerciale — risque juridique confirmé, non tranché

🔴 **CONFIRMÉ par le dépôt lui-même** :

| Source | Citation (extrait) |
|---|---|
| `docs/adr/0034-atelier-parite-linguistique.md:18` | « Les poids **MMS = CC-BY-NC** (non commercial) » |
| `docs/adr/0034-atelier-parite-linguistique.md:74` | « **Dettes tracées** : (1) licence MMS **non-commerciale** » |
| `docs/adr/0002-ajout-provider-omnilingual.md:126` | « **Question licence MMS-dyu non tranchée** » |
| `docs/adr/0003-plan-ajout-omnilingual.md:221` | « Question licence MMS-dyu (CC-BY-NC vs produit payant) » |

La **voix dioula en production** (`facebook/mms-tts-dyu`) et la traduction
(`facebook/nllb-200-distilled-600M`) reposent sur des poids dont le projet signale lui-même le
caractère **non commercial**. Le sujet est identifié depuis plusieurs ADR et **reste ouvert**.

🔍 **À VÉRIFIER** — hors périmètre de cette mission : les termes exacts applicables à chaque
poids utilisé et au modèle économique visé. Cela demande une **source à jour** et un **avis
juridique**, non une lecture de code.

> **C'est le risque le plus lourd du projet.** Il ne se manifeste pas tant que le produit
> n'est pas commercialisé — puis il bloque **tout**. Il doit être tranché **avant** toute
> facturation, pas après.

### C.2 Aucune mesure de qualité exécutable depuis l'application

❌ **ABSENT** — `app/services/asr_quality/` **ne contient aucun fichier source** (uniquement un
`__pycache__/`). Une recherche de `WER`, `CER`, `jiwer` dans `app/`, `scripts/` et `tests/` ne
remonte qu'une mention dans `app/config.py`.

Les mesures existent **uniquement dans des notebooks**, donc **hors de la CI** : aucune
régression de qualité linguistique ne peut être détectée automatiquement.

### C.3 Suivi de version des modèles

🟡 **PARTIEL** — `app/services/model_registry.py` existe et gère le préchargement
(ADR-0011). 🔍 **À VÉRIFIER** : qu'il enregistre la **révision exacte** du modèle servie en
production. Sans cela, un résultat mesuré ne peut pas être rattaché à un artefact précis, et
une comparaison avant/après perd sa valeur.

### C.4 Reproductibilité d'une expérience

| Facteur | État |
|---|---|
| Révision de dataset épinglée | ✅ favorable (benchmark 0003) |
| Versions de bibliothèques figées | ✅ favorable (benchmark 0002 : torch 2.8.0, etc.) |
| Synchronisation notebook vers script | ✅ favorable (`sync_smoke_test_notebook.py`) |
| Graine aléatoire versionnée | 🔍 non trouvée |
| Découpage train/test versionné | 🔍 non trouvé |
| Copie obsolète du pipeline hors dépôt | ⚠️ `finetune/` racine, daté de mars 2026 — risque d'exécution par erreur |

### C.5 Synthèse comparative des deux langues

| Critère | Dioula | Baoulé |
|---|---|---|
| En production | ✅ oui | ❌ non |
| Qualité **mesurée** | ❌ **aucune** | ✅ CER 22,1 % (n=290) |
| Décision de modèle tracée | 🟡 partielle | ✅ ADR-0036 accepté |
| Corpus validé natif | ✅ 197 entrées | 🟡 Bronze en collecte |
| Porte d'entrée utilisateur | ✅ oui | ❌ **bloquée (#477)** |

**Lecture** : les deux langues ont des manques **opposés**. Le dioula a des utilisateurs mais
pas de mesure ; le baoulé a une mesure mais pas d'utilisateurs. La feuille de route traite les
deux par leur point faible respectif.
