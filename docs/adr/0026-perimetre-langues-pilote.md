# ADR-0026 — Périmètre des langues pour le pilote

**Statut** : accepté
**Date** : 2026-08-13
**Auteur** : Marcel Djedje-Li
**Valideur** : Manager Général (à confirmer en restitution du 17/08)
**Contexte** : semaine Focus Dev 11 au 16 août, porte de validation G08

---

## Contexte

La feuille de route prévoit deux benchmarks de reconnaissance vocale pour la
porte G08 : LNG-02 pour le dioula et LNG-03 pour le baoulé, chacun devant
produire une décision GO ou FALLBACK documentée.

L'audit du dépôt réalisé le 13 août établit les faits suivants.

### Dioula

La chaîne déclare trois fournisseurs (`app/services/asr/__init__.py`) : NeMo
Soloni, MMS-dyu fine-tuné, et MMS générique en dernier recours.

- Le fournisseur **NeMo** est indisponible : le paquet `nemo` n'est ni dans
  `requirements.txt` ni dans `Dockerfile.prod`.
- Le fournisseur **MMS-dyu**, seul modèle spécifique au dioula de Côte d'Ivoire,
  ne se charge pas : le fichier de poids `model.safetensors` (environ 3,86 Go)
  est absent du dépôt de travail. Le motif `*.safetensors` étant dans
  `.gitignore`, ce fichier n'a jamais été versionné et n'existe que sur la
  machine ayant réalisé l'entraînement.
- Aggravant : `is_available()` ne teste que l'existence du **répertoire**
  (`mms_dyu_provider.py:50`), lequel contient les fichiers de configuration. Le
  fournisseur se déclare donc disponible, échoue au chargement, et la chaîne
  bascule silencieusement sur le modèle générique.

Conséquence : en l'état, **100 % de l'audio dioula est transcrit par
`facebook/mms-1b-all`**, un modèle générique entraîné sur du bambara malien, et
non par un modèle dioula ivoirien.

### Baoulé

Aucun élément baoulé n'existe dans le projet : ni fournisseur de reconnaissance
vocale, ni jeu de données, ni dictionnaire, ni entrée de configuration. La
recherche sur l'ensemble de `app/`, `tests/` et `dictionnaires/` ne retourne
aucune occurrence.

### Corpus d'évaluation

Le dépôt contient 44 fichiers audio, tous issus de la **synthèse vocale**
(`data/tts_test_axe1/`, `data/tts_e2e_axe5/`). Il n'existe aucun enregistrement
de parole humaine dioula transcrit. Le script `finetune/evaluate_wer.py` indique
lui-même qu'en l'absence d'audio réel il simule la mesure sur du texte seul.

Un taux d'erreur mesuré sur de la voix synthétique ne mesure pas la performance
en conditions réelles : il évalue la capacité du modèle à transcrire une autre
machine.

## Décision

**1. Le baoulé sort du périmètre du pilote.** LNG-03 n'est pas livrable : il n'y
a ni modèle, ni données, ni corpus pour le construire dans le temps imparti. La
porte G08 est donc traitée sur le seul dioula. La reprise du baoulé fera l'objet
d'une planification distincte, incluant la constitution d'un corpus.

**2. NeMo est retiré du périmètre du pilote.** Le fournisseur reste déclaré dans
le code mais son indisponibilité est explicite et journalisée. Installer le
`nemo-toolkit` n'est pas justifié avant que le modèle dioula spécifique soit
opérationnel et mesuré.

**3. Aucune mesure de performance dioula ne sera publiée sans corpus de parole
humaine.** Si le corpus d'évaluation réel n'est pas disponible avant la
restitution, G08 est présentée comme une décision de repli assumée, accompagnée
d'un plan de collecte, et non comme un résultat mesuré.

**4. Le modèle générique ne sera jamais présenté comme du dioula ivoirien.**
Toute démonstration précise quel modèle produit la transcription.

## Conséquences

### Positives

- La restitution du 17 août repose sur des faits vérifiables plutôt que sur une
  mesure fabriquée.
- La dégradation silencieuse est rendue visible par un test de disponibilité
  réelle, non mocké, ajouté en parallèle de cette décision.
- Le périmètre annoncé au CNRA et à la SODEXAM correspond à ce qui fonctionne.

### Négatives

- Deux tâches de la feuille de route, LNG-03 et une partie de LNG-02, ne seront
  pas livrées à la date prévue.
- La promesse multilingue du produit est temporairement réduite au dioula et au
  français.

### Neutres

- Le socle de gouvernance linguistique construit côté Convex (corrections
  versionnées, glossaire, corpus, journal d'audit) est indépendant du modèle de
  reconnaissance et reste pleinement opérationnel.

## Suivi

- Obtenir de l'équipe le fichier de poids `model.safetensors` ou l'archive
  d'entraînement.
- Constituer un corpus d'évaluation dioula de 30 à 50 énoncés agricoles
  enregistrés par un locuteur natif, avec transcription.
- Rejouer la mesure et convertir cette décision en résultat mesuré.
- Planifier le baoulé dans un cycle ultérieur, corpus d'abord.

## Références

- Issue #358, chaîne dioula réduite au modèle générique.
- `docs/AUDIT_DIOULA_2026-08.md`, sections 3 et 7.1.
- Feuille de route Focus Dev, LNG-02, LNG-03, porte G08.
