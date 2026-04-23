# Contraintes & principes non-négociables — Wourri

Ce document extrait et consolide les règles durables du projet. Extraction depuis
[CLAUDE.md](../CLAUDE.md), [MEMORY.md](../../.claude/projects/c--Users-USER-PC-Documents-propre---moi-wourri/memory/MEMORY.md)
et les corrections récurrentes de l'utilisateur.

**Ces contraintes dominent toute autre considération.** Toute décision (ADR, plan,
code) qui entre en conflit avec une contrainte ici listée doit être remontée
à l'utilisateur avant exécution.

---

## 1. Qualité

### 1.1 Qualité > vitesse — JAMAIS l'inverse

La qualité prime toujours sur la vitesse de livraison. Aucune justification
("c'est un prototype", "on améliorera plus tard", "MVP") n'autorise un
raccourci sur la qualité du code, du corpus, du test, ou de l'architecture.

**Conséquence pour le code** :
- Production-ready dès la première livraison
- Tests obligatoires pour toute logique non-triviale
- Pas de TODO/FIXME laissés en l'état — ou ils bloquent la livraison

### 1.2 Pas de hardcoding

Aucune donnée métier dans le code Python :
- Pas de chemins de fichiers en dur dans les modules
- Pas de listes de mots / patterns / seuils inline
- Pas de magic numbers non documentés
- Tout paramétrable doit passer par `config.py` ou fichier externe (JSON/YAML)

### 1.3 SOLID + tests obligatoires

- Responsabilités séparées (une classe = un rôle clair)
- Injection de dépendances pour tout ce qui a un I/O (fichier, réseau, DB)
- Tests unitaires pour la logique, tests d'intégration pour les chaînes
- Coverage non mesurée en pourcentage, mais en chemins critiques couverts

---

## 2. Processus de décision

### 2.1 Investiguer avant de répondre

Ne jamais supposer le contenu d'un fichier. Lire avant de répondre ou modifier.
Vérifier qu'un code compile/fonctionne avant de dire "c'est fait".

### 2.2 Plan avant code

Pour tout changement non-trivial :
1. Lire et comprendre le code existant
2. Présenter un plan clair (fichiers concernés, comportement avant/après)
3. Attendre approbation explicite ("OKAY", "tu peux aller")
4. Coder exactement ce qui a été approuvé — rien de plus

### 2.3 ADR pour toute décision structurante

Avant tout code touchant :
- Stockage de données (BDD, VDB, cache)
- Modèles ML (ASR, TTS, NLU, embeddings)
- Stack technique (framework, langage, infra)
- Nouveau service ou intégration externe
- Protocole réseau / API publique

→ Rédiger un ADR (template : `docs/adr/0000-template.md`) avec options, trade-offs,
décision justifiée. Validation utilisateur obligatoire avant exécution.

### 2.4 Ne jamais agir sans approbation

Les modifications non demandées ou "améliorations" spontanées sont interdites.
Si l'intention est ambiguë, présenter le plan et attendre confirmation.

---

## 3. Anti-patterns bannis

### 3.1 Pas de sur-ingénierie

- Pas de features au-delà de ce qui est demandé
- Pas de refactoring hors périmètre de la tâche
- Pas de docstrings/commentaires sur du code non modifié
- Pas de gestion d'erreurs pour des scénarios impossibles
- Pas d'abstraction prématurée ("on pourrait en avoir besoin plus tard")

### 3.2 Pas de raccourci

- Pas de mock en production
- Pas de valeur par défaut fantaisiste pour masquer un bug
- Pas de `try/except: pass` silencieux
- Pas de skip-test pour faire passer la CI

### 3.3 Pas d'invention linguistique

- Tout mot dioula/bambara ajouté doit être validé depuis une source fiable
  (An Ka Taa, Bayelemabaga, Koumankan, Findora, agri_vocab.md)
- Jamais de mot inventé ou dérivé par analogie sans validation
- Vocabulaire agricole validé : voir MEMORY.md

---

## 4. Règles projet spécifiques

### 4.1 Langue cible

Dioula ivoirien (code ISO `dyu`), **pas** bambara malien (`bam`).
Distinctions lexicales critiques :
- `kalo` (mois) ≠ `karo` (Mali)
- `lɔgɔ` (marché CI) ≠ `sugu` (Mali)
- `filɛ` (regarder CI) ≠ `lajɛ` (Mali)
- Suffixe diminutif : `-nin` (CI) vs `-len` (Mali)
- Grammaire SOV stricte, verbe en fin de phrase

### 4.2 Langue de communication avec l'utilisateur

Toujours français. Utilisateur francophone basé en Côte d'Ivoire.

### 4.3 Self-verification avant livraison

Avant de déclarer un travail terminé :
1. Relire chaque fichier modifié
2. Vérifier qu'aucune info n'a été supprimée par erreur
3. Lancer tests ou serveur pour confirmer
4. Si changement corpus bambara/dioula : tester TTS avec curl

Jamais dire "c'est fait" sans preuve concrète.

---

## 5. Posture assistant IA (Claude)

Extrait des corrections récurrentes de l'utilisateur — comportements à tenir
en permanence :

- **Poser les questions stratégiques AVANT de proposer une solution**, pas après
- **Défier les demandes qui contredisent les principes ici listés**, même si
  l'utilisateur les formule avec insistance (ex: "rapidement", "en attendant")
- **Surfacer les trade-offs mesurés, pas les intuitions** — si je n'ai pas de
  mesure, je dois le dire explicitement
- **Refuser d'inventer du contenu** (code, vocabulaire, chiffres) par défaut ;
  demander les sources ou la validation utilisateur
- **Ne jamais m'oublier** : chaque décision structurante doit repasser par ce
  document et par les ADR. Le passé du projet n'est pas un argument pour
  reproduire une erreur.

---

**Dernière révision** : 2026-04-21 (création initiale)
**Règle** : toute modification de ce fichier passe par un ADR.
